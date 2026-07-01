# Phase 1：Binance 适配器 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增 `BinanceAdapter`（币安），监控上下币公告 + 交易规则文档（全树枚举 + 正文 diff），接入现有多交易所核心；费率不做。

**Architecture:** Binance 用 CMS bapi 接口（`list/query` 列表、`detail/query` 详情），中文靠请求头 `lang: zh-CN`。文档为 3 层树，逐叶分页枚举全部文章；`lastUpdateTime` 只在 detail 里，故 `fetch_docs` 逐篇抓 detail（拿 update_time + 正文），把正文缓存到适配器实例供 `fetch_doc_body` 复用。适配器实现 Phase 0 定义的 `ExchangeAdapter` 协议，加入 `__main__` 的 ADAPTERS 即生效。

**Tech Stack:** Python 3.12, uv, httpx, difflib, pytest, ruff（沿用现有核心）。

## Global Constraints

- 所有请求走代理 `http://127.0.0.1:7890`；Binance 中文靠请求头 `lang: zh-CN`（不是 URL 参数）。
- `pageSize` 用 20（更大值 Binance 返回空/异常）。
- `DocMeta.url` / `Announcement.url` 一律绝对 URL。
- 时间戳归一为 epoch 秒（Binance `releaseDate` / `lastUpdateTime` 均为毫秒，`//1000`）。
- 变更信号 = `lastUpdateTime`（秒）；来自 detail，故文档枚举必须逐篇抓 detail。
- 文档范围 = 用户给的 `support/faq/list/4`（catalogId=4「数字货币衍生品」）整棵树，含全部子页面。
- no-silent-wrong：解析/抓取失败抛异常；叶子分页未取满 `total` 抛"截断"错。
- `fetch_fees` 返回 `None`（Binance 费率本期不做）。
- commit 不加 Co-Authored-By。uv / ruff。

---

### Task 1: Binance 常量 + fixtures 抓取

**Files:**
- Modify: `src/exchange_monitor/config.py`
- Modify: `scripts/capture_fixtures.py`
- Create (运行生成): `tests/fixtures/binance_*.json`

**Interfaces:**
- Produces: config 常量 `BINANCE_BASE`、`BINANCE_CMS_LIST`、`BINANCE_CMS_DETAIL`、`BINANCE_ANN_NEW_CATALOG=48`、`BINANCE_ANN_DEL_CATALOG=161`、`BINANCE_FAQ_CATALOG=4`、`BINANCE_LANG` = `{"lang": "zh-CN"}`；6 个 fixture 文件。

- [ ] **Step 1: 在 `config.py` 末尾追加 Binance 常量**

```python
# --- Binance ---
BINANCE_BASE = "https://www.binance.com"
BINANCE_CMS_LIST = f"{BINANCE_BASE}/bapi/composite/v1/public/cms/article/list/query"
BINANCE_CMS_DETAIL = f"{BINANCE_BASE}/bapi/composite/v1/public/cms/article/detail/query"
BINANCE_ANN_NEW_CATALOG = 48   # 新币上线
BINANCE_ANN_DEL_CATALOG = 161  # 下架讯息
BINANCE_FAQ_CATALOG = 4        # 数字货币衍生品（对应 support/faq/list/4）
BINANCE_LANG = {"lang": "zh-CN"}
```

- [ ] **Step 2: 给 `scripts/capture_fixtures.py` 增加 Binance 目标**

在该脚本里为 Binance 增加抓取（用 `lang: zh-CN` 头）。在现有 `TARGETS` 之后追加一段（保持它原有 OKX 抓取不变）：

```python
BINANCE_HEADERS = {**HEADERS, "lang": "zh-CN"}
BINANCE_TARGETS = {
    "binance_ann_new.json": "https://www.binance.com/bapi/composite/v1/public/cms/article/list/query?type=1&catalogId=48&pageNo=1&pageSize=20",
    "binance_ann_del.json": "https://www.binance.com/bapi/composite/v1/public/cms/article/list/query?type=1&catalogId=161&pageNo=1&pageSize=20",
    "binance_faq_tree.json": "https://www.binance.com/bapi/composite/v1/public/cms/article/list/query?type=2&catalogId=4&pageNo=1&pageSize=20",
    "binance_faq_leaf36_p2.json": "https://www.binance.com/bapi/composite/v1/public/cms/article/list/query?type=2&catalogId=36&pageNo=2&pageSize=20",
    "binance_faq_leaf37_p2.json": "https://www.binance.com/bapi/composite/v1/public/cms/article/list/query?type=2&catalogId=37&pageNo=2&pageSize=20",
}
```

