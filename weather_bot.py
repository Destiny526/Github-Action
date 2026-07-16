import os
import requests
from datetime import datetime, timedelta

# 从环境变量获取配置
WEATHER_KEY = os.environ.get('WEATHER_API_KEY')
CITY_CODE = os.environ.get('CITY_CODE') 
FEISHU_WEBHOOK = os.environ.get('FEISHU_WEBHOOK')
DEEPSEEK_API_KEY = os.environ.get('DEEPSEEK_API_KEY')

def get_weather():
    """获取明日天气数据"""
    # 高德天气 API 接口 (extensions=all 获取全量数据)
    url = f"https://restapi.amap.com/v3/weather/weatherInfo?key={WEATHER_KEY}&city={CITY_CODE}&extensions=all"
    resp = requests.get(url, timeout=10).json()
    # forecasts[0]['casts'][1] 代表第二天（即明天）的预报
    return resp['forecasts'][0]['casts'][1]

def get_advice_by_ai(weather_info):
    """调用 DeepSeek AI 生成天气建议"""
    prompt = f"""
    明天天气状况：{weather_info['dayweather']}，
    气温：{weather_info['nighttemp']}°C 到 {weather_info['daytemp']}°C。
    请作为一名贴心的生活助手，为用户提供一条简短的、充满关怀的天气建议。
    要求：
    1. 包含穿衣、出行或防范建议。
    2. 如果有极端天气（雨雪、高温、大温差），语气要严肃并给出具体避险方案。
    3. 语言温暖自然，50字以内。
    """
    
    url = "https://api.deepseek.com/chat/completions"
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY.strip()}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7
    }
    
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=15)
        if response.status_code == 200:
            return response.json()['choices'][0]['message']['content']
        else:
            return "🌤️ 天气不错，记得保持好心情！"
    except Exception as e:
        print(f"AI 调用失败: {e}")
        return "🌤️ 天气不错，记得保持好心情！"

def send_feishu(info, advice):
    """通过飞书发送交互式卡片"""
    tomorrow = (datetime.now() + timedelta(days=1)).strftime('%m月%d日')
    card = {
        "msg_type": "interactive",
        "card": {
            "header": {"title": {"tag": "plain_text", "content": f"📅 {tomorrow} 天气助手"}},
            "elements": [
                {
                    "tag": "div", 
                    "text": {"tag": "lark_md", "content": f"**天气状况**：{info['dayweather']}\n**气温**：{info['nighttemp']}°C ~ {info['daytemp']}°C"}
                },
                {"tag": "hr"},
                {"tag": "div", "text": {"tag": "lark_md", "content": f"**管家建议**：\n{advice}"}}
            ]
        }
    }
    requests.post(FEISHU_WEBHOOK, json=card, timeout=10)

if __name__ == "__main__":
    try:
        w_data = get_weather()
        ai_advice = get_advice_by_ai(w_data)
        send_feishu(w_data, ai_advice)
    except Exception as e:
        print(f"执行异常: {e}")
