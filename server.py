#!/usr/bin/env python3
"""统一服务器 - 静态文件 + 基金API代理"""
import json
import re
import time
import os
from datetime import datetime
import requests
from flask import Flask, request, jsonify, send_from_directory, make_response

app = Flask(__name__)

# 缓存
cache = {}
CACHE_TTL = 300

def get_cache(key):
    if key in cache:
        ts, val = cache[key]
        if time.time() - ts < CACHE_TTL:
            return val
    return None

def set_cache(key, val):
    cache[key] = (time.time(), val)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Referer': 'https://fund.eastmoney.com/'
}

def fetch_fund_detail(code):
    cached = get_cache(f'fund_{code}')
    if cached:
        return cached
    result = {'code': code, 'name': '', 'nav': 0, 'nav_date': '', 'estimate_nav': 0, 'estimate_pct': 0, 'estimate_time': ''}
    try:
        url = f'https://fund.eastmoney.com/pingzhongdata/{code}.js'
        r = requests.get(url, headers=HEADERS, timeout=8)
        if r.status_code == 200:
            text = r.text
            m_name = re.search(r'fS_name\s*=\s*"([^"]+)"', text)
            if m_name:
                result['name'] = m_name.group(1)
            m_trend = re.search(r'Data_netWorthTrend\s*=\s*(\[.*?\])', text)
            if m_trend:
                trend_data = json.loads(m_trend.group(1))
                if trend_data:
                    latest = trend_data[-1]
                    prev = trend_data[-2] if len(trend_data) >= 2 else latest
                    result['nav'] = float(latest.get('y', 0))
                    result['estimate_nav'] = result['nav']
                    ts = latest.get('x', 0)
                    if ts:
                        result['nav_date'] = datetime.fromtimestamp(ts/1000).strftime('%Y-%m-%d')
                    prev_nav = float(prev.get('y', 0))
                    if prev_nav > 0:
                        result['estimate_pct'] = round((result['nav'] - prev_nav) / prev_nav * 100, 2)
    except Exception as e:
        print(f'fund detail error: {e}')
    set_cache(f'fund_{code}', result)
    return result

@app.route('/api/fund/realtime')
def fund_realtime():
    codes = request.args.get('codes', '')
    if not codes:
        return jsonify({'error': 'no codes'}), 400
    code_list = [c.strip() for c in codes.split(',') if c.strip()]
    results = [fetch_fund_detail(c) for c in code_list]
    return jsonify({'funds': results, 'time': datetime.now().strftime('%H:%M:%S')})

@app.route('/api/fund/news')
def fund_news():
    cached = get_cache('fund_news')
    if cached:
        return jsonify(cached)
    news_list = []
    try:
        r = requests.get('https://fund.eastmoney.com/a/cjjyw.html', headers=HEADERS, timeout=10)
        r.encoding = 'gbk'
        html = r.text
        pattern = r'(\d{4}-\d{2}-\d{2}\s*\d{2}:\d{2}).*?<a[^>]*href="([^"]*)"[^>]*>(.*?)</a>'
        matches = re.findall(pattern, html, re.DOTALL)
        seen = set()
        for date_str, url, title in matches:
            title = re.sub(r'<[^>]+>', '', title).strip()
            title = title.replace('&nbsp;', ' ').replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
            if title and len(title) > 8 and title not in seen:
                seen.add(title)
                full_url = url if url.startswith('http') else ('https://fund.eastmoney.com/a/' + url)
                news_list.append({'title': title, 'url': full_url, 'time': date_str.strip()})
    except Exception as e:
        print(f'news error: {e}')
    if not news_list:
        news_list = [{'title': '正在获取最新资讯...', 'url': '#', 'time': '--'}]
    result = {'news': news_list[:15], 'time': datetime.now().strftime('%H:%M:%S')}
    set_cache('fund_news', result)
    return jsonify(result)

