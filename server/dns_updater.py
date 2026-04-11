#!/usr/bin/env python3
"""
DNS Updater - 阿里云 DNS API 调用模块

修复内容：
1. 所有代码路径明确返回 True/False
2. 添加异常处理和日志记录
3. 增加超时重试机制
"""

import os
import hmac
import hashlib
import base64
import urllib.parse
import urllib.request
import json
import logging
from datetime import datetime

ACCESS_KEY_ID = os.environ.get('ALIYUN_ACCESS_KEY_ID', '')
ACCESS_KEY_SECRET = os.environ.get('ALIYUN_ACCESS_KEY_SECRET', '')

def sign_request(params, secret):
    """阿里云 API 签名"""
    sorted_params = sorted(params.items())
    query_string = '&'.join(f'{k}={urllib.parse.quote(str(v), safe="")}' for k, v in sorted_params)
    string_to_sign = f'GET&%2F&{urllib.parse.quote(query_string, safe="")}'
    return base64.b64encode(hmac.new(f'{secret}&'.encode(), string_to_sign.encode(), hashlib.sha1).digest()).decode()

def call_api(action, params, max_retries=2):
    """调用阿里云 API，带重试机制"""
    if not ACCESS_KEY_ID or not ACCESS_KEY_SECRET:
        logging.error('No credentials')
        return {}
    
    for attempt in range(max_retries + 1):
        try:
            common = {
                'AccessKeyId': ACCESS_KEY_ID,
                'Format': 'JSON',
                'SignatureMethod': 'HMAC-SHA1',
                'SignatureNonce': os.urandom(16).hex(),
                'SignatureVersion': '1.0',
                'Timestamp': datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'),
                'Version': '2015-01-09',
                'Action': action,
                **params
            }
            common['Signature'] = sign_request(common, ACCESS_KEY_SECRET)
            url = 'https://alidns.aliyuncs.com/?' + '&'.join(f'{k}={urllib.parse.quote(str(v), safe="")}' for k, v in sorted(common.items()))
            
            with urllib.request.urlopen(urllib.request.Request(url), timeout=10) as r:
                result = json.loads(r.read().decode())
                logging.debug(f"API {action} success: {result}")
                return result
        except urllib.error.HTTPError as e:
            error_body = e.read().decode() if e.fp else ''
            logging.error(f'API {action} HTTP Error {e.code}: {error_body}')
            if attempt == max_retries:
                return {}
        except Exception as e:
            logging.error(f'API {action} error (attempt {attempt + 1}/{max_retries + 1}): {e}')
            if attempt == max_retries:
                return {}
    
    return {}

def get_dns_value(domain, rr):
    """获取域名当前 DNS 记录值"""
    try:
        main = domain.split('.', 1)[1] if '.' in domain else domain
        result = call_api('DescribeDomainRecords', {'DomainName': main, 'RRKeyWord': rr})
        for rec in result.get('DomainRecords', {}).get('Record', []):
            if rec.get('RR') == rr:
                return rec.get('Value', '')
    except Exception as e:
        logging.error(f'Get DNS value error for {domain}: {e}')
    return ''

def update_dns(domain, ip):
    """
    更新域名 DNS 记录
    
    Returns:
        bool: 成功返回 True，失败返回 False
    """
    if not domain or not ip:
        logging.error('Invalid domain or IP')
        return False
    
    try:
        parts = domain.split('.', 1)
        if len(parts) != 2:
            logging.error(f'Invalid domain format: {domain}')
            return False
        
        rr, main = parts[0], parts[1]
        current = get_dns_value(domain, rr)
        logging.info(f'DNS check: {domain} current={current} target={ip}')
        
        if current == ip:
            logging.info('IP unchanged, skip update')
            return True
        
        # 查找现有记录
        rid = None
        try:
            result = call_api('DescribeDomainRecords', {'DomainName': main, 'RRKeyWord': rr})
            for rec in result.get('DomainRecords', {}).get('Record', []):
                if rec.get('RR') == rr:
                    rid = rec.get('RecordId')
                    break
        except Exception as e:
            logging.error(f'Find record error: {e}')
            rid = None
        
        if rid:
            # 更新现有记录
            res = call_api('UpdateDomainRecord', {'RecordId': rid, 'RR': rr, 'Type': 'A', 'Value': ip})
            if res.get('RecordId'):
                logging.info(f'DNS updated: {domain} -> {ip}')
                return True
            else:
                logging.error(f'DNS update failed: {res}')
                return False
        else:
            # 添加新记录
            res = call_api('AddDomainRecord', {'DomainName': main, 'RR': rr, 'Type': 'A', 'Value': ip})
            if res.get('RecordId'):
                logging.info(f'DNS created: {domain} -> {ip}')
                return True
            else:
                logging.error(f'DNS create failed: {res}')
                return False
    except Exception as e:
        logging.error(f'Update DNS exception for {domain}: {e}')
        return False
