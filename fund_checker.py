import os
import re
import json
import requests
from typing import List, Dict, Any, Optional

# 要监控的基金代码列表（可以换成你关注的基金）
WATCH_LIST: List[str] = ["001186", "161725"] 

def get_fund_data(fund_code: str) -> Optional[Dict[str, Any]]:
    """
    获取单只基金的当日估值情况
    """
    # 天天基金的即时估值 API
    url: str = f"http://fundgz.1234567.com.cn/js/{fund_code}.js"
    try:
        response: requests.Response = requests.get(url, timeout=10)
        if response.status_code == 200:
            # API 返回的是 jsonpgz({...}); 需要提取出 json 字符串
            match = re.match(r"jsonpgz\((.*)\);", response.text)
            if match:
                json_str: str = match.group(1)
                data: Dict[str, Any] = json.loads(json_str)
                return data
    except Exception as e:
        print(f"获取基金 {fund_code} 失败: {e}")
    return None

def judge_fund(fund_data: Dict[str, Any]) -> bool:
    """
    判断基金是否值得入手（示例逻辑：当日估值跌幅超过 1.5% 视为值得关注）
    你可以根据需要修改这里的量化策略
    """
    try:
        # gszzl 为估值涨跌幅，字符串类型，如 "-1.85"
        gszzl: float = float(fund_data.get("gszzl", 0))
        if gszzl <= -1.5:
            return True
    except ValueError:
        pass
    return False

def send_notification(webhook_url: str, content: str) -> None:
    """
    通过 Webhook 发送通知（此处以企业微信/飞书/钉钉通用的文本格式为例）
    """
    headers: Dict[str, str] = {"Content-Type": "application/json"}
    payload: Dict[str, Any] = {
        "msgtype": "text",
        "text": {
            "content": content
        }
    }
    try:
        res: requests.Response = requests.post(webhook_url, json=payload, headers=headers, timeout=10)
        print(f"通知发送状态: {res.status_code}")
    except Exception as e:
        print(f"发送通知失败: {e}")

def main() -> None:
    # 从环境变量中读取 Webhook URL
    webhook_url: Optional[str] = os.getenv("WEBHOOK_URL")
    if not webhook_url:
        print("未配置 WEBHOOK_URL 环境变量，脚本退出。")
        return

    triggered_funds: List[str] = []

    for code in WATCH_LIST:
        data: Optional[Dict[str, Any]] = get_fund_data(code)
        if data:
            name: str = data.get("name", "未知基金")
            gsz: str = data.get("gsz", "0")       # 当前估值
            gszzl: str = data.get("gszzl", "0")   # 估值涨跌幅
            gztime: str = data.get("gztime", "")  # 估值时间
            
            print(f"检查基金: {name}({code}) | 涨跌幅: {gszzl}% | 时间: {gztime}")
            
            if judge_fund(data):
                triggered_funds.append(f"【值得入手】{name}({code})\n当前估值: {gsz}\n当日跌幅: {gszzl}%\n---")

    if triggered_funds:
        message: str = "🚨 基金购买提醒 🚨\n\n" + "\n".join(triggered_funds)
        send_notification(webhook_url, message)
    else:
        print("今日无满足条件的基金，不发送提醒。")

if __name__ == "__main__":
    main()
