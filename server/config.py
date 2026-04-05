#!/usr/bin/env python3
"""
DDNS Server Configuration Manager
支持 JSON5 配置文件和环境变量覆盖
"""

import os
import signal
import threading
import json
import logging

# 简单的 JSON5 解析（移除注释和尾随逗号）
def parse_json5(content: str) -> dict:
    """解析 JSON5 内容（简化版：移除注释和尾随逗号）"""
    lines = []
    for line in content.split('\n'):
        # 移除行注释
        if '//' in line:
            line = line[:line.index('//')]
        lines.append(line)
    
    content = '\n'.join(lines)
    # 移除尾随逗号
    content = content.replace(',}', '}').replace(',]', ']')
    
    return json.loads(content)

class ConfigManager:
    _instance = None
    
    def __init__(self, config_path: str):
        self.config_path = config_path
        self._config = {}
        self._config_lock = threading.RLock()
        self._config = self.load_config()  # 修复：将加载的配置赋值给 self._config
    
    def load_config(self) -> dict:
        """加载配置到临时变量"""
        with open(self.config_path, 'r', encoding='utf-8') as f:
            content = f.read()
        return parse_json5(content)
    
    def reload_config(self, signum=None, frame=None):
        """线程安全的配置重载（原子替换）"""
        new_config = self.load_config()
        with self._config_lock:
            self._config = new_config
        logging.info("Configuration reloaded")
    
    def get(self, key: str, default=None) -> any:
        """线程安全的配置读取"""
        with self._config_lock:
            return self._config.get(key, default)
    
    def get_domain_key(self, domain: str) -> str:
        """获取域名对应的 APIKey"""
        domains = self.get('domains', {})
        return domains.get(domain)

# 全局单例
config_manager = None

def init_config(config_path: str):
    """初始化配置管理器"""
    global config_manager
    config_manager = ConfigManager(config_path)
    # 注册 SIGHUP 信号处理器
    signal.signal(signal.SIGHUP, config_manager.reload_config)
    logging.info(f"Configuration loaded from {config_path}")
    return config_manager  # 返回实例供验证
