import time

import httpx

from okx_monitor.config import Config


class Fetcher:
    def __init__(self, config: Config):
        self.cfg = config
        self._client = httpx.Client(
            proxy=config.proxy,
            timeout=config.timeout,
            headers={
                "User-Agent": config.user_agent,
                "Accept-Language": config.accept_language,
            },
        )

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self._client.close()

    def _get(self, url: str, params: dict | None) -> httpx.Response:
        last: Exception | None = None
        for attempt in range(self.cfg.retries):
            try:
                r = self._client.get(url, params=params)
                r.raise_for_status()
                time.sleep(self.cfg.request_delay)
                return r
            except (httpx.HTTPError,) as e:
                last = e
                time.sleep(1.0 * (attempt + 1))
        raise RuntimeError(f"请求失败（重试{self.cfg.retries}次）: {url} -> {last}")

    def get_json(self, url: str, params: dict | None = None) -> dict:
        return self._get(url, params).json()

    def get_text(self, url: str, params: dict | None = None) -> str:
        return self._get(url, params).text
