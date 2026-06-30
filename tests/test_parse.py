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
    anns = parse.parse_announcements(_json("ann_new.json"), "SENTINEL-not-a-real-type")
    assert anns, "应有上币公告"
    a = anns[0]
    assert a.ann_type == "announcements-new-listings"  # 来自 item 的 annType 字段，而非传入参数
    assert a.ptime > 1_700_000_000
    assert a.url.startswith("http")


def test_extract_article_body_nonempty_chinese():
    body = parse.extract_article_body((FIX / "article.html").read_text(encoding="utf-8"))
    assert len(body) > 200
    assert "委托" in body


def test_extract_fees_text_is_stable_fee_data():
    html = (FIX / "fees.html").read_text(encoding="utf-8")
    text = parse.extract_fees_text(html)
    # 结果必须是合法 JSON
    obj = json.loads(text)
    assert obj, "feeDataInfo 不应为空"
    # 包含稳定的费率表结构标识
    assert "feeTables" in text
    assert "tableData" in text
    assert "现货" in text
    # 核心回归守卫：不含 traceId（volatile 字段已被剔除）
    assert "traceId" not in text
    # 确定性：同一 HTML 两次调用结果完全一致
    assert parse.extract_fees_text(html) == text


def test_resolve_section_id():
    sid = parse.resolve_section_id(
        _json("category.json"),
        "product-documentation-introduction-to-basic-trading-rules",
    )
    assert sid == "3HsUPMtNszv47YPMMMx8Dw"
