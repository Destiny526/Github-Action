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

# ==========================================
# 1. 核心算法：连接数据库获取用户的持仓配置
# ==========================================
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

# ==========================================
# 2. 爬虫：抓取天天基金网真实盘中估值并计算盈亏
# ==========================================
def fetch_and_calculate():
    holdings = get_user_holdings()
    if not holdings:
        print("[!] 警告：未在数据库中检测到任何资产持仓配置！")
        return [], 0.0, 0.0

    print(f"[*] 开始计算资产实时盈亏，目标监控代码: {list(holdings.keys())}")
    calculated_funds = []
    total_today_earning = 0.0  # 今日总盈亏汇总
    total_hold_earning = 0.0   # 累计总盈亏汇总

    for code, meta in holdings.items():
        try:
            url = f"http://fundgz.1234567.com.cn/js/{code}.js"
            response = requests.get(url, timeout=5)
            
            if response.status_code == 200 and "jsonpgz" in response.text:
                clean_text = response.text[max(0, response.text.find("{")):response.text.rfind("}")+1]
                data = json.loads(clean_text)
                
                # 🛡️ 全天候容灾核心：如果非交易时间（收盘后）盘中估值 gsz 为空，则自动用单位净值 dwjz 代替，防止非交易时间运行报错
                estimated_nav = float(data.get("gsz", data["dwjz"])) if data.get("gsz") else float(data["dwjz"])
                growth_rate = float(data.get("gszzl", "0.0")) if data.get("gszzl") else 0.0
                yesterday_nav = float(data["dwjz"])      
                v_time = data.get("gztime", datetime.now().strftime('%H:%M'))
                
                # --- 核心量化算法区 ---
                shares = float(meta['holding_shares'])
                cost = float(meta['cost_price'])
                investment = float(meta['total_investment'])
                
                # 1. 计算今日盈亏 = 持有份额 * (最新估值 - 昨收净值)
                today_earning = shares * (estimated_nav - yesterday_nav)
                # 2. 计算累计持仓总盈亏 = 持有总市值 - 总投入本金
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
                    "hold_earning": round(hold_earning, 2)
                })
        except Exception as e:
            print(f"[-] 基金 [{code}] 计算失败: {e}")
            
    return calculated_funds, round(total_today_earning, 2), round(total_hold_earning, 2)

# ==========================================
# 3. 存储：保存实时流水快照
# ==========================================
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

# ==========================================
# 4. 通知：飞书终极 Fields 双栏卡片生成引擎
# ==========================================
def send_advanced_feishu_card(fund_list, today_total, hold_total, db_success):
    if not FEISHU_WEBHOOK: return

    today_str = datetime.now().strftime('%Y-%m-%d')
    
    # 账户全局状态大盘头
    account_color = "red" if today_total >= 0 else "green"
    account_sign = "+" if today_total >= 0 else ""
    hold_sign = "+" if hold_total >= 0 else ""
    db_status_text = "🟢 写入成功" if db_success else "🔴 写入异常"
    
    # 动态组装高阶 Fields 栅格组件
    card_fields = []
    for f in fund_list:
        if f['rate'] >= 1.5: icon = "🔺 暴涨"
        elif f['rate'] > 0: icon = "📈 翻红"
        elif f['rate'] < -1.5: icon = "🚨 暴跌"
        else: icon = "📉 飘绿"
        
        color = "red" if f['rate'] >= 0 else "green"
        rate_sign = "+" if f['rate'] >= 0 else ""
        today_earn_sign = "+" if f['today_earning'] >= 0 else ""
        hold_earn_sign = "+" if f['hold_earning'] >= 0 else ""
        
        # 左栏：基础行情
        card_fields.append({
            "is_short": True,
            "text": {
                "tag": "lark_md",
                "content": f"**{f['name']}** ({f['code']})\n⏱️ 状态：{icon}\n📊 实时涨跌：<font color='{color}'>**{rate_sign}{f['rate']}%**</font>"
            }
        })
        # 右栏：精确到分钱的盈亏量化（已剔除多余反引号标记）
        card_fields.append({
            "is_short": True,
            "text": {
                "tag": "lark_md",
                "content": f"💰 今日盈亏：<font color='{color}'>**{today_earn_sign}{f['today_earning']} 元**</font>\n📦 累计盈亏：**{hold_earn_sign}{f['hold_earning']} 元**\n💎 净值估算：**{f['nav']}**"
            }
        })

    # 飞书高级卡片完备体协议
    advanced_payload = {
        "msg_type": "interactive",
        "card": {
            "config": {"enable_forward": True},
            "header": {
                "template": "violet" if today_total >= 0 else "turquoise",  # 赚了显示紫色，亏了显示松石绿
                "title": {"tag": "plain_text", "content": f"🏆 智能资产财富大盘日报 ({today_str})"}
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": "# 📊 今日账户总资产复盘"  # 🟢 终极修复：独立拆分组件并采用一级大标题，彻底告别“###”乱码不加粗 Bug！
                    }
                },
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"☀️ 今日全账户收益总计：<font color='{account_color}'>**{account_sign}{today_total} 元**</font>\n🌲 历史全账户持仓总盈亏：**{hold_sign}{hold_total} 元**"
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
