import os
import sys
import requests
import pymysql
import json
from datetime import datetime

# 从 GitHub Secrets 自动读取环境变量
FEISHU_WEBHOOK = os.environ.get('FEISHU_WEBHOOK')
DB_HOST = os.environ.get('DB_HOST')
DB_USER = os.environ.get('DB_USER')
DB_PASSWORD = os.environ.get('DB_PASSWORD')
DB_NAME = os.environ.get('DB_NAME')

def get_user_holdings():
    holdings = {}
    try:
        connection = pymysql.connect(
            host=DB_HOST, user=DB_USER, password=DB_PASSWORD, database=DB_NAME,
            port=3306, charset='utf8mb4', connect_timeout=10
        )
        with connection.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute("SELECT * FROM user_holdings")
            rows = cursor.fetchall()
            for row in rows:
                holdings[row['fund_code']] = row
    except Exception as e:
        print(f"[-] 读取持仓配置失败: {e}")
    finally:
        if 'connection' in locals() and connection:
            connection.close()
    return holdings

# 📊 独家算法：根据涨跌幅动态生成可视化纯文本图形条
def generate_visual_bar(rate):
    try:
        # 将涨跌幅放大映射到 10 个格子的进度条
        level = min(max(int(abs(rate) * 3), 1), 10) 
        filled = "█" * level
        empty = "░" * (10 - level)
        if rate >= 0:
            return f"`[{filled}{empty}]` 📈"
        else:
            return f"`[{empty}{filled}]` 📉"
    except:
        return "`[░░░░░░░░░░]`"

def fetch_and_calculate():
    holdings = get_user_holdings()
    if not holdings:
        print("[!] 警告：未在数据库中检测到任何资产持仓配置！")
        return [], 0.0, 0.0

    calculated_funds = []
    total_today_earning = 0.0  
    total_hold_earning = 0.0   

    for code, meta in holdings.items():
        try:
            url = f"http://fundgz.1234567.com.cn/js/{code}.js"
            response = requests.get(url, timeout=5)
            
            if response.status_code == 200 and "jsonpgz" in response.text:
                clean_text = response.text[max(0, response.text.find("{")):response.text.rfind("}")+1]
                data = json.loads(clean_text)
                
                estimated_nav = float(data.get("gsz", data["dwjz"])) if data.get("gsz") else float(data["dwjz"])
                growth_rate = float(data.get("gszzl", "0.0")) if data.get("gszzl") else 0.0
                yesterday_nav = float(data["dwjz"])      
                v_time = data.get("gztime", datetime.now().strftime('%H:%M'))
                
                shares = float(meta['holding_shares'])
                cost = float(meta['cost_price'])
                investment = float(meta['total_investment'])
                
                today_earning = shares * (estimated_nav - yesterday_nav)
                current_market_value = shares * estimated_nav
                hold_earning = current_market_value - investment
                
                total_today_earning += today_earning
                total_hold_earning += hold_earning
                
                calculated_funds.append({
                    "code": code,
                    "name": meta['fund_name'],
                    "nav": estimated_nav,
                    "rate": growth_rate,
                    "v_time": v_time,
                    "today_earning": round(today_earning, 2),
                    "hold_earning": round(hold_earning, 2),
                    "visual_bar": generate_visual_bar(growth_rate) # 塞入图形数据
                })
        except Exception as e:
            print(f"[-] 基金 [{code}] 计算失败: {e}")
            
    return calculated_funds, round(total_today_earning, 2), round(total_hold_earning, 2)

def save_snapshot_to_mysql(fund_list):
    if not fund_list: return False
    try:
        connection = pymysql.connect(
            host=DB_HOST, user=DB_USER, password=DB_PASSWORD, database=DB_NAME, port=3306
        )
        with connection.cursor() as cursor:
            sql = """
            INSERT INTO fund_valuation_history 
            (fund_code, fund_name, estimated_nav, growth_rate, valuation_time) 
            VALUES (%s, %s, %s, %s, %s)
            """
            payload = [(f['code'], f['name'], f['nav'], f['rate'], f['v_time']) for f in fund_list]
            cursor.executemany(sql, payload)
        connection.commit()
        return True
    except Exception as e:
        print(f"[-] 历史快照存入失败: {e}")
        return False
    finally:
        if 'connection' in locals() and connection: connection.close()

