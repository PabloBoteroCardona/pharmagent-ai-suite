"""Tests unitarios de `verify_api_key` (autenticación por cabecera `X-API-Key`)."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from src.infrastructure.api import security


class TestVerifyApiKey:
    @pytest.mark.asyncio
    async def test_allows_any_request_when_api_key_not_configured(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(security.settings, "api_key", None)

        await security.verify_api_key(x_api_key=None)
        await security.verify_api_key(x_api_key="anything")

    @pytest.mark.asyncio
    async def test_accepts_matching_api_key(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(security.settings, "api_key", "secret-key")

        await security.verify_api_key(x_api_key="secret-key")

    @pytest.mark.asyncio
    async def test_rejects_missing_api_key(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(security.settings, "api_key", "secret-key")

        with pytest.raises(HTTPException) as exc_info:
            await security.verify_api_key(x_api_key=None)

        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_rejects_wrong_api_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(security.settings, "api_key", "secret-key")

        with pytest.raises(HTTPException) as exc_info:
            await security.verify_api_key(x_api_key="wrong-key")

        assert exc_info.value.status_code == 401
