# Phase 0：多交易所核心泛化重构 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 OKX 专有的 `run()` 泛化为"通用核心 + 交易所适配器"，OKX 改造成第一个适配器，行为不变、可扩展到 Binance/Bybit。

**Architecture:** 引入 `ExchangeAdapter` 协议（每家实现 fetch_docs / fetch_doc_body / fetch_announcements / fetch_fees）。核心 `run(config, fetcher, now_ts, adapters)` 遍历适配器，每家独立读写 `snapshots/{name}.json`、算 diff，聚合成 `RunResult{generated_at, exchanges:[ExchangeResult]}`。报告/Slack 按交易所分节。

**Tech Stack:** Python 3.12, uv, httpx, selectolax, difflib, pytest, ruff。

## Global Constraints

- 包名由 `okx_monitor` 重命名为 `exchange_monitor`（监控多家，旧名误导）。
- 所有 OKX 请求走代理 `http://127.0.0.1:7890`；OKX 中文靠 `Accept-Language: zh-CN`。
- no-silent-wrong：解析/抓取失败必须抛异常，不静默返回空。
- 适配器返回的 `DocMeta.url` / `Announcement.url` 一律为**绝对 URL**（报告/Slack 不再拼接站点前缀）。
- 变更检测：`update_time`（秒）为权威信号；变化则重抓正文给 diff。
- 行为不变：重构后 OKX 端到端行为与现状一致，测试全绿（按新结构调整）。
- commit 不加 Co-Authored-By。uv / ruff。

---

### Task 1: 包重命名 okx_monitor → exchange_monitor

**Files:**
- Rename dir: `src/okx_monitor/` → `src/exchange_monitor/`
- Modify: 所有 `src/**/*.py`、`tests/**/*.py` 中的 `okx_monitor` 导入；`pyproject.toml`；`scripts/capture_fixtures.py`

**Interfaces:**
- Produces: 包 `exchange_monitor`，`python -m exchange_monitor` 可运行。

- [ ] **Step 1: 用 git mv 重命名包目录**

```bash
cd /Users/mac/dev/exchange_base_rule
git mv src/okx_monitor src/exchange_monitor
```

- [ ] **Step 2: 全局替换标识符 okx_monitor → exchange_monitor**

```bash
grep -rl 'okx_monitor' src tests pyproject.toml scripts | while read f; do
  sed -i '' 's/okx_monitor/exchange_monitor/g' "$f"
done
grep -rn 'okx_monitor' src tests pyproject.toml scripts || echo "✓ 无残留 okx_monitor"
```
（注意：仅替换标识符 `okx_monitor`；OKX 的 URL 常量 `okx.com`、快照文件名 `okx.json`、显示名 "OKX" 不受影响，因为它们不含下划线形式。）

- [ ] **Step 3: 运行全套测试确认重命名无破坏**

Run: `uv run pytest -q`
Expected: `17 passed, 1 deselected`（live 测试仍 deselected）

- [ ] **Step 4: 确认 CLI 模块入口可用**

Run: `uv run python -c "import exchange_monitor.__main__; print('ok')"`
Expected: 打印 `ok`

- [ ] **Step 5: ruff + Commit**

```bash
uv run ruff check src tests
git add -A
git commit -m "refactor: rename package okx_monitor -> exchange_monitor"
```

---

### Task 2: Fetcher 支持按调用传自定义 header

**Files:**
- Modify: `src/exchange_monitor/fetcher.py`
- Test: `tests/test_fetcher_headers.py`

**Interfaces:**
- Consumes: `Config`
- Produces: `Fetcher.get_json(url, params=None, headers=None)`、`get_text(url, params=None, headers=None)`、`post_json(url, payload, headers=None)`。`headers` 合并覆盖到默认头之上。

- [ ] **Step 1: 写失败测试 `tests/test_fetcher_headers.py`**

```python
from exchange_monitor.config import Config
from exchange_monitor.fetcher import Fetcher


def test_merge_headers_overrides_defaults():
    f = Fetcher(Config())
    merged = f._merge_headers({"lang": "zh-CN"})
    assert merged["lang"] == "zh-CN"
    assert merged["User-Agent"]  # 默认头仍在
    assert merged["Accept-Language"] == "zh-CN,zh"


def test_merge_headers_none_returns_defaults():
    f = Fetcher(Config())
    merged = f._merge_headers(None)
    assert "User-Agent" in merged and "Accept-Language" in merged
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_fetcher_headers.py -v`
Expected: FAIL（`_merge_headers` 不存在）

- [ ] **Step 3: 修改 `fetcher.py`**

将 `__init__` 中固定 headers 改为保存默认头字典，并加 `_merge_headers`；`_get`/`post_json` 接受并传入 headers。完整新文件：

