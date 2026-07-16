import os
import requests
from datetime import datetime, timedelta
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# 配置获取
WEATHER_KEY = os.environ.get('WEATHER_API_KEY')
CITY_CODE = os.environ.get('CITY_CODE')
FEISHU_WEBHOOK = os.environ.get('FEISHU_WEBHOOK')
DEEPSEEK_API_KEY = os.environ.get('DEEPSEEK_API_KEY')

def get_weather_data():
    """获取明日预报及小时级趋势数据，加入重试机制"""
    url = f"https://restapi.amap.com/v3/weather/weatherInfo?key={WEATHER_KEY}&city={CITY_CODE}&extensions=all"
    
    # 设置重试策略：遇到网络抖动自动重试 3 次
    session = requests.Session()
    retry_strategy = Retry(total=3, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("https://", adapter)
    
    try:
        # 超时时间延长至 30 秒
        resp = session.get(url, timeout=30).json()
        if resp.get('status') != '1':
            raise Exception(f"API错误: {resp.get('info')}")
            
        tomorrow = resp['forecasts'][0]['casts'][1]
        hourly_raw = resp['forecasts'][0].get('hourly', [])
        # 筛选关键时间点
        points = [h for h in hourly_raw if h['time'][-5:] in ["00:00", "04:00", "08:00", "12:00", "16:00", "20:00"]]
        return tomorrow, points
    except Exception as e:
        print(f"数据获取失败: {e}")
        raise e

def get_ai_advice(info):
    """DeepSeek 生成智能生活洞察"""
    prompt = f"明日天气：{info['dayweather']}，气温：{info['nighttemp']}°C~{info['daytemp']}°C。请以专业气象专家口吻，提供一条简短（50字内）的建议。"
    url = "https://api.deepseek.com/chat/completions"
    headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY.strip()}", "Content-Type": "application/json"}
    payload = {"model": "deepseek-chat", "messages": [{"role": "user", "content": prompt}], "temperature": 0.5}
    
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=30).json()
        return resp['choices'][0]['message']['content']
    except:
        return "建议关注气温起伏，合理规划户外行程。"

def send_feishu_card(info, hourly_points, advice):
    """发送企业级 UI 布局卡片"""
    tomorrow_date = (datetime.now() + timedelta(days=1)).strftime('%m月%d日')
    
    columns = []
    for h in hourly_points:
        icon = "☀️" if "晴" in h['weather'] else "☁️" if "云" in h['weather'] else "🌧️"
        columns.append({
            "tag": "column",
            "elements": [{"tag": "div", "text": {"tag": "lark_md", "content": f"{h['time'][-5:-3]}时\n**{h['temperature']}°C**\n{icon}"}}]
        })

    card = {
        "msg_type": "interactive",
        "card": {
            "header": {"template": "blue", "title": {"tag": "plain_text", "content": f"📅 {tomorrow_date} 气象趋势预报"}},
            "elements": [
                {"tag": "div", "text": {"tag": "lark_md", "content": f"**今日概况**：{info['dayweather']} | 气温：{info['nighttemp']}°C - {info['daytemp']}°C"}},
                {"tag": "hr"},
                {"tag": "div", "text": {"tag": "lark_md", "content": "**🕰️ 气温变化趋势**"}},
                {"tag": "column_set", "flex_mode": "none", "columns": columns},
                {"tag": "hr"},
                {"tag": "div", "text": {"tag": "lark_md", "content": f"**🤖 AI 深度智能洞察**\n<font color='blue'>{advice}</font>"}, "background_style": "grey"},
                {"tag": "note", "elements": [{"tag": "plain_text", "content": "实时高德气象数据 | 自动运行已启用"}]}
            ]
        }
    }
    requests.post(FEISHU_WEBHOOK, json=card, timeout=30)

if __name__ == "__main__":
    tomorrow_info, hourly_data = get_weather_data()
    advice = get_ai_advice(tomorrow_info)
    send_feishu_card(tomorrow_info, hourly_data, advice)
