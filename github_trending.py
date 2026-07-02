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

# 🎯 配置区：切换为 "go" 以测试 3.0 全新排版效果（后续可改回 "python"）
MONITOR_LANGUAGE = "go" 

# ==========================================
# 1. 官方 API 驱动：获取过去一周内最火爆的开源项目
# ==========================================
def fetch_github_trending_official(lang="python"):
    print(f"[*] 正在调用 GitHub 官方 API 获取最热开源项目 (语言: {lang})...")
    
    # 计算 7 天前的日期，用于筛选真正的“新晋黑马”项目
    seven_days_ago = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
    
    # 组装官方高级搜索 Query：指定语言 + 创建时间在一周内
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
            return items[:5]  # 精选全网最火的前 5 名
        else:
            print(f"[-] 官方 API 响应异常，状态码: {response.status_code}，详情: {response.text}")
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
                name = r.get("full_name")  # 官方字段格式: "author/repo"
                url = r.get("html_url")     # 官方标准链接
                desc = r.get("description", "暂无项目简介")
                if not desc: desc = "暂无项目简介"
                
                lang = r.get("language", MONITOR_LANGUAGE.capitalize())
                total_stars = int(r.get("stargazers_count", 0))
                forks = int(r.get("forks_count", 0)) 
                
                # 🛡️ 查重逻辑：3天内推送过的项目绝对不重复推送
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
# 3. 发送飞书高级 3.0 Columns 分栏卡片
# ==========================================
def send_feishu_trending_card(repo_list):
    if not FEISHU_WEBHOOK or not repo_list: return

    today_str = datetime.now().strftime('%Y-%m-%d')
    lang_tag = f"官方认证 · {MONITOR_LANGUAGE.upper()}"
    
    # 顶栏导言
    card_elements = [
        {
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": f"🎯 **订阅大盘：** `{lang_tag}`\n📅 **快报日期：** {today_str}\n\n*为您精选过去 7 天内，全球开源社区热度爆发系数最高的新晋黑马项目。*"
            }
        },
        {"tag": "hr"}
    ]
    
    medals = ["🥇", "🥈", "🥉", "⚡", "✨"]
    for idx, r in enumerate(repo_list):
        medal = medals[idx] if idx < len(medals) else "🔹"
        
        # 3.0 视觉核心：利用 Columns 组件将卡片左右对齐分栏
        card_elements.append({
            "tag": "column_set",
            "flex_mode": "stretch",
            "background_style": "default",
            "columns": [
                {
                    "tag": "column",
                    "width": "weighted",
                    "weight": 7,  # 左边占 70% 宽度放名字和简介
                    "elements": [
                        {
                            "tag": "div",
                            "text": {
                                "tag": "lark_md",
                                "content": f"{medal} **{r['name']}**\n<font color='grey'>📝 {r['desc']}</font>"
                            }
                        }
                    ]
                },
                {
                    "tag": "column",
                    "width": "weighted",
                    "weight": 3,  # 右边占 30% 宽度，独立包裹数据方块
                    "elements": [
                        {
                            "tag": "div",
                            "text": {
                                "tag": "lark_md",
                                "content": f"<font color='red'><b>⭐ {r['total_stars']}</b></font>\n<font color='blue'>🍴 {r['forks']}</font>"
                            }
                        }
                    ]
                }
            ]
        })
        
        # 紧凑轻量按钮：告别臃肿，只占一小行
        card_elements.append({
            "tag": "action",
            "actions": [{
                "tag": "button",
                "text": {"tag": "plain_text", "content": "⚡ 探索源码仓库"},
                "type": "default", 
                "size": "small",
                "url": r['url']
            }]
        })
        card_elements.append({"tag": "hr"})

    payload = {
        "msg_type": "interactive",
        "card": {
            "config": {"enable_forward": True},
            "header": {
                "template": "violet",  # 升级为高级极客紫底色
                "title": {"tag": "plain_text", "content": "💡 GitHub New-Waves 趋势早报"}
            },
            "elements": card_elements[:-1] # 移除末尾多余的分割线
        }
    }

    try:
        response = requests.post(FEISHU_WEBHOOK, json=payload, timeout=10)
        print(f"[+] 3.0 美化版卡片发送成功，状态码: {response.status_code}")
    except Exception as e: 
        print(f"[-] 飞书发送失败: {e}")

if __name__ == "__main__":
    raw_repos = fetch_github_trending_official(MONITOR_LANGUAGE)
    filtered_repos = save_and_filter_repos(raw_repos)
    if filtered_repos:
        send_feishu_trending_card(filtered_repos)
    else:
        print("[*] 官方抓取成功，但今日捕获的顶流项目此前已完成推送。")
