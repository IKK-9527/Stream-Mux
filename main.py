from datetime import datetime, timedelta
import requests
from bs4 import BeautifulSoup
import re
from config import load_config
from flask import render_template, Flask, request, redirect, url_for, flash, jsonify
import json
import os
import time
import random
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import quote as url_quote, urlparse, parse_qs
from Crypto.Cipher import DES3, DES
from Crypto.Util.Padding import pad
import binascii
import dns.resolver
import threading

app = Flask(__name__)  # 添加这行，确保在使用 flash 之前定义
app.secret_key = 'your_secret_key'  # 添加这行，用于 flash 消息加密


# 加载配置
config = load_config()
BASE_URL = config['BASE_URL']
USER_ID = config['USER_ID']
STBID = config['STBID']
USER_AGENT = config['USER_AGENT']
Authenticator = config['Authenticator']
UDPXY = config['UDPXY']
EPG_HOST = config.get('EPG_HOST', 'http://172.23.35.201:8080')
# 动态 Authenticator 生成相关
STB_IP = config.get('STB_IP', '172.34.24.71')
STB_TYPE = config.get('STB_TYPE', '')
MAC = config.get('MAC', '')
ENCRYPT_KEY = config.get('ENCRYPT_KEY', '')
DNS_SERVERS = config.get('DNS_SERVERS', '172.16.5.144,172.16.5.145')
EAS_DOMAIN = config.get('EAS_DOMAIN', 'epg.itv.cq.cn')

# ========== Token 缓存 ==========
# Token 有效期 48 小时，避免频繁重新认证
_token_cache = {"token": None, "time": 0}
TOKEN_TTL = 48 * 3600  # 48 小时（秒）

# ========== EAS 服务器地址 ==========
# EAS_IP 有值 → 直接使用（跳过 DNS）
# EAS_IP 为空 → 用 DNS_SERVERS 解析域名
EAS_IP = config.get('EAS_IP', '').strip()
if not EAS_IP and DNS_SERVERS:
    dns_servers_list = [s.strip() for s in DNS_SERVERS.split(',') if s.strip()]
    if dns_servers_list:
        try:
            _resolver = dns.resolver.Resolver()
            _resolver.nameservers = dns_servers_list
            _resolver.timeout = 3
            _resolver.lifetime = 5
            answers = _resolver.resolve(EAS_DOMAIN, 'A')
            EAS_IP = str(answers[0])
            print(f"[AutoIPTV] DNS 解析: {EAS_DOMAIN} → {EAS_IP}")
        except Exception as e:
            print(f"[AutoIPTV] DNS 解析失败: {e}")
if EAS_IP:
    print(f"[AutoIPTV] EAS 服务器: {EAS_DOMAIN} @ {EAS_IP}:8080")


# ========== 服务会话初始化（通用） ==========
# index.jsp + funcportalauth.jsp，BASE_URL 和 EPG_HOST 共用

def _init_service_session(session, token, host):
    """在指定 host 上初始化服务会话"""
    headers = {
        "Accept-Encoding": "deflate, gzip",
        "User-Agent": USER_AGENT,
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Connection": "Keep-Alive",
    }
    # index.jsp - 初始化会话
    try:
        session.get(
            f"{host}/iptvepg/function/index.jsp",
            params={
                "UserGroupNMB": "31", "EPGGroupNMB": "31",
                "UserToken": token, "UserID": USER_ID, "STBID": STBID,
                "easip": "172.16.5.214", "networkid": "1", "loadbalanced": "-1"
            },
            headers={**headers, "Referer": f"{host}/iptvepg/function/index.jsp"},
            timeout=10
        )
    except Exception:
        pass
    # funcportalauth.jsp - 通道认证
    try:
        payload = (
            f"UserToken={token}&UserID={USER_ID}&STBID={STBID}"
            f"&stbinfo=&prmid=&easip=172.16.5.214&networkid=1"
            f"&stbtype=EC2106V1H_pub&drmsupplier="
        )
        session.post(
            f"{host}/iptvepg/function/funcportalauth.jsp",
            data=payload,
            headers={**headers,
                "Referer": f"{host}/iptvepg/function/index.jsp?loadbalanced=0",
                "Origin": f"{host}",
            },
            timeout=10
        )
    except Exception:
        pass


# ========== 动态 Authenticator 生成 ==========

