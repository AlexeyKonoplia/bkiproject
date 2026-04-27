from __future__ import annotations

from typing import Any

import httpx

from app.config import settings


class UpstreamApiError(RuntimeError):
    def __init__(self, status_code: int, payload: Any):
        self.status_code = status_code
        self.payload = payload
        super().__init__(str(payload))


async def post_json(path: str, payload: dict[str, Any], *, authorization: str | None = None) -> Any:
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if authorization:
        headers["Authorization"] = authorization

    async with httpx.AsyncClient(base_url=settings.APP_API_URL, timeout=60.0) as client:
        response = await client.post(path, json=payload, headers=headers)

    try:
        data = response.json()
    except ValueError:
        data = response.text

    if response.is_error:
        raise UpstreamApiError(response.status_code, data)
    return data


async def post_multipart(
    path: str,
    *,
    data: dict[str, Any],
    files: dict[str, tuple[str, bytes, str]],
    authorization: str | None = None,
) -> Any:
    headers: dict[str, str] = {}
    if authorization:
        headers["Authorization"] = authorization

    async with httpx.AsyncClient(base_url=settings.APP_API_URL, timeout=120.0) as client:
        response = await client.post(path, data=data, files=files, headers=headers)

    try:
        payload = response.json()
    except ValueError:
        payload = response.text

    if response.is_error:
        raise UpstreamApiError(response.status_code, payload)
    return payload
