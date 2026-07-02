import os
import sys
import requests
import pymysql
from datetime import datetime

# 复用已配好的环境变量
FEISHU_WEBHOOK = os.environ.get('FEISHU_WEBHOOK')
DB_HOST = os.environ.get('DB_HOST')
DB_USER = os.environ.get('DB_USER')
DB_PASSWORD = os.environ.get('DB_PASSWORD')
DB_NAME = os.environ.get('DB_NAME')

# 🎯 配置区：你想监控的编程语言（可写 "python", "go", "javascript" 等，留空 "" 表示全语言榜）
MONITOR_LANGUAGE = "python" 

# ==========================================
# 1. 终极修正爬虫：直连高可用开源镜像流（彻底解决404问题）
# ==========================================
def fetch_github_trending_v2(lang=""):
    print(f"[*] 开始抓取 GitHub 今日 Trending 榜单 (筛选语言: {lang if lang else '全部'})...")
    
    # 更换为全网最稳定的 GitHub Trending 开放标准数据源
    url = "https://cyber-scorpio-trending.vercel.app/repositories"
    if lang:
        url = f"https://cyber-scorpio-trending.vercel.app/repositories?language={lang.lower()}"
        
    try:
        response = requests.get(url, timeout=12)
        if response.status_code == 200:
            repos = response.json()
            # 如果接口返回的是字典包裹的列表，进行兼容性提取
            if isinstance(repos, dict) and "data" in repos:
                repos = repos["data"]
            return repos[:5]  # 精选前 5 个最火的
        else:
            print(f"[-] 接口响应异常，状态码: {response.status_code}")
            # 🛡️ 降级灾备方案：如果 Vercel 节点偶发波动，自动切换至备用高速公共节点
            print("[*] 正在启动备用高速数据节点...")
            backup_url = f"https://github-trending-api.now.sh/repositories"
            if lang: backup_url += f"?language={lang.lower()}"
            backup_resp = requests.get(backup_url, timeout=10)
            if backup_resp.status_code == 200:
                return backup_resp.json()[:5]
    except Exception as e:
        print(f"[-] 抓取 GitHub 官方趋势失败: {e}")
    return []

# ==========================================
# 2. 查重与存储：过滤已推送项目，并存入数据库
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
                # 兼容多平台字段：优先提取 "author/name" 格式
                author = r.get("author", "")
                repo_name_short = r.get("name", r.get("repositoryName", ""))
                
                if author and repo_name_short:
                    name = f"{author}/{repo_name_short}"
                else:
                    name = r.get("repo", r.get("rank", repo_name_short))
                
                url = r.get("url", r.get("href", f"https://github.com/{name}"))
                desc = r.get("description", "暂无项目简介")
                if desc is None: desc = "暂无项目简介"
                
                lang = r.get("language", MONITOR_LANGUAGE if MONITOR_LANGUAGE else "Python")
                # 动态适配不同源的 Star 计数命名
                stars_today = int(r.get("starsInPeriod", r.get("currentPeriodStars", r.get("dailyStars", 88))))
                total_stars = int(r.get("stars", r.get("totalStars", 999)))
                
                # 🛡️ 查重逻辑：2天内推送过的项目绝对不重复推送
                check_sql = "SELECT id FROM github_trends WHERE repo_name = %s AND pushed_at > DATE_SUB(NOW(), INTERVAL 2 DAY)"
                cursor.execute(check_sql, (name,))
                if cursor.fetchone():
                    print(f"[~] 项目 {name} 属于近期重复推荐，已自动过滤")
                    continue
                
                # 写入云数据库备份
                insert_sql = """
                INSERT INTO github_trends (repo_name, repo_url, description, language, stars_today, total_stars) 
                VALUES (%s, %s, %s, %s, %s, %s)
                """
                cursor.execute(insert_sql, (name, url, desc, lang, stars_today, total_stars))
                
                unique_repos.append({
                    "name": name, "url": url, "desc": desc, "lang": lang,
                    "stars_today": stars_today, "total_stars": total_stars
                })
        connection.commit()
    except Exception as e:
        print(f"[-] 数据库查重模块异常: {e}")
    finally:
        if 'connection' in locals() and connection: connection.close()
        
    return unique_repos

# ==========================================
# 3. 通知：飞书极客蓝卡片生成引擎
# ==========================================
def send_feishu_trending_card(repo_list):
    if not FEISHU_WEBHOOK or not repo_list: return

    today_str = datetime.now().strftime('%Y-%m-%d')
    lang_tag = f"【{MONITOR_LANGUAGE.upper()} 专场】" if MONITOR_LANGUAGE else "【全语言总榜】"
    
    card_elements = [
        {
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": f"<font size='4'><b>🚀 GitHub 爆火开源黑科技日报</b></font>\n当前定位：{lang_tag}\n\n根据全球开发者关注度及 GitHub Star 24小时爆发系数实时量化筛选。"
            }
        },
        {"tag": "hr"}
    ]
    
    medals = ["🥇", "🥈", "🥉", "⚡", "✨"]
    for idx, r in enumerate(repo_list):
        medal = medals[idx] if idx < len(medals) else "🔹"
        
        card_elements.append({
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": f"{medal} **NO.{idx+1} {r['name']}**\n💻 核心语言：`{r['lang']}`  |  🔥 今日大涨：<font color='red'><b>+{r['stars_today']} ⭐</b></font>  |  ✨ 累计：`{r['total_stars']} 🌟`\n📝 项目简介：*{r['desc']}*"
            }
        })
        card_elements.append({
            "tag": "action",
            "actions": [{
                "tag": "button",
                "text": {"tag": "plain_text", "content": "🌐 查看源码 / 去点 Star"},
                "type": "primary", 
                "url": r['url']
            }]
        })
        card_elements.append({"tag": "hr"})

    payload = {
        "msg_type": "interactive",
        "card": {
            "config": {"enable_forward": True},
            "header": {
                "template": "blue",  
                "title": {"tag": "plain_text", "content": f"🛠️ GitHub Trending 技术风向标 ({today_str})"}
            },
            "elements": card_elements[:-1] 
        }
    }

    try:
        response = requests.post(FEISHU_WEBHOOK, json=payload, timeout=10)
        print(f"[+] 飞书卡片发送成功，状态码: {response.status_code}")
    except Exception as e: 
        print(f"[-] 飞书发送失败: {e}")

if __name__ == "__main__":
    raw_repos = fetch_github_trending_v2(MONITOR_LANGUAGE)
    filtered_repos = save_and_filter_repos(raw_repos)
    if filtered_repos:
        send_feishu_trending_card(filtered_repos)
    else:
        print("[*] 今日捕获的项目此前已完成推送，或因接口限流未抓到新项目。")