def get_encrypt_token():
    """调用 getencrypttoken.jsp 获取 EncryptToken
    用解析到的 EAS_IP + Host 头发送请求"""
    # 确定目标 IP（解析到的 IP 或回退域名）
    if EAS_IP:
        eas_base = f"http://{EAS_IP}:8080"
    else:
        eas_base = f"http://{EAS_DOMAIN}:8080"

    params = {
        "UserID": USER_ID,
        "Action": "Login",
        "TerminalFlag": "1",
        "TerminalOsType": "0",
        "STBID": STBID,
        "stbtype": STB_TYPE
    }
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-cn",
        "Accept-Encoding": "gzip",
        "Host": f"{EAS_DOMAIN}:8080",  # 关键：用域名 Host 头
        "Referer": f"http://{EAS_DOMAIN}:8080/iptvepg/platform/index.jsp?UserID={USER_ID}&Action=Login&FCCSupport=1"
    }
    url = f"{eas_base}/iptvepg/platform/getencrypttoken.jsp"
    try:
        response = requests.get(url, params=params, headers=headers, timeout=10)
        response.raise_for_status()
        match = re.search(r"GetAuthInfo\('(.*?)'\)", response.text)
        if match:
            token = match.group(1)
            log_message(f"获取 EncryptToken 成功: {token[:30]}...")
            return token
        else:
            log_message("获取 EncryptToken 失败: 未找到 GetAuthInfo 调用")
            return None
    except Exception as e:
        log_message(f"获取 EncryptToken 异常: {str(e)}")
        return None


def generate_authenticator_3des(encrypt_token, key, rand_num=None):
    """使用 3DES ECB 生成 Authenticator (论坛通用算法)
    注意: 部分 3DES 密钥会退化为单 DES，此时自动降级为 DES"""
    if rand_num is None:
        rand_num = str(random.randint(10000000, 99999999))
    # 构建明文字符串: random$token$UserID$STBID$IP$MAC$$CTC
    plaintext = f"{rand_num}${encrypt_token}${USER_ID}${STBID}${STB_IP}${MAC}$$CTC"
    msg_bytes = plaintext.encode('utf-8')
    padded_msg = pad(msg_bytes, DES3.block_size)

    # 3DES 密钥: 取 key 前 8 位小写 + 16 个 null 字节 = 24 字节
    # 部分 key 会导致 3DES 退化，此时回退到 DES
    key_str = key[:8].lower()
    try:
        key_bytes = key_str.encode('ascii') + (b'\x00' * 16)
        cipher = DES3.new(key_bytes, DES3.MODE_ECB)
        encrypted = cipher.encrypt(padded_msg)
        return binascii.hexlify(encrypted).decode('utf-8').upper()
    except ValueError:
        # 3DES 退化，使用 DES
        pass

    # 降级: 当 K2==K3 时 3DES 退化为 DES，直接用 DES
    des_key = key_str[:8].ljust(8, '0')
    des_cipher = DES.new(des_key.encode('ascii'), DES.MODE_ECB)
    encrypted = des_cipher.encrypt(padded_msg)
    return binascii.hexlify(encrypted).decode('utf-8').upper()


def generate_authenticator_des(encrypt_token, key, rand_num=None):
    """使用 DES ECB 生成 Authenticator (山东联通参考算法)"""
    if rand_num is None:
        rand_num = str(random.randint(10000000, 99999999))
    plaintext = f"{rand_num}${encrypt_token}${USER_ID}${STBID}${STB_IP}${MAC}$$CTC"
    # DES 密钥: 取 key 前 8 位, 不足补 '0'
    key_str = key[:8].ljust(8, '0')
    key_bytes = key_str.encode('utf-8')
    msg_bytes = plaintext.encode('utf-8')
    padded_msg = pad(msg_bytes, DES.block_size)
    cipher = DES.new(key_bytes, DES.MODE_ECB)
    encrypted = cipher.encrypt(padded_msg)
    return binascii.hexlify(encrypted).decode('utf-8').upper()


def generate_authenticator(encrypt_token):
    """根据配置自动选择合适的加密算法生成 Authenticator"""
    if not ENCRYPT_KEY or not MAC:
        log_message("动态 Authenticator 生成失败: 缺少 ENCRYPT_KEY 或 MAC")
        return None
    # 先尝试 3DES (部分密钥退化为 DES 时自动降级)
    try:
        auth = generate_authenticator_3des(encrypt_token, ENCRYPT_KEY)
        log_message("Authenticator 动态生成成功")
        return auth
    except Exception as e:
        log_message(f"3DES 生成失败, 尝试 DES: {str(e)}")
    # 回退 DES 方式
    try:
        auth = generate_authenticator_des(encrypt_token, ENCRYPT_KEY)
        log_message("Authenticator 动态生成成功 (DES)")
        return auth
    except Exception as e:
        log_message(f"DES 生成也失败: {str(e)}")
        return None


