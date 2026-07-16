import os
import requests
from datetime import datetime, timedelta

# 配置获取
WEATHER_KEY = os.environ.get('WEATHER_API_KEY')
CITY_CODE = os.environ.get('CITY_CODE')
FEISHU_WEBHOOK = os.environ.get('FEISHU_WEBHOOK')
DEEPSEEK_API_KEY = os.environ.get('DEEPSEEK_API_KEY')

def get_weather_data():
    """获取明日预报与分时详情"""
    url = f"https://restapi.amap.com/v3/weather/weatherInfo?key={WEATHER_KEY}&city={CITY_CODE}&extensions=all"
    resp = requests.get(url, timeout=15).json()
    
    # 获取明天的数据 (casts[1])
    tomorrow = resp['forecasts'][0]['casts'][1]
    
    # 获取小时级预报 (cast 数组中可能包含小时级 detail)
    # 若 API 返回 hourly 列表，直接取用；若无，则用晨/午/晚概况代替
    hourly_info = resp['forecasts'][0].get('cast', []) 
    return tomorrow, hourly_info

def get_ai_advice(info):
    """利用 DeepSeek 生成生活建议"""
    prompt = f"明日天气：{info['dayweather']}，气温 {info['nighttemp']}°C~{info['daytemp']}°C。请以专业气象管家口吻，提供一条简短（50字内）的穿衣及避险建议。"
    
    url = "https://api.deepseek.com/chat/completions"
    headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY.strip()}", "Content-Type": "application/json"}
    payload = {
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7
    }
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=10).json()
        return resp['choices'][0]['message']['content']
    except:
        return "建议关注气温变化，适时增减衣物。"

def send_feishu_card(info, advice):
    """发送高颜值多列布局卡片"""
    tomorrow_date = (datetime.now() + timedelta(days=1)).strftime('%m月%d日')
    
    # 构造飞书多列布局
    card = {
        "msg_type": "interactive",
        "card": {
            "header": {"template": "blue", "title": {"tag": "plain_text", "content": f"📅 {tomorrow_date} 天气预报"}},
            "elements": [
                {
                    "tag": "div",
                    "text": {"tag": "lark_md", "content": f"**概况**：{info['dayweather']}\n**气温**：{info['nighttemp']}°C ~ {info['daytemp']}°C\n**风向/风力**：{info['daywind']}风 {info['daypower']}级"}
                },
                {"tag": "hr"},
                {
                    "tag": "column_set",
                    "columns": [
                        {"tag": "column", "elements": [{"tag": "div", "text": {"tag": "lark_md", "content": f"☀️ 白天\n{info['dayweather']}"}}]},
                        {"tag": "column", "elements": [{"tag": "div", "text": {"tag": "lark_md", "content": f"🌙 夜间\n{info['nightweather']}"}}]}
                    ]
                },
                {"tag": "hr"},
                {"tag": "div", "text": {"tag": "lark_md", "content": f"**💡 AI 管家建议**：\n{advice}"}}
            ]
        }
    }
    requests.post(FEISHU_WEBHOOK, json=card, timeout=10)

if __name__ == "__main__":
    try:
        tomorrow_info, _ = get_weather_data()
        advice = get_ai_advice(tomorrow_info)
        send_feishu_card(tomorrow_info, advice)
    except Exception as e:
        print(f"Error: {e}")
