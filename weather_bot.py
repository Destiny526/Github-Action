import os
import requests
from datetime import datetime, timedelta

# 配置获取
WEATHER_KEY = os.environ.get('WEATHER_API_KEY')
CITY_CODE = os.environ.get('CITY_CODE')
FEISHU_WEBHOOK = os.environ.get('FEISHU_WEBHOOK')
DEEPSEEK_API_KEY = os.environ.get('DEEPSEEK_API_KEY')

def get_weather_data():
    """获取高德全量天气数据"""
    url = f"https://restapi.amap.com/v3/weather/weatherInfo?key={WEATHER_KEY}&city={CITY_CODE}&extensions=all"
    resp = requests.get(url, timeout=30).json()
    
    if resp.get('status') != '1':
        raise Exception(f"高德API错误: {resp.get('info')}")
        
    forecast = resp['forecasts'][0]
    tomorrow = forecast['casts'][1]
    
    # 尝试提取小时级数据
    hourly_points = forecast.get('hourly', [])
    return tomorrow, hourly_points

def get_ai_advice(info):
    prompt = f"明日天气：{info['dayweather']}，气温：{info['nighttemp']}°C~{info['daytemp']}°C。请以专业气象员口吻，提供一条50字以内的避险建议。"
    url = "https://api.deepseek.com/chat/completions"
    headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY.strip()}", "Content-Type": "application/json"}
    payload = {"model": "deepseek-chat", "messages": [{"role": "user", "content": prompt}], "temperature": 0.5}
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=30).json()
        return resp['choices'][0]['message']['content']
    except:
        return "请密切关注天气变化，合理安排户外出行。"

def send_feishu_card(info, hourly_points, advice):
    tomorrow_date = (datetime.now() + timedelta(days=1)).strftime('%m月%d日')
    
    # 智能布局逻辑：如果有小时数据则展示，无则展示概况
    if hourly_points:
        # 每隔4小时取样，保证卡片整洁
        sampled_data = hourly_points[::4]
        columns = [{"tag": "column", "elements": [{"tag": "div", "text": {"tag": "lark_md", "content": f"{h['time'][-5:-3]}时\n**{h['temperature']}°C**\n☀️"}}]} for h in sampled_data]
    else:
        # 降级方案：早中晚分布
        columns = [
            {"tag": "column", "elements": [{"tag": "div", "text": {"tag": "lark_md", "content": f"☀️ 白天\n{info['daytemp']}°C\n{info['dayweather']}"}}]},
            {"tag": "column", "elements": [{"tag": "div", "text": {"tag": "lark_md", "content": f"🌙 夜间\n{info['nighttemp']}°C\n{info['nightweather']}"}}]}
        ]

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
                {"tag": "div", "text": {"tag": "lark_md", "content": f"**🤖 AI 深度智能洞察**\n<font color='blue'>{advice}</font>"}},
                {"tag": "note", "elements": [{"tag": "plain_text", "content": "实时高德气象数据 | 自动运行已启用"}]}
            ]
        }
    }
    requests.post(FEISHU_WEBHOOK, json=card, timeout=30)

if __name__ == "__main__":
    tomorrow_info, hourly_data = get_weather_data()
    advice = get_ai_advice(tomorrow_info)
    send_feishu_card(tomorrow_info, hourly_data, advice)
