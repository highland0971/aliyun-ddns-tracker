#!/usr/bin/env python3
import os, hmac, hashlib, base64, urllib.parse, urllib.request, json, logging
from datetime import datetime

ACCESS_KEY_ID = os.environ.get('ALIYUN_ACCESS_KEY_ID', '')
ACCESS_KEY_SECRET = os.environ.get('ALIYUN_ACCESS_KEY_SECRET', '')

def sign_request(params, secret):
    sorted_params = sorted(params.items())
    query_string = '&'.join(f'{k}={urllib.parse.quote(str(v), safe="")}' for k, v in sorted_params)
    string_to_sign = f'GET&%2F&{urllib.parse.quote(query_string, safe="")}'
    return base64.b64encode(hmac.new(f'{secret}&'.encode(), string_to_sign.encode(), hashlib.sha1).digest()).decode()

def call_api(action, params):
    if not ACCESS_KEY_ID or not ACCESS_KEY_SECRET:
        logging.error('No credentials')
        return {}
    common = {'AccessKeyId': ACCESS_KEY_ID, 'Format': 'JSON', 'SignatureMethod': 'HMAC-SHA1', 'SignatureNonce': os.urandom(16).hex(), 'SignatureVersion': '1.0', 'Timestamp': datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'), 'Version': '2015-01-09', 'Action': action, **params}
    common['Signature'] = sign_request(common, ACCESS_KEY_SECRET)
    url = 'https://alidns.aliyuncs.com/?' + '&'.join(f'{k}={urllib.parse.quote(str(v), safe="")}' for k, v in sorted(common.items()))
    try:
        with urllib.request.urlopen(urllib.request.Request(url), timeout=10) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        logging.error(f'API error: {e}')
        return {}

def get_dns_value(domain, rr):
    main = domain.split('.', 1)[1] if '.' in domain else domain
    for rec in call_api('DescribeDomainRecords', {'DomainName': main, 'RRKeyWord': rr}).get('DomainRecords', {}).get('Record', []):
        if rec.get('RR') == rr:
            return rec.get('Value', '')
    return ''

def update_dns(domain, ip):
    if not domain or not ip:
        return False
    parts = domain.split('.', 1)
    if len(parts) != 2:
        return False
    rr, main = parts[0], parts[1]
    current = get_dns_value(domain, rr)
    logging.info(f'DNS check: {domain} current={current} target={ip}')
    if current == ip:
        logging.info('IP unchanged, skip update')
        return True
    rid = None
    for rec in call_api('DescribeDomainRecords', {'DomainName': main, 'RRKeyWord': rr}).get('DomainRecords', {}).get('Record', []):
        if rec.get('RR') == rr:
            rid = rec.get('RecordId')
            break
    if rid:
        res = call_api('UpdateDomainRecord', {'RecordId': rid, 'RR': rr, 'Type': 'A', 'Value': ip})
        if res.get('RecordId'):
            logging.info(f'DNS updated: {domain}')
            return True
    else:
        res = call_api('AddDomainRecord', {'DomainName': main, 'RR': rr, 'Type': 'A', 'Value': ip})
        if res.get('RecordId'):
            logging.info(f'DNS created: {domain}')
            return True
    return False
