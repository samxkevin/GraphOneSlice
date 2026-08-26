from __future__ import annotations

import asyncio
import base64
from datetime import date, datetime, timezone
import re
from typing import Any

from src.ai_orbit.adapters.base import SourceAdapter
from src.ai_orbit.config import AIOrbitSettings
from src.ai_orbit.models import RawEntityRecord, SourceFeasibility
from src.ai_orbit.utils.http import FailureClass, HttpRetryConfig, JsonHttpClient, SourceFetchError
from src.ai_orbit.utils.url import is_valid_http_url, normalize_url

# Specific, short AI signals matched on word boundaries so substrings inside
# unrelated words (e.g. "llm" inside "ballmer") are not accepted.
_STRONG_SHORT_SIGNALS = ("llm", "gpt", "nlp", "rag")

# Strong, distinctive AI signals. A single strong match is enough to accept a
# video as AI-relevant.
_STRONG_LONG_SIGNALS = (
    "artificial intelligence",
    "artificial-intelligence",
    "machine learning",
    "machine-learning",
    "deep learning",
    "deep-learning",
    "neural network",
    "neural-network",
    "large language model",
    "large-language-model",
    "foundation model",
    "foundation-model",
    "computer vision",
    "computer-vision",
    "natural language",
    "natural-language",
    "reinforcement learning",
    "reinforcement-learning",
    "generative ai",
    "generative",
    "diffusion",
    "stable diffusion",
    "stable-diffusion",
    "transformer",
    "pytorch",
    "tensorflow",
    "jax",
    "pretraining",
    "pre-training",
    "fine-tuning",
    "fine tuning",
    "embedding",
    "embeddings",
    "quantization",
    "tokenizer",
    "hallucination",
    "multimodal",
    "multi-modal",
    "chatgpt",
    "chatbot",
    "openai",
    "open ai",
    "anthropic",
    "cohere",
    "mistral",
    "groq",
    "hugging face",
    "huggingface",
    "langchain",
    "model-context-protocol",
    "model context protocol",
)

# Weaker signals that only count toward acceptance when combined (two or more)
# or when a strong signal is already present.
_WEAK_AI_SIGNALS = (
    "ai",
    "ml",
    "gpu",
    "cuda",
    "inference",
    "training",
    "agent",
    "agents",
    "neural",
)


def _video_ai_tokens(text: str) -> tuple[list[str], list[str]]:
    """Return (strong_tokens, weak_tokens) observed in ``text``.

    Short tokens use word-boundary matching; longer tokens use substring
    matching. The order of returned tokens is deterministic.
    """
    lowered = " ".join(str(text or "").split()).lower()
    strong: list[str] = []
    weak: list[str] = []
    for token in _STRONG_SHORT_SIGNALS:
        if re.search(rf"(?<![a-z0-9]){re.escape(token)}(?![a-z0-9])", lowered):
            strong.append(token)
    for token in _STRONG_LONG_SIGNALS:
        if token in lowered:
            strong.append(token)
    for token in _WEAK_AI_SIGNALS:
        if re.search(rf"(?<![a-z0-9]){re.escape(token)}(?![a-z0-9])", lowered):
            weak.append(token)
    return strong, weak


def _is_ai_relevant(*texts: str) -> bool:
    strong: list[str] = []
    weak: list[str] = []
    for text in texts:
        s, w = _video_ai_tokens(text)
        strong.extend(s)
        weak.extend(w)
    # A single strong signal, or at least two weak signals, is required so a
    # lone broad term such as "ai", "training", or "agent" cannot accept a
    # video on its own.
    return bool(strong) or len(weak) >= 2


def _normalize_iso_date(value: str) -> str | None:
    """Normalize a PyVideo ``recorded`` value to an ISO date (``YYYY-MM-DD``).

    PyVideo documents ``recorded`` as the date the video was recorded. This
    helper only canonicalizes an observed value; it never invents a date.
    """
    value = (value or "").strip()
    if not value:
        return None
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError:
        pass
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.date().isoformat()


