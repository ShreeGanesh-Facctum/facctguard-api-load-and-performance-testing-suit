"""
Reporter Module - Enhanced Analysis & Report Generation
========================================================
Generates comprehensive reports in multiple formats:
- Rich console output with tables and charts
- JSON export for programmatic analysis
- CSV export for spreadsheet analysis
- HTML report with interactive Chart.js graphs
- Pass/fail verdict based on configurable thresholds
- Apdex score calculation
- SLA compliance tracking
- Executive summary
"""

import json
import csv
import os
import time
import statistics
from datetime import datetime
from typing import Optional
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text

from .load_test import ScenarioResult

console = Console()


class ReportGenerator:
    """Generates enhanced load test reports in multiple formats."""

    def __init__(
        self,
        results: list[ScenarioResult],
        pass_fail_criteria: Optional[dict] = None,
        output_dir: str = "results",
        sla_threshold_ms: float = 500.0,
        apdex_threshold_ms: float = 500.0,
        test_config: Optional[dict] = None,
    ):
        self.results = results
        self.criteria = pass_fail_criteria or {
            "max_p95_ms": 2000,
            "max_p99_ms": 5000,
            "max_error_rate_percent": 5,
            "min_throughput_rps": 1,
        }
        self.output_dir = output_dir
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.sla_threshold_ms = sla_threshold_ms
        self.apdex_threshold_ms = apdex_threshold_ms
        self.test_config = test_config or {}
        os.makedirs(output_dir, exist_ok=True)

    def calculate_apdex(self, response_times: list, threshold_ms: float = None) -> float:
        """
        Calculate Apdex score.
        Satisfied: <= T
        Tolerating: <= 4T
        Frustrated: > 4T
        Apdex = (Satisfied + Tolerating/2) / Total
        """
        if not response_times:
            return 0.0
        t = threshold_ms or self.apdex_threshold_ms
        satisfied = sum(1 for rt in response_times if rt <= t)
        tolerating = sum(1 for rt in response_times if t < rt <= 4 * t)
        total = len(response_times)
        return (satisfied + tolerating / 2) / total

    def calculate_sla_compliance(self, response_times: list, threshold_ms: float = None) -> float:
        """Calculate percentage of requests meeting SLA threshold."""
        if not response_times:
            return 0.0
        t = threshold_ms or self.sla_threshold_ms
        within_sla = sum(1 for rt in response_times if rt <= t)
        return (within_sla / len(response_times)) * 100

    def get_time_series_data(self, scenario: ScenarioResult, bucket_seconds: float = 1.0) -> dict:
        """
        Build time-series data for charts: response times and throughput over time.
        Groups requests into time buckets.
        """
        if not scenario.requests:
            return {"timestamps": [], "avg_response_times": [], "throughput": [], "error_rates": []}

        requests_sorted = sorted(scenario.requests, key=lambda r: r.timestamp)
        start_ts = requests_sorted[0].timestamp
        end_ts = requests_sorted[-1].timestamp
        duration = end_ts - start_ts

        if duration <= 0:
            return {
                "timestamps": [0],
                "avg_response_times": [sum(scenario.response_times) / len(scenario.response_times) if scenario.response_times else 0],
                "throughput": [len(scenario.requests)],
                "error_rates": [scenario.error_rate],
            }

        num_buckets = max(1, int(duration / bucket_seconds))
        bucket_size = duration / num_buckets

        timestamps = []
        avg_response_times = []
        throughput = []
        error_rates = []
        p95_times = []

        for i in range(num_buckets):
            bucket_start = start_ts + i * bucket_size
            bucket_end = bucket_start + bucket_size

            bucket_requests = [r for r in requests_sorted if bucket_start <= r.timestamp < bucket_end]

            timestamps.append(round(i * bucket_size, 1))

            if bucket_requests:
                rts = [r.response_time_ms for r in bucket_requests]
                avg_response_times.append(round(sum(rts) / len(rts), 1))
                throughput.append(len(bucket_requests) / bucket_size)
                errors = sum(1 for r in bucket_requests if r.error or (r.status_code != 200 and r.status_code != 400))
                error_rates.append(round(errors / len(bucket_requests) * 100, 1))
                sorted_rts = sorted(rts)
                p95_idx = min(int(len(sorted_rts) * 0.95), len(sorted_rts) - 1)
                p95_times.append(round(sorted_rts[p95_idx], 1))
            else:
                avg_response_times.append(0)
                throughput.append(0)
                error_rates.append(0)
                p95_times.append(0)

        return {
            "timestamps": timestamps,
            "avg_response_times": avg_response_times,
            "p95_response_times": p95_times,
            "throughput": throughput,
            "error_rates": error_rates,
        }

    def get_percentile_distribution(self, response_times: list) -> dict:
        """Build CDF data for percentile distribution chart."""
        if not response_times:
            return {"percentiles": [], "values": []}

        sorted_times = sorted(response_times)
        percentiles = list(range(1, 101))
        values = []
        for p in percentiles:
            idx = min(int(len(sorted_times) * p / 100), len(sorted_times) - 1)
            values.append(round(sorted_times[idx], 1))

        return {"percentiles": percentiles, "values": values}

    def evaluate_pass_fail(self) -> dict:
        """Evaluate all scenarios against pass/fail criteria."""
        verdicts = {}
        overall_pass = True

        for scenario in self.results:
            verdict = {"scenario": scenario.scenario_name, "checks": {}, "pass": True}

            p95 = scenario.percentile(95)
            p95_pass = p95 <= self.criteria["max_p95_ms"]
            verdict["checks"]["p95_ms"] = {
                "value": round(p95, 1),
                "threshold": self.criteria["max_p95_ms"],
                "pass": p95_pass,
            }
            if not p95_pass:
                verdict["pass"] = False

            p99 = scenario.percentile(99)
            p99_pass = p99 <= self.criteria["max_p99_ms"]
            verdict["checks"]["p99_ms"] = {
                "value": round(p99, 1),
                "threshold": self.criteria["max_p99_ms"],
                "pass": p99_pass,
            }
            if not p99_pass:
                verdict["pass"] = False

            err = scenario.error_rate
            err_pass = err <= self.criteria["max_error_rate_percent"]
            verdict["checks"]["error_rate_percent"] = {
                "value": round(err, 2),
                "threshold": self.criteria["max_error_rate_percent"],
                "pass": err_pass,
            }
            if not err_pass:
                verdict["pass"] = False

            rps = scenario.throughput_rps
            rps_pass = rps >= self.criteria["min_throughput_rps"]
            verdict["checks"]["throughput_rps"] = {
                "value": round(rps, 2),
                "threshold": self.criteria["min_throughput_rps"],
                "pass": rps_pass,
            }
            if not rps_pass:
                verdict["pass"] = False

            if not verdict["pass"]:
                overall_pass = False

            verdicts[scenario.scenario_name] = verdict

        return {"overall_pass": overall_pass, "scenarios": verdicts}

    def print_console_report(self):
        """Print a comprehensive report to the console."""
        console.print()
        console.print(Panel(
            "[bold white]LOAD TEST REPORT[/bold white]",
            style="bold blue",
            subtitle=f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        ))

        # Executive Summary
        self._print_executive_summary()

        # Summary table
        summary_table = Table(title="Scenario Summary", show_lines=True)
        summary_table.add_column("Scenario", style="cyan", min_width=20)
        summary_table.add_column("Requests", justify="right")
        summary_table.add_column("Success", justify="right", style="green")
        summary_table.add_column("Failed", justify="right", style="red")
        summary_table.add_column("Err%", justify="right")
        summary_table.add_column("RPS", justify="right")
        summary_table.add_column("Avg(ms)", justify="right")
        summary_table.add_column("P50(ms)", justify="right")
        summary_table.add_column("P95(ms)", justify="right")
        summary_table.add_column("P99(ms)", justify="right")
        summary_table.add_column("Max(ms)", justify="right")
        summary_table.add_column("Apdex", justify="right")
        summary_table.add_column("SLA%", justify="right")

        for s in self.results:
            avg = sum(s.response_times) / len(s.response_times) if s.response_times else 0
            err_style = "red" if s.error_rate > 5 else "yellow" if s.error_rate > 1 else "green"
            apdex = self.calculate_apdex(s.response_times)
            sla = self.calculate_sla_compliance(s.response_times)
            apdex_style = "green" if apdex >= 0.9 else "yellow" if apdex >= 0.7 else "red"
            sla_style = "green" if sla >= 95 else "yellow" if sla >= 80 else "red"

            summary_table.add_row(
                s.scenario_name,
                str(s.total_requests),
                str(s.successful),
                str(s.failed),
                f"[{err_style}]{s.error_rate:.1f}%[/{err_style}]",
                f"{s.throughput_rps:.2f}",
                f"{avg:.0f}",
                f"{s.percentile(50):.0f}",
                f"{s.percentile(95):.0f}",
                f"{s.percentile(99):.0f}",
                f"{max(s.response_times):.0f}" if s.response_times else "0",
                f"[{apdex_style}]{apdex:.2f}[/{apdex_style}]",
                f"[{sla_style}]{sla:.1f}%[/{sla_style}]",
            )

        console.print(summary_table)

        # Error breakdown
        all_errors = {}
        all_status_codes = {}
        for s in self.results:
            for err, count in s.errors.items():
                all_errors[err] = all_errors.get(err, 0) + count
            for code, count in s.status_codes.items():
                all_status_codes[code] = all_status_codes.get(code, 0) + count

        if all_errors:
            err_table = Table(title="Error Breakdown", show_lines=False)
            err_table.add_column("Error Type", style="red")
            err_table.add_column("Count", justify="right")
            for err, count in sorted(all_errors.items(), key=lambda x: x[1], reverse=True):
                err_table.add_row(err, str(count))
            console.print(err_table)

        if all_status_codes:
            code_table = Table(title="Status Code Distribution", show_lines=False)
            code_table.add_column("Status Code", style="cyan")
            code_table.add_column("Count", justify="right")
            code_table.add_column("Percentage", justify="right")
            total = sum(all_status_codes.values())
            for code, count in sorted(all_status_codes.items()):
                pct = count / total * 100
                style = "green" if code == "200" else "yellow" if code.startswith("4") else "red"
                code_table.add_row(f"[{style}]{code}[/{style}]", str(count), f"{pct:.1f}%")
            console.print(code_table)

        # Validation summary
        for s in self.results:
            if s.validation_summary and s.validation_summary.get("total_validated", 0) > 0:
                vs = s.validation_summary
                console.print(f"\n[bold]Validation: {s.scenario_name}[/bold]")
                console.print(f"  Validated: {vs['total_validated']} | Valid: {vs['valid_responses']} | Invalid: {vs['invalid_responses']}")
                if vs.get("data_corruption_detected", 0) > 0:
                    console.print(f"  [red bold]DATA CORRUPTION DETECTED: {vs['data_corruption_detected']} responses[/red bold]")
                    for detail in vs.get("corruption_details", [])[:5]:
                        console.print(f"    Request #{detail['request']}: {detail['detail']}")

        self._print_response_time_histogram()

        # Pass/Fail verdict
        verdict = self.evaluate_pass_fail()
        self._print_verdict(verdict)

    def _print_executive_summary(self):
        """Print a one-paragraph executive summary."""
        all_times = []
        total_requests = 0
        total_failed = 0
        total_duration = 0

        for s in self.results:
            all_times.extend(s.response_times)
            total_requests += s.total_requests
            total_failed += s.failed
            total_duration = max(total_duration, s.duration_seconds)

        if not all_times:
            return

        overall_apdex = self.calculate_apdex(all_times)
        overall_sla = self.calculate_sla_compliance(all_times)
        overall_error_rate = (total_failed / total_requests * 100) if total_requests > 0 else 0
        avg_rps = total_requests / total_duration if total_duration > 0 else 0

        verdict = self.evaluate_pass_fail()
        status = "[green]PASSED[/green]" if verdict["overall_pass"] else "[red]FAILED[/red]"

        summary = (
            f"Test executed {total_requests} requests across {len(self.results)} scenario(s) "
            f"over {total_duration:.0f}s. "
            f"Average throughput: {avg_rps:.1f} RPS. "
            f"Error rate: {overall_error_rate:.1f}%. "
            f"Apdex: {overall_apdex:.2f} (T={self.apdex_threshold_ms:.0f}ms). "
            f"SLA compliance (<{self.sla_threshold_ms:.0f}ms): {overall_sla:.1f}%. "
            f"Overall: {status}"
        )
        console.print(Panel(summary, title="[bold]Executive Summary[/bold]", style="blue"))

    def _print_response_time_histogram(self):
        """Print a text-based response time distribution."""
        all_times = []
        for s in self.results:
            all_times.extend(s.response_times)

        if not all_times:
            return

        console.print("\n[bold]Response Time Distribution[/bold]")
        buckets = [100, 200, 500, 1000, 2000, 5000, 10000, float("inf")]
        bucket_labels = ["<100ms", "100-200ms", "200-500ms", "500ms-1s", "1-2s", "2-5s", "5-10s", ">10s"]
        counts = [0] * len(buckets)

        for t in all_times:
            for i, b in enumerate(buckets):
                if t < b:
                    counts[i] += 1
                    break

        max_count = max(counts) if counts else 1
        for label, count in zip(bucket_labels, counts):
            bar_len = int(count / max_count * 40) if max_count > 0 else 0
            bar = "\u2588" * bar_len
            pct = count / len(all_times) * 100 if all_times else 0
            console.print(f"  {label:>10s} | {bar:<40s} {count:>5d} ({pct:.1f}%)")

    def _print_verdict(self, verdict: dict):
        """Print pass/fail verdict."""
        console.print()
        if verdict["overall_pass"]:
            console.print(Panel(
                "[bold green]OVERALL VERDICT: PASS[/bold green]",
                style="green",
            ))
        else:
            console.print(Panel(
                "[bold red]OVERALL VERDICT: FAIL[/bold red]",
                style="red",
            ))

        for name, v in verdict["scenarios"].items():
            status = "[green]PASS[/green]" if v["pass"] else "[red]FAIL[/red]"
            console.print(f"  {name}: {status}")
            for check_name, check in v["checks"].items():
                icon = "\u2713" if check["pass"] else "\u2717"
                style = "green" if check["pass"] else "red"
                console.print(
                    f"    [{style}]{icon}[/{style}] {check_name}: "
                    f"{check['value']} (threshold: {check['threshold']})"
                )

    def export_json(self) -> str:
        """Export results to JSON file."""
        filepath = os.path.join(self.output_dir, f"loadtest_{self.timestamp}.json")
        report = {
            "generated_at": datetime.now().isoformat(),
            "test_config": self.test_config,
            "verdict": self.evaluate_pass_fail(),
            "scenarios": [],
        }

        for s in self.results:
            avg = sum(s.response_times) / len(s.response_times) if s.response_times else 0
            std_dev = statistics.stdev(s.response_times) if len(s.response_times) > 1 else 0
            apdex = self.calculate_apdex(s.response_times)
            sla = self.calculate_sla_compliance(s.response_times)

            scenario_data = {
                "name": s.scenario_name,
                "total_requests": s.total_requests,
                "successful": s.successful,
                "failed": s.failed,
                "error_rate_percent": round(s.error_rate, 2),
                "throughput_rps": round(s.throughput_rps, 2),
                "duration_seconds": round(s.duration_seconds, 2),
                "apdex_score": round(apdex, 3),
                "sla_compliance_percent": round(sla, 2),
                "response_times": {
                    "min": round(min(s.response_times), 1) if s.response_times else 0,
                    "avg": round(avg, 1),
                    "max": round(max(s.response_times), 1) if s.response_times else 0,
                    "std_dev": round(std_dev, 1),
                    "p50": round(s.percentile(50), 1),
                    "p75": round(s.percentile(75), 1),
                    "p90": round(s.percentile(90), 1),
                    "p95": round(s.percentile(95), 1),
                    "p99": round(s.percentile(99), 1),
                },
                "status_codes": s.status_codes,
                "errors": s.errors,
                "rate_limited": s.rate_limited_count,
                "timeouts": s.timeout_count,
                "connection_errors": s.connection_errors,
                "validation": s.validation_summary,
                "requests": [],
            }

            for r in s.requests:
                response_parsed = None
                try:
                    if r.response_body:
                        response_parsed = json.loads(r.response_body)
                except (json.JSONDecodeError, TypeError):
                    response_parsed = r.response_body if r.response_body else None

                request_detail = {
                    "index": r.index,
                    "txn_id": r.txn_id_sent,
                    "status_code": r.status_code,
                    "response_time_ms": round(r.response_time_ms, 1),
                    "timestamp": r.timestamp,
                    "error": r.error,
                    "response": response_parsed,
                }
                scenario_data["requests"].append(request_detail)

            report["scenarios"].append(scenario_data)

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, default=str)

        console.print(f"\n[dim]JSON report saved: {filepath}[/dim]")
        return filepath

    def export_csv(self) -> str:
        """Export results to CSV file."""
        filepath = os.path.join(self.output_dir, f"loadtest_{self.timestamp}.csv")

        with open(filepath, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "Scenario", "Total", "Success", "Failed", "Error%",
                "RPS", "Duration(s)", "Min(ms)", "Avg(ms)", "StdDev(ms)", "Max(ms)",
                "P50(ms)", "P75(ms)", "P90(ms)", "P95(ms)", "P99(ms)",
                "429s", "Timeouts", "ConnErrors", "Apdex", "SLA%",
            ])
            for s in self.results:
                avg = sum(s.response_times) / len(s.response_times) if s.response_times else 0
                std_dev = statistics.stdev(s.response_times) if len(s.response_times) > 1 else 0
                apdex = self.calculate_apdex(s.response_times)
                sla = self.calculate_sla_compliance(s.response_times)
                writer.writerow([
                    s.scenario_name, s.total_requests, s.successful, s.failed,
                    f"{s.error_rate:.2f}", f"{s.throughput_rps:.2f}",
                    f"{s.duration_seconds:.2f}",
                    f"{min(s.response_times):.1f}" if s.response_times else 0,
                    f"{avg:.1f}", f"{std_dev:.1f}",
                    f"{max(s.response_times):.1f}" if s.response_times else 0,
                    f"{s.percentile(50):.1f}", f"{s.percentile(75):.1f}",
                    f"{s.percentile(90):.1f}", f"{s.percentile(95):.1f}",
                    f"{s.percentile(99):.1f}",
                    s.rate_limited_count, s.timeout_count, s.connection_errors,
                    f"{apdex:.3f}", f"{sla:.1f}",
                ])

        console.print(f"[dim]CSV report saved: {filepath}[/dim]")
        return filepath

    def export_html(self) -> str:
        """Export results to an enhanced HTML report with interactive Chart.js graphs."""
        filepath = os.path.join(self.output_dir, f"loadtest_{self.timestamp}.html")
        verdict = self.evaluate_pass_fail()
        overall_class = "pass" if verdict["overall_pass"] else "fail"

        # Gather all response times for aggregate charts
        all_times = []
        total_requests = 0
        total_failed = 0
        total_duration = 0
        for s in self.results:
            all_times.extend(s.response_times)
            total_requests += s.total_requests
            total_failed += s.failed
            total_duration = max(total_duration, s.duration_seconds)

        overall_apdex = self.calculate_apdex(all_times)
        overall_sla = self.calculate_sla_compliance(all_times)
        overall_error_rate = (total_failed / total_requests * 100) if total_requests > 0 else 0
        avg_rps = total_requests / total_duration if total_duration > 0 else 0
        avg_rt = sum(all_times) / len(all_times) if all_times else 0
        std_dev = statistics.stdev(all_times) if len(all_times) > 1 else 0

        # Build scenario summary rows
        rows_html = ""
        for s in self.results:
            avg = sum(s.response_times) / len(s.response_times) if s.response_times else 0
            err_class = "fail" if s.error_rate > 5 else "warn" if s.error_rate > 1 else "pass"
            apdex = self.calculate_apdex(s.response_times)
            sla = self.calculate_sla_compliance(s.response_times)
            apdex_class = "pass" if apdex >= 0.9 else "warn" if apdex >= 0.7 else "fail"
            sla_class = "pass" if sla >= 95 else "warn" if sla >= 80 else "fail"
            rows_html += f"""<tr>
                <td style="text-align:left">{s.scenario_name}</td><td>{s.total_requests}</td>
                <td class="pass">{s.successful}</td><td class="fail">{s.failed}</td>
                <td class="{err_class}">{s.error_rate:.1f}%</td>
                <td>{s.throughput_rps:.2f}</td><td>{avg:.0f}</td>
                <td>{s.percentile(50):.0f}</td><td>{s.percentile(95):.0f}</td>
                <td>{s.percentile(99):.0f}</td>
                <td>{max(s.response_times):.0f}</td>
                <td class="{apdex_class}">{apdex:.2f}</td>
                <td class="{sla_class}">{sla:.1f}%</td>
            </tr>"""

        # Build time-series data for each scenario
        time_series_datasets = []
        throughput_datasets = []
        error_datasets = []
        colors = ['#00d4ff', '#ff6384', '#36a2eb', '#ffce56', '#4bc0c0', '#9966ff', '#ff9f40', '#00ff88']

        for idx, s in enumerate(self.results):
            ts_data = self.get_time_series_data(s, bucket_seconds=max(1, s.duration_seconds / 60))
            color = colors[idx % len(colors)]
            time_series_datasets.append({
                "label": s.scenario_name,
                "data": ts_data["avg_response_times"],
                "timestamps": ts_data["timestamps"],
                "borderColor": color,
                "fill": False,
                "tension": 0.3,
            })
            throughput_datasets.append({
                "label": s.scenario_name,
                "data": ts_data["throughput"],
                "timestamps": ts_data["timestamps"],
                "borderColor": color,
                "fill": False,
                "tension": 0.3,
            })
            error_datasets.append({
                "label": s.scenario_name,
                "data": ts_data["error_rates"],
                "timestamps": ts_data["timestamps"],
                "borderColor": color,
                "backgroundColor": color + "33",
                "fill": True,
                "tension": 0.3,
            })

        # Percentile distribution (CDF)
        percentile_data = self.get_percentile_distribution(all_times)

        # Status code pie chart data
        all_status_codes = {}
        for s in self.results:
            for code, count in s.status_codes.items():
                all_status_codes[code] = all_status_codes.get(code, 0) + count

        # Response time histogram data
        hist_buckets = [0, 100, 200, 300, 500, 750, 1000, 1500, 2000, 3000, 5000]
        hist_counts = [0] * (len(hist_buckets))
        for t in all_times:
            placed = False
            for i in range(len(hist_buckets) - 1):
                if hist_buckets[i] <= t < hist_buckets[i + 1]:
                    hist_counts[i] += 1
                    placed = True
                    break
            if not placed:
                hist_counts[-1] += 1

        hist_labels = [f"{hist_buckets[i]}-{hist_buckets[i+1]}ms" for i in range(len(hist_buckets) - 1)]
        hist_labels.append(f">{hist_buckets[-1]}ms")

        # Error breakdown table
        all_errors = {}
        for s in self.results:
            for err, count in s.errors.items():
                all_errors[err] = all_errors.get(err, 0) + count

        error_rows_html = ""
        if all_errors:
            for err, count in sorted(all_errors.items(), key=lambda x: x[1], reverse=True):
                error_rows_html += f"<tr><td style='text-align:left'>{err}</td><td>{count}</td></tr>"

        # Recommendations
        recommendations = self._generate_recommendations(all_times, overall_error_rate, avg_rps)
        recommendations_html = "".join(f"<li>{r}</li>" for r in recommendations)

        # Per-request detail sections
        request_details_html = ""
        for s in self.results:
            request_details_html += f'<h2>Request Details: {s.scenario_name}</h2>\n'
            request_details_html += """<div class="table-scroll"><table class="request-table">
                <tr><th>#</th><th>Transaction ID</th><th>Status</th><th>Time (ms)</th><th>Error</th><th>API Response</th></tr>\n"""

            for r in s.requests:
                status_class = "pass" if r.status_code == 200 else "warn" if r.status_code == 400 else "fail"
                error_text = r.error or "-"

                response_text = ""
                try:
                    if r.response_body:
                        parsed = json.loads(r.response_body)
                        response_text = json.dumps(parsed, indent=2)
                    else:
                        response_text = "-"
                except (json.JSONDecodeError, TypeError):
                    response_text = r.response_body[:500] if r.response_body else "-"

                response_text = (
                    response_text
                    .replace("&", "&amp;")
                    .replace("<", "&lt;")
                    .replace(">", "&gt;")
                )

                request_details_html += f"""<tr>
                    <td>{r.index}</td>
                    <td>{r.txn_id_sent}</td>
                    <td class="{status_class}">{r.status_code}</td>
                    <td>{r.response_time_ms:.1f}</td>
                    <td>{error_text}</td>
                    <td><pre class="response-pre">{response_text}</pre></td>
                </tr>\n"""

            request_details_html += "</table></div>\n"

        # Build the full HTML
        html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>FacctGuard Load Test Report - {self.timestamp}</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
