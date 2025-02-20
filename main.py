import datetime
from datetime import datetime
import requests
from bs4 import BeautifulSoup
import re

# def first_login():
#     url = "http://epg.itv.cq.cn:8080/iptvepg/platform/index.jsp"
#     querystring = {"UserID": "i52011813111@itv", "Action": "Login"}
#     payload = ""
#     headers = {
#         "Accept-Encoding": "deflate, gzip",
#         "User-Agent": "Mozilla/5.0 (compatible; EIS iPanel 2.0; Linux2.4.26/mips; win32; HI3110) AppleWebKit/2.0 (KHTML, like Gecko) EC2106V1H Hybroad;Resolution(PAL,720P,1080i)",
#         "Accept": "application/xml,application/xhtml+xml,text/html;q=0.9,text/plain;q=0.8,image/png,*/*;q=0.5",
#         "Connection": "Keep-Alive",
#         "content-type": "application/x-www-form-urlencoded"
#     }
#     response = requests.request("GET", url, data=payload, headers=headers, params=querystring)
#     #print(response.cookies)
#     login()

# def login():
#     url = "http://epg.itv.cq.cn:8080/iptvepg/platform/getencrypttoken.jsp"
#     querystring = {"UserID":"i52011813111@itv","Action":"Login","TerminalFlag":"1","TerminalOsType":"0","STBID":"","stbtype":""}
#     payload = ""
#     headers = {
#         "Accept-Encoding": "deflate, gzip",
#         "User-Agent": "Mozilla/5.0 (compatible; EIS iPanel 2.0; Linux2.4.26/mips; win32; HI3110) AppleWebKit/2.0 (KHTML, like Gecko) EC2106V1H Hybroad;Resolution(PAL,720P,1080i)",
#         "Accept": "application/xml,application/xhtml+xml,text/html;q=0.9,text/plain;q=0.8,image/png,*/*;q=0.5",
#         "Referer": "http://epg.itv.cq.cn:8080/iptvepg/platform/index.jsp?UserID=i52011813111@itv&Action=Login",
#         "Connection": "Keep-Alive",
#         "content-type": "application/x-www-form-urlencoded"
#     }
#     response = requests.request("GET", url, data=payload, headers=headers, params=querystring)
# 
#     get_user_token()

def get_user_token():
    url = "http://172.23.34.169:8080/iptvepg/platform/auth.jsp"
    querystring = {"easip": "172.16.5.214", "ipVersion": "4", "networkid": "1", "serterminalno": "9923"}
    payload = "UserID=i52011813111@itv&Authenticator=223E09B9CDEEEDC06493F45C524586A9EFD98D760A42A6FD776E18069F7092CDB42A44F39BE9CB92813766FC26776CE8D926E87753ECB0CC96C43F99B6279DA767049C1A7E036CE06E81EC7D1B85374C43144EE63E417DD0BEF2B274552481A933EE50D6EE68F5C3699F064F6201E3078B90B25DF275D178CFBABEABA88CB4F9016E27CA00F26792&StbIP=172.34.24.71"
    headers = {
        "Accept-Encoding": "deflate, gzip",
        "Origin": "http://epg.itv.cq.cn:8080",
        "User-Agent": "Mozilla/5.0 (compatible; EIS iPanel 2.0; Linux2.4.26/mips; win32; HI3110) AppleWebKit/2.0 (KHTML, like Gecko) EC2106V1H Hybroad;Resolution(PAL,720P,1080i)",
        "Accept": "application/xml,application/xhtml+xml,text/html;q=0.9,text/plain;q=0.8,image/png,*/*;q=0.5",
        "Referer": "http://epg.itv.cq.cn:8080/iptvepg/platform/getencrypttoken.jsp?UserID=i52011813111@itv&Action=Login&TerminalFlag=1&TerminalOsType=0&STBID=&stbtype=",
        "Connection": "Keep-Alive",
        "Content-Length": "315",
        "content-type": "application/x-www-form-urlencoded"
    }
    response = requests.request("POST", url, data=payload, headers=headers, params=querystring)
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
                token_jsessionid = [user_token,jsessionid]
                #模拟访问iptvepg/function/index.jsp，不知道为啥要模拟访问下才能获取播放地址
                get_stbid(user_token,jsessionid)
                return token_jsessionid