def get_user_token(force_refresh=False):
    """获取用户 token，带 48 小时缓存"""
    global _token_cache, Authenticator

    # 检查缓存
    now = time.time()
    if not force_refresh and _token_cache["token"] and (now - _token_cache["time"]) < TOKEN_TTL:
        return _token_cache["token"]

    # 缓存过期或强制刷新 → 重新认证
    use_dynamic = bool(ENCRYPT_KEY and MAC)
    if use_dynamic:
        encrypt_token = get_encrypt_token()
        if encrypt_token:
            dynamic_auth = generate_authenticator(encrypt_token)
            if dynamic_auth:
                log_message("使用动态生成的 Authenticator 进行认证")
                auth_value = dynamic_auth
            else:
                log_message("动态生成 Authenticator 失败，回退到静态配置")
                auth_value = Authenticator
        else:
            log_message("获取 EncryptToken 失败，回退到静态配置")
            auth_value = Authenticator
    else:
        auth_value = Authenticator

    try:
        url = f"{BASE_URL}/iptvepg/platform/auth.jsp"
        querystring = {"easip": "172.16.5.214", "ipVersion": "4", "networkid": "1", "serterminalno": "9923"}
        payload = f"UserID={USER_ID}&Authenticator={auth_value}&StbIP={STB_IP}"
        headers = {
            "Accept-Encoding": "deflate, gzip",
            "Origin": "http://epg.itv.cq.cn:8080",
            "User-Agent": USER_AGENT,
            "Accept": "application/xml,application/xhtml+xml,text/html;q=0.9,text/plain;q=0.8,image/png,*/*;q=0.5",
            "Connection": "Keep-Alive",
            "content-type": "application/x-www-form-urlencoded"
        }
        response = requests.request("POST", url, data=payload, headers=headers, params=querystring)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        script_tags = soup.find_all('script')
        for script in script_tags:
            if script.string and 'jsSetConfig(\'UserToken\'' in script.string:
                match = re.search(r"jsSetConfig\('UserToken',\s*'([^']+)'", script.string)
                if match:
                    jsessionid = response.cookies.get('JSESSIONID')
                    user_token = match.group(1)
                    token_jsessionid = [user_token, jsessionid]
                    # 写入缓存
                    _token_cache["token"] = token_jsessionid
                    _token_cache["time"] = now
                    return token_jsessionid
    except requests.exceptions.RequestException as e:
        log_message(f"网络请求失败：{str(e)}")
        return None


def _init_channel_session(jsessionid):
    """初始化频道服务会话（BASE_URL）"""
    token = _token_cache["token"][0] if _token_cache.get("token") else ""
    if not token:
        return
    session = requests.Session()
    session.cookies.set("JSESSIONID", jsessionid)
    _init_service_session(session, token, BASE_URL)


def log_message(message):
    try:
        os.makedirs('static', exist_ok=True)
        with open('static/relogs.txt', 'a', encoding='utf-8') as file:
            file.write(f"{datetime.now()} {message}\n")
    except Exception as e:
        print(f"[AutoIPTV] 写日志失败: {e}", flush=True)


def cleanup_logs():
    """清理超过 24 小时的日志"""
    import shutil
    log_file = 'static/relogs.txt'
    tmp_file = 'static/relogs.tmp'
    now = datetime.now()
    kept = 0
    removed = 0
    try:
        with open(log_file, 'r', encoding='utf-8') as fin, \
             open(tmp_file, 'w', encoding='utf-8') as fout:
            for line in fin:
                line = line.strip()
                if not line:
                    continue
                try:
                    ts_str = line[:19]
                    ts = datetime.strptime(ts_str, '%Y-%m-%d %H:%M:%S')
                    if (now - ts).total_seconds() < 86400:
                        fout.write(line + '\n')
                        kept += 1
                    else:
                        removed += 1
                except ValueError:
                    fout.write(line + '\n')
                    kept += 1
        shutil.move(tmp_file, log_file)
        if removed > 0:
            print(f"[AutoIPTV] 日志清理: 保留 {kept} 条, 清理 {removed} 条")
    except FileNotFoundError:
        pass
    except Exception as e:
        print(f"[AutoIPTV] 日志清理失败: {e}")


