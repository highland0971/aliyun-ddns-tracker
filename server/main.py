#!/usr/bin/env python3
"""
DDNS Heartbeat Receiver Server
监听 LXC 容器心跳上报，提取源 IP 并更新阿里云 DNS

修复内容：
1. 修正启动顺序：先 init_config() 再访问 config_manager
2. 改用 ThreadingHTTPServer 防止阻塞
3. 添加异常处理和日志强制刷新
"""

import os
import sys
import logging
from logging.handlers import TimedRotatingFileHandler
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
import json
import threading
from datetime import datetime

from config import init_config
import config
from security import RateLimiter, IPBanManager
from dns_updater import update_dns

# 常量
LISTEN_PORT = 8989  # DDNS 心跳接收端口
LOG_DIR = '/var/log/ddns-heartbeat'
LOG_FILE = os.path.join(LOG_DIR, 'server.log')

# 全局变量
rate_limiter = None
ip_ban_manager = None

def setup_logging():
    """配置日志（每日轮转，压缩归档）"""
    os.makedirs(LOG_DIR, exist_ok=True)
    
    handler = TimedRotatingFileHandler(
        LOG_FILE,
        when='D',
        interval=1,
        backupCount=30,
        encoding='utf-8'
    )
    handler.suffix = '%Y-%m-%d'
    handler.setLevel(logging.INFO)
    
    formatter = logging.Formatter(
        '%(asctime)s %(levelname)s [%(name)s] %(message)s'
    )
    handler.setFormatter(formatter)
    
    logging.basicConfig(
        level=logging.INFO,
        handlers=[handler, logging.StreamHandler(sys.stdout)],
        force=True  # 强制覆盖已有配置
    )

class HeartbeatHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        logging.info("%s - %s", self.client_address[0], format % args)
    
    def do_POST(self):
        global rate_limiter, ip_ban_manager
        client_ip = self.client_address[0]
        
        # 读取请求体
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length).decode('utf-8') if content_length > 0 else '{}'
        
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            logging.warning(f"Invalid JSON from {client_ip}")
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b'Invalid JSON')
            return
        
        # 鉴权
        domain = data.get('domain', '')
        api_key = data.get('api_key', '')
        
        if not domain or not api_key:
            logging.warning(f"Missing credentials from {client_ip}")
            self.send_response(401)
            self.end_headers()
            self.wfile.write(b'Missing credentials')
            return
        
        # 验证 APIKey
        expected_key = None
        if config.config_manager:
            domains = config.config_manager.get('domains', {})
            expected_key = domains.get(domain) if domains else None
        
        if not expected_key or api_key != expected_key:
            logging.warning(f"Auth failed for {domain} from {client_ip}")
            self.send_response(401)
            self.end_headers()
            self.wfile.write(b'Unauthorized')
            return
        
        # 检查 IP 封禁
        if ip_ban_manager and ip_ban_manager.is_banned(client_ip):
            logging.warning(f"Banned IP {client_ip} attempted access")
            self.send_response(403)
            self.end_headers()
            self.wfile.write(b'Forbidden')
            return
        
        # 检查频率限制
        if rate_limiter and not rate_limiter.is_allowed(client_ip):
            logging.warning(f"Rate limit exceeded for {client_ip}")
            if ip_ban_manager:
                ip_ban_manager.record_failure(client_ip)
            self.send_response(429)
            self.end_headers()
            self.wfile.write(b'Too Many Requests')
            return
        
        # 提取上报的 IP（或使用源 IP）
        reported_ip = data.get('ip', client_ip)
        
        logging.info(f"Heartbeat received: domain={domain}, ip={reported_ip}, source={client_ip}")
        
        # 检查当前 DNS 记录
        current_dns_ip = get_current_dns_ip(domain)
        
        if current_dns_ip == reported_ip:
            logging.info(f"IP unchanged for {domain}: {reported_ip}")
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'OK (unchanged)')
        else:
            logging.info(f"IP changed for {domain}: {current_dns_ip} -> {reported_ip}")
            try:
                if update_dns(domain, reported_ip):
                    logging.info(f"DNS updated: {domain} -> {reported_ip}")
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(f'OK (updated: {reported_ip})'.encode())
                else:
                    logging.error(f"DNS update failed for {domain}")
                    self.send_response(500)
                    self.end_headers()
                    self.wfile.write(b'DNS update failed')
            except Exception as e:
                logging.error(f"DNS update exception for {domain}: {e}")
                self.send_response(500)
                self.end_headers()
                self.wfile.write(b'DNS update error')
    
    def do_GET(self):
        """健康检查端点"""
        global rate_limiter, ip_ban_manager
        if self.path == '/health':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            
            status = {
                'status': 'healthy',
                'timestamp': datetime.now().isoformat(),
                'port': LISTEN_PORT,
                'banned_ips': ip_ban_manager.get_banned_count() if ip_ban_manager else 0,
                'rate_limiter_ips': len(rate_limiter.requests) if rate_limiter else 0
            }
            self.wfile.write(json.dumps(status).encode())
            return
        
        self.send_response(404)
        self.end_headers()
        self.wfile.write(b'Not Found')

def get_current_dns_ip(domain: str) -> str:
    """获取当前 DNS 解析的 IP（简化实现）"""
    cache_file = f'/tmp/ddns_cache_{domain.replace(".", "_")}.txt'
    try:
        with open(cache_file, 'r') as f:
            return f.read().strip()
    except FileNotFoundError:
        return ''

def main():
    global rate_limiter, ip_ban_manager
    logging.info("=" * 60)
    logging.info("DDNS Heartbeat Receiver Server Starting")
    logging.info(f"Port: {LISTEN_PORT}")
    logging.info(f"Config: {config.config_manager.config_path if config.config_manager else 'N/A'}")
    logging.info("=" * 60)
    
    # 创建多线程 HTTP 服务器（防止阻塞）
    server = ThreadingHTTPServer(('0.0.0.0', LISTEN_PORT), HeartbeatHandler)
    
    logging.info(f"Server listening on 0.0.0.0:{LISTEN_PORT}")
    logging.info("Press Ctrl+C to stop")
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logging.info("")
        logging.info("Stopping server...")
    finally:
        server.shutdown()
        logging.info("Server stopped")

if __name__ == '__main__':
    # 初始化配置（必须在访问 config_manager 之前）
    config_path = os.environ.get('CONFIG_PATH', '/etc/ddns-heartbeat/server.json5')
    init_config(config_path)
    
    # 验证配置已加载（必须在 main() 之前）
    if config.config_manager is None:
        logging.error("Failed to initialize config manager")
        sys.exit(1)
    
    # 初始化安全管理
    rate_limiter = RateLimiter(limit=10, window=60, max_ips=10000)
    ip_ban_manager = IPBanManager(max_fails=10, ban_duration=3600)
    
    main()