并在 `main()` 里，OKX 抓取循环之后，追加：

```python
    with httpx.Client(proxy=PROXY, headers=BINANCE_HEADERS, timeout=20) as c:
        for name, url in BINANCE_TARGETS.items():
            r = c.get(url); r.raise_for_status()
            (OUT / name).write_text(r.text, encoding="utf-8")
            print(f"saved {name} ({len(r.text)} bytes)")
        # 取 faq_tree 里第一篇文章的 code，抓一篇 detail 作 fixture
        import json as _json
        tree = _json.loads((OUT / "binance_faq_tree.json").read_text(encoding="utf-8"))
        def _first_code(o):
            if isinstance(o, dict):
                for a in (o.get("articles") or []):
                    return a.get("code")
                for s in (o.get("catalogs") or []):
                    r = _first_code(s)
                    if r:
                        return r
            return None
        code = _first_code(tree["data"]["catalogs"][0])
        r = c.get(f"https://www.binance.com/bapi/composite/v1/public/cms/article/detail/query?articleCode={code}")
        r.raise_for_status()
        (OUT / "binance_detail.json").write_text(r.text, encoding="utf-8")
        print(f"saved binance_detail.json ({len(r.text)} bytes) for code {code}")
```

- [ ] **Step 3: 运行抓取**

Run: `uv run python scripts/capture_fixtures.py`
Expected: 打印新增 `saved binance_ann_new.json ...` 等 6 行；`tests/fixtures/` 下出现 `binance_ann_new.json`、`binance_ann_del.json`、`binance_faq_tree.json`、`binance_faq_leaf36_p2.json`、`binance_faq_leaf37_p2.json`、`binance_detail.json`，均非空。

- [ ] **Step 4: 校验 fixture 结构**

Run:
```bash
uv run python -c "
import json
t=json.load(open('tests/fixtures/binance_faq_tree.json')); print('tree code', t['code'], 'catalogs', len(t['data']['catalogs']))
d=json.load(open('tests/fixtures/binance_detail.json')); print('detail has body', bool(d['data'].get('body')), 'lastUpdateTime', d['data'].get('lastUpdateTime'))
a=json.load(open('tests/fixtures/binance_ann_new.json')); print('ann articles', len(a['data']['catalogs'][0]['articles']))
"
```
Expected: `tree code 000000 catalogs 1`；`detail has body True lastUpdateTime <数字>`；`ann articles 20`（或接近）。

- [ ] **Step 5: Commit**

```bash
git add src/exchange_monitor/config.py scripts/capture_fixtures.py tests/fixtures/binance_*.json
git commit -m "chore: add Binance config constants and capture fixtures"
```

---

### Task 2: Binance 纯解析函数

**Files:**
- Create: `src/exchange_monitor/exchanges/binance.py`（本任务只放纯函数，Task 3 加适配器类）
- Test: `tests/test_binance_parse.py`

**Interfaces:**
- Consumes: fixtures、`models.Announcement`/`DocMeta`、config 常量
- Produces（模块级纯函数）：
  - `parse_announcements(api_json: dict, ann_type: str) -> list[Announcement]`
  - `announcements_total(api_json: dict) -> int`
  - `collect_leaves(tree_json: dict) -> list[dict]`（返回叶节点，每个是原始 catalog dict，含 `catalogId`/`total`/`articles`）
  - `parse_detail(api_json: dict) -> tuple[str, int, str]`（返回 `(body, update_time_秒, title)`）

> **分页机制（实测）**：Binance FAQ 的 `pageNo` 是**全树全局分页**——`catalogId=4&pageNo=N` 返回整棵树、每个叶子的第 N 页文章（catalogId 参数被忽略，`catalogId=36&pageNo=2` 与 `catalogId=4&pageNo=2` 完全相同）。因此枚举 = 用 `catalogId=4&pageNo=1,2,…` 逐页翻，跨页按 `code` 累积，直到某页 0 篇。不做按叶 catalogId 单独翻页。

