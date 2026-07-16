import os
import requests
from datetime import datetime, timedelta

# 从环境变量加载配置
WEATHER_KEY = os.environ.get('WEATHER_API_KEY')
CITY_CODE = os.environ.get('CITY_CODE')
FEISHU_WEBHOOK = os.environ.get('FEISHU_WEBHOOK')
DEEPSEEK_API_KEY = os.environ.get('DEEPSEEK_API_KEY')

def get_weather_data():
    """获取明日预报及小时级趋势数据"""
    url = f"https://restapi.amap.com/v3/weather/weatherInfo?key={WEATHER_KEY}&city={CITY_CODE}&extensions=all"
    resp = requests.get(url, timeout=15).json()
    
    # 获取明天数据 (casts[1])
    tomorrow = resp['forecasts'][0]['casts'][1]
    
    # 获取小时级预报 (高德接口返回的 hourly 列表)
    # 筛选出一天中的 6 个关键时间点，构建趋势矩阵
    hourly_raw = resp['forecasts'][0].get('hourly', [])
    # 如果接口返回 hourly 数据，取关键点；如果返回为空，则构建备用数据
    if hourly_raw:
        # 取 00, 04, 08, 12, 16, 20 时刻
        points = [h for h in hourly_raw if h['time'][-5:] in ["00:00", "04:00", "08:00", "12:00", "16:00", "20:00"]]
    else:
        # 兼容性降级处理
        points = []
        
    return tomorrow, points

def get_ai_advice(info):
    """DeepSeek 生成专业生活洞察"""
    prompt = f"明日天气：{info['dayweather']}，气温：{info['nighttemp']}°C~{info['daytemp']}°C。请作为气象专家，提供专业、简短（50字内）的穿衣及防护建议。"
    url = "https://api.deepseek.com/chat/completions"
    headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY.strip()}", "Content-Type": "application/json"}
    payload = {
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.5
    }
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=10).json()
        return resp['choices'][0]['message']['content']
    except:
        return "建议关注气温起伏，合理规划户外行程。"

def send_feishu_card(info, hourly_points, advice):
    """发送企业级 UI 布局卡片"""
    tomorrow_date = (datetime.now() + timedelta(days=1)).strftime('%m月%d日')
    
    # 构造趋势矩阵列
    columns = []
    for h in hourly_points:
        # 简单判定图标
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
                {"tag": "div", "text": {"tag": "lark_md", "content": "**🕰️ 24小时气温变化趋势**"}},
                {"tag": "column_set", "flex_mode": "none", "columns": columns},
                {"tag": "hr"},
                {"tag": "div", "text": {"tag": "lark_md", "content": f"**🤖 AI 深度智能洞察**\n<font color='blue'>{advice}</font>"}, "background_style": "grey"},
                {"tag": "note", "elements": [{"tag": "plain_text", "content": "由高德实时气象接口提供"}]}
            ]
        }
    }
    requests.post(FEISHU_WEBHOOK, json=card, timeout=10)

if __name__ == "__main__":
    try:
        tomorrow_info, hourly_data = get_weather_data()
        advice = get_ai_advice(tomorrow_info)
        send_feishu_card(tomorrow_info, hourly_data, advice)
    except Exception as e:
        print(f"运行出错: {e}")
