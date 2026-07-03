import os
import requests
import pymysql
import time
from datetime import datetime, timedelta

# 配置获取
FEISHU_WEBHOOK = os.environ.get('FEISHU_WEBHOOK')
DB_HOST = os.environ.get('DB_HOST')
DB_USER = os.environ.get('DB_USER')
DB_PASSWORD = os.environ.get('DB_PASSWORD')
DB_NAME = os.environ.get('DB_NAME')
DB_PORT = int(os.environ.get('DB_PORT', 4000))
DEEPSEEK_API_KEY = os.environ.get('DEEPSEEK_API_KEY')
GITHUB_TOKEN = os.environ.get('MY_GITHUB_PAT')

MONITOR_LANGUAGE = "python"

# 1. 统一的数据库连接函数（带重试机制）
def get_db_connection(retries=3, delay=5):
    for i in range(retries):
        try:
            return pymysql.connect(
                host=DB_HOST, port=DB_PORT, user=DB_USER,
                password=DB_PASSWORD, database=DB_NAME, autocommit=True
            )
        except Exception as e:
            print(f"数据库连接失败，重试 ({i+1}/{retries})... 错误: {e}")
            time.sleep(delay)
    raise Exception("无法连接到数据库")

# 2. AI 智能摘要（已修正 URL 和鉴权格式）
def ask_ai_to_summarize_and_score(repo_name, raw_desc):
    if not DEEPSEEK_API_KEY: return 5, raw_desc
    
    # 使用标准接口地址
    url = "https://api.deepseek.com/chat/completions"
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY.strip()}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "deepseek-chat", 
        "messages": [{"role": "user", "content": f"项目: {repo_name}，简介: {raw_desc}。请：1.30字内总结；2.技术价值打分(0-10)。格式：[分数] 总结。"}], 
        "temperature": 0.2
    }
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=20)
        if response.status_code == 200:
            data = response.json()
            content = data['choices'][0]['message']['content'].strip()
            if ']' in content:
                score = int(content.split(']')[0].replace('[', ''))
                summary = content.split(']')[1].strip()
                return score, summary
        else:
            print(f"DEBUG: AI API 失败 (状态码: {response.status_code}), 响应内容: {response.text}")
    except Exception as e:
        print(f"DEBUG: AI 请求异常: {str(e)}")
    return 5, raw_desc

# 3. 获取 GitHub 数据
def fetch_github_trending_official(lang="python"):
    url = f"https://api.github.com/search/repositories?q=language:{lang} created:>{(datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')}&sort=stars&order=desc"
    headers = {"Accept": "application/vnd.github.v3+json", "Authorization": f"token {GITHUB_TOKEN}", "User-Agent": "GitHub-Trending-Bot"}
    try:
        response = requests.get(url, headers=headers, timeout=15)
        return response.json().get("items", [])[:8] if response.status_code == 200 else []
    except Exception as e:
        print(f"获取 GitHub 数据失败: {e}")
        return []

# 4. 处理、评分、存储
def save_and_filter_repos(repos):
    unique_repos = []
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            for r in repos:
                name, total_stars = r.get("full_name"), int(r.get("stargazers_count", 0))
                cursor.execute("SELECT total_stars FROM github_trends WHERE repo_name = %s ORDER BY pushed_at DESC LIMIT 1", (name,))
                last = cursor.fetchone()
                stars_today = (total_stars - int(last[0])) if last and last[0] else 0
                
                cursor.execute("SELECT id FROM github_trends WHERE repo_name = %s AND pushed_at > DATE_SUB(NOW(), INTERVAL 3 DAY)", (name,))
                if cursor.fetchone(): continue
                
                score, ai_desc = ask_ai_to_summarize_and_score(name, r.get("description", "暂无简介"))
                if score < 6: continue
                
                cursor.execute("INSERT INTO github_trends (repo_name, repo_url, description, language, stars_today, total_stars) VALUES (%s, %s, %s, %s, %s, %s)",
                               (name, r.get("html_url"), ai_desc, r.get("language", "Python"), stars_today, total_stars))
                unique_repos.append({"name": name, "url": r.get("html_url"), "desc": ai_desc, "stars": total_stars, "today": stars_today})
    finally:
        conn.close()
    return unique_repos

# 5. 发送飞书卡片
def send_feishu_card(repo_list):
    if not repo_list or not FEISHU_WEBHOOK: return
    elements = [{"tag": "div", "text": {"tag": "lark_md", "content": f"**[{r['name']}]({r['url']})**\n⭐ {r['stars']} (今日 +{r['today']}) | 💡 {r['desc']}"}} for r in repo_list]
    for i in range(len(elements) - 1, 0, -1): elements.insert(i, {"tag": "hr"})
    requests.post(FEISHU_WEBHOOK, json={"msg_type": "interactive", "card": {"header": {"title": {"tag": "plain_text", "content": "🚀 GitHub 智能趋势 (精选)"}}, "elements": elements}})

if __name__ == "__main__":
    raw_data = fetch_github_trending_official(MONITOR_LANGUAGE)
    if raw_data:
        filtered_data = save_and_filter_repos(raw_data)
        if filtered_data: send_feishu_card(filtered_data)
