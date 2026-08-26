from __future__ import annotations

import base64
from datetime import datetime, timezone
import re
from typing import Any

from src.ai_orbit.adapters.base import SourceAdapter
from src.ai_orbit.config import AIOrbitSettings
from src.ai_orbit.models import RawEntityRecord, SourceFeasibility
from src.ai_orbit.utils.http import FailureClass, HttpRetryConfig, JsonHttpClient, SourceFetchError
from src.ai_orbit.utils.url import is_valid_http_url, normalize_url

# Sections in the source README that contain actual board entries. Entries are
# accepted only from these sections. "Available later" (announced-but-not-
# shipped) and "MCUs only" (bare chips, not boards/devices) sections are
# excluded because they do not establish currently-available device identity
# with a device-specific product URL.
_INCLUDE_SECTION_MARKERS = ("available now", "boards with other")
_EXCLUDE_SECTION_MARKERS = ("available later", "mcus only", "no boards")

# Markdown link extractor.
_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")

# Controlled, source-derived manufacturer map: a board name token -> the
# manufacturer that token names. This is deterministic and auditable; each
# record stores the matched token and observed name as evidence. This is not
# free-form inference: the manufacturer is named by the board name itself
# (e.g. "NXP MCIMX93-EVK", "Arduino Nicla Voice", "STM32N6570-DK").
_MANUFACTURER_BY_TOKEN = (
    ("seeed", "Seeed Studio"),
    ("grove", "Seeed Studio"),
    ("nxp", "NXP"),
    ("alif", "Alif Semiconductor"),
    ("nuvoton", "Nuvoton"),
    ("synaptics", "Synaptics"),
    ("arduino", "Arduino"),
    ("silabs", "Silicon Labs"),
    ("sipeed", "Sipeed"),
    ("01studio", "01Studio"),
    ("maaxboard", "Avnet"),
    ("avnet", "Avnet"),
    ("syntiant", "Syntiant"),
    ("stm32", "STMicroelectronics"),
    ("nucleo", "STMicroelectronics"),
    ("launchxl", "Texas Instruments"),
    ("esp32", "Espressif"),
    ("max78000", "Analog Devices"),
    ("infenion", "Infineon"),
)

# Accelerator/NPU tokens that constitute AI relevance evidence. Short tokens
# use word boundaries so substrings inside unrelated words are not accepted.
_ACCELERATOR_SHORT = ("npu", "kpu", "pie", "nnlite", "tpu")
_ACCELERATOR_LONG = (
    "ethos",
    "neural-art",
    "neural decision processor",
    "neural network accelerator",
    "processor instruction extensions",
    "accelerator",
    "neural",
)


def _extract_links(text: str) -> list[tuple[str, str]]:
    return _LINK_RE.findall(text)


def _clean_markdown(value: str) -> str:
    value = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", value or "")
    value = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", value)
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def _accelerator_tokens(text: str) -> list[str]:
    lowered = " ".join(str(text or "").split()).lower()
    matched: list[str] = []
    for token in _ACCELERATOR_SHORT:
        if re.search(rf"(?<![a-z0-9]){re.escape(token)}(?![a-z0-9])", lowered):
            matched.append(token)
    for token in _ACCELERATOR_LONG:
        if token in lowered:
            matched.append(token)
    return matched


def _derive_manufacturer(name: str) -> tuple[str | None, str | None]:
    lowered = name.lower()
    for token, manufacturer in _MANUFACTURER_BY_TOKEN:
        if token in lowered:
            return manufacturer, f"matched '{token}' in board name '{name}'"
    return None, None