```python
import time

import httpx

from exchange_monitor.config import Config


class Fetcher:
    def __init__(self, config: Config):
        self.cfg = config
        self._default_headers = {
            "User-Agent": config.user_agent,
            "Accept-Language": config.accept_language,
        }
        self._client = httpx.Client(proxy=config.proxy, timeout=config.timeout)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self._client.close()

    def _merge_headers(self, headers: dict | None) -> dict:
        merged = dict(self._default_headers)
        if headers:
            merged.update(headers)
        return merged

    def _get(self, url: str, params: dict | None, headers: dict | None) -> httpx.Response:
        last: Exception | None = None
        for attempt in range(self.cfg.retries):
            try:
                r = self._client.get(url, params=params, headers=self._merge_headers(headers))
                r.raise_for_status()
                time.sleep(self.cfg.request_delay)
                return r
            except httpx.HTTPError as e:
                last = e
                time.sleep(1.0 * (attempt + 1))
        raise RuntimeError(f"请求失败（重试{self.cfg.retries}次）: {url} -> {last}")

    def get_json(self, url: str, params: dict | None = None, headers: dict | None = None) -> dict:
        return self._get(url, params, headers).json()

    def get_text(self, url: str, params: dict | None = None, headers: dict | None = None) -> str:
        return self._get(url, params, headers).text

    def post_json(self, url: str, payload: dict, headers: dict | None = None) -> dict:
        last: Exception | None = None
        for attempt in range(self.cfg.retries):
            try:
                r = self._client.post(url, json=payload, headers=self._merge_headers(headers))
                r.raise_for_status()
                time.sleep(self.cfg.request_delay)
                return {"status": r.status_code, "text": r.text}
            except httpx.HTTPError as e:
                last = e
                time.sleep(1.0 * (attempt + 1))
        raise RuntimeError(f"POST 失败（重试{self.cfg.retries}次）: {url} -> {last}")
```

- [ ] **Step 4: 运行确认通过 + 全套**

Run: `uv run pytest tests/test_fetcher_headers.py -v && uv run pytest -q`
Expected: 新测试 2 passed；全套仍 `19 passed, 1 deselected`（原 17 + 2）

- [ ] **Step 5: ruff + Commit**

```bash
uv run ruff check src tests
git add src/exchange_monitor/fetcher.py tests/test_fetcher_headers.py
git commit -m "feat: allow per-call header overrides in Fetcher"
```

---

### Task 3: 数据模型 ExchangeResult / RunResult + 适配器协议

**Files:**
- Modify: `src/exchange_monitor/models.py`
- Create: `src/exchange_monitor/adapter.py`
- Test: `tests/test_models_multi.py`

**Interfaces:**
- Produces:
  - `ExchangeResult(name, is_baseline, doc_changes, doc_inventory, fee_changed, fee_diff, fee_supported, anns_new, anns_del)`
  - `RunResult(generated_at, exchanges: list[ExchangeResult])`（**替换**旧的扁平 RunResult）
  - `ExchangeAdapter` Protocol：`name: str`、`snapshot_name: str`、`fetch_docs(fetcher, config) -> list[DocMeta]`、`fetch_doc_body(fetcher, config, doc) -> str`、`fetch_announcements(fetcher, config, now_ts) -> tuple[list[Announcement], list[Announcement]]`、`fetch_fees(fetcher, config) -> str | None`

- [ ] **Step 1: 写失败测试 `tests/test_models_multi.py`**

```python
from exchange_monitor.models import ExchangeResult, RunResult


def test_exchange_result_defaults():
    ex = ExchangeResult(name="OKX", is_baseline=True)
    assert ex.name == "OKX"
    assert ex.doc_changes == [] and ex.anns_new == [] and ex.anns_del == []
    assert ex.fee_supported is False and ex.fee_changed is False


def test_run_result_holds_exchanges():
    r = RunResult(generated_at="2026-07-01 00:00 UTC",
                  exchanges=[ExchangeResult(name="OKX", is_baseline=False)])
    assert r.generated_at.endswith("UTC")
    assert r.exchanges[0].name == "OKX"
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_models_multi.py -v`
Expected: FAIL（`ExchangeResult` 不存在）

- [ ] **Step 3: 改 `models.py`**

保留 `DocMeta`/`Announcement`/`DocChange` 不变，**删除旧 `RunResult`**，追加：

```python
@dataclass
class ExchangeResult:
    name: str
    is_baseline: bool
    doc_changes: list[DocChange] = field(default_factory=list)
    doc_inventory: list[DocMeta] = field(default_factory=list)
    fee_changed: bool = False
    fee_diff: str = ""
    fee_supported: bool = False   # 该交易所是否监控费率
    anns_new: list[Announcement] = field(default_factory=list)
    anns_del: list[Announcement] = field(default_factory=list)


@dataclass
class RunResult:
    generated_at: str
    exchanges: list["ExchangeResult"] = field(default_factory=list)
```

