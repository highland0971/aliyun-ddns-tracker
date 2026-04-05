# aliyun-ddns-tracker

基于心跳上报机制的动态 DNS 更新服务

**评审状态:** ✅ 玉坤 (CT1001) 六次评审 - 无条件通过

## 架构

```
LXC 容器 (心跳上报) → 阿里云 ECS:8989 (心跳接收) → 阿里云 DNS API → 更新域名
```

## 特性

- ✅ HTTPS 加密通信（TLS 1.2+）
- ✅ APIKey 配对鉴权
- ✅ IP 封禁持久化（SQLite）
- ✅ 请求频率限制（滑动窗口）
- ✅ 心跳失败指数退避
- ✅ 日志轮转 + 压缩归档
- ✅ 证书自动续期（Let's Encrypt）
- ✅ 配置热重载（SIGHUP）
- ✅ 备份恢复流程

## 协议

GPL-3.0

## 快速开始

### 服务端（阿里云 ECS）

```bash
# 安装依赖
apt-get update && apt-get install -y python3 python3-pip sqlite3

# 部署代码
mkdir -p /opt/ddns-heartbeat
# 解压代码...

# 配置
cat > /etc/ddns-heartbeat/server.json5 << 'EOF'
{
  "port": 8989,
  "domains": {
    "your-domain.com": "your-secure-api-key"
  }
}
EOF
chmod 600 /etc/ddns-heartbeat/server.json5

# 启动服务
cp /opt/ddns-heartbeat/systemd/ddns-server.service /etc/systemd/system/
systemctl daemon-reload && systemctl enable --now ddns-server

# 验证
curl http://localhost:8989/health
```

### 客户端（LXC 容器）

```bash
# 安装依赖
apt-get update && apt-get install -y python3

# 部署代码
mkdir -p /opt/ddns-heartbeat
# 解压代码...

# 配置
cat > /etc/ddns-heartbeat/client.env << 'EOF'
ECS_ENDPOINT=http://39.100.28.57:8989
DDNS_DOMAIN=your-domain.com
DDNS_API_KEY=your-secure-api-key
HEARTBEAT_INTERVAL=60
EOF
chmod 600 /etc/ddns-heartbeat/client.env

# 启动服务
cp /opt/ddns-heartbeat/systemd/ddns-client.service /etc/systemd/system/
systemctl daemon-reload && systemctl enable --now ddns-client

# 验证
tail -f /var/log/ddns-heartbeat-client/client.log
```

## 文档

- [INSTALL.md](docs/INSTALL.md) - 详细安装指南
- [API.md](docs/API.md) - 接口文档

## 安全建议

1. **使用 HTTPS** - 生产环境必须启用
2. **保护 APIKey** - 不提交到 Git，定期轮换
3. **配置权限** - 配置文件权限 600
4. **网络隔离** - 配置防火墙白名单

## 评审记录

| 评审次数 | 评审人 | 结论 | 日期 |
|----------|--------|------|------|
| 1 | 玉坤 (CT1001) | 有条件通过 | 2026-04-05 |
| 2 | 玉坤 (CT1001) | 有条件通过 | 2026-04-05 |
| 3 | 玉坤 (CT1001) | 有条件通过 | 2026-04-05 |
| 4 | 玉坤 (CT1001) | 有条件通过 | 2026-04-05 |
| 5 | 玉坤 (CT1001) | 有条件通过 | 2026-04-05 |
| 6 | 玉坤 (CT1001) | **无条件通过** | 2026-04-05 |

## License

GPL-3.0