def get_channels():
    user_token = get_user_token()
    if not user_token:
        log_message("获取用户token失败")
        return "同步失败：无法获取用户token"

    # 在 BASE_URL 上初始化频道会话
    _init_channel_session(user_token[1])

    # 尝试获取频道列表，最多重试 2 次（JESSIONID 可能过期）
    for attempt in range(2):
        result = _do_fetch_channels(user_token)
        if result == "retry":
            log_message("会话可能过期，强制刷新 token 重试")
            user_token = get_user_token(force_refresh=True)
            if not user_token:
                return "同步失败：刷新token失败"
            continue
        return result
    return "同步失败！"


def _do_fetch_channels(user_token):
    """执行一次频道列表获取，返回成功/失败/需要重试"""
    url = f"{BASE_URL}/iptvepg/function/frameset_builder.jsp"
    payload = "MAIN_WIN_SRC=/iptvepg/frame1341/portal.jsp&NEED_UPDATE_STB=1&BUILD_ACTION=FRAMESET_BUILDER&hdmistatus=undefined"
    headers = {
        "Accept-Encoding": "deflate, gzip",
        "Origin": f"{BASE_URL}",
        "User-Agent": USER_AGENT,
        "Accept": "application/xml,application/xhtml+xml,text/html;q=0.9,text/plain;q=0.8,image/png,*/*;q=0.5",
        "Connection": "Keep-Alive",
        "content-type": "application/x-www-form-urlencoded",
        "cookie": "JSESSIONID=" + user_token[1] + "",
        "SessionID": user_token[1]
    }
    response = requests.request("POST", url, data=payload, headers=headers)
    # 检查请求是否成功
    if response.status_code == 200:
        # 正则表达式提取每个完整的 jsSetConfig('Channel', ...) 块
        # 每个频道数据格式如: jsSetConfig('Channel','ChannelID="...",ChannelName="CCTV1",...ChannelURL="igmp://...",...ChannelSDP="igmp://...|rtsp://...",...');
        channel_blocks = re.findall(r"jsSetConfig\('Channel',\s*'([^']+)'\)", response.text)
        if channel_blocks:
            channels_udpxy = []
            channels_rtsp = []
            # 用于提取 AuthInfo 中的时间戳线索
            usersessionid = ""
            for block in channel_blocks:
                # 提取 ChannelName
                name_match = re.search(r'ChannelName="([^"]*)"', block)
                if not name_match:
                    continue
                channel_name = name_match.group(1)

                # 提取 ChannelURL 中的 igmp 地址
                url_match = re.search(r'ChannelURL="([^"]*)"', block)
                if not url_match:
                    continue
                channel_url = url_match.group(1)

                # --- UDPXY 版本（igmp 转 http） ---
                igmp_addr = channel_url.replace('igmp://', '')
                channels_udpxy.append(f"{channel_name},{UDPXY}{igmp_addr}")

                # --- RTSP 点播版本 ---
                # 优先从 ChannelSDP 提取，格式: igmp://...|rtsp://...
                rtsp_url = ""
                sdp_match = re.search(r'ChannelSDP="[^"]*?(rtsp://[^"]+)"', block)
                if sdp_match:
                    rtsp_url = sdp_match.group(1)
                else:
                    # 其次从 TimeShiftURL 提取
                    ts_match = re.search(r'TimeShiftURL="[^"]*?(rtsp://[^"]+)"', block)
                    if ts_match:
                        rtsp_url = ts_match.group(1)
                    else:
                        # 最后从 ChannelURL 本身找 rtsp
                        url_rtsp = re.search(r'rtsp://[^"]+', channel_url)
                        if url_rtsp:
                            rtsp_url = url_rtsp.group(0)

                if rtsp_url:
                    # 生成带时间变量的 URL（用于 APTV catchup-source）
                    # 使用 Playseek 格式（兼容 APTV playseek 标准和 RTSP 服务器 API）
                    if '?' in rtsp_url:
                        rtsp_url_catchup = rtsp_url + '&Playseek=${(b)yyyyMMddHHmmss:utc}-${(e)yyyyMMddHHmmss:utc}'
                    else:
                        rtsp_url_catchup = rtsp_url + '?Playseek=${(b)yyyyMMddHHmmss:utc}-${(e)yyyyMMddHHmmss:utc}'
                    channels_rtsp.append(f"{channel_name},{rtsp_url_catchup},{rtsp_url}")

                # 提取 usersessionid 用于分析有效期
                if not usersessionid:
                    usid_match = re.search(r'usersessionid=(\d+)', block)
                    if usid_match:
                        usersessionid = usid_match.group(1)

            # 保存 UDPXY 版本（保持向后兼容）
            with open('static/channels.txt', 'w', encoding='utf-8') as file:
                for channel in channels_udpxy:
                    file.write(channel + '\n')

            # 保存 RTSP 版本
            with open('static/channels_rtsp.txt', 'w', encoding='utf-8') as file:
                for channel in channels_rtsp:
                    file.write(channel + '\n')

            # 保存同步时间戳和会话信息，用于前端展示有效期
            now = datetime.now()
            sync_info = {
                "last_sync_time": now.strftime("%Y-%m-%d %H:%M:%S"),
                "last_sync_timestamp": int(now.timestamp()),
                "usersessionid": usersessionid,
                "channel_count_udpxy": len(channels_udpxy),
                "channel_count_rtsp": len(channels_rtsp)
            }
            with open('static/sync_info.json', 'w', encoding='utf-8') as f:
                json.dump(sync_info, f, indent=4, ensure_ascii=False)

            log_message(f"更新成功，获取到 {len(channels_udpxy)} 个UDPXY频道，{len(channels_rtsp)} 个RTSP频道")
            return "同步成功！"
        else:
            # 无频道数据 - 可能是 JSESSIONID 过期
            resp_preview = response.text[:200]
            log_message(f"频道数据获取失败，响应前200字符: {resp_preview}")
            return "retry"
    else:
        return f"访问失败！ {response.status_code}"


