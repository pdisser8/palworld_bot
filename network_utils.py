"""Network utilities for Palworld server address resolution and public IP detection."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

import aiohttp

logger = logging.getLogger("palworld_bot.network")

# Cache public IP for 30 minutes
_CACHED_IP: Optional[str] = None
_CACHE_TIMESTAMP: float = 0.0
_CACHE_TTL_SECONDS: float = 1800.0

IP_SERVICES = [
    "https://api.ipify.org",
    "https://icanhazip.com",
    "https://ifconfig.me/ip",
    "https://checkip.amazonaws.com",
]


async def fetch_public_ip() -> Optional[str]:
    """Fetch the host machine's public IPv4 address using external IP services."""
    global _CACHED_IP, _CACHE_TIMESTAMP

    now = time.time()
    if _CACHED_IP and (now - _CACHE_TIMESTAMP) < _CACHE_TTL_SECONDS:
        return _CACHED_IP

    timeout = aiohttp.ClientTimeout(total=5)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        for service_url in IP_SERVICES:
            try:
                async with session.get(service_url) as resp:
                    if resp.status == 200:
                        ip_text = (await resp.text()).strip()
                        # Basic validation for an IPv4 address
                        parts = ip_text.split(".")
                        if len(parts) == 4 and all(p.isdigit() and 0 <= int(p) <= 255 for p in parts):
                            _CACHED_IP = ip_text
                            _CACHE_TIMESTAMP = now
                            return _CACHED_IP
            except Exception as exc:
                logger.debug(f"Failed to fetch public IP from {service_url}: {exc}")
                continue

    return _CACHED_IP


async def get_display_address(configured_address: Optional[str] = None) -> str:
    """
    Return the configured domain/IP if provided, otherwise auto-detect public IP.
    Falls back to '127.0.0.1' if detection fails.
    """
    if configured_address and configured_address.strip():
        return configured_address.strip()

    detected_ip = await fetch_public_ip()
    if detected_ip:
        return detected_ip

    return "127.0.0.1"


async def get_connect_address(configured_address: Optional[str] = None, port: int | str = 8211) -> str:
    """Format address and port into a connection string, e.g. 1.2.3.4:8211."""
    addr = await get_display_address(configured_address)
    return f"{addr}:{port}"

