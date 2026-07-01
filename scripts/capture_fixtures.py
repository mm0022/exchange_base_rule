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

BINANCE_HEADERS = {**HEADERS, "lang": "zh-CN"}
BINANCE_TARGETS = {
    "binance_ann_new.json": "https://www.binance.com/bapi/composite/v1/public/cms/article/list/query?type=1&catalogId=48&pageNo=1&pageSize=20",
    "binance_ann_del.json": "https://www.binance.com/bapi/composite/v1/public/cms/article/list/query?type=1&catalogId=161&pageNo=1&pageSize=20",
    # catalogId=4 数字货币衍生品（大叶需翻页；pageNo 是全树全局分页，catalogId 在 p>=2 被忽略）
    "binance_faq_tree.json": "https://www.binance.com/bapi/composite/v1/public/cms/article/list/query?type=2&catalogId=4&pageNo=1&pageSize=20",
    "binance_faq_tree_p2.json": "https://www.binance.com/bapi/composite/v1/public/cms/article/list/query?type=2&catalogId=4&pageNo=2&pageSize=20",
    # catalogId=3 现货杠杆（各叶均 ≤20，单页即全量）
    "binance_faq_tree3.json": "https://www.binance.com/bapi/composite/v1/public/cms/article/list/query?type=2&catalogId=3&pageNo=1&pageSize=20",
}

def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with httpx.Client(proxy=PROXY, headers=HEADERS, timeout=20) as c:
        for name, url in TARGETS.items():
            r = c.get(url)
            r.raise_for_status()
            (OUT / name).write_text(r.text, encoding="utf-8")
            print(f"saved {name} ({len(r.text)} bytes)")

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

if __name__ == "__main__":
    main()
