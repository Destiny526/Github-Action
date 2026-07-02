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
DEEPSEEK_API_KEY = os.environ.get('DEEPSEEK_API_KEY')  # 💡 引入 AI 密钥

# 🎯 配置区：设定你想监控的编程语言（可以随时改回 python、go、javascript 等）
MONITOR_LANGUAGE = "python" 

# ==========================================
# 🧠 AI 赋能模块：大模型一句话大白话总结
# ==========================================
def ask_ai_to_summarize(repo_name, raw_desc):
    if not DEEPSEEK_API_KEY:
        print("[~] 未检测到 DEEPSEEK_API_KEY，降级使用原始简介")
        return raw_desc

    # 根据是否有原版简介，动态生成更聪明的 Prompt
    if not raw_desc or raw_desc == "暂无项目简介":
        prompt = f"请根据 GitHub 项目名 '{repo_name}'，用一句话大白话中文预测并说明这个开源项目是干嘛的。严格控制在 25 字以内。"
    else:
        prompt = f"请将这个 GitHub 项目的英文简介翻译并精简为一句话大白话中文。项目名: {repo_name}，原简介: {raw_desc}。要求：1. 必须是中文；2. 极其通俗易懂；3. 严格控制在 30 字以内，去掉多余废话。"

    url = "https://api.deepseek.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2  # 低随机性，保证翻译和总结稳定
    }
    
    try:
        print(f"[*] 正在为项目 {repo_name} 唤醒 AI 生成中文大白话简介...")
        response = requests.post(url, json=payload, timeout=12)
        if response.status_code == 200:
            ai_result = response.json()['choices'][0]['message']['content'].strip()
            # 过滤掉大模型偶尔带的多余双引号
            return ai_result.replace('"', '').replace('“', '').replace('”', '')
        else:
            print(f"[~] AI 接口响应异常(状态码 {response.status_code})，降级使用原简介")
    except Exception as e:
        print(f"[~] AI 摘要请求超时或失败，降级使用原简介: {e}")
    return raw_desc

# ==========================================
# 🛡️ 工业级灾备：飞书报错告警卡片
# ==========================================
def send_error_alert(error_msg):
    if not FEISHU_WEBHOOK: return
    payload = {
        "msg_type": "interactive",
        "card": {
            "config": {"enable_forward": True},
            "header": {
                "template": "red",
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
    try: requests.post(FEISHU_WEBHOOK, json=payload, timeout=10)
    except Exception as e: print(f"[-] 连报警卡片都发不出去了: {e}")

# ==========================================
# 1. 官方 API 驱动：获取新晋黑马项目
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
            send_error_alert(err_text)
    except Exception as e:
        err_text = f"请求 GitHub 官方接口发生致命崩溃: {e}"
        print(f"[-] {err_text}")
        send_error_alert(err_text)
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
                raw_desc = r.get("description", "暂无项目简介")
                if not raw_desc: raw_desc = "暂无项目简介"
                
                lang = r.get("language", MONITOR_LANGUAGE.capitalize())
                total_stars = int(r.get("stargazers_count", 0))
                forks = int(r.get("forks_count", 0)) 
                
                # 📈 增量计算：去数据库追踪这个项目历史上的 Star 数
                stars_today = 0
                history_sql = "SELECT total_stars FROM github_trends WHERE repo_name = %s ORDER BY pushed_at DESC LIMIT 1"
                cursor.execute(history_sql, (name,))
                history_data = cursor.fetchone()
                if history_data:
                    last_total_stars = int(history_data[0])
                    if total_stars > last_total_stars:
                        stars_today = total_stars - last_total_stars
                
                # 🛡️ 查重：3 天内推送过的不重复推送
                check_sql = "SELECT id FROM github_trends WHERE repo_name = %s AND pushed_at > DATE_SUB(NOW(), INTERVAL 3 DAY)"
                cursor.execute(check_sql, (name,))
                if cursor.fetchone():
                    print(f"[~] 项目 {name} 近期已推送，自动跳过")
                    continue
                
                # 🧠 查重通过后，临门一脚触发 AI 中文大白话提炼，省时省流量
                ai_desc = ask_ai_to_summarize(name, raw_desc)
                
                # 写入云数据库备份
                insert_sql = """
                INSERT INTO github_trends (repo_name, repo_url, description, language, stars_today, total_stars) 
                VALUES (%s, %s, %s, %s, %s, %s)
                """
                cursor.execute(insert_sql, (name, url, ai_desc, lang, stars_today, total_stars))
                
                unique_repos.append({
                    "name": name, "url": url, "desc": ai_desc, "lang": lang,
                    "forks": forks, "total_stars": total_stars, "stars_today": stars_today
                })
        connection.commit()
    except Exception as e:
        print(f"[-] 数据库处理异常: {e}")
        send_error_alert(f"数据库存储/查重/AI摘要模块崩溃: {e}")
    finally:
        if 'connection' in locals() and connection: connection.close()
    return unique_repos

# ==========================================
# 3. 发送飞书 7.0 AI 全景卡片
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
                "content": f"🎯 **订阅大盘：** `{lang_tag}`  |  🤖 **AI 引擎已唤醒**\n📅 **快报日期：** {today_str}\n\n*为你穿透全球开源数据，由 AI 大模型实时提供一句话技术精髓大白话提炼。*"
            }
        },
        {"tag": "hr"}
    ]
    
    medals = ["🥇", "🥈", "🥉", "⚡", "✨"]
    for idx, r in enumerate(repo_list):
        medal = medals[idx] if idx < len(medals) else "🔹"
        trend_tail = f" (今日 +{r['stars_today']} 🔥)" if r['stars_today'] > 0 else ""
        
        card_elements.append({
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": f"{medal} **[{r['name']}]({r['url']})**\n✨ 全网总计：<font color='red'><b>{r['total_stars']} ⭐</b></font>{trend_tail}  |  🍴 派生：`{r['forks']}`  |  💻 语言：`{r['lang']}`\n<font color='green'>💡 **AI 极简速读：** {r['desc']}</font>"
            }
        })
        card_elements.append({"tag": "hr"})

    payload = {
        "msg_type": "interactive",
        "card": {
            "config": {"enable_forward": True},
            "header": {
                "template": "blue", 
                "title": {"tag": "plain_text", "content": "🚀 GitHub New-Waves 智能早报"}
            },
            "elements": card_elements[:-1]
        }
    }

    try:
        response = requests.post(FEISHU_WEBHOOK, json=payload, timeout=10)
        print(f"[+] 7.0 智能版卡片发送成功，状态码: {response.status_code}")
    except Exception as e: 
        print(f"[-] 飞书发送失败: {e}")

if __name__ == "__main__":
    raw_repos = fetch_github_trending_official(MONITOR_LANGUAGE)
    filtered_repos = save_and_filter_repos(raw_repos)
    if filtered_repos:
        send_feishu_trending_card(filtered_repos)
    else:
        print("[*] 官方抓取成功，但今日捕获的项目此前已推送。")
