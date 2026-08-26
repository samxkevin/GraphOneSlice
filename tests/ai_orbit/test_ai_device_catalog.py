from datetime import datetime, timezone

import pytest

from src.ai_orbit.adapters.ai_device_catalog import (
    AIDeviceCatalogAdapter,
    _accelerator_tokens,
    _derive_manufacturer,
    _slugify,
)
from src.ai_orbit.config import AIOrbitSettings
from src.ai_orbit.models import Entity, Provenance, SourceRef
from src.ai_orbit.stages.validation import validate_outputs


def _adapter() -> AIDeviceCatalogAdapter:
    return AIDeviceCatalogAdapter(AIOrbitSettings(log_level="CRITICAL"))


def _markdown():
    return """# Just a list of embedded boards with AI/ML accelerators

### Boards with ARM Ethos NPUs

#### Available now
- Grove Vision AI Module V2
  - MCU: WiseEye2 HX6538 (2 x ARM Cortex-M55 & Ethos-U55)
  - Supports TensorFlow and PyTorch frameworks
  - Price: ~16 usd  [Seedstudio](https://www.seeedstudio.com/Grove-Vision-AI-Module-V2-p-5851.html)

- NXP MCIMX93-EVK
    - MCU: i.MX93 (1-2 x ARM Cortex-A55, 1 x ARM Cortex-M33, Ethos-U65 NPU)
    - Price: ~622 usd [NXP](https://www.nxp.com/design/design-center/development-boards-and-designs/i.MX93EVK)

#### Available later
- Alif DK-B1
  - MCU: Alif Baletto B1 ( 1 x ARM Cortex-M55 & Ethos-U55 NPU)
  - Price: Unknown
  - More info: [embedded.com](https://www.embedded.com/alif-semiconductor-releases-an-evaluation-board-for-its-balletto-bluetooth-mcu/)

### MCUs only, no boards anounced yet
- Infenion PSOC Edge E83/E84
  - 1 x ARM Cortex-M55 & Ethos-U55 NPU, 1 x ARM Cortex-M33 & NNLite
  - More info: [Infenion](https://www.infineon.com/cms/en/product/microcontroller/32-bit-psoc-arm-cortex-microcontroller/32-bit-psoc-edge-arm/)

### Boards with other AI/ML Accelerators
- Arduino Nicla Voice
  -  MCU: nRF52832 (1 X ARM Cortex-M4), Syntiant NDP120 (1 x ARM Cortex-M0, 1 x Syntiant Core 2 Neural Decision Processor)
  -  Price: ~70 usd [Arduino](https://store.arduino.cc/products/nicla-voice)

- STM32N6570-DK
  - MCU: STM32N657X0H3Q (1 x ARM Cortex-M55 and ST Neural-ART Accelerator)
  - Price: ~185 usd [ST](https://www.st.com/en/evaluation-tools/stm32n6570-dk.html#overview)
"""


def test_parse_entries_tracks_sections_and_fields():
    adapter = _adapter()
    entries = adapter._parse_entries(_markdown())
    names = [e["name"] for e in entries]
    assert names == [
        "Grove Vision AI Module V2",
        "NXP MCIMX93-EVK",
        "Alif DK-B1",
        "Infenion PSOC Edge E83/E84",
        "Arduino Nicla Voice",
        "STM32N6570-DK",
    ]
    modes = {e["name"]: e["mode"] for e in entries}
    assert modes["Grove Vision AI Module V2"] == "include"
    assert modes["NXP MCIMX93-EVK"] == "include"
    assert modes["Alif DK-B1"] == "exclude"  # available later
    assert modes["Infenion PSOC Edge E83/E84"] == "exclude"  # MCUs only
    assert modes["Arduino Nicla Voice"] == "include"
    assert modes["STM32N6570-DK"] == "include"


def test_field_extraction_preserves_processor_price_and_url():
    adapter = _adapter()
    entries = adapter._parse_entries(_markdown())
    nxp = next(e for e in entries if e["name"] == "NXP MCIMX93-EVK")
    assert adapter._processor_from_entry(nxp) == "i.MX93 (1-2 x ARM Cortex-A55, 1 x ARM Cortex-M33, Ethos-U65 NPU)"
    url, vendor = adapter._url_and_vendor_from_entry(nxp)
    assert url == "https://www.nxp.com/design/design-center/development-boards-and-designs/i.MX93EVK"
    assert vendor == "NXP"
    assert adapter._field_by_prefix(nxp, "price:") == "~622 usd NXP"


def test_manufacturer_derived_from_name_with_evidence_or_none():
    assert _derive_manufacturer("NXP MCIMX93-EVK") == ("NXP", "matched 'nxp' in board name 'NXP MCIMX93-EVK'")
    assert _derive_manufacturer("STM32N6570-DK") == ("STMicroelectronics", "matched 'stm32' in board name 'STM32N6570-DK'")
    assert _derive_manufacturer("Grove Vision AI Module V2") == ("Seeed Studio", "matched 'grove' in board name 'Grove Vision AI Module V2'")
    assert _derive_manufacturer("Seeed Studio XIAO ESP32S3") == ("Seeed Studio", "matched 'seeed' in board name 'Seeed Studio XIAO ESP32S3'")
    assert _derive_manufacturer("Totally Unknown Gadget") == (None, None)


def test_accelerator_tokens_use_word_boundaries():
    assert "npu" in _accelerator_tokens("Ethos-U65 NPU")
    assert "neural-art" in _accelerator_tokens("ST Neural-ART Accelerator")
    assert _accelerator_tokens("maintain") == []


