from flask import Flask, send_from_directory, request, render_template, jsonify, flash, redirect, url_for, Response
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from main import get_channels, index, save_config  # 从 main.py 导入所需函数
import requests

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
            logs = f.read()
        return logs
    except Exception as e:
        return f"获取频道列表失败：{str(e)}"

@app.route('/refresh_logs')
def refresh_logs_content():
    try:
        with open('static/relogs.txt', 'r', encoding='utf-8') as f:
            logs = f.read()
        return logs
    except Exception as e:
        return f"获取日志失败：{str(e)}"

# 订阅链接生成
@app.route('/sub')
def get_sub():
    try:
        with open('static/channels.txt', 'r', encoding='utf-8') as f:
            channels = f.readlines()
        
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
