# OKX 文档/规则更新监控 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现一个可重复运行的 Python 脚本，监控 OKX 交易规则文档、费率页、上下币公告的更新，以今天首次运行为基线，之后输出相对基线的逐字变更与新增公告。

**Architecture:** 纯 httpx（走代理 + `Accept-Language: zh-CN` 头）调用已逆向确认的 OKX JSON 接口与 SSR 页面，解析为数据模型；快照存盘，运行时与上次快照对比产出 diff；渲染 Markdown 报告并打印终端摘要。无无头浏览器。

**Tech Stack:** Python 3.12, `uv`, `httpx`, `selectolax`, 标准库 `difflib`/`json`/`re`，`pytest`，`ruff`。

## Global Constraints

- 所有对 OKX 的请求必须走代理 `http://127.0.0.1:7890`，并带头 `Accept-Language: zh-CN,zh` 和一个浏览器 UA。
- 不允许 silent-wrong：接口/解析失败必须抛出明确异常或在报告中显式标注，禁止静默返回空。
- 首次运行 = 建立基线，明确标注「基线建立，无 diff」，不得伪造变更内容。
- section id 运行时动态解析，不硬编码。
- 包管理用 `uv`，格式化/lint 用 `ruff`。
- 时间统一用 UTC 时间戳（秒）比较；展示用 `datetime.fromtimestamp(ts, tz=UTC)` 的日期。
- 网络相关逻辑不写进单元测试（用 fixture）；仅保留一个可手动跑的 live smoke 测试。

## 文件结构

```
pyproject.toml                         # uv 项目 + 依赖 + ruff 配置
src/okx_monitor/__init__.py
src/okx_monitor/config.py              # Config 数据类与默认常量
src/okx_monitor/models.py              # DocMeta / Announcement / RunResult 数据类
src/okx_monitor/fetcher.py             # Fetcher：httpx 封装(代理/头/重试)
src/okx_monitor/parse.py               # 纯解析函数(无网络)
src/okx_monitor/snapshot.py            # 快照存取 + 文本 diff
src/okx_monitor/monitor.py             # 编排：抓取→对比→RunResult
src/okx_monitor/report.py              # 渲染 Markdown + 终端摘要
src/okx_monitor/__main__.py            # CLI 入口
scripts/capture_fixtures.py            # 一次性抓取真实响应存为 fixture
tests/fixtures/                        # 提交的真实响应样本
tests/test_parse.py
tests/test_snapshot.py
tests/test_monitor.py
tests/test_report.py
tests/test_fetcher_live.py             # 标 @pytest.mark.live，默认跳过
snapshots/                             # 运行期生成(gitignore)
reports/                               # 运行期生成(gitignore)
```

数据流：`__main__` → `Config` → `monitor.run()` 用 `Fetcher` 拿数据、`parse` 解析、`snapshot` 对比 → 产出 `RunResult` → `report` 渲染。

---

### Task 1: 项目脚手架与 fixture 抓取

**Files:**
- Create: `pyproject.toml`, `src/okx_monitor/__init__.py`, `.gitignore`
- Create: `scripts/capture_fixtures.py`
- Create: `tests/fixtures/` (运行脚本生成)

**Interfaces:**
- Produces: 可导入的包 `okx_monitor`；`tests/fixtures/` 下的真实样本文件。

- [ ] **Step 1: 初始化 uv 项目**

```bash
cd /Users/mac/dev/exchange_base_rule
uv init --package --name okx-monitor --python 3.12 .
uv add httpx selectolax
uv add --dev pytest ruff
```

- [ ] **Step 2: 写 `.gitignore`**

```
__pycache__/
*.pyc
.venv/
snapshots/
reports/
.pytest_cache/
```

- [ ] **Step 3: 配置 ruff（追加到 `pyproject.toml`）**

```toml
[tool.ruff]
line-length = 100

[tool.pytest.ini_options]
markers = ["live: 需要真实网络与代理，默认手动运行"]
addopts = "-m 'not live'"
```

- [ ] **Step 4: 写 `scripts/capture_fixtures.py`（抓真实响应存盘）**

