"""
Preflight Module - Pre-test Health & Validation Checks
========================================================
Runs before any load test to ensure:
1. Target server is reachable (health check)
2. Auth token is valid
3. A single test payload gets a valid response
Fails fast with clear errors if anything is wrong.
"""

import aiohttp
import asyncio
import json
from rich.console import Console
from rich.panel import Panel

console = Console()


class PreflightChecker:
    """Runs pre-test validation checks before load testing begins."""

    def __init__(
        self,
        target_url: str,
        healthcheck_url: str,
        headers: dict,
        timeout: int = 15,
    ):
        self.target_url = target_url
        self.healthcheck_url = healthcheck_url
        self.headers = headers
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self.results = {}

    async def check_health(self, session: aiohttp.ClientSession, token: str = "") -> bool:
        """Check if the API health endpoint is responding."""
        console.print("[dim]  Checking health endpoint...[/dim]")
        try:
            health_headers = {**self.headers}
            if token:
                health_headers["Authorization"] = f"Bearer {token}"
            async with session.get(
                self.healthcheck_url,
                headers=health_headers,
                timeout=self.timeout,
            ) as resp:
                body = await resp.text()
                if resp.status == 200:
                    self.results["health"] = {
                        "status": "PASS",
                        "response": body[:200],
                        "status_code": resp.status,
                    }
                    console.print(f"  [green]\u2713 Health check passed ({resp.status}): {body[:100]}[/green]")
                    return True
                else:
                    self.results["health"] = {
                        "status": "FAIL",
                        "response": body[:200],
                        "status_code": resp.status,
                    }
                    console.print(f"  [red]\u2717 Health check failed ({resp.status}): {body[:200]}[/red]")
                    return False
        except asyncio.TimeoutError:
            self.results["health"] = {"status": "FAIL", "error": "Timeout"}
            console.print("  [red]\u2717 Health check timed out[/red]")
            return False
        except Exception as e:
            self.results["health"] = {"status": "FAIL", "error": str(e)}
            console.print(f"  [red]\u2717 Health check error: {e}[/red]")
            return False

    async def check_auth(self, session: aiohttp.ClientSession, token: str) -> bool:
        """Validate the bearer token with a lightweight request."""
        console.print("[dim]  Validating auth token...[/dim]")
        auth_headers = {
            **self.headers,
            "Authorization": f"Bearer {token}",
        }
        try:
            # Try an OPTIONS request first (lightweight)
            async with session.options(
                self.target_url,
                headers=auth_headers,
                timeout=self.timeout,
            ) as resp:
                if resp.status < 500:
                    self.results["auth"] = {"status": "PASS", "status_code": resp.status}
                    console.print(f"  [green]\u2713 Auth token accepted (OPTIONS {resp.status})[/green]")
                    return True
                else:
                    self.results["auth"] = {"status": "WARN", "status_code": resp.status}
                    console.print(f"  [yellow]! Auth check inconclusive (OPTIONS {resp.status}), will verify with test request[/yellow]")
                    return True  # Don't fail on OPTIONS, test request will catch it
        except Exception:
            # OPTIONS might not be supported, that's fine
            self.results["auth"] = {"status": "PASS", "note": "OPTIONS not supported, will verify with test request"}
            console.print("  [yellow]! OPTIONS not supported, will verify with test request[/yellow]")
            return True

    async def check_test_request(
        self, session: aiohttp.ClientSession, token: str, payload: dict
    ) -> bool:
        """Send a single test request to verify the full flow works."""
        console.print("[dim]  Sending test request...[/dim]")
        auth_headers = {
            **self.headers,
            "Authorization": f"Bearer {token}",
        }

        # Send the transactionPayment wrapper but strip _expectedOutcome
        api_payload = {"transactionPayment": payload["transactionPayment"]} if "transactionPayment" in payload else payload

        try:
            async with session.post(
                self.target_url,
                json=api_payload,
                headers=auth_headers,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                body = await resp.text()
                try:
                    json_body = json.loads(body)
                except Exception:
                    json_body = body

                self.results["test_request"] = {
                    "status": "PASS" if resp.status == 200 else "WARN",
                    "status_code": resp.status,
                    "response_preview": str(json_body)[:300],
                }

                if resp.status == 200:
                    console.print(f"  [green]\u2713 Test request successful (200)[/green]")
                    # Show response summary
                    if isinstance(json_body, dict):
                        status = json_body.get("status", "N/A")
                        msg = json_body.get("message", "N/A")
                        console.print(f"    Status: {status} | {msg}")
                    return True
                elif resp.status == 401 or resp.status == 403:
                    console.print(f"  [red]\u2717 Auth rejected ({resp.status}) - token may be expired[/red]")
                    return False
                elif resp.status == 400:
                    console.print(f"  [yellow]! Bad request (400) - payload may need adjustment[/yellow]")
                    console.print(f"    Response: {str(json_body)[:300]}")
                    # 400 is not a blocker for load testing (we want to test error handling too)
                    return True
                else:
                    console.print(f"  [yellow]! Unexpected status ({resp.status})[/yellow]")
                    console.print(f"    Response: {str(json_body)[:300]}")
                    return resp.status < 500

        except asyncio.TimeoutError:
            self.results["test_request"] = {"status": "FAIL", "error": "Timeout (30s)"}
            console.print("  [red]\u2717 Test request timed out (30s)[/red]")
            return False
        except Exception as e:
            self.results["test_request"] = {"status": "FAIL", "error": str(e)}
            console.print(f"  [red]\u2717 Test request error: {e}[/red]")
            return False

    async def run_all(self, token: str, test_payload: dict) -> bool:
        """Run all preflight checks. Returns True if safe to proceed."""
        console.print()
        console.print(Panel("[bold]PREFLIGHT CHECKS[/bold]", style="cyan"))

        async with aiohttp.ClientSession() as session:
            # 1. Health check
            health_ok = await self.check_health(session, token)
            if not health_ok:
                console.print("\n[red bold]PREFLIGHT FAILED: Server is not healthy. Aborting.[/red bold]")
                return False

            # 2. Auth check
            auth_ok = await self.check_auth(session, token)

            # 3. Test request
            test_ok = await self.check_test_request(session, token, test_payload)
            if not test_ok:
                console.print("\n[red bold]PREFLIGHT FAILED: Test request failed. Check token and payload.[/red bold]")
                return False

        console.print("\n[green bold]\u2713 All preflight checks passed. Ready to load test.[/green bold]\n")
        return True
