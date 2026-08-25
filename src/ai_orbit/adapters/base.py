from __future__ import annotations

from abc import ABC, abstractmethod

from src.ai_orbit.models import RawEntityRecord, SourceFeasibility


class SourceAdapter(ABC):
    name: str

    @abstractmethod
    async def verify(self) -> SourceFeasibility:
        raise NotImplementedError

    @abstractmethod
    async def discover(self) -> list[RawEntityRecord]:
        raise NotImplementedError