```python
"""一次性抓取 OKX 真实响应，存为测试 fixture。需代理 127.0.0.1:7890。"""
import pathlib
import httpx

PROXY = "http://127.0.0.1:7890"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept-Language": "zh-CN,zh",
}
OUT = pathlib.Path(__file__).parent.parent / "tests" / "fixtures"
SECTION_ID = "3HsUPMtNszv47YPMMMx8Dw"

TARGETS = {
    "category.json": "https://www.okx.com/priapi/v1/assistant/service-center/kb/unified/category?slug=product-documentation",
    "doc_list.json": f"https://www.okx.com/priapi/v1/assistant/service-center/search/articles?sectionIds={SECTION_ID}&page=1&size=50",
    "article.html": "https://www.okx.com/zh-hans/help/x-basic-order-types",
    "ann_new.json": "https://www.okx.com/api/v5/support/announcements?annType=announcements-new-listings&page=1",
    "ann_del.json": "https://www.okx.com/api/v5/support/announcements?annType=announcements-delistings&page=1",
    "fees.html": "https://www.okx.com/zh-hans/fees",
}

def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with httpx.Client(proxy=PROXY, headers=HEADERS, timeout=20) as c:
        for name, url in TARGETS.items():
            r = c.get(url)
            r.raise_for_status()
            (OUT / name).write_text(r.text, encoding="utf-8")
            print(f"saved {name} ({len(r.text)} bytes)")

if __name__ == "__main__":
    main()
```

- [ ] **Step 5: 运行抓取 fixture**

Run: `uv run python scripts/capture_fixtures.py`
Expected: 打印 6 个 `saved ...`，`tests/fixtures/` 下生成 6 个文件，每个 > 1KB。

- [ ] **Step 6: Commit**

```bash
git init && git add -A
git commit -m "chore: scaffold okx-monitor project and capture fixtures"
```
（注：仓库当前非 git；若用户未要求提交，可跳过 commit，仅保留文件。）

---

### Task 2: 数据模型

**Files:**
- Create: `src/okx_monitor/models.py`
- Test: `tests/test_parse.py`（本任务先建空壳，下任务填充）

**Interfaces:**
- Produces:
  - `DocMeta(slug: str, title: str, url: str, update_time: int, publish_time: int)`
  - `Announcement(title: str, url: str, ptime: int, ann_type: str)`
  - `DocChange(slug: str, title: str, url: str, update_date: str, kind: str, diff: str)` — kind ∈ {"new","updated","removed"}
  - `RunResult(is_baseline: bool, generated_at: str, doc_changes: list[DocChange], doc_inventory: list[DocMeta], fee_changed: bool, fee_diff: str, anns_new: list[Announcement], anns_del: list[Announcement])`

- [ ] **Step 1: 写 `models.py`**

```python
from dataclasses import dataclass, field


@dataclass
class DocMeta:
    slug: str
    title: str
    url: str
    update_time: int   # epoch 秒
    publish_time: int   # epoch 秒


@dataclass
class Announcement:
    title: str
    url: str
    ptime: int          # epoch 秒
    ann_type: str       # announcements-new-listings | announcements-delistings


@dataclass
class DocChange:
    slug: str
    title: str
    url: str
    update_date: str    # YYYY-MM-DD
    kind: str           # new | updated | removed
    diff: str           # 统一 diff 文本，removed 时为空


@dataclass
class RunResult:
    is_baseline: bool
    generated_at: str
    doc_changes: list[DocChange] = field(default_factory=list)
    doc_inventory: list[DocMeta] = field(default_factory=list)
    fee_changed: bool = False
    fee_diff: str = ""
    anns_new: list[Announcement] = field(default_factory=list)
    anns_del: list[Announcement] = field(default_factory=list)
```

- [ ] **Step 2: 验证可导入**

Run: `uv run python -c "from okx_monitor.models import DocMeta, RunResult; print('ok')"`
Expected: 打印 `ok`

- [ ] **Step 3: Commit**

```bash
git add src/okx_monitor/models.py && git commit -m "feat: add data models"
```

---

### Task 3: 纯解析函数

**Files:**
- Create: `src/okx_monitor/parse.py`
- Test: `tests/test_parse.py`

**Interfaces:**
- Consumes: `tests/fixtures/*`（Task 1），`models.DocMeta`/`Announcement`
- Produces:
  - `resolve_section_id(category_json: dict, section_slug: str) -> str`
  - `parse_doc_list(api_json: dict) -> list[DocMeta]`
  - `parse_announcements(api_json: dict, ann_type: str) -> list[Announcement]`
  - `extract_article_body(html: str) -> str`
  - `extract_fees_text(html: str) -> str`

- [ ] **Step 1: 写 `tests/test_parse.py` 失败测试**

