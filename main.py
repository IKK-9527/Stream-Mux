from datetime import datetime, timedelta
import requests
from bs4 import BeautifulSoup
import re
from config import load_config
from flask import render_template, Flask, request, redirect, url_for, flash, jsonify
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import quote as url_quote, urlparse, parse_qs

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

def get_user_token():
    try:
        url = f"{BASE_URL}/iptvepg/platform/auth.jsp"
        querystring = {"easip": "172.16.5.214", "ipVersion": "4", "networkid": "1", "serterminalno": "9923"}
        payload = f"UserID={USER_ID}&Authenticator={Authenticator}&StbIP=172.34.24.71"
        headers = {
            "Accept-Encoding": "deflate, gzip",
            "Origin": "http://epg.itv.cq.cn:8080",
            "User-Agent": USER_AGENT,
            "Accept": "application/xml,application/xhtml+xml,text/html;q=0.9,text/plain;q=0.8,image/png,*/*;q=0.5",
            "Connection": "Keep-Alive",
            "Content-Length": "315",
            "content-type": "application/x-www-form-urlencoded"
        }
        response = requests.request("POST", url, data=payload, headers=headers, params=querystring)
        response.raise_for_status()  # 检查响应状态
        soup = BeautifulSoup(response.text, 'html.parser')
        # 查找所有<script>标签
        script_tags = soup.find_all('script')
        # 遍历每个<script>标签，查找包含UserToken的内容
        for script in script_tags:
            # 如果script.string存在且包含UserToken
            if script.string and 'jsSetConfig(\'UserToken\'' in script.string:
                # 提取UserToken的值
                match = re.search(r"jsSetConfig\('UserToken',\s*'([^']+)'", script.string)
                if match:
                    jsessionid = response.cookies.get('JSESSIONID')
                    user_token = match.group(1)
                    token_jsessionid = [user_token, jsessionid]
                    # 模拟访问iptvepg/function/index.jsp，不知道为啥要模拟访问下才能获取播放地址
                    get_stbid(user_token, jsessionid)
                    return token_jsessionid
    except requests.exceptions.RequestException as e:
        log_message(f"网络请求失败：{str(e)}")  # 使用log_message函数来追加日志
        return None


def get_stbid(user_token, jsessionid):
    url = f"{BASE_URL}/iptvepg/function/index.jsp"
    querystring = {
        "UserGroupNMB": "31",
        "EPGGroupNMB": "31",
        "UserToken": user_token,
        "UserID": USER_ID,
        "STBID": STBID,
        "easip": "172.16.5.214",
        "networkid": "1",
        "loadbalanced": "-1"}
    headers = {
        "Accept-Encoding": "deflate, gzip",
        "Origin": "http://epg.itv.cq.cn:8080",
        "User-Agent": USER_AGENT,
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/xml,application/xhtml+xml,text/html;q=0.9,text/plain;q=0.8,image/png,*/*;q=0.5",
        "Connection": "Keep-Alive",
        "cookie": "JSESSIONID=" + jsessionid + ""
    }
    requests.request("GET", url, headers=headers, params=querystring)
    post_sessionid(user_token, jsessionid)


def post_sessionid(user_token, jsessionid):
    url = f"{BASE_URL}/iptvepg/function/funcportalauth.jsp"
    payload = f"UserToken={user_token}&UserID={USER_ID}&STBID={STBID}&stbinfo=&prmid=&easip=172.16.5.214&networkid=1&stbtype=EC2106V1H_pub&drmsupplier="
    headers = {
        "Accept-Encoding": "deflate, gzip",
        "Origin": "http://epg.itv.cq.cn:8080",
        "User-Agent": USER_AGENT,
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/xml,application/xhtml+xml,text/html;q=0.9,text/plain;q=0.8,image/png,*/*;q=0.5",
        "Connection": "Keep-Alive",
        "Content-Length": "189",
        "content-type": "application/x-www-form-urlencoded",
        "cookie": "JSESSIONID=" + jsessionid + ""

    }
    requests.request("POST", url, data=payload, headers=headers)


def log_message(message):
    with open('static/relogs.txt', 'a', encoding='utf-8') as file:
        file.write(f"{datetime.now()} {message}\n")


