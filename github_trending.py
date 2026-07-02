import os
import sys
import requests
import pymysql
from datetime import datetime

# 复用你已经配好的 GitHub Secrets
FEISHU_WEBHOOK = os.environ.get('FEISHU_WEBHOOK')
DB_HOST = os.environ.get('DB_HOST')
DB_USER = os.environ.get('DB_USER')
DB_PASSWORD = os.environ.get('DB_PASSWORD')
DB_NAME = os.environ.get('DB_NAME')

# ==========================================
# 1. 爬虫：抓取今日 GitHub 顶流项目
# ==========================================
def fetch_github_trending():
    print("[*] 开始抓取 GitHub 今日 Trending 榜单...")
    # 使用稳定且无需认证的开放 GitHub Trending API (默认监控全语言 Daily 榜)
    url = "https://data.jsdelivr.com/v1/package/gh/tiangolo/fastapi" # 备用流或开源爬虫源逻辑
    # 转换为直接请求官方或聚合源
    url = "https://api.gitterapp.com/repositories" # 行业通用的免配置免Token源
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            repos = response.json()
            # 我们只取前 5 个最火的，精简阅读
            return repos[:5]
    except Exception as e:
        print(f"[-] 抓取 GitHub 失败: {e}")
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
                name = r.get("author") + "/" + r.get("name")
                url = r.get("url", f"https://github.com/{name}")
                desc = r.get("description", "暂无简介")
                lang = r.get("language", "Unknown")
                stars_today = int(r.get("starsInPeriod", 0))
                total_stars = int(r.get("stars", 0))
                
                # 检查近3天内是否推送过该项目
                check_sql = "SELECT id FROM github_trends WHERE repo_name = %s AND pushed_at > DATE_SUB(NOW(), INTERVAL 3 DAY)"
                cursor.execute(check_sql, (name,))
                if cursor.fetchone():
                    print(f"[~] 项目 {name} 近期已推送，自动跳过")
                    continue
                
                # 写入数据库记录
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
        print(f"[-] 数据库处理异常: {e}")
    finally:
        if 'connection' in locals() and connection: connection.close()
        
    return unique_repos

# ==========================================
# 3. 通知：飞书极客蓝色交互卡片引擎
# ==========================================
def send_feishu_trending_card(repo_list):
    if not FEISHU_WEBHOOK or not repo_list: return

    today_str = datetime.now().strftime('%Y-%m-%d')
    card_elements = [
        {
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": f"<font size='4'><b>🚀 过去24小时 GitHub 爆火开源黑科技</b></font>\n根据全球开发者关注度及 Star 增量算法实时筛选。"
            }
        },
        {"tag": "hr"}
    ]
    
    # 组装每一个项目详情
    for idx, r in enumerate(repo_list, 1):
        card_elements.append({
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": f"🥇 **NO.{idx} {r['name']}**\n💻 语言：`{r['lang']}`  |  🔥 今日新增：<font color='red'><b>+{r['stars_today']} ⭐</b></font>  |  ✨ 总计：`{r['total_stars']} 🌟`\n📝 简介：*{r['desc']}*"
            }
        })
        # 增加一键直达项目的交互按钮组件
        card_elements.append({
            "tag": "action",
            "actions": [{
                "tag": "button",
                "text": {"tag": "plain_text", "content": "🌐 查看源码 / 去点 Star"},
                "type": "primary", # 蓝色商务高亮按钮
                "url": r['url']
            }]
        })
        card_elements.append({"tag": "hr"})

    # 飞书极客蓝卡片外壳
    payload = {
        "msg_type": "interactive",
        "card": {
            "config": {"enable_forward": True},
            "header": {
                "template": "blue",  # 极客科技蓝
                "title": {"tag": "plain_text", "content": f"🛠️ GitHub Trending 极客技术早报 ({today_str})"}
            },
            "elements": card_elements[:-1] # 移除最后一个多余的分割线
        }
    }

    try: requests.post(FEISHU_WEBHOOK, json=payload, timeout=10)
    except Exception as e: print(f"[-] 飞书发送失败: {e}")

if __name__ == "__main__":
    raw_repos = fetch_github_trending()
    filtered_repos = save_and_filter_repos(raw_repos)
    if filtered_repos:
        send_feishu_trending_card(filtered_repos)
    else:
        print("[*] 今日无新增未推送的热门项目。")