```python
import json
import pathlib

from okx_monitor import parse

FIX = pathlib.Path(__file__).parent / "fixtures"


def _json(name):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


def test_parse_doc_list_returns_all_21_with_dates():
    docs = parse.parse_doc_list(_json("doc_list.json"))
    assert len(docs) == 21
    d = docs[0]
    assert d.slug and d.title and d.url.startswith("/")
    assert d.update_time > 1_700_000_000  # 合理 epoch 秒
    # 标题应为中文（Accept-Language 生效）
    assert any("一" <= ch <= "鿿" for ch in d.title)


def test_parse_announcements_classifies_type():
    anns = parse.parse_announcements(_json("ann_new.json"), "announcements-new-listings")
    assert anns, "应有上币公告"
    a = anns[0]
    assert a.ann_type == "announcements-new-listings"
    assert a.ptime > 1_700_000_000
    assert a.url.startswith("http")


def test_extract_article_body_nonempty_chinese():
    body = parse.extract_article_body((FIX / "article.html").read_text(encoding="utf-8"))
    assert len(body) > 200
    assert "委托" in body


def test_extract_fees_text_has_fee_terms():
    text = parse.extract_fees_text((FIX / "fees.html").read_text(encoding="utf-8"))
    assert "手续费" in text


def test_resolve_section_id():
    sid = parse.resolve_section_id(
        _json("category.json"),
        "product-documentation-introduction-to-basic-trading-rules",
    )
    assert sid == "3HsUPMtNszv47YPMMMx8Dw"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/test_parse.py -v`
Expected: FAIL（`module okx_monitor has no attribute parse` 或函数缺失）

- [ ] **Step 3: 写 `parse.py`**

```python
"""纯解析：输入原始响应文本/JSON，输出数据模型。无网络。"""
import json
import re

from selectolax.parser import HTMLParser

from okx_monitor.models import Announcement, DocMeta


def parse_doc_list(api_json: dict) -> list[DocMeta]:
    items = api_json["data"]["list"]
    docs: list[DocMeta] = []
    for it in items:
        docs.append(
            DocMeta(
                slug=it["slug"],
                title=it["title"].strip(),
                url=it["url"],
                update_time=int(it["updateTime"]),
                publish_time=int(it["publishTime"]),
            )
        )
    return docs


def parse_announcements(api_json: dict, ann_type: str) -> list[Announcement]:
    data = api_json.get("data") or []
    if not data:
        return []
    details = data[0].get("details") or []
    out: list[Announcement] = []
    for d in details:
        out.append(
            Announcement(
                title=d["title"].strip(),
                url=d["url"],
                ptime=int(d["pTime"]) // 1000,  # 毫秒→秒
                ann_type=d.get("annType", ann_type),
            )
        )
    return out


def announcements_total_pages(api_json: dict) -> int:
    data = api_json.get("data") or []
    if not data:
        return 0
    return int(data[0].get("totalPage", 1))


def extract_article_body(html: str) -> str:
    """文章页内嵌唯一一个 JSON "content" 字段含全文。"""
    m = re.search(r'"content":"((?:[^"\\]|\\.)*)"', html)
    if not m:
        raise ValueError("article body: 未找到 content 字段，接口/页面可能已变更")
    return json.loads('"' + m.group(1) + '"').strip()


def extract_fees_text(html: str) -> str:
    """费率页无稳定 content 字段，取渲染后正文文本。"""
    tree = HTMLParser(html)
    body = tree.body
    if body is None:
        raise ValueError("fees: 无 body，页面可能已变更")
    text = body.text(separator="\n", strip=True)
    if "手续费" not in text:
        raise ValueError("fees: 正文未含'手续费'，解析可能失效")
    return text


def resolve_section_id(category_json: dict, section_slug: str) -> str:
    """从分类接口响应里按 slug 找 section id。"""
    blob = json.dumps(category_json, ensure_ascii=False)
    # category 响应包含若干 section 对象，含 id 与 slug
    for m in re.finditer(r'\{"id":"([^"]+)","slug":"([^"]+)"', blob):
        if m.group(2) == section_slug:
            return m.group(1)
    # 退化：递归搜索
    def walk(o):
        if isinstance(o, dict):
            if o.get("slug") == section_slug and "id" in o:
                return o["id"]
            for v in o.values():
                r = walk(v)
                if r:
                    return r
        elif isinstance(o, list):
            for v in o:
                r = walk(v)
                if r:
                    return r
        return None

    sid = walk(category_json)
    if not sid:
        raise ValueError(f"未找到 section '{section_slug}' 的 id，分类接口可能已变更")
    return sid
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/test_parse.py -v`
Expected: 5 passed。若 `test_resolve_section_id` 失败，先 `uv run python -c "import json;d=json.load(open('tests/fixtures/category.json'));print(json.dumps(d)[:400])"` 核对结构再调 `resolve_section_id` 的正则。

- [ ] **Step 5: Commit**

```bash
git add src/okx_monitor/parse.py tests/test_parse.py
git commit -m "feat: add parsers for docs, announcements, article body, fees"
```

---

### Task 4: 配置与 Fetcher

**Files:**
- Create: `src/okx_monitor/config.py`, `src/okx_monitor/fetcher.py`
- Test: `tests/test_fetcher_live.py`

