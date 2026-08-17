from __future__ import annotations

import asyncio
import random
from abc import ABC, abstractmethod
from typing import Any

import httpx

from .schemas import ExtractionResult, ReviewResult


class ProviderError(RuntimeError):
    pass


class LLMProvider(ABC):
    name: str
    model: str

    @abstractmethod
    async def extract(self, evidence: str) -> ExtractionResult:
        raise NotImplementedError

    @abstractmethod
    async def review(
        self,
        evidence: str,
        draft: ExtractionResult,
    ) -> ReviewResult:
        raise NotImplementedError

    @abstractmethod
    async def adjudicate(
        self,
        evidence: str,
        gemini: ExtractionResult,
        cohere: ReviewResult,
    ) -> ExtractionResult:
        raise NotImplementedError

    async def fallback_extract(
        self,
        evidence: str,
    ) -> ExtractionResult:
        raise NotImplementedError(
            f"{self.name} does not support fallback extraction"
        )


async def _request_with_retry(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    headers: dict[str, str],
    json: dict[str, Any],
    attempts: int = 3,
) -> dict[str, Any]:
    for attempt in range(attempts):
        try:
            response = await client.request(
                method,
                url,
                headers=headers,
                json=json,
            )

            if response.status_code == 429:
                retry_after = response.headers.get("Retry-After")

                if retry_after:
                    try:
                        delay = float(retry_after)
                    except ValueError:
                        delay = 2.0
                else:
                    delay = 2**attempt

                delay += random.uniform(0, 0.5)

                if attempt == attempts - 1:
                    raise ProviderError(
                        f"HTTP 429 after {attempts} attempts"
                    )

                await asyncio.sleep(min(delay, 30.0))
                continue

            if response.status_code in {500, 502, 503, 504}:
                if attempt == attempts - 1:
                    raise ProviderError(
                        f"HTTP {response.status_code} after "
                        f"{attempts} attempts: {response.text[:500]}"
                    )

                delay = min(2**attempt, 10) + random.uniform(0, 0.5)
                await asyncio.sleep(delay)
                continue

            if response.status_code == 413:
                raise ProviderError(
                    "HTTP 413: request payload too large"
                )

            if response.is_error:
                raise ProviderError(
                    f"HTTP {response.status_code}: {response.text}"
                )

            try:
                return response.json()
            except ValueError as exc:
                raise ProviderError(
                    "Provider returned invalid JSON"
                ) from exc

        except httpx.TimeoutException as exc:
            if attempt == attempts - 1:
                raise ProviderError(
                    f"Request timed out after {attempts} attempts"
                ) from exc

            delay = min(2**attempt, 10) + random.uniform(0, 0.5)
            await asyncio.sleep(delay)

        except httpx.RequestError as exc:
            if attempt == attempts - 1:
                raise ProviderError(
                    f"Provider request failed: {exc}"
                ) from exc

            delay = min(2**attempt, 10) + random.uniform(0, 0.5)
            await asyncio.sleep(delay)

    raise ProviderError("Provider request failed")


