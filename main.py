from datetime import datetime
import requests
from bs4 import BeautifulSoup
import re
from config import load_config
from flask import render_template, Flask, request, redirect, url_for, flash, jsonify
import json
import os

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
        # 正则表达式提取 ChannelName 和 ChannelURL
        pattern = r'ChannelName="([^"]+)",.*?ChannelURL="([^"]+)"'
        # 查找所有匹配的内容
        matches = re.findall(pattern, response.text)
        if matches:
            # 输出每个匹配的 ChannelName 和 ChannelURL
            channels = []
            for match in matches:
                channel_name = match[0]
                channel_url = match[1].replace('igmp://', '')
                channels.append(f"{channel_name},{UDPXY}{channel_url}")
            with open('static/channels.txt', 'w', encoding='utf-8') as file:
                for channel in channels:
                    file.write(channel + '\n')
            log_message("更新成功")
            return "同步成功！"
        else:
            log_message("组播地址获取失败")
            return "同步失败！"
    else:
        return f"访问失败！ {response.status_code}"


def get_channels_content():
    try:
        with open('static/channels.txt', 'r', encoding='utf-8') as file:
            return file.read()
    except FileNotFoundError:
        return "暂无频道数据"

def get_logs_content():
    try:
        with open('static/relogs.txt', 'r', encoding='utf-8') as file:
            return file.read()
    except FileNotFoundError:
        return "暂无日志"

@app.route('/')
def index():
    config = load_config()
    channels = get_channels_content()
    logs = get_logs_content()
    return render_template('index.html', config=config, channels=channels, logs=logs)

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
            'Authenticator': authenticator
        }
        
        # 保存配置
        with open('static/config.json', 'w', encoding='utf-8') as f:
            json.dump(new_config, f, indent=4, ensure_ascii=False)
        
        # 更新全局配置变量
        global config, BASE_URL, USER_ID, STBID, USER_AGENT, Authenticator, UDPXY
        config = new_config
        BASE_URL = new_config['BASE_URL']
        USER_ID = new_config['USER_ID']
        STBID = new_config['STBID']
        USER_AGENT = new_config['USER_AGENT']
        Authenticator = new_config['Authenticator']
        UDPXY = new_config['UDPXY']
        # 更新频道列表
        result = get_channels()
        flash('配置保存成功，频道列表已更新')
        return redirect(url_for('index'))
    except Exception as e:
        log_message(f"保存配置失败：{str(e)}")
        flash(f'保存配置失败：{str(e)}')
        return redirect(url_for('index'))


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