**Interfaces:**
- Consumes: `Config`
- Produces:
  - `Config(proxy, accept_language, user_agent, section_slug, window_days, snapshot_dir, report_dir, timeout, retries, request_delay)` 带默认值
  - `Fetcher(config)`：`get_json(url, params=None) -> dict`、`get_text(url, params=None) -> str`；自动重试、走代理、带头。

- [ ] **Step 1: 写 `config.py`**

```python
from dataclasses import dataclass
from pathlib import Path

BASE = "https://www.okx.com"
SEARCH_ARTICLES = f"{BASE}/priapi/v1/assistant/service-center/search/articles"
CATEGORY = f"{BASE}/priapi/v1/assistant/service-center/kb/unified/category"
ANNOUNCEMENTS = f"{BASE}/api/v5/support/announcements"
FEES_URL = f"{BASE}/zh-hans/fees"
ARTICLE_URL = f"{BASE}/zh-hans/help"  # + /{slug}
CATEGORY_SLUG = "product-documentation"
SECTION_SLUG = "product-documentation-introduction-to-basic-trading-rules"


@dataclass
class Config:
    proxy: str = "http://127.0.0.1:7890"
    accept_language: str = "zh-CN,zh"
    user_agent: str = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
    section_slug: str = SECTION_SLUG
    category_slug: str = CATEGORY_SLUG
    window_days: int = 3
    snapshot_dir: Path = Path("snapshots")
    report_dir: Path = Path("reports")
    timeout: float = 20.0
    retries: int = 3
    request_delay: float = 0.5  # 每次请求后小延时，避免限频
```

- [ ] **Step 2: 写 `fetcher.py`**

```python
import time

import httpx

from okx_monitor.config import Config


class Fetcher:
    def __init__(self, config: Config):
        self.cfg = config
        self._client = httpx.Client(
            proxy=config.proxy,
            timeout=config.timeout,
            headers={
                "User-Agent": config.user_agent,
                "Accept-Language": config.accept_language,
            },
        )

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self._client.close()

    def _get(self, url: str, params: dict | None) -> httpx.Response:
        last: Exception | None = None
        for attempt in range(self.cfg.retries):
            try:
                r = self._client.get(url, params=params)
                r.raise_for_status()
                time.sleep(self.cfg.request_delay)
                return r
            except (httpx.HTTPError,) as e:
                last = e
                time.sleep(1.0 * (attempt + 1))
        raise RuntimeError(f"请求失败（重试{self.cfg.retries}次）: {url} -> {last}")

    def get_json(self, url: str, params: dict | None = None) -> dict:
        return self._get(url, params).json()

    def get_text(self, url: str, params: dict | None = None) -> str:
        return self._get(url, params).text
```

- [ ] **Step 3: 写 live smoke 测试 `tests/test_fetcher_live.py`**

```python
import pytest

from okx_monitor.config import Config, ANNOUNCEMENTS
from okx_monitor.fetcher import Fetcher


@pytest.mark.live
def test_live_announcements_reachable():
    with Fetcher(Config()) as f:
        data = f.get_json(ANNOUNCEMENTS, {"annType": "announcements-new-listings", "page": 1})
    assert data["code"] == "0"
    assert data["data"][0]["details"]
```

- [ ] **Step 4: 确认默认跳过 live、包可导入**

Run: `uv run pytest tests/ -v`
Expected: 选中的非 live 测试通过；`test_fetcher_live` 显示 deselected。

- [ ] **Step 5: 手动验证 live（需代理在跑）**

Run: `uv run pytest tests/test_fetcher_live.py -v -m live`
Expected: PASS（确认代理与接口可达）。

- [ ] **Step 6: Commit**

```bash
git add src/okx_monitor/config.py src/okx_monitor/fetcher.py tests/test_fetcher_live.py
git commit -m "feat: add Config and proxied Fetcher with retry"
```

---

### Task 5: 快照存取与 diff

**Files:**
- Create: `src/okx_monitor/snapshot.py`
- Test: `tests/test_snapshot.py`

**Interfaces:**
- Produces:
  - `load_snapshot(path: Path) -> dict | None` — 不存在返回 None
  - `save_snapshot(path: Path, data: dict) -> None`
  - `unified_diff(old: str, new: str, label: str) -> str` — 无差异返回 ""

- [ ] **Step 1: 写 `tests/test_snapshot.py` 失败测试**

```python
from pathlib import Path

from okx_monitor import snapshot


def test_load_missing_returns_none(tmp_path):
    assert snapshot.load_snapshot(tmp_path / "nope.json") is None


def test_save_then_load_roundtrip(tmp_path):
    p = tmp_path / "snap.json"
    snapshot.save_snapshot(p, {"a": 1, "中文": "值"})
    assert snapshot.load_snapshot(p) == {"a": 1, "中文": "值"}


def test_unified_diff_detects_change():
    d = snapshot.unified_diff("line1\nline2\n", "line1\nCHANGED\n", "doc")
    assert "CHANGED" in d
    assert d.startswith("---") or "@@" in d


def test_unified_diff_empty_when_same():
    assert snapshot.unified_diff("same\n", "same\n", "doc") == ""
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_snapshot.py -v`
Expected: FAIL（模块/函数缺失）