- [ ] **Step 4: 写 `adapter.py`**

```python
from typing import Protocol

from exchange_monitor.models import Announcement, DocMeta


class ExchangeAdapter(Protocol):
    name: str
    snapshot_name: str

    def fetch_docs(self, fetcher, config) -> list[DocMeta]: ...

    def fetch_doc_body(self, fetcher, config, doc: DocMeta) -> str: ...

    def fetch_announcements(
        self, fetcher, config, now_ts: int
    ) -> tuple[list[Announcement], list[Announcement]]: ...

    def fetch_fees(self, fetcher, config) -> str | None: ...
```

- [ ] **Step 5: 运行确认通过**

Run: `uv run pytest tests/test_models_multi.py -v`
Expected: 2 passed
（注意：此步骤后 test_monitor/test_report/test_slack 会因旧 RunResult 被删而失败——它们在 Task 5/6/7 更新。本任务只提交 models+adapter+新测试。）

- [ ] **Step 6: Commit**

```bash
git add src/exchange_monitor/models.py src/exchange_monitor/adapter.py tests/test_models_multi.py
git commit -m "feat: add ExchangeResult/RunResult and ExchangeAdapter protocol"
```

---

### Task 4: OKX 适配器 exchanges/okx.py

**Files:**
- Create: `src/exchange_monitor/exchanges/__init__.py`（空）
- Create: `src/exchange_monitor/exchanges/okx.py`
- Test: `tests/test_okx_adapter.py`

**Interfaces:**
- Consumes: `parse.*`、config 常量、`Fetcher`
- Produces: `OkxAdapter` 类，`name="OKX"`、`snapshot_name="okx"`，实现协议四方法。文档/公告 URL 归一为绝对。

- [ ] **Step 1: 写失败测试 `tests/test_okx_adapter.py`（用 FakeFetcher + 现有 fixtures）**

```python
import json
import pathlib

from exchange_monitor.config import Config
from exchange_monitor.exchanges.okx import OkxAdapter

FIX = pathlib.Path(__file__).parent / "fixtures"


class FakeFetcher:
    def get_json(self, url, params=None, headers=None):
        if "search/articles" in url:
            return json.loads((FIX / "doc_list.json").read_text(encoding="utf-8"))
        if "unified/category" in url:
            return json.loads((FIX / "category.json").read_text(encoding="utf-8"))
        if "support/announcements" in url:
            name = "ann_new.json" if params["annType"].endswith("new-listings") else "ann_del.json"
            return json.loads((FIX / name).read_text(encoding="utf-8"))
        raise AssertionError(url)

    def get_text(self, url, params=None, headers=None):
        if "/fees" in url:
            return (FIX / "fees.html").read_text(encoding="utf-8")
        if "/help/" in url:
            return (FIX / "article.html").read_text(encoding="utf-8")
        raise AssertionError(url)


def test_okx_adapter_identity():
    a = OkxAdapter()
    assert a.name == "OKX" and a.snapshot_name == "okx"


def test_fetch_docs_absolute_url_and_count():
    docs = OkxAdapter().fetch_docs(FakeFetcher(), Config())
    assert len(docs) == 21
    assert all(d.url.startswith("https://www.okx.com") for d in docs)
    assert all(d.update_time > 1_700_000_000 for d in docs)


def test_fetch_fees_and_body_nonempty():
    a = OkxAdapter()
    fees = a.fetch_fees(FakeFetcher(), Config())
    assert fees and "feeTables" in fees
    docs = a.fetch_docs(FakeFetcher(), Config())
    body = a.fetch_doc_body(FakeFetcher(), Config(), docs[0])
    assert "委托" in body


def test_fetch_announcements_split_and_window():
    a = OkxAdapter()
    new, delist = a.fetch_announcements(FakeFetcher(), Config(), now_ts=1_782_900_000)
    assert isinstance(new, list) and isinstance(delist, list)
    cutoff = 1_782_900_000 - 3 * 86400
    assert all(x.ptime >= cutoff for x in new + delist)
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_okx_adapter.py -v`
Expected: FAIL（`exchanges.okx` 不存在）

- [ ] **Step 3: 写 `exchanges/__init__.py`（空文件）与 `exchanges/okx.py`**

