import json
import os

CONFIG_FILE = 'static/config.json'

# 默认配置
DEFAULT_CONFIG = {
    "BASE_URL": "http://172.23.34.169:8080",
    "USER_ID": "",
    "STBID": "",
    "USER_AGENT": ("Mozilla/5.0 (compatible; EIS iPanel 2.0; Linux2.4.26/mips; win32; HI3110) "
                   "AppleWebKit/2.0 (KHTML, like Gecko) EC2106V1H Hybroad;Resolution(PAL,720P,1080i)"),
    "Authenticator": "",
    "UDPXY": "",
    "EPG_HOST": "http://172.23.35.201:8080",
    "STB_IP": "172.34.24.71",
    "STB_TYPE": "B860AV1.1-T2",
    "MAC": "",
    "ENCRYPT_KEY": "",
    "DNS_SERVERS": "172.16.5.144,172.16.5.145",
    "EAS_DOMAIN": "epg.itv.cq.cn",
    "EAS_IP": "172.16.5.217"
}

def load_config():
    """加载配置文件，如果不存在则创建默认配置"""
    if not os.path.exists('static'):
        os.makedirs('static')
        
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    else:
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG

def save_config(config):
    """保存配置到文件"""
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=4, ensure_ascii=False) 