- [ ] **Step 3: 写 `snapshot.py`**

```python
import difflib
import json
from pathlib import Path


def load_snapshot(path: Path) -> dict | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def save_snapshot(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def unified_diff(old: str, new: str, label: str) -> str:
    if old == new:
        return ""
    diff = difflib.unified_diff(
        old.splitlines(keepends=True),
        new.splitlines(keepends=True),
        fromfile=f"{label} (基线)",
        tofile=f"{label} (本次)",
        n=2,
    )
    return "".join(diff)
```

- [ ] **Step 4: 运行确认通过**

Run: `uv run pytest tests/test_snapshot.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add src/okx_monitor/snapshot.py tests/test_snapshot.py
git commit -m "feat: add snapshot store and unified diff"
```

---

### Task 6: 编排逻辑

**Files:**
- Create: `src/okx_monitor/monitor.py`
- Test: `tests/test_monitor.py`

**Interfaces:**
- Consumes: `Config`、`parse.*`、`snapshot.*`、`models.*`，一个 `fetcher`-like 对象（鸭子类型，供测试注入假对象）
- Produces:
  - `run(config: Config, fetcher, now_ts: int) -> RunResult`
  - 内部：`build_doc_changes(docs, bodies, baseline) -> list[DocChange]`（纯函数，便于测试）

  快照布局（单文件 `snapshots/okx.json`）：
  ```json
  {"docs": {"<slug>": {"title": "...", "update_time": 0, "body": "..."}},
   "fees_text": "...",
   "seen_ann_urls": ["..."]}
  ```

- [ ] **Step 1: 写 `tests/test_monitor.py` 失败测试（用假 fetcher + 注入基线）**

```python
import json
import pathlib

from okx_monitor import monitor, snapshot
from okx_monitor.config import Config

FIX = pathlib.Path(__file__).parent / "fixtures"


class FakeFetcher:
    """按 URL 子串返回 fixture。"""

    def __init__(self):
        self.article_body = "第一行\n第二行\n"

    def get_json(self, url, params=None):
        if "search/articles" in url:
            return json.loads((FIX / "doc_list.json").read_text(encoding="utf-8"))
        if "unified/category" in url:
            return json.loads((FIX / "category.json").read_text(encoding="utf-8"))
        if "support/announcements" in url:
            name = "ann_new.json" if params["annType"].endswith("new-listings") else "ann_del.json"
            return json.loads((FIX / name).read_text(encoding="utf-8"))
        raise AssertionError(url)

    def get_text(self, url, params=None):
        if "/fees" in url:
            return (FIX / "fees.html").read_text(encoding="utf-8")
        if "/help/" in url:
            return (FIX / "article.html").read_text(encoding="utf-8")
        raise AssertionError(url)


def test_first_run_is_baseline(tmp_path):
    cfg = Config(snapshot_dir=tmp_path)
    res = monitor.run(cfg, FakeFetcher(), now_ts=1_782_900_000)
    assert res.is_baseline is True
    assert len(res.doc_inventory) == 21
    assert res.doc_changes == []
    assert res.fee_changed is False
    # 公告窗口内仍应列出（近3天）
    assert isinstance(res.anns_new, list)
    # 基线已落盘
    assert (tmp_path / "okx.json").exists()


def test_second_run_detects_doc_update(tmp_path):
    cfg = Config(snapshot_dir=tmp_path)
    # 先建基线
    monitor.run(cfg, FakeFetcher(), now_ts=1_782_900_000)
    # 篡改基线：把某文档 update_time 调小、body 改旧，制造"已更新"
    snap = snapshot.load_snapshot(tmp_path / "okx.json")
    any_slug = next(iter(snap["docs"]))
    snap["docs"][any_slug]["update_time"] = 1
    snap["docs"][any_slug]["body"] = "旧内容\n"
    snapshot.save_snapshot(tmp_path / "okx.json", snap)
    # 第二次运行
    res = monitor.run(cfg, FakeFetcher(), now_ts=1_782_900_000)
    assert res.is_baseline is False
    assert any(c.slug == any_slug and c.kind == "updated" for c in res.doc_changes)
    changed = next(c for c in res.doc_changes if c.slug == any_slug)
    assert changed.diff  # 有 diff 文本
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_monitor.py -v`
Expected: FAIL（`monitor.run` 缺失）

- [ ] **Step 3: 写 `monitor.py`**

