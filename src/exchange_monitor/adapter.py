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

    def fetch_fees(self, fetcher, config) -> str | None:
        """返回费率快照文本；返回 None 表示该交易所不监控费率。
        注意：不要返回空串 ""——那会被当作"支持费率但内容为空"，渲染出空费率段。"""
        ...
