"""Tier 1: title(s) to raw wikitext, via MediaWiki's Special:Export.

See docs/specs/001-fetch.md.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import random
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypedDict
from urllib.parse import quote
from xml.etree.ElementTree import Element

import defusedxml.ElementTree as ET
import requests

from .errors import ConfigurationError, ExportParseError, FetchError, RateLimitError

logger = logging.getLogger("special_export_mcp")

REPO_URL = "https://github.com/Mirza404/special-export-mcp"
RETRYABLE_STATUS = {429, 500, 502, 503, 504}
NON_RETRYABLE_STATUS = {400, 403, 404}
MAX_BATCH_SIZE = 20


class _PageInfo(TypedDict):
    title: str
    page_id: int | None
    wikitext: str
    revision_id: int | None
    revision_timestamp: str | None


@dataclass
class FetchResult:
    """One page's fetch outcome. Internal to fetch.py and client.py."""

    requested_title: str
    exists: bool
    resolved_title: str | None = None
    wikitext: str | None = None
    page_id: int | None = None
    revision_id: int | None = None
    revision_timestamp: str | None = None
    error: str | None = None


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _build_user_agent(user_agent: str | None, user_agent_contact: str | None) -> str:
    if user_agent is not None:
        if not user_agent.strip():
            raise ConfigurationError("user_agent must not be empty")
        return user_agent
    contact = user_agent_contact or os.environ.get("SPECIAL_EXPORT_CONTACT") or REPO_URL
    from . import __version__

    return f"special-export-mcp/{__version__} ({contact})"


def _title_for_path(title: str) -> str:
    return quote(title.replace(" ", "_"), safe="")


def _normalize_for_match(title: str) -> str:
    return title.replace("_", " ").strip().lower()


def _cache_path(cache_dir: Path, title: str) -> Path:
    digest = hashlib.sha256(title.encode("utf-8")).hexdigest()[:16]
    return cache_dir / f"{digest}.json"


