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

# Short AI-signal tokens are matched on word boundaries so that substrings
# inside unrelated words (e.g. "ai" inside "maintain") are not accepted.
_SHORT_AI_SIGNALS = ("ai", "gpt", "llm", "nlp", "mcp")

# Longer, distinctive AI-signal tokens (including recognized AI provider
# names) may match as substrings.
_LONG_AI_SIGNALS = (
    "artificial-intelligence",
    "artificial intelligence",
    "machine-learning",
    "machine learning",
    "deep-learning",
    "deep learning",
    "generative",
    "transformer",
    "diffusion",
    "stable-diffusion",
    "stable diffusion",
    "openai",
    "open ai",
    "anthropic",
    "cohere",
    "groq",
    "mistral",
    "huggingface",
    "hugging face",
    "model-context-protocol",
    "model context protocol",
    "chatgpt",
    "chatbot",
    "multimodal",
    "neural",
    "embedding",
    "natural-language",
    "computer-vision",
    "speech-recognition",
    "reinforcement-learning",
)


def _ai_signal_tokens(text: str) -> list[str]:
    """Return the AI-signal tokens observed in ``text``.

    Short tokens use word-boundary matching; longer tokens use substring
    matching. The order of returned tokens is deterministic (short tokens
    first, then long tokens in declaration order).
    """
    lowered = " ".join(str(text or "").split()).lower()
    matched: list[str] = []
    for token in _SHORT_AI_SIGNALS:
        if re.search(rf"(?<![a-z0-9]){re.escape(token)}(?![a-z0-9])", lowered):
            matched.append(token)
    for token in _LONG_AI_SIGNALS:
        if token in lowered:
            matched.append(token)
    return matched


def _normalize_iso_timestamp(value: str) -> str | None:
    """Normalize a source ISO-8601 timestamp to UTC ``+00:00`` form.

    Returns ``None`` when the value is not a parseable timestamp. This
    function only canonicalizes observed timestamps; it never invents one.
    """
    value = (value or "").strip()
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat()