```python
from exchange_monitor import parse
from exchange_monitor.config import (
    ANNOUNCEMENTS,
    ARTICLE_URL,
    BASE,
    CATEGORY,
    FEES_URL,
    SEARCH_ARTICLES,
)
from exchange_monitor.models import Announcement, DocMeta

_ANN_TYPES = ["announcements-new-listings", "announcements-delistings"]


class OkxAdapter:
    name = "OKX"
    snapshot_name = "okx"

    def fetch_docs(self, fetcher, config) -> list[DocMeta]:
        cat = fetcher.get_json(CATEGORY, {"slug": config.category_slug})
        sid = parse.resolve_section_id(cat, config.section_slug)
        data = fetcher.get_json(SEARCH_ARTICLES, {"sectionIds": sid, "page": 1, "size": 50})
        docs = parse.parse_doc_list(data)
        total = (data.get("data") or {}).get("total")
        if total is not None and int(total) > len(docs):
            raise ValueError(f"OKX doc list 截断: 共 {total} 篇但只取到 {len(docs)} 篇")
        for d in docs:
            if d.url.startswith("/"):
                d.url = f"{BASE}{d.url}"
        return docs

    def fetch_doc_body(self, fetcher, config, doc: DocMeta) -> str:
        html = fetcher.get_text(f"{ARTICLE_URL}/{doc.slug}")
        return parse.extract_article_body(html)

    def fetch_announcements(
        self, fetcher, config, now_ts: int
    ) -> tuple[list[Announcement], list[Announcement]]:
        cutoff = now_ts - config.window_days * 86400
        out: dict[str, list[Announcement]] = {t: [] for t in _ANN_TYPES}
        for ann_type in _ANN_TYPES:
            page = 1
            while True:
                data = fetcher.get_json(ANNOUNCEMENTS, {"annType": ann_type, "page": page})
                anns = parse.parse_announcements(data, ann_type)
                if not anns:
                    break
                out[ann_type].extend([a for a in anns if a.ptime >= cutoff])
                if anns[-1].ptime < cutoff or page >= parse.announcements_total_pages(data):
                    break
                page += 1
        return out["announcements-new-listings"], out["announcements-delistings"]

    def fetch_fees(self, fetcher, config) -> str | None:
        return parse.extract_fees_text(fetcher.get_text(FEES_URL))
```

- [ ] **Step 4: 运行确认通过**

Run: `uv run pytest tests/test_okx_adapter.py -v`
Expected: 4 passed

- [ ] **Step 5: ruff + Commit**

```bash
uv run ruff check src tests
git add src/exchange_monitor/exchanges/ tests/test_okx_adapter.py
git commit -m "feat: add OkxAdapter implementing ExchangeAdapter"
```

---

### Task 5: 核心 run/_run_one 泛化（monitor.py）

**Files:**
- Modify: `src/exchange_monitor/monitor.py`
- Modify: `tests/test_monitor.py`

**Interfaces:**
- Consumes: `ExchangeAdapter`、`snapshot.*`、`ExchangeResult`/`RunResult`
- Produces: `run(config, fetcher, now_ts, adapters) -> RunResult`；`_run_one(config, fetcher, now_ts, adapter) -> ExchangeResult`；`build_doc_changes(docs, bodies, baseline_docs) -> list[DocChange]`（保留）

- [ ] **Step 1: 改写 `tests/test_monitor.py`（FakeFetcher 加 headers 形参；run 传 adapters；断言走 exchanges[0]）**

```python
import pathlib

from exchange_monitor import monitor, snapshot
from exchange_monitor.config import Config
from exchange_monitor.exchanges.okx import OkxAdapter
from tests.test_okx_adapter import FakeFetcher  # 复用

FIX = pathlib.Path(__file__).parent / "fixtures"


def test_first_run_is_baseline(tmp_path):
    cfg = Config(snapshot_dir=tmp_path)
    res = monitor.run(cfg, FakeFetcher(), 1_782_900_000, [OkxAdapter()])
    ex = res.exchanges[0]
    assert ex.name == "OKX"
    assert ex.is_baseline is True
    assert len(ex.doc_inventory) == 21
    assert ex.doc_changes == []
    assert ex.fee_changed is False and ex.fee_supported is True
    assert (tmp_path / "okx.json").exists()


def test_second_run_detects_doc_update(tmp_path):
    cfg = Config(snapshot_dir=tmp_path)
    monitor.run(cfg, FakeFetcher(), 1_782_900_000, [OkxAdapter()])
    snap = snapshot.load_snapshot(tmp_path / "okx.json")
    any_slug = next(iter(snap["docs"]))
    snap["docs"][any_slug]["update_time"] = 1
    snap["docs"][any_slug]["body"] = "旧内容\n"
    snapshot.save_snapshot(tmp_path / "okx.json", snap)
    res = monitor.run(cfg, FakeFetcher(), 1_782_900_000, [OkxAdapter()])
    ex = res.exchanges[0]
    assert ex.is_baseline is False
    changed = next(c for c in ex.doc_changes if c.slug == any_slug)
    assert changed.kind == "updated" and changed.diff
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_monitor.py -v`
Expected: FAIL（`run` 签名/`RunResult` 结构不匹配）

