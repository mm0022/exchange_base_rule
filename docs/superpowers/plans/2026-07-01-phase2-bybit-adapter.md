# Phase 2：Bybit 适配器 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增 `BybitAdapter`，监控 Bybit 上下币公告 + 「统一交易账户」帮助文档（全树 24 篇，正文 diff），接入现有多交易所核心；费率不做。

**Architecture:** 公告用官方 V5 REST API（`api.bybit.com/v5/announcements/index`）。文档为 Next.js SSR：topic-list 页的 `__NEXT_DATA__` 给出文章树（24 篇），逐篇抓 article 页拿 `tabs[0].last_updated`(更新时间) + `tab_content`(正文)。中文靠 URL 里的 `zh-MY` 语言路径（不是请求头）。适配器实现 Phase 0 的 `ExchangeAdapter` 协议，加入 `__main__` ADAPTERS 即生效。文章仅 24 篇，全部做正文 diff，无限频问题。

**Tech Stack:** Python 3.12, uv, httpx, difflib, `re`+`json`(解析 __NEXT_DATA__), pytest, ruff。

## Global Constraints

- 所有请求走代理 `http://127.0.0.1:7890`。Bybit 中文靠 URL 语言段 `zh-MY`（`zh-CN` 不支持）。
- `DocMeta.url` / `Announcement.url` 一律绝对 URL。
- 时间戳归一为 epoch 秒：公告 `publishTime` 毫秒 `//1000`；文档 `last_updated` 是字符串 `"YYYY-MM-DD HH:MM:SS"`(UTC)，用 `datetime.strptime(...).replace(tzinfo=UTC).timestamp()` 转秒。
- 变更信号 = 文档的 `last_updated`（秒）；正文 = `tab_content`。全部 24 篇都抓正文做 diff。
- 文档范围 = 用户给的 `help-center/topic-list/unified-trading-account`（统一交易账户）整棵树，含全部子主题（5 个子主题，24 篇）。
- `fetch_fees` 返回 None（Bybit 费率本期不做）。
- no-silent-wrong：解析失败抛异常（找不到 __NEXT_DATA__ / article 为空 / tabs 为空 均 raise）。
- commit 不加 Co-Authored-By。uv / ruff。

---

### Task 1: Bybit 常量 + fixtures 抓取

**Files:**
- Modify: `src/exchange_monitor/config.py`
- Modify: `scripts/capture_fixtures.py`
- Create (运行生成): `tests/fixtures/bybit_*.{json,html}`

**Interfaces:**
- Produces: config 常量 `BYBIT_ANN_API`、`BYBIT_HELP_BASE`、`BYBIT_TOPIC`、`BYBIT_LOCALE`；4 个 fixture。

- [ ] **Step 1: config.py 末尾追加 Bybit 常量**

```python
# --- Bybit ---
BYBIT_ANN_API = "https://api.bybit.com/v5/announcements/index"
BYBIT_LOCALE = "zh-MY"                     # 中文靠 URL 语言段；zh-CN 不被支持
BYBIT_HELP_BASE = "https://www.bybit.com"  # + /{locale}/help-center/topic-list|article/{...}
BYBIT_TOPIC = "unified-trading-account"    # 统一交易账户主题（含子主题，24 篇）
BYBIT_ANN_TYPES = ["new_crypto", "delistings"]
```

- [ ] **Step 2: capture_fixtures.py 增加 Bybit 目标**

在 Binance 抓取之后追加（Bybit 公告 API 无需特殊头；文档页也不需要 lang 头，用 zh-MY 路径）：
```python
    with httpx.Client(proxy=PROXY, headers=HEADERS, timeout=20) as c:
        bybit = {
            "bybit_ann_new.json": "https://api.bybit.com/v5/announcements/index?locale=zh-MY&type=new_crypto&page=1&limit=20",
            "bybit_ann_del.json": "https://api.bybit.com/v5/announcements/index?locale=zh-MY&type=delistings&page=1&limit=20",
            "bybit_topic.html": "https://www.bybit.com/zh-MY/help-center/topic-list/unified-trading-account",
        }
        for name, url in bybit.items():
            r = c.get(url); r.raise_for_status()
            (OUT / name).write_text(r.text, encoding="utf-8")
            print(f"saved {name} ({len(r.text)} bytes)")
        # 从 topic 页取第一篇文章 url，抓其 article 页作 fixture
        import re as _re, json as _json
        th = (OUT / "bybit_topic.html").read_text(encoding="utf-8")
        nd = _json.loads(_re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', th, _re.S).group(1))
        data = nd["props"]["pageProps"]["data"]
        def _first(o):
            for a in (o.get("articles") or []): return a
            for ch in (o.get("children") or []):
                r = _first(ch)
                if r: return r
            return None
        art_url = _first(data)["url"]
        r = c.get(f"https://www.bybit.com/zh-MY/help-center/article/{art_url}")
        r.raise_for_status()
        (OUT / "bybit_article.html").write_text(r.text, encoding="utf-8")
        print(f"saved bybit_article.html ({len(r.text)} bytes) for {art_url}")
```

