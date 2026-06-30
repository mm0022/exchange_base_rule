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
