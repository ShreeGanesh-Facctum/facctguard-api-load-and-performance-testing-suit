"""
Load Test Engine - Core Test Runner
=====================================
Fires requests against the FacctGuard API with multiple test scenarios:
- Baseline (single burst)
- Ramp-up (gradual increase)
- Spike (sudden burst)
- Sustained (constant rate over duration)
- Stress (push beyond limits)
- Breakpoint (auto-find breaking point)
- Recovery (spike then recover)
- Payload size variation
"""

import aiohttp
import asyncio
import time
import json
import os
from dataclasses import dataclass, field
from typing import Optional
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn
from rich.live import Live
from rich.table import Table

from .validator import ResponseValidator

console = Console()

# Directory to store payloads of failed requests
FAILED_PAYLOADS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "temp")


@dataclass
class RequestResult:
    """Result of a single HTTP request."""
    index: int
    status_code: int
    response_time_ms: float
    response_body: str
    error: Optional[str] = None
    timestamp: float = 0.0
    connection_reused: bool = False
    dns_time_ms: float = 0.0
    txn_id_sent: str = ""
    payload_sent: Optional[dict] = None


@dataclass
class ScenarioResult:
    """Aggregated results for a test scenario."""
    scenario_name: str
    total_requests: int = 0
    successful: int = 0
    failed: int = 0
    errors: dict = field(default_factory=dict)
    response_times: list = field(default_factory=list)
    status_codes: dict = field(default_factory=dict)
    start_time: float = 0.0
    end_time: float = 0.0
    requests: list = field(default_factory=list)
    rate_limited_count: int = 0
    timeout_count: int = 0
    connection_errors: int = 0
    validation_summary: dict = field(default_factory=dict)

    @property
    def duration_seconds(self) -> float:
        return self.end_time - self.start_time if self.end_time else 0

    @property
    def throughput_rps(self) -> float:
        d = self.duration_seconds
        return self.total_requests / d if d > 0 else 0

    @property
    def error_rate(self) -> float:
        return (self.failed / self.total_requests * 100) if self.total_requests > 0 else 0

    def percentile(self, p: float) -> float:
        if not self.response_times:
            return 0
        sorted_times = sorted(self.response_times)
        idx = int(len(sorted_times) * p / 100)
        idx = min(idx, len(sorted_times) - 1)
        return sorted_times[idx]