class GitHubReleasesNewsAdapter(SourceAdapter):
    """Ingests GitHub release announcements as bounded AI news records.

    The GitHub Releases API is reachable from this environment and exposes
    structured announcement records with a genuine publication timestamp
    (``published_at``), a canonical release URL, a title, release-note body,
    and the publishing repository/owner. This adapter treats those records as
    news/announcement entities for a curated allowlist of AI repositories.

    ``published_at`` is the time the release was published on GitHub; it is
    never substituted with crawl/retrieval/commit time. ``fetched_at`` remains
    a separate provenance field.
    """

    name = "GitHub Releases Announcements"

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
        self._repos: list[dict[str, Any]] = []
        self._releases_cache: dict[str, list[dict[str, Any]]] = {}

    async def verify(self) -> SourceFeasibility:
        url = f"{self.settings.github_api_base.rstrip('/')}/repos/{self.settings.github_releases_news_repos[0]}/releases"
        try:
            repos, failed_repos = await self._fetch_repos()
            self._repos = repos
            usable_sample: list[dict[str, Any]] = []
            for repo in repos[:2]:
                releases = await self._fetch_releases(repo)
                self._releases_cache[str(repo.get("full_name") or "")] = releases
                usable_sample.extend(rel for rel in releases if self._is_candidate_release(rel))
            inventory = (
                f"configured repositories={len(self.settings.github_releases_news_repos)}; "
                f"repository metadata fetched={len(repos)}; "
                f"repository metadata failures={len(failed_repos)}; "
                f"sampled releases={sum(len(v) for v in self._releases_cache.values())}; "
                f"sampled usable release records={len(usable_sample)}"
            )
            return SourceFeasibility(
                source_name=self.name,
                source_type="GitHub REST releases API announcements",
                access_method="GitHub REST /repos/{owner}/{repo}/releases for a curated AI repository allowlist",
                url=url,
                status="usable" if usable_sample else "partial",
                domain="News",
                http_status=200,
                pagination="per_page/page parameters; adapter ingests a bounded deterministic per-repository sample",
                available_fields=[
                    "id",
                    "tag_name",
                    "name",
                    "body",
                    "html_url",
                    "url",
                    "published_at",
                    "created_at",
                    "draft",
                    "prerelease",
                    "author",
                ],
                required_fields=[
                    "name or tag_name",
                    "html_url",
                    "published_at",
                    "body (release notes)",
                    "repository owner/login",
                    "repository AI relevance evidence",
                ],
                authentication_required=False,
                rate_limit_observed={},
                freshness="release published_at is the genuine GitHub publication timestamp for the announcement; it is preserved as news.published_at with explicit timestamp semantics and never substituted with crawl/commit time",
                anti_bot_js="GitHub REST API returned JSON; no browser automation or JavaScript required",
                inventory_evidence=inventory,
                company_identity_quality="repository owner.login identifies the publishing organization; published_by relationships are emitted only when that organization already resolves to an ingested company entity",
                ai_relevance="curated AI repository allowlist; each accepted record captures observed AI-signal tokens from the repository description/topics/full_name",
                actual_crawl_feasibility="usable for bounded News records with genuine source-backed publication timestamps",
                record_volume_estimate=f"bounded by AI_ORBIT_GITHUB_RELEASES_NEWS_LIMIT={self.settings.github_releases_news_limit} across {len(self.settings.github_releases_news_repos)} configured repositories",
                failure_behavior="404/403/malformed JSON are source failures; per-repository failures are skipped without aborting the whole source; 429/5xx use bounded retry via the shared HTTP client",
                yielded_usable_records=0,
            )
        except SourceFetchError as exc:
            return SourceFeasibility(
                source_name=self.name,
                source_type="GitHub REST releases API announcements",
                access_method="GitHub REST /repos/{owner}/{repo}/releases for a curated AI repository allowlist",
                url=url,
                status="unusable",
                domain="News",
                http_status=exc.status_code,
                required_fields=["name or tag_name", "html_url", "published_at", "body (release notes)"],
                authentication_required=False,
                anti_bot_js="not determined; API request failed",
                actual_crawl_feasibility="not usable from this environment based on observed failure",
                failure_behavior=f"{exc.failure_class.value}: {exc}",
            )

    async def discover(self) -> list[RawEntityRecord]:
        if not self._repos:
            repos, _failed = await self._fetch_repos()
            self._repos = repos
        now = datetime.now(timezone.utc)

        # Fetch (or reuse cached) releases for every configured repository so
        # that publisher diversity is not truncated by the bounded record
        # limit being reached early on the first few repositories. A per-
        # repository release fetch failure is isolated: it skips that
        # repository without aborting the rest of the source.
        repo_release_lists: list[list[dict[str, Any]]] = []
        for repo in self._repos:
            repo_name = str(repo.get("full_name") or "")
            releases = self._releases_cache.get(repo_name)
            if releases is None:
                try:
                    releases = await self._fetch_releases(repo)
                except SourceFetchError:
                    releases = []
                self._releases_cache[repo_name] = releases
            repo_release_lists.append(releases)

        # Round-robin interleave across repositories so the bounded sample
        # spans as many publishers as possible (newest release per repository
        # first, then second-newest, and so on).
        records: list[RawEntityRecord] = []
        seen_keys: set[str] = set()
        index = 0
        while len(records) < self.settings.github_releases_news_limit:
            progressed = False
            for repo, releases in zip(self._repos, repo_release_lists):
                if len(records) >= self.settings.github_releases_news_limit:
                    break
                if index < len(releases):
                    progressed = True
                    record = self._record_from_release(releases[index], repo, fetched_at=now)
                    if record is not None and record.source_key not in seen_keys:
                        seen_keys.add(record.source_key)
                        records.append(record)
            if not progressed:
                break
            index += 1
        return records

    async def _fetch_repos(self) -> tuple[list[dict[str, Any]], list[str]]:
        base = self.settings.github_api_base.rstrip("/")
        urls = [f"{base}/repos/{full_name}" for full_name in self.settings.github_releases_news_repos]
        semaphore = asyncio.Semaphore(5)

        async def fetch_one(url: str) -> dict[str, Any] | None:
            async with semaphore:
                try:
                    response = await self.client.get_json(url)
                except SourceFetchError:
                    return None
                if not isinstance(response.data, dict) or not response.data.get("full_name"):
                    return None
                return response.data

        results = await asyncio.gather(*(fetch_one(url) for url in urls))
        repos = [result for result in results if result is not None]
        failed = [url for url, result in zip(urls, results) if result is None]
        return repos, failed

    async def _fetch_releases(self, repo: dict[str, Any]) -> list[dict[str, Any]]:
        full_name = str(repo.get("full_name") or "")
        url = f"{self.settings.github_api_base.rstrip('/')}/repos/{full_name}/releases"
        response = await self.client.get_json(url, params={"per_page": self.settings.github_releases_news_per_repo})
        data = response.data
        if not isinstance(data, list):
            raise SourceFetchError(FailureClass.MALFORMED_JSON, f"GitHub releases response for {full_name} was not a JSON array")
        return [item for item in data if isinstance(item, dict)]

    def _record_from_release(self, release: dict[str, Any], repo: dict[str, Any], *, fetched_at: datetime) -> RawEntityRecord | None:
        if not self._is_candidate_release(release):
            return None
        owner = repo.get("owner") if isinstance(repo.get("owner"), dict) else {}
        full_name = str(repo.get("full_name") or "")
        owner_login = str(owner.get("login") or "")
        release_id = release.get("id")
        title = self._release_title(release)
        description = self._clean_excerpt(str(release.get("body") or ""), limit=800)
        html_url = normalize_url(str(release.get("html_url") or ""))
        source_url = normalize_url(str(release.get("url") or "") or str(release.get("html_url") or ""))
        published_at = _normalize_iso_timestamp(str(release.get("published_at") or ""))
        created_at = _normalize_iso_timestamp(str(release.get("created_at") or ""))
        ai_evidence = self._ai_relevance_evidence(repo)
        pending: list[dict[str, Any]] = []
        if owner.get("type") == "Organization" and owner_login:
            pending.append({
                "relationship_type": "published_by",
                "other_source_key": f"github:org:{owner_login.lower()}",
                "method": "github_release_publisher",
                "evidence": {
                    "field": "repository.owner.login",
                    "value": owner_login,
                    "release_url": html_url,
                    "repository": full_name,
                    "source_url": source_url,
                },
            })
        return RawEntityRecord(
            source_key=f"github:release:{full_name.lower()}:{release_id}",
            entity_type="news",
            name=title,
            description=description,
            url=html_url,
            categories=["News"],
            source_name=self.name,
            source_url=source_url,
            raw={
                "release_id": release_id,
                "tag_name": release.get("tag_name"),
                "body_excerpt": self._clean_excerpt(str(release.get("body") or ""), limit=500),
                "repository": full_name,
            },
            metadata={
                "news": {
                    "canonical_url": html_url,
                    "subtype": "github_release_announcement",
                    "published_at": published_at,
                    "created_at": created_at,
                    "timestamp_semantics": "github_release_published_at",
                    "publisher": {
                        "login": owner_login,
                        "type": owner.get("type"),
                        "html_url": normalize_url(str(owner.get("html_url") or "")),
                    },
                    "repository": full_name,
                    "tag_name": release.get("tag_name"),
                    "release_id": release_id,
                    "prerelease": bool(release.get("prerelease")),
                    "ai_relevance_evidence": ai_evidence,
                }
            },
            pending_relationships=pending,
            fetched_at=fetched_at,
        )

    def _is_candidate_release(self, release: dict[str, Any]) -> bool:
        if not isinstance(release, dict):
            return False
        if release.get("draft") is True or release.get("prerelease") is True:
            return False
        html_url = str(release.get("html_url") or "")
        if not is_valid_http_url(html_url):
            return False
        if _normalize_iso_timestamp(str(release.get("published_at") or "")) is None:
            return False
        if not self._release_title(release):
            return False
        body = self._clean_excerpt(str(release.get("body") or ""), limit=800)
        if not body:
            return False
        return True

    def _release_title(self, release: dict[str, Any]) -> str:
        name = (str(release.get("name") or "") or "").strip()
        if name:
            return name
        return (str(release.get("tag_name") or "") or "").strip()

    def _ai_relevance_evidence(self, repo: dict[str, Any]) -> dict[str, Any] | None:
        fields = {
            "repository.description": str(repo.get("description") or ""),
            "repository.topics": " ".join(str(t) for t in (repo.get("topics") or [])),
            "repository.full_name": str(repo.get("full_name") or ""),
        }
        matched_fields: dict[str, list[str]] = {}
        for field, text in fields.items():
            tokens = _ai_signal_tokens(text)
            if tokens:
                matched_fields[field] = tokens
        if not matched_fields:
            return None
        flat_tokens: list[str] = []
        for tokens in matched_fields.values():
            for token in tokens:
                if token not in flat_tokens:
                    flat_tokens.append(token)
        excerpt = " ".join(str(repo.get("description") or "").split())[:200] or str(repo.get("full_name") or "")
        return {
            "matched_fields": sorted(matched_fields.keys()),
            "matched_tokens": flat_tokens,
            "excerpt": excerpt,
        }

    def _clean_excerpt(self, value: str, *, limit: int) -> str:
        value = re.sub(r"<[^>]+>", " ", value or "")
        value = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", value)
        value = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", value)
        value = re.sub(r"[#*_`'\"|]", " ", value)
        value = re.sub(r"\s+", " ", value).strip()
        return value[:limit].strip()
