# OKX 文档/规则更新监控 — 设计文档

日期：2026-06-30
状态：已批准，待实现

## 1. 目标

监控 OKX（欧易）以下三类页面的更新，产出报告，可重复运行：

1. **交易规则**：检测"更新于"日期前移或正文变化的文档，给出逐字变更。
2. **费率规则**：检测费率页内容是否变化，给出 diff。
3. **上下币公告**：汇总相对基线新增 / 近 N 天（默认 3 天）发布的上币/下币公告。

**基线策略：以今天（2026-06-30）首次运行抓到的信息为基线。** 不使用固定日期阈值；首次运行只建立基线，之后每次运行报告"相对基线（上次快照）的变化"。

## 2. 数据来源（已逆向确认的真实接口）

所有请求走代理 `http://127.0.0.1:7890`，并带请求头 `Accept-Language: zh-CN,zh`（这是返回中文的关键，URL 的 locale 参数无效）。

| 目标 | 接口 | 关键字段 |
|---|---|---|
| 交易规则文档清单 | `GET https://www.okx.com/priapi/v1/assistant/service-center/search/articles?sectionIds=<sectionId>&page=1&size=50` | 返回 `data.list[]`：`title`、`slug`、`url`、`content`(摘要)、`updateTime`(秒，=「更新于」)、`publishTime`。total=21 全量 |
| section id 解析 | `GET https://www.okx.com/priapi/v1/assistant/service-center/kb/unified/category?slug=product-documentation` | 列出该分类所有 section 及 id；按 slug `product-documentation-introduction-to-basic-trading-rules` 取 id（当前为 `3HsUPMtNszv47YPMMMx8Dw`，运行时动态解析、不硬编码） |
| 单篇正文(供 diff) | `GET https://www.okx.com/zh-hans/help/{slug}` | SSR HTML 内嵌 JSON 的 `content` 字段含全文 |
| 上下币公告 | `GET https://www.okx.com/api/v5/support/announcements?annType={announcements-new-listings\|announcements-delistings}&page=N` | `data[0].details[]`：`title`(中文)、`url`、`pTime`(毫秒)、`annType`；`data[0].totalPage`。倒序，逐页直到超出时间窗 |
| 费率规则 | `GET https://www.okx.com/zh-hans/fees` | SSR，含 VIP 等级/挂单/吃单费率内容 |

## 3. 形态与技术栈

- 可重复运行的 Python 脚本，`uv` 管理依赖，`ruff` 格式化/lint。
- 依赖：`httpx`（走代理）+ `selectolax`（HTML 解析）+ 标准库 `difflib`（逐字 diff）、`json`/`re`（从 SSR 提取内嵌 JSON）。
- **所有对 OKX 的请求走代理 `http://127.0.0.1:7890`**，并带 `Accept-Language: zh-CN,zh` 头。
- 数据主要来自 JSON 接口（见 §2），无需无头浏览器（Playwright 不需要）。
- WebFetch 工具不支持代理，故抓取一律由脚本完成。

## 4. 监控逻辑

### 4.1 交易规则
1. 抓取分类页（含翻页）得到全部文档：标题、链接、"更新于"日期。
2. 逐篇抓正文。
3. **首次运行**：把文档清单（标题/链接/更新于日期）+ 各篇正文全部存为基线，不报变化。
4. **后续运行**：与基线对比 —— 文档"更新于"日期前移或正文有差异的，列出并给逐字 diff；新增/删除的文档也列出。

### 4.2 费率规则
- 抓正文存快照。首次为基线；后续与基线对比给 diff。无日期信号，仅靠内容 diff。

### 4.3 上下币公告
- 抓公告分类页（含翻页到覆盖窗口为止）。
- 首次运行：记录当前公告列表为基线，并列出近 N 天（默认 3，即 2026-06-27 至今）的公告。
- 后续运行：列出相对基线新增的公告（即上次运行后发布的）。
- 均按上币 / 下币分类汇总：标题、日期、链接。

## 5. 诚实边界

- "具体改了什么"只能靠**快照 diff**，OKX 无公开 changelog。
- **首次运行 = 建立基线**：能立即给出文档清单、各篇"更新于"日期、近 3 天公告；但逐字 diff 从第二次运行起才有。脚本须明确标注"首次基线，无 diff"，不得伪造变更内容。

## 6. 数据与产物

- 快照：`snapshots/`，每篇文档 / 费率页一份（正文文本 + 元数据 JSON）。
- 报告：`reports/okx-YYYYMMDD-HHMM.md`，同时终端打印摘要。
- 可配置项（顶部常量或简单配置）：近 N 天、代理端口、超时/重试。

## 7. 报告结构

```
# OKX 监控报告 2026-06-30 HH:MM  （首次：标注「基线建立」）
## 一、交易规则
  ### 相对基线有变化的文档（M 篇）— 标题/日期/链接 + 每篇 diff 片段
      （首次运行：列出全部文档清单作为基线，无 diff）
## 二、费率规则
  ### 是否变化 + diff 片段（首次：基线，无 diff）
## 三、上下币公告
  ### 相对基线新增 / 近 N 天 — 上币（X 条）/ 下币（Y 条）— 标题/日期/链接
```

## 8. 已知风险

- **接口变更**：`/priapi/...` 为内部接口，OKX 改版可能失效；解析失败需明确报错而非静默吞掉（no silent-wrong）。
- **OKX 反爬/限频**：需合理 UA、超时、重试；走代理；请求间加小延时。
- **section id 漂移**：动态解析，不硬编码。
- **公告时间窗翻页**：逐页抓直到 `pTime` 早于窗口起点，避免漏（且对每个 annType 都翻）。
```