def get_channels_content():
    try:
        with open('static/channels.txt', 'r', encoding='utf-8') as file:
            return file.read()
    except FileNotFoundError:
        return "暂无频道数据"

def get_channels_rtsp_content():
    try:
        with open('static/channels_rtsp.txt', 'r', encoding='utf-8') as file:
            return file.read()
    except FileNotFoundError:
        return "暂无频道数据"

def get_logs_content():
    try:
        with open('static/relogs.txt', 'r', encoding='utf-8') as file:
            return file.read()
    except FileNotFoundError:
        return "暂无日志"

def get_sync_info():
    """获取同步信息"""
    try:
        with open('static/sync_info.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


# ========== EPG 节目单功能 ==========

def get_channel_id_mapping():
    """从 channels_rtsp.txt 提取频道名和 channelId 的映射"""
    mapping = {}
    try:
        with open('static/channels_rtsp.txt', 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                parts = line.split(',', 2)
                if len(parts) < 2:
                    continue
                name = parts[0]
                url = parts[1]  # 使用 catchup URL（第一个 URL）
                # 尝试从 programid 或 channelId 参数提取
                match = re.search(r'[?&](?:programid|channelId)=([^&]+)', url)
                if match:
                    channel_id = match.group(1)
                    mapping[channel_id] = name
    except FileNotFoundError:
        pass
    return mapping


def rebuild_epg_session(session, token, channel_id):
    """重建 EPG 会话（EPG 服务器要求先触发 rebuild 再获取数据）"""
    epg_url = f"{EPG_HOST}/iptvepg/frame1265/utilsData/tVodProgramList.jsp"
    params = {"channelId": channel_id, "dateIndex": 0, "dateSize": 2, "tVodNumPerPage": 999}
    headers = {
        "Accept-Encoding": "gzip",
        "Referer": f"{EPG_HOST}/iptvepg/frame1265/channel/channelPlayingList.html",
        "Accept-Language": "zh-cn",
        "User-Agent": USER_AGENT,
        "Accept": "text/xml, text/html, application/xhtml+xml, image/png, text/plain, */*;q=0.8"
    }

    # 第一次调用触发 rebuild 页面
    try:
        r = session.get(epg_url, params=params, headers=headers, timeout=10)
        raw_text = r.content.decode('GBK', errors='replace')
        match = re.search(r"frameurl=([^']+)'", raw_text)
        if match:
            # 使用正确的 rebuild 路径：/iptvepg/function/ 而非 /frame1265/utilsData/
            rebuild_url = f"{EPG_HOST}/iptvepg/function/rebuildsessionresponse.jsp"
            session.get(
                rebuild_url,
                params={"UserToken": token, "ismenu": 0, "frameurl": url_quote(match.group(1))},
                headers=headers,
                timeout=10
            )
    except Exception:
        pass


def fetch_epg_for_channel(session, channel_id, channel_name, date_indexes=None):
    """获取单个频道的 EPG 数据，支持多天循环"""
    if date_indexes is None:
        date_indexes = [-1, 0, 1]  # 默认：昨天(-1) + 今天(0) + 明天(1)
    headers = {
        "Accept-Encoding": "gzip",
        "Referer": f"{EPG_HOST}/iptvepg/frame1265/channel/channelPlayingList.html",
        "Accept-Language": "zh-cn",
        "User-Agent": USER_AGENT,
        "Accept": "text/xml, text/html, application/xhtml+xml, image/png, text/plain, */*;q=0.8"
    }

    all_programs = []
    for di in date_indexes:
        try:
            # dateIndex=0 需要 dateSize>=2 才能获取到当天数据
            ds = 2 if di == 0 else 1
            params = {"channelId": channel_id, "dateIndex": di, "dateSize": ds, "tVodNumPerPage": 999}
            r = session.get(
                f"{EPG_HOST}/iptvepg/frame1265/utilsData/tVodProgramList.jsp",
                params=params, headers=headers, timeout=15
            )
            r.raise_for_status()
            try:
                raw_text = r.content.decode('utf-8')
            except UnicodeDecodeError:
                raw_text = r.content.decode('GBK', errors='replace')

            if not raw_text.strip().startswith('['):
                continue

            data = json.loads(raw_text)
            for day_data in data[1]['data']:
                for prog in day_data:
                    all_programs.append({
                        'start': prog['beginTimeFormat'],
                        'stop': prog['endTimeFormat'],
                        'title': prog['programName'],
                        'channel_id': channel_id,
                        'channel_name': channel_name
                    })
        except Exception:
            continue

    return all_programs if all_programs else None


def fetch_all_epg(max_workers=10, date_indexes=None):
    """获取所有频道的 EPG 数据"""
    if date_indexes is None:
        date_indexes = [-1, 0, 1]  # 默认：昨天(-1) + 今天(0) + 明天(1)
    mapping = get_channel_id_mapping()
    if not mapping:
        return []

    # 先认证一次，获取 user_token
    user_token = get_user_token()
    if not user_token:
        log_message("EPG: 获取用户 token 失败")
        return []
    token = user_token[0]

    all_programs = []
    channel_ids = list(mapping.items())

    def process_channel(item):
        cid, cname = item
        import requests as req
        session = req.Session()
        # 在 EPG_HOST 上初始化会话
        _init_service_session(session, token, EPG_HOST)
        # rebuild
        rebuild_epg_session(session, token, cid)
        # 获取 EPG
        return fetch_epg_for_channel(session, cid, cname, date_indexes=date_indexes)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(process_channel, item): item for item in channel_ids}
        for future in as_completed(futures):
            result = future.result()
            if result:
                all_programs.extend(result)

    # 按时间排序
    all_programs.sort(key=lambda x: (x['start'], x['channel_name']))
    return all_programs


def build_xmltv(programs):
    """将 EPG 数据构建为 XMLTV 格式"""
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<!DOCTYPE tv SYSTEM "http://www.xmltvepg.dtd">',
        '<tv generator-info-name="AutoIPTV">'
    ]
    
    # 收集所有频道
    channels = {}
    for p in programs:
        if p['channel_id'] not in channels:
            channels[p['channel_id']] = p['channel_name']
    
    # 输出 channel 信息
    for cid, cname in channels.items():
        lines.append(f'  <channel id="{cid}">')
        lines.append(f'    <display-name lang="zh">{cname}</display-name>')
        lines.append(f'  </channel>')
    
    # 输出 programme 信息
    for p in programs:
        # EPG 服务器返回的是北京时间 (UTC+8)，标注时区供播放器正确解析
        start_str = p['start'] + " +0800"
        stop_str = p['stop'] + " +0800"
        lines.append(f'  <programme start="{start_str}" stop="{stop_str}" channel="{p["channel_id"]}">')
        lines.append(f'    <title lang="zh">{p["title"]}</title>')
        lines.append(f'  </programme>')
    
    lines.append('</tv>')
    return '\n'.join(lines)