class GeminiProvider(LLMProvider):
    name = "gemini"

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-3.7-flash",
    ):
        self.api_key = api_key
        self.model = model

    async def _call(
        self,
        prompt: str,
        schema: dict[str, Any],
    ) -> str:
        url = (
            "https://generativelanguage.googleapis.com/"
            "v1beta/interactions"
        )

        payload = {
            "model": self.model,
            "input": prompt,
            "response_format": {
                "type": "text",
                "mime_type": "application/json",
                "schema": schema,
            },
        }

        headers = {
            "x-goog-api-key": self.api_key,
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            data = await _request_with_retry(
                client,
                "POST",
                url,
                headers=headers,
                json=payload,
            )

        for step in data.get("steps", []):
            if step.get("type") != "model_output":
                continue

            for content in step.get("content", []):
                if content.get("type") == "text":
                    text = content.get("text")
                    if text:
                        return text

        raise ProviderError(
            "Gemini returned no model output"
        )

    async def extract(
        self,
        evidence: str,
    ) -> ExtractionResult:
        from .prompts import gemini_prompt

        schema = {
            "type": "object",
            "properties": {
                "company": {
                    "type": ["string", "null"],
                },
                "role_family": {
                    "type": ["string", "null"],
                },
                "is_remote": {
                    "type": ["boolean", "null"],
                },
                "summary": {
                    "type": ["string", "null"],
                },
                "evidence_quotes": {
                    "type": "array",
                    "items": {
                        "type": "string",
                    },
                },
                "claims": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "field": {
                                "type": "string",
                            },
                            "value": {
                                "type": [
                                    "string",
                                    "boolean",
                                    "null",
                                ],
                            },
                            "evidence_quote": {
                                "type": [
                                    "string",
                                    "null",
                                ],
                            },
                            "supported": {
                                "type": "boolean",
                            },
                        },
                        "required": [
                            "field",
                            "value",
                            "evidence_quote",
                            "supported",
                        ],
                    },
                },
            },
            "required": [
                "company",
                "role_family",
                "is_remote",
                "summary",
                "evidence_quotes",
                "claims",
            ],
        }

        text = await self._call(
            gemini_prompt(evidence),
            schema,
        )

        return ExtractionResult.model_validate_json(text)

    async def review(
        self,
        evidence: str,
        draft: ExtractionResult,
    ) -> ReviewResult:
        raise NotImplementedError(
            "Gemini is the initial extraction stage"
        )

    async def adjudicate(
        self,
        evidence: str,
        gemini: ExtractionResult,
        cohere: ReviewResult,
    ) -> ExtractionResult:
        raise NotImplementedError(
            "Gemini is not the final adjudication stage"
        )


class CohereProvider(LLMProvider):
    name = "cohere"

    def __init__(
        self,
        api_key: str,
        model: str = "command-a-plus-05-2026",
    ):
        self.api_key = api_key
        self.model = model

    async def _call(
        self,
        prompt: str,
        schema: dict[str, Any],
    ) -> str:
        url = "https://api.cohere.com/v2/chat"

        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
            "temperature": 0,
            "response_format": {
                "type": "json_object",
                "schema": schema,
            },
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            data = await _request_with_retry(
                client,
                "POST",
                url,
                headers=headers,
                json=payload,
            )

        try:
            content = data["message"]["content"]

            if isinstance(content, list):
                for item in content:
                    if (
                        isinstance(item, dict)
                        and item.get("type") == "text"
                    ):
                        text = item.get("text")
                        if text:
                            return text

            if isinstance(content, str) and content:
                return content

        except (KeyError, TypeError):
            pass

        raise ProviderError(
            f"Cohere returned no usable text output: {data}"
        )

    async def extract(
        self,
        evidence: str,
    ) -> ExtractionResult:
        return await self.fallback_extract(evidence)

    async def fallback_extract(
        self,
        evidence: str,
    ) -> ExtractionResult:
        from .prompts import gemini_prompt

        schema = {
            "type": "object",
            "properties": {
                "company": {
                    "type": ["string", "null"],
                },
                "role_family": {
                    "type": ["string", "null"],
                },
                "is_remote": {
                    "type": ["boolean", "null"],
                },
                "summary": {
                    "type": ["string", "null"],
                },
                "evidence_quotes": {
                    "type": "array",
                    "items": {
                        "type": "string",
                    },
                },
                "claims": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "field": {
                                "type": "string",
                            },
                            "value": {
                                "type": [
                                    "string",
                                    "boolean",
                                    "null",
                                ],
                            },
                            "evidence_quote": {
                                "type": [
                                    "string",
                                    "null",
                                ],
                            },
                            "supported": {
                                "type": "boolean",
                            },
                        },
                        "required": [
                            "field",
                            "value",
                            "evidence_quote",
                            "supported",
                        ],
                        "additionalProperties": False,
                    },
                },
            },
            "required": [
                "company",
                "role_family",
                "is_remote",
                "summary",
                "evidence_quotes",
                "claims",
            ],
            "additionalProperties": False,
        }

        text = await self._call(
            gemini_prompt(
                evidence,
                execution_mode="fallback",
            ),
            schema,
        )

        return ExtractionResult.model_validate_json(text)

    async def review(
        self,
        evidence: str,
        draft: ExtractionResult,
    ) -> ReviewResult:
        from .prompts import cohere_prompt

        text = await self._call(
            cohere_prompt(
                evidence,
                draft,
                execution_mode="primary",
            ),
            ReviewResult.model_json_schema(),
        )

        return ReviewResult.model_validate_json(text)

    async def adjudicate(
        self,
        evidence: str,
        gemini: ExtractionResult,
        cohere: ReviewResult,
    ) -> ExtractionResult:
        raise NotImplementedError(
            "Cohere is the review stage"
        )