- [ ] **Step 3: 改写 `monitor.py`**

```python
from datetime import UTC, datetime

from exchange_monitor import snapshot
from exchange_monitor.config import Config
from exchange_monitor.models import DocChange, DocMeta, ExchangeResult, RunResult


def _date(ts: int) -> str:
    return datetime.fromtimestamp(ts, tz=UTC).strftime("%Y-%m-%d")


def build_doc_changes(
    docs: list[DocMeta], bodies: dict[str, str], baseline_docs: dict
) -> list[DocChange]:
    changes: list[DocChange] = []
    seen = set()
    for d in docs:
        seen.add(d.slug)
        base = baseline_docs.get(d.slug)
        if base is None:
            changes.append(DocChange(d.slug, d.title, d.url, _date(d.update_time), "new", ""))
            continue
        if d.update_time != base["update_time"]:
            diff = snapshot.unified_diff(base.get("body", ""), bodies[d.slug], d.title)
            changes.append(DocChange(d.slug, d.title, d.url, _date(d.update_time), "updated", diff))
    for slug, base in baseline_docs.items():
        if slug not in seen:
            changes.append(DocChange(slug, base["title"], "", "", "removed", ""))
    return changes


def _run_one(config: Config, fetcher, now_ts: int, adapter) -> ExchangeResult:
    snap_path = config.snapshot_dir / f"{adapter.snapshot_name}.json"
    baseline = snapshot.load_snapshot(snap_path)
    is_baseline = baseline is None
    baseline = baseline or {"docs": {}}

    docs = adapter.fetch_docs(fetcher, config)
    bodies: dict[str, str] = {}
    for d in docs:
        base = baseline["docs"].get(d.slug)
        if is_baseline or base is None or d.update_time != base["update_time"]:
            bodies[d.slug] = adapter.fetch_doc_body(fetcher, config, d)
        else:
            bodies[d.slug] = base.get("body", "")
    doc_changes = [] if is_baseline else build_doc_changes(docs, bodies, baseline["docs"])

    fees_text = adapter.fetch_fees(fetcher, config)
    fee_supported = fees_text is not None
    fee_diff = ""
    if fee_supported and not is_baseline:
        fee_diff = snapshot.unified_diff(baseline.get("fees_text", ""), fees_text, "费率")
    fee_changed = bool(fee_diff)

    anns_new, anns_del = adapter.fetch_announcements(fetcher, config, now_ts)

    new_snap: dict = {
        "docs": {
            d.slug: {"title": d.title, "update_time": d.update_time, "body": bodies[d.slug]}
            for d in docs
        }
    }
    if fee_supported:
        new_snap["fees_text"] = fees_text
    snapshot.save_snapshot(snap_path, new_snap)

    return ExchangeResult(
        name=adapter.name,
        is_baseline=is_baseline,
        doc_changes=doc_changes,
        doc_inventory=docs,
        fee_changed=fee_changed,
        fee_diff=fee_diff,
        fee_supported=fee_supported,
        anns_new=anns_new,
        anns_del=anns_del,
    )


def run(config: Config, fetcher, now_ts: int, adapters: list) -> RunResult:
    return RunResult(
        generated_at=datetime.fromtimestamp(now_ts, tz=UTC).strftime("%Y-%m-%d %H:%M UTC"),
        exchanges=[_run_one(config, fetcher, now_ts, a) for a in adapters],
    )
```

- [ ] **Step 4: 运行确认通过**

Run: `uv run pytest tests/test_monitor.py -v`
Expected: 2 passed

- [ ] **Step 5: ruff + Commit**

```bash
uv run ruff check src tests
git add src/exchange_monitor/monitor.py tests/test_monitor.py
git commit -m "refactor: generalize monitor.run over exchange adapters"
```

---

### Task 6: report.py 多交易所渲染

**Files:**
- Modify: `src/exchange_monitor/report.py`
- Modify: `tests/test_report.py`

**Interfaces:**
- Consumes: `RunResult`/`ExchangeResult`
- Produces: `render_markdown(result, window_days) -> str`；`summary_lines(result) -> list[str]`（按交易所）

- [ ] **Step 1: 改写 `tests/test_report.py`**

