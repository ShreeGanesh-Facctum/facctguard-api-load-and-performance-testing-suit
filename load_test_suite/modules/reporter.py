"""
Reporter Module - Analysis & Report Generation
================================================
Generates comprehensive reports in multiple formats:
- Rich console output with tables and charts
- JSON export for programmatic analysis
- CSV export for spreadsheet analysis
- HTML report for sharing
- Pass/fail verdict based on configurable thresholds
"""

import json
import csv
import os
import time
from datetime import datetime
from typing import Optional
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text

from .load_test import ScenarioResult

console = Console()


class ReportGenerator:
    """Generates load test reports in multiple formats."""

    def __init__(
        self,
        results: list[ScenarioResult],
        pass_fail_criteria: Optional[dict] = None,
        output_dir: str = "results",
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
        os.makedirs(output_dir, exist_ok=True)

    def evaluate_pass_fail(self) -> dict:
        """Evaluate all scenarios against pass/fail criteria."""
        verdicts = {}
        overall_pass = True

        for scenario in self.results:
            verdict = {"scenario": scenario.scenario_name, "checks": {}, "pass": True}

            # P95 check
            p95 = scenario.percentile(95)
            p95_pass = p95 <= self.criteria["max_p95_ms"]
            verdict["checks"]["p95_ms"] = {
                "value": round(p95, 1),
                "threshold": self.criteria["max_p95_ms"],
                "pass": p95_pass,
            }
            if not p95_pass:
                verdict["pass"] = False

            # P99 check
            p99 = scenario.percentile(99)
            p99_pass = p99 <= self.criteria["max_p99_ms"]
            verdict["checks"]["p99_ms"] = {
                "value": round(p99, 1),
                "threshold": self.criteria["max_p99_ms"],
                "pass": p99_pass,
            }
            if not p99_pass:
                verdict["pass"] = False

            # Error rate check
            err = scenario.error_rate
            err_pass = err <= self.criteria["max_error_rate_percent"]
            verdict["checks"]["error_rate_percent"] = {
                "value": round(err, 2),
                "threshold": self.criteria["max_error_rate_percent"],
                "pass": err_pass,
            }
            if not err_pass:
                verdict["pass"] = False

            # Throughput check
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

        for s in self.results:
            avg = sum(s.response_times) / len(s.response_times) if s.response_times else 0
            err_style = "red" if s.error_rate > 5 else "yellow" if s.error_rate > 1 else "green"
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

        # Status code distribution
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

        # Response time distribution (text histogram)
        self._print_response_time_histogram()

        # Pass/Fail verdict
        verdict = self.evaluate_pass_fail()
        self._print_verdict(verdict)

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
            "verdict": self.evaluate_pass_fail(),
            "scenarios": [],
        }

        for s in self.results:
            avg = sum(s.response_times) / len(s.response_times) if s.response_times else 0
            scenario_data = {
                "name": s.scenario_name,
                "total_requests": s.total_requests,
                "successful": s.successful,
                "failed": s.failed,
                "error_rate_percent": round(s.error_rate, 2),
                "throughput_rps": round(s.throughput_rps, 2),
                "duration_seconds": round(s.duration_seconds, 2),
                "response_times": {
                    "min": round(min(s.response_times), 1) if s.response_times else 0,
                    "avg": round(avg, 1),
                    "max": round(max(s.response_times), 1) if s.response_times else 0,
                    "p50": round(s.percentile(50), 1),
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

            # Include per-request details with API response
            for r in s.requests:
                # Parse response body as JSON if possible
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
                    "error": r.error,
                    "response": response_parsed,
                }
                scenario_data["requests"].append(request_detail)

            report["scenarios"].append(scenario_data)

        with open(filepath, "w") as f:
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
                "RPS", "Duration(s)", "Min(ms)", "Avg(ms)", "Max(ms)",
                "P50(ms)", "P95(ms)", "P99(ms)", "429s", "Timeouts", "ConnErrors",
            ])
            for s in self.results:
                avg = sum(s.response_times) / len(s.response_times) if s.response_times else 0
                writer.writerow([
                    s.scenario_name, s.total_requests, s.successful, s.failed,
                    f"{s.error_rate:.2f}", f"{s.throughput_rps:.2f}",
                    f"{s.duration_seconds:.2f}",
                    f"{min(s.response_times):.1f}" if s.response_times else 0,
                    f"{avg:.1f}",
                    f"{max(s.response_times):.1f}" if s.response_times else 0,
                    f"{s.percentile(50):.1f}", f"{s.percentile(95):.1f}",
                    f"{s.percentile(99):.1f}",
                    s.rate_limited_count, s.timeout_count, s.connection_errors,
                ])

        console.print(f"[dim]CSV report saved: {filepath}[/dim]")
        return filepath

    def export_html(self) -> str:
        """Export results to an HTML report."""
        filepath = os.path.join(self.output_dir, f"loadtest_{self.timestamp}.html")
        verdict = self.evaluate_pass_fail()
        overall_class = "pass" if verdict["overall_pass"] else "fail"

        rows_html = ""
        for s in self.results:
            avg = sum(s.response_times) / len(s.response_times) if s.response_times else 0
            err_class = "fail" if s.error_rate > 5 else "warn" if s.error_rate > 1 else "pass"
            rows_html += f"""<tr>
                <td>{s.scenario_name}</td><td>{s.total_requests}</td>
                <td class="pass">{s.successful}</td><td class="fail">{s.failed}</td>
                <td class="{err_class}">{s.error_rate:.1f}%</td>
                <td>{s.throughput_rps:.2f}</td><td>{avg:.0f}</td>
                <td>{s.percentile(50):.0f}</td><td>{s.percentile(95):.0f}</td>
                <td>{s.percentile(99):.0f}</td>
                <td>{max(s.response_times):.0f}</td>
            </tr>"""

        # Build per-request detail sections for each scenario
        request_details_html = ""
        for s in self.results:
            request_details_html += f'<h2>Request Details: {s.scenario_name}</h2>\n'
            request_details_html += """<table class="request-table">
                <tr><th>#</th><th>Transaction ID</th><th>Status</th><th>Time (ms)</th><th>Error</th><th>API Response</th></tr>\n"""

            for r in s.requests:
                status_class = "pass" if r.status_code == 200 else "warn" if r.status_code == 400 else "fail"
                error_text = r.error or "-"

                # Parse and format response
                response_text = ""
                try:
                    if r.response_body:
                        parsed = json.loads(r.response_body)
                        response_text = json.dumps(parsed, indent=2)
                    else:
                        response_text = "-"
                except (json.JSONDecodeError, TypeError):
                    response_text = r.response_body[:500] if r.response_body else "-"

                # Escape HTML in response
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

            request_details_html += "</table>\n"

        html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Load Test Report</title>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; margin: 2rem; background: #1a1a2e; color: #eee; }}
