from flask import Flask, send_from_directory, request, render_template, jsonify, flash, redirect, url_for, Response
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from main import get_channels, index, save_config, get_sync_info  # 从 main.py 导入所需函数
import requests
import json
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'your_secret_key'  # 用于flash消息

# 主页路由
app.route('/')(index)

# 保存配置路由
app.route('/save_config', methods=['POST'])(save_config)

@app.route('/refresh_channels')
def refresh_channels_content():
    try:
        with open('static/channels.txt', 'r', encoding='utf-8') as f:
            data = f.read()
        return data
    except Exception as e:
        return f"获取UDPXY频道列表失败：{str(e)}"

@app.route('/refresh_channels_rtsp')
def refresh_channels_rtsp_content():
    try:
        with open('static/channels_rtsp.txt', 'r', encoding='utf-8') as f:
            data = f.read()
        return data
    except Exception as e:
        return f"获取RTSP频道列表失败：{str(e)}"

@app.route('/refresh_logs')
def refresh_logs_content():
    try:
        with open('static/relogs.txt', 'r', encoding='utf-8') as f:
            logs = f.read()
        return logs
    except Exception as e:
        return f"获取日志失败：{str(e)}"

# 订阅链接生成 - UDPXY版本（igmp转http）
@app.route('/sub')
def get_sub():
    return generate_sub('static/channels.txt')

# 订阅链接生成 - RTSP点播版本
@app.route('/sub_rtsp')
def get_sub_rtsp():
    return generate_sub('static/channels_rtsp.txt')

def generate_sub(channel_file):
    try:
        with open(channel_file, 'r', encoding='utf-8') as f:
            channels = f.readlines()
        
        if not channels:
            return "暂无频道数据", 404

        # 构建订阅内容
        sub_content = '#EXTM3U\n'
        for line in channels:
            if line.strip():  # 跳过空行
                name, url = line.strip().split(',')
                sub_content += f'#EXTINF:-1 tvg-name="{name}",{name}\n{url}\n'
        
        # 返回文本内容，设置正确的 Content-Type
        response = app.make_response(sub_content)
        response.headers['Content-Type'] = 'text/plain; charset=utf-8'
        return response
        
    except FileNotFoundError:
        return "频道列表文件未找到", 404
    except Exception as e:
        return f"生成订阅链接失败：{str(e)}", 500

# RTSP 鉴权状态查询
@app.route('/rtsp_status')
def rtsp_status():
    """返回 RTSP 鉴权的时效性分析"""
    sync_info = get_sync_info()
    if not sync_info:
        return jsonify({
            "status": "unknown",
            "message": "暂无同步数据，请先执行一次频道同步",
            "last_sync_time": None
        })

    now = datetime.now()
    last_sync_ts = sync_info.get("last_sync_timestamp", 0)
    elapsed_hours = (now.timestamp() - last_sync_ts) / 3600

    # 根据经验估算有效期状态
    # 重庆电信通常 AuthInfo 有效期为 6-24 小时
    if elapsed_hours < 6:
        status = "valid"
        message = f"RTSP 鉴权有效（已过 {elapsed_hours:.1f} 小时，通常在 6-24 小时内有效）"
    elif elapsed_hours < 12:
        status = "warning"
        message = f"RTSP 鉴权可能即将失效（已过 {elapsed_hours:.1f} 小时，建议重新同步）"
    elif elapsed_hours < 24:
        status = "expiring"
        message = f"RTSP 鉴权可能已失效（已过 {elapsed_hours:.1f} 小时，大部分情况下已过期）"
    else:
        status = "expired"
        message = f"RTSP 鉴权很可能已失效（已过 {elapsed_hours:.1f} 小时，请重新同步）"

    # 从 usersessionid 推断原始认证时间
    usersessionid = sync_info.get("usersessionid", "")
    session_hint = ""
    if usersessionid and usersessionid.isdigit():
        session_ts = int(usersessionid)
        # 判断是否是时间戳（如果数值合理）
        if session_ts > 1000000000:  # 是 unix 时间戳
            session_time = datetime.fromtimestamp(session_ts)
            session_hint = f"会话创建时间: {session_time.strftime('%Y-%m-%d %H:%M:%S')}"

    return jsonify({
        "status": status,
        "last_sync_time": sync_info.get("last_sync_time"),
        "elapsed_hours": round(elapsed_hours, 1),
        "udpxy_channel_count": sync_info.get("channel_count_udpxy", 0),
        "rtsp_channel_count": sync_info.get("channel_count_rtsp", 0),
        "usersessionid": usersessionid,
        "session_hint": session_hint,
        "message": message,
        "sync_schedule": "每天 16:00 自动同步"
    })

# 定义定时任务的逻辑
def job():
    with app.app_context():  # 确保在 Flask 应用上下文中运行
        get_channels()  # 调用 get_channels() 函数执行任务

# 启动调度器
def start_scheduler():
    scheduler = BackgroundScheduler()
    # 使用 Cron 表达式，每天的特定时间（例如，16:00）执行任务
    trigger = CronTrigger(hour=16, minute=0)  # 每天 16:00 执行
    scheduler.add_job(job, trigger)
    scheduler.start()

# 在应用启动时启动调度器
if __name__ == '__main__':
    start_scheduler()  # 启动调度器
    app.run(debug=True, host='0.0.0.0', port=5000)
