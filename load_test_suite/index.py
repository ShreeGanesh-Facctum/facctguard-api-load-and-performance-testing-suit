"""
FacctGuard Load Test Suite - Main Orchestrator
================================================
Interactive CLI that orchestrates the full load testing pipeline:
1. Configure test parameters (interactive or from config)
2. Generate/validate auth token
3. Generate demo transaction payloads
4. Run preflight checks
5. Execute selected test scenarios
6. Generate comprehensive reports

Usage:
    python index.py                  # Interactive mode
    python index.py --profile smoke  # Use a preset profile
    python index.py --config config/loadtest_config.json --profile stress
"""

import asyncio
import json
import sys
import os
import argparse
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, IntPrompt, Confirm

# Add parent to path for module imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from modules.auth import TokenManager
from modules.data_generator import TransactionDataGenerator
from modules.preflight import PreflightChecker
from modules.load_test import LoadTestEngine
from modules.validator import ResponseValidator
from modules.reporter import ReportGenerator

console = Console()

# Default configuration
DEFAULT_CONFIG = {
    "target_url": "https://api-qa-saas.facctum.com/transactionmonitoring/api/facctguard",
    "healthcheck_url": "https://api-qa-saas.facctum.com/transactionmonitoring/api/healthcheck",
    "auth_url": "https://auth-qa-saas.facctum.com/oauth/token",
    "tenant_id": "facctum",
    "timeout_seconds": 30,
}

HEADERS = {
    "Content-Type": "application/json",
    "User-Agent": "insomnia/12.5.0",
    "x-tenant-id": "facctum",
}


