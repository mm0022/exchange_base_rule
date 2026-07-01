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