```python
from exchange_monitor import report
from exchange_monitor.models import Announcement, DocChange, DocMeta, ExchangeResult, RunResult


def _baseline_run():
    return RunResult(
        generated_at="2026-07-01 03:00 UTC",
        exchanges=[ExchangeResult(
            name="OKX", is_baseline=True, fee_supported=True,
            doc_inventory=[DocMeta("s1", "基础委托类型", "https://www.okx.com/help/s1", 1_782_000_000, 1_700_000_000)],
            anns_new=[Announcement("某币上线", "https://www.okx.com/help/1", 1_782_800_000, "announcements-new-listings")],
        )],
    )


def test_markdown_marks_baseline_and_exchange_name():
    md = report.render_markdown(_baseline_run(), 3)
    assert "OKX" in md and "基线建立" in md
    assert "基础委托类型" in md and "某币上线" in md


def test_markdown_shows_doc_diff_with_absolute_url():
    res = RunResult(generated_at="2026-07-01 03:00 UTC", exchanges=[ExchangeResult(
        name="OKX", is_baseline=False, fee_supported=True,
        doc_changes=[DocChange("s1", "基础委托类型", "https://www.okx.com/help/s1", "2026-06-29", "updated", "@@ -1 +1 @@\n-旧\n+新\n")],
    )])
    md = report.render_markdown(res, 3)
    assert "更新" in md and "+新" in md and "https://www.okx.com/help/s1" in md


def test_summary_lines_per_exchange():
    lines = report.summary_lines(_baseline_run())
    assert lines and any("OKX" in ln for ln in lines)
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_report.py -v`
Expected: FAIL

- [ ] **Step 3: 改写 `report.py`**

```python
from datetime import UTC, datetime

from exchange_monitor.models import ExchangeResult, RunResult

_KIND_CN = {"new": "新增", "updated": "更新", "removed": "下架"}


def _d(ts: int) -> str:
    return datetime.fromtimestamp(ts, tz=UTC).strftime("%Y-%m-%d")


def _render_exchange(lines: list[str], ex: ExchangeResult, window_days: int) -> None:
    tag = "（基线建立，无 diff）" if ex.is_baseline else ""
    lines.append(f"\n# {ex.name}{tag}")

    lines.append("\n## 一、交易规则")
    if ex.is_baseline:
        lines.append(f"\n首次运行，记录 {len(ex.doc_inventory)} 篇文档为基线：\n")
        for d in ex.doc_inventory:
            lines.append(f"- {d.title} — 更新于 {_d(d.update_time)} — {d.url}")
    elif not ex.doc_changes:
        lines.append("\n相对基线无变化。")
    else:
        lines.append(f"\n相对基线有变化的文档（{len(ex.doc_changes)} 篇）：\n")
        for c in ex.doc_changes:
            head = f"### [{_KIND_CN.get(c.kind, c.kind)}] {c.title}"
            if c.update_date:
                head += f" — 更新于 {c.update_date}"
            lines.append(head)
            if c.url:
                lines.append(c.url)
            if c.diff:
                lines.append("\n```diff")
                lines.append(c.diff.rstrip())
                lines.append("```")
            lines.append("")

    if ex.fee_supported:
        lines.append("\n## 二、费率规则")
        if ex.is_baseline:
            lines.append("\n已记录费率页为基线，无 diff。")
        elif ex.fee_changed:
            lines.append("\n费率页**有变化**：\n")
            lines.append("```diff")
            lines.append(ex.fee_diff.rstrip())
            lines.append("```")
        else:
            lines.append("\n费率页无变化。")

    lines.append(f"\n## 三、上下币公告（近 {window_days} 天）")
    lines.append(f"\n### 上币（{len(ex.anns_new)} 条）")
    for a in ex.anns_new:
        lines.append(f"- {a.title} — {_d(a.ptime)} — {a.url}")
    lines.append(f"\n### 下币（{len(ex.anns_del)} 条）")
    for a in ex.anns_del:
        lines.append(f"- {a.title} — {_d(a.ptime)} — {a.url}")


def render_markdown(result: RunResult, window_days: int) -> str:
    lines = [f"# 交易所监控报告 {result.generated_at}"]
    for ex in result.exchanges:
        _render_exchange(lines, ex, window_days)
    return "\n".join(lines) + "\n"


def summary_lines(result: RunResult) -> list[str]:
    out: list[str] = []
    for ex in result.exchanges:
        if ex.is_baseline:
            out.append(
                f"[{ex.name}] 基线: 文档 {len(ex.doc_inventory)} 篇 / "
                f"上币 {len(ex.anns_new)} 下币 {len(ex.anns_del)}"
            )
        else:
            fee = ("费率有变化" if ex.fee_changed else "费率无变化") if ex.fee_supported else "费率未监控"
            out.append(
                f"[{ex.name}] 文档变更 {len(ex.doc_changes)} 篇 / {fee} / "
                f"上币 {len(ex.anns_new)} 下币 {len(ex.anns_del)}"
            )
    return out
