"""
Auth Module - Token Generation for FacctGuard API
==================================================
Generates bearer tokens via Auth0 client credentials flow.
Supports multiple users/clients for concurrent testing.
Generates a fresh token before every batch of requests.
"""

import aiohttp
import asyncio
import time
from typing import Optional
from rich.console import Console

console = Console()


class TokenManager:
    """Manages bearer token generation and caching with auto-refresh."""

    def __init__(
        self,
        auth_url: str,
        client_id: str,
        client_secret: str,
        audience: str,
        tenant_id: str = "facctum",
    ):
        self.auth_url = auth_url
        self.client_id = client_id
        self.client_secret = client_secret
        self.audience = audience
        self.tenant_id = tenant_id
        self._token: Optional[str] = None
        self._token_expiry: float = 0
        self._manual_token: Optional[str] = None

    def set_manual_token(self, token: str):
        """Set a manually provided bearer token (skips Auth0 flow)."""
        self._manual_token = token
        console.print("[yellow]Using manually provided bearer token[/yellow]")

    async def get_token(self, session: Optional[aiohttp.ClientSession] = None) -> str:
        """
        Get a valid bearer token. Uses cached token if still valid,
        otherwise fetches a new one from Auth0.
        """
        # If manual token is set, always return it
        if self._manual_token:
            return self._manual_token

        # Check if cached token is still valid (with 60s buffer)
        if self._token and time.time() < (self._token_expiry - 60):
            return self._token

        # Fetch new token
        return await self._fetch_token(session)

    async def _fetch_token(
        self, session: Optional[aiohttp.ClientSession] = None
    ) -> str:
        """Fetch a new token from Auth0 using client credentials grant."""
        payload = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "audience": self.audience,
            "grant_type": "client_credentials",
        }

        close_session = False
        if session is None:
            session = aiohttp.ClientSession()
            close_session = True

        try:
            async with session.post(
                self.auth_url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    self._token = data["access_token"]
                    # Auth0 returns expires_in in seconds
                    expires_in = data.get("expires_in", 86400)
                    self._token_expiry = time.time() + expires_in
                    console.print(
                        f"[green]✓ Token acquired (expires in {expires_in}s)[/green]"
                    )
                    return self._token
                else:
                    body = await resp.text()
                    raise Exception(
                        f"Auth failed with status {resp.status}: {body[:500]}"
                    )
        finally:
            if close_session:
                await session.close()

    async def validate_token(self, target_url: str, headers: dict) -> bool:
        """Validate the token works by making a lightweight test request."""
        token = await self.get_token()
        test_headers = {
            **headers,
            "Authorization": f"Bearer {token}",
        }

        async with aiohttp.ClientSession() as session:
            try:
                async with session.options(
                    target_url,
                    headers=test_headers,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    # OPTIONS or any non-error response means token is accepted
                    return resp.status < 500
            except Exception:
                # If OPTIONS fails, try a HEAD or just return True
                # (actual validation happens in preflight)
                return True


class MultiUserTokenManager:
    """Manages tokens for multiple simulated users/clients."""

    def __init__(self, base_config: dict):
        self.managers: list[TokenManager] = []
        self.base_config = base_config

    def add_user(
        self,
        client_id: str,
        client_secret: str,
        label: str = "",
    ):
        """Add a user/client for token generation."""
        mgr = TokenManager(
            auth_url=self.base_config["auth_url"],
            client_id=client_id,
            client_secret=client_secret,
            audience=self.base_config["audience"],
            tenant_id=self.base_config.get("tenant_id", "facctum"),
        )
        self.managers.append(mgr)
        console.print(f"[dim]Added user: {label or client_id[:12]}...[/dim]")

    def add_manual_token(self, token: str, label: str = "manual"):
        """Add a manually provided token as a user."""
        mgr = TokenManager(
            auth_url="",
            client_id="",
            client_secret="",
            audience="",
        )
        mgr.set_manual_token(token)
        self.managers.append(mgr)

    async def get_token_for_user(
        self, user_index: int, session: Optional[aiohttp.ClientSession] = None
    ) -> str:
        """Get token for a specific user by index (round-robin)."""
        idx = user_index % len(self.managers)
        return await self.managers[idx].get_token(session)

    async def refresh_all(self):
        """Refresh tokens for all users."""
        tasks = [mgr.get_token() for mgr in self.managers]
        await asyncio.gather(*tasks, return_exceptions=True)
        console.print(
            f"[green]✓ Refreshed {len(self.managers)} token(s)[/green]"
        )
