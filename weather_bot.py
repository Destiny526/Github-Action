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
        raise Exception(f"API请求失败: {resp.get('info')}")
    
    forecast = resp['forecasts'][0]
    tomorrow = forecast['casts'][1]
    hourly = forecast.get('hourly', [])
    return tomorrow, hourly

def get_ai_advice(info):
    """DeepSeek 生成智能建议"""
    prompt = f"明天{info['dayweather']}，气温{info['nighttemp']}°C~{info['daytemp']}°C。请提供一条专业的穿衣及活动建议（50字内）。"
    headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY.strip()}", "Content-Type": "application/json"}
    payload = {"model": "deepseek-chat", "messages": [{"role": "user", "content": prompt}]}
    try:
        resp = requests.post("https://api.deepseek.com/chat/completions", json=payload, headers=headers, timeout=30).json()
        return resp['choices'][0]['message']['content']
    except:
        return "气温波动，建议关注天气预报，合理规划行程。"

def send_feishu_card(info, hourly, advice):
    tomorrow_date = (datetime.now() + timedelta(days=1)).strftime('%m月%d日')
    header_template = "red" if int(info['daytemp']) > 30 else "blue"
    
    # 构造动态内容逻辑：有小时数据则热力监测，无则日夜对比
    if hourly:
        elements = [{"tag": "div", "text": {"tag": "lark_md", "content": "**🌡️ 气温时序热力监测**"}}]
        for h in hourly[::6]:
            temp = int(h['temperature'])
            elements.append({
                "tag": "div",
                "text": {"tag": "lark_md", "content": f"{h['time'][-5:-3]}时: **{temp}°C**"},
                "extra": {"tag": "progress", "percent": min(max(temp * 2, 0), 100)}
            })
    else:
        elements = [
            {"tag": "div", "text": {"tag": "lark_md", "content": "**🌡️ 气温监测（无时序数据）**"}},
            {
                "tag": "column_set",
                "columns": [
                    {"tag": "column", "elements": [{"tag": "div", "text": {"tag": "lark_md", "content": f"☀️ 白天最高\n**{info['daytemp']}°C**"}}]},
                    {"tag": "column", "elements": [{"tag": "div", "text": {"tag": "lark_md", "content": f"🌙 夜间最低\n**{info['nighttemp']}°C**"}}]}
                ]
            }
        ]
    
    card = {
        "msg_type": "interactive",
        "card": {
            "header": {"template": header_template, "title": {"tag": "plain_text", "content": f"🌤️ {tomorrow_date} 天气监测看板"}},
            "elements": [
                {
                    "tag": "div",
                    "fields": [
                        {"is_short": True, "text": {"tag": "lark_md", "content": f"**最高温度**\n{info['daytemp']}°C"}},
                        {"is_short": True, "text": {"tag": "lark_md", "content": f"**最低温度**\n{info['nighttemp']}°C"}},
                        {"is_short": True, "text": {"tag": "lark_md", "content": f"**天气状况**\n{info['dayweather']}"}},
                        {"is_short": True, "text": {"tag": "lark_md", "content": f"**风向/等级**\n{info['daywind']}/{info['daypower']}级"}}
                    ]
                },
                {"tag": "hr"},
                *elements,
                {"tag": "hr"},
                {"tag": "div", "text": {"tag": "lark_md", "content": f"**🤖 AI 深度分析**\n<font color='blue'>{advice}</font>"}},
                {
                    "tag": "action",
                    "actions": [{
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "查看权威气象详情"},
                        "type": "primary",
                        "url": "https://weather.cma.cn/"
                    }]
                }
            ]
        }
    }
    requests.post(FEISHU_WEBHOOK, json=card, timeout=30)

if __name__ == "__main__":
    info, hourly = get_weather_data()
    advice = get_ai_advice(info)
    send_feishu_card(info, hourly, advice)
