#!/usr/bin/env python3
"""
Aliyun DNS API Updater
调用阿里云 DNS API 更新 A 记录
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

# 阿里云凭证（从环境变量读取）
ACCESS_KEY_ID = os.environ.get('ALIYUN_ACCESS_KEY_ID', '')
ACCESS_KEY_SECRET = os.environ.get('ALIYUN_ACCESS_KEY_SECRET', '')

def sign_request(params: dict, secret: str) -> str:
    """生成阿里云 API 签名"""
    # 排序参数
    sorted_params = sorted(params.items())
    query_string = '&'.join(f'{k}={urllib.parse.quote(str(v), safe="")}' for k, v in sorted_params)
    
    # 构建签名字符串
    string_to_sign = f'GET&%2F&{urllib.parse.quote(query_string, safe="")}'
    
    # 计算签名
    signature = hmac.new(
        f'{secret}&'.encode('utf-8'),
        string_to_sign.encode('utf-8'),
        hashlib.sha1
    ).digest()
    
    return base64.b64encode(signature).decode('utf-8')

def call_alidns_api(action: str, params: dict) -> dict:
    """调用阿里云 DNS API"""
    if not ACCESS_KEY_ID or not ACCESS_KEY_SECRET:
        logging.error("Aliyun credentials not configured")
        return {}
    
    # 公共参数
    common_params = {
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
    
    # 生成签名
    signature = sign_request(common_params, ACCESS_KEY_SECRET)
    common_params['Signature'] = signature
    
    # 构建请求 URL
    query_string = '&'.join(f'{k}={urllib.parse.quote(str(v), safe="")}' for k, v in sorted(common_params.items()))
    url = f'https://alidns.aliyuncs.com/?{query_string}'
    
    try:
        req = urllib.request.Request(url, method='GET')
        with urllib.request.urlopen(req, timeout=10) as response:
            return json.loads(response.read().decode('utf-8'))
    except Exception as e:
        logging.error(f"Aliyun API call failed: {e}")
        return {}

def get_record_id(domain: str, rr: str) -> str:
    """获取 DNS 记录 ID"""
    result = call_alidns_api('DescribeDomainRecords', {
        'DomainName': domain.split('.', 1)[-1] if '.' in domain else domain,
        'RRKeyWord': rr
    })
    
    records = result.get('DomainRecords', {}).get('Record', [])
    for record in records:
        if record.get('RR') == rr:
            return record.get('RecordId')
    
    return ''

def update_dns(domain: str, ip: str) -> bool:
    """更新 DNS A 记录"""
    if not domain or not ip:
        logging.error("Invalid domain or IP")
        return False
    
    # 解析 RR 和主域名
    parts = domain.split('.', 1)
    if len(parts) != 2:
        logging.error(f"Invalid domain format: {domain}")
        return False
    
    rr = parts[0]
    main_domain = parts[1]
    
    logging.info(f"Updating DNS: {domain} -> {ip}")
    
    # 查询现有记录
    record_id = get_record_id(domain, rr)
    
    if record_id:
        # 更新现有记录
        result = call_alidns_api('UpdateDomainRecord', {
            'RecordId': record_id,
            'RR': rr,
            'Type': 'A',
            'Value': ip
        })
        
        if result.get('RecordId'):
            logging.info(f"DNS record updated: {domain} -> {ip}")
            return True
        else:
            logging.error(f"Failed to update DNS: {result}")
            return False
    else:
        # 创建新记录
        result = call_alidns_api('AddDomainRecord', {
            'DomainName': main_domain,
            'RR': rr,
            'Type': 'A',
            'Value': ip
        })
        
        if result.get('RecordId'):
            logging.info(f"DNS record created: {domain} -> {ip}")
            return True
        else:
            logging.error(f"Failed to create DNS: {result}")
            return False
