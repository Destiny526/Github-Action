import os
import requests
from datetime import datetime, timedelta

# 配置获取
WEATHER_KEY = os.environ.get('WEATHER_API_KEY')
CITY_CODE = os.environ.get('CITY_CODE')
FEISHU_WEBHOOK = os.environ.get('FEISHU_WEBHOOK')
DEEPSEEK_API_KEY = os.environ.get('DEEPSEEK_API_KEY')

def get_weather_data():
    """获取明日预报详情"""
    # 强制请求全量数据以获取详细字段
    url = f"https://restapi.amap.com/v3/weather/weatherInfo?key={WEATHER_KEY}&city={CITY_CODE}&extensions=all"
    resp = requests.get(url, timeout=15).json()
    
    # 返回明天的数据 (casts[1])
    return resp['forecasts'][0]['casts'][1]

def get_ai_advice(info):
    """利用 DeepSeek 生成智能生活洞察"""
    prompt = f"""
    明日天气：{info['dayweather']}，气温：{info['nighttemp']}°C~{info['daytemp']}°C。
    请以专业气象服务专家口吻，生成一条建议。
    要求：
    1. 包含穿衣建议与避险提醒。
    2. 语气专业、冷静、客观。
    3. 50字以内。
    """
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
        return "请密切关注天气变化，合理安排户外出行计划。"

def send_feishu_card(info, advice):
    """发送企业级 UI 布局的交互式卡片"""
    tomorrow_date = (datetime.now() + timedelta(days=1)).strftime('%m月%d日')
    
    card = {
        "msg_type": "interactive",
        "card": {
            "header": {"template": "blue", "title": {"tag": "plain_text", "content": f"📅 {tomorrow_date} 气象预报中心"}},
            "elements": [
                # 矩阵看板：企业级数据对齐
                {
                    "tag": "div",
                    "fields": [
                        {"is_short": True, "text": {"tag": "lark_md", "content": f"**天气状况**\n{info['dayweather']}"}},
                        {"is_short": True, "text": {"tag": "lark_md", "content": f"**温度区间**\n{info['nighttemp']}°C - {info['daytemp']}°C"}},
                        {"is_short": True, "text": {"tag": "lark_md", "content": f"**白天风向**\n{info['daywind']}风"}},
                        {"is_short": True, "text": {"tag": "lark_md", "content": f"**最大风力**\n{info['daypower']} 级"}}
                    ]
                },
                {"tag": "hr"},
                # 双列对比视图
                {
                    "tag": "column_set",
                    "flex_mode": "bisect",
                    "columns": [
                        {"tag": "column", "elements": [{"tag": "div", "text": {"tag": "lark_md", "content": f"☀️ **白日气象**\n{info['dayweather']}"}}]},
                        {"tag": "column", "elements": [{"tag": "div", "text": {"tag": "lark_md", "content": f"🌙 **夜间气象**\n{info['nightweather']}"}}]}
                    ]
                },
                {"tag": "hr"},
                # 智能洞察区
                {
                    "tag": "div",
                    "text": {"tag": "lark_md", "content": f"**🤖 AI 深度智能洞察**\n<font color='blue'>{advice}</font>"}
                },
                # 系统页脚
                {
                    "tag": "note",
                    "elements": [{"tag": "plain_text", "content": "实时高德气象数据接口 | 系统自动监测运行"}]
                }
            ]
        }
    }
    requests.post(FEISHU_WEBHOOK, json=card, timeout=10)

if __name__ == "__main__":
    try:
        tomorrow_info = get_weather_data()
        advice = get_ai_advice(tomorrow_info)
        send_feishu_card(tomorrow_info, advice)
    except Exception as e:
        print(f"执行异常: {e}")
