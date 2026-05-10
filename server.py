#!/usr/bin/env python3
"""
MCP 服务：多源金融资讯采集（SSE 版本，适配魔搭免费托管）
"""

import sys
import json
import time
import csv
import io
import ssl
import smtplib
import re
import requests
from datetime import datetime, timezone, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from bs4 import BeautifulSoup
from collections import Counter, defaultdict
from typing import List, Optional

from fastmcp import FastMCP

# 尝试导入股吧库，若未安装则自动跳过（不影响其他数据源）
try:
    from stock_stil import comments
    STOCK_STIL_AVAILABLE = True
except ImportError:
    STOCK_STIL_AVAILABLE = False

mcp = FastMCP("FinanceCrawler")

# ===================== 通用配置 =====================
TZ_CN = timezone(timedelta(hours=8))
HEADERS_10JQKA = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://stock.10jqka.com.cn/",
}

SMTP_SERVER = "smtp.163.com"
SMTP_PORT = 465
SENDER_EMAIL = "m13956155221_1@163.com"
AUTH_CODE = "JEYLKpUU3pthEddH"          # 建议改用环境变量
RECEIVER_EMAILS = [
    "kellybian89@163.com",
    "1239601342@qq.com"
]

# ===================== 工具函数 =====================
def clean_text(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r'<[^>]+>', '', text)
    text = text.replace('\n', ' ').replace('\r', ' ').replace('\t', ' ')
    text = re.sub(r'\s+', ' ', text).strip()
    return text

# ===================== 数据源 1：股吧评论 =====================
def fetch_guba_posts(stock_code: str = "002455", target: int = 50) -> List[dict]:
    if not STOCK_STIL_AVAILABLE:
        print("stock_stil 未安装，跳过股吧抓取", file=sys.stderr)
        return []
    try:
        post_list = comments.getEastMoneyPostList(stock_code=stock_code)
    except Exception as e:
        print(f"股吧列表获取失败: {e}", file=sys.stderr)
        return []
    results = []
    for post in post_list[:target]:
        pid = post.post_id
        title = getattr(post, "post_title", "")
        try:
            detail = comments.getEstMoneyPostDetail(stock_code=stock_code, post_id=pid)
            content = getattr(detail, "post_content", "")
        except:
            content = ""
        results.append({
            "type": "股吧评论",
            "title": clean_text(title),
            "content": clean_text(content),
            "post_id": pid,
            "publish_time": getattr(post, "post_publish_time", ""),
            "source": "东方财富股吧"
        })
        time.sleep(1.0)
    print(f"股吧评论获取 {len(results)} 条", file=sys.stderr)
    return results

# ===================== 数据源 2：个股聚焦（API + HTML 备用）=====================
def _extract_body(url: str) -> str:
    try:
        resp = requests.get(url, headers=HEADERS_10JQKA, timeout=10)
        resp.encoding = resp.apparent_encoding or "utf-8"
        soup = BeautifulSoup(resp.text, "html.parser")
        for sel in ["div.main-text", "div.article-content", "div.article_con", "div#content",
                     "div.detail-content", "div.newsContent", "div.art_main", "div.article-body", "div.body"]:
            container = soup.select_one(sel)
            if container:
                text = container.get_text(separator=' ', strip=True)
                text = re.sub(r'\s+', ' ', text)
                if len(text) > 100:
                    return text
        pars = [p.get_text(strip=True) for p in soup.find_all("p") if len(p.get_text(strip=True)) > 20]
        if pars:
            text = " ".join(pars)
            if len(text) > 100:
                return text
        body = soup.find("body")
        if body:
            for tag in body(["script", "style", "nav", "footer"]):
                tag.decompose()
            text = body.get_text(separator=' ', strip=True)
            text = re.sub(r'\s+', ' ', text)
            if len(text) > 100:
                return text
    except:
        pass
    return ""

def _fetch_news_contents(news_items: list, source_type: str) -> list:
    results = []
    for item in news_items[:20]:
        title = item["title"]
        url = item["url"]
        content = _extract_body(url)
        results.append({
            "type": source_type,
            "title": title,
            "content": clean_text(content),
            "url": url,
            "source": "同花顺"
        })
        time.sleep(1.5)
    return results

