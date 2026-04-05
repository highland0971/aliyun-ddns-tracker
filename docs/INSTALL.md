# DDNS Heartbeat Service - 安装指南

## 系统要求

### 服务端（阿里云 ECS）
- Ubuntu 20.04+ / Debian 11+
- Python 3.8+
- 1 Core, 256MB RAM, 1GB 存储
- 公网 IP（用于接收心跳）

### 客户端（LXC 容器）
- Debian 11+ / Ubuntu 20.04+
- Python 3.8+
- 1 Core, 128MB RAM, 512MB 存储
- 可访问互联网（获取公网 IP）

---

## 服务端部署

### 1. 安装依赖

```bash
apt-get update
apt-get install -y python3 python3-pip sqlite3
```

### 2. 部署代码

```bash
mkdir -p /opt/ddns-heartbeat
# 解压代码到 /opt/ddns-heartbeat/
```

### 3. 创建配置文件

```bash
mkdir -p /etc/ddns-heartbeat
cat > /etc/ddns-heartbeat/server.json5 << 'EOF'
{
  // 服务端端口
  "port": 8989,
  
  // 域名:APIKey 映射（一个域名一个 APIKey）
  "domains": {
    "your-domain.com": "your-secure-api-key-here"
  }
}
EOF

# 设置权限（仅 root 可读）
chmod 600 /etc/ddns-heartbeat/server.json5
```

### 4. 配置环境变量（阿里云凭证）

```bash
# 方式 1：systemd 服务文件（推荐）
# 编辑 /etc/systemd/system/ddns-server.service
# 添加：
# Environment="ALIYUN_ACCESS_KEY_ID=your-key-id"
# Environment="ALIYUN_ACCESS_KEY_SECRET=your-key-secret"

# 方式 2：环境变量文件
cat > /etc/ddns-heartbeat/server.env << 'EOF'
ALIYUN_ACCESS_KEY_ID=your-key-id
ALIYUN_ACCESS_KEY_SECRET=your-key-secret
EOF

chmod 600 /etc/ddns-heartbeat/server.env
```

### 5. 安装 systemd 服务

```bash
cp /opt/ddns-heartbeat/systemd/ddns-server.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable ddns-server
systemctl start ddns-server
systemctl status ddns-server
```

### 6. 验证服务

```bash
# 健康检查
curl http://localhost:8989/health

# 预期输出
{
  "status": "healthy",
  "timestamp": "2026-04-05T18:00:00.000000",
  "port": 8989,
  "banned_ips": 0,
  "rate_limiter_ips": 0
}
```

### 7. 配置防火墙

```bash
# 允许心跳上报端口
ufw allow 8989/tcp

# 如启用 HTTPS，添加 443 端口
# ufw allow 443/tcp
```

---

## 客户端部署

### 1. 安装依赖

```bash
apt-get update
apt-get install -y python3 python3-pip
```

### 2. 部署代码

```bash
mkdir -p /opt/ddns-heartbeat
# 解压客户端代码到 /opt/ddns-heartbeat/
```

### 3. 配置环境变量

```bash
cat > /etc/ddns-heartbeat/client.env << 'EOF'
# 服务端地址
ECS_ENDPOINT=http://39.100.28.57:8989

# 域名和 APIKey（需与服务端配置匹配）
DDNS_DOMAIN=your-domain.com
DDNS_API_KEY=your-secure-api-key-here

# 心跳间隔（秒，默认 60）
HEARTBEAT_INTERVAL=60
EOF

chmod 600 /etc/ddns-heartbeat/client.env
```

### 4. 安装 systemd 服务

```bash
cp /opt/ddns-heartbeat/systemd/ddns-client.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable ddns-client
systemctl start ddns-client
systemctl status ddns-client
```

### 5. 验证客户端

```bash
# 查看日志
tail -f /var/log/ddns-heartbeat-client/client.log

# 预期看到
# Got public IP: x.x.x.x
# Heartbeat sent: OK (updated: x.x.x.x)
```

---

## 配置说明

### 服务端配置（server.json5）

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `port` | int | 否 | 监听端口（默认 8989） |
| `domains` | object | 是 | 域名:APIKey 映射 |

**示例：**
```json5
{
  "port": 8989,
  "domains": {
    "home.example.com": "secure-key-1",
    "office.example.com": "secure-key-2"
  }
}
```

### 客户端配置（环境变量）

| 变量 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `ECS_ENDPOINT` | string | 是 | 服务端地址 |
| `DDNS_DOMAIN` | string | 是 | 要更新的域名 |
| `DDNS_API_KEY` | string | 是 | 域名对应的 APIKey |
| `HEARTBEAT_INTERVAL` | int | 否 | 心跳间隔（秒，默认 60） |

---

## 安全建议

### 1. 文件权限
```bash
# 配置文件权限 600（仅 root 可读）
chmod 600 /etc/ddns-heartbeat/*.json5
chmod 600 /etc/ddns-heartbeat/*.env

# 代码目录权限 755
chmod 755 /opt/ddns-heartbeat
```

### 2. APIKey 管理
- 每个域名使用独立 APIKey
- APIKey 长度建议 ≥32 字符
- 定期轮换 APIKey
- 不提交 APIKey 到 Git 仓库

### 3. 网络隔离
- 服务端仅开放必要端口（8989）
- 配置防火墙白名单（仅允许已知客户端 IP）
- 生产环境启用 HTTPS

### 4. 日志安全
```bash
# 日志目录权限 750
chmod 750 /var/log/ddns-heartbeat
chmod 750 /var/log/ddns-heartbeat-client
```

---

## 故障排查

### 服务端无法启动

```bash
# 查看日志
journalctl -u ddns-server -n 50

# 检查配置文件
python3 -c "import sys; sys.path.insert(0, '/opt/ddns-heartbeat/server'); from config import init_config; init_config('/etc/ddns-heartbeat/server.json5')"

# 检查端口占用
ss -tlnp | grep 8989
```

### 客户端心跳失败

```bash
# 查看日志
tail -f /var/log/ddns-heartbeat-client/client.log

# 测试网络连通性
curl -v http://39.100.28.57:8989/health

# 检查公网 IP 获取
curl https://api.ipify.org?format=json
```

### APIKey 鉴权失败

```bash
# 测试鉴权
curl -X POST http://localhost:8989/ \
  -H 'Content-Type: application/json' \
  -d '{"domain":"your-domain.com","api_key":"your-key","ip":"1.2.3.4"}'

# 检查服务端配置
cat /etc/ddns-heartbeat/server.json5
```

---

## 备份与恢复

### 备份

```bash
/opt/ddns-heartbeat/scripts/backup.sh
```

### 恢复

```bash
/opt/ddns-heartbeat/scripts/restore.sh <backup-timestamp>
```

---

## 升级

```bash
# 停止服务
systemctl stop ddns-server
systemctl stop ddns-client

# 备份当前配置
cp -r /opt/ddns-heartbeat /opt/ddns-heartbeat.bak

# 解压新版本
# ...

# 启动服务
systemctl start ddns-server
systemctl start ddns-client

# 验证
systemctl status ddns-server
systemctl status ddns-client
```