```

- [ ] **Step 4: 运行确认通过**

Run: `uv run pytest tests/test_report.py -v`
Expected: 3 passed

- [ ] **Step 5: ruff + Commit**

```bash
uv run ruff check src tests
git add src/exchange_monitor/report.py tests/test_report.py
git commit -m "refactor: multi-exchange markdown report and per-exchange summary"
```

---

### Task 7: slack.py 多交易所消息

**Files:**
- Modify: `src/exchange_monitor/slack.py`
- Modify: `tests/test_slack.py`

**Interfaces:**
- Consumes: `RunResult`/`ExchangeResult`、`report.summary_lines`
- Produces: `build_slack_message(result, window_days) -> dict`；`send_report(fetcher, webhook_url, result, window_days)`（不变）

- [ ] **Step 1: 改写 `tests/test_slack.py`**

```python
from exchange_monitor import slack
from exchange_monitor.models import Announcement, DocChange, DocMeta, ExchangeResult, RunResult


def _run(exchanges):
    return RunResult(generated_at="2026-07-01 03:00 UTC", exchanges=exchanges)


def test_build_slack_message_baseline():
    r = _run([ExchangeResult(
        name="OKX", is_baseline=True,
        doc_inventory=[DocMeta("s1", "基础委托类型", "https://x/1", 1_782_000_000, 1_700_000_000)],
        anns_new=[Announcement("某币上线", "https://x/a", 1_782_800_000, "announcements-new-listings")],
    )])
    payload = slack.build_slack_message(r, 3)
    assert isinstance(payload, dict) and "text" in payload
    assert "OKX" in payload["text"] and "某币上线" in payload["text"] and "• " in payload["text"]


def test_build_slack_message_with_changes():
    r = _run([ExchangeResult(
        name="Binance", is_baseline=False,
        doc_changes=[DocChange("s1", "交易规则文档", "https://b/help/s1", "2026-06-30", "updated", "d")],
        anns_new=[Announcement("上新X", "https://b/a", 1_782_800_000, "48")],
    )])
    text = slack.build_slack_message(r, 3)["text"]
    assert "Binance" in text and "更新" in text
    assert "<https://b/help/s1|交易规则文档>" in text and "⬆️" in text


def test_build_slack_message_no_changes_has_summary():
    r = _run([ExchangeResult(name="OKX", is_baseline=False, fee_supported=True)])
    text = slack.build_slack_message(r, 3)["text"]
    assert "OKX" in text and "• " in text
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_slack.py -v`
Expected: FAIL

- [ ] **Step 3: 改写 `slack.py`**

```python
"""把多交易所监控结果组装为 Slack 消息并发送（Incoming Webhook）。"""
from exchange_monitor.models import RunResult
from exchange_monitor.report import summary_lines

_KIND_CN = {"new": "新增", "updated": "更新", "removed": "下架"}


def build_slack_message(result: RunResult, window_days: int) -> dict:
    lines: list[str] = [f"*交易所监控*  {result.generated_at}"]
    for s in summary_lines(result):
        lines.append("• " + s)
    for ex in result.exchanges:
        seg: list[str] = []
        if not ex.is_baseline and ex.doc_changes:
            seg.append(f"*{ex.name} 规则变更：*")
            for c in ex.doc_changes:
                label = _KIND_CN.get(c.kind, c.kind)
                seg.append(f"• [{label}] <{c.url}|{c.title}>" if c.url else f"• [{label}] {c.title}")
        if ex.anns_new or ex.anns_del:
            seg.append(f"*{ex.name} 上下币（近 {window_days} 天）：*")
            for a in ex.anns_new:
                seg.append(f"• ⬆️ <{a.url}|{a.title}>")
            for a in ex.anns_del:
                seg.append(f"• ⬇️ <{a.url}|{a.title}>")
        if seg:
            lines.append("")
            lines.extend(seg)
    return {"text": "\n".join(lines)}


def send_report(fetcher, webhook_url: str, result: RunResult, window_days: int) -> None:
    payload = build_slack_message(result, window_days)
    fetcher.post_json(webhook_url, payload)
```

- [ ] **Step 4: 运行确认通过 + 全套**

Run: `uv run pytest tests/test_slack.py -v && uv run pytest -q`
Expected: 3 passed；全套全绿

- [ ] **Step 5: ruff + Commit**

```bash
uv run ruff check src tests
git add src/exchange_monitor/slack.py tests/test_slack.py
git commit -m "refactor: multi-exchange Slack message"
```

---

### Task 8: __main__ 接线 + 端到端验证

**Files:**
- Modify: `src/exchange_monitor/__main__.py`

**Interfaces:**
- Consumes: `run`、`OkxAdapter`、`render_markdown`/`summary_lines`、`send_report`
- Produces: `python -m exchange_monitor` 遍历适配器（当前仅 OKX），写 `reports/exchanges-YYYYMMDD-HHMM.md`（仅有变更时），发 Slack。

- [ ] **Step 1: 改写 `__main__.py`**

```python
import os
import sys
from datetime import UTC, datetime

