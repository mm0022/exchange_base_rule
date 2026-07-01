"""纯解析：输入原始响应文本/JSON，输出数据模型。无网络。"""
import json

from selectolax.parser import HTMLParser

from exchange_monitor.models import Announcement, DocMeta


def parse_doc_list(api_json: dict) -> list[DocMeta]:
    try:
        items = api_json["data"]["list"]
    except (KeyError, TypeError) as e:
        raise ValueError("doc list: 响应缺少 data.list，接口可能已变更") from e
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
    """从费率页嵌入 JSON 中提取稳定的 feeDataInfo 对象并返回确定性序列化字符串。

    页面 body 含有 traceId 等易变字段，直接取 body text 会导致每次请求产生虚假变化。
    feeDataInfo 只含费率表数据，两次请求完全一致。
    """
    key = '"feeDataInfo":'
    idx = html.find(key)
    if idx == -1:
        raise ValueError("fees: 未找到 feeDataInfo，页面结构可能已变更")

    # 从 key 之后找第一个 '{'
    start = html.find("{", idx + len(key))
    if start == -1:
        raise ValueError("fees: feeDataInfo 后未找到 JSON 对象")

    # 用 JSON parser 提取完整对象，正确处理字符串值中的大括号
    obj, _ = json.JSONDecoder().raw_decode(html, start)
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2)


def resolve_section_id(response: dict, section_slug: str) -> str:
    """从分类或 section 接口响应里按 slug 找 section id。"""
    # 递归搜索
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

    sid = walk(response)
    if not sid:
        raise ValueError(f"未找到 section '{section_slug}' 的 id，分类接口可能已变更")
    return sid