- [ ] **Step 3: 运行抓取**

Run: `uv run python scripts/capture_fixtures.py`
Expected: 新增 `saved bybit_ann_new.json ...` 等 4 行；`tests/fixtures/` 下出现 `bybit_ann_new.json`、`bybit_ann_del.json`、`bybit_topic.html`、`bybit_article.html`，均非空。

- [ ] **Step 4: 校验 fixture 结构**

Run:
```bash
uv run python -c "
import json,re
a=json.load(open('tests/fixtures/bybit_ann_new.json')); print('ann retCode',a['retCode'],'total',a['result']['total'],'首条',a['result']['list'][0]['title'][:20])
h=open('tests/fixtures/bybit_topic.html',encoding='utf-8').read()
d=json.loads(re.search(r'<script id=\"__NEXT_DATA__\"[^>]*>(.*?)</script>',h,re.S).group(1))
data=d['props']['pageProps']['data']
def cnt(o):
    n=len(o.get('articles') or [])
    for ch in (o.get('children') or []): n+=cnt(ch)
    return n
print('topic 文章数:',cnt(data))
ah=open('tests/fixtures/bybit_article.html',encoding='utf-8').read()
ad=json.loads(re.search(r'<script id=\"__NEXT_DATA__\"[^>]*>(.*?)</script>',ah,re.S).group(1))
t=ad['props']['pageProps']['article']['tabs'][0]
print('article last_updated:',t['last_updated'],'| tab_content 长度:',len(t['tab_content']))
"
```
Expected: `ann retCode 0 total <大数> ...`；`topic 文章数: 24`（或接近）；`article last_updated: 2026-... | tab_content 长度: >1000`。

- [ ] **Step 5: Commit**

```bash
git add src/exchange_monitor/config.py scripts/capture_fixtures.py tests/fixtures/bybit_*.json tests/fixtures/bybit_*.html
git commit -m "chore: add Bybit config constants and capture fixtures"
```

---

### Task 2: Bybit 纯解析函数

**Files:**
- Create: `src/exchange_monitor/exchanges/bybit.py`（本任务只放纯函数）
- Test: `tests/test_bybit_parse.py`

**Interfaces:**
- Produces（模块级纯函数）：
  - `parse_announcements(api_json: dict, ann_type: str) -> list[Announcement]`
  - `announcements_total(api_json: dict) -> int`
  - `extract_next_data(html: str) -> dict`（提取并解析 `__NEXT_DATA__`）
  - `collect_articles(topic_data: dict) -> list[dict]`（递归 children/articles，返回每篇 `{url,title,code?}`）
  - `parse_article(article_html: str) -> tuple[str, int, str]`（返回 `(body, update_time_秒, title)`）
  - `parse_last_updated(s: str) -> int`（`"YYYY-MM-DD HH:MM:SS"` UTC → epoch 秒）

- [ ] **Step 1: 写失败测试 `tests/test_bybit_parse.py`**

```python
import json
import pathlib

from exchange_monitor.exchanges import bybit as by

FIX = pathlib.Path(__file__).parent / "fixtures"


def _txt(name):
    return (FIX / name).read_text(encoding="utf-8")


def _json(name):
    return json.loads(_txt(name))


def test_parse_announcements_seconds_absolute_chinese():
    anns = by.parse_announcements(_json("bybit_ann_new.json"), "bybit-new-listings")
    assert anns
    a = anns[0]
    assert a.ann_type == "bybit-new-listings"
    assert a.url.startswith("http")
    assert a.ptime > 1_700_000_000  # 秒
    assert any("一" <= ch <= "鿿" for ch in a.title)


def test_announcements_total_positive():
    assert by.announcements_total(_json("bybit_ann_new.json")) > 100


def test_parse_last_updated_utc_seconds():
    ts = by.parse_last_updated("2026-01-23 09:57:02")
    # 2026-01-23 09:57:02 UTC
    assert ts == 1769162222


def test_collect_articles_from_topic():
    data = by.extract_next_data(_txt("bybit_topic.html"))["props"]["pageProps"]["data"]
    arts = by.collect_articles(data)
    assert len(arts) >= 10
    assert all(x.get("url") and x.get("title") for x in arts)


def test_parse_article_body_seconds_title():
    body, upd, title = by.parse_article(_txt("bybit_article.html"))
    assert len(body) > 200
    assert upd > 1_700_000_000
    assert isinstance(title, str) and title
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_bybit_parse.py -v`
Expected: FAIL（模块/函数缺失）

