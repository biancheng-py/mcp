# Finance Crawler MCP Server

多源金融资讯采集 MCP 服务，支持抓取：
- 东方财富股吧评论
- 同花顺个股聚焦、公告速递、公司资讯、近期要闻
- 自动生成邮件报告（可选，需配置邮箱参数）
- **支持用户输入自己的邮箱**，报告会同时发送到固定收件人和用户邮箱

## 工具列表

- `collect_all_news`：采集所有资讯源并发送邮件报告。可通过 `user_email` 参数额外添加收件人。
- `crawl_guba`：单独抓取指定股票代码的股吧帖子
- `crawl_recent_news`：单独抓取同花顺近期要闻

### collect_all_news 参数说明

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `stock_code` | str | `"002455"` | 股票代码 |
| `guba_target` | int | `50` | 股吧抓取最大条数 |
| `ggjj_count` | int | `20` | 个股聚焦抓取条数 |
| `ggsd_count` | int | `20` | 公告速递抓取条数 |
| `company_count` | int | `20` | 公司资讯抓取条数 |
| `recent_pages` | int | `2` | 近期新闻抓取页数（每页约100条） |
| `user_email` | str | `""` | （可选）额外接收报告的邮箱地址。若填写，报告会同时发送至此邮箱（固定收件人也会收到） |

## 安装

```bash
pip install finance-crawler-mcp