def fetch_ggjj_news() -> list:
    items = []
    api_url = "https://stock.10jqka.com.cn/interface/getArticleList.php?class=ggjj&page=1&num=20"
    try:
        resp = requests.get(api_url, headers=HEADERS_10JQKA, timeout=10)
        data = resp.json()
        articles = data.get("list") or data.get("article_list") or []
        for art in articles:
            title = art.get("title", "").strip()
            url = art.get("art_url") or art.get("url", "")
            if not title or not url:
                continue
            full_url = url if url.startswith("http") else "https:" + url
            items.append({"title": title, "url": full_url})
        if items:
            print(f"个股聚焦 API 获取 {len(items)} 条", file=sys.stderr)
            return _fetch_news_contents(items, "个股聚焦")
    except Exception as e:
        print(f"个股聚焦 API 失败，尝试 HTML 解析: {e}", file=sys.stderr)

    list_url = "https://stock.10jqka.com.cn/ggjj_list/"
    try:
        resp = requests.get(list_url, headers=HEADERS_10JQKA, timeout=10)
        resp.encoding = resp.apparent_encoding or "gbk"
        soup = BeautifulSoup(resp.text, "html.parser")
        for a in soup.find_all("a", href=True):
            href = a['href']
            title = a.get_text(strip=True)
            if re.search(r"/\d{8}/c\d+\.shtml", href) and len(title) > 5:
                full_url = href if href.startswith("http") else "https:" + href
                items.append({"title": title, "url": full_url})
            if len(items) >= 20:
                break
    except Exception as e:
        print(f"个股聚焦 HTML 获取失败: {e}", file=sys.stderr)
    return _fetch_news_contents(items, "个股聚焦")

# ===================== 数据源 3：公告速递 =====================
def fetch_ggsd_today() -> list:
    base_url = "https://data.10jqka.com.cn/market/ggsd/"
    today_str = datetime.now().strftime("%m-%d")
    all_titles = []
    page = 1
    while page <= 3:
        url = base_url if page == 1 else f"{base_url}?page={page}"
        try:
            resp = requests.get(url, headers=HEADERS_10JQKA, timeout=10)
            resp.encoding = resp.apparent_encoding or "gbk"
            soup = BeautifulSoup(resp.text, "html.parser")
            rows = soup.select("table.m-table tr") or soup.find_all("tr")
            for row in rows:
                cols = row.find_all("td")
                if len(cols) < 3:
                    continue
                date_text = cols[0].get_text(strip=True)
                if today_str not in date_text:
                    continue
                title = ""
                for col in cols[1:]:
                    txt = col.get_text(strip=True)
                    if len(txt) > 5 and len(txt) > len(title):
                        title = txt
                if title:
                    all_titles.append(title)
            if not all_titles:
                break
            page += 1
            time.sleep(1.5)
        except Exception as e:
            print(f"公告速递第{page}页失败: {e}", file=sys.stderr)
            break
    unique = []
    for t in all_titles:
        if t not in unique:
            unique.append(t)
    print(f"公告速递获取 {len(unique)} 条", file=sys.stderr)
    return [{"type": "公告速递", "title": t, "content": "", "source": "同花顺公告"} for t in unique[:20]]

# ===================== 数据源 4：公司资讯 =====================
def fetch_company_news() -> list:
    list_url = "https://stock.10jqka.com.cn/companynews_list/"
    items = []
    try:
        resp = requests.get(list_url, headers=HEADERS_10JQKA, timeout=10)
        resp.encoding = 'gbk'
        soup = BeautifulSoup(resp.text, "html.parser")
        for a in soup.find_all("a", href=True):
            href = a['href']
            title = a.get_text(strip=True)
            if re.search(r"/\d{8}/c\d+\.shtml", href) and len(title) > 5:
                full_url = href if href.startswith("http") else "https:" + href
                items.append({"title": title, "url": full_url})
            if len(items) >= 20:
                break
    except Exception as e:
        print(f"公司资讯列表获取失败: {e}", file=sys.stderr)
        return []
    return _fetch_news_contents(items, "公司资讯")

# ===================== 数据源 5：近期新闻（同花顺要闻）=====================
def fetch_recent_news(pages: int = 2) -> list:
    headers = {"User-Agent": "Mozilla/5.0"}
    all_items = []
    for page in range(1, pages+1):
        url = f"https://news.10jqka.com.cn/tapp/news/push/stock/?page={page}&pagesize=100"
        try:
            resp = requests.get(url, headers=headers, timeout=10)
            data = resp.json()
            for item in data.get('data', {}).get('list', []):
                title = item.get('title', '').strip()
                if len(title) >= 5:
                    all_items.append({
                        "type": "近期新闻",
                        "title": title,
                        "content": item.get('digest', ''),
                        "publish_time": item.get('ctime', ''),
                        "source": item.get('source', '同花顺')
                    })
            time.sleep(0.5)
        except Exception as e:
            print(f"近期新闻第{page}页失败: {e}", file=sys.stderr)
            break
    seen = set()
    unique = []
    for item in all_items:
        if item['title'] not in seen:
            seen.add(item['title'])
            unique.append(item)
    return unique[:100]