- [ ] **Step 3: 写 `exchanges/bybit.py`（纯函数部分）**

```python
"""Bybit 数据源解析 + 适配器。公告用 V5 API；文档为 Next.js SSR(__NEXT_DATA__)。中文靠 zh-MY 路径。"""
import json
import re
from datetime import UTC, datetime

from exchange_monitor.models import Announcement, DocMeta

_NEXT_DATA_RE = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)


def parse_announcements(api_json: dict, ann_type: str) -> list[Announcement]:
    lst = (api_json.get("result") or {}).get("list") or []
    out: list[Announcement] = []
    for a in lst:
        pt = a.get("publishTime") or a.get("dateTimestamp")
        if not pt:
            continue
        out.append(
            Announcement(
                title=a["title"].strip(),
                url=a["url"],
                ptime=int(pt) // 1000,
                ann_type=ann_type,
            )
        )
    return out


def announcements_total(api_json: dict) -> int:
    return int((api_json.get("result") or {}).get("total") or 0)


def extract_next_data(html: str) -> dict:
    m = _NEXT_DATA_RE.search(html)
    if not m:
        raise ValueError("Bybit: 未找到 __NEXT_DATA__，页面结构可能已变更")
    return json.loads(m.group(1))


def collect_articles(topic_data: dict) -> list[dict]:
    """递归 topic 树，收集全部文章 dict（含 url/title/code）。"""
    out: list[dict] = []

    def walk(node: dict) -> None:
        for a in (node.get("articles") or []):
            out.append(a)
        for ch in (node.get("children") or []):
            walk(ch)

    walk(topic_data)
    return out


def parse_last_updated(s: str) -> int:
    dt = datetime.strptime(s.strip(), "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
    return int(dt.timestamp())


def parse_article(article_html: str) -> tuple[str, int, str]:
    art = extract_next_data(article_html).get("props", {}).get("pageProps", {}).get("article")
    if not art:
        raise ValueError("Bybit article: article 为空（可能该语言无内容，需 zh-MY/zh-TW）")
    tabs = art.get("tabs") or []
    if not tabs:
        raise ValueError("Bybit article: 无 tabs")
    tab = tabs[0]
    body = tab.get("tab_content") or ""
    upd = parse_last_updated(tab["last_updated"]) if tab.get("last_updated") else 0
    title = (art.get("title") or "").strip()
    return body, upd, title


# 供 Task 3 适配器使用
_ = DocMeta
```

- [ ] **Step 4: 运行确认通过**

Run: `uv run pytest tests/test_bybit_parse.py -v`
Expected: 5 passed（若 `test_parse_last_updated_utc_seconds` 的期望值 `1769162222` 与实际差几秒，以实际 `parse_last_updated("2026-01-23 09:57:02")` 计算值为准修正断言——该值是纯函数确定的，用 `python -c` 核对后填正确值）。

- [ ] **Step 5: ruff + Commit**

```bash
uv run ruff check src/exchange_monitor/exchanges/bybit.py tests/test_bybit_parse.py
git add src/exchange_monitor/exchanges/bybit.py tests/test_bybit_parse.py
git commit -m "feat: add Bybit parsers (announcements, topic tree, article)"
```

---

### Task 3: BybitAdapter

**Files:**
- Modify: `src/exchange_monitor/exchanges/bybit.py`（追加 `BybitAdapter`）
- Test: `tests/test_bybit_adapter.py`

**Interfaces:**
- Consumes: 本模块纯函数、config 常量、`Fetcher`
- Produces: `BybitAdapter`，`name="Bybit"`、`snapshot_name="bybit"`，实现协议四方法。文档枚举 topic 树 + 逐篇抓 article 页（body + last_updated），正文缓存。`fetch_fees` 返回 None。

- [ ] **Step 1: 写失败测试 `tests/test_bybit_adapter.py`**