from exchange_monitor.config import Config
from exchange_monitor.exchanges.okx import OkxAdapter
from exchange_monitor.fetcher import Fetcher
from exchange_monitor.monitor import run
from exchange_monitor.report import render_markdown, summary_lines
from exchange_monitor.slack import send_report

ADAPTERS = [OkxAdapter()]


def main() -> int:
    cfg = Config(slack_webhook_url=os.environ.get("SLACK_WEBHOOK_URL"))
    now = datetime.now(tz=UTC)
    now_ts = int(now.timestamp())
    try:
        with Fetcher(cfg) as fetcher:
            result = run(cfg, fetcher, now_ts, ADAPTERS)
    except Exception as e:  # noqa: BLE001 — 顶层兜底，明确报错不静默
        print(f"运行失败: {e}", file=sys.stderr)
        return 1

    has_changes = any(
        ex.is_baseline or ex.doc_changes or ex.fee_changed for ex in result.exchanges
    )
    if has_changes:
        md = render_markdown(result, cfg.window_days)
        cfg.report_dir.mkdir(parents=True, exist_ok=True)
        out = cfg.report_dir / f"exchanges-{now.strftime('%Y%m%d-%H%M')}.md"
        out.write_text(md, encoding="utf-8")
        print(f"\n报告已写入: {out}\n")
    else:
        print("\n本次无变化，未写报告\n")
    for line in summary_lines(result):
        print("  " + line)

    if cfg.slack_webhook_url:
        try:
            with Fetcher(cfg) as fetcher:
                send_report(fetcher, cfg.slack_webhook_url, result, cfg.window_days)
            print("  已发送到 Slack")
        except Exception as e:  # noqa: BLE001 — 发送失败需可见
            print(f"Slack 发送失败: {e}", file=sys.stderr)
            return 1
    else:
        print("  未配置 SLACK_WEBHOOK_URL，跳过 Slack 发送")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: 全套测试 + ruff**

Run: `uv run pytest -q && uv run ruff check src tests`
Expected: 全绿；ruff 干净

- [ ] **Step 3: 端到端（需代理在跑）——首次基线**

```bash
rm -f snapshots/okx.json
uv run python -m exchange_monitor
```
Expected: 打印 `报告已写入: reports/exchanges-...md` + `[OKX] 基线: 文档 21 篇 ...`；`snapshots/okx.json` 存在且 21 篇。

- [ ] **Step 4: 端到端——第二次（无变化不写报告）**

Run: `uv run python -m exchange_monitor`
Expected: 退出码 0；打印 `本次无变化，未写报告`（除非 OKX 恰好更新）；`[OKX] 文档变更 0 篇 / 费率无变化 / ...`；若配了 webhook 则 `已发送到 Slack`。

- [ ] **Step 5: Commit**

```bash
git add src/exchange_monitor/__main__.py
git commit -m "refactor: wire __main__ to adapter-based multi-exchange run"
```

---

## Self-Review 检查

- **Spec 覆盖**：通用核心泛化（Task 5）、适配器接口（Task 3）、OKX 适配器（Task 4）、按调用 header（Task 2，供 Binance 用）、按交易所快照文件（Task 5 `_run_one`）、合并报告（Task 6）、合并 Slack（Task 7）、包重命名（Task 1）、__main__ 接线（Task 8）均覆盖。费率 OKX 保留（`fetch_fees` 返回文本，`fee_supported`）。
- **类型一致**：`run(config, fetcher, now_ts, adapters)` 在 Task 5 定义、Task 8 使用一致；`ExchangeResult` 字段在 Task 3 定义、Task 4/5/6/7 使用一致；`DocMeta.url` 绝对化在 Task 4，report/slack（Task 6/7）直接用不再拼前缀；`summary_lines(result)` 在 Task 6 定义、Task 7/8 使用。
- **占位符**：无 TBD/TODO；每步含真实代码/命令。
- **行为不变性**：Task 8 端到端验证 OKX 与现状一致（基线 21 篇、无变化不写报告、Slack 发送）。

## 后续（不在本计划）
- Phase 1：`exchanges/binance.py`（公告 CMS API + 文档 list/detail 枚举 + 正文 diff），加入 `ADAPTERS`。
- Phase 2：`exchanges/bybit.py`（公告 V5 API + `__NEXT_DATA__` 文档 + 正文 diff），加入 `ADAPTERS`。