class GroqProvider(LLMProvider):
    name = "groq"

    def __init__(
        self,
        api_key: str,
        model: str = "openai/gpt-oss-120b",
    ):
        self.api_key = api_key
        self.model = model

    async def _call(
        self,
        prompt: str,
    ) -> str:
        url = (
            "https://api.groq.com/openai/v1/"
            "chat/completions"
        )

        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are the final adjudication stage "
                        "of a factual extraction pipeline. "
                        "Return only valid JSON. "
                        "Use only information supported by "
                        "the provided evidence. "
                        "Do not guess or use outside knowledge."
                    ),
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "extraction_result",
                    "schema": {
                        "type": "object",
                        "properties": {
                            "company": {
                                "type": [
                                    "string",
                                    "null",
                                ]
                            },
                            "role_family": {
                                "type": [
                                    "string",
                                    "null",
                                ]
                            },
                            "is_remote": {
                                "type": [
                                    "boolean",
                                    "null",
                                ]
                            },
                            "summary": {
                                "type": [
                                    "string",
                                    "null",
                                ]
                            },
                            "evidence_quotes": {
                                "type": "array",
                                "items": {
                                    "type": "string"
                                },
                            },
                            "claims": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "field": {
                                            "type": "string"
                                        },
                                        "value": {
                                            "type": [
                                                "string",
                                                "boolean",
                                                "null",
                                            ]
                                        },
                                        "evidence_quote": {
                                            "type": [
                                                "string",
                                                "null",
                                            ]
                                        },
                                        "supported": {
                                            "type": "boolean"
                                        },
                                    },
                                    "required": [
                                        "field",
                                        "value",
                                        "evidence_quote",
                                        "supported",
                                    ],
                                    "additionalProperties": False,
                                },
                            },
                        },
                        "required": [
                            "company",
                            "role_family",
                            "is_remote",
                            "summary",
                            "evidence_quotes",
                            "claims",
                        ],
                        "additionalProperties": False,
                    },
                },
            },
            "temperature": 0,
        }

        async with httpx.AsyncClient(timeout=90.0) as client:
            data = await _request_with_retry(
                client,
                "POST",
                url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )

        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError(
                "Groq returned no usable content"
            ) from exc

    async def extract(
        self,
        evidence: str,
    ) -> ExtractionResult:
        return await self.fallback_extract(evidence)

    async def fallback_extract(
        self,
        evidence: str,
    ) -> ExtractionResult:
        from .prompts import gemini_prompt

        text = await self._call(
            gemini_prompt(
                evidence,
                execution_mode="fallback",
            )
        )

        return ExtractionResult.model_validate_json(text)

    async def review(
        self,
        evidence: str,
        draft: ExtractionResult,
    ) -> ReviewResult:
        raise NotImplementedError(
            "Groq is the final adjudication stage"
        )

    async def adjudicate(
        self,
        evidence: str,
        gemini: ExtractionResult,
        cohere: ReviewResult,
        execution_mode: str = "primary",
    ) -> ExtractionResult:
        from .prompts import groq_prompt

        text = await self._call(
            groq_prompt(
                evidence,
                gemini,
                cohere,
                execution_mode=execution_mode,
            )
        )

        return ExtractionResult.model_validate_json(text)