* {{ box-sizing: border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; margin: 0; padding: 2rem; background: #0d1117; color: #e6edf3; }}
h1 {{ color: #00d4ff; margin-bottom: 0.5rem; }} 
h2 {{ color: #7b68ee; border-bottom: 1px solid #21262d; padding-bottom: 0.5rem; margin-top: 2rem; }}
h3 {{ color: #58a6ff; }}
.subtitle {{ color: #8b949e; margin-bottom: 2rem; }}
.grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1rem; margin: 1.5rem 0; }}
.metric-card {{ background: #161b22; border: 1px solid #21262d; border-radius: 8px; padding: 1.2rem; text-align: center; }}
.metric-card .value {{ font-size: 2rem; font-weight: bold; color: #00d4ff; }}
.metric-card .label {{ color: #8b949e; font-size: 0.85rem; margin-top: 0.3rem; }}
.metric-card.pass .value {{ color: #00ff88; }}
.metric-card.fail .value {{ color: #ff4444; }}
.metric-card.warn .value {{ color: #ffaa00; }}
table {{ border-collapse: collapse; width: 100%; margin: 1rem 0; }}
th, td {{ border: 1px solid #21262d; padding: 8px 12px; text-align: right; font-size: 0.9rem; }}
th {{ background: #161b22; color: #00d4ff; position: sticky; top: 0; }}
tr:nth-child(even) {{ background: #161b22; }}
tr:hover {{ background: #1c2128; }}
.pass {{ color: #00ff88; font-weight: bold; }}
.fail {{ color: #ff4444; font-weight: bold; }}
.warn {{ color: #ffaa00; font-weight: bold; }}
.verdict {{ padding: 1.2rem 2rem; border-radius: 8px; font-size: 1.5rem; text-align: center; margin: 1.5rem 0; font-weight: bold; }}
.verdict.pass {{ background: #0a3d0a; border: 2px solid #00ff88; color: #00ff88; }}
.verdict.fail {{ background: #3d0a0a; border: 2px solid #ff4444; color: #ff4444; }}
.chart-container {{ background: #161b22; border: 1px solid #21262d; border-radius: 8px; padding: 1.5rem; margin: 1rem 0; }}
.chart-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(500px, 1fr)); gap: 1.5rem; margin: 1.5rem 0; }}
.executive-summary {{ background: #161b22; border: 1px solid #21262d; border-radius: 8px; padding: 1.5rem; margin: 1.5rem 0; line-height: 1.6; }}
.recommendations {{ background: #161b22; border-left: 4px solid #58a6ff; border-radius: 0 8px 8px 0; padding: 1.2rem 1.5rem; margin: 1.5rem 0; }}
.recommendations li {{ margin: 0.5rem 0; color: #c9d1d9; }}
.table-scroll {{ overflow-x: auto; }}
.request-table td {{ text-align: left; vertical-align: top; }}
.request-table th {{ text-align: left; }}
.response-pre {{ background: #0d1117; border: 1px solid #21262d; border-radius: 4px; padding: 8px; margin: 0; font-size: 11px; max-height: 200px; overflow: auto; white-space: pre-wrap; word-break: break-word; color: #c9d1d9; }}
.config-section {{ background: #161b22; border: 1px solid #21262d; border-radius: 8px; padding: 1.2rem; margin: 1rem 0; }}
.config-section code {{ color: #79c0ff; }}
canvas {{ max-height: 350px; }}
</style></head><body>

<h1>FacctGuard Load Test Report</h1>
<p class="subtitle">Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | Duration: {total_duration:.0f}s | Scenarios: {len(self.results)}</p>

<div class="verdict {overall_class}">OVERALL VERDICT: {"PASS \u2713" if verdict["overall_pass"] else "FAIL \u2717"}</div>

<!-- Executive Summary -->
<div class="executive-summary">
<h3>Executive Summary</h3>
<p>Executed <strong>{total_requests}</strong> requests across <strong>{len(self.results)}</strong> scenario(s) over <strong>{total_duration:.0f}s</strong>.
Average throughput: <strong>{avg_rps:.1f} RPS</strong>. Error rate: <strong>{overall_error_rate:.1f}%</strong>.
Apdex score: <strong>{overall_apdex:.2f}</strong> (T={self.apdex_threshold_ms:.0f}ms).
SLA compliance (&lt;{self.sla_threshold_ms:.0f}ms): <strong>{overall_sla:.1f}%</strong>.</p>
</div>

<!-- Key Metrics Cards -->
<div class="grid">
    <div class="metric-card"><div class="value">{total_requests}</div><div class="label">Total Requests</div></div>
    <div class="metric-card {'pass' if overall_error_rate < 5 else 'fail'}"><div class="value">{overall_error_rate:.1f}%</div><div class="label">Error Rate</div></div>
    <div class="metric-card"><div class="value">{avg_rps:.1f}</div><div class="label">Avg RPS</div></div>
    <div class="metric-card"><div class="value">{avg_rt:.0f}ms</div><div class="label">Avg Response Time</div></div>
    <div class="metric-card {'pass' if overall_apdex >= 0.9 else 'warn' if overall_apdex >= 0.7 else 'fail'}"><div class="value">{overall_apdex:.2f}</div><div class="label">Apdex Score</div></div>
    <div class="metric-card {'pass' if overall_sla >= 95 else 'warn' if overall_sla >= 80 else 'fail'}"><div class="value">{overall_sla:.1f}%</div><div class="label">SLA Compliance</div></div>
    <div class="metric-card"><div class="value">{std_dev:.0f}ms</div><div class="label">Std Deviation</div></div>
    <div class="metric-card"><div class="value">{total_duration:.0f}s</div><div class="label">Test Duration</div></div>
</div>

<!-- Charts -->
<h2>Performance Charts</h2>
<div class="chart-grid">
    <div class="chart-container">
        <h3>Response Time Over Time</h3>
        <canvas id="responseTimeChart"></canvas>
    </div>
    <div class="chart-container">
        <h3>Throughput Over Time (RPS)</h3>
        <canvas id="throughputChart"></canvas>
    </div>
    <div class="chart-container">
        <h3>Error Rate Over Time</h3>
        <canvas id="errorRateChart"></canvas>
    </div>
    <div class="chart-container">
        <h3>Response Time Percentile Distribution (CDF)</h3>
        <canvas id="percentileChart"></canvas>
    </div>
    <div class="chart-container">
        <h3>Response Time Histogram</h3>
        <canvas id="histogramChart"></canvas>
    </div>
    <div class="chart-container">
        <h3>Status Code Distribution</h3>
        <canvas id="statusCodeChart"></canvas>
    </div>
</div>

<!-- Scenario Summary Table -->
<h2>Scenario Summary</h2>
<div class="table-scroll">
<table><tr><th style="text-align:left">Scenario</th><th>Total</th><th>Success</th><th>Failed</th><th>Err%</th>
<th>RPS</th><th>Avg(ms)</th><th>P50</th><th>P95</th><th>P99</th><th>Max</th><th>Apdex</th><th>SLA%</th></tr>
{rows_html}</table>
</div>

<!-- Error Breakdown -->
{"<h2>Error Breakdown</h2><table><tr><th style='text-align:left'>Error Type</th><th>Count</th></tr>" + error_rows_html + "</table>" if error_rows_html else ""}

<!-- Recommendations -->
<div class="recommendations">
<h3>Recommendations</h3>
<ul>{recommendations_html}</ul>
</div>

<!-- Request Details -->
{request_details_html}

<script>
// Chart.js configuration
Chart.defaults.color = '#8b949e';
Chart.defaults.borderColor = '#21262d';

// Response Time Over Time
const rtCtx = document.getElementById('responseTimeChart').getContext('2d');
new Chart(rtCtx, {{
    type: 'line',
    data: {{
        labels: {json.dumps(time_series_datasets[0]["timestamps"] if time_series_datasets else [])},
        datasets: {json.dumps([{"label": d["label"], "data": d["data"], "borderColor": d["borderColor"], "fill": d["fill"], "tension": d["tension"]} for d in time_series_datasets])}
    }},
    options: {{
        responsive: true,
        plugins: {{
            annotation: {{
                annotations: {{
                    slaLine: {{ type: 'line', yMin: {self.sla_threshold_ms}, yMax: {self.sla_threshold_ms}, borderColor: '#ff4444', borderDash: [5,5], borderWidth: 2, label: {{ content: 'SLA: {self.sla_threshold_ms:.0f}ms', enabled: true }} }}
                }}
            }}
        }},
        scales: {{
            x: {{ title: {{ display: true, text: 'Time (seconds)' }} }},
            y: {{ title: {{ display: true, text: 'Response Time (ms)' }}, beginAtZero: true }}
        }}
    }}
}});

// Throughput Over Time
const tpCtx = document.getElementById('throughputChart').getContext('2d');
new Chart(tpCtx, {{
    type: 'line',
    data: {{
        labels: {json.dumps(throughput_datasets[0]["timestamps"] if throughput_datasets else [])},
        datasets: {json.dumps([{"label": d["label"], "data": [round(v, 2) for v in d["data"]], "borderColor": d["borderColor"], "fill": d["fill"], "tension": d["tension"]} for d in throughput_datasets])}
    }},
    options: {{
        responsive: true,
        scales: {{
            x: {{ title: {{ display: true, text: 'Time (seconds)' }} }},
            y: {{ title: {{ display: true, text: 'Requests/sec' }}, beginAtZero: true }}
        }}
    }}
}});

// Error Rate Over Time
const errCtx = document.getElementById('errorRateChart').getContext('2d');
new Chart(errCtx, {{
    type: 'line',
    data: {{
        labels: {json.dumps(error_datasets[0]["timestamps"] if error_datasets else [])},
        datasets: {json.dumps([{"label": d["label"], "data": d["data"], "borderColor": d["borderColor"], "backgroundColor": d["backgroundColor"], "fill": d["fill"], "tension": d["tension"]} for d in error_datasets])}
    }},
    options: {{
        responsive: true,
        scales: {{
            x: {{ title: {{ display: true, text: 'Time (seconds)' }} }},
            y: {{ title: {{ display: true, text: 'Error Rate (%)' }}, beginAtZero: true, max: 100 }}
        }}
    }}
}});

// Percentile Distribution (CDF)
const pctCtx = document.getElementById('percentileChart').getContext('2d');
new Chart(pctCtx, {{
    type: 'line',
    data: {{
        labels: {json.dumps(percentile_data["percentiles"])},
        datasets: [{{
            label: 'Response Time',
            data: {json.dumps(percentile_data["values"])},
            borderColor: '#00d4ff',
            backgroundColor: '#00d4ff22',
            fill: true,
            tension: 0.3,
        }}]
    }},
    options: {{
        responsive: true,
        scales: {{
            x: {{ title: {{ display: true, text: 'Percentile' }} }},
            y: {{ title: {{ display: true, text: 'Response Time (ms)' }}, beginAtZero: true }}
        }}
    }}
}});

// Response Time Histogram
const histCtx = document.getElementById('histogramChart').getContext('2d');
new Chart(histCtx, {{
    type: 'bar',
    data: {{
        labels: {json.dumps(hist_labels)},
        datasets: [{{
            label: 'Request Count',
            data: {json.dumps(hist_counts)},
            backgroundColor: '#36a2eb88',
            borderColor: '#36a2eb',
            borderWidth: 1,
        }}]
    }},
    options: {{
        responsive: true,
        scales: {{
            x: {{ title: {{ display: true, text: 'Response Time Bucket' }} }},
            y: {{ title: {{ display: true, text: 'Count' }}, beginAtZero: true }}
        }}
    }}
}});

// Status Code Pie Chart
const scCtx = document.getElementById('statusCodeChart').getContext('2d');
new Chart(scCtx, {{
    type: 'doughnut',
    data: {{
        labels: {json.dumps(list(all_status_codes.keys()))},
        datasets: [{{
            data: {json.dumps(list(all_status_codes.values()))},
            backgroundColor: {json.dumps(['#00ff88' if k == '200' else '#ffaa00' if k.startswith('4') else '#ff4444' if k.startswith('5') else '#8b949e' for k in all_status_codes.keys()])},
        }}]
    }},
    options: {{
        responsive: true,
        plugins: {{
            legend: {{ position: 'right' }}
        }}
    }}
}});
</script>

</body></html>"""

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(html)

        console.print(f"[dim]HTML report saved: {filepath}[/dim]")
        return filepath

    def _generate_recommendations(self, all_times: list, error_rate: float, avg_rps: float) -> list:
        """Generate auto-recommendations based on test results."""
        recommendations = []

        if not all_times:
            return ["No data collected - check connectivity and authentication."]

        avg_rt = sum(all_times) / len(all_times)
        p95 = sorted(all_times)[int(len(all_times) * 0.95)] if all_times else 0
        p99 = sorted(all_times)[int(len(all_times) * 0.99)] if all_times else 0
        sla = self.calculate_sla_compliance(all_times)

        if p95 > self.sla_threshold_ms:
            recommendations.append(
                f"P95 response time ({p95:.0f}ms) exceeds SLA target ({self.sla_threshold_ms:.0f}ms). "
                f"Consider optimizing rule engine processing or adding caching."
            )

        if error_rate > 5:
            recommendations.append(
                f"Error rate ({error_rate:.1f}%) is above acceptable threshold. "
                f"Investigate server logs for root cause (capacity, timeouts, or application errors)."
            )

        if p99 / avg_rt > 5 and len(all_times) > 10:
            recommendations.append(
                f"High tail latency detected (P99/Avg ratio: {p99/avg_rt:.1f}x). "
                f"This suggests occasional slow queries or GC pauses. Consider connection pooling or async processing."
            )

        std_dev = statistics.stdev(all_times) if len(all_times) > 1 else 0
        if std_dev > avg_rt:
            recommendations.append(
                f"Response time variance is very high (StdDev: {std_dev:.0f}ms > Avg: {avg_rt:.0f}ms). "
                f"Performance is inconsistent - check for resource contention or cold starts."
            )

        if sla < 95:
            recommendations.append(
                f"SLA compliance is {sla:.1f}% (target: 95%). "
                f"Consider scaling up infrastructure or optimizing the targeted rule set."
            )

        if avg_rps < self.criteria.get("min_throughput_rps", 1):
            recommendations.append(
                f"Throughput ({avg_rps:.1f} RPS) is below minimum threshold. "
                f"Server may be throttling or under-provisioned for the target load."
            )

        # Check for rate limiting
        total_429 = sum(s.rate_limited_count for s in self.results)
        if total_429 > 0:
            recommendations.append(
                f"Rate limiting detected ({total_429} requests got 429). "
                f"Coordinate with API team to increase rate limits for load testing, or reduce concurrency."
            )

        if not recommendations:
            recommendations.append("All metrics are within acceptable thresholds. System is performing well under the tested load.")

        return recommendations

    def generate_all_reports(self):
        """Generate all report formats."""
        self.print_console_report()
        self.export_json()
        self.export_csv()
        self.export_html()
        console.print(f"\n[bold green]All reports saved to: {self.output_dir}/[/bold green]")
        return self.evaluate_pass_fail()["overall_pass"]