h1 {{ color: #00d4ff; }} h2 {{ color: #7b68ee; }}
table {{ border-collapse: collapse; width: 100%; margin: 1rem 0; }}
th, td {{ border: 1px solid #333; padding: 8px 12px; text-align: right; }}
th {{ background: #16213e; color: #00d4ff; }}
td:first-child {{ text-align: left; }}
tr:nth-child(even) {{ background: #16213e; }}
.pass {{ color: #00ff88; font-weight: bold; }}
.fail {{ color: #ff4444; font-weight: bold; }}
.warn {{ color: #ffaa00; font-weight: bold; }}
.verdict {{ padding: 1rem 2rem; border-radius: 8px; font-size: 1.5rem; text-align: center; margin: 1rem 0; }}
.verdict.pass {{ background: #0a3d0a; border: 2px solid #00ff88; }}
.verdict.fail {{ background: #3d0a0a; border: 2px solid #ff4444; }}
.request-table td {{ text-align: left; vertical-align: top; }}
.request-table th {{ text-align: left; }}
.response-pre {{ background: #0d1117; border: 1px solid #333; border-radius: 4px; padding: 8px; margin: 0; font-size: 11px; max-height: 200px; overflow: auto; white-space: pre-wrap; word-break: break-word; color: #c9d1d9; }}
</style></head><body>
<h1>FacctGuard Load Test Report</h1>
<p>Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
<div class="verdict {overall_class}">OVERALL: {"PASS" if verdict["overall_pass"] else "FAIL"}</div>
<h2>Scenario Summary</h2>
<table><tr><th>Scenario</th><th>Total</th><th>Success</th><th>Failed</th><th>Err%</th>
<th>RPS</th><th>Avg(ms)</th><th>P50</th><th>P95</th><th>P99</th><th>Max</th></tr>
{rows_html}</table>
{request_details_html}
</body></html>"""

        with open(filepath, "w") as f:
            f.write(html)

        console.print(f"[dim]HTML report saved: {filepath}[/dim]")
        return filepath

    def generate_all_reports(self):
        """Generate all report formats."""
        self.print_console_report()
        self.export_json()
        self.export_csv()
        self.export_html()
        console.print(f"\n[bold green]All reports saved to: {self.output_dir}/[/bold green]")
        return self.evaluate_pass_fail()["overall_pass"]