```python
from datetime import UTC, datetime

from okx_monitor import parse, snapshot
from okx_monitor.config import (
    ANNOUNCEMENTS,
    ARTICLE_URL,
    CATEGORY,
    FEES_URL,
    SEARCH_ARTICLES,
    Config,
)
from okx_monitor.models import Announcement, DocChange, DocMeta, RunResult

ANN_TYPES = ["announcements-new-listings", "announcements-delistings"]


def _date(ts: int) -> str:
    return datetime.fromtimestamp(ts, tz=UTC).strftime("%Y-%m-%d")


def _fetch_docs(cfg: Config, fetcher) -> list[DocMeta]:
    cat = fetcher.get_json(CATEGORY, {"slug": cfg.category_slug})
    sid = parse.resolve_section_id(cat, cfg.section_slug)
    data = fetcher.get_json(SEARCH_ARTICLES, {"sectionIds": sid, "page": 1, "size": 50})
    return parse.parse_doc_list(data)


def _fetch_body(cfg: Config, fetcher, slug: str) -> str:
    html = fetcher.get_text(f"{ARTICLE_URL}/{slug}")
    return parse.extract_article_body(html)


def _fetch_announcements(cfg: Config, fetcher, now_ts: int) -> dict[str, list[Announcement]]:
    cutoff = now_ts - cfg.window_days * 86400
    result: dict[str, list[Announcement]] = {t: [] for t in ANN_TYPES}
    for ann_type in ANN_TYPES:
        page = 1
        while True:
            data = fetcher.get_json(ANNOUNCEMENTS, {"annType": ann_type, "page": page})
            anns = parse.parse_announcements(data, ann_type)
            if not anns:
                break
            in_window = [a for a in anns if a.ptime >= cutoff]
            result[ann_type].extend(in_window)
            # 倒序：本页最旧一条已早于窗口 → 后续页更早，停止
            if anns[-1].ptime < cutoff or page >= parse.announcements_total_pages(data):
                break
            page += 1
    return result


def build_doc_changes(
    docs: list[DocMeta], bodies: dict[str, str], baseline_docs: dict
) -> list[DocChange]:
    changes: list[DocChange] = []
    seen = set()
    for d in docs:
        seen.add(d.slug)
        base = baseline_docs.get(d.slug)
        if base is None:
            changes.append(
                DocChange(d.slug, d.title, d.url, _date(d.update_time), "new", "")
            )
            continue
        if d.update_time != base["update_time"] or bodies[d.slug] != base.get("body", ""):
            diff = snapshot.unified_diff(base.get("body", ""), bodies[d.slug], d.title)
            changes.append(
                DocChange(d.slug, d.title, d.url, _date(d.update_time), "updated", diff)
            )
    for slug, base in baseline_docs.items():
        if slug not in seen:
            changes.append(
                DocChange(slug, base["title"], "", "", "removed", "")
            )
    return changes


def run(config: Config, fetcher, now_ts: int) -> RunResult:
    snap_path = config.snapshot_dir / "okx.json"
    baseline = snapshot.load_snapshot(snap_path)
    is_baseline = baseline is None
    baseline = baseline or {"docs": {}, "fees_text": "", "seen_ann_urls": []}

    # --- 文档 ---
    docs = _fetch_docs(config, fetcher)
    # 仅对"可能变化"的文档抓正文：首次全抓做基线；后续抓 update_time 变化或新文档
    bodies: dict[str, str] = {}
    for d in docs:
        base = baseline["docs"].get(d.slug)
        if is_baseline or base is None or d.update_time != base["update_time"]:
            bodies[d.slug] = _fetch_body(config, fetcher, d.slug)
        else:
            bodies[d.slug] = base.get("body", "")

    doc_changes = [] if is_baseline else build_doc_changes(docs, bodies, baseline["docs"])

    # --- 费率 ---
    fees_text = parse.extract_fees_text(fetcher.get_text(FEES_URL))
    fee_diff = "" if is_baseline else snapshot.unified_diff(
        baseline.get("fees_text", ""), fees_text, "费率"
    )
    fee_changed = bool(fee_diff)

    # --- 公告 ---
    anns = _fetch_announcements(config, fetcher, now_ts)

    # --- 落盘新快照 ---
    new_snap = {
        "docs": {
            d.slug: {"title": d.title, "update_time": d.update_time, "body": bodies[d.slug]}
            for d in docs
        },
        "fees_text": fees_text,
        "seen_ann_urls": sorted(
            set(baseline.get("seen_ann_urls", []))
            | {a.url for lst in anns.values() for a in lst}
        ),
    }
    snapshot.save_snapshot(snap_path, new_snap)

    return RunResult(
        is_baseline=is_baseline,
        generated_at=datetime.fromtimestamp(now_ts, tz=UTC).strftime("%Y-%m-%d %H:%M UTC"),
        doc_changes=doc_changes,
        doc_inventory=docs,
        fee_changed=fee_changed,
        fee_diff=fee_diff,
        anns_new=anns["announcements-new-listings"],
        anns_del=anns["announcements-delistings"],
    )
```

