import time

import httpx

from exchange_monitor.config import Config


class Fetcher:
    def __init__(self, config: Config):
        self.cfg = config
        self._default_headers = {
            "User-Agent": config.user_agent,
            "Accept-Language": config.accept_language,
        }
        # follow_redirects：交易所文章页常有 301/308（如 OKX /en/help→/help、
        # Bybit 条款页→/legal）；跟随后取到最终页面，解析失败的仍由各适配器逐篇容错兜底。
        self._client = httpx.Client(
            proxy=config.proxy, timeout=config.timeout, follow_redirects=True
        )

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self._client.close()

    def _merge_headers(self, headers: dict | None) -> dict:
        merged = dict(self._default_headers)
        if headers:
            merged.update(headers)
        return merged

    def _get(self, url: str, params: dict | None, headers: dict | None) -> httpx.Response:
        last = None
        for attempt in range(self.cfg.retries):
            try:
                r = self._client.get(url, params=params, headers=self._merge_headers(headers))
                if r.status_code == 429:
                    last = httpx.HTTPStatusError("429 Too Many Requests", request=r.request, response=r)
                    time.sleep(self.cfg.rate_limit_backoff * (attempt + 1))
                    continue
                r.raise_for_status()
                time.sleep(self.cfg.request_delay)
                return r
            except httpx.HTTPError as e:
                last = e
                time.sleep(1.0 * (attempt + 1))
        raise RuntimeError(f"请求失败（重试{self.cfg.retries}次）: {url} -> {last}")

    def get_json(self, url: str, params: dict | None = None, headers: dict | None = None) -> dict:
        return self._get(url, params, headers).json()

    def get_text(self, url: str, params: dict | None = None, headers: dict | None = None) -> str:
        return self._get(url, params, headers).text

    def post_json(self, url: str, payload: dict, headers: dict | None = None) -> dict:
        last: Exception | None = None
        for attempt in range(self.cfg.retries):
            try:
                r = self._client.post(url, json=payload, headers=self._merge_headers(headers))
                r.raise_for_status()
                time.sleep(self.cfg.request_delay)
                return {"status": r.status_code, "text": r.text}
            except httpx.HTTPError as e:
                last = e
                time.sleep(1.0 * (attempt + 1))
        raise RuntimeError(f"POST 失败（重试{self.cfg.retries}次）: {url} -> {last}")
