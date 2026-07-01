# 多交易所监控（Binance + Bybit 扩展）设计文档

日期：2026-07-01
状态：已批准，待写实现计划

## 1. 目标

把现有的 OKX 监控扩展为 **3 大交易所（OKX / Binance / Bybit）** 统一监控：
- **上下币公告**：三家，近 N 天滚动窗口，上币/下币分类。
- **交易规则文档**：三家，列表枚举（含子页面/全树）+ 正文逐字 diff。
- **费率**：仅 OKX 保留现有能力；**Binance / Bybit 本期不做**（费率来源不干净，用户决定先搁置）。

产物：**一份合并报告 + 一条合并 Slack**（三家分节）；沿用"仅有变更才写报告"。

## 2. 数据源（全部已实测，纯 curl，无需无头浏览器）

所有请求走代理 `http://127.0.0.1:7890`。时间戳统一归一为 **epoch 秒**。

### 2.1 OKX（现有，保留）
见 `2026-06-30-okx-doc-monitor-design.md`。中文靠 `Accept-Language: zh-CN` 头。

### 2.2 Binance（中文靠请求头 `lang: zh-CN`）
- **公告**：`GET https://www.binance.com/bapi/composite/v1/public/cms/article/list/query?type=1&catalogId=<48上线|161下架>&pageNo=<n>&pageSize=20`
  - 列表：`data.catalogs[0].articles[]`；每项 `id`/`code`/`title`(中文)/`releaseDate`(ms)。总数 `data.catalogs[0].total`；`pageNo` 递增到 `articles` 空。
  - 文章 URL：`https://www.binance.com/zh-CN/support/announcement/<code>`。
- **规则文档-列表**：同端点 `type=2&catalogId=4`（衍生品；其它顶级 catalogId：1账户/2充提/3现货杠杆/4衍生品/5金融/6API/7安全/8其它）。3 层树，文章挂在叶节点 `catalogs[..].catalogs[..].articles[]`；`pageNo` 是**每个叶分类**的分页。
- **规则文档-正文**：`GET .../bapi/composite/v1/public/cms/article/detail/query?articleCode=<code>`
  - `data.body`（正文，稳定，约 12KB）、`data.title`、`data.lastUpdateTime`(ms，**权威更新信号**)。整个响应跨请求稳定、无易变 token。
- **费率**：本期不做（`/fee/trading` 与 bapi fee 均被 WAF/鉴权挡住）。

### 2.3 Bybit（中文靠 URL locale `zh-MY`；`zh-CN` 不支持）
- **公告**：`GET https://api.bybit.com/v5/announcements/index?locale=zh-MY&type=<new_crypto|delistings>&page=<n>&limit=20`
  - 列表：`result.list[]`；每项 `title`/`url`/`publishTime`(ms)/`type.key`(分类)。总数 `result.total`（`ceil(total/limit)` 得页数）。无鉴权、无易变 token。
- **规则文档-列表**：`GET https://www.bybit.com/zh-MY/help-center/topic-list/<category-url>`，SSR，解析 `<script id="__NEXT_DATA__">` 的 `props.pageProps.data.children[].articles[]`（每项 `code`/`url`/`title`）。全部分类在 `props.pageProps.categories[]`。
- **规则文档-正文**：`GET https://www.bybit.com/zh-MY/help-center/article/<article-url>`，解析 `props.pageProps.article`：`tabs[0].tab_content`(HTML 正文，用于 diff)、`tabs[0].last_updated`(字符串 `"YYYY-MM-DD HH:MM:SS"` UTC，**权威更新信号**)。**必须用 zh-MY/zh-TW**（en 下部分文章为空）。`buildId` 为静态部署哈希，diff 干净。
- **费率**：本期不做（用户给的 `announcement-info/fee-rate` 实测 301 无效；费率分散在 help-center 若干文章）。

## 3. 架构：通用核心 + 交易所适配器

