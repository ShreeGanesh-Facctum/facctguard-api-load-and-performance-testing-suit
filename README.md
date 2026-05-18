# FacctGuard Load Test Suite

A Python-based load testing and performance validation tool for the FacctGuard Transaction Monitoring API. Generates realistic transaction payloads with configurable fraud/clean ratios and executes multiple test scenarios against the API.

## Features

- **Fraud-aware payload generation** — Generates transactions designed to trigger specific FacctGuard rules
- **Multiple test scenarios** — Baseline, ramp-up, spike, sustained, stress, breakpoint, recovery, and race condition tests
- **Interactive & CLI modes** — Run interactively with prompts or fully headless via CLI flags
- **Comprehensive reporting** — JSON, CSV, and HTML reports with interactive Chart.js graphs
- **Pass/fail verdicts** — Configurable thresholds for P95, P99, error rate, and throughput
- **Apdex & SLA tracking** — Apdex score calculation and SLA compliance percentage
- **Auto-generated recommendations** — Actionable suggestions based on test results
- **Failed payload capture** — Automatically saves payloads that caused errors to `temp/` for debugging
- **Response validation** — Checks response structure, data corruption, and session isolation
- **OAuth2 client credentials** — Authenticate via CLI flags without interactive prompts

## Project Structure

```
load_test_suite/
├── index.py                    # Main entry point & orchestrator
├── config/
│   └── loadtest_config.json    # Test profiles & default configuration
├── modules/
│   ├── auth.py                 # Token management (OAuth2 client credentials)
│   ├── data_generator.py       # Transaction payload generator
│   ├── load_test.py            # Core test engine (async HTTP)
│   ├── preflight.py            # Pre-test health & validation checks
│   ├── reporter.py             # Report generation (JSON/CSV/HTML + charts)
│   └── validator.py            # Response validation & corruption detection
├── gendata/                    # Sample generated payloads
├── results/                    # Test reports output
├── temp/                       # Failed request payloads (auto-created)
└── requirements.txt            # Python dependencies
```

## Prerequisites

- Python 3.10+
- Access to the FacctGuard API (QA environment)
- Valid bearer token or OAuth2 client credentials

## Installation

```bash
cd load_test_suite
pip install -r requirements.txt
```

## Usage

### Interactive Mode

```bash
python index.py
```

You'll be prompted for:
1. Target API URL
2. Authentication (bearer token or OAuth2 credentials)
3. Test scenario (smoke, load, stress, endurance, breakpoint, custom, all)
4. Fraud transaction percentage (0-100%)
5. Pass/fail thresholds (optional)

### CLI Mode

```bash
# Quick smoke test with bearer token
python index.py --profile smoke --token YOUR_BEARER_TOKEN

# Standard load test with OAuth2 client credentials
python index.py --profile load --client-id "YOUR_CLIENT_ID" --client-secret "YOUR_SECRET"

# Custom test: 6000 requests, 10 concurrency, 600s duration, sustained load
python index.py --client-id "YOUR_CLIENT_ID" --client-secret "YOUR_SECRET" \
  --requests 6000 --concurrency 10 --duration 600 --test-types sustained \
  --p95 500 --p99 1000 --max-error-rate 1 --min-rps 5

# Spike test: 110 TPS burst
python index.py --token YOUR_TOKEN --requests 1100 --concurrency 110 \
  --duration 10 --test-types baseline --p95 1000 --max-error-rate 5

# Breakpoint discovery
python index.py --token YOUR_TOKEN --requests 2000 --concurrency 10 \
  --duration 300 --test-types breakpoint --max-error-rate 10

# Override target URL and tenant
python index.py --token YOUR_TOKEN --url https://api-qa-saas.facctum.com/transactionmonitoring/api/facctguard \
  --tenant facctum --profile load
```

### CLI Arguments