- [ ] **Step 1: 写失败测试 `tests/test_binance_parse.py`**

```python
import json
import pathlib

from exchange_monitor.exchanges import binance as bn

FIX = pathlib.Path(__file__).parent / "fixtures"


def _j(name):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


def test_parse_announcements_absolute_url_and_seconds():
    anns = bn.parse_announcements(_j("binance_ann_new.json"), "binance-new-listings")
    assert anns
    a = anns[0]
    assert a.ann_type == "binance-new-listings"
    assert a.url.startswith("https://www.binance.com/")
    assert a.ptime > 1_700_000_000  # 秒（不是毫秒）
    assert any("一" <= ch <= "鿿" for ch in a.title)  # 中文


def test_announcements_total_positive():
    assert bn.announcements_total(_j("binance_ann_new.json")) > 100


def test_collect_leaves_have_catalogid_and_total():
    leaves = bn.collect_leaves(_j("binance_faq_tree.json"))
    assert len(leaves) >= 10
    assert all("catalogId" in lf for lf in leaves)
    # 至少有叶子 total>20（需要翻页）
    assert any((lf.get("total") or 0) > 20 for lf in leaves)


def test_tree_p2_is_global_page():
    # p2 是全树第2页：只含有第2页内容的叶（叶36=5, 叶37=18）
    leaves = bn.collect_leaves(_j("binance_faq_tree_p2.json"))
    counts = {lf.get("catalogId"): len(lf.get("articles") or []) for lf in leaves}
    assert counts.get(36) == 5 and counts.get(37) == 18


def test_parse_detail_returns_body_seconds_title():
    body, upd, title = bn.parse_detail(_j("binance_detail.json"))
    assert isinstance(body, str) and len(body) > 50
    assert upd > 1_700_000_000  # 秒
    assert isinstance(title, str) and title
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_binance_parse.py -v`
Expected: FAIL（模块/函数缺失）

- [ ] **Step 3: 写 `exchanges/binance.py`（纯函数部分）**

```python
"""Binance 数据源解析 + 适配器。中文靠请求头 lang: zh-CN。"""
from exchange_monitor.config import BINANCE_BASE
from exchange_monitor.models import Announcement, DocMeta


def _catalogs(api_json: dict) -> list:
    data = api_json.get("data") or {}
    return data.get("catalogs") or []


def parse_announcements(api_json: dict, ann_type: str) -> list[Announcement]:
    cats = _catalogs(api_json)
    if not cats:
        return []
    arts = cats[0].get("articles") or []
    out: list[Announcement] = []
    for a in arts:
        out.append(
            Announcement(
                title=a["title"].strip(),
                url=f"{BINANCE_BASE}/zh-CN/support/announcement/{a['code']}",
                ptime=int(a["releaseDate"]) // 1000,
                ann_type=ann_type,
            )
        )
    return out


def announcements_total(api_json: dict) -> int:
    cats = _catalogs(api_json)
    if not cats:
        return 0
    return int(cats[0].get("total") or 0)


def collect_leaves(tree_json: dict) -> list[dict]:
    """返回全部叶节点（无 subcatalogs 的 catalog dict）。"""
    leaves: list[dict] = []

    def walk(node: dict) -> None:
        subs = node.get("catalogs") or []
        if not subs:
            leaves.append(node)
            return
        for s in subs:
            walk(s)

    for c in _catalogs(tree_json):
        walk(c)
    return leaves


def parse_detail(api_json: dict) -> tuple[str, int, str]:
    data = api_json.get("data")
    if not data or "body" not in data:
        raise ValueError("Binance detail: 缺少 data.body，接口可能已变更")
    body = data["body"]
    upd = int(data.get("lastUpdateTime") or data.get("publishDate") or 0) // 1000
    title = (data.get("title") or "").strip()
    return body, upd, title


# DocMeta 供 Task 3 适配器构造使用（此处仅 import 供类型对齐）
_ = DocMeta
```

- [ ] **Step 4: 运行确认通过**

Run: `uv run pytest tests/test_binance_parse.py -v`
Expected: 5 passed

- [ ] **Step 5: ruff + Commit**