def get_channels():
    user_token = get_user_token()
    if not user_token:
        log_message("获取用户token失败")
        return "同步失败：无法获取用户token"
    url = f"{BASE_URL}/iptvepg/function/frameset_builder.jsp"
    payload = "MAIN_WIN_SRC=/iptvepg/frame1341/portal.jsp&NEED_UPDATE_STB=1&BUILD_ACTION=FRAMESET_BUILDER&hdmistatus=undefined"
    headers = {
        "Accept-Encoding": "deflate, gzip",
        "Origin": "http://172.23.34.169:8080",
        "User-Agent": USER_AGENT,
        "Accept": "application/xml,application/xhtml+xml,text/html;q=0.9,text/plain;q=0.8,image/png,*/*;q=0.5",
        "Connection": "Keep-Alive",
        "Content-Length": "117",
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
            log_message("频道数据获取失败")
            return "同步失败！"
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


def get_epg_session():
    """创建 EPG 服务器会话，返回 (session, user_token)"""
    import requests as req
    session = req.Session()

    # 获取用户 token
    user_token = get_user_token()
    if not user_token:
        return None, None

    token = user_token[0]

    headers = {
        "Accept-Encoding": "deflate, gzip",
        "Origin": f"{EPG_HOST}",
        "User-Agent": USER_AGENT,
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Connection": "Keep-Alive",
    }

    # 1. 访问 EPG_HOST 的 index.jsp 初始化会话（如 STB 抓包所示）
    try:
        session.get(
            f"{EPG_HOST}/iptvepg/function/index.jsp",
            params={
                "UserGroupNMB": "31", "EPGGroupNMB": "31",
                "UserToken": token, "UserID": USER_ID, "STBID": STBID,
                "easip": "172.16.5.214", "networkid": "1", "loadbalanced": "-1"
            },
            headers={**headers, "Referer": f"{EPG_HOST}/iptvepg/function/index.jsp"},
            timeout=10
        )
    except Exception:
        pass

    # 2. POST funcportalauth.jsp 在 EPG_HOST 上建立认证（STB 抓包的关键步骤）
    try:
        payload = (
            f"UserToken={token}&UserID={USER_ID}&STBID={STBID}"
            f"&stbinfo=&prmid=&easip=172.16.5.214&networkid=1"
            f"&stbtype=EC2106V1H_pub&drmsupplier="
        )
        session.post(
            f"{EPG_HOST}/iptvepg/function/funcportalauth.jsp",
            data=payload,
            headers={**headers,
                "Referer": f"{EPG_HOST}/iptvepg/function/index.jsp?loadbalanced=0",
                "Origin": f"{EPG_HOST}",
            },
            timeout=10
        )
    except Exception:
        pass

    return session, token


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
    
    all_programs = []
    channel_ids = list(mapping.items())
    
    def process_channel(item):
        cid, cname = item
        local_session, local_token = get_epg_session()
        if not local_session:
            return None
        # 先 rebuild 一次（调用 rebuildsessionresponse.jsp 重建会话）
        rebuild_epg_session(local_session, local_token, cid)
        # 抓取多天数据
        return fetch_epg_for_channel(local_session, cid, cname, date_indexes=date_indexes)
    
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

def get_epg(refresh=False, days=7):
    """获取 EPG 数据，优先使用缓存
    days: 抓取天数，默认7天=过去6天(回看)+今天"""
    global _epg_memory_cache, _epg_memory_cache_time

    cache_file = 'static/epg_cache.json'
    xml_file = 'static/epg.xml'

    if not refresh:
        # 内存缓存（30秒有效，避免频繁读盘）
        now = time.time()
        if _epg_memory_cache is not None and now - _epg_memory_cache_time < 30:
            return _epg_memory_cache
        # 尝试从文件缓存读取
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                cached = json.load(f)
                cache_time = cached.get('cache_time', 0)
                cache_days = cached.get('days', 0)
                if datetime.now().timestamp() - cache_time < 3600 and cache_days == days:
                    programs = cached.get('programs', [])
                    _epg_memory_cache = programs
                    _epg_memory_cache_time = time.time()
                    return programs
        except (FileNotFoundError, json.JSONDecodeError, UnicodeDecodeError):
            try:
                os.remove(cache_file)
            except OSError:
                pass

    # 计算需要抓取的日期索引
    # EPG 服务器: dateIndex:-5~-1=过去5天, -6=6天前, 0=今天(dS=2)
    # days=7 -> 过去6天 + 今天 = 7天
    if days >= 2:
        past_days = max(days - 1, 1)
        date_indexes = list(range(-past_days, 1))  # 过去N天 + 今天(0)
    else:
        date_indexes = [0]

    # 重新获取
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
            'EPG_HOST': request.form.get('epg_host', '').strip()
        }
        
        # 保存配置
        with open('static/config.json', 'w', encoding='utf-8') as f:
            json.dump(new_config, f, indent=4, ensure_ascii=False)
        
        # 更新全局配置变量
        global config, BASE_URL, USER_ID, STBID, USER_AGENT, Authenticator, UDPXY, EPG_HOST
        config = new_config
        BASE_URL = new_config['BASE_URL']
        USER_ID = new_config['USER_ID']
        STBID = new_config['STBID']
        USER_AGENT = new_config['USER_AGENT']
        Authenticator = new_config['Authenticator']
        UDPXY = new_config['UDPXY']
        EPG_HOST = new_config.get('EPG_HOST', 'http://172.23.35.201:8080')
        # 更新频道列表
        result = get_channels()
        flash('配置保存成功，频道列表已更新')
        return redirect(url_for('index'))
    except Exception as e:
        log_message(f"保存配置失败：{str(e)}")
        flash(f'保存配置失败：{str(e)}')
        return redirect(url_for('index'))
