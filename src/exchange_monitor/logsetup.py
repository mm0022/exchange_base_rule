"""日志配置：仅由入口 __main__ 调用一次。

库模块（monitor / fetcher / adapters）只 `logging.getLogger(__name__)` 记录，
不在模块内配置 handler——这样 pytest 导入它们时不产生日志文件、不污染测试输出。
"""
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

_FMT = "%(asctime)s %(levelname)s %(name)s %(message)s"


def setup_logging(log_dir: Path) -> None:
    """配置 `exchange_monitor` 父 logger：文件 handler=DEBUG(逐篇/翻页/请求，带轮转)，
    控制台 handler=INFO(每家摘要)。幂等，可重复调用。"""
    log_dir.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger("exchange_monitor")
    root.setLevel(logging.DEBUG)
    root.handlers.clear()  # 幂等：重复调用不叠加 handler
    root.propagate = False

    fileh = RotatingFileHandler(
        log_dir / "monitor.log", maxBytes=2_000_000, backupCount=5, encoding="utf-8"
    )
    fileh.setLevel(logging.DEBUG)
    fileh.setFormatter(logging.Formatter(_FMT))

    console = logging.StreamHandler()  # 默认 stderr
    console.setLevel(logging.INFO)
    console.setFormatter(logging.Formatter(_FMT))

    root.addHandler(fileh)
    root.addHandler(console)