- [ ] **Step 4: 运行确认通过**

Run: `uv run pytest tests/test_monitor.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add src/okx_monitor/monitor.py tests/test_monitor.py
git commit -m "feat: add monitor orchestration with baseline/diff logic"
```

---

### Task 7: 报告渲染

**Files:**
- Create: `src/okx_monitor/report.py`
- Test: `tests/test_report.py`

**Interfaces:**
- Consumes: `RunResult`
- Produces:
  - `render_markdown(result: RunResult, window_days: int) -> str`
  - `summary_lines(result: RunResult) -> list[str]` — 终端摘要

- [ ] **Step 1: 写 `tests/test_report.py` 失败测试**

```python
from okx_monitor import report
from okx_monitor.models import Announcement, DocChange, DocMeta, RunResult


def _baseline_result():
    return RunResult(
        is_baseline=True,
        generated_at="2026-06-30 03:00 UTC",
        doc_inventory=[DocMeta("s1", "基础委托类型", "/help/s1", 1_782_000_000, 1_700_000_000)],
        anns_new=[Announcement("某币上线", "http://x/1", 1_782_800_000, "announcements-new-listings")],
    )


def test_markdown_marks_baseline():
    md = report.render_markdown(_baseline_result(), window_days=3)
    assert "基线建立" in md
    assert "基础委托类型" in md
    assert "某币上线" in md


def test_markdown_shows_doc_diff():
    res = RunResult(
        is_baseline=False,
        generated_at="2026-06-30 03:00 UTC",
        doc_changes=[DocChange("s1", "基础委托类型", "/help/s1", "2026-06-29", "updated", "@@ -1 +1 @@\n-旧\n+新\n")],
    )
    md = report.render_markdown(res, window_days=3)
    assert "基础委托类型" in md
    assert "+新" in md
    assert "更新" in md


def test_summary_lines_nonempty():
    assert report.summary_lines(_baseline_result())
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_report.py -v`
Expected: FAIL

- [ ] **Step 3: 写 `report.py`**

```python
from okx_monitor.models import RunResult

_KIND_CN = {"new": "新增", "updated": "更新", "removed": "下架"}


def render_markdown(result: RunResult, window_days: int) -> str:
    lines: list[str] = []
    tag = "（基线建立，无 diff）" if result.is_baseline else ""
    lines.append(f"# OKX 监控报告 {result.generated_at} {tag}".rstrip())

    # 一、交易规则
    lines.append("\n## 一、交易规则")
    if result.is_baseline:
        lines.append(f"\n首次运行，记录 {len(result.doc_inventory)} 篇文档为基线：\n")
        for d in result.doc_inventory:
            lines.append(f"- {d.title} — 更新于 {_d(d.update_time)} — https://www.okx.com{d.url}")
    elif not result.doc_changes:
        lines.append("\n相对基线无变化。")
    else:
        lines.append(f"\n相对基线有变化的文档（{len(result.doc_changes)} 篇）：\n")
        for c in result.doc_changes:
            head = f"### [{_KIND_CN.get(c.kind, c.kind)}] {c.title}"
            if c.update_date:
                head += f" — 更新于 {c.update_date}"
            lines.append(head)
            if c.url:
                lines.append(f"https://www.okx.com{c.url}" if c.url.startswith("/") else c.url)
            if c.diff:
                lines.append("\n```diff")
                lines.append(c.diff.rstrip())
                lines.append("```")
            lines.append("")

    # 二、费率规则
    lines.append("\n## 二、费率规则")
    if result.is_baseline:
        lines.append("\n已记录费率页为基线，无 diff。")
    elif result.fee_changed:
        lines.append("\n费率页**有变化**：\n")
        lines.append("```diff")
        lines.append(result.fee_diff.rstrip())
        lines.append("```")
    else:
        lines.append("\n费率页无变化。")

    # 三、上下币公告
    lines.append(f"\n## 三、上下币公告（近 {window_days} 天）")
    lines.append(f"\n### 上币（{len(result.anns_new)} 条）")
    for a in result.anns_new:
        lines.append(f"- {a.title} — {_d(a.ptime)} — {a.url}")
    lines.append(f"\n### 下币（{len(result.anns_del)} 条）")
    for a in result.anns_del:
        lines.append(f"- {a.title} — {_d(a.ptime)} — {a.url}")

    return "\n".join(lines) + "\n"


