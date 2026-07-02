import os
import requests
import pymysql
from datetime import datetime, timedelta

# 配置获取
FEISHU_WEBHOOK = os.environ.get('FEISHU_WEBHOOK')
DB_HOST, DB_USER = os.environ.get('DB_HOST'), os.environ.get('DB_USER')
DB_PASSWORD, DB_NAME = os.environ.get('DB_PASSWORD'), os.environ.get('DB_NAME')
DEEPSEEK_API_KEY, GITHUB_TOKEN = os.environ.get('DEEPSEEK_API_KEY'), os.environ.get('MY_GITHUB_PAT')

MONITOR_LANGUAGE = "python"

def ask_ai_to_summarize_and_score(repo_name, raw_desc):
    if not DEEPSEEK_API_KEY: return 5, raw_desc
    prompt = f"项目名: {repo_name}，简介: {raw_desc}。请：1.用30字内中文大白话总结核心用途；2.根据技术价值从 0-10 分打分（0-5分代表文档/简单Demo，6-10分代表有价值工具/框架）。返回格式：[分数] 总结内容。"
    url = "https://api.deepseek.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
    payload = {"model": "deepseek-chat", "messages": [{"role": "user", "content": prompt}], "temperature": 0.2}
    try:
        response = requests.post(url, json=payload, timeout=10)
        content = response.json()['choices'][0]['message']['content'].strip()
        if ']' in content:
            score = int(content.split(']')[0].replace('[', ''))
            summary = content.split(']')[1].strip()
            return score, summary
    except: pass
    return 5, raw_desc

def send_feishu_card(repo_list, title="🚀 GitHub 智能趋势 (精选)"):
    if not repo_list: return
    elements = [{"tag": "div", "text": {"tag": "lark_md", "content": f"**[{r['name']}]({r['url']})**\n⭐ {r['stars']} (今日 +{r['today']}) | 💡 {r['desc']}"}} for r in repo_list]
    for i in range(len(elements) - 1, 0, -1): elements.insert(i, {"tag": "hr"})
    requests.post(FEISHU_WEBHOOK, json={"msg_type": "interactive", "card": {"header": {"title": {"tag": "plain_text", "content": title}}, "elements": elements}})

def send_weekly_report():
    try:
        conn = pymysql.connect(host=DB_HOST, user=DB_USER, password=DB_PASSWORD, database=DB_NAME, port=3306)
        with conn.cursor() as cursor:
            # 获取本周增量最大的 Top 5
            sql = """SELECT repo_name, repo_url, SUM(stars_today) as weekly_growth, MAX(total_stars) as total 
                     FROM github_trends WHERE pushed_at > DATE_SUB(NOW(), INTERVAL 7 DAY) 
                     GROUP BY repo_name ORDER BY weekly_growth DESC LIMIT 5"""
            cursor.execute(sql)
            rows = cursor.fetchall()
            if rows:
                elements = [{"tag": "div", "text": {"tag": "lark_md", "content": f"**[{r[0]}]({r[1]})**\n📈 本周爆涨: +{r[2]} | 🔥 总量: {r[3]}"}} for r in rows]
                for i in range(len(elements) - 1, 0, -1): elements.insert(i, {"tag": "hr"})
                requests.post(FEISHU_WEBHOOK, json={"msg_type": "interactive", "card": {"header": {"title": {"tag": "plain_text", "content": "🏆 GitHub 本周硬核黑马周报"}}, "elements": elements}})
        conn.close()
    except Exception as e: print(f"周报发送失败: {e}")

def save_and_filter_repos(repos):
    unique_repos = []
    conn = pymysql.connect(host=DB_HOST, user=DB_USER, password=DB_PASSWORD, database=DB_NAME, port=3306)
    with conn.cursor() as cursor:
        for r in repos:
            name, total_stars = r.get("full_name"), int(r.get("stargazers_count", 0))
            cursor.execute("SELECT total_stars FROM github_trends WHERE repo_name = %s ORDER BY pushed_at DESC LIMIT 1", (name,))
            last = cursor.fetchone()
            stars_today = (total_stars - int(last[0])) if last else 0
            
            cursor.execute("SELECT id FROM github_trends WHERE repo_name = %s AND pushed_at > DATE_SUB(NOW(), INTERVAL 3 DAY)", (name,))
            if cursor.fetchone(): continue
            
            score, ai_desc = ask_ai_to_summarize_and_score(name, r.get("description", "暂无简介"))
            if score < 6: continue
            
            cursor.execute("INSERT INTO github_trends (repo_name, repo_url, description, language, stars_today, total_stars) VALUES (%s, %s, %s, %s, %s, %s)",
                           (name, r.get("html_url"), ai_desc, r.get("language", "Python"), stars_today, total_stars))
            unique_repos.append({"name": name, "url": r.get("html_url"), "desc": ai_desc, "stars": total_stars, "today": stars_today})
    conn.commit(); conn.close()
    return unique_repos

if __name__ == "__main__":
    raw_data = fetch_github_trending_official(MONITOR_LANGUAGE)
    filtered_data = save_and_filter_repos(raw_data)
    if filtered_data: send_feishu_card(filtered_data)
    # 周日自动发送周报 (weekday 6 代表周日)
    if datetime.now().weekday() == 6: send_weekly_report()
