import os
import sys
import requests
import pymysql
from datetime import datetime

# ==========================================
# 1. 从 GitHub Secrets 自动读取环境变量
# ==========================================
# 飞书配置
FEISHU_WEBHOOK = os.environ.get('FEISHU_WEBHOOK')

# 阿里云 MySQL 配置
DB_HOST = os.environ.get('DB_HOST')
DB_USER = os.environ.get('DB_USER')
DB_PASSWORD = os.environ.get('DB_PASSWORD')
DB_NAME = os.environ.get('DB_NAME')

# ==========================================
# 2. 核心业务：数据抓取与策略筛选
# ==========================================
def fetch_and_filter_funds():
    """
    这里编写你原有的天天基金数据抓取与策略筛选逻辑。
    为了演示整套流水线畅通，这里模拟两条即将入库的基金估值数据。
    实际使用时，请将其替换为你真正的抓取解析代码，并返回相同格式的列表。
    """
    print("[*] 开始抓取基金当日盘中估值行情...")
    
    # 模拟抓取到的数据列表，每个元素为一个元组，对应数据库表字段：
    # (fund_code, fund_name, estimated_nav, growth_rate, valuation_time)
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    mock_filtered_funds = [
        ("005918", "天弘中证计算机主题ETF联接A", 0.9854, 1.25, current_time),
        ("161725", "招商中证白酒指数A", 2.1450, -0.85, current_time)
    ]
    
    # 💡 提示：如果今天没有符合你策略的基金，可以返回空列表 []
    return mock_filtered_funds

# ==========================================
# 3. 核心功能：批量写入云服务器 MySQL
# ==========================================
def save_to_mysql(fund_list):
    if not fund_list:
        print("[*] 今日无符合策略的基金数据，跳过数据库写入。")
        return False

    # 检查数据库环境变量是否齐全
    if not all([DB_HOST, DB_USER, DB_PASSWORD, DB_NAME]):
        print("[-] 错误: 缺少数据库配置环境变量，请检查 GitHub Secrets！")
        return False

    print(f"[*] 发现 {len(fund_list)} 条基金数据，正在尝试连接远程服务器 {DB_HOST}...")
    connection = None
    try:
        # 建立与阿里云服务器的公网 SSL/TCP 连接
        connection = pymysql.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME,
            port=3306,
            charset='utf8mb4',
            connect_timeout=10
        )
        
        with connection.cursor() as cursor:
            # 编写标准的批量插入 SQL 语句
            sql = """
            INSERT INTO fund_valuation_history 
            (fund_code, fund_name, estimated_nav, growth_rate, valuation_time) 
            VALUES (%s, %s, %s, %s, %s)
            """
            # 使用 executemany 高效批量插入
            cursor.executemany(sql, fund_list)
            
        # 提交事务
        connection.commit()
        print("[+] 恭喜！基金数据已成功实时同步至阿里云 MySQL 数据库！")
        return True

    except Exception as e:
        print(f"[-] 数据库入库失败，错误原因: {e}")
        return False
    finally:
        if connection:
            connection.close()

# ==========================================
# 4. 核心功能：发送飞书卡片通知
# ==========================================
def send_feishu_notification(fund_list, db_success):
    if not FEISHU_WEBHOOK:
        print("[*] 未配置飞书 Webhook，跳过群通知发送。")
        return

    # 根据数据库写入结果，动态在卡片底部加个小标签
    db_status_text = "🟢 数据已同步至云数据库" if db_success else "🔴 数据未写入数据库"

    # 构建飞书消息体（这里可以放你原本高颜值的卡片 JSON）
    # 简单示例如下：
    content_text = f"💡 今日基金监控报告\n时间: {datetime.now().strftime('%Y-%m-%d')}\n\n"
    if fund_list:
        for fund in fund_list:
            content_text += f"📌 [{fund[0]}] {fund[1]}\n   盘中估值: {fund[2]} ({fund[3]}%)\n"
    else:
        content_text += "✨ 今日无满足特定策略的基金。\n"
        
    content_text += f"\n状态: {db_status_text}"

    payload = {
        "msg_type": "text",
        "content": {
            "text": content_text
        }
    }

    try:
        response = requests.post(FEISHU_WEBHOOK, json=payload, timeout=10)
        if response.status_code == 200:
            print("[+] 飞书消息卡片发送成功！")
        else:
            print(f"[-] 飞书发送失败，状态码: {response.status_code}")
    except Exception as e:
        print(f"[-] 飞书发送异常: {e}")

# ==========================================
# 5. 主程序入口
# ==========================================
if __name__ == "__main__":
    # 1. 抓取并筛选
    filtered_funds = fetch_and_filter_funds()
    
    # 2. 存入阿里云 MySQL 并拿到结果状态
    db_status = save_to_mysql(filtered_funds)
    
    # 3. 推送飞书通知
    send_feishu_notification(filtered_funds, db_status)
    
    print("[*] 今日自动化流水线执行完毕。")