# 内存缓存，避免频繁读取 epg_cache.json
_epg_memory_cache = None
_epg_memory_cache_time = 0
_epg_fetch_lock = threading.Lock()  # 防止并发抓取 EPG

# ========== 异步 EPG 抓取 ==========
_epg_async_status = {"running": False, "last_error": None, "progress": ""}


def epg_async_fetch(days=8):
    """后台线程：异步抓取 EPG，不阻塞 Web 请求"""
    global _epg_memory_cache, _epg_memory_cache_time, _epg_async_status
    if _epg_async_status["running"]:
        return
    _epg_async_status["running"] = True
    _epg_async_status["last_error"] = None
    _epg_async_status["progress"] = "正在抓取 EPG 数据..."
    try:
        log_message("后台异步抓取 EPG 开始...")
        # 计算日期范围
        today = datetime.now()
        date_indexes = [i for i in range(-(days - 2), 2)]  # days-2天前 ~ 明天
        programs = fetch_all_epg(date_indexes=date_indexes)
        if programs:
            now_ts = time.time()
            # 保存到文件缓存
            cache_file = 'static/epg_cache.json'
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump({
                    "programs": programs,
                    "cache_time": now_ts,
                    "days": days
                }, f, indent=2, ensure_ascii=False)
            # 生成 XMLTV
            xml_data = build_xmltv(programs)
            with open('static/epg.xml', 'w', encoding='utf-8') as f:
                f.write(xml_data)
            # 更新内存缓存
            _epg_memory_cache = programs
            _epg_memory_cache_time = now_ts
            log_message(f"后台异步抓取 EPG 完成，共 {len(programs)} 个节目")
            _epg_async_status["progress"] = f"EPG 抓取完成，共 {len(programs)} 个节目"
        else:
            log_message("后台异步抓取 EPG 完成，未获取到数据")
            _epg_async_status["progress"] = "EPG 未获取到数据"
    except Exception as e:
        err_msg = f"后台异步抓取 EPG 失败: {str(e)}"
        log_message(err_msg)
        _epg_async_status["last_error"] = str(e)
        _epg_async_status["progress"] = err_msg
    finally:
        _epg_async_status["running"] = False

