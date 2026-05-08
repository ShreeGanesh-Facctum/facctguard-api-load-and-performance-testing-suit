# FacctGuard Load Test Suite

A Python-based load testing and performance validation tool for the FacctGuard Transaction Monitoring API. Generates realistic transaction payloads with configurable fraud/clean ratios and executes multiple test scenarios against the API.

## Features

- **Fraud-aware payload generation** — Generates transactions designed to trigger specific FacctGuard rules
- **Multiple test scenarios** — Baseline, ramp-up, spike, sustained, stress, breakpoint, recovery, and race condition tests
- **Interactive & CLI modes** — Run interactively with prompts or headless via CLI flags
- **Comprehensive reporting** — JSON, CSV, and HTML reports with per-request API responses
- **Pass/fail verdicts** — Configurable thresholds for P95, P99, error rate, and throughput
- **Failed payload capture** — Automatically saves payloads that caused errors to `temp/` for debugging
- **Response validation** — Checks response structure, data corruption, and session isolation

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
│   ├── reporter.py             # Report generation (JSON/CSV/HTML)
│   └── validator.py            # Response validation & corruption detection
├── gendata/                    # Sample generated payloads
├── results/                    # Test reports output
├── temp/                       # Failed request payloads (auto-created)
└── requirements.txt            # Python dependencies
```

## Prerequisites

- Python 3.10+
- Access to the FacctGuard API (dev/QA environment)
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
# Quick smoke test
python index.py --profile smoke --token YOUR_BEARER_TOKEN

# Standard load test with 60% fraud transactions
python index.py --profile load --token YOUR_TOKEN --fraud-pct 60

# Stress test against a specific URL
python index.py --profile stress --token YOUR_TOKEN --url https://api-dev-saas.facctum.com/transactionmonitoring/api/facctguard

# Custom request count and concurrency
python index.py --profile load --token YOUR_TOKEN --requests 200 --concurrency 20
```

### CLI Arguments

| Argument | Description | Default |
|----------|-------------|---------|
| `--profile` | Test profile: `smoke`, `load`, `stress`, `endurance`, `breakpoint` | `load` |
| `--token` | Bearer token for authentication | — |
| `--url` | Target API URL | Dev environment |
| `--tenant` | Tenant ID | `Facctum` |
| `--config` | Path to config JSON file | `config/loadtest_config.json` |
| `--requests` | Total requests (overrides profile) | Profile default |
| `--concurrency` | Concurrency level (overrides profile) | Profile default |
| `--fraud-pct` | Percentage of fraud transactions (0-100) | `40` |

## Test Profiles

| Profile | Requests | Concurrency | Duration | Scenarios |
|---------|----------|-------------|----------|-----------|
| **smoke** | 5 | 2 | 10s | Baseline |
| **load** | 100 | 10 | 60s | Ramp-up, Sustained |
| **stress** | 500 | 50 | 120s | Ramp-up, Spike, Sustained, Stress |
| **endurance** | 1000 | 20 | 10 min | Sustained, Recovery |
| **breakpoint** | 2000 | 5→200 | 5 min | Auto-increment until failure |

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

- **JSON** (`loadtest_YYYYMMDD_HHMMSS.json`) — Full results with per-request API responses
- **CSV** (`loadtest_YYYYMMDD_HHMMSS.csv`) — Summary metrics for spreadsheet analysis
- **HTML** (`loadtest_YYYYMMDD_HHMMSS.html`) — Visual report with request details table

### Pass/Fail Criteria (defaults)

| Metric | Threshold |
|--------|-----------|
| P95 response time | ≤ 2000 ms |
| P99 response time | ≤ 5000 ms |
| Error rate | ≤ 5% |
| Throughput | ≥ 1 req/s |

## Failed Request Debugging

When requests fail (timeout, connection error, 5xx, 429), the payloads are automatically saved to `temp/` with the error details and API response. This makes it easy to replay or investigate failures.

## Standalone Data Generation

Generate transaction payloads without running the load test:

```bash
cd load_test_suite
python -m modules.data_generator
```

This outputs `facctum_300_transactions.json` with 300 transactions (40% fraud by default). Edit the variables at the bottom of `data_generator.py` to change the count or ratio.

## Configuration

Edit `config/loadtest_config.json` to customize:
- API endpoints
- OAuth2 credentials
- Test profiles (requests, concurrency, duration)
- Pass/fail thresholds

## Sample API Response

**Successful (alert raised):**
```json
{
  "transaction_id": "TXN202605080912430001",
  "tenant_id": "Facctum",
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
  "tenant_id": "Facctum",
  "message": "There is no alert raised against this transaction",
  "status": "Green",
  "alert_details": []
}
```

## Exit Codes

- `0` — All tests passed
- `1` — One or more tests failed thresholds (useful for CI/CD pipelines)
