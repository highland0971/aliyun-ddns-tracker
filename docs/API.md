# DDNS Heartbeat Service - API 文档

## 接口概述

服务端提供以下 HTTP 接口：

| 接口 | 方法 | 认证 | 说明 |
|------|------|------|------|
| `/` | POST | 是 | 心跳上报 |
| `/health` | GET | 否 | 健康检查 |

---

## 心跳上报接口

### 请求

**URL:** `POST /`

**Headers:**
```
Content-Type: application/json
```

**Body:**
```json
{
  "domain": "your-domain.com",
  "api_key": "your-secure-api-key",
  "ip": "1.2.3.4",
  "timestamp": "2026-04-05T18:00:00.000000",
  "hostname": "client-hostname"
}
```

**字段说明:**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `domain` | string | 是 | 要更新的域名 |
| `api_key` | string | 是 | 域名对应的 APIKey |
| `ip` | string | 是 | 当前公网 IP |
| `timestamp` | string | 否 | 客户端时间戳 |
| `hostname` | string | 否 | 客户端主机名 |

### 响应

**成功（IP 未变化）:**
```
HTTP/1.0 200 OK
Content-Type: text/plain

OK (unchanged)
```

**成功（IP 已更新）:**
```
HTTP/1.0 200 OK
Content-Type: text/plain

OK (updated: 1.2.3.4)
```

**认证失败:**
```
HTTP/1.0 401 Unauthorized
Content-Type: text/plain

Unauthorized
```

**IP 被封禁:**
```
HTTP/1.0 403 Forbidden
Content-Type: text/plain

Forbidden
```

**频率超限:**
```
HTTP/1.0 429 Too Many Requests
Content-Type: text/plain

Too Many Requests
```

**服务器错误:**
```
HTTP/1.0 500 Internal Server Error
Content-Type: text/plain

DNS update failed
```

---

## 健康检查接口

### 请求

**URL:** `GET /health`

**Headers:** 无

### 响应

**成功:**
```json
{
  "status": "healthy",
  "timestamp": "2026-04-05T18:00:00.000000",
  "port": 8989,
  "banned_ips": 0,
  "rate_limiter_ips": 0
}
```

**字段说明:**

| 字段 | 类型 | 说明 |
|------|------|------|
| `status` | string | 服务状态（healthy/unhealthy） |
| `timestamp` | string | 当前时间 |
| `port` | int | 监听端口 |
| `banned_ips` | int | 当前封禁的 IP 数量 |
| `rate_limiter_ips` | int | 频率限制器中的 IP 数量 |

---

## 错误码

| 状态码 | 说明 | 处理建议 |
|--------|------|----------|
| 200 | 成功 | - |
| 400 | 请求格式错误 | 检查 JSON 格式 |
| 401 | 认证失败 | 检查 domain 和 api_key |
| 403 | IP 被封禁 | 等待封禁解除（1 小时） |
| 429 | 频率超限 | 降低请求频率 |
| 500 | 服务器错误 | 检查服务端日志 |

---

## 使用示例

### cURL 示例

```bash
# 心跳上报
curl -X POST http://39.100.28.57:8989/ \
  -H 'Content-Type: application/json' \
  -d '{
    "domain": "home.example.com",
    "api_key": "your-secure-api-key",
    "ip": "1.2.3.4",
    "timestamp": "2026-04-05T18:00:00.000000",
    "hostname": "lxc-client"
  }'

# 健康检查
curl http://39.100.28.57:8989/health
```

### Python 示例

```python
import urllib.request
import json
from datetime import datetime

def send_heartbeat(endpoint, domain, api_key, ip):
    """发送心跳上报"""
    data = {
        'domain': domain,
        'api_key': api_key,
        'ip': ip,
        'timestamp': datetime.now().isoformat(),
        'hostname': 'client-hostname'
    }
    
    req = urllib.request.Request(
        endpoint,
        data=json.dumps(data).encode('utf-8'),
        headers={'Content-Type': 'application/json'},
        method='POST'
    )
    
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            result = response.read().decode('utf-8')
            print(f"Heartbeat sent: {result}")
            return True
    except urllib.error.HTTPError as e:
        print(f"HTTP Error: {e.code} - {e.read().decode()}")
        return False
    except Exception as e:
        print(f"Failed: {e}")
        return False

# 使用示例
send_heartbeat(
    'http://39.100.28.57:8989/',
    'home.example.com',
    'your-secure-api-key',
    '1.2.3.4'
)
```

### Shell 示例

```bash
#!/bin/bash
# 手动心跳上报脚本

ENDPOINT="http://39.100.28.57:8989/"
DOMAIN="home.example.com"
API_KEY="your-secure-api-key"
IP=$(curl -s https://api.ipify.org)

curl -X POST "$ENDPOINT" \
  -H 'Content-Type: application/json' \
  -d "{
    \"domain\": \"$DOMAIN\",
    \"api_key\": \"$API_KEY\",
    \"ip\": \"$IP\",
    \"timestamp\": \"$(date -Iseconds)\",
    \"hostname\": \"$(hostname)\"
  }"
```

---

## 安全注意事项

1. **使用 HTTPS**
   - 生产环境必须启用 HTTPS
   - 避免 APIKey 明文传输

2. **保护 APIKey**
   - 不提交到 Git 仓库
   - 使用环境变量或加密存储
   - 定期轮换

3. **频率限制**
   - 默认 10 次/分钟/IP
   - 超出后自动封禁（1 小时）

4. **日志脱敏**
   - APIKey 在日志中显示为 `sk_****xxxx`
   - IP 地址可选脱敏
