from datetime import datetime, timezone

import pytest

from src.ai_orbit.adapters.base import SourceAdapter
from src.ai_orbit.config import AIOrbitSettings
from src.ai_orbit.models import RawEntityRecord, SourceFeasibility
from src.ai_orbit.pipeline import run_ai_orbit_pipeline


class GoodAdapter(SourceAdapter):
    name = "good fixture"

    async def verify(self) -> SourceFeasibility:
        return SourceFeasibility(
            source_name=self.name,
            source_type="API/JSON",
            access_method="fixture",
            url="https://example.com/good",
            status="usable",
            authentication_required=False,
        )

    async def discover(self) -> list[RawEntityRecord]:
        return [
            RawEntityRecord(
                source_key="fixture:tool",
                entity_type="tool",
                name="Fixture Tool",
                description="Fixture tool from a successful adapter.",
                url="https://example.com/tool",
                categories=["Tools"],
                source_name=self.name,
                source_url="https://example.com/good",
                raw={},
                fetched_at=datetime.now(timezone.utc),
            )
        ]


class FailingAdapter(SourceAdapter):
    name = "failing fixture"

    async def verify(self) -> SourceFeasibility:
        return SourceFeasibility(
            source_name=self.name,
            source_type="API/JSON",
            access_method="fixture",
            url="https://example.com/failing",
            status="unusable",
            authentication_required=False,
            failure_behavior="network: fixture failure",
        )

    async def discover(self) -> list[RawEntityRecord]:  # pragma: no cover - verify should prevent this
        raise AssertionError("discover should not be called for unusable source")


@pytest.mark.asyncio
async def test_failing_source_isolated_from_successful_records():
    settings = AIOrbitSettings(output_dir="data/test-ai-orbit", log_level="CRITICAL")
    state = await run_ai_orbit_pipeline(settings, adapters=[FailingAdapter(), GoodAdapter()], write_files=False)
    assert len(state.entities) == 1
    assert state.entities[0].name == "Fixture Tool"
    assert state.source_failures[0]["source"] == "failing fixture"
    assert state.metrics["validation_status"] == "passed"