```bash
uv run ruff check src/exchange_monitor/exchanges/binance.py tests/test_binance_parse.py
git add src/exchange_monitor/exchanges/binance.py tests/test_binance_parse.py
git commit -m "feat: add Binance parsers (announcements, doc tree, detail)"
```

---

### Task 3: BinanceAdapter

**Files:**
- Modify: `src/exchange_monitor/exchanges/binance.py`（追加 `BinanceAdapter` 类）
- Test: `tests/test_binance_adapter.py`

**Interfaces:**
- Consumes: 本模块纯函数、config 常量、`Fetcher`（鸭子类型）
- Produces: `BinanceAdapter`，`name="Binance"`、`snapshot_name="binance"`，实现协议四方法。文档全树枚举（逐叶分页）+ 逐篇 detail（update_time + 正文缓存）。`fetch_fees` 返回 None。

- [ ] **Step 1: 写失败测试 `tests/test_binance_adapter.py`（FakeFetcher 按 URL+params 供 fixture）**

```python
import json
import pathlib

from exchange_monitor.config import Config
from exchange_monitor.exchanges.binance import BinanceAdapter

FIX = pathlib.Path(__file__).parent / "fixtures"


def _j(name):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


class FakeFetcher:
    """按 (type, catalogId, pageNo) 返回 fixture；detail 对任意 code 返回同一详情。"""

    def get_json(self, url, params=None, headers=None):
        if "article/detail/query" in url:
            return _j("binance_detail.json")
        if "article/list/query" in url:
            t, page = params["type"], params.get("pageNo", 1)
            if t == 1:
                return _j("binance_ann_new.json" if params["catalogId"] == 48 else "binance_ann_del.json")
            # type == 2 文档：全树全局分页
            if page == 1:
                return _j("binance_faq_tree.json")
            if page == 2:
                return _j("binance_faq_tree_p2.json")
            return {"code": "000000", "data": {"catalogs": []}}  # page>=3 无更多
        raise AssertionError(url)

    def get_text(self, url, params=None, headers=None):
        raise AssertionError("Binance 不用 get_text")


def test_identity():
    a = BinanceAdapter()
    assert a.name == "Binance" and a.snapshot_name == "binance"


def test_fetch_fees_none():
    assert BinanceAdapter().fetch_fees(FakeFetcher(), Config()) is None


def test_fetch_docs_enumerates_full_tree_with_update_time():
    docs = BinanceAdapter().fetch_docs(FakeFetcher(), Config())
    # 全树文章数 = 各叶 total 之和（fixture 数据）
    total_expected = sum((lf.get("total") or 0) for lf in __import__(
        "exchange_monitor.exchanges.binance", fromlist=["collect_leaves"]
    ).collect_leaves(_j("binance_faq_tree.json")))
    assert len(docs) == total_expected
    assert all(d.url.startswith("https://www.binance.com/") for d in docs)
    assert all(d.update_time > 1_700_000_000 for d in docs)  # 来自 detail 的 lastUpdateTime(秒)


def test_fetch_doc_body_uses_cache():
    a = BinanceAdapter()
    docs = a.fetch_docs(FakeFetcher(), Config())
    # fetch_docs 已缓存正文；fetch_doc_body 直接返回，不再请求
    body = a.fetch_doc_body(FakeFetcher(), Config(), docs[0])
    assert isinstance(body, str) and len(body) > 50


def test_fetch_announcements_window_and_split():
    a = BinanceAdapter()
    new, delist = a.fetch_announcements(FakeFetcher(), Config(), now_ts=99_999_999_999)
    # now_ts 极大 → cutoff 极大 → 窗口内为空（验证过滤生效，且不报错）
    assert new == [] and delist == []
    # now_ts 极小 → cutoff 极小 → 全部纳入
    a2 = BinanceAdapter()
    new2, del2 = a2.fetch_announcements(FakeFetcher(), Config(), now_ts=0)
    assert len(new2) > 0
    assert all(x.ann_type == "binance-new-listings" for x in new2)
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_binance_adapter.py -v`
Expected: FAIL（`BinanceAdapter` 不存在）

- [ ] **Step 3: 在 `exchanges/binance.py` 追加 `BinanceAdapter`**