def get_stbid(user_token,jsessionid):
    url = "http://172.23.34.169:8080/iptvepg/function/index.jsp"
    querystring = {
        "UserGroupNMB": "31",
        "EPGGroupNMB": "31",
        "UserToken": user_token,
        "UserID": "i52011813111@itv",
        "STBID": "001002990060202014490C565C18DFE6",
        "easip": "172.16.5.214",
        "networkid": "1",
        "loadbalanced": "-1"}
    headers = {
        "Accept-Encoding": "deflate, gzip",
        "Origin": "http://epg.itv.cq.cn:8080",
        "User-Agent": "Mozilla/5.0 (compatible; EIS iPanel 2.0; Linux2.4.26/mips; win32; HI3110) AppleWebKit/2.0 (KHTML, like Gecko) EC2106V1H Hybroad;Resolution(PAL,720P,1080i)",
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/xml,application/xhtml+xml,text/html;q=0.9,text/plain;q=0.8,image/png,*/*;q=0.5",
        "Referer": "http://172.23.34.169:8080/iptvepg/platform/auth.jsp?easip=172.16.5.214&ipVersion=4&networkid=1&serterminalno=9923",
        "Connection": "Keep-Alive",
        "cookie": "JSESSIONID="+jsessionid+""
    }
    response = requests.request("GET", url, headers=headers, params=querystring)
    post_sessionid(user_token,jsessionid)

def post_sessionid(user_token,jsessionid):
    url = "http://172.23.34.169:8080/iptvepg/function/funcportalauth.jsp"
    payload = "UserToken="+user_token+"&UserID=i52011813111@itv&STBID=001002990060202014490C565C18DFE6&stbinfo=&prmid=&easip=172.16.5.214&networkid=1&stbtype=EC2106V1H_pub&drmsupplier="
    headers = {
        "Accept-Encoding": "deflate, gzip",
        "Origin": "http://epg.itv.cq.cn:8080",
        "User-Agent": "Mozilla/5.0 (compatible; EIS iPanel 2.0; Linux2.4.26/mips; win32; HI3110) AppleWebKit/2.0 (KHTML, like Gecko) EC2106V1H Hybroad;Resolution(PAL,720P,1080i)",
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/xml,application/xhtml+xml,text/html;q=0.9,text/plain;q=0.8,image/png,*/*;q=0.5",
        "Referer": "http://172.23.34.169:8080/iptvepg/function/index.jsp?loadbalanced=0?UserGroupNMB=31&EPGGroupNMB=31&UserToken=jOU6mN_vvrX3ItNhOoKySUo137099088&UserID=i52011813111@itv&STBID=001002990060202014490C565C18DFE6&easip=172.16.5.214&networkid=1&loadbalanced=-1",
        "Connection": "Keep-Alive",
        "Content-Length": "189",
        "content-type": "application/x-www-form-urlencoded",
        "cookie": "JSESSIONID="+jsessionid+""

    }
    response = requests.request("POST", url, data=payload, headers=headers)

def get_channels():
    user_token=get_user_token()
    url = "http://172.23.34.169:8080/iptvepg/function/frameset_builder.jsp"
    payload = "MAIN_WIN_SRC=/iptvepg/frame1341/portal.jsp&NEED_UPDATE_STB=1&BUILD_ACTION=FRAMESET_BUILDER&hdmistatus=undefined"
    headers = {
        "Accept-Encoding": "deflate, gzip",
        "Origin": "http://172.23.34.169:8080",
        "User-Agent": "Mozilla/5.0 (compatible; EIS iPanel 2.0; Linux2.4.26/mips; win32; HI3110) AppleWebKit/2.0 (KHTML, like Gecko) EC2106V1H Hybroad;Resolution(PAL,720P,1080i)",
        "Accept": "application/xml,application/xhtml+xml,text/html;q=0.9,text/plain;q=0.8,image/png,*/*;q=0.5",
        "Connection": "Keep-Alive",
        "Referer": "http://172.23.34.169:8080/iptvepg/function/frameset_judger.jsp",
        "Content-Length": "117",
        "content-type": "application/x-www-form-urlencoded",
        "cookie": "JSESSIONID="+user_token[1]+"",
        "SessionID":  user_token[1]
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
                channels.append(f"{channel_name},http://10.10.10.1:7088/udp/{channel_url}")
            with open('static/channels.txt', 'w', encoding='utf-8') as file:
                for channel in channels:
                    file.write(channel + '\n')
            with open('static/relogs.txt', 'w', encoding='utf-8') as file:
                file.write(str(datetime.now()) + '更新成功' + '\n')
            return "同步成功！"
        else:
            with open('static/relogs.txt', 'w', encoding='utf-8') as file:
                file.write(str(datetime.now()) + '组播地址获取失败！' + '\n')
            return "同步失败！"
    else:
        return f"访问失败！ {response.status_code}"

# if __name__ == '__main__':
#     get_channels()