class LoadTestEngine:
    """Core load testing engine with multiple test scenarios."""

    def __init__(
        self,
        target_url: str,
        headers: dict,
        token: str,
        timeout_seconds: int = 30,
        tenant_id: str = "Facctum",
    ):
        self.target_url = target_url
        self.base_headers = {
            **headers,
            "Authorization": f"Bearer {token}",
        }
        self.timeout = aiohttp.ClientTimeout(total=timeout_seconds)
        self.tenant_id = tenant_id
        self.all_results: list[ScenarioResult] = []

    async def _fire_request(
        self,
        session: aiohttp.ClientSession,
        payload: dict,
        index: int,
        semaphore: asyncio.Semaphore,
    ) -> RequestResult:
        """Fire a single HTTP request."""
        async with semaphore:
            start = time.perf_counter()
            txn_id = ""

            # Build the API payload: send transactionPayment wrapper but strip _expectedOutcome
            api_payload = {"transactionPayment": payload["transactionPayment"]} if "transactionPayment" in payload else payload

            try:
                txn_ident = api_payload.get("transactionPayment", {}).get(
                    "InterbankPaymentTransaction", {}
                ).get("TransactionIdentification", {})
                txn_id = txn_ident.get("TransactionID", "")
            except Exception:
                pass

            try:
                async with session.post(
                    self.target_url,
                    json=api_payload,
                    headers=self.base_headers,
                    timeout=self.timeout,
                ) as resp:
                    elapsed = (time.perf_counter() - start) * 1000
                    body = await resp.text()
                    return RequestResult(
                        index=index,
                        status_code=resp.status,
                        response_time_ms=elapsed,
                        response_body=body,
                        timestamp=time.time(),
                        txn_id_sent=txn_id,
                        payload_sent=api_payload,
                    )
            except asyncio.TimeoutError:
                elapsed = (time.perf_counter() - start) * 1000
                return RequestResult(
                    index=index,
                    status_code=0,
                    response_time_ms=elapsed,
                    response_body="",
                    error="TIMEOUT",
                    timestamp=time.time(),
                    txn_id_sent=txn_id,
                    payload_sent=api_payload,
                )
            except aiohttp.ClientConnectorError as e:
                elapsed = (time.perf_counter() - start) * 1000
                return RequestResult(
                    index=index,
                    status_code=0,
                    response_time_ms=elapsed,
                    response_body="",
                    error=f"CONNECTION_ERROR: {e}",
                    timestamp=time.time(),
                    txn_id_sent=txn_id,
                    payload_sent=api_payload,
                )
            except Exception as e:
                elapsed = (time.perf_counter() - start) * 1000
                return RequestResult(
                    index=index,
                    status_code=0,
                    response_time_ms=elapsed,
                    response_body="",
                    error=str(e),
                    timestamp=time.time(),
                    txn_id_sent=txn_id,
                    payload_sent=api_payload,
                )

    def _aggregate_results(
        self, scenario_name: str, results: list[RequestResult], validator: ResponseValidator
    ) -> ScenarioResult:
        """Aggregate individual request results into a scenario result."""
        scenario = ScenarioResult(scenario_name=scenario_name)
        scenario.total_requests = len(results)
        scenario.start_time = min(r.timestamp for r in results) if results else 0
        scenario.end_time = max(r.timestamp for r in results) if results else 0

        failed_payloads = []

        for r in results:
            scenario.response_times.append(r.response_time_ms)
            code_key = str(r.status_code) if r.status_code else "ERROR"
            scenario.status_codes[code_key] = scenario.status_codes.get(code_key, 0) + 1

            if r.error:
                scenario.failed += 1
                err_type = r.error.split(":")[0]
                scenario.errors[err_type] = scenario.errors.get(err_type, 0) + 1
                if "TIMEOUT" in r.error:
                    scenario.timeout_count += 1
                if "CONNECTION" in r.error:
                    scenario.connection_errors += 1
                # Track failed payload
                if r.payload_sent:
                    failed_payloads.append({
                        "index": r.index,
                        "txn_id": r.txn_id_sent,
                        "error": r.error,
                        "status_code": r.status_code,
                        "payload": r.payload_sent,
                    })
            elif r.status_code == 200:
                scenario.successful += 1
                # Validate response
                validator.validate_response(
                    request_index=r.index,
                    status_code=r.status_code,
                    response_body=r.response_body,
                    expected_txn_id=r.txn_id_sent,
                )
            elif r.status_code == 429:
                scenario.rate_limited_count += 1
                scenario.failed += 1
                # Track failed payload
                if r.payload_sent:
                    failed_payloads.append({
                        "index": r.index,
                        "txn_id": r.txn_id_sent,
                        "error": "RATE_LIMITED",
                        "status_code": r.status_code,
                        "payload": r.payload_sent,
                    })
            elif r.status_code == 400:
                scenario.successful += 1  # 400 is a valid server response
                validator.validate_response(
                    request_index=r.index,
                    status_code=r.status_code,
                    response_body=r.response_body,
                )
            else:
                scenario.failed += 1
                # Track failed payload (5xx or unexpected status)
                if r.payload_sent:
                    failed_payloads.append({
                        "index": r.index,
                        "txn_id": r.txn_id_sent,
                        "error": f"HTTP_{r.status_code}",
                        "status_code": r.status_code,
                        "response_body": r.response_body[:500],
                        "payload": r.payload_sent,
                    })

        # Save failed payloads to temp folder
        if failed_payloads:
            self._save_failed_payloads(scenario_name, failed_payloads)

        scenario.requests = results
        scenario.validation_summary = validator.get_summary()
        return scenario

    def _save_failed_payloads(self, scenario_name: str, failed_payloads: list):
        """Save payloads of failed requests to the temp folder for debugging."""
        os.makedirs(FAILED_PAYLOADS_DIR, exist_ok=True)

        # Create a timestamped file for this scenario's failures
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = scenario_name.replace(" ", "_").replace("(", "").replace(")", "").replace("=", "")
        filename = f"failed_{safe_name}_{timestamp}.json"
        filepath = os.path.join(FAILED_PAYLOADS_DIR, filename)

        with open(filepath, "w") as f:
            json.dump(failed_payloads, f, indent=2)

        console.print(
            f"  [yellow]Saved {len(failed_payloads)} failed payload(s) to: temp/{filename}[/yellow]"
        )

    async def run_baseline(
        self, payloads: list, concurrency: int
    ) -> ScenarioResult:
        """Baseline test: fire all requests at once with given concurrency."""
        console.print(f"\n[bold cyan]>>> BASELINE TEST[/bold cyan] ({len(payloads)} requests, {concurrency} concurrent)")
        semaphore = asyncio.Semaphore(concurrency)
        validator = ResponseValidator(self.tenant_id)

        connector = aiohttp.TCPConnector(limit=concurrency, limit_per_host=concurrency)
        async with aiohttp.ClientSession(connector=connector) as session:
            tasks = [
                self._fire_request(session, p, i, semaphore)
                for i, p in enumerate(payloads)
            ]

            results = []
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TextColumn("{task.completed}/{task.total}"),
                TimeElapsedColumn(),
            ) as progress:
                task = progress.add_task("Baseline", total=len(tasks))
                for coro in asyncio.as_completed(tasks):
                    result = await coro
                    results.append(result)
                    progress.update(task, advance=1)

        scenario = self._aggregate_results("Baseline", results, validator)
        self.all_results.append(scenario)
        self._print_scenario_summary(scenario)
        return scenario

    async def run_ramp_up(
        self, payloads: list, start_concurrency: int, end_concurrency: int, steps: int = 5
    ) -> list[ScenarioResult]:
        """Ramp-up test: gradually increase concurrency."""
        console.print(f"\n[bold cyan]>>> RAMP-UP TEST[/bold cyan] ({start_concurrency} -> {end_concurrency} concurrent, {steps} steps)")
        step_size = max(1, (end_concurrency - start_concurrency) // steps)
        per_step = max(1, len(payloads) // steps)
        results_list = []

        for step in range(steps):
            concurrency = min(start_concurrency + step * step_size, end_concurrency)
            start_idx = step * per_step
            end_idx = min(start_idx + per_step, len(payloads))
            step_payloads = payloads[start_idx:end_idx]

            if not step_payloads:
                break

            console.print(f"  [dim]Step {step + 1}/{steps}: {concurrency} concurrent, {len(step_payloads)} requests[/dim]")
            semaphore = asyncio.Semaphore(concurrency)
            validator = ResponseValidator(self.tenant_id)

            connector = aiohttp.TCPConnector(limit=concurrency, limit_per_host=concurrency)
            async with aiohttp.ClientSession(connector=connector) as session:
                tasks = [
                    self._fire_request(session, p, start_idx + i, semaphore)
                    for i, p in enumerate(step_payloads)
                ]
                step_results = await asyncio.gather(*tasks)

            scenario = self._aggregate_results(
                f"Ramp-Up Step {step + 1} (c={concurrency})",
                list(step_results),
                validator,
            )
            self.all_results.append(scenario)
            results_list.append(scenario)
            self._print_scenario_summary(scenario)

            # Brief pause between steps
            await asyncio.sleep(1)

        return results_list

    async def run_spike(
        self, payloads: list, spike_concurrency: int
    ) -> ScenarioResult:
        """Spike test: sudden burst of all requests at maximum concurrency."""
        console.print(f"\n[bold cyan]>>> SPIKE TEST[/bold cyan] ({len(payloads)} requests, {spike_concurrency} concurrent - ALL AT ONCE)")
        semaphore = asyncio.Semaphore(spike_concurrency)
        validator = ResponseValidator(self.tenant_id)

        connector = aiohttp.TCPConnector(limit=spike_concurrency, limit_per_host=spike_concurrency)
        async with aiohttp.ClientSession(connector=connector) as session:
            tasks = [
                self._fire_request(session, p, i, semaphore)
                for i, p in enumerate(payloads)
            ]
            results = []
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TextColumn("{task.completed}/{task.total}"),
                TimeElapsedColumn(),
            ) as progress:
                task = progress.add_task("Spike", total=len(tasks))
                for coro in asyncio.as_completed(tasks):
                    result = await coro
                    results.append(result)
                    progress.update(task, advance=1)

        scenario = self._aggregate_results("Spike", results, validator)
        self.all_results.append(scenario)
        self._print_scenario_summary(scenario)
        return scenario

    async def run_sustained(
        self, payloads: list, concurrency: int, duration_seconds: int
    ) -> ScenarioResult:
        """Sustained load test: constant rate over a duration."""
        console.print(f"\n[bold cyan]>>> SUSTAINED LOAD TEST[/bold cyan] ({concurrency} concurrent, {duration_seconds}s duration)")
        semaphore = asyncio.Semaphore(concurrency)
        validator = ResponseValidator(self.tenant_id)
        all_request_results = []

        interval = duration_seconds / max(len(payloads), 1)
        connector = aiohttp.TCPConnector(limit=concurrency, limit_per_host=concurrency)

        async with aiohttp.ClientSession(connector=connector) as session:
            start_time = time.time()
            tasks = []

            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TextColumn("{task.completed}/{task.total}"),
                TimeElapsedColumn(),
            ) as progress:
                task = progress.add_task("Sustained", total=len(payloads))

                for i, payload in enumerate(payloads):
                    elapsed = time.time() - start_time
                    if elapsed >= duration_seconds:
                        break

                    t = asyncio.create_task(
                        self._fire_request(session, payload, i, semaphore)
                    )
                    tasks.append(t)

                    # Pace the requests
                    if interval > 0.01:
                        await asyncio.sleep(interval)

                # Wait for remaining tasks
                for t in asyncio.as_completed(tasks):
                    result = await t
                    all_request_results.append(result)
                    progress.update(task, advance=1)

        scenario = self._aggregate_results("Sustained", all_request_results, validator)
        self.all_results.append(scenario)
        self._print_scenario_summary(scenario)
        return scenario

    async def run_stress(
        self, payloads: list, max_concurrency: int
    ) -> ScenarioResult:
        """Stress test: push beyond expected limits."""
        console.print(f"\n[bold cyan]>>> STRESS TEST[/bold cyan] ({len(payloads)} requests, {max_concurrency} concurrent)")
        semaphore = asyncio.Semaphore(max_concurrency)
        validator = ResponseValidator(self.tenant_id)

        connector = aiohttp.TCPConnector(
            limit=max_concurrency,
            limit_per_host=max_concurrency,
            enable_cleanup_closed=True,
        )
        async with aiohttp.ClientSession(connector=connector) as session:
            tasks = [
                self._fire_request(session, p, i, semaphore)
                for i, p in enumerate(payloads)
            ]
            results = []
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TextColumn("{task.completed}/{task.total}"),
                TimeElapsedColumn(),
            ) as progress:
                task = progress.add_task("Stress", total=len(tasks))
                for coro in asyncio.as_completed(tasks):
                    result = await coro
                    results.append(result)
                    progress.update(task, advance=1)

        scenario = self._aggregate_results("Stress", results, validator)
        self.all_results.append(scenario)
        self._print_scenario_summary(scenario)
        return scenario

    async def run_breakpoint(
        self,
        payload_generator,
        start_concurrency: int = 5,
        max_concurrency: int = 200,
        step: int = 5,
        requests_per_step: int = 20,
        error_threshold_percent: float = 10.0,
    ) -> list[ScenarioResult]:
        """Breakpoint test: auto-increment concurrency until error threshold is exceeded."""
        console.print(f"\n[bold cyan]>>> BREAKPOINT TEST[/bold cyan] (finding breaking point, {start_concurrency} -> {max_concurrency})")
        results_list = []
        breaking_point = None

        for concurrency in range(start_concurrency, max_concurrency + 1, step):
            payloads = payload_generator(requests_per_step)
            console.print(f"  [dim]Testing concurrency: {concurrency}...[/dim]")

            semaphore = asyncio.Semaphore(concurrency)
            validator = ResponseValidator(self.tenant_id)

            connector = aiohttp.TCPConnector(limit=concurrency, limit_per_host=concurrency)
            async with aiohttp.ClientSession(connector=connector) as session:
                tasks = [
                    self._fire_request(session, p, i, semaphore)
                    for i, p in enumerate(payloads)
                ]
                step_results = await asyncio.gather(*tasks)

            scenario = self._aggregate_results(
                f"Breakpoint (c={concurrency})",
                list(step_results),
                validator,
            )
            self.all_results.append(scenario)
            results_list.append(scenario)

            error_rate = scenario.error_rate
            avg_time = sum(scenario.response_times) / len(scenario.response_times) if scenario.response_times else 0

            console.print(
                f"    c={concurrency}: "
                f"err={error_rate:.1f}% | "
                f"avg={avg_time:.0f}ms | "
                f"p95={scenario.percentile(95):.0f}ms | "
                f"rps={scenario.throughput_rps:.1f}"
            )

            if error_rate >= error_threshold_percent:
                breaking_point = concurrency
                console.print(
                    f"\n  [red bold]BREAKING POINT FOUND at concurrency={concurrency} "
                    f"(error rate: {error_rate:.1f}% >= {error_threshold_percent}%)[/red bold]"
                )
                break

            await asyncio.sleep(2)  # Cool-down between steps

        if breaking_point is None:
            console.print(
                f"\n  [green]Server handled all concurrency levels up to {max_concurrency} "
                f"within error threshold[/green]"
            )

        return results_list

    async def run_recovery(
        self, payloads: list, spike_concurrency: int, normal_concurrency: int
    ) -> list[ScenarioResult]:
        """Recovery test: spike hard, drop to zero, then normal load."""
        console.print(f"\n[bold cyan]>>> RECOVERY TEST[/bold cyan]")
        results_list = []

        # Phase 1: Spike
        third = max(1, len(payloads) // 3)
        console.print("  [dim]Phase 1: Spike...[/dim]")
        spike_result = await self.run_spike(payloads[:third], spike_concurrency)
        results_list.append(spike_result)

        # Phase 2: Cool-down
        console.print("  [dim]Phase 2: Cool-down (5s)...[/dim]")
        await asyncio.sleep(5)

        # Phase 3: Normal load
        console.print("  [dim]Phase 3: Normal load...[/dim]")
        normal_result = await self.run_baseline(payloads[third: third * 2], normal_concurrency)
        results_list.append(normal_result)

        # Compare
        if spike_result.response_times and normal_result.response_times:
            spike_avg = sum(spike_result.response_times) / len(spike_result.response_times)
            normal_avg = sum(normal_result.response_times) / len(normal_result.response_times)
            recovery_ratio = normal_avg / spike_avg if spike_avg > 0 else 0
            console.print(
                f"\n  Recovery analysis: spike_avg={spike_avg:.0f}ms, "
                f"post_recovery_avg={normal_avg:.0f}ms, "
                f"ratio={recovery_ratio:.2f}"
            )
            if recovery_ratio < 1.2:
                console.print("  [green]Server recovered well after spike[/green]")
            else:
                console.print("  [yellow]Server shows degradation after spike[/yellow]")

        return results_list

    async def run_concurrent_race_condition(
        self, identical_payload: dict, count: int = 20
    ) -> ScenarioResult:
        """Race condition test: fire identical requests simultaneously."""
        console.print(f"\n[bold cyan]>>> RACE CONDITION TEST[/bold cyan] ({count} identical requests)")
        semaphore = asyncio.Semaphore(count)  # All at once
        validator = ResponseValidator(self.tenant_id)

        connector = aiohttp.TCPConnector(limit=count, limit_per_host=count)
        async with aiohttp.ClientSession(connector=connector) as session:
            tasks = [
                self._fire_request(session, identical_payload, i, semaphore)
                for i in range(count)
            ]
            results = await asyncio.gather(*tasks)

        scenario = self._aggregate_results("Race Condition", list(results), validator)
        self.all_results.append(scenario)

        # Check for duplicate handling
        response_bodies = []
        for r in results:
            try:
                body = json.loads(r.response_body) if r.response_body else {}
                response_bodies.append(body)
            except Exception:
                pass

        # Check if all responses are consistent
        txn_ids = set()
        alert_ids = set()
        for body in response_bodies:
            if isinstance(body, dict):
                txn_ids.add(body.get("transaction_id", ""))
                for alert in body.get("alert_details", []):
                    if isinstance(alert, dict):
                        alert_ids.add(alert.get("alert_id", ""))

        console.print(f"  Unique transaction_ids in responses: {len(txn_ids)}")
        console.print(f"  Unique alert_ids generated: {len(alert_ids)}")
        if len(alert_ids) > 1:
            console.print("  [yellow]Multiple unique alert IDs for same payload - check for race conditions[/yellow]")

        self._print_scenario_summary(scenario)
        return scenario

    def _print_scenario_summary(self, scenario: ScenarioResult):
        """Print a quick summary table for a scenario."""
        table = Table(title=f"[bold]{scenario.scenario_name}[/bold]", show_lines=False)
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="white")

        table.add_row("Total Requests", str(scenario.total_requests))
        table.add_row("Successful", f"[green]{scenario.successful}[/green]")
        table.add_row("Failed", f"[red]{scenario.failed}[/red]" if scenario.failed else "0")
        table.add_row("Error Rate", f"{scenario.error_rate:.1f}%")
        table.add_row("Throughput", f"{scenario.throughput_rps:.2f} req/s")
        table.add_row("Duration", f"{scenario.duration_seconds:.2f}s")

        if scenario.response_times:
            table.add_row("Min", f"{min(scenario.response_times):.0f} ms")
            table.add_row("Avg", f"{sum(scenario.response_times) / len(scenario.response_times):.0f} ms")
            table.add_row("Max", f"{max(scenario.response_times):.0f} ms")
            table.add_row("P50", f"{scenario.percentile(50):.0f} ms")
            table.add_row("P95", f"{scenario.percentile(95):.0f} ms")
            table.add_row("P99", f"{scenario.percentile(99):.0f} ms")

        if scenario.rate_limited_count:
            table.add_row("Rate Limited (429)", f"[yellow]{scenario.rate_limited_count}[/yellow]")
        if scenario.timeout_count:
            table.add_row("Timeouts", f"[red]{scenario.timeout_count}[/red]")
        if scenario.connection_errors:
            table.add_row("Connection Errors", f"[red]{scenario.connection_errors}[/red]")

        table.add_row("Status Codes", str(scenario.status_codes))

        console.print(table)
