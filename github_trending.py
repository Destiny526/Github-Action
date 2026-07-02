import os
import sys
import requests
import pymysql
from datetime import datetime, timedelta

# 复用已配好的环境变量
FEISHU_WEBHOOK = os.environ.get('FEISHU_WEBHOOK')
DB_HOST = os.environ.get('DB_HOST')
DB_USER = os.environ.get('DB_USER')
DB_PASSWORD = os.environ.get('DB_PASSWORD')
DB_NAME = os.environ.get('DB_NAME')

# 🎯 配置区：设定你想监控的编程语言
MONITOR_LANGUAGE = "python" 

# ==========================================
# 🛡️ 工业级灾备：新增飞书报错告警卡片
# ==========================================
def send_error_alert(error_msg):
    if not FEISHU_WEBHOOK: return
    payload = {
        "msg_type": "interactive",
        "card": {
            "config": {"enable_forward": True},
            "header": {
                "template": "red", # 显眼的警报红
                "title": {"tag": "plain_text", "content": "⚠️ GitHub 监控流运行异常"}
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"🚨 **异常时间：** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n🔍 **监控语言：** `{MONITOR_LANGUAGE.upper()}`\n❌ **详细错误日志：**\n```\n{error_msg}\n```\n*请及时检查 GitHub Actions 运行状态或 API 额度是否耗尽。*"
                    }
                }
            ]
        }
    }
    try:
        requests.post(FEISHU_WEBHOOK, json=payload, timeout=10)
    except Exception as e:
        print(f"[-] 连报警卡片都发不出去了: {e}")

# ==========================================
# 1. 官方 API 驱动：稳定获取新晋黑马项目
# ==========================================
def fetch_github_trending_official(lang="python"):
    print(f"[*] 正在调用 GitHub 官方 API 获取最热开源项目 (语言: {lang})...")
    seven_days_ago = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
    query = f"language:{lang} created:>{seven_days_ago}"
    url = f"https://api.github.com/search/repositories?q={query}&sort=stars&order=desc"
    
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    }
    try:
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code == 200:
            result = response.json()
            items = result.get("items", [])
            print(f"[+] 成功从官方捕获到 {len(items)} 个候选项目！")
            return items[:5]
        else:
            err_text = f"官方 API 响应异常，状态码: {response.status_code}，详情: {response.text}"
            print(f"[-] {err_text}")
            send_error_alert(err_text) # 💡 触发飞书报错告警
    except Exception as e:
        err_text = f"请求 GitHub 官方接口发生致命崩溃: {e}"
        print(f"[-] {err_text}")
        send_error_alert(err_text) # 💡 触发飞书崩溃告警
    return []

# ==========================================
# 2. 查重、动态增量计算与持久化存储
# ==========================================
def save_and_filter_repos(repos):
    if not repos: return []
    unique_repos = []
    try:
        connection = pymysql.connect(
            host=DB_HOST, user=DB_USER, password=DB_PASSWORD, database=DB_NAME, port=3306
        )
        with connection.cursor() as cursor:
            for r in repos:
                name = r.get("full_name")
                url = r.get("html_url")
                desc = r.get("description", "暂无项目简介")
                if not desc: desc = "暂无项目简介"
                
                lang = r.get("language", MONITOR_LANGUAGE.capitalize())
                total_stars = int(r.get("stargazers_count", 0))
                forks = int(r.get("forks_count", 0)) 
                
                # 📈 算法核心：去数据库追踪这个项目历史上的 Star 数，计算真正的“今日暴涨”
                stars_today = 0
                history_sql = "SELECT total_stars FROM github_trends WHERE repo_name = %s ORDER BY pushed_at DESC LIMIT 1"
                cursor.execute(history_sql, (name,))
                history_data = cursor.fetchone()
                
                if history_data:
                    last_total_stars = int(history_data[0])
                    # 算差值
                    if total_stars > last_total_stars:
                        stars_today = total_stars - last_total_stars
                
                # 🛡️ 查重：3 天内推送过的不重复推送
                check_sql = "SELECT id FROM github_trends WHERE repo_name = %s AND pushed_at > DATE_SUB(NOW(), INTERVAL 3 DAY)"
                cursor.execute(check_sql, (name,))
                if cursor.fetchone():
                    print(f"[~] 项目 {name} 近期已推送，自动跳过")
                    continue
                
                # 写入云数据库备份
                insert_sql = """
                INSERT INTO github_trends (repo_name, repo_url, description, language, stars_today, total_stars) 
                VALUES (%s, %s, %s, %s, %s, %s)
                """
                cursor.execute(insert_sql, (name, url, desc, lang, stars_today, total_stars))
                
                unique_repos.append({
                    "name": name, "url": url, "desc": desc, "lang": lang,
                    "forks": forks, "total_stars": total_stars, "stars_today": stars_today
                })
        connection.commit()
    except Exception as e:
        print(f"[-] 数据库处理异常: {e}")
        send_error_alert(f"数据库存储/查重模块崩溃: {e}") # 💡 触发飞书存储异常告警
    finally:
        if 'connection' in locals() and connection: connection.close()
    return unique_repos

# ==========================================
# 3. 发送飞书 6.0 数据全景卡片
# ==========================================
def send_feishu_trending_card(repo_list):
    if not FEISHU_WEBHOOK or not repo_list: return

    today_str = datetime.now().strftime('%Y-%m-%d')
    lang_tag = f"官方认证 · {MONITOR_LANGUAGE.upper()} 趋势"
    
    card_elements = [
        {
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": f"🎯 **订阅大盘：** `{lang_tag}`\n📅 **快报日期：** {today_str}\n\n*为你穿透全球开源数据，实时追踪近 7 天内热度爆发最高的黑马项目。*"
            }
        },
        {"tag": "hr"}
    ]
    
    medals = ["🥇", "🥈", "🥉", "⚡", "✨"]
    
    for idx, r in enumerate(repo_list):
        medal = medals[idx] if idx < len(medals) else "🔹"
        
        # 💡 根据是否算出了“今日新增”动态渲染尾巴
        trend_tail = f" (今日 +{r['stars_today']} 🔥)" if r['stars_today'] > 0 else ""
        
        card_elements.append({
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": f"{medal} **[{r['name']}]({r['url']})**\n✨ 全网总计：<font color='red'><b>{r['total_stars']} ⭐</b></font>{trend_tail}  |  🍴 派生：`{r['forks']}`  |  💻 语言：`{r['lang']}`\n<font color='grey'>📝 {r['desc']}</font>"
            }
        })
        card_elements.append({"tag": "hr"})

    payload = {
        "msg_type": "interactive",
        "card": {
            "config": {"enable_forward": True},
            "header": {
                "template": "blue", 
                "title": {"tag": "plain_text", "content": "🚀 GitHub New-Waves 趋势早报"}
            },
            "elements": card_elements[:-1]
        }
    }

    try:
        response = requests.post(FEISHU_WEBHOOK, json=payload, timeout=10)
        print(f"[+] 6.0 升级版卡片发送成功，状态码: {response.status_code}")
    except Exception as e: 
        print(f"[-] 飞书发送失败: {e}")

if __name__ == "__main__":
    raw_repos = fetch_github_trending_official(MONITOR_LANGUAGE)
    filtered_repos = save_and_filter_repos(raw_repos)
    if filtered_repos:
        send_feishu_trending_card(filtered_repos)
    else:
        print("[*] 官方抓取成功，但当前无新增未推送项目。")
