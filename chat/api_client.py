"""HTTP client for the orchestrator FastAPI app (see orchestrator.main)."""

from __future__ import annotations

from typing import Any

import httpx


class OrchestratorClient:
    def __init__(self, base_url: str, timeout: float = 300.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def health(self) -> dict[str, Any]:
        r = httpx.get(f"{self.base_url}/health", timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    def list_flows(self) -> list[dict[str, Any]]:
        r = httpx.get(f"{self.base_url}/orchestrate/flows", timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    def orchestrate_json(
        self,
        *,
        user_prompt: str,
        chat_history: list[dict[str, str]],
        model: str | None = None,
        context: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "user_prompt": user_prompt,
            "chat_history": chat_history,
            "model": model,
            "context": context,
            "metadata": metadata,
        }
        r = httpx.post(
            f"{self.base_url}/orchestrate/json",
            json=payload,
            timeout=self.timeout,
        )
        r.raise_for_status()
        return r.json()

    def named_flow(
        self,
        flow_id: str,
        *,
        user_prompt: str,
        chat_history: list[dict[str, str]],
        model: str | None = None,
        context: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "user_prompt": user_prompt,
            "chat_history": chat_history,
            "model": model,
            "context": context,
            "metadata": metadata,
        }
        r = httpx.post(
            f"{self.base_url}/orchestrate/flows/{flow_id}",
            json=payload,
            timeout=self.timeout,
        )
        r.raise_for_status()
        return r.json()
