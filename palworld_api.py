"""Asynchronous client for Palworld Dedicated Server REST API."""

from __future__ import annotations

import logging
from typing import Any, Optional

import aiohttp

logger = logging.getLogger("palworld_bot.api")


class PalworldAPI:
    """Client for interacting with Palworld's native REST API (port 8212 by default)."""

    def __init__(self, base_url: str = "http://127.0.0.1:8212", admin_password: str = ""):
        self.base_url = base_url.rstrip("/")
        self.admin_password = admin_password

    @property
    def is_configured(self) -> bool:
        return bool(self.admin_password and self.admin_password.strip())

    def _get_auth(self) -> Optional[aiohttp.BasicAuth]:
        if not self.is_configured:
            return None
        return aiohttp.BasicAuth("admin", self.admin_password)

    async def get_info(self) -> Optional[dict[str, Any]]:
        """Fetch server information (version, server name, description)."""
        if not self.is_configured:
            return None
        url = f"{self.base_url}/v1/api/info"
        try:
            timeout = aiohttp.ClientTimeout(total=4)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url, auth=self._get_auth()) as resp:
                    if resp.status == 200:
                        return await resp.json()
        except Exception as exc:
            logger.debug(f"REST API get_info failed: {exc}")
        return None

    async def is_online(self) -> bool:
        """Check if the REST API endpoint responds."""
        info = await self.get_info()
        return info is not None

    async def get_metrics(self) -> Optional[dict[str, Any]]:
        """Fetch server metrics (serverfps, currentplayernum, maxplayernum, uptime, etc.)."""
        if not self.is_configured:
            return None
        url = f"{self.base_url}/v1/api/metrics"
        try:
            timeout = aiohttp.ClientTimeout(total=4)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url, auth=self._get_auth()) as resp:
                    if resp.status == 200:
                        return await resp.json()
        except Exception as exc:
            logger.debug(f"REST API get_metrics failed: {exc}")
        return None

    async def get_players(self) -> list[dict[str, Any]]:
        """Fetch list of connected players with name, ping, level, and player IDs."""
        if not self.is_configured:
            return []
        url = f"{self.base_url}/v1/api/players"
        try:
            timeout = aiohttp.ClientTimeout(total=4)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url, auth=self._get_auth()) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data.get("players", [])
        except Exception as exc:
            logger.debug(f"REST API get_players failed: {exc}")
        return []

    async def save_world(self) -> tuple[bool, str]:
        """Trigger an immediate world save."""
        if not self.is_configured:
            return False, "REST API admin password is not configured."
        url = f"{self.base_url}/v1/api/save"
        try:
            timeout = aiohttp.ClientTimeout(total=15)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, auth=self._get_auth()) as resp:
                    if resp.status == 200:
                        return True, "World saved successfully."
                    body = await resp.text()
                    return False, f"Server returned HTTP {resp.status}: {body}"
        except Exception as exc:
            return False, f"Failed to connect to Palworld REST API: {exc}"

    async def announce(self, message: str) -> tuple[bool, str]:
        """Broadcast an on-screen message to all active players."""
        if not self.is_configured:
            return False, "REST API admin password is not configured."
        url = f"{self.base_url}/v1/api/announce"
        try:
            timeout = aiohttp.ClientTimeout(total=5)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, auth=self._get_auth(), json={"message": message}) as resp:
                    if resp.status == 200:
                        return True, "Announcement sent."
                    body = await resp.text()
                    return False, f"Server returned HTTP {resp.status}: {body}"
        except Exception as exc:
            return False, f"Failed to connect to Palworld REST API: {exc}"

    async def shutdown(self, wait_seconds: int = 30, message: str = "") -> tuple[bool, str]:
        """Gracefully shut down the dedicated server with a countdown message."""
        if not self.is_configured:
            return False, "REST API admin password is not configured."
        url = f"{self.base_url}/v1/api/shutdown"
        payload: dict[str, Any] = {"waittime": wait_seconds}
        if message:
            payload["message"] = message
        try:
            timeout = aiohttp.ClientTimeout(total=5)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, auth=self._get_auth(), json=payload) as resp:
                    if resp.status == 200:
                        return True, f"Shutdown scheduled in {wait_seconds}s."
                    body = await resp.text()
                    return False, f"Server returned HTTP {resp.status}: {body}"
        except Exception as exc:
            return False, f"Failed to connect to Palworld REST API: {exc}"

    async def stop(self) -> tuple[bool, str]:
        """Force stop the dedicated server immediately."""
        if not self.is_configured:
            return False, "REST API admin password is not configured."
        url = f"{self.base_url}/v1/api/stop"
        try:
            timeout = aiohttp.ClientTimeout(total=5)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, auth=self._get_auth()) as resp:
                    if resp.status == 200:
                        return True, "Server stopped."
                    body = await resp.text()
                    return False, f"Server returned HTTP {resp.status}: {body}"
        except Exception as exc:
            return False, f"Failed to connect to Palworld REST API: {exc}"

