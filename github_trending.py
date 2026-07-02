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

# 🎯 配置区（为了强行看效果，我们先换成 "python" 再次触发新数据，看完效果可以随时改）
MONITOR_LANGUAGE = "python" 

# ==========================================
# 1. 官方 API 驱动
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
            return items[:5]
    except Exception as e:
        print(f"[-] 请求 GitHub 官方接口失败: {e}")
    return []

# ==========================================
# 2. 查重与持久化存储
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
                
                check_sql = "SELECT id FROM github_trends WHERE repo_name = %s AND pushed_at > DATE_SUB(NOW(), INTERVAL 3 DAY)"
                cursor.execute(check_sql, (name,))
                if cursor.fetchone():
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
# 3. 发送飞书极简美学 4.0 艺术卡片
# ==========================================
def send_feishu_trending_card(repo_list):
    if not FEISHU_WEBHOOK or not repo_list: return

    today_str = datetime.now().strftime('%Y-%m-%d')
    lang_tag = f"官方认证 · {MONITOR_LANGUAGE.upper()}"
    
    # 顶部简介面板
    card_elements = [
        {
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": f"🎯 **订阅看板：** `{lang_tag}`  |  📅 **日期：** `{today_str}`\n*为您穿透全球开源数据，精准追踪近 7 天内热度增长最快的黑马项目。*"
            }
        },
        {"tag": "hr"}
    ]
    
    medals = ["🥇", "🥈", "🥉", "⚡", "✨"]
    
    for idx, r in enumerate(repo_list):
        medal = medals[idx] if idx < len(medals) else "🔹"
        
        # 4.0 核心：将名字直接做成一键跳转的超链接，同时将数据做成紧随其后的彩色标签
        card_elements.append({
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": f"{medal} **[{r['name']}]({r['url']})**\n🔥 `⭐ {r['total_stars']}`   🌀 `🍴 {r['forks']}`   🏷️ `{r['lang']}`\n<font color='grey'>📝 {r['desc']}</font>"
            }
        })
        card_elements.append({"tag": "hr"})

    payload = {
        "msg_type": "interactive",
        "card": {
            "config": {"enable_forward": True},
            "header": {
                "template": "blue",  # 沉稳高级商务蓝
                "title": {"tag": "plain_text", "content": "⚡ GitHub Weekly New-Waves 趋势精选"}
            },
            "elements": card_elements[:-1] # 移除多余的末尾分割线
        }
    }

    try:
        response = requests.post(FEISHU_WEBHOOK, json=payload, timeout=10)
        print(f"[+] 4.0 流线版卡片发送成功，状态码: {response.status_code}")
    except Exception as e: 
        print(f"[-] 飞书发送失败: {e}")

if __name__ == "__main__":
    raw_repos = fetch_github_trending_official(MONITOR_LANGUAGE)
    filtered_repos = save_and_filter_repos(raw_repos)
    if filtered_repos:
        send_feishu_trending_card(filtered_repos)
    else:
        print("[*] 官方抓取成功，但当前无新增未推送项目。")