| Argument | Description | Default |
|----------|-------------|---------|
| **Test Configuration** | | |
| `--profile` | Test profile: `smoke`, `load`, `stress`, `endurance`, `breakpoint`, `custom` | `custom` (when other flags used) |
| `--requests` | Total requests (overrides profile) | Profile default |
| `--concurrency` | Concurrency level (overrides profile) | Profile default |
| `--duration` | Test duration in seconds (overrides profile) | Profile default |
| `--test-types` | Comma-separated: `baseline,ramp_up,spike,sustained,stress,breakpoint,recovery,race_condition` | Profile default |
| `--fraud-pct` | Percentage of fraud transactions (0-100) | `40` |
| `--timeout` | Per-request timeout in seconds | `30` |
| **Authentication** | | |
| `--token` | Bearer token (skip OAuth2 flow) | — |
| `--client-id` | OAuth2 client ID (alternative to --token) | — |
| `--client-secret` | OAuth2 client secret (use with --client-id) | — |
| `--auth-url` | OAuth2 token endpoint URL | QA environment |
| `--audience` | OAuth2 audience | QA environment |
| **Endpoints** | | |
| `--url` | Target API URL | QA environment |
| `--tenant` | Tenant ID | `facctum` |
| `--config` | Path to config JSON file | `config/loadtest_config.json` |
| **Pass/Fail Thresholds** | | |
| `--p95` | Max P95 response time threshold (ms) | `2000` |
| `--p99` | Max P99 response time threshold (ms) | `5000` |
| `--max-error-rate` | Max error rate threshold (%) | `5` |
| `--min-rps` | Min throughput threshold (req/s) | `1` |

## Test Profiles

| Profile | Requests | Concurrency | Duration | Scenarios |
|---------|----------|-------------|----------|-----------|
| **smoke** | 5 | 2 | 10s | Baseline |
| **load** | 100 | 10 | 60s | Ramp-up, Sustained |
| **stress** | 500 | 50 | 120s | Ramp-up, Spike, Sustained, Stress |
| **endurance** | 6000 | 10 | 10 min | Sustained, Recovery |
| **breakpoint** | 2000 | 5→200 | 5 min | Auto-increment until failure |

## Production Readiness Test Plan

Based on LuLu Exchange UAE data volumes (2025 actuals + 10% YoY growth for 2026):

| Test | Command |
|------|---------|
| **Sustained Peak (7 TPS, 1hr)** | `--requests 24000 --concurrency 7 --duration 3600 --test-types sustained --p95 500 --p99 1000 --max-error-rate 1 --min-rps 7` |
| **Spike (110 TPS)** | `--requests 1100 --concurrency 110 --duration 10 --test-types baseline --p95 1000 --p99 2000 --max-error-rate 5 --min-rps 50` |
| **Recovery** | `--requests 3000 --concurrency 37 --duration 60 --test-types recovery --p95 500 --p99 1000 --max-error-rate 5 --min-rps 5` |
| **Endurance (4hr soak)** | `--requests 69000 --concurrency 10 --duration 14400 --test-types sustained --p95 500 --p99 1000 --max-error-rate 1 --min-rps 4 --timeout 60` |
| **Breakpoint** | `--requests 2000 --concurrency 10 --duration 300 --test-types breakpoint --p95 500 --p99 1000 --max-error-rate 10 --min-rps 5` |

### Production SLA Targets

| Metric | Target |
|--------|--------|
| P95 Response Time | < 500ms |
| P99 Response Time | < 1000ms |
| Max Response Time | < 3000ms |
| Error Rate | < 1% |
| Availability | 99.9% (24x7x365) |
| Sustained Throughput | ≥ 7 TPS (400 txn/min) |
| Spike Handling | 110 TPS for 10s |
| Recovery Time | < 5s post-spike |

## Fraud Rules Targeted

The data generator creates payloads designed to trigger these FacctGuard rules:

| Rule | Trigger Conditions |
|------|-------------------|
| **HIGH_RISK_COUNTRY** | Sender in high-risk country (LBY, AFG, SYR, IRN, IRQ, TUR) + Amount > 100,000 AED |
| **HIGH_RISK_CUSTOMER** | CustomerRiskRating = HIGH + Amount > 50,000 AED |
| **HIGH_AMOUNT_NATURAL_PERSON** | PartyType = Individual + Amount > 99,999 AED |
| **HIGH_AMOUNT_LEGAL_PERSON** | PartyType = Corporate + Amount > 250,000 AED |
| **HIGH_FREQUENCY_NATURAL_PERSON** | Same customer, multiple transactions within 3 days |
| **MULTIPLE_ORIGINATORS_SAME_BENEFICIARY** | Different senders to same beneficiary within 7 days |

Clean transactions are generated with amounts below 45,000 AED and low-risk profiles.

## Reports

After each test run, reports are saved to `results/`:

- **JSON** (`loadtest_YYYYMMDD_HHMMSS.json`) — Full results with per-request API responses, Apdex, SLA compliance
- **CSV** (`loadtest_YYYYMMDD_HHMMSS.csv`) — Summary metrics including StdDev, P75, P90, Apdex, SLA%
- **HTML** (`loadtest_YYYYMMDD_HHMMSS.html`) — Interactive report with Chart.js graphs

### HTML Report Contents

- Executive summary with key metrics
- Metric cards dashboard (Total Requests, Error Rate, RPS, Apdex, SLA%)
- **Response Time Over Time** — Line chart with SLA threshold line
- **Throughput Over Time** — RPS trend chart
- **Error Rate Over Time** — Error trend with fill
- **Percentile Distribution (CDF)** — Response time CDF curve
- **Response Time Histogram** — Latency bucket distribution
- **Status Code Distribution** — Doughnut chart
- Scenario summary table with Apdex and SLA columns
- Error breakdown table
- Auto-generated recommendations
- Per-request detail table with full API responses

### Pass/Fail Criteria (defaults)

| Metric | Threshold |
|--------|-----------|
| P95 response time | ≤ 2000 ms |
| P99 response time | ≤ 5000 ms |
| Error rate | ≤ 5% |
| Throughput | ≥ 1 req/s |

Override via CLI: `--p95 500 --p99 1000 --max-error-rate 1 --min-rps 7`

## Failed Request Debugging

When requests fail (timeout, connection error, 5xx, 429), the payloads are automatically saved to `temp/` with the error details and API response. This makes it easy to replay or investigate failures.

## Standalone Data Generation

Generate transaction payloads without running the load test:

```bash
cd load_test_suite
python -m modules.data_generator
```

This outputs `facctum_300_transactions.json` with 300 transactions (40% fraud by default).

## Configuration

Edit `config/loadtest_config.json` to customize:
- API endpoints (target URL, healthcheck URL, auth URL)
- OAuth2 credentials (client_id, client_secret, audience)
- Test profiles (requests, concurrency, duration, test types)
- Pass/fail thresholds (P95, P99, error rate, throughput)

## Environment

| Environment | API Base URL | Auth URL |
|-------------|-------------|----------|
| QA | `https://api-qa-saas.facctum.com` | `https://auth-qa-saas.facctum.com/oauth/token` |
| Dev | `https://api-dev-saas.facctum.com` | `https://auth-dev-saas.facctum.com/oauth/token` |

Default: **QA environment**

## Sample API Response

**Successful (alert raised):**
```json
{
  "transaction_id": "TXN202605080912430001",
  "tenant_id": "facctum",
  "message": "Alert raised against this transaction",
  "status": "Red",
  "alert_details": [
    {
      "alert_id": "ALT_001",
      "alert_risk_score": 0.85,
      "rule_triggered": "HIGH_RISK_COUNTRY"
    }
  ]
}
```

**Successful (no alert):**
```json
{
  "transaction_id": "TXN202605080912430002",
  "tenant_id": "facctum",
  "message": "There is no alert raised against this transaction",
  "status": "Green",
  "alert_details": []
}
```

## Exit Codes

- `0` — All tests passed
- `1` — One or more tests failed thresholds (useful for CI/CD pipelines)