```python
import json
import pathlib

from exchange_monitor.config import Config
from exchange_monitor.exchanges.bybit import BybitAdapter

FIX = pathlib.Path(__file__).parent / "fixtures"


class FakeFetcher:
    def __init__(self):
        self.calls = 0

    def get_json(self, url, params=None, headers=None):
        self.calls += 1
        name = "bybit_ann_new.json" if params["type"] == "new_crypto" else "bybit_ann_del.json"
        return json.loads((FIX / name).read_text(encoding="utf-8"))

    def get_text(self, url, params=None, headers=None):
        self.calls += 1
        if "/topic-list/" in url:
            return (FIX / "bybit_topic.html").read_text(encoding="utf-8")
        if "/article/" in url:
            return (FIX / "bybit_article.html").read_text(encoding="utf-8")
        raise AssertionError(url)


def test_identity():
    a = BybitAdapter()
    assert a.name == "Bybit" and a.snapshot_name == "bybit"


def test_fetch_fees_none():
    assert BybitAdapter().fetch_fees(FakeFetcher(), Config()) is None


def test_fetch_docs_enumerates_topic_with_body_and_time():
    import exchange_monitor.exchanges.bybit as by
    data = by.extract_next_data((FIX / "bybit_topic.html").read_text(encoding="utf-8"))["props"]["pageProps"]["data"]
    expected = len(by.collect_articles(data))
    docs = BybitAdapter().fetch_docs(FakeFetcher(), Config())
    assert len(docs) == expected
    assert all(d.url.startswith("https://www.bybit.com/") for d in docs)
    assert all(d.update_time > 1_700_000_000 for d in docs)


def test_fetch_doc_body_cached():
    a = BybitAdapter()
    f = FakeFetcher()
    docs = a.fetch_docs(f, Config())
    n = f.calls
    body = a.fetch_doc_body(f, Config(), docs[0])
    assert isinstance(body, str) and len(body) > 200
    assert f.calls == n  # 命中缓存


def test_fetch_announcements_window_split():
    a = BybitAdapter()
    new, delist = a.fetch_announcements(FakeFetcher(), Config(), now_ts=0)
    assert new and all(x.ann_type == "bybit-new-listings" for x in new)
    assert all(x.ann_type == "bybit-delistings" for x in delist)
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_bybit_adapter.py -v`
Expected: FAIL（`BybitAdapter` 不存在）

- [ ] **Step 3: 追加 `BybitAdapter` 到 `exchanges/bybit.py`**

```python
from exchange_monitor.config import (
    BYBIT_ANN_API,
    BYBIT_ANN_TYPES,
    BYBIT_HELP_BASE,
    BYBIT_LOCALE,
    BYBIT_TOPIC,
)

_LIMIT = 20


class BybitAdapter:
    name = "Bybit"
    snapshot_name = "bybit"

    def __init__(self):
        self._body_cache: dict[str, str] = {}

    def _article_url(self, art_url: str) -> str:
        return f"{BYBIT_HELP_BASE}/{BYBIT_LOCALE}/help-center/article/{art_url}"

    def fetch_docs(self, fetcher, config) -> list[DocMeta]:
        topic_html = fetcher.get_text(
            f"{BYBIT_HELP_BASE}/{BYBIT_LOCALE}/help-center/topic-list/{BYBIT_TOPIC}"
        )
        data = extract_next_data(topic_html)["props"]["pageProps"]["data"]
        articles = collect_articles(data)
        self._body_cache = {}
        docs: list[DocMeta] = []
        for a in articles:
            art_url = a["url"]
            html = fetcher.get_text(self._article_url(art_url))
            body, upd, title = parse_article(html)
            self._body_cache[art_url] = body
            docs.append(
                DocMeta(
                    slug=art_url,
                    title=title or (a.get("title") or "").strip(),
                    url=self._article_url(art_url),
                    update_time=upd,
                    publish_time=upd,
                )
            )
        return docs

    def fetch_doc_body(self, fetcher, config, doc: DocMeta) -> str:
        if doc.slug in self._body_cache:
            return self._body_cache[doc.slug]
        return parse_article(fetcher.get_text(self._article_url(doc.slug)))[0]

    def _collect_ann(self, fetcher, config, now_ts, ann_type, label):
        cutoff = now_ts - config.window_days * 86400
        out: list[Announcement] = []
        page = 1
        while True:
            data = fetcher.get_json(
                BYBIT_ANN_API,
                {"locale": BYBIT_LOCALE, "type": ann_type, "page": page, "limit": _LIMIT},
            )
            anns = parse_announcements(data, label)
            if not anns:
                break
            out.extend([a for a in anns if a.ptime >= cutoff])
            total = announcements_total(data)
            if anns[-1].ptime < cutoff or page * _LIMIT >= total:
                break
            page += 1
        return out

    def fetch_announcements(
        self, fetcher, config, now_ts: int
    ) -> tuple[list[Announcement], list[Announcement]]:
        new = self._collect_ann(fetcher, config, now_ts, "new_crypto", "bybit-new-listings")
        delist = self._collect_ann(fetcher, config, now_ts, "delistings", "bybit-delistings")
        return new, delist

    def fetch_fees(self, fetcher, config) -> str | None:
        return None
```
删除文件底部 `_ = DocMeta` 占位。