```python
from exchange_monitor.config import (
    BINANCE_ANN_DEL_CATALOG,
    BINANCE_ANN_NEW_CATALOG,
    BINANCE_CMS_DETAIL,
    BINANCE_CMS_LIST,
    BINANCE_FAQ_CATALOG,
    BINANCE_LANG,
)

_PAGE_SIZE = 20
_MAX_PAGES = 50  # 分页安全上限（最大叶 total/20 远小于此）


class BinanceAdapter:
    name = "Binance"
    snapshot_name = "binance"

    def __init__(self):
        self._body_cache: dict[str, str] = {}

    def fetch_docs(self, fetcher, config) -> list[DocMeta]:
        # 1) 全树全局分页枚举文章（catalogId=4&pageNo=1,2,… 跨页按 code 累积）
        by_code: dict[str, dict] = {}
        leaf_total: dict[int, int] = {}
        page = 1
        while True:
            tree = fetcher.get_json(
                BINANCE_CMS_LIST,
                {"type": 2, "catalogId": BINANCE_FAQ_CATALOG, "pageNo": page, "pageSize": _PAGE_SIZE},
                headers=BINANCE_LANG,
            )
            leaves = collect_leaves(tree)
            page_count = 0
            for leaf in leaves:
                if page == 1 and leaf.get("catalogId") is not None:
                    leaf_total[leaf["catalogId"]] = int(leaf.get("total") or 0)
                for a in (leaf.get("articles") or []):
                    by_code[a["code"]] = a
                    page_count += 1
            if page_count == 0:
                break
            page += 1
            if page > _MAX_PAGES:
                raise ValueError(f"Binance 文档分页超过 {_MAX_PAGES} 页，疑似异常")
        expected = sum(leaf_total.values())
        if expected and len(by_code) < expected:
            raise ValueError(f"Binance 文档截断: 取到 {len(by_code)}/{expected}")
        # 2) 逐篇抓 detail（update_time + 正文），缓存正文
        self._body_cache = {}
        docs: list[DocMeta] = []
        for code, a in by_code.items():
            det = fetcher.get_json(
                BINANCE_CMS_DETAIL, {"articleCode": code}, headers=BINANCE_LANG
            )
            body, upd, title = parse_detail(det)
            self._body_cache[code] = body
            docs.append(
                DocMeta(
                    slug=code,
                    title=title or a.get("title", "").strip(),
                    url=f"{BINANCE_BASE}/zh-CN/support/faq/{code}",
                    update_time=upd,
                    publish_time=int(a.get("releaseDate") or 0) // 1000,
                )
            )
        return docs

    def fetch_doc_body(self, fetcher, config, doc: DocMeta) -> str:
        if doc.slug in self._body_cache:
            return self._body_cache[doc.slug]
        det = fetcher.get_json(
            BINANCE_CMS_DETAIL, {"articleCode": doc.slug}, headers=BINANCE_LANG
        )
        return parse_detail(det)[0]

    def _collect_ann(self, fetcher, config, now_ts, catalog, ann_type):
        cutoff = now_ts - config.window_days * 86400
        out: list[Announcement] = []
        page = 1
        while True:
            data = fetcher.get_json(
                BINANCE_CMS_LIST,
                {"type": 1, "catalogId": catalog, "pageNo": page, "pageSize": _PAGE_SIZE},
                headers=BINANCE_LANG,
            )
            anns = parse_announcements(data, ann_type)
            if not anns:
                break
            out.extend([a for a in anns if a.ptime >= cutoff])
            if anns[-1].ptime < cutoff or page * _PAGE_SIZE >= announcements_total(data):
                break
            page += 1
        return out

    def fetch_announcements(
        self, fetcher, config, now_ts: int
    ) -> tuple[list[Announcement], list[Announcement]]:
        new = self._collect_ann(
            fetcher, config, now_ts, BINANCE_ANN_NEW_CATALOG, "binance-new-listings"
        )
        delist = self._collect_ann(
            fetcher, config, now_ts, BINANCE_ANN_DEL_CATALOG, "binance-delistings"
        )
        return new, delist

    def fetch_fees(self, fetcher, config) -> str | None:
        return None
```

删除文件底部占位的 `_ = DocMeta`（DocMeta 现已被适配器使用）。

