from flask import Flask, send_from_directory
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from main import get_channels  # 确保从 main.py 中导入 get_channels 函数

app = Flask(__name__)

# 提供 channels.txt 文件
@app.route('/')
def get_channelsx():
    try:
        return send_from_directory('static', 'channels.txt')  # 确保文件路径正确
    except FileNotFoundError:
        return "channels.txt 文件未找到", 404

# 提供 relogs.txt 文件
@app.route('/log')
def get_logs():
    try:
        return send_from_directory('static', 'relogs.txt')  # 确保文件路径正确
    except FileNotFoundError:
        return "relogs.txt 文件未找到", 404

@app.route('/sync')
def sync():
    return get_channels()

# 定义定时任务的逻辑
def job():
    with app.app_context():  # 确保在 Flask 应用上下文中运行
        print("Running scheduled task...")
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