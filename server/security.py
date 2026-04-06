#!/usr/bin/env python3
"""
DDNS Server Security Module
- 滑动窗口频率限制（线程安全）
- IP 封禁管理（SQLite 持久化）
"""

import time
import sqlite3
import logging
from threading import Thread, RLock
from collections import defaultdict
from datetime import datetime, timedelta

DB_PATH = '/var/lib/ddns-heartbeat/ddns.db'

class RateLimiter:
    """滑动窗口频率限制器（使用 RLock 避免死锁）"""
    
    def __init__(self, limit=10, window=60, max_ips=10000):
        self.limit = limit  # 最大请求次数
        self.window = window  # 时间窗口（秒）
        self.max_ips = max_ips  # 最大 IP 数量限制
        self.requests = defaultdict(list)
        self.lock = RLock()  # 可重入锁，避免死锁
        self._start_cleanup_thread()
    
    def _start_cleanup_thread(self):
        """启动后台清理线程（每 5 分钟清理一次）"""
        def cleanup_loop():
            while True:
                time.sleep(300)  # 5 分钟
                self.cleanup()
        
        cleanup_thread = Thread(target=cleanup_loop, daemon=True)
        cleanup_thread.start()
    
    def is_allowed(self, ip: str) -> bool:
        """检查 IP 是否允许请求（滑动窗口算法）"""
        now = time.time()
        with self.lock:
            # 如果 IP 数量超限，强制清理
            if len(self.requests) >= self.max_ips:
                self.cleanup()
                # 清理后仍超限，拒绝新 IP
                if len(self.requests) >= self.max_ips:
                    return False
            
            # 滑动窗口：只保留 window 秒内的请求
            self.requests[ip] = [
                t for t in self.requests[ip]
                if now - t < self.window
            ]
            if len(self.requests[ip]) >= self.limit:
                return False
            self.requests[ip].append(now)
            return True
    
    def cleanup(self):
        """清理过期数据"""
        now = time.time()
        with self.lock:
            expired = [
                ip for ip, times in self.requests.items()
                if all(now - t >= self.window for t in times)
            ]
            for ip in expired:
                del self.requests[ip]

class IPBanManager:
    """IP 封禁管理器（SQLite 持久化）"""
    
    def __init__(self, max_fails=10, ban_duration=3600):
        self.max_fails = max_fails
        self.ban_duration = ban_duration
        self.fail_counts = defaultdict(list)
        self.lock = RLock()
        self._init_db()
        self._start_cleanup_thread()
    
    def _init_db(self):
        """初始化 SQLite 数据库"""
        import os
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        
        conn = sqlite3.connect(DB_PATH)
        conn.execute('PRAGMA journal_mode=WAL')  # 启用 WAL 模式
        conn.execute('''
            CREATE TABLE IF NOT EXISTS ip_bans (
                ip TEXT PRIMARY KEY,
                reason TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP
            )
        ''')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_expires ON ip_bans(expires_at)')
        conn.commit()
        conn.close()
        logging.info(f"SQLite database initialized: {DB_PATH}")
    
    def _start_cleanup_thread(self):
        """启动后台清理线程（每 10 分钟清理过期记录）"""
        def cleanup_loop():
            while True:
                time.sleep(600)  # 10 分钟
                self._cleanup_db()
                self._cleanup_memory()
        
        cleanup_thread = Thread(target=cleanup_loop, daemon=True)
        cleanup_thread.start()
    
    def record_failure(self, ip: str):
        """记录失败尝试，检查是否需要封禁"""
        now = datetime.now()
        with self.lock:
            # 清理过期记录
            window_start = now - timedelta(seconds=300)  # 5 分钟窗口
            self.fail_counts[ip] = [
                t for t in self.fail_counts[ip]
                if t > window_start
            ]
            
            # 添加当前失败记录
            self.fail_counts[ip].append(now)
            
            # 检查是否达到封禁阈值
            if len(self.fail_counts[ip]) >= self.max_fails:
                self._ban_ip(ip)
                return True
            
            return False
    
    def _ban_ip(self, ip: str):
        """封禁 IP（写入 SQLite）"""
        now = datetime.now()
        expires = now + timedelta(seconds=self.ban_duration)
        
        conn = sqlite3.connect(DB_PATH)
        conn.execute('''
            INSERT OR REPLACE INTO ip_bans (ip, reason, expires_at)
            VALUES (?, ?, ?)
        ''', (ip, 'Too many auth failures', expires))
        conn.commit()
        conn.close()
        
        logging.warning(f"IP banned: {ip} for {self.ban_duration}s")
    
    def is_banned(self, ip: str) -> bool:
        """检查 IP 是否被封禁"""
        now = datetime.now()
        
        # 先检查内存缓存
        with self.lock:
            if ip in self.fail_counts and len(self.fail_counts[ip]) >= self.max_fails:
                return True
        
        # 查询数据库
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.execute('''
            SELECT expires_at FROM ip_bans
            WHERE ip = ? AND expires_at > ?
        ''', (ip, now.isoformat()))
        result = cursor.fetchone()
        conn.close()
        
        return result is not None
    
    def get_banned_count(self) -> int:
        """获取当前封禁的 IP 数量"""
        now = datetime.now()
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.execute('''
            SELECT COUNT(*) FROM ip_bans WHERE expires_at > ?
        ''', (now.isoformat(),))
        result = cursor.fetchone()[0]
        conn.close()
        return result
    
    def _cleanup_db(self):
        """清理数据库中的过期记录"""
        now = datetime.now()
        conn = sqlite3.connect(DB_PATH)
        conn.execute('DELETE FROM ip_bans WHERE expires_at <= ?', (now.isoformat(),))
        conn.commit()
        conn.close()
    
    def _cleanup_memory(self):
        """清理内存中的过期失败记录"""
        now = datetime.now()
        window_start = now - timedelta(seconds=300)
        with self.lock:
            for ip in list(self.fail_counts.keys()):
                self.fail_counts[ip] = [
                    t for t in self.fail_counts[ip]
                    if t > window_start
                ]
                if not self.fail_counts[ip]:
                    del self.fail_counts[ip]