def get_epg(refresh=False, days=8, async_fetch=True):
    """获取 EPG 数据，优先使用缓存
    async_fetch=True: 缓存过期时后台异步抓取，立即返回旧缓存（不阻塞HTTP请求）
    refresh=True: 强制后台刷新
    days: 抓取天数，默认8天=过去6天(回看)+今天+明天"""
    global _epg_memory_cache, _epg_memory_cache_time

    cache_file = 'static/epg_cache.json'
    xml_file = 'static/epg.xml'

    now_ts = time.time()

    # 1. 内存缓存（当前进程有效，30秒内直接返回）
    if not refresh:
        if _epg_memory_cache is not None and now_ts - _epg_memory_cache_time < 30:
            return _epg_memory_cache

    # 2. 尝试读文件缓存
    cached_ok = False
    cached_programs = []
    try:
        with open(cache_file, 'r', encoding='utf-8') as f:
            cached = json.load(f)
            cache_time = cached.get('cache_time', 0)
            cache_days = cached.get('days', 0)
            if now_ts - cache_time < 3600 and cache_days == days:
                _epg_memory_cache = cached.get('programs', [])
                _epg_memory_cache_time = now_ts
                cached_programs = _epg_memory_cache
                cached_ok = True
    except (FileNotFoundError, json.JSONDecodeError, UnicodeDecodeError):
        try:
            os.remove(cache_file)
        except OSError:
            pass

    if cached_ok and not refresh:
        return cached_programs

    # 3. 需要抓取
    if async_fetch:
        # 后台异步：启动后台线程抓取，立即返回缓存数据（即使过期）
        if not _epg_async_status["running"]:
            t = threading.Thread(target=epg_async_fetch, args=(days,), daemon=True)
            t.start()
            log_message("EPG: 后台异步抓取已启动")
        if cached_ok:
            return cached_programs
        # 没有缓存时返回空（前台会显示加载中）
        return []
    else:
        # 同步抓取（定时任务使用）
        programs = _sync_fetch_epg(days)
        return programs


def _sync_fetch_epg(days=8):
    """同步抓取 EPG（定时任务使用，不启动后台线程）"""
    cache_file = 'static/epg_cache.json'
    xml_file = 'static/epg.xml'

    # 计算需要抓取的日期索引
    if days >= 2:
        past_days = max(days - 2, 1)
        date_indexes = list(range(-past_days, 2))
    else:
        date_indexes = [0]

    programs = fetch_all_epg(date_indexes=date_indexes)

    # 写入内存缓存
    _epg_memory_cache = programs
    _epg_memory_cache_time = time.time()

    # 保存文件缓存
    cache_data = {
        'cache_time': datetime.now().timestamp(),
        'days': days,
        'programs': programs
    }
    with open(cache_file, 'w', encoding='utf-8') as f:
        json.dump(cache_data, f, ensure_ascii=False, indent=2)

    # 生成并保存 XMLTV
    xmltv = build_xmltv(programs)
    with open(xml_file, 'w', encoding='utf-8') as f:
        f.write(xmltv)

    log_message(f"EPG 更新完成，获取到 {len(programs)} 个节目（天数: {days}）")
    return programs


