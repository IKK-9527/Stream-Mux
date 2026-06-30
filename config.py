import json
import os
from dotenv import load_dotenv

CONFIG_FILE = 'static/config.json'

# 默认配置（占位符，不含真实内网 IP）
DEFAULT_CONFIG = {
    "BASE_URL": "",
    "USER_ID": "",
    "STBID": "",
    "USER_AGENT": ("Mozilla/5.0 (compatible; EIS iPanel 2.0; Linux2.4.26/mips; win32; HI3110) "
                   "AppleWebKit/2.0 (KHTML, like Gecko) EC2106V1H Hybroad;Resolution(PAL,720P,1080i)"),
    "Authenticator": "",
    "UDPXY": "",
    "EPG_HOST": "",
    "STB_IP": "",
    "STB_TYPE": "",
    "MAC": "",
    "ENCRYPT_KEY": "",
    "DNS_SERVERS": "",
    "EAS_DOMAIN": "epg.itv.cq.cn",
    "EAS_IP": "",
    "EAS_SESSION_IP": "",
    "EAS_STB_TYPE": "",
    "SECRET_KEY": "change-me-to-a-random-string",
}

# 从 .env 文件加载环境变量
load_dotenv()


def _env_overrides():
    """读取环境变量，覆盖默认配置（环境变量 > config.json > 默认值）"""
    env_map = {
        "BASE_URL": "BASE_URL",
        "USER_ID": "USER_ID",
        "STBID": "STBID",
        "USER_AGENT": "USER_AGENT",
        "Authenticator": "AUTHENTICATOR",
        "UDPXY": "UDPXY",
        "EPG_HOST": "EPG_HOST",
        "STB_IP": "STB_IP",
        "STB_TYPE": "STB_TYPE",
        "MAC": "MAC",
        "ENCRYPT_KEY": "ENCRYPT_KEY",
        "DNS_SERVERS": "DNS_SERVERS",
        "EAS_DOMAIN": "EAS_DOMAIN",
        "EAS_IP": "EAS_IP",
        "EAS_SESSION_IP": "EAS_SESSION_IP",
        "EAS_STB_TYPE": "EAS_STB_TYPE",
        "SECRET_KEY": "SECRET_KEY",
    }
    overrides = {}
    for config_key, env_key in env_map.items():
        val = os.environ.get(env_key)
        if val is not None:
            overrides[config_key] = val
    return overrides


def load_config():
    """加载配置，优先级：环境变量 > static/config.json > 默认值"""
    if not os.path.exists('static'):
        os.makedirs('static')

    # 从文件读取
    file_config = {}
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            file_config = json.load(f)

    # 合并：文件配置覆盖默认，环境变量覆盖文件
    merged = {**DEFAULT_CONFIG, **file_config, **_env_overrides()}
    return merged


def save_config(config):
    """保存配置到文件"""
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=4, ensure_ascii=False)