### 3.1 通用核心（复用现有，做必要泛化）
- `fetcher.py`：`get_json`/`get_text`/`post_json` 增加**按调用传自定义 header** 的能力（Binance 需 `lang: zh-CN`，OKX 需 `Accept-Language`），默认仍带全局头。
- `snapshot.py`：不变（load/save/unified_diff）。
- `report.py`：改为渲染**多交易所合并报告**（三家分节，每家含 文档变更 / 费率(仅OKX) / 公告）。
- `slack.py`：`build_slack_message` 改为多交易所分节汇总。
- `monitor.py`：`run()` 泛化为**遍历适配器**，每家独立读写自己的快照、算 diff，聚合为一个 `RunResult`（含各交易所结果）。

### 3.2 交易所适配器接口 `ExchangeAdapter`
每家一个模块（`exchanges/okx.py`、`exchanges/binance.py`、`exchanges/bybit.py`），实现：
```
name: str                                              # "OKX" / "Binance" / "Bybit"
fetch_docs(fetcher) -> list[DocMeta]                   # 枚举全树+子页面; update_time 归一为秒
fetch_doc_body(fetcher, doc: DocMeta) -> str           # 单篇正文(用于 diff)
fetch_announcements(fetcher, now_ts, window_days) -> AnnResult  # {new:[Announcement], delist:[Announcement]}
fetch_fees(fetcher) -> str | None                      # OKX 返回费率文本; Binance/Bybit 返回 None
```
- `DocMeta` 归一字段：`slug/title/url/update_time(秒)`；各家在适配器内把 ms / 字符串时间转成秒。
- 核心逻辑与 OKX 现状一致：`update_time` 为权威变更信号，变化则重抓正文给逐字 diff；新增/删除文档也列出。

### 3.3 各家变更检测归一
- OKX：`updateTime`(秒)。
- Binance：`detail.lastUpdateTime`(ms→秒)。**注意**：列表只有 `releaseDate`，要拿 `lastUpdateTime` 必须抓详情——即枚举后逐篇抓详情（详情同时给 body）。
- Bybit：`article.tabs[0].last_updated`(字符串→秒)。同样需抓文章页。

## 4. 快照与产物
- 快照按交易所分文件：`snapshots/{okx,binance,bybit}.json`，结构 `{docs:{slug:{title,update_time,body}}, fees_text?}`（费率键仅 OKX 有）。隔离，互不影响；删单个文件 = 重置该家基线。
- 报告：`reports/exchanges-YYYYMMDD-HHMM.md`，三家分节；沿用"仅有实质变更（任一家文档变更或 OKX 费率变化）才写"。
- Slack：一条消息，`build_slack_message` 三家分节汇总（标题/链接/上下币）。每次运行都发（沿用现状）。

## 5. 诚实边界
- 变更详情靠快照 diff；首次运行每家各自建基线、标注"基线建立，无 diff"。
- Binance 文档需逐篇抓详情才能拿 `lastUpdateTime`+正文——每次运行请求量较大（按叶分类枚举 + 每篇详情），需 `request_delay` 限速；用 `lastUpdateTime` 变化触发正文重比，未变则复用快照 body（同 OKX 优化）。
- 解析/抓取失败必须显式报错，不静默吞（no silent-wrong）。

## 6. 构建顺序（各自 spec 已合并于此；实现分阶段）
1. **Phase 0**：泛化重构核心 + 把 OKX 改造成 `exchanges/okx.py` 适配器。行为不变，现有 17 测试保持全绿（必要时调整为经适配器调用）。
2. **Phase 1**：`exchanges/binance.py`（公告 + 文档列表枚举 + 详情正文 diff）。
3. **Phase 2**：`exchanges/bybit.py`（公告 + `__NEXT_DATA__` 文档 + 正文 diff）。

## 7. 已知风险
- **接口变更**：三家都用内部/CMS 接口，改版可能失效；解析失败显式报错。
- **Binance 请求量**：文档全树逐篇抓详情，量大、耗时；需限速，必要时按 `lastUpdateTime` 优化（但首次基线仍需全抓）。
- **Bybit `__NEXT_DATA__` 结构**：随站点改版可能变；`buildId` 变化不影响内容 diff。
- **反爬**：Binance bapi 目前无鉴权/无 token，但 HTML/WAF 路径不可用——只走 bapi JSON 接口。
- **子页面/全树枚举深度**：Binance 3 层、Bybit 最多 3 层；需完整枚举，避免静默漏页（沿用 OKX 的截断守卫思路）。