- [ ] **Step 4: 运行确认通过 + 全套**

Run: `uv run pytest tests/test_bybit_adapter.py -v && uv run pytest -q`
Expected: adapter 测试全过；全套（OKX+Binance+Bybit）全绿。

- [ ] **Step 5: ruff + Commit**

```bash
uv run ruff check src/exchange_monitor/exchanges/bybit.py tests/test_bybit_adapter.py
git add src/exchange_monitor/exchanges/bybit.py tests/test_bybit_adapter.py
git commit -m "feat: add BybitAdapter (announcements + topic-tree docs with body diff)"
```

---

### Task 4: 接入 __main__ + 端到端

**Files:**
- Modify: `src/exchange_monitor/__main__.py`

**Interfaces:**
- Produces: `ADAPTERS = [OkxAdapter(), BinanceAdapter(), BybitAdapter()]`；一次运行监控三家。

- [ ] **Step 1: 注册 BybitAdapter**

```python
from exchange_monitor.exchanges.bybit import BybitAdapter
# ...
ADAPTERS = [OkxAdapter(), BinanceAdapter(), BybitAdapter()]
```

- [ ] **Step 2: 全套测试 + ruff**

Run: `uv run pytest -q && uv run ruff check src tests`
Expected: 全绿；ruff 干净。

- [ ] **Step 3: 端到端（需代理；Bybit 24 篇 + Binance 145 篇，总计约 10 分钟）**

```bash
source ~/.zshrc 2>/dev/null; rm -f snapshots/bybit.json
uv run python -m exchange_monitor
```
Expected: 报告写入 `reports/exchanges-*.md`；摘要含 `[OKX]`、`[Binance]`、`[Bybit] 基线: 文档 ~24 篇 / 上币 X 下币 Y`；`snapshots/bybit.json` 生成含 ~24 篇（都有正文）。`cat reports/exchanges-*.md` 确认 Bybit 分节（交易规则清单 + 上下币公告；无费率节）。

- [ ] **Step 4: 第二次运行**

Run: `uv run python -m exchange_monitor`
Expected: 退出码 0；`[Bybit] 文档变更 0 篇 / 费率未监控 / 上币 X 下币 Y`（两次间无更新则 0）。

- [ ] **Step 5: Commit**

```bash
git add src/exchange_monitor/__main__.py
git commit -m "feat: register BybitAdapter — three exchanges live"
```

---

## Self-Review 检查

- **Spec 覆盖**：Bybit 公告（Task 2/3）、文档全树枚举+子主题（Task 3 fetch_docs 递归 collect_articles）、正文 diff（article tab_content + 核心 build_doc_changes）、中文 zh-MY 路径（config + 各 URL）、费率不做（fetch_fees→None）、接入运行（Task 4）均覆盖。
- **类型一致**：`parse_article -> (body, update_time_秒, title)` 定义与使用一致；`DocMeta(slug=art_url, ...)`、`Announcement(title,url,ptime秒,ann_type)` 与 Phase 0 模型一致；适配器方法签名匹配 `ExchangeAdapter`（`fetch_fees->str|None` 返回 None）；`_body_cache` 键用 `art_url`(=slug)。
- **占位符**：无 TBD/TODO；每步含真实代码/命令。`parse_last_updated` 断言值实现期用 `python -c` 核对。
- **无限频风险**：Bybit 文档仅 24 篇、逐篇抓 article 页(~24 次)，远小于 Binance；公告用官方 API 无鉴权无限频。沿用每交易所隔离（Phase 1 已加）——若 Bybit 抓取失败不影响 OKX/Binance。

## 已知取舍
- Bybit 文档正文是 HTML(`tab_content`)，diff 为 HTML 文本行 diff（可读性略逊纯文本，但能准确反映变更；与 OKX/Binance 的正文 diff 一致对待）。
- 范围限定 `unified-trading-account` 主题（用户所指 URL）。Bybit 帮助中心有 22 个 category，如需更多后续再加（BYBIT_TOPIC 可扩为列表）。