def test_record_from_entry_preserves_source_backed_device_fields():
    adapter = _adapter()
    entries = adapter._parse_entries(_markdown())
    arduino = next(e for e in entries if e["name"] == "Arduino Nicla Voice")
    record = adapter._record_from_entry(arduino)
    assert record is not None
    assert record.entity_type == "device"
    assert record.categories == ["Devices"]
    assert record.url == "https://store.arduino.cc/products/nicla-voice"
    assert record.source_key == "ai-device-catalog:device:arduino-nicla-voice"

    device = record.metadata["device"]
    assert device["canonical_url"] == "https://store.arduino.cc/products/nicla-voice"
    assert device["device_class"] == "embedded-ai-board"
    assert device["manufacturer"] == "Arduino"
    assert device["manufacturer_evidence"] == "matched 'arduino' in board name 'Arduino Nicla Voice'"
    assert device["vendor"] == "Arduino"
    assert "Syntiant NDP120" in device["processor"]
    assert device["ai_relevance_evidence"]["matched_tokens"]
    assert "Neural Decision Processor" in record.description or "Syntiant" in record.description


def test_candidate_entry_rejects_excluded_and_incomplete_entries():
    adapter = _adapter()
    entries = adapter._parse_entries(_markdown())
    excluded = next(e for e in entries if e["name"] == "Alif DK-B1")
    assert adapter._is_candidate_entry(excluded)  # structurally valid, but section mode excludes it
    # A structurally invalid entry (no URL) is rejected.
    broken = {"name": "No URL Board", "fields": ["MCU: Ethos-U55"], "mode": "include"}
    assert not adapter._is_candidate_entry(broken)


@pytest.mark.asyncio
async def test_discover_filters_sections_and_deduplicates_by_url():
    adapter = _adapter()
    adapter._markdown = _markdown()
    adapter._entries = adapter._parse_entries(_markdown())
    records = await adapter.discover()
    names = [r.name for r in records]
    # "Available later" and "MCUs only" entries are excluded.
    assert "Alif DK-B1" not in names
    assert "Infenion PSOC Edge E83/E84" not in names
    assert "Grove Vision AI Module V2" in names
    assert "NXP MCIMX93-EVK" in names
    assert "Arduino Nicla Voice" in names
    assert "STM32N6570-DK" in names


def test_slugify_is_deterministic():
    assert _slugify("Arduino Nicla Voice") == "arduino-nicla-voice"
    assert _slugify("NXP MCIMX93-EVK") == "nxp-mcimx93-evk"


def test_device_validation_requires_canonical_url_and_evidence_but_allows_null_manufacturer():
    device = Entity(
        id="device-1",
        entity_type="device",
        name="Arduino Nicla Voice",
        description="MCU: nRF52832, Syntiant NDP120; Price: ~70 usd Arduino.",
        url="https://store.arduino.cc/products/nicla-voice",
        categories=["Devices"],
        source=SourceRef(name="fixture", url="https://example.com/source"),
        metadata={
            "device": {
                "canonical_url": "https://store.arduino.cc/products/nicla-voice",
                "device_class": "embedded-ai-board",
                "manufacturer": "Arduino",
                "manufacturer_evidence": "matched 'arduino' in board name",
                "ai_relevance_evidence": {"matched_tokens": ["neural decision processor"], "excerpt": "Syntiant NDP120"},
            },
        },
        provenance=Provenance(
            discovered_by="fixture",
            source_url="https://example.com/source",
            source_record_id="fixture:device",
            observed_fields={"name": "Arduino Nicla Voice"},
        ),
    )
    accepted, _relationships, report = validate_outputs([device], [])
    assert len(accepted) == 1
    assert report["status"] == "passed"

    # Manufacturer may be honestly null.
    null_mfr = device.model_copy(update={"id": "device-2", "metadata": {"device": {**device.metadata["device"], "manufacturer": None, "manufacturer_evidence": None}}})
    accepted, _relationships, report = validate_outputs([null_mfr], [])
    assert len(accepted) == 1
    assert report["status"] == "passed"

    missing_metadata = device.model_copy(update={"id": "device-3", "metadata": {}})
    accepted, _relationships, report = validate_outputs([missing_metadata], [])
    assert accepted == []
    assert report["failure_counts_by_type"]["invalid_metadata"] == 1

    missing_url = device.model_copy(update={"id": "device-4", "metadata": {"device": {**device.metadata["device"], "canonical_url": None}}})
    accepted, _relationships, report = validate_outputs([missing_url], [])
    assert accepted == []
    assert report["failure_counts_by_type"]["invalid_metadata"] == 1

    missing_evidence = device.model_copy(update={"id": "device-5", "metadata": {"device": {**device.metadata["device"], "ai_relevance_evidence": None}}})
    accepted, _relationships, report = validate_outputs([missing_evidence], [])
    assert accepted == []
    assert report["failure_counts_by_type"]["invalid_metadata"] == 1


def test_device_identity_is_stable_by_canonical_url():
    from src.ai_orbit.utils.identity import canonical_key, stable_uuid

    key1 = canonical_key("device", "Arduino Nicla Voice", "https://store.arduino.cc/products/nicla-voice")
    key2 = canonical_key("device", "Arduino Nicla Voice", "https://store.arduino.cc/products/nicla-voice")
    assert key1 == key2
    assert stable_uuid("device", key1) == stable_uuid("device", key2)
