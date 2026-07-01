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