class AIDeviceCatalogAdapter(SourceAdapter):
    """Ingests bounded AI-hardware device records from a GitHub-hosted catalog.

    The source repository (Vge0rge/ai-ml-embedded-boards) is an explicit,
    structured Markdown list of embedded boards with AI/ML accelerators. Each
    entry names a real physical device and supplies its MCU/processor, an
    accelerator (NPU/Ethos/Neural/etc.), a price, and a vendor product URL.
    This adapter ingests those as Device entities.

    ``device.manufacturer`` is derived only from the board name via a
    controlled, source-derived token map (with the matched token and observed
    name recorded as evidence); it is ``null`` when the source does not name a
    manufacturer. No ``Device -> runs -> Model`` relationship is produced
    because this source documents framework support (TensorFlow/PyTorch), not
    specific supported model IDs.
    """

    name = "AI Device Catalog"

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
        self._markdown: str | None = None
        self._entries: list[dict[str, Any]] = []

    async def verify(self) -> SourceFeasibility:
        url = self.settings.ai_device_catalog_api_url
        try:
            markdown = await self._fetch_markdown()
            self._markdown = markdown
            parsed = self._parse_entries(markdown)
            self._entries = parsed
            included = [e for e in parsed if e["mode"] == "include"]
            candidates = [e for e in included if self._is_candidate_entry(e)]
            deduped = self._dedupe_by_url(candidates)
            inventory = (
                f"parsed entries={len(parsed)}; "
                f"included board entries={len(included)}; "
                f"excluded (available-later/mcus-only)={len(parsed) - len(included)}; "
                f"candidate device entries={len(candidates)}; "
                f"device-specific entries after URL dedup={len(deduped)}"
            )
            return SourceFeasibility(
                source_name=self.name,
                source_type="GitHub-hosted structured Markdown device catalog",
                access_method="GitHub REST contents API for the AI device catalog README (Vge0rge/ai-ml-embedded-boards)",
                url=url,
                status="usable" if deduped else "partial",
                domain="Devices",
                http_status=200,
                pagination="single Markdown catalog document; adapter ingests a bounded deterministic sample",
                available_fields=[
                    "board name",
                    "MCU/processor",
                    "accelerator/NPU",
                    "framework support",
                    "price",
                    "vendor label",
                    "vendor product URL",
                ],
                required_fields=[
                    "device name",
                    "canonical vendor URL",
                    "MCU/processor description",
                    "AI accelerator evidence",
                ],
                authentication_required=False,
                rate_limit_observed={},
                freshness="the source does not supply per-device timestamps; no release/publication date is fabricated for devices",
                anti_bot_js="GitHub REST API returned Markdown as JSON/base64; no browser automation or JavaScript required",
                inventory_evidence=inventory,
                company_identity_quality="manufacturer is derived from the board name via a controlled token map and recorded with evidence; null when the name does not identify a manufacturer",
                ai_relevance="catalog is explicitly a list of boards with AI/ML accelerators; each accepted record captures observed accelerator/NPU tokens from the entry text",
                actual_crawl_feasibility="usable for bounded Device records with real board identity, accelerator evidence, and vendor product URLs",
                record_volume_estimate=f"bounded by AI_ORBIT_AI_DEVICE_LIMIT={self.settings.ai_device_limit}; {len(deduped)} device-specific entries available in the catalog",
                failure_behavior="403/404/malformed JSON/Markdown are source failures; 429/5xx use bounded retry via the shared HTTP client",
                yielded_usable_records=0,
            )
        except SourceFetchError as exc:
            return SourceFeasibility(
                source_name=self.name,
                source_type="GitHub-hosted structured Markdown device catalog",
                access_method="GitHub REST contents API for the AI device catalog README (Vge0rge/ai-ml-embedded-boards)",
                url=url,
                status="unusable",
                domain="Devices",
                http_status=exc.status_code,
                required_fields=["device name", "canonical vendor URL", "MCU/processor description", "AI accelerator evidence"],
                authentication_required=False,
                anti_bot_js="not determined; API request failed",
                actual_crawl_feasibility="not usable from this environment based on observed failure",
                failure_behavior=f"{exc.failure_class.value}: {exc}",
            )

    async def discover(self) -> list[RawEntityRecord]:
        if self._markdown is None:
            self._markdown = await self._fetch_markdown()
            self._entries = self._parse_entries(self._markdown)
        now = datetime.now(timezone.utc)
        records: list[RawEntityRecord] = []
        seen_urls: set[str] = set()
        seen_names: set[str] = set()
        for entry in self._entries:
            if len(records) >= self.settings.ai_device_limit:
                break
            if entry["mode"] != "include":
                continue
            if not self._is_candidate_entry(entry):
                continue
            record = self._record_from_entry(entry, fetched_at=now)
            if record is None:
                continue
            normalized_url = normalize_url(record.url)
            # The source occasionally links two distinct boards to one generic
            # catalog page; keep the first device-specific occurrence only.
            if normalized_url in seen_urls:
                continue
            key = f"{record.entity_type}:{record.name.lower()}:{normalized_url}"
            if key in seen_names:
                continue
            seen_urls.add(normalized_url)
            seen_names.add(key)
            records.append(record)
        return records

    def _dedupe_by_url(self, entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Keep the first entry per normalized canonical URL.

        The source occasionally links two distinct boards to one generic
        catalog page; keeping the first device-specific occurrence avoids
        conflation under deterministic URL identity.
        """
        deduped: list[dict[str, Any]] = []
        seen_urls: set[str] = set()
        for entry in entries:
            url, _vendor = self._url_and_vendor_from_entry(entry)
            normalized = normalize_url(url)
            if not normalized or normalized in seen_urls:
                continue
            seen_urls.add(normalized)
            deduped.append(entry)
        return deduped

    async def _fetch_markdown(self) -> str:
        response = await self.client.get_json(self.settings.ai_device_catalog_api_url)
        data = response.data
        if not isinstance(data, dict):
            raise SourceFetchError(FailureClass.MALFORMED_JSON, "AI device catalog contents payload was not an object")
        content = data.get("content")
        encoding = data.get("encoding")
        if not isinstance(content, str) or encoding != "base64":
            raise SourceFetchError(FailureClass.MALFORMED_JSON, "AI device catalog missing base64 Markdown content")
        try:
            return base64.b64decode(content).decode("utf-8", "replace")
        except ValueError as exc:
            raise SourceFetchError(FailureClass.MALFORMED_JSON, "AI device catalog had malformed base64 content") from exc

    def _parse_entries(self, markdown: str) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []
        current: dict[str, Any] | None = None
        mode = "exclude"
        for line in markdown.splitlines():
            stripped = line.strip()
            if stripped.startswith("#### "):
                title = stripped[5:].strip().lower()
                if any(marker in title for marker in _INCLUDE_SECTION_MARKERS):
                    mode = "include"
                elif any(marker in title for marker in _EXCLUDE_SECTION_MARKERS):
                    mode = "exclude"
                continue
            if stripped.startswith("### "):
                title = stripped[4:].strip().lower()
                if any(marker in title for marker in _EXCLUDE_SECTION_MARKERS):
                    mode = "exclude"
                elif any(marker in title for marker in _INCLUDE_SECTION_MARKERS) or "boards with" in title:
                    mode = "include"
                continue
            if line.startswith("- "):
                if current is not None:
                    entries.append(current)
                current = {"name": line[2:].strip(), "fields": [], "mode": mode}
                continue
            if stripped.startswith("- "):
                if current is not None:
                    current["fields"].append(stripped[2:].strip())
                continue
        if current is not None:
            entries.append(current)
        return entries

    def _record_from_entry(self, entry: dict[str, Any], *, fetched_at=None) -> RawEntityRecord | None:
        if not self._is_candidate_entry(entry):
            return None
        name = " ".join(str(entry.get("name") or "").split())
        processor = self._processor_from_entry(entry)
        supports = self._field_by_prefix(entry, "supports")
        price = self._field_by_prefix(entry, "price:")
        url, vendor = self._url_and_vendor_from_entry(entry)
        manufacturer, manufacturer_evidence = _derive_manufacturer(name)
        tokens = _accelerator_tokens(" ".join([name, processor or "", supports or ""]))
        description = self._description_from_entry(entry, processor, supports, price)
        return RawEntityRecord(
            source_key=f"ai-device-catalog:device:{_slugify(name)}",
            entity_type="device",
            name=name,
            description=description,
            url=normalize_url(url),
            categories=["Devices"],
            source_name=self.name,
            source_url=normalize_url(self.settings.ai_device_catalog_api_url),
            raw={
                "board_name": name,
                "fields": entry.get("fields"),
                "section_mode": entry.get("mode"),
            },
            metadata={
                "device": {
                    "canonical_url": normalize_url(url),
                    "device_class": "embedded-ai-board",
                    "manufacturer": manufacturer,
                    "manufacturer_evidence": manufacturer_evidence,
                    "vendor": vendor,
                    "vendor_url": normalize_url(url),
                    "processor": processor,
                    "supports": supports,
                    "price": _clean_markdown(price) if price else None,
                    "ai_relevance_evidence": {
                        "matched_tokens": tokens,
                        "excerpt": (processor or name)[:200],
                    },
                }
            },
            fetched_at=fetched_at,
        )

    def _is_candidate_entry(self, entry: dict[str, Any]) -> bool:
        if not isinstance(entry, dict):
            return False
        name = str(entry.get("name") or "").strip()
        if not name:
            return False
        url, _vendor = self._url_and_vendor_from_entry(entry)
        if not is_valid_http_url(url):
            return False
        processor = self._processor_from_entry(entry)
        if not processor:
            return False
        if not _accelerator_tokens(" ".join([name, processor])):
            return False
        return True

    def _processor_from_entry(self, entry: dict[str, Any]) -> str | None:
        value = self._field_by_prefix(entry, "mcu:")
        return value if value else None

    def _field_by_prefix(self, entry: dict[str, Any], prefix: str) -> str | None:
        for field in entry.get("fields") or []:
            text = " ".join(str(field).split())
            if text.lower().startswith(prefix.lower()):
                remainder = text[len(prefix):].strip()
                if remainder:
                    return _clean_markdown(remainder)
        return None

    def _url_and_vendor_from_entry(self, entry: dict[str, Any]) -> tuple[str, str | None]:
        # Prefer the price line's link (the vendor product page), then any
        # "More info" link as a fallback.
        price = self._field_by_prefix(entry, "price:")
        if price is not None:
            for field in entry.get("fields") or []:
                if " ".join(str(field).split()).lower().startswith("price:"):
                    links = _extract_links(str(field))
                    if links:
                        return links[0][1], links[0][0]
        for field in entry.get("fields") or []:
            lower = " ".join(str(field).split()).lower()
            if lower.startswith("more info:"):
                links = _extract_links(str(field))
                if links:
                    return links[0][1], links[0][0]
        return "", None

    def _description_from_entry(self, entry: dict[str, Any], processor: str | None, supports: str | None, price: str | None) -> str:
        parts: list[str] = []
        if processor:
            parts.append(f"MCU: {processor}")
        if supports:
            parts.append(supports)
        if price:
            parts.append(f"Price: {_clean_markdown(price)}")
        if not parts:
            parts.append("AI/ML embedded board listed in the source device catalog.")
        return "; ".join(parts)


def _slugify(name: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return value or "unknown"