class Fetcher:
    """Fetches raw wikitext for one or more titles from Special:Export."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        language: str = "en",
        user_agent: str | None = None,
        user_agent_contact: str | None = None,
        timeout: tuple[float, float] = (5.0, 30.0),
        max_retries: int = 3,
        min_request_interval: float = 1.0,
        cache_dir: str | Path | None = None,
        session: requests.Session | None = None,
    ) -> None:
        self.base_url = (base_url or f"https://{language}.wikipedia.org").rstrip("/")
        self.user_agent = _build_user_agent(user_agent, user_agent_contact)
        self.timeout = timeout
        self.max_retries = max_retries
        self.min_request_interval = min_request_interval
        self.cache_dir = Path(cache_dir) if cache_dir else None
        if self.cache_dir is not None:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._session = session or requests.Session()
        self._last_request_at: float | None = None

    def close(self) -> None:
        self._session.close()

    # -- politeness ----------------------------------------------------

    def _throttle(self) -> None:
        if self._last_request_at is None:
            return
        elapsed = time.monotonic() - self._last_request_at
        remaining = self.min_request_interval - elapsed
        if remaining > 0:
            time.sleep(remaining)

    def _mark_request(self) -> None:
        self._last_request_at = time.monotonic()

    # -- on-disk cache ---------------------------------------------------

    def _cache_get(self, title: str) -> FetchResult | None:
        if self.cache_dir is None:
            return None
        path = _cache_path(self.cache_dir, title)
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        logger.debug("cache hit for %r at %s", title, path)
        return FetchResult(
            requested_title=title,
            exists=True,
            resolved_title=data["resolved_title"],
            wikitext=data["wikitext"],
            page_id=data["page_id"],
            revision_id=data["revision_id"],
            revision_timestamp=data["revision_timestamp"],
        )

    def _cache_put(self, title: str, result: FetchResult) -> None:
        if self.cache_dir is None or not result.exists:
            return
        path = _cache_path(self.cache_dir, title)
        payload = {
            "requested_title": result.requested_title,
            "resolved_title": result.resolved_title,
            "wikitext": result.wikitext,
            "page_id": result.page_id,
            "revision_id": result.revision_id,
            "revision_timestamp": result.revision_timestamp,
            "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        path.write_text(json.dumps(payload), encoding="utf-8")

    # -- HTTP with retry ---------------------------------------------------

    def _request(self, method: str, url: str, **kwargs: Any) -> requests.Response:
        headers = kwargs.pop("headers", {})
        headers["User-Agent"] = self.user_agent
        last_exc: Exception | None = None

        for attempt in range(self.max_retries + 1):
            self._throttle()
            try:
                self._mark_request()
                response = self._session.request(
                    method, url, headers=headers, timeout=self.timeout, **kwargs
                )
            except (requests.ConnectionError, requests.Timeout) as exc:
                last_exc = exc
                if attempt >= self.max_retries:
                    raise FetchError(f"network error fetching {url}: {exc}") from exc
                logger.warning("network error on attempt %d for %s: %s", attempt + 1, url, exc)
                self._sleep_backoff(attempt, None)
                continue

            if response.status_code in NON_RETRYABLE_STATUS:
                raise FetchError(
                    f"non-retryable HTTP {response.status_code} for {url}",
                    status_code=response.status_code,
                )

            if response.status_code in RETRYABLE_STATUS:
                if attempt >= self.max_retries:
                    if response.status_code == 429:
                        raise RateLimitError(
                            f"HTTP 429 for {url} after {attempt + 1} attempts",
                            status_code=429,
                        )
                    raise FetchError(
                        f"HTTP {response.status_code} for {url} after {attempt + 1} attempts",
                        status_code=response.status_code,
                    )
                logger.warning(
                    "HTTP %d on attempt %d for %s", response.status_code, attempt + 1, url
                )
                self._sleep_backoff(attempt, response.headers.get("Retry-After"))
                continue

            response.raise_for_status()
            logger.info("fetched %s", url)
            return response

        assert last_exc is not None
        raise FetchError(f"network error fetching {url}: {last_exc}") from last_exc

    def _sleep_backoff(self, attempt: int, retry_after: str | None) -> None:
        if retry_after is not None:
            try:
                time.sleep(float(retry_after))
                return
            except ValueError:
                pass
        base = 2**attempt
        time.sleep(random.uniform(0, base))

    # -- public API -----------------------------------------------------

    def fetch_wikitext(self, title: str, *, refresh: bool = False) -> FetchResult:
        return self.fetch_many([title], refresh=refresh)[0]

    def fetch_many(self, titles: list[str], *, refresh: bool = False) -> list[FetchResult]:
        if not titles:
            return []

        results: dict[int, FetchResult] = {}
        to_fetch_indices: list[int] = []
        for i, title in enumerate(titles):
            cached = None if refresh else self._cache_get(title)
            if cached is not None:
                results[i] = cached
            else:
                to_fetch_indices.append(i)

        for batch_start in range(0, len(to_fetch_indices), MAX_BATCH_SIZE):
            batch_indices = to_fetch_indices[batch_start : batch_start + MAX_BATCH_SIZE]
            batch_titles = [titles[i] for i in batch_indices]
            if len(batch_titles) == 1:
                batch_results = [self._fetch_single(batch_titles[0])]
            else:
                batch_results = self._fetch_batch(batch_titles)
            for i, result in zip(batch_indices, batch_results, strict=True):
                results[i] = result
                self._cache_put(titles[i], result)

        return [results[i] for i in range(len(titles))]

    def _fetch_single(self, title: str) -> FetchResult:
        url = f"{self.base_url}/wiki/Special:Export/{_title_for_path(title)}?redirects=1"
        response = self._request("GET", url)
        page_map = self._parse_export_xml(response.text)
        if not page_map:
            return FetchResult(
                requested_title=title,
                exists=False,
                error=f"Page not found: {title}",
            )
        # redirects=1 collapses a redirect into its target: exactly one page
        # comes back even when its title differs from what was requested.
        page = next(iter(page_map.values()))
        return FetchResult(
            requested_title=title,
            exists=True,
            resolved_title=page["title"],
            wikitext=page["wikitext"],
            page_id=page["page_id"],
            revision_id=page["revision_id"],
            revision_timestamp=page["revision_timestamp"],
        )

    def _fetch_batch(self, titles: list[str]) -> list[FetchResult]:
        url = f"{self.base_url}/w/index.php?title=Special:Export&action=submit"
        data = {
            "pages": "\n".join(titles),
            "curonly": "1",
            "wpDownload": "0",
            "redirects": "1",
        }
        response = self._request("POST", url, data=data)
        page_map = self._parse_export_xml(response.text)
        return self._resolve_batch(titles, page_map)

    @staticmethod
    def _resolve_batch(titles: list[str], page_map: dict[str, _PageInfo]) -> list[FetchResult]:
        pages_in_order = list(page_map.values())
        claimed = [False] * len(pages_in_order)
        result_by_index: dict[int, FetchResult] = {}
        unmatched_indices: list[int] = []

        for i, title in enumerate(titles):
            target = _normalize_for_match(title)
            match_pos = next(
                (
                    j
                    for j, page in enumerate(pages_in_order)
                    if not claimed[j] and _normalize_for_match(page["title"]) == target
                ),
                None,
            )
            if match_pos is not None:
                claimed[match_pos] = True
                page = pages_in_order[match_pos]
                result_by_index[i] = FetchResult(
                    requested_title=title,
                    exists=True,
                    resolved_title=page["title"],
                    wikitext=page["wikitext"],
                    page_id=page["page_id"],
                    revision_id=page["revision_id"],
                    revision_timestamp=page["revision_timestamp"],
                )
            else:
                unmatched_indices.append(i)

        # Leftover requests paired, in order, with leftover pages: these are
        # the redirect cases, where the returned title differs from the
        # request and an exact-match pass above could not find it.
        leftover_pages = [p for j, p in enumerate(pages_in_order) if not claimed[j]]
        for i, page in zip(unmatched_indices, leftover_pages, strict=False):
            result_by_index[i] = FetchResult(
                requested_title=titles[i],
                exists=True,
                resolved_title=page["title"],
                wikitext=page["wikitext"],
                page_id=page["page_id"],
                revision_id=page["revision_id"],
                revision_timestamp=page["revision_timestamp"],
            )
        for i in unmatched_indices[len(leftover_pages) :]:
            result_by_index[i] = FetchResult(
                requested_title=titles[i],
                exists=False,
                error=f"Page not found: {titles[i]}",
            )

        return [result_by_index[i] for i in range(len(titles))]

    @staticmethod
    def _parse_export_xml(xml_text: str) -> dict[str, _PageInfo]:
        try:
            root = ET.fromstring(xml_text)
        except (ET.ParseError, ValueError) as exc:
            raise ExportParseError(f"invalid export XML: {exc}", raw=xml_text[:500]) from exc

        pages: dict[str, _PageInfo] = {}
        for page_el in root:
            if _local_name(page_el.tag) != "page":
                continue

            title_text: str | None = None
            id_text: str | None = None
            revision_el: Element | None = None
            for child in page_el:
                name = _local_name(child.tag)
                if name == "title":
                    title_text = child.text
                elif name == "id" and id_text is None:
                    id_text = child.text
                elif name == "revision":
                    revision_el = child

            if title_text is None or revision_el is None:
                continue

            text_value: str | None = None
            rev_id_text: str | None = None
            timestamp_text: str | None = None
            for child in revision_el:
                name = _local_name(child.tag)
                if name == "text":
                    text_value = child.text
                elif name == "id":
                    rev_id_text = child.text
                elif name == "timestamp":
                    timestamp_text = child.text

            if text_value is None:
                raise ExportParseError(
                    f"page {title_text!r} has no revision text", title=title_text
                )

            pages[title_text] = {
                "title": title_text,
                "page_id": int(id_text) if id_text else None,
                "wikitext": text_value,
                "revision_id": int(rev_id_text) if rev_id_text else None,
                "revision_timestamp": timestamp_text,
            }
        return pages