@app.route('/api/fund/hotsectors')
def hot_sectors():
    cached = get_cache('hot_sectors')
    if cached:
        return jsonify(cached)
    sectors = []
    try:
        url = 'https://fund.eastmoney.com/Data/Fund_JJJZ_Data.aspx?t=1&lx=1&letter=&gsid=&text=&sort=zdf,desc&page=1,60&dt=' + str(int(time.time() * 1000))
        r = requests.get(url, headers=HEADERS, timeout=10)
        text = r.text
        # 提取 var db={...}; 使用括号匹配
        idx = text.index('var db=')
        start = idx + 7
        depth = 0
        end = start
        for i in range(start, len(text)):
            if text[i] == '{': depth += 1
            elif text[i] == '}':
                depth -= 1
                if depth == 0: end = i + 1; break
        content = text[start:end]
        # 修复 JS 对象为合法 JSON
        content = re.sub(r'(?<=[\{,])\s*([a-zA-Z_]\w*)\s*:', r'"\1":', content)
        content = re.sub(r',\s*([}\]])', r'\1', content)
        data = json.loads(content)
        if data.get('datas'):
            sector_map = {
                '白酒': '🍶 白酒', '酒': '🍶 白酒', '食品饮料': '🍶 白酒',
                '新能源': '⚡ 新能源', '光伏': '⚡ 新能源', '锂电': '⚡ 新能源', '电池': '⚡ 新能源',
                '医药': '💊 医药', '医疗': '💊 医药', '生物医药': '💊 医药', '中药': '💊 医药',
                '半导体': '💻 半导体', '芯片': '💻 半导体', '电子': '💻 半导体',
                '消费': '🛒 消费', '农业': '🛒 消费',
                '金融': '🏦 金融', '银行': '🏦 金融', '证券': '🏦 金融', '保险': '🏦 金融',
                '人工智能': '🤖 AI科技', 'AI': '🤖 AI科技', '科技': '🤖 AI科技', '计算机': '🤖 AI科技', '大数据': '🤖 AI科技',
                '汽车': '🚗 汽车', '新能源车': '🚗 汽车',
                '军工': '🛡️ 军工', '国防': '🛡️ 军工',
                '通信': '📡 通信', '5G': '📡 通信',
                '传媒': '🎬 传媒', '游戏': '🎬 传媒', '动漫': '🎬 传媒',
                '化工': '⚗️ 化工', '有色': '⛏️ 资源', '煤炭': '⛏️ 资源', '钢铁': '⛏️ 资源',
                '地产': '🏗️ 地产基建', '基建': '🏗️ 地产基建', '建材': '🏗️ 地产基建',
            }
            sector_agg = {}
            for item in data.get('datas', []):
                if len(item) >= 11:
                    name = item[1]
                    pct = float(item[8]) if item[8] else 0
                    matched = None
                    for kw, sec_name in sector_map.items():
                        if kw in name:
                            matched = sec_name
                            break
                    if not matched:
                        matched = '📊 其他'
                    if matched not in sector_agg:
                        sector_agg[matched] = {'total_pct': 0, 'count': 0, 'top_fund': name}
                    sector_agg[matched]['total_pct'] += pct
                    sector_agg[matched]['count'] += 1
            for sec_name, val in sector_agg.items():
                avg_pct = round(val['total_pct'] / val['count'], 2)
                sectors.append({'name': sec_name, 'pct': avg_pct, 'count': val['count'], 'desc': f'代表基金：{val["top_fund"][:12]}'})
            sectors.sort(key=lambda x: x['pct'], reverse=True)
            sectors = sectors[:10]
    except Exception as e:
        print(f'sectors error: {e}')
    if not sectors:
        sectors = [{'name': '数据加载中...', 'pct': 0, 'count': 0, 'desc': ''}]
    result = {'sectors': sectors, 'time': datetime.now().strftime('%H:%M:%S')}
    set_cache('hot_sectors', result)
    return jsonify(result)

@app.route('/health')
def health():
    return jsonify({'status': 'ok'})

# 静态文件服务
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

@app.route('/')
def index():
    return send_from_directory(BASE_DIR, 'index.html')

@app.route('/<path:filename>')
def static_files(filename):
    if filename.endswith('.mobileconfig'):
        return send_from_directory(BASE_DIR, filename, mimetype='application/x-apple-aspen-config')
    return send_from_directory(BASE_DIR, filename)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000, debug=False)