@app.route('/')
def index():
    config = load_config()
    channels = get_channels_content()
    channels_rtsp = get_channels_rtsp_content()
    logs = get_logs_content()
    sync_info = get_sync_info()
    # 判断是否启用了动态 Authenticator 生成
    config['DYNAMIC_AUTH_ENABLED'] = bool(config.get('MAC') and config.get('ENCRYPT_KEY'))
    return render_template('index.html', config=config, channels=channels, channels_rtsp=channels_rtsp, logs=logs, sync_info=sync_info)

@app.route('/save_config', methods=['POST'])
def save_config():
    try:
        # 检查必填字段
        user_id = request.form.get('user_id', '').strip()
        stbid = request.form.get('stbid', '').strip()
        authenticator = request.form.get('authenticator', '').strip()

        if not all([user_id, stbid, authenticator]):
            flash('USER_ID、STBID 和 Authenticator 为必填项')
            return redirect(url_for('index'))

        # 创建新的配置字典
        new_config = {
            'UDPXY': request.form.get('udpxy', '').strip(),
            'BASE_URL': request.form.get('base_url', '').strip(),
            'USER_ID': user_id,
            'STBID': stbid,
            'USER_AGENT': request.form.get('user_agent', '').strip(),
            'Authenticator': authenticator,
            'EPG_HOST': request.form.get('epg_host', '').strip(),
            'STB_IP': request.form.get('stb_ip', '').strip() or '172.34.24.71',
            'STB_TYPE': request.form.get('stb_type', '').strip(),
            'MAC': request.form.get('mac', '').strip().upper(),
            'ENCRYPT_KEY': request.form.get('encrypt_key', '').strip(),
            'DNS_SERVERS': request.form.get('dns_servers', '').strip() or '172.16.5.144,172.16.5.145',
            'EAS_DOMAIN': request.form.get('eas_domain', '').strip() or 'epg.itv.cq.cn',
            'EAS_IP': request.form.get('eas_ip', '').strip()
        }

        # 保存配置
        with open('static/config.json', 'w', encoding='utf-8') as f:
            json.dump(new_config, f, indent=4, ensure_ascii=False)

        # 更新全局配置变量
        global config, BASE_URL, USER_ID, STBID, USER_AGENT, Authenticator, UDPXY, EPG_HOST
        global STB_IP, STB_TYPE, MAC, ENCRYPT_KEY, DNS_SERVERS, EAS_DOMAIN, EAS_IP
        config = new_config
        BASE_URL = new_config['BASE_URL']
        USER_ID = new_config['USER_ID']
        STBID = new_config['STBID']
        USER_AGENT = new_config['USER_AGENT']
        Authenticator = new_config['Authenticator']
        UDPXY = new_config['UDPXY']
        EPG_HOST = new_config.get('EPG_HOST', 'http://172.23.35.201:8080')
        STB_IP = new_config.get('STB_IP', '172.34.24.71')
        STB_TYPE = new_config.get('STB_TYPE', '')
        MAC = new_config.get('MAC', '')
        ENCRYPT_KEY = new_config.get('ENCRYPT_KEY', '')
        DNS_SERVERS = new_config.get('DNS_SERVERS', '172.16.5.144,172.16.5.145')
        EAS_DOMAIN = new_config.get('EAS_DOMAIN', 'epg.itv.cq.cn')
        EAS_IP = new_config.get('EAS_IP', '').strip()
        # 清除 token 缓存（配置变更后强制重新认证）
        _token_cache["token"] = None
        _token_cache["time"] = 0
        # 如果 EAS_IP 为空，尝试重新 DNS 解析
        if not EAS_IP and DNS_SERVERS:
            _dns_list = [s.strip() for s in DNS_SERVERS.split(',') if s.strip()]
            if _dns_list:
                try:
                    _resolver = dns.resolver.Resolver()
                    _resolver.nameservers = _dns_list
                    _resolver.timeout = 3
                    _resolver.lifetime = 5
                    answers = _resolver.resolve(EAS_DOMAIN, 'A')
                    EAS_IP = str(answers[0])
                except Exception:
                    pass
        # 更新频道列表
        result = get_channels()
        flash('配置保存成功，频道列表已更新')
        return redirect(url_for('index'))
    except Exception as e:
        log_message(f"保存配置失败：{str(e)}")
        flash(f'保存配置失败：{str(e)}')
        return redirect(url_for('index'))
