import os
import requests
import pymysql
import json
import time
from datetime import datetime
from chinese_calendar import is_workday

# 配置获取
FEISHU_WEBHOOK = os.environ.get('FEISHU_WEBHOOK')
DB_HOST = os.environ.get('DB_HOST')
DB_USER = os.environ.get('DB_USER')
DB_PASSWORD = os.environ.get('DB_PASSWORD')
DB_NAME = os.environ.get('DB_NAME')
DB_PORT = int(os.environ.get('DB_PORT', 4000))

# 1. 统一数据库连接（带有重试逻辑）
def get_db_connection(retries=3, delay=5):
    for i in range(retries):
        try:
            return pymysql.connect(
                host=DB_HOST, port=DB_PORT, user=DB_USER,
                password=DB_PASSWORD, database=DB_NAME, 
                charset='utf8mb4', connect_timeout=10,
                cursorclass=pymysql.cursors.DictCursor
            )
        except Exception as e:
            print(f"数据库连接失败，重试 ({i+1}/{retries})... 错误: {e}")
            time.sleep(delay)
    raise Exception("无法连接到数据库")

# 2. 可视化条算法
def generate_visual_bar(rate):
    try:
        level = min(max(int(abs(rate) * 3), 1), 10)
        filled = "█" * level
        empty = "░" * (10 - level)
        return f"`[{filled}{empty}]` 📈" if rate >= 0 else f"`[{empty}{filled}]` 📉"
    except:
        return "`[░░░░░░░░░░]`"

# 3. 获取配置和最近一次历史净值（修复晚上降级为0的问题）
def get_user_holdings():
    holdings = {}
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # 获取持仓信息
            cursor.execute("SELECT * FROM user_holdings")
            for row in cursor.fetchall():
                code = row['fund_code']
                holdings[code] = row
                # 默认先拿成本价兜底
                holdings[code]['last_nav'] = float(row['cost_price'])

            # 从历史快照表里查出每只基金“最近一次”的估值，作为晚上非交易时间的兜底
            for code in holdings:
                cursor.execute(
                    "SELECT estimated_nav FROM fund_valuation_history WHERE fund_code = %s ORDER BY valuation_time DESC LIMIT 1",
                    (code,)
                )
                res = cursor.fetchone()
                if res and res['estimated_nav']:
                    holdings[code]['last_nav'] = float(res['estimated_nav'])
    finally:
        conn.close()
    return holdings

# 4. 核心计算逻辑
def fetch_and_calculate():
    holdings = get_user_holdings()
    if not holdings:
        print("[!] 未检测到持仓配置！请检查数据库 user_holdings 表中是否有数据。")
        return [], 0.0, 0.0

    calculated_funds, total_today_earning, total_hold_earning = [], 0.0, 0.0

    for code, meta in holdings.items():
        estimated_nav, growth_rate, v_time = None, 0.0, datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        try:
            url = f"http://fundgz.1234567.com.cn/js/{code}.js"
            response = requests.get(url, timeout=5)
            if response.status_code == 200 and "jsonpgz" in response.text:
                clean_text = response.text[response.text.find("{"):response.text.rfind("}")+1]
                data = json.loads(clean_text)
                estimated_nav = float(data.get("gsz", data["dwjz"]))
                growth_rate = float(data.get("gszzl", "0.0"))
                v_time = data.get("gztime", v_time)
        except Exception as e:
            print(f"[-] 实时接口请求 [{code}] 失败: {e}，将使用数据库历史净值降级兜底。")

        cost_price = float(meta['cost_price'])
        shares = float(meta['holding_shares'])
        investment = float(meta['total_investment'])
        fallback_nav = float(meta['last_nav'])

        # 如果接口拿不到实时净值，使用数据库中最近一次的历史净值降级
        if estimated_nav is None:
            estimated_nav = fallback_nav

        # 今日收益 = 份额 * (当前估值 - 最近一次历史净值)
        today_earning = shares * (estimated_nav - fallback_nav)
        hold_earning = (shares * estimated_nav) - investment
        
        total_today_earning += today_earning
        total_hold_earning += hold_earning
        
        calculated_funds.append({
            "code": code, "name": meta['fund_name'], "nav": estimated_nav,
            "rate": growth_rate, "v_time": v_time,
            "today_earning": round(today_earning, 2),
            "hold_earning": round(hold_earning, 2),
            "visual_bar": generate_visual_bar(growth_rate)
        })
        
    return calculated_funds, round(total_today_earning, 2), round(total_hold_earning, 2)

# 5. 数据入库
def save_snapshot_to_mysql(fund_list):
    if not fund_list: return False
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            sql = "INSERT INTO fund_valuation_history (fund_code, fund_name, estimated_nav, growth_rate, valuation_time) VALUES (%s, %s, %s, %s, %s)"
            cursor.executemany(sql, [(f['code'], f['name'], f['nav'], f['rate'], f['v_time']) for f in fund_list])
        conn.commit()
        return True
    except Exception as e:
        print(f"[-] 历史快照存入失败: {e}")
        return False
    finally:
        conn.close()

# 6. 推送飞书卡片
def send_advanced_feishu_card(fund_list, today_total, hold_total, db_success):
    if not FEISHU_WEBHOOK: return
    
    alert_msg = "\n".join([f"⚠️ 预警: {f['name']} 波动达 {f['rate']}%!" for f in fund_list if abs(f['rate']) > 3.0])
    today_str = datetime.now().strftime('%Y-%m-%d')
    account_color = "red" if today_total >= 0 else "green"
    
    card_fields = []
    for f in fund_list:
        color = "red" if f['rate'] >= 0 else "green"
        card_fields.append({"is_short": True, "text": {"tag": "lark_md", "content": f"**{f['name']}**\n📊 涨跌: <font color='{color}'>**{f['rate']}%**</font>\n{f['visual_bar']}"}})
        card_fields.append({"is_short": True, "text": {"tag": "lark_md", "content": f"💰 今日: **{f['today_earning']}**\n📦 累计: **{f['hold_earning']}**"}})

    payload = {
        "msg_type": "interactive",
        "card": {
            "header": {"template": "violet" if today_total >= 0 else "turquoise", "title": {"tag": "plain_text", "content": f"🏆 资产复盘 ({today_str})"}},
            "elements": [
                {"tag": "div", "text": {"tag": "lark_md", "content": f"今日总收益：<font color='{account_color}'>**{today_total} 元**</font>{alert_msg}"}},
                {"tag": "hr"}, {"tag": "div", "fields": card_fields}, {"tag": "hr"},
                {"tag": "note", "elements": [{"tag": "plain_text", "content": f"存储状态：{'🟢 成功' if db_success else '🔴 异常'}"}]}
            ]
        }
    }
    requests.post(FEISHU_WEBHOOK, json=payload, timeout=10)

if __name__ == "__main__":
    today = datetime.now().date()
    
    if not is_workday(today):
        print(f"今天 ({today}) 是周末或法定节假日，跳过基金检测任务。")
        exit(0)
        
    print(f"今天 ({today}) 是法定工作日，开始执行基金检测任务...")
    
    data_list, today_sum, hold_sum = fetch_and_calculate()
    
    if not data_list:
        print("[!] 未获取到任何基金数据。")
        exit(0)
        
    db_status = save_snapshot_to_mysql(data_list)
    send_advanced_feishu_card(data_list, today_sum, hold_sum, db_status)
    print("基金检测任务执行完毕并已成功推送。")
