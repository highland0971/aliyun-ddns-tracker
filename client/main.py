#!/usr/bin/env python3
"""
DDNS Heartbeat Client
每分钟向服务端上报心跳（携带当前出口公网 IP）
"""

import os
import sys
import json
import time
import logging
import urllib.request
import urllib.error
from datetime import datetime
from logging.handlers import TimedRotatingFileHandler

# 配置
ECS_ENDPOINT = os.environ.get('ECS_ENDPOINT', 'https://39.100.28.57:8443')
DOMAIN = os.environ.get('DDNS_DOMAIN', 'hyee-ar6121s.haoyuanee.com')
API_KEY = os.environ.get('DDNS_API_KEY', '')
HEARTBEAT_INTERVAL = int(os.environ.get('HEARTBEAT_INTERVAL', '60'))  # 秒
LOG_DIR = '/var/log/ddns-heartbeat-client'
LOG_FILE = os.path.join(LOG_DIR, 'client.log')

def setup_logging():
    """配置日志（每日轮转）"""
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
        handlers=[handler, logging.StreamHandler(sys.stdout)]
    )

def get_public_ip() -> str:
    """获取当前出口公网 IP（通过多个服务，避免单点故障）"""
    services = [
        'https://api.ipify.org?format=json',
        'https://ifconfig.me/ip',
        'https://icanhazip.com',
        'https://ip.sb/ip',
    ]
    
    for url in services:
        try:
            logging.debug(f"Trying {url}...")
            req = urllib.request.Request(url, headers={'User-Agent': 'curl/7.68.0'})
            with urllib.request.urlopen(req, timeout=5) as response:
                data = response.read().decode('utf-8').strip()
                # 处理 JSON 格式
                if 'json' in url:
                    data = json.loads(data).get('ip', '')
                # 验证 IP 格式
                import re
                if re.match(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$', data):
                    logging.info(f"Got public IP: {data}")
                    return data
        except Exception as e:
            logging.debug(f"Failed to get IP from {url}: {e}")
            continue
    
    logging.error("Failed to get public IP from all services")
    return None

def send_heartbeat(ip: str) -> bool:
    """发送心跳到服务端"""
    url = ECS_ENDPOINT
    data = {
        'domain': DOMAIN,
        'api_key': API_KEY,
        'ip': ip,
        'timestamp': datetime.now().isoformat(),
        'hostname': os.uname().nodename
    }
    
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(data).encode('utf-8'),
            headers={'Content-Type': 'application/json'},
            method='POST'
        )
        
        # 创建 HTTPS 上下文（验证证书）
        context = ssl.create_default_context()
        
        with urllib.request.urlopen(req, timeout=10, context=context) as response:
            result = response.read().decode('utf-8')
            logging.info(f"Heartbeat sent: {result}")
            return True
    except urllib.error.HTTPError as e:
        logging.error(f"HTTP Error: {e.code} - {e.read().decode()}")
        return False
    except Exception as e:
        logging.error(f"Failed to send heartbeat: {e}")
        return False

def main():
    setup_logging()
    logging.info("=" * 60)
    logging.info("DDNS Heartbeat Client Started")
    logging.info(f"ECS Endpoint: {ECS_ENDPOINT}")
    logging.info(f"Domain: {DOMAIN}")
    logging.info(f"Interval: {HEARTBEAT_INTERVAL}s")
    logging.info("=" * 60)
    
    last_ip = None
    fail_count = 0
    retry_interval = HEARTBEAT_INTERVAL
    
    # 首次启动立即上报
    logging.info("Initial heartbeat...")
    current_ip = get_public_ip()
    if current_ip:
        send_heartbeat(current_ip)
        last_ip = current_ip
        fail_count = 0
        retry_interval = HEARTBEAT_INTERVAL
    
    while True:
        try:
            # 等待下一个周期
            logging.debug(f"Sleeping for {retry_interval}s...")
            time.sleep(retry_interval)
            
            # 获取当前公网 IP
            current_ip = get_public_ip()
            
            if current_ip:
                # 检查 IP 是否变化
                if current_ip != last_ip:
                    logging.info(f"IP changed: {last_ip} -> {current_ip}")
                    last_ip = current_ip
                    fail_count = 0
                    retry_interval = HEARTBEAT_INTERVAL
                
                # 发送心跳
                if send_heartbeat(current_ip):
                    fail_count = 0
                    retry_interval = HEARTBEAT_INTERVAL
                else:
                    fail_count += 1
                    # 指数退避重试
                    retry_interval = min(HEARTBEAT_INTERVAL * (2 ** fail_count), 600)
                    logging.warning(f"Heartbeat failed, retry in {retry_interval}s (attempt {fail_count})")
            else:
                logging.warning("Could not get public IP, skipping this cycle")
                fail_count += 1
                retry_interval = min(HEARTBEAT_INTERVAL * (2 ** fail_count), 600)
            
        except KeyboardInterrupt:
            logging.info("")
            logging.info("Stopping...")
            break
        except Exception as e:
            logging.error(f"ERROR: {e}")
            fail_count += 1
            retry_interval = min(HEARTBEAT_INTERVAL * (2 ** fail_count), 600)

if __name__ == '__main__':
    import ssl
    main()