def send_advanced_feishu_card(fund_list, today_total, hold_total, db_success):
    if not FEISHU_WEBHOOK: return

    today_str = datetime.now().strftime('%Y-%m-%d')
    account_color = "red" if today_total >= 0 else "green"
    account_sign = "+" if today_total >= 0 else ""
    hold_sign = "+" if hold_total >= 0 else ""
    db_status_text = "🟢 写入成功" if db_success else "🔴 写入异常"
    
    card_fields = []
    for f in fund_list:
        if f['rate'] >= 1.5: icon = "🔺 暴涨"
        elif f['rate'] > 0: icon = "📈 翻红"
        elif f['rate'] < -1.5: icon = "🚨 暴跌"
        else: icon = "📉 飘绿"
        
        color = "red" if f['rate'] >= 0 else "green"
        rate_sign = "+" if f['rate'] >= 0 else ""
        today_earn_sign = "+" if f['today_earning'] >= 0 else ""
        hold_earn_sign = "+" if f['hold_earn_sign'] if 'hold_earn_sign' in locals() else ("+" if f['hold_earning'] >= 0 else "")
        
        # 左栏：加入图形化能量条
        card_fields.append({
            "is_short": True,
            "text": {
                "tag": "lark_md",
                "content": f"**{f['name']}** ({f['code']})\n⏱️ 状态：{icon}\n📊 实时涨跌：<font color='{color}'>**{rate_sign}{f['rate']}%**</font>\n纵览：{f['visual_bar']}"
            }
        })
        # 右栏
        card_fields.append({
            "is_short": True,
            "text": {
                "tag": "lark_md",
                "content": f"💰 今日盈亏：<font color='{color}'>**{today_earn_sign}{f['today_earning']} 元**</font>\n📦 累计盈亏：**{"+" if f['hold_earning']>=0 else ""}{f['hold_earning']} 元**\n💎 净值估算：**{f['nav']}**"
            }
        })

    advanced_payload = {
        "msg_type": "interactive",
        "card": {
            "config": {"enable_forward": True},
            "header": {
                "template": "violet" if today_total >= 0 else "turquoise",  
                "title": {"tag": "plain_text", "content": f"🏆 智能资产财富大盘日报 ({today_str})"}
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        # ✨ 彻底解决井号乱码：去掉所有 # 号，使用飞书原生支持的粗体超大高亮文字
                        "content": f"<font size='4'><b>📊 今日账户总资产复盘</b></font>\n\n☀️ 今日全账户收益总计：<font color='{account_color}'>**{account_sign}{today_total} 元**</font>\n🌲 历史全账户持仓总盈亏：**{hold_sign}{hold_total} 元**"
                    }
                },
                {"tag": "hr"}, 
                {
                    "tag": "div",
                    "fields": card_fields 
                },
                {"tag": "hr"},
                {
                    "tag": "note",
                    "elements": [
                        {"tag": "plain_text", "content": f"📡 数据源：天天基金实时节点 | 存储状态：{db_status_text}"}
                    ]
                }
            ]
        }
    }

    try:
        response = requests.post(FEISHU_WEBHOOK, json=advanced_payload, timeout=10)
        print(f"[+] 飞书发送完成，响应状态码: {response.status_code}")
    except Exception as e:
        print(f"[-] 飞书发送失败: {e}")

if __name__ == "__main__":
    data_list, today_sum, hold_sum = fetch_and_calculate()
    db_status = save_snapshot_to_mysql(data_list)
    send_advanced_feishu_card(data_list, today_sum, hold_sum, db_status)
