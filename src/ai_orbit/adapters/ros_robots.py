from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import re
from typing import Any

from src.ai_orbit.adapters.base import SourceAdapter
from src.ai_orbit.config import AIOrbitSettings
from src.ai_orbit.models import RawEntityRecord, SourceFeasibility
from src.ai_orbit.utils.http import FailureClass, HttpRetryConfig, JsonHttpClient, SourceFetchError
from src.ai_orbit.utils.url import is_valid_http_url, normalize_url


_ROBOT_POST_PATTERN = re.compile(r"^_posts/\d{4}-\d{2}-\d{2}-(?P<slug>.+)\.md$")
_ALLOWED_ROBOT_CLASSES = {"aerial", "ground", "manipulator", "marine", "component"}
_NON_ROBOT_DESCRIPTION_PATTERNS = (
    re.compile(r"^\s*ros-industrial support for\b", re.I),
    re.compile(r"^\s*this repository is part of\b", re.I),
)


class RosRobotsCatalogAdapter(SourceAdapter):
    """Ingests a bounded sample of actual robot entities from robots.ros.org.

    The source repository powers robots.ros.org and stores one Markdown/Jekyll
    post per robot entry. This adapter treats those posts as robot catalog
    records, not as software repositories, and keeps manufacturer/provider null
    unless a specific source field supplies it.
    """

    name = "ROS Robots Catalog"

    def __init__(self, settings: AIOrbitSettings):
        self.settings = settings
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "GraphOneSlice-AIOrbit-VerticalSlice/0.1",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if settings.github_token:
            headers["Authorization"] = f"Bearer {settings.github_token}"
        self.client = JsonHttpClient(
            timeout_seconds=settings.http_timeout_seconds,
            verify=settings.ca_bundle,
            headers=headers,
            retry=HttpRetryConfig(
                max_attempts=settings.max_retry_attempts,
                backoff_base_seconds=settings.retry_backoff_base_seconds,
                backoff_max_seconds=settings.retry_backoff_max_seconds,
                jitter_seconds=settings.retry_jitter_seconds,
            ),
        )
        self._post_items: list[dict[str, Any]] = []
        self._sample_rows: list[dict[str, Any]] = []
        self._response_url: str | None = None

    async def verify(self) -> SourceFeasibility:
        try:
            items = await self._fetch_post_listing()
            sample_items = items[: min(len(items), max(self.settings.ros_robots_limit * 2, 20))]
            sample_rows = await self._fetch_posts(sample_items)
            usable_sample = [row for row in sample_rows if self._is_candidate_robot(row)]
            self._post_items = items
            self._sample_rows = sample_rows
            status = "usable" if usable_sample else "partial"
            return SourceFeasibility(
                source_name=self.name,
                source_type="GitHub-hosted Jekyll robot catalog",
                access_method="GitHub REST contents API for ros-infrastructure/robots.ros.org _posts Markdown records",
                url=self._response_url or self.settings.ros_robots_catalog_api_url,
                status=status,  # type: ignore[arg-type]
                domain="Robots",
                http_status=200,
                pagination="GitHub contents directory listing returns all _posts files for this repository path; adapter ingests a bounded deterministic sample",
                available_fields=[
                    "title",
                    "date",
                    "description",
                    "introduction",
                    "main-class",
                    "tags",
                    "website",
                    "wiki_homepage",
                    "source_path",
                    "html_url",
                ],
                required_fields=["title", "introduction or description/body", "catalog post path", "catalog URL or website/wiki URL"],
                authentication_required=False,
                rate_limit_observed={},
                freshness="front-matter date is the robots.ros.org catalog post date; it is preserved as catalog_posted_at and not treated as robot launch date",
                anti_bot_js="GitHub REST API returned Markdown catalog files as JSON/base64; no browser automation or JavaScript required",
                inventory_evidence=f"post files listed={len(items)}; sampled post files={len(sample_rows)}; sampled usable robot records={len(usable_sample)}",
                company_identity_quality="catalog identifies robot names, classes, tags, websites/wiki pages; manufacturer/provider is not a dedicated field and remains null unless later source evidence supplies it",
                ai_relevance="robots.ros.org is an index of ROS robots; accepted records are actual robot catalog posts, not robotics software repositories",
                actual_crawl_feasibility="usable for bounded Robot records with direct robot identity from catalog posts",
                record_volume_estimate=f"bounded by AI_ORBIT_ROS_ROBOTS_LIMIT={self.settings.ros_robots_limit}; listed inventory={len(items)}",
                failure_behavior="403/404/malformed JSON/Markdown are source failures; 429/5xx use bounded retry via the shared HTTP client",
                yielded_usable_records=0,
            )
        except SourceFetchError as exc:
            return SourceFeasibility(
                source_name=self.name,
                source_type="GitHub-hosted Jekyll robot catalog",
                access_method="GitHub REST contents API for ros-infrastructure/robots.ros.org _posts Markdown records",
                url=self.settings.ros_robots_catalog_api_url,
                status="unusable",
                domain="Robots",
                http_status=exc.status_code,
                required_fields=["title", "introduction or description/body", "catalog post path"],
                authentication_required=False,
                anti_bot_js="not determined; API request failed",
                actual_crawl_feasibility="not usable from this environment based on observed failure",
                failure_behavior=f"{exc.failure_class.value}: {exc}",
            )

    async def discover(self) -> list[RawEntityRecord]:
        if not self._post_items:
            await self.verify()
        now = datetime.now(timezone.utc)
        records: list[RawEntityRecord] = []
        seen_slugs: set[str] = set()
        start_index = len(self._sample_rows)
        rows = list(self._sample_rows)

        # Reuse the verification sample first, then fetch more posts only if the
        # sample did not yield the configured bounded record count.
        while len(records) < self.settings.ros_robots_limit:
            for row in rows:
                if len(records) >= self.settings.ros_robots_limit:
                    break
                record = self._record_from_row(row, fetched_at=now)
                if record is None:
                    continue
                slug = record.metadata["robot"]["catalog_slug"]
                if slug in seen_slugs:
                    continue
                seen_slugs.add(slug)
                records.append(record)
            if len(records) >= self.settings.ros_robots_limit or start_index >= len(self._post_items):
                break
            next_items = self._post_items[start_index : start_index + max(self.settings.ros_robots_limit, 15)]
            start_index += len(next_items)
            rows = await self._fetch_posts(next_items)
        return records

    async def _fetch_post_listing(self) -> list[dict[str, Any]]:
        response = await self.client.get_json(self.settings.ros_robots_catalog_api_url)
        self._response_url = response.url
        data = response.data
        if not isinstance(data, list):
            raise SourceFetchError(FailureClass.MALFORMED_JSON, "ROS robots catalog listing was not a JSON array")
        items = [item for item in data if isinstance(item, dict) and item.get("type") == "file" and self._slug_from_path(str(item.get("path") or ""))]
        if not items:
            raise SourceFetchError(FailureClass.MALFORMED_JSON, "ROS robots catalog listing contained no _posts Markdown files")
        return sorted(items, key=lambda item: str(item.get("path") or ""))

    async def _fetch_posts(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        semaphore = asyncio.Semaphore(5)

        async def fetch_one(item: dict[str, Any]) -> dict[str, Any] | None:
            async with semaphore:
                url = item.get("url")
                if not isinstance(url, str):
                    return None
                response = await self.client.get_json(url)
                return self._decode_post_payload(response.data, item=item, response_url=response.url)

        rows = await asyncio.gather(*(fetch_one(item) for item in items))
        return [row for row in rows if row is not None]

    def _decode_post_payload(self, data: Any, *, item: dict[str, Any], response_url: str) -> dict[str, Any]:
        if not isinstance(data, dict):
            raise SourceFetchError(FailureClass.MALFORMED_JSON, "ROS robot post payload was not an object")
        content = data.get("content")
        encoding = data.get("encoding")
        if not isinstance(content, str) or encoding != "base64":
            raise SourceFetchError(FailureClass.MALFORMED_JSON, "ROS robot post missing base64 Markdown content")
        try:
            import base64

            text = base64.b64decode(content).decode("utf-8", "replace")
        except ValueError as exc:
            raise SourceFetchError(FailureClass.MALFORMED_JSON, "ROS robot post had malformed base64 content") from exc
        front_matter, body = self._parse_front_matter(text)
        path = str(data.get("path") or item.get("path") or "")
        slug = self._slug_from_path(path)
        return {
            "front_matter": front_matter,
            "body": body,
            "path": path,
            "slug": slug,
            "html_url": data.get("html_url") if isinstance(data.get("html_url"), str) else item.get("html_url"),
            "api_url": response_url,
        }

    def _record_from_row(self, row: dict[str, Any], *, fetched_at: datetime) -> RawEntityRecord | None:
        if not self._is_candidate_robot(row):
            return None
        front_matter = row["front_matter"]
        title = str(front_matter["title"]).strip()
        slug = str(row["slug"])
        description = self._description_from_row(row)
        catalog_url = f"https://robots.ros.org/{slug}/"
        website = normalize_url(str(front_matter.get("website") or ""))
        wiki_homepage = normalize_url(str(front_matter.get("wiki_homepage") or ""))
        canonical_url = catalog_url
        if website and is_valid_http_url(website):
            canonical_url = website
        elif wiki_homepage and is_valid_http_url(wiki_homepage):
            canonical_url = wiki_homepage
        robot_class = str(front_matter.get("main-class") or "").strip() or None
        tags = front_matter.get("tags") if isinstance(front_matter.get("tags"), list) else []
        catalog_posted_at = self._catalog_posted_at(str(front_matter.get("date") or ""))
        source_url = str(row["api_url"])
        html_url = str(row.get("html_url") or "")
        return RawEntityRecord(
            source_key=f"ros-robots:robot:{slug}",
            entity_type="robot",
            name=title,
            description=description,
            url=canonical_url,
            categories=["Robots"],
            source_name=self.name,
            source_url=source_url,
            raw={
                "path": row.get("path"),
                "slug": slug,
                "front_matter": front_matter,
                "body_excerpt": self._clean_excerpt(str(row.get("body") or ""), limit=500),
            },
            metadata={
                "robot": {
                    "catalog_slug": slug,
                    "catalog_url": catalog_url,
                    "source_post_path": row.get("path"),
                    "source_html_url": html_url,
                    "catalog_posted_at": catalog_posted_at,
                    "robot_class": robot_class,
                    "tags": tags,
                    "external_website": website if website and is_valid_http_url(website) else None,
                    "wiki_homepage": wiki_homepage if wiki_homepage and is_valid_http_url(wiki_homepage) else None,
                    "manufacturer": None,
                    "provider": None,
                    "identity_evidence": {
                        "field": "title/introduction",
                        "catalog": "robots.ros.org",
                        "title": title,
                        "excerpt": description[:240],
                    },
                }
            },
            fetched_at=fetched_at,
        )

    def _is_candidate_robot(self, row: dict[str, Any]) -> bool:
        front_matter = row.get("front_matter")
        slug = row.get("slug")
        if not isinstance(front_matter, dict) or not isinstance(slug, str) or not slug:
            return False
        title = front_matter.get("title")
        if not isinstance(title, str) or not title.strip():
            return False
        robot_class = front_matter.get("main-class")
        if robot_class and str(robot_class).strip().lower().strip("'\"") not in _ALLOWED_ROBOT_CLASSES:
            return False
        description = self._description_from_row(row)
        if not description:
            return False
        if any(pattern.search(description) for pattern in _NON_ROBOT_DESCRIPTION_PATTERNS):
            return False
        catalog_url = f"https://robots.ros.org/{slug}/"
        website = normalize_url(str(front_matter.get("website") or ""))
        wiki_homepage = normalize_url(str(front_matter.get("wiki_homepage") or ""))
        return any(is_valid_http_url(url) for url in [catalog_url, website, wiki_homepage])

    def _description_from_row(self, row: dict[str, Any]) -> str:
        front_matter = row.get("front_matter") if isinstance(row.get("front_matter"), dict) else {}
        for key in ["introduction", "description"]:
            value = front_matter.get(key)
            if isinstance(value, str) and value.strip():
                return " ".join(value.split())
        return self._clean_excerpt(str(row.get("body") or ""), limit=320)

    def _parse_front_matter(self, text: str) -> tuple[dict[str, Any], str]:
        if not text.startswith("---"):
            return {}, text
        parts = text.split("---", 2)
        if len(parts) < 3:
            return {}, text
        front_text = parts[1]
        body = parts[2]
        data: dict[str, Any] = {}
        current_list_key: str | None = None
        for raw_line in front_text.splitlines():
            line = raw_line.rstrip()
            if not line.strip():
                continue
            stripped = line.strip()
            if stripped.startswith("-") and current_list_key:
                data.setdefault(current_list_key, []).append(self._unquote(stripped[1:].strip()))
                continue
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            key = key.strip()
            value = value.strip()
            if not key:
                continue
            if value == "":
                data[key] = [] if key in {"tags", "categories"} else ""
                current_list_key = key if key in {"tags", "categories"} else None
            else:
                data[key] = self._unquote(value)
                current_list_key = None
        return data, body

    def _unquote(self, value: str) -> str:
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            return value[1:-1]
        return value

    def _slug_from_path(self, path: str) -> str | None:
        match = _ROBOT_POST_PATTERN.match(path)
        if not match:
            return None
        return match.group("slug").strip().lower()

    def _catalog_posted_at(self, value: str) -> str | None:
        value = value.strip()
        if not value:
            return None
        for pattern in ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d"]:
            try:
                parsed = datetime.strptime(value, pattern).replace(tzinfo=timezone.utc)
                return parsed.isoformat()
            except ValueError:
                continue
        return value

    def _clean_excerpt(self, value: str, *, limit: int) -> str:
        value = re.sub(r"<[^>]+>", " ", value)
        value = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", value)
        value = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", value)
        value = re.sub(r"[#*_`'\"]+", " ", value)
        value = re.sub(r"\s+", " ", value).strip()
        return value[:limit].strip()
