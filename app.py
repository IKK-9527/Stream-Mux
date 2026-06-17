from flask import Flask, send_from_directory, request, render_template, jsonify, flash, redirect, url_for, Response
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from main import get_channels, index, save_config, get_sync_info, get_epg  # 从 main.py 导入所需函数
import requests
import json
import re
import random
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

# 后台同步频道列表（AJAX 调用）
@app.route('/api/sync_channels')
def api_sync_channels():
    try:
        result = get_channels()  # 执行频道同步
        sync_info = get_sync_info()
        channel_count = sync_info.get('channel_count_udpxy', 0) if sync_info else 0
        return jsonify({
            'success': True,
            'message': f'获取到 {channel_count} 个频道'
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

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

        # 判断是否为 RTSP 频道（需要添加 APTV 回看支持）
        is_rtsp = 'rtsp' in channel_file

        # 构建订阅内容
        sub_content = '#EXTM3U\n'
        for line in channels:
            if line.strip():  # 跳过空行
                parts = line.strip().split(',', 2)
                name = parts[0]
                # 从 URL 中提取 programid 作为 tvg-id（用于 EPG 精确匹配）
                first_url = parts[1] if len(parts) > 1 else ''
                tvg_id = ''
                id_match = re.search(r'[?&](?:programid|channelId)=([^&]+)', first_url)
                if id_match:
                    tvg_id = id_match.group(1)

                if is_rtsp and len(parts) == 3:
                    # 三字段：频道名,带变量的URL（catchup-source）,原始URL（实际播放）
                    catchup_url = parts[1]
                    play_url = parts[2]
                    sub_content += f'#EXTINF:-1 tvg-id="{tvg_id}" tvg-name="{name}" tvg-logo="" group-title="" catchup="default" catchup-source="{catchup_url}",{name}\n'
                    sub_content += f'{play_url}\n'
                else:
                    # 两字段：频道名,URL（UDPXY版本）
                    url = parts[1]
                    sub_content += f'#EXTINF:-1 tvg-id="{tvg_id}" tvg-name="{name}" tvg-logo="" group-title="",{name}\n'
                    sub_content += f'{url}\n'

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
        "sync_schedule": "每天 13:00~17:00 间随机时间自动同步"
    })

# EPG - 轻量级统计（不加载完整节目列表，快速返回总数）
@app.route('/api/epg/stats')
def api_epg_stats():
    try:
        # 直接从 JSON 文件头部读取 streams数，避免全量解析
        with open('static/epg_cache.json', 'r', encoding='utf-8') as f:
            # 只解析顶层字段
            header = json.load(f)
            programs = header.get('programs', [])
            return jsonify({
                'total': len(programs),
                'cache_time': header.get('cache_time', 0),
                'days': header.get('days', 0)
            })
    except Exception:
        # 降级：用完整函数
        programs = get_epg()
        return jsonify({'total': len(programs)})

# EPG 节目单 - XMLTV 格式（兼容 APTV/Tvheadend 等）
@app.route('/epg.xml')
def epg_xml():
    refresh = request.args.get('refresh', '').lower() in ('true', '1')
    days = request.args.get('days', 7, type=int)
    try:
        get_epg(refresh=refresh, days=days)  # 确保数据已生成
        with open('static/epg.xml', 'r', encoding='utf-8') as f:
            xml_data = f.read()
        return Response(xml_data, mimetype='application/xml; charset=utf-8')
    except FileNotFoundError:
        return "EPG 数据尚未生成，请先访问 /refresh_epg", 404

# EPG 节目单 - JSON 格式（前端使用）
@app.route('/api/epg')
def api_epg():
    refresh = request.args.get('refresh', '').lower() in ('true', '1')
    days = request.args.get('days', 7, type=int)
    programs = get_epg(refresh=refresh, days=days)
    return jsonify({
        'total': len(programs),
        'programs': programs
    })

# EPG - 获取可用日期列表
@app.route('/api/epg/dates')
def api_epg_dates():
    programs = get_epg()
    dates = sorted(set(p['start'][:8] for p in programs))
    return jsonify({'dates': dates})

# EPG - 获取有 EPG 数据的频道及其节目数
@app.route('/api/epg/channels')
def api_epg_channels():
    programs = get_epg()
    from collections import Counter
    channel_counts = Counter(p['channel_name'] for p in programs)
    channels = [{'name': name, 'count': count} for name, count in channel_counts.items()]
    channels.sort(key=lambda x: -x['count'])
    return jsonify({'channels': channels, 'total': len(channels)})

# EPG - 分页查询节目（按日期+频道筛选）
@app.route('/api/epg/programs')
def api_epg_programs():
    date = request.args.get('date', '')
    channel_id = request.args.get('channel_id', '')
    channel_name = request.args.get('channel_name', '')
    offset = request.args.get('offset', 0, type=int)
    limit = request.args.get('limit', 50, type=int)

    programs = get_epg()
    # 筛选
    if date:
        programs = [p for p in programs if p['start'].startswith(date)]
    if channel_id:
        programs = [p for p in programs if p['channel_id'] == channel_id]
    if channel_name:
        programs = [p for p in programs if p['channel_name'] == channel_name]

    total = len(programs)
    # 分页
    page = programs[offset:offset + limit]
    return jsonify({
        'total': total,
        'offset': offset,
        'limit': limit,
        'programs': page
    })

# 手动刷新 EPG
@app.route('/refresh_epg')
def refresh_epg():
    try:
        programs = get_epg(refresh=True)
        return jsonify({
            'success': True,
            'message': f'EPG 更新完成，获取到 {len(programs)} 个节目',
            'total': len(programs)
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

# EPG 初始化（抓取前面 7 天数据：过去 6 天 + 今天）
@app.route('/init_epg')
def init_epg():
    try:
        days = request.args.get('days', 7, type=int)
        programs = get_epg(refresh=True, days=days)
        return jsonify({
            'success': True,
            'message': f'EPG 初始化完成，获取到 {len(programs)} 个节目（天数: {days}）',
            'total': len(programs)
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

# 定义定时任务的逻辑
def job():
    with app.app_context():  # 确保在 Flask 应用上下文中运行
        get_channels()  # 同步频道列表
        get_epg(refresh=True)  # 同步 EPG 节目数据

# 启动调度器（每天随机时间 13:00~16:59 执行）
def start_scheduler():
    scheduler = BackgroundScheduler()
    rand_hour = random.randint(13, 16)
    rand_min = random.randint(0, 59)
    trigger = CronTrigger(hour=rand_hour, minute=rand_min)
    scheduler.add_job(job, trigger)
    print(f"定时任务已启动: 每天 {rand_hour:02d}:{rand_min:02d} 自动同步")
    scheduler.start()

# 在应用启动时启动调度器
if __name__ == '__main__':
    start_scheduler()  # 启动调度器
    app.run(debug=False, host='0.0.0.0', port=8899)