def summary_lines(result: RunResult) -> list[str]:
    if result.is_baseline:
        return [
            f"[基线] 文档 {len(result.doc_inventory)} 篇已记录",
            f"[基线] 上币 {len(result.anns_new)} / 下币 {len(result.anns_del)}（近窗口）",
        ]
    return [
        f"交易规则变化：{len(result.doc_changes)} 篇",
        f"费率：{'有变化' if result.fee_changed else '无变化'}",
        f"上币 {len(result.anns_new)} / 下币 {len(result.anns_del)}（近窗口）",
    ]


def _d(ts: int) -> str:
    from datetime import UTC, datetime

    return datetime.fromtimestamp(ts, tz=UTC).strftime("%Y-%m-%d")
```

- [ ] **Step 4: 运行确认通过**

Run: `uv run pytest tests/test_report.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add src/okx_monitor/report.py tests/test_report.py
git commit -m "feat: add markdown report and terminal summary"
```

---

### Task 8: CLI 入口与端到端

**Files:**
- Create: `src/okx_monitor/__main__.py`
- Modify: `pyproject.toml`（加 script 入口，可选）

**Interfaces:**
- Consumes: 全部模块
- Produces: `python -m okx_monitor` 运行：抓取→对比→写报告到 `reports/okx-YYYYMMDD-HHMM.md`→打印摘要。

- [ ] **Step 1: 写 `__main__.py`**

```python
import sys
from datetime import UTC, datetime
from pathlib import Path

from okx_monitor.config import Config
from okx_monitor.fetcher import Fetcher
from okx_monitor.monitor import run
from okx_monitor.report import render_markdown, summary_lines


def main() -> int:
    cfg = Config()
    now = datetime.now(tz=UTC)
    now_ts = int(now.timestamp())
    try:
        with Fetcher(cfg) as fetcher:
            result = run(cfg, fetcher, now_ts)
    except Exception as e:  # noqa: BLE001 — 顶层兜底，明确报错不静默
        print(f"运行失败: {e}", file=sys.stderr)
        return 1

    md = render_markdown(result, cfg.window_days)
    cfg.report_dir.mkdir(parents=True, exist_ok=True)
    out = cfg.report_dir / f"okx-{now.strftime('%Y%m%d-%H%M')}.md"
    out.write_text(md, encoding="utf-8")

    print(f"\n报告已写入: {out}\n")
    for line in summary_lines(result):
        print("  " + line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: 首次运行（建立基线，需代理在跑）**

Run: `uv run python -m okx_monitor`
Expected: 打印「报告已写入: reports/okx-...md」+ `[基线]` 摘要；`snapshots/okx.json` 生成，含 21 篇 docs。

- [ ] **Step 3: 查看报告内容**

Run: `cat reports/okx-*.md | head -40`
Expected: 标题含「基线建立」，交易规则列出 21 篇及更新日期，公告分上币/下币。

- [ ] **Step 4: 第二次运行（验证 diff 路径不报错）**

Run: `uv run python -m okx_monitor`
Expected: 退出码 0；摘要显示「交易规则变化：N 篇」「费率：无变化/有变化」。若两次间无真实更新，N 可能为 0，属正常。

- [ ] **Step 5: 全量测试**

Run: `uv run pytest -v && uv run ruff check src tests`
Expected: 全部 passed；ruff 无报错。

- [ ] **Step 6: Commit**

```bash
git add src/okx_monitor/__main__.py pyproject.toml
git commit -m "feat: add CLI entrypoint and end-to-end run"
```

---

## Self-Review 检查

- **Spec 覆盖**：交易规则(Task 3/6)、费率(Task 3/6)、上下币公告(Task 3/6)、基线策略(Task 6 `is_baseline`)、代理+中文头(Task 4)、报告(Task 7)、诚实边界(基线无 diff，解析失败抛异常) 均有任务覆盖。
- **类型一致**：`DocMeta.update_time`(秒) 在 parse/monitor/report 一致；`Announcement.ptime` 秒；`parse_announcements` 做毫秒→秒转换，下游统一秒。
- **占位符**：无 TBD/TODO；所有步骤含真实代码与命令。
- **歧义**：公告"近 N 天"以 `pTime` 秒 vs `now_ts - window_days*86400` 比较，明确。文档"变化"判定 = `update_time` 变化或正文 diff 非空，明确。

## 待实现期注意

- `category.json` 的 section 对象结构若与 `resolve_section_id` 正则不符，按 Task 3 Step 4 的提示用递归 `walk` 兜底（代码已含）。
- 若某篇文章 `extract_article_body` 抛异常（个别页面结构特殊），顶层会整体失败——实现时可在 `_fetch_body` 调用处按 slug 容错（记录该篇解析失败、继续其余），属合理增强，但需在报告中显式列出失败篇目（no silent-wrong）。
