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

# 🎯 配置区：设定你想监控的编程语言（"python", "go", "javascript" 等）
MONITOR_LANGUAGE = "python" 

# ==========================================
# 1. 官方 API 驱动：稳定获取新晋黑马项目
# ==========================================
def fetch_github_trending_official(lang="python"):
    print(f"[*] 正在调用 GitHub 官方 API 获取最热开源项目 (语言: {lang})...")
    # 筛选过去 7 天内创建的项目
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
            print(f"[-] 官方 API 响应异常，状态码: {response.status_code}")
    except Exception as e:
        print(f"[-] 请求 GitHub 官方接口失败: {e}")
    return []

# ==========================================
# 2. 查重与持久化存储（内置自动备份机制）
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
                
                # 🛡️ 查重：3 天内推送过的不重复推送
                check_sql = "SELECT id FROM github_trends WHERE repo_name = %s AND pushed_at > DATE_SUB(NOW(), INTERVAL 3 DAY)"
                cursor.execute(check_sql, (name,))
                if cursor.fetchone():
                    print(f"[~] 项目 {name} 近期已推送，自动跳过")
                    continue
                
                insert_sql = """
                INSERT INTO github_trends (repo_name, repo_url, description, language, stars_today, total_stars) 
                VALUES (%s, %s, %s, %s, %s, %s)
                """
                cursor.execute(insert_sql, (name, url, desc, lang, forks, total_stars))
                unique_repos.append({
                    "name": name, "url": url, "desc": desc, "lang": lang,
                    "forks": forks, "total_stars": total_stars
                })
        connection.commit()
    except Exception as e:
        print(f"[-] 数据库处理异常: {e}")
    finally:
        if 'connection' in locals() and connection: connection.close()
    return unique_repos

# ==========================================
# 3. 发送飞书 5.0 终极流线美学卡片
# ==========================================
def send_feishu_trending_card(repo_list):
    if not FEISHU_WEBHOOK or not repo_list: return

    today_str = datetime.now().strftime('%Y-%m-%d')
    lang_tag = f"官方认证 · {MONITOR_LANGUAGE.upper()} 趋势"
    
    # 顶部摘要区：借鉴基金报结构，简洁清爽
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
    
    # 核心流式排版：坚固耐看，绝无错位变形
    for idx, r in enumerate(repo_list):
        medal = medals[idx] if idx < len(medals) else "🔹"
        
        card_elements.append({
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": f"{medal} **[{r['name']}]({r['url']})**\n✨ 全网总计：<font color='red'><b>{r['total_stars']} ⭐</b></font>  |  🍴 派生：`{r['forks']}`  |  💻 语言：`{r['lang']}`\n<font color='grey'>📝 {r['desc']}</font>"
            }
        })
        card_elements.append({"tag": "hr"})

    payload = {
        "msg_type": "interactive",
        "card": {
            "config": {"enable_forward": True},
            "header": {
                "template": "blue",  # 换回你熟悉的经典沉稳商务蓝
                "title": {"tag": "plain_text", "content": "🚀 GitHub New-Waves 趋势早报"}
            },
            "elements": card_elements[:-1] # 优雅地移除最后一条多余的分割线
        }
    }

    try:
        response = requests.post(FEISHU_WEBHOOK, json=payload, timeout=10)
        print(f"[+] 5.0 完美版卡片发送成功，状态码: {response.status_code}")
    except Exception as e: 
        print(f"[-] 飞书发送失败: {e}")

if __name__ == "__main__":
    raw_repos = fetch_github_trending_official(MONITOR_LANGUAGE)
    filtered_repos = save_and_filter_repos(raw_repos)
    if filtered_repos:
        send_feishu_trending_card(filtered_repos)
    else:
        print("[*] 官方抓取成功，但当前无新增未推送项目。")