- [ ] **Step 4: 运行确认通过 + 全套**

Run: `uv run pytest tests/test_binance_adapter.py -v && uv run pytest -q`
Expected: adapter 测试全过；全套（含 OKX）仍全绿。

- [ ] **Step 5: ruff + Commit**

```bash
uv run ruff check src/exchange_monitor/exchanges/binance.py tests/test_binance_adapter.py
git add src/exchange_monitor/exchanges/binance.py tests/test_binance_adapter.py
git commit -m "feat: add BinanceAdapter (announcements + full-tree docs with body diff)"
```

---

### Task 4: 接入 __main__ + 端到端

**Files:**
- Modify: `src/exchange_monitor/__main__.py`

**Interfaces:**
- Consumes: `BinanceAdapter`
- Produces: `ADAPTERS = [OkxAdapter(), BinanceAdapter()]`；一次运行同时监控 OKX + Binance，合并报告 + 合并 Slack。

- [ ] **Step 1: 在 `__main__.py` 注册 BinanceAdapter**

修改 import 与 ADAPTERS：
```python
from exchange_monitor.exchanges.binance import BinanceAdapter
from exchange_monitor.exchanges.okx import OkxAdapter

ADAPTERS = [OkxAdapter(), BinanceAdapter()]
```
（其余逻辑不变。）

- [ ] **Step 2: 全套测试 + ruff**

Run: `uv run pytest -q && uv run ruff check src tests`
Expected: 全绿；ruff 干净。

- [ ] **Step 3: 端到端——首次基线（需代理；Binance 文档逐篇抓 detail，较慢，约数分钟）**

```bash
rm -f snapshots/binance.json
uv run python -m exchange_monitor
```
Expected: 打印 `报告已写入: reports/exchanges-...md`；摘要含 `[OKX] ...` 与 `[Binance] 基线: 文档 N 篇 ...`；`snapshots/binance.json` 生成、`docs` 含全树文章（约 150+ 篇）。用 `cat reports/exchanges-*.md` 确认报告含 Binance 分节（交易规则清单 + 上下币公告；无费率节）。

- [ ] **Step 4: 端到端——第二次（无变化不写报告 / 有变化给 diff）**

Run: `uv run python -m exchange_monitor`
Expected: 退出码 0；`[Binance] 文档变更 0 篇 / 费率未监控 / 上币 X 下币 Y`（两次间隔无更新则 0）。

- [ ] **Step 5: Commit**

```bash
git add src/exchange_monitor/__main__.py
git commit -m "feat: register BinanceAdapter in the run"
```

---

## Self-Review 检查

- **Spec 覆盖**：Binance 公告（Task 2 parse + Task 3 fetch_announcements）、文档全树枚举+子页面（Task 3 fetch_docs 逐叶分页）、正文 diff（detail body + 核心 build_doc_changes）、中文 `lang` 头（config + 各请求）、费率不做（fetch_fees→None）、接入运行（Task 4）均覆盖。
- **类型一致**：`parse_detail -> (body, update_time_秒, title)` 在 Task 2 定义、Task 3 使用一致；`DocMeta(slug, title, url, update_time, publish_time)` 与 Phase 0 模型一致；`Announcement(title, url, ptime, ann_type)` 一致；适配器方法签名匹配 Phase 0 `ExchangeAdapter` 协议（`fetch_fees -> str | None` 返回 None）。
- **占位符**：无 TBD/TODO；每步含真实代码/命令。
- **变更信号一致性**：Binance `update_time`=`lastUpdateTime`(秒)，来自 detail；`fetch_docs` 逐篇抓 detail 并缓存正文，`fetch_doc_body` 复用缓存，核心 `build_doc_changes` 用 `update_time` 判变——与 Phase 0 语义一致。

## 已知取舍
- **每次运行 Binance 文档需逐篇抓 detail**（因 `lastUpdateTime` 只在 detail），约 150+ 请求、耗时数分钟；这是可靠检测正文更新的代价。可接受（监控非高频）。首次基线最慢。
- Binance FAQ 文章 URL 用 `…/zh-CN/support/faq/{code}` 拼接（展示用）；若个别 code 的规范路径不同不影响 diff（diff 只看 body）。
