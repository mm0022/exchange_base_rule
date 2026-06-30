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
