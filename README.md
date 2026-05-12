# Finance Crawler MCP Server

多源金融资讯采集 MCP 服务，支持抓取：
- 东方财富股吧评论
- 同花顺个股聚焦、公告速递、公司资讯、近期要闻
- 自动生成邮件报告（可选，需配置邮箱参数）

## 工具列表

- `collect_all_news`：采集所有资讯源并发送邮件报告
- `crawl_guba`：单独抓取指定股票代码的股吧帖子
- `crawl_recent_news`：单独抓取同花顺近期要闻

## 安装

```bash
pip install finance-crawler-mcp