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
    """文章页 SSR 渲染，正文在 <article> 元素中。"""
    tree = HTMLParser(html)
    nodes = tree.css("article")
    if not nodes:
        raise ValueError("article body: 未找到 <article> 元素，页面结构可能已变更")
    return nodes[0].text(separator="\n", strip=True)


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
