import os
import re
import json
import requests
from typing import List, Dict, Any, Optional

# ================= 配置区域 =================
WATCH_LIST: List[str] = ["001186", "161725"] 
TEST_MODE: bool = False  # 如果想测试卡片效果，可以先改成 True
# ============================================

def get_fund_data(fund_code: str) -> Optional[Dict[str, Any]]:
    """
    从天天基金官方数据源获取单只基金的即时盘中数据
    """
    url: str = f"http://fundgz.1234567.com.cn/js/{fund_code}.js"
    try:
        response: requests.Response = requests.get(url, timeout=10)
        if response.status_code == 200:
            match = re.match(r"jsonpgz\((.*)\);", response.text)
            if match:
                return json.loads(match.group(1))
    except Exception as e:
        print(f"[-] 获取基金 {fund_code} 失败: {e}")
    return None

def judge_fund(fund_data: Dict[str, Any]) -> bool:
    """
    策略判定：盘中估值跌幅是否达到定投标准
    """
    if TEST_MODE:
        return True
    try:
        growth_rate: float = float(fund_data.get("gszzl", 0))
        if growth_rate <= -1.5:  # 跌幅超过 1.5% 触发
            return True
    except ValueError:
        pass
    return False

def build_feishu_card(fund_list: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    构建飞书高级互动卡片数据结构
    """
    elements: List[Dict[str, Any]] = []
    
    for fund in fund_list:
        name: str = fund.get("name", "未知基金")
        code: str = fund.get("fundcode", "000000")
        price: str = fund.get("gsz", "0.0000")
        growth: str = fund.get("gszzl", "0.00")
        time: str = fund.get("gztime", "未知时间")
        
        # 判断涨跌颜色（国内股市：绿跌红涨）
        is_drop: bool = float(growth) < 0
        color_tag: str = "🟢" if is_drop else "🔴"
        text_color: str = "green" if is_drop else "red"
        
        # 组装飞书卡片的内容区块
        elements.append({
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": f"{color_tag} **{name}** ({code})\n• **盘中估净值**: {price}\n• **当日涨跌幅**: <font color='{text_color}'>**{growth}%**</font>\n• **数据更新时间**: {time}"
            }
        })
        elements.append({"tag": "hr"}) # 分割线
        
    if elements:
        elements.pop() # 移除最后一个多余的分割线

    # 飞书卡片标准 JSON 协议
    return {
        "msg_type": "interactive",
        "card": {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": "🤖 基金定投策略监控日报" if not TEST_MODE else "🧪 飞书高级卡片测试成功"
                },
                "template": "turquoise" if not TEST_MODE else "blue"
            },
            "elements": elements
        }
    }

def send_to_feishu(webhook_url: str, card_payload: Dict[str, Any]) -> None:
    """
    将卡片消息推送到飞书网关
    """
    headers: Dict[str, str] = {"Content-Type": "application/json"}
    try:
        res: requests.Response = requests.post(webhook_url, json=card_payload, headers=headers, timeout=10)
        print(f"[+] 飞书卡片推送状态: {res.status_code}, 响应: {res.text}")
    except Exception as e:
        print(f"[-] 推送异常: {e}")

def main() -> None:
    webhook_url: Optional[str] = os.getenv("WEBHOOK_URL")
    if not webhook_url:
        print("[-] 未检测到 WEBHOOK_URL 环境变量。")
        return

    triggered_funds: List[Dict[str, Any]] = []

    for code in WATCH_LIST:
        data: Optional[Dict[str, Any]] = get_fund_data(code)
        if data and judge_fund(data):
            triggered_funds.append(data)

    if triggered_funds:
        card_payload = build_feishu_card(triggered_funds)
        send_to_feishu(webhook_url, card_payload)
    else:
        print("[*] 今日无满足定投策略的基金。")

if __name__ == "__main__":
    main()