def load_config(config_path: str) -> dict:
    """Load configuration from JSON file."""
    try:
        with open(config_path, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        console.print(f"[yellow]Config file not found: {config_path}, using defaults[/yellow]")
        return {}
    except json.JSONDecodeError as e:
        console.print(f"[red]Invalid config JSON: {e}[/red]")
        return {}


def print_banner():
    """Print the application banner."""
    banner = """
[bold cyan]╔══════════════════════════════════════════════════════════╗
║         FacctGuard Load & Performance Test Suite         ║
║                    Python Edition v1.0                    ║
╚══════════════════════════════════════════════════════════╝[/bold cyan]
    """
    console.print(banner)


def get_interactive_config() -> dict:
    """Get test configuration interactively from the user."""
    console.print(Panel("[bold]Test Configuration[/bold]", style="cyan"))

    # Target URL
    target_url = Prompt.ask(
        "Target API URL",
        default=DEFAULT_CONFIG["target_url"],
    )

    # Health check URL
    healthcheck_url = Prompt.ask(
        "Health check URL",
        default=DEFAULT_CONFIG["healthcheck_url"],
    )

    # Tenant ID
    tenant_id = Prompt.ask("Tenant ID", default="facctum")

    # Auth method
    console.print("\n[bold]Authentication:[/bold]")
    console.print("  1. Enter bearer token manually")
    console.print("  2. Use Auth0 client credentials")
    auth_choice = Prompt.ask("Choose auth method", choices=["1", "2"], default="1")

    token = ""
    auth_config = {}
    if auth_choice == "1":
        token = Prompt.ask("Bearer token")
    else:
        auth_config = {
            "auth_url": Prompt.ask("Auth URL", default=DEFAULT_CONFIG["auth_url"]),
            "client_id": Prompt.ask("Client ID"),
            "client_secret": Prompt.ask("Client Secret"),
            "audience": Prompt.ask("Audience", default="https://api-qa-saas.facctum.com"),
        }

    # Test type selection
    console.print("\n[bold]Test Scenarios:[/bold]")
    console.print("  1. Smoke (quick sanity - 5 requests)")
    console.print("  2. Load (standard - 100 requests, 10 concurrent)")
    console.print("  3. Stress (heavy - 500 requests, 50 concurrent)")
    console.print("  4. Endurance (soak - 1000 requests over 10 min)")
    console.print("  5. Breakpoint (find breaking point)")
    console.print("  6. Custom (you define everything)")
    console.print("  7. All scenarios")

    test_choice = Prompt.ask(
        "Choose test scenario",
        choices=["1", "2", "3", "4", "5", "6", "7"],
        default="2",
    )

    # Map choices to profiles
    profile_map = {
        "1": "smoke", "2": "load", "3": "stress",
        "4": "endurance", "5": "breakpoint", "6": "custom", "7": "all",
    }
    profile = profile_map[test_choice]

    custom_config = {}
    if profile == "custom":
        custom_config = {
            "total_requests": IntPrompt.ask("Total requests", default=100),
            "concurrency": IntPrompt.ask("Concurrency level", default=10),
            "duration_seconds": IntPrompt.ask("Duration (seconds)", default=60),
        }
        console.print("\n[bold]Select test types (comma-separated):[/bold]")
        console.print("  baseline, ramp_up, spike, sustained, stress, breakpoint, recovery, race_condition")
        test_types_str = Prompt.ask("Test types", default="baseline,sustained")
        custom_config["test_types"] = [t.strip() for t in test_types_str.split(",")]

    # Fraud percentage for generated transactions
    fraud_pct = IntPrompt.ask("Fraud transaction percentage (0-100)", default=40)
    if fraud_pct < 0 or fraud_pct > 100:
        fraud_pct = 40

    # Pass/fail thresholds
    use_custom_thresholds = Confirm.ask("Customize pass/fail thresholds?", default=False)
    thresholds = {}
    if use_custom_thresholds:
        thresholds = {
            "max_p90_ms": IntPrompt.ask("Max P90 response time (ms)", default=1000),
            "max_p95_ms": IntPrompt.ask("Max P95 response time (ms)", default=2000),
            "max_p99_ms": IntPrompt.ask("Max P99 response time (ms)", default=5000),
            "max_error_rate_percent": IntPrompt.ask("Max error rate (%)", default=5),
            "min_throughput_rps": IntPrompt.ask("Min throughput (req/s)", default=1),
        }

    return {
        "target_url": target_url,
        "healthcheck_url": healthcheck_url,
        "tenant_id": tenant_id,
        "token": token,
        "auth_config": auth_config,
        "profile": profile,
        "custom_config": custom_config,
        "fraud_percentage": fraud_pct,
        "thresholds": thresholds,
    }


def get_profile_config(profile_name: str, config: dict) -> dict:
    """Get configuration for a named profile."""
    profiles = config.get("profiles", {})
    if profile_name in profiles:
        return profiles[profile_name]

    # Fallback defaults
    defaults = {
        "smoke": {"total_requests": 5, "concurrency": 2, "duration_seconds": 10, "test_types": ["baseline"]},
        "load": {"total_requests": 100, "concurrency": 10, "duration_seconds": 60, "test_types": ["ramp_up", "sustained"]},
        "stress": {"total_requests": 500, "concurrency": 50, "duration_seconds": 120, "test_types": ["ramp_up", "spike", "sustained", "stress"]},
        "endurance": {"total_requests": 1000, "concurrency": 20, "duration_seconds": 600, "test_types": ["sustained", "recovery"]},
        "breakpoint": {"total_requests": 2000, "concurrency": 5, "max_concurrency": 200, "concurrency_step": 5, "error_threshold_percent": 10, "duration_seconds": 300, "test_types": ["breakpoint"]},
    }
    return defaults.get(profile_name, defaults["load"])


async def run_tests(config: dict):
    """Main test execution pipeline."""
    target_url = config["target_url"]
    healthcheck_url = config["healthcheck_url"]
    tenant_id = config["tenant_id"]
    fraud_percentage = config.get("fraud_percentage", 40.0)

    # ── Step 1: Auth ──
    console.print(Panel("[bold]STEP 1: Authentication[/bold]", style="cyan"))
    token = config.get("token", "")

    if not token and config.get("auth_config"):
        ac = config["auth_config"]
        token_mgr = TokenManager(
            auth_url=ac["auth_url"],
            client_id=ac["client_id"],
            client_secret=ac["client_secret"],
            audience=ac["audience"],
            tenant_id=tenant_id,
        )
        token = await token_mgr.get_token()
    elif token:
        console.print("[green]Using provided bearer token[/green]")
    else:
        console.print("[red]No authentication configured. Aborting.[/red]")
        return False

    # Update headers with tenant
    headers = {**HEADERS, "x-tenant-id": tenant_id}

    # ── Step 2: Generate Data ──
    console.print(Panel("[bold]STEP 2: Generating Test Data[/bold]", style="cyan"))
    generator = TransactionDataGenerator(tenant_id=tenant_id)

    # Determine request count
    profile = config.get("profile", "load")
    if profile == "custom":
        profile_config = config.get("custom_config", {})
    elif profile == "all":
        profile_config = {"total_requests": 200, "concurrency": 20, "duration_seconds": 120, "test_types": ["baseline", "ramp_up", "spike", "sustained", "stress", "recovery", "race_condition"]}
    else:
        file_config = load_config(os.path.join(os.path.dirname(__file__), "config", "loadtest_config.json"))
        profile_config = get_profile_config(profile, file_config)

    total_requests = profile_config.get("total_requests", 100)
    concurrency = profile_config.get("concurrency", 10)
    duration = profile_config.get("duration_seconds", 60)
    test_types = profile_config.get("test_types", ["baseline"])

    console.print(f"  Generating {total_requests} unique transaction payloads...")
    console.print(f"  Fraud percentage: {fraud_percentage}%")
    payloads = generator.generate_batch(total_requests, fraud_percentage=fraud_percentage)
    console.print(f"  [green]Generated {len(payloads)} payloads ({int(total_requests * fraud_percentage / 100)} fraud, {total_requests - int(total_requests * fraud_percentage / 100)} clean)[/green]")

    # ── Step 3: Preflight ──
    console.print(Panel("[bold]STEP 3: Preflight Checks[/bold]", style="cyan"))
    preflight = PreflightChecker(
        target_url=target_url,
        healthcheck_url=healthcheck_url,
        headers=headers,
    )
    preflight_ok = await preflight.run_all(token, payloads[0])
    if not preflight_ok:
        skip = Confirm.ask("Preflight failed. Continue anyway?", default=False)
        if not skip:
            console.print("[red]Aborting.[/red]")
            return False

    # ── Step 4: Run Tests ──
    console.print(Panel("[bold]STEP 4: Running Load Tests[/bold]", style="cyan"))
    engine = LoadTestEngine(
        target_url=target_url,
        headers=headers,
        token=token,
        timeout_seconds=config.get("timeout_seconds", 30),
        tenant_id=tenant_id,
    )

    for test_type in test_types:
        try:
            if test_type == "baseline":
                await engine.run_baseline(payloads, concurrency)

            elif test_type == "ramp_up":
                start_c = max(1, concurrency // 5)
                await engine.run_ramp_up(payloads, start_c, concurrency, steps=5)

            elif test_type == "spike":
                spike_c = concurrency * 2
                await engine.run_spike(payloads, spike_c)

            elif test_type == "sustained":
                await engine.run_sustained(payloads, concurrency, duration)

            elif test_type == "stress":
                stress_c = concurrency * 3
                await engine.run_stress(payloads, stress_c)

            elif test_type == "breakpoint":
                start_c = profile_config.get("concurrency", 5)
                max_c = profile_config.get("max_concurrency", 200)
                step = profile_config.get("concurrency_step", 5)
                threshold = profile_config.get("error_threshold_percent", 10)
                await engine.run_breakpoint(
                    payload_generator=lambda n: generator.generate_batch(n, fraud_percentage=fraud_percentage),
                    start_concurrency=start_c,
                    max_concurrency=max_c,
                    step=step,
                    error_threshold_percent=threshold,
                )

            elif test_type == "recovery":
                spike_c = concurrency * 3
                await engine.run_recovery(payloads, spike_c, concurrency)

            elif test_type == "race_condition":
                await engine.run_concurrent_race_condition(payloads[0], count=20)

            else:
                console.print(f"[yellow]Unknown test type: {test_type}, skipping[/yellow]")

        except Exception as e:
            console.print(f"[red]Error in {test_type}: {e}[/red]")
            import traceback
            traceback.print_exc()

    # ── Step 5: Report ──
    console.print(Panel("[bold]STEP 5: Generating Reports[/bold]", style="cyan"))
    thresholds = config.get("thresholds") or {
        "max_p95_ms": 2000,
        "max_p99_ms": 5000,
        "max_error_rate_percent": 5,
        "min_throughput_rps": 1,
    }

    # Build test configuration metadata for the report
    test_config_meta = {
        "profile": profile,
        "target_url": target_url,
        "healthcheck_url": healthcheck_url,
        "tenant_id": tenant_id,
        "total_requests": total_requests,
        "concurrency": concurrency,
        "duration_seconds": duration,
        "test_types": test_types,
        "fraud_percentage": fraud_percentage,
        "timeout_seconds": config.get("timeout_seconds", 30),
        "pass_fail_criteria": thresholds,
        "auth_method": "OAuth2 Client Credentials" if config.get("auth_config") else "Bearer Token",
    }

    reporter = ReportGenerator(
        results=engine.all_results,
        pass_fail_criteria=thresholds,
        output_dir=os.path.join(os.path.dirname(__file__), "results"),
        test_config=test_config_meta,
    )
    passed = reporter.generate_all_reports()

    return passed


def main():
    """Entry point."""
    parser = argparse.ArgumentParser(description="FacctGuard Load Test Suite")
    parser.add_argument("--profile", type=str, help="Test profile: smoke, load, stress, endurance, breakpoint, custom")
    parser.add_argument("--config", type=str, help="Path to config JSON file")
    parser.add_argument("--token", type=str, help="Bearer token (skip interactive auth)")
    parser.add_argument("--url", type=str, help="Target API URL")
    parser.add_argument("--tenant", type=str, help="Tenant ID")
    parser.add_argument("--requests", type=int, help="Total requests (overrides profile)")
    parser.add_argument("--concurrency", type=int, help="Concurrency level (overrides profile)")
    parser.add_argument("--duration", type=int, help="Test duration in seconds (overrides profile)")
    parser.add_argument("--test-types", type=str, help="Comma-separated test types: baseline,ramp_up,spike,sustained,stress,breakpoint,recovery,race_condition")
    parser.add_argument("--fraud-pct", type=int, default=40, help="Percentage of fraud transactions (0-100)")
    parser.add_argument("--p90", type=int, help="Max P90 response time threshold (ms)")
    parser.add_argument("--p95", type=int, help="Max P95 response time threshold (ms)")
    parser.add_argument("--p99", type=int, help="Max P99 response time threshold (ms)")
    parser.add_argument("--max-error-rate", type=float, help="Max error rate threshold (%%)")
    parser.add_argument("--min-rps", type=float, help="Min throughput threshold (req/s)")
    parser.add_argument("--timeout", type=int, help="Request timeout in seconds (default: 30)")
    # Auth0 client credentials (alternative to --token)
    parser.add_argument("--client-id", type=str, help="Auth0 client ID (use instead of --token)")
    parser.add_argument("--client-secret", type=str, help="Auth0 client secret (use with --client-id)")
    parser.add_argument("--auth-url", type=str, help="Auth0 token URL (default: from config)")
    parser.add_argument("--audience", type=str, help="Auth0 audience (default: from config)")
    args = parser.parse_args()

    print_banner()

    # Determine if running in CLI mode or interactive mode
    if args.profile or args.token or args.client_id:
        # CLI mode - build config from args
        file_config = {}
        if args.config:
            file_config = load_config(args.config)

        profile = args.profile or "custom"
        profile_config = get_profile_config(profile, file_config)

        # Override profile config with CLI args
        if args.requests:
            profile_config["total_requests"] = args.requests
        if args.concurrency:
            profile_config["concurrency"] = args.concurrency
        if args.duration:
            profile_config["duration_seconds"] = args.duration
        if args.test_types:
            profile_config["test_types"] = [t.strip() for t in args.test_types.split(",")]

        # Build thresholds from CLI args or config file
        config_thresholds = file_config.get("defaults", {}).get("pass_fail_criteria", {})
        thresholds = {
            "max_p90_ms": args.p90 or config_thresholds.get("max_p90_ms", 1000),
            "max_p95_ms": args.p95 or config_thresholds.get("max_p95_ms", 2000),
            "max_p99_ms": args.p99 or config_thresholds.get("max_p99_ms", 5000),
            "max_error_rate_percent": args.max_error_rate if args.max_error_rate is not None else config_thresholds.get("max_error_rate_percent", 5),
            "min_throughput_rps": args.min_rps if args.min_rps is not None else config_thresholds.get("min_throughput_rps", 1),
        }

        # Build auth config if client credentials provided
        auth_config = {}
        if args.client_id and args.client_secret:
            auth_config = {
                "auth_url": args.auth_url or DEFAULT_CONFIG["auth_url"],
                "client_id": args.client_id,
                "client_secret": args.client_secret,
                "audience": args.audience or "https://api-qa-saas.facctum.com",
            }

        config = {
            "target_url": args.url or DEFAULT_CONFIG["target_url"],
            "healthcheck_url": DEFAULT_CONFIG["healthcheck_url"],
            "tenant_id": args.tenant or "facctum",
            "token": args.token or "",
            "auth_config": auth_config,
            "profile": "custom" if (args.requests or args.duration or args.test_types) else profile,
            "custom_config": profile_config,
            "fraud_percentage": args.fraud_pct,
            "thresholds": thresholds,
            "timeout_seconds": args.timeout or 30,
        }
    else:
        # Interactive mode
        config = get_interactive_config()

    # Run
    passed = asyncio.run(run_tests(config))

    # Exit code for CI/CD
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