class PyVideoVideosAdapter(SourceAdapter):
    """Ingests bounded AI-relevant conference-talk video records from PyVideo.

    PyVideo's ``pyvideo/data`` repository (which powers pyvideo.org) stores one
    JSON document per conference-talk video with the talk title, description,
    speakers, a real canonical YouTube URL, and the genuine ``recorded`` date
    (the date the talk was recorded). This adapter ingests those as video
    entities for a curated allowlist of AI-relevant conferences.

    ``video.recorded_at`` is the source's talk recording date — a recording
    date, **not** a publication or upload timestamp. PyVideo's schema documents
    ``recorded`` as "ISO 8601 Date on which video was recorded", and the
    assessment schema does not require a publication timestamp for Videos, so
    none is fabricated. ``video.timestamp_semantics`` is set to
    ``pyvideo_recorded_date`` to make this explicit. ``fetched_at`` remains a
    separate provenance field. No channel name is fabricated: the publisher is
    the conference/event the source attributes the talk to.
    """

    name = "PyVideo Catalog"

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
        self._event_titles: dict[str, str] = {}
        self._event_listings: dict[str, list[str]] = {}

    async def verify(self) -> SourceFeasibility:
        events = self.settings.pyvideo_events
        url = f"{self.settings.github_api_base.rstrip('/')}/repos/pyvideo/data/contents/{events[0]}/category.json"
        try:
            titles: dict[str, str] = {}
            listings: dict[str, list[str]] = {}
            for event in events:
                title = await self._fetch_event_title(event)
                listing = await self._fetch_video_listing(event)
                titles[event] = title
                listings[event] = listing
            self._event_titles = titles
            self._event_listings = listings

            # Inspect a small deterministic sample to verify parseable schema.
            usable_sample = 0
            sampled = 0
            for event, files in listings.items():
                candidates = [name for name in files if self._slug_suggests_ai(name)]
                for name in candidates[:3]:
                    sampled += 1
                    row = await self._fetch_video_row(event, name)
                    if row is not None and self._is_candidate_video(row):
                        usable_sample += 1
                if sampled >= 6:
                    break
            total_listed = sum(len(v) for v in listings.values())
            slug_candidates = sum(1 for files in listings.values() for name in files if self._slug_suggests_ai(name))
            return SourceFeasibility(
                source_name=self.name,
                source_type="GitHub-hosted structured JSON video catalog",
                access_method="GitHub REST contents API for pyvideo/data conference video JSON documents",
                url=url,
                status="usable" if usable_sample else "partial",
                domain="Videos",
                http_status=200,
                pagination="GitHub contents directory listing per conference; adapter ingests a bounded deterministic sample",
                available_fields=[
                    "title",
                    "description",
                    "recorded",
                    "videos[].url (YouTube)",
                    "speakers",
                    "language",
                    "related_urls",
                    "thumbnail_url",
                    "slug",
                ],
                required_fields=[
                    "title",
                    "canonical YouTube URL",
                    "recorded (talk recording date)",
                    "description",
                    "event/publisher",
                    "AI relevance evidence",
                ],
                authentication_required=False,
                rate_limit_observed={},
                freshness="recorded is the source-documented date the talk was recorded; it is preserved as video.recorded_at with explicit timestamp semantics and never substituted with crawl/commit time",
                anti_bot_js="GitHub REST API returned JSON/base64; no browser automation or JavaScript required",
                inventory_evidence=f"configured conferences={len(events)}; listed video files={total_listed}; slug-suggested AI candidates={slug_candidates}; sampled files={sampled}; sampled usable video records={usable_sample}",
                company_identity_quality="the source attributes each talk to a conference/event, not a company; publisher is the event title from the source category document",
                ai_relevance="curated AI-relevant conference allowlist plus per-record title/description AI-signal evidence (>=1 strong or >=2 weak tokens)",
                actual_crawl_feasibility="usable for bounded Video records with real canonical YouTube URLs and genuine recording dates",
                record_volume_estimate=f"bounded by AI_ORBIT_PYVIDEO_LIMIT={self.settings.pyvideo_limit} across {len(events)} configured conferences",
                failure_behavior="403/404/malformed JSON are source failures; per-conference/per-file failures are skipped without aborting the whole source; 429/5xx use bounded retry via the shared HTTP client",
                yielded_usable_records=0,
            )
        except SourceFetchError as exc:
            return SourceFeasibility(
                source_name=self.name,
                source_type="GitHub-hosted structured JSON video catalog",
                access_method="GitHub REST contents API for pyvideo/data conference video JSON documents",
                url=url,
                status="unusable",
                domain="Videos",
                http_status=exc.status_code,
                required_fields=["title", "canonical YouTube URL", "recorded", "description", "event/publisher"],
                authentication_required=False,
                anti_bot_js="not determined; API request failed",
                actual_crawl_feasibility="not usable from this environment based on observed failure",
                failure_behavior=f"{exc.failure_class.value}: {exc}",
            )

    async def discover(self) -> list[RawEntityRecord]:
        if not self._event_listings:
            for event in self.settings.pyvideo_events:
                try:
                    self._event_titles[event] = await self._fetch_event_title(event)
                    self._event_listings[event] = await self._fetch_video_listing(event)
                except SourceFetchError:
                    self._event_titles.setdefault(event, event)
                    self._event_listings.setdefault(event, [])
        now = datetime.now(timezone.utc)

        # Build AI-relevant records per conference, isolated per conference.
        per_event_records: list[list[RawEntityRecord]] = []
        for event in self.settings.pyvideo_events:
            event_records: list[RawEntityRecord] = []
            files = self._event_listings.get(event, [])
            title = self._event_titles.get(event, event)
            # Deterministic order, then cheap slug triage before fetching files.
            candidate_files = [name for name in sorted(files) if self._slug_suggests_ai(name)]
            for name in candidate_files[: self.settings.pyvideo_per_event_limit]:
                if len(event_records) >= self.settings.pyvideo_limit:
                    break
                try:
                    row = await self._fetch_video_row(event, name)
                except SourceFetchError:
                    continue
                record = self._record_from_row(row, event=event, event_title=title, fetched_at=now)
                if record is not None:
                    event_records.append(record)
            per_event_records.append(event_records)

        # Round-robin across conferences so the bounded sample spans as many
        # publishers (conferences) as possible.
        records: list[RawEntityRecord] = []
        seen_keys: set[str] = set()
        index = 0
        while len(records) < self.settings.pyvideo_limit:
            progressed = False
            for event_records in per_event_records:
                if len(records) >= self.settings.pyvideo_limit:
                    break
                if index < len(event_records):
                    progressed = True
                    record = event_records[index]
                    if record.source_key not in seen_keys:
                        seen_keys.add(record.source_key)
                        records.append(record)
            if not progressed:
                break
            index += 1
        return records

    async def _fetch_event_title(self, event: str) -> str:
        url = f"{self.settings.github_api_base.rstrip('/')}/repos/pyvideo/data/contents/{event}/category.json"
        response = await self.client.get_json(url)
        data = self._decode_payload(response.data)
        title = data.get("title") if isinstance(data, dict) else None
        return str(title).strip() if title else event

    async def _fetch_video_listing(self, event: str) -> list[str]:
        url = f"{self.settings.github_api_base.rstrip('/')}/repos/pyvideo/data/contents/{event}/videos"
        response = await self.client.get_json(url)
        data = response.data
        if not isinstance(data, list):
            raise SourceFetchError(FailureClass.MALFORMED_JSON, f"PyVideo listing for {event} was not a JSON array")
        names = [str(item.get("name") or "") for item in data if isinstance(item, dict) and str(item.get("name") or "").endswith(".json")]
        if not names:
            raise SourceFetchError(FailureClass.MALFORMED_JSON, f"PyVideo listing for {event} contained no video JSON files")
        return names

    async def _fetch_video_row(self, event: str, name: str) -> dict[str, Any]:
        url = f"{self.settings.github_api_base.rstrip('/')}/repos/pyvideo/data/contents/{event}/videos/{name}"
        response = await self.client.get_json(url)
        data = self._decode_payload(response.data)
        if not isinstance(data, dict):
            raise SourceFetchError(FailureClass.MALFORMED_JSON, f"PyVideo video payload for {event}/{name} was not an object")
        data.setdefault("_api_url", response.url)
        data.setdefault("_event", event)
        data.setdefault("_slug", name[: -len(".json")] if name.endswith(".json") else name)
        return data

    def _decode_payload(self, data: Any) -> Any:
        if not isinstance(data, dict):
            raise SourceFetchError(FailureClass.MALFORMED_JSON, "PyVideo contents payload was not an object")
        content = data.get("content")
        encoding = data.get("encoding")
        if not isinstance(content, str) or encoding != "base64":
            raise SourceFetchError(FailureClass.MALFORMED_JSON, "PyVideo contents payload missing base64 content")
        try:
            import json

            return json.loads(base64.b64decode(content).decode("utf-8", "replace"))
        except (ValueError, json.JSONDecodeError) as exc:
            raise SourceFetchError(FailureClass.MALFORMED_JSON, "PyVideo contents payload had malformed JSON content") from exc

    def _record_from_row(self, row: dict[str, Any], *, event: str, event_title: str, fetched_at: datetime) -> RawEntityRecord | None:
        if not self._is_candidate_video(row):
            return None
        title = " ".join(str(row.get("title") or "").split())
        description = self._clean_excerpt(str(row.get("description") or ""), limit=800)
        youtube_url = self._youtube_url(row)
        slug = str(row.get("_slug") or "")
        recorded_at = _normalize_iso_date(str(row.get("recorded") or ""))
        speakers = row.get("speakers") if isinstance(row.get("speakers"), list) else []
        language = row.get("language")
        related_urls = row.get("related_urls") if isinstance(row.get("related_urls"), list) else []
        thumbnail_url = normalize_url(str(row.get("thumbnail_url") or "")) or None
        youtube_video_id = self._youtube_video_id(youtube_url)
        source_url = normalize_url(str(row.get("_api_url") or ""))
        ai_evidence = self._ai_relevance_evidence(row)
        return RawEntityRecord(
            source_key=f"pyvideo:video:{event}:{slug}",
            entity_type="video",
            name=title,
            description=description,
            url=normalize_url(youtube_url),
            categories=["Videos"],
            source_name=self.name,
            source_url=source_url,
            raw={
                "slug": slug,
                "event": event,
                "speakers": speakers,
                "language": language,
                "related_urls": related_urls,
            },
            metadata={
                "video": {
                    "canonical_url": normalize_url(youtube_url),
                    "youtube_video_id": youtube_video_id,
                    "recorded_at": recorded_at,
                    "timestamp_semantics": "pyvideo_recorded_date",
                    "publisher": {
                        "name": event_title,
                        "event": event,
                        "type": "conference",
                    },
                    "speakers": speakers,
                    "language": language,
                    "related_urls": related_urls,
                    "thumbnail_url": thumbnail_url,
                    "ai_relevance_evidence": ai_evidence,
                }
            },
            fetched_at=fetched_at,
        )

    def _is_candidate_video(self, row: dict[str, Any]) -> bool:
        if not isinstance(row, dict):
            return False
        title = str(row.get("title") or "").strip()
        if not title:
            return False
        youtube_url = self._youtube_url(row)
        if not is_valid_http_url(youtube_url) or "youtube" not in youtube_url.lower():
            return False
        if _normalize_iso_date(str(row.get("recorded") or "")) is None:
            return False
        description = self._clean_excerpt(str(row.get("description") or ""), limit=800)
        if not description:
            return False
        if not _is_ai_relevant(title, description):
            return False
        return True

    def _youtube_url(self, row: dict[str, Any]) -> str:
        videos = row.get("videos") if isinstance(row.get("videos"), list) else []
        for item in videos:
            if isinstance(item, dict) and item.get("type") == "youtube":
                url = str(item.get("url") or "")
                if url:
                    return url
        # Fall back to the first video location regardless of type only when
        # no explicit YouTube location exists; the type field still has to be
        # present so a canonical video URL is not invented.
        for item in videos:
            if isinstance(item, dict) and item.get("url"):
                return str(item.get("url") or "")
        return ""

    def _youtube_video_id(self, url: str) -> str | None:
        from urllib.parse import parse_qs, urlsplit

        try:
            parts = urlsplit(url)
        except ValueError:
            return None
        if "youtu.be" in parts.netloc:
            return parts.path.strip("/") or None
        query = parse_qs(parts.query)
        return (query.get("v") or [None])[0]

    def _ai_relevance_evidence(self, row: dict[str, Any]) -> dict[str, Any] | None:
        title = str(row.get("title") or "")
        description = str(row.get("description") or "")
        strong: list[str] = []
        weak: list[str] = []
        for text in (title, description):
            s, w = _video_ai_tokens(text)
            strong.extend(s)
            weak.extend(w)
        flat: list[str] = []
        for token in strong + weak:
            if token not in flat:
                flat.append(token)
        if not flat:
            return None
        return {
            "matched_strong_tokens": sorted(set(strong)),
            "matched_weak_tokens": sorted(set(weak)),
            "matched_tokens": flat,
            "excerpt": " ".join(title.split())[:200],
        }

    def _slug_suggests_ai(self, filename: str) -> bool:
        if not filename.endswith(".json"):
            return False
        slug = filename[: -len(".json")]
        return _is_ai_relevant(slug)

    def _clean_excerpt(self, value: str, *, limit: int) -> str:
        value = re.sub(r"<[^>]+>", " ", value or "")
        value = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", value)
        value = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", value)
        value = re.sub(r"[#*_`'\"|]", " ", value)
        value = re.sub(r"\s+", " ", value).strip()
        return value[:limit].strip()
