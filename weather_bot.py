import os
import requests
from datetime import datetime

# 环境变量获取
WEATHER_API_KEY = os.environ.get('WEATHER_API_KEY')
CITY_CODE = os.environ.get('CITY_CODE') # 城市的代码，比如北京是110000
FEISHU_WEBHOOK = os.environ.get('FEISHU_WEBHOOK')

def get_weather():
    # 这里调用天气 API，例如和风天气
    url = f"https://devapi.qweather.com/v7/weather/3d?location={CITY_CODE}&key={WEATHER_API_KEY}"
    response = requests.get(url).json()
    return response['daily'][1] # 返回明天的天气

def analyze_weather(weather_data):
    temp_min = int(weather_data['tempMin'])
    temp_max = int(weather_data['tempMax'])
    text = weather_data['textDay']
    
    warnings = []
    advice = ""
    
    # 极端天气逻辑
    if "雨" in text or "雪" in text:
        warnings.append("🌧️ 极端天气预警：明天有降水")
        advice = "记得带伞，防滑防潮。"
    if (temp_max - temp_min) > 12:
        warnings.append("🌡️ 温差预警：明天昼夜温差大")
        advice = "采取洋葱式穿衣法，防止感冒。"
        
    return warnings, advice

def send_to_feishu(weather_data, warnings, advice):
    # 构造飞书交互式卡片
    # ... (类似之前的卡片逻辑)
    pass