# ===================== 邮件发送（摘要 + CSV 附件）=====================
def send_email_with_csv_attachment(analysis_time: str, all_data: list):
    if not all_data:
        return
    type_counts = Counter(item['type'] for item in all_data)
    lines = [f"<h3>📋 本次采集概览</h3><ul>"]
    for t, cnt in type_counts.items():
        lines.append(f"<li><b>{t}</b>：{cnt} 条</li>")
    lines.append("</ul>")
    grouped = defaultdict(list)
    for item in all_data:
        grouped[item['type']].append(item)
    for category in ["股吧评论", "个股聚焦", "公告速递", "公司资讯", "近期新闻"]:
        items = grouped.get(category, [])
        if not items:
            continue
        lines.append(f"<h4>{category} 示例（前3条）</h4><ul>")
        for it in items[:3]:
            title = it.get('title', '')[:80]
            content = it.get('content', '')
            snippet = content[:60] + "..." if len(content) > 60 else content
            lines.append(f"<li><b>{title}</b> —— {snippet}</li>")
        lines.append("</ul>")
    html_body = f"""
    <html><head><style>body{{font-family:'Microsoft YaHei',Arial;}}h2{{color:#2c3e50;}}h3{{color:#27ae60;}}ul{{list-style:none;padding:0;}}li{{margin:5px 0;}}.footer{{margin-top:30px;font-size:12px;color:#7f8c8d;}}</style></head>
    <body><h2>📊 多源金融资讯采集报告</h2><p><strong>生成时间：</strong> {analysis_time}</p>{''.join(lines)}<div class="footer"><p>完整数据见附件 <b>financial_news.csv</b></p><p>此邮件由自动化系统生成，仅供参考</p></div></body></html>"""
    fieldnames = ["type", "title", "content", "url", "publish_time", "source", "post_id"]
    output = io.StringIO()
    output.write('\ufeff')
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction='ignore')
    writer.writeheader()
    writer.writerows(all_data)
    csv_content = output.getvalue()
    output.close()
    csv_filename = f"financial_news_{analysis_time.replace(' ', '_').replace(':', '-')}.csv"
    for receiver in RECEIVER_EMAILS:
        msg = MIMEMultipart('mixed')
        msg['Subject'] = f"金融数据采集报告_{analysis_time.replace(' ', '_')}"
        msg['From'] = SENDER_EMAIL
        msg['To'] = receiver
        msg.attach(MIMEText(html_body, 'html', 'utf-8'))
        part = MIMEBase('application', 'octet-stream')
        part.set_payload(csv_content.encode('utf-8'))
        encoders.encode_base64(part)
        part.add_header('Content-Disposition', f'attachment; filename="{csv_filename}"')
        msg.attach(part)
        try:
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT, context=context) as server:
                server.login(SENDER_EMAIL, AUTH_CODE)
                server.send_message(msg)
            print(f"✅ 邮件已成功发送至 {receiver}")
            time.sleep(1)
        except Exception as e:
            print(f"❌ 发送至 {receiver} 失败: {e}")

# ===================== MCP 工具注册 =====================
@mcp.tool()
def collect_all_news(stock_code: str = "002455",
                     guba_target: int = 50,
                     ggjj_count: int = 20,
                     ggsd_count: int = 20,
                     company_count: int = 20,
                     recent_pages: int = 2) -> dict:
    """采集五种金融资讯源，自动发送邮件报告。"""
    analysis_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    all_data = []
    all_data.extend(fetch_guba_posts(stock_code, guba_target))
    all_data.extend(fetch_ggjj_news()[:ggjj_count])
    all_data.extend(fetch_ggsd_today()[:ggsd_count])
    all_data.extend(fetch_company_news()[:company_count])
    all_data.extend(fetch_recent_news(recent_pages))
    send_email_with_csv_attachment(analysis_time, all_data)
    type_counts = Counter(item['type'] for item in all_data)
    return {"status": "success", "analysis_time": analysis_time,
            "total_items": len(all_data), "type_counts": dict(type_counts)}

@mcp.tool()
def crawl_guba(stock_code: str = "002455", target: int = 50) -> list:
    """单独抓取东方财富股吧帖子"""
    return fetch_guba_posts(stock_code, target)

@mcp.tool()
def crawl_recent_news(pages: int = 2) -> list:
    """单独抓取同花顺要闻"""
    return fetch_recent_news(pages)

# ===================== 启动入口（SSE 模式）=====================
def main():
    # 显式开启 SSE 传输，监听 8000 端口，适配魔搭免费托管容器
    mcp.run(transport="sse", host="0.0.0.0", port=8000)

if __name__ == "__main__":
    main()