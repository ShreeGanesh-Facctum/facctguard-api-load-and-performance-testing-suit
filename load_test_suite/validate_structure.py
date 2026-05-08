"""
Structural Validation: Generated Payload vs transaction.json Template
=====================================================================
Compares the key structure of generated payloads against the working
transaction.json template to catch mismatches before load testing.

Since the data_generator module may be incomplete, this script can also
assemble a payload directly from the available private generator methods.

Checks performed:
  1. Keys in template missing from generated payload
  2. Extra keys in generated payload not in template
  3. Type mismatches (dict vs scalar, array vs scalar, etc.)
  4. Case sensitivity issues (e.g., CardDetails vs cardDetails)

Usage:
    python validate_structure.py
    python validate_structure.py --verbose
    python validate_structure.py --no-card
"""

import json
import sys
import os
import argparse
import random
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from modules.data_generator import TransactionDataGenerator


# ============================================================
# PAYLOAD ASSEMBLY (fallback when generate_full_payload is missing)
# ============================================================

def assemble_payload_from_generator(gen: TransactionDataGenerator, include_card: bool = True) -> dict:
    """
    Assemble a full transaction payload by calling the generator's
    private methods directly. This is a fallback for when the public
    generate_full_payload/generate_batch methods are not yet implemented.
    """
    txn_type = random.choice(["CARD", "WIRE", "FX"])

    # Required IDs
    ord_cust_id = gen._gen_customer_id("CUST")
    ord_acct = gen._gen_account_number()
    ord_iban = gen._gen_iban()
    ben_cust_id = gen._gen_customer_id("BENEF")
    ben_acct = gen._gen_account_number()
    ben_iban = gen._gen_iban()

    # Build InterbankPaymentTransaction
    txn_header = gen._gen_transaction_header(txn_type)
    txn_id_section = gen._gen_transaction_identification()
    txn_id = txn_id_section["TransactionID"]
    amount_section = gen._gen_amount_section()

    interbank = {
        "TransactionHeader": txn_header,
        "TransactionIdentification": txn_id_section,
        "BeneficiaryDetails": {
            "BeneficiaryAccountNumber": ben_acct,
            "BeneficiaryIBAN": ben_iban,
            "BeneficiaryCustomerID": ben_cust_id,
        },
        "OrderingPartyDetails": {
            "OrderingPartyAccountNumber": ord_acct,
            "OrderingPartyIBAN": ord_iban,
            "OrderingPartyCustomerID": ord_cust_id,
        },
        "Amount": amount_section,
    }

    # OrderingParty & Beneficiary
    ordering_party, ord_name = gen._gen_ordering_party(ord_cust_id, ord_acct, ord_iban)
    beneficiary = gen._gen_beneficiary(ben_cust_id, ben_acct, ben_iban)

    # Assemble the full payload
    payload = {
        "transactionPayment": {
            "InterbankPaymentTransaction": interbank,
            "TenantDetails": gen._gen_tenant_details(),
            "OrderingParty": ordering_party,
            "Beneficiary": beneficiary,
        }
    }

    # Note: Optional sections (PaymentChain, PaymentDetails, ComplianceData, etc.)
    # are NOT generated here because the data_generator doesn't have those methods yet.
    # The structural comparison will flag them as "missing from generated".

    return payload


# ============================================================
# STRUCTURAL COMPARISON ENGINE
# ============================================================

def get_all_keys(obj: Any, prefix: str = "") -> dict:
    """
    Recursively extract all key paths from a JSON object.
    Returns a dict of {path: type_name} for structural comparison.

    Arrays are traversed into their first element (if it's a dict).
    """
    keys = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            full_path = f"{prefix}.{k}" if prefix else k
            keys[full_path] = type(v).__name__
            if isinstance(v, dict):
                keys.update(get_all_keys(v, full_path))
            elif isinstance(v, list):
                keys[full_path] = "list"
                if v and isinstance(v[0], dict):
                    keys.update(get_all_keys(v[0], f"{full_path}[]"))
    return keys


def compare_structures(generated: dict, template: dict) -> dict:
    """
    Compare two JSON structures and return categorized issues.
    """
    gen_keys = get_all_keys(generated)
    tpl_keys = get_all_keys(template)

    gen_paths = set(gen_keys.keys())
    tpl_paths = set(tpl_keys.keys())

    missing = sorted(tpl_paths - gen_paths)
    extra = sorted(gen_paths - tpl_paths)

    # Type mismatches
    type_mismatches = []
    common = gen_paths & tpl_paths
    for path in sorted(common):
        gen_type = gen_keys[path]
        tpl_type = tpl_keys[path]
        normalize = {"int": "number", "float": "number", "NoneType": "null", "bool": "bool"}
        g = normalize.get(gen_type, gen_type)
        t = normalize.get(tpl_type, tpl_type)
        if g != t:
            type_mismatches.append(f"{path}: generated={gen_type}, template={tpl_type}")

    # Case mismatches
    case_mismatches = []
    missing_lower = {p.lower(): p for p in missing}
    extra_lower = {p.lower(): p for p in extra}
    for lower_key in set(missing_lower.keys()) & set(extra_lower.keys()):
        case_mismatches.append(
            f"template='{missing_lower[lower_key]}' vs generated='{extra_lower[lower_key]}'"
        )

    return {
        "missing_from_generated": missing,
        "extra_in_generated": extra,
        "type_mismatches": type_mismatches,
        "case_mismatches": case_mismatches,
    }


def print_section(title: str, items: list, max_show: int = 30):
    """Print a labeled section of issues."""
    if not items:
        print(f"\n  [PASS] {title}: None")
        return
    print(f"\n  [FAIL] {title} ({len(items)}):")
    for item in items[:max_show]:
        print(f"      - {item}")
    if len(items) > max_show:
        print(f"      ... and {len(items) - max_show} more")


def deep_value_check(generated: dict, template: dict, path: str = "") -> list:
    """
    Check for empty/placeholder values in generated payload where
    the template has meaningful values.
    """
    warnings = []
    if isinstance(template, dict) and isinstance(generated, dict):
        for key in template:
            if key in generated:
                tpl_val = template[key]
                gen_val = generated[key]
                full_path = f"{path}.{key}" if path else key

                if isinstance(tpl_val, dict) and isinstance(gen_val, dict):
                    warnings.extend(deep_value_check(gen_val, tpl_val, full_path))
                elif isinstance(tpl_val, str) and tpl_val and gen_val == "":
                    warnings.append(f"{full_path}: template has value but generated is empty")
                elif isinstance(tpl_val, (int, float)) and gen_val is None:
                    warnings.append(f"{full_path}: template has number but generated is None")
    return warnings


# ============================================================
# MAIN
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="Validate generated payload structure against template")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show extra diagnostics and value warnings")
    parser.add_argument("--no-card", action="store_true", help="Skip card transaction details")
    parser.add_argument("--template", type=str, default=None, help="Path to template JSON")
    parser.add_argument("--dump-keys", action="store_true", help="Dump all key paths for both payloads")
    args = parser.parse_args()

    # Load the working template
    template_path = args.template or os.path.join(os.path.dirname(__file__), "..", "transaction.json")
    try:
        with open(template_path, "r") as f:
            template = json.load(f)
    except FileNotFoundError:
        print(f"ERROR: Template file not found: {template_path}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"ERROR: Invalid JSON in template: {e}")
        sys.exit(1)

    # Generate a payload
    gen = TransactionDataGenerator(tenant_id="facctum", seed=42)
    include_card = not args.no_card

    # Try public methods first, fall back to manual assembly
    generated = None
    generation_method = "unknown"

    if hasattr(gen, "generate_full_payload") and callable(getattr(gen, "generate_full_payload")):
        generated = gen.generate_full_payload(include_card=include_card)
        generation_method = "generate_full_payload()"
    elif hasattr(gen, "generate_batch") and callable(getattr(gen, "generate_batch")):
        batch = gen.generate_batch(1, include_card=include_card)
        generated = batch[0] if batch else None
        generation_method = "generate_batch(1)"
    elif hasattr(gen, "generate_single") and callable(getattr(gen, "generate_single")):
        generated = gen.generate_single(include_card=include_card)
        generation_method = "generate_single()"
    else:
        # Fallback: assemble from private methods
        generated = assemble_payload_from_generator(gen, include_card=include_card)
        generation_method = "assemble_payload_from_generator() [fallback]"

    if not generated:
        print("ERROR: Generator returned empty payload.")
        sys.exit(1)

    # Run comparison
    print("=" * 70)
    print("  STRUCTURAL VALIDATION: Generated Payload vs transaction.json")
    print("=" * 70)
    print(f"\n  Template file : {os.path.abspath(template_path)}")
    print(f"  Generation    : {generation_method}")
    print(f"  Seed          : 42")
    print(f"  Include card  : {include_card}")

    results = compare_structures(generated, template)

    # Print results
    print_section("Case Mismatches (naming convention bugs)", results["case_mismatches"])
    print_section("Type Mismatches (structural bugs)", results["type_mismatches"])
    print_section("Keys in template MISSING from generated payload", results["missing_from_generated"])
    print_section("Extra keys in generated NOT in template (informational)", results["extra_in_generated"])

    # Summary counts
    gen_keys = get_all_keys(generated)
    tpl_keys = get_all_keys(template)
    common_count = len(set(gen_keys.keys()) & set(tpl_keys.keys()))

    print("\n" + "-" * 70)
    print(f"  Template total keys : {len(tpl_keys)}")
    print(f"  Generated total keys: {len(gen_keys)}")
    print(f"  Common keys         : {common_count}")
    print(f"  Coverage            : {common_count}/{len(tpl_keys)} ({100*common_count/max(len(tpl_keys),1):.1f}%)")

    # Critical issues = case mismatches + type mismatches + missing required sections
    critical_issues = len(results["case_mismatches"]) + len(results["type_mismatches"])

    print("\n" + "=" * 70)
    if critical_issues == 0 and not results["missing_from_generated"]:
        print("  RESULT: PASS - Structure fully matches template")
    elif critical_issues == 0:
        print(f"  RESULT: PARTIAL - {len(results['missing_from_generated'])} template keys not yet generated")
        print("  (No critical bugs found, but generator coverage is incomplete)")
    else:
        print(f"  RESULT: FAIL - {critical_issues} critical issues (case/type mismatches)")
    print("=" * 70)

    # Verbose output
    if args.verbose:
        print("\n" + "-" * 70)
        print("  VALUE-LEVEL WARNINGS:")
        print("-" * 70)
        value_warnings = deep_value_check(generated, template)
        if value_warnings:
            for w in value_warnings[:50]:
                print(f"    ! {w}")
            if len(value_warnings) > 50:
                print(f"    ... and {len(value_warnings) - 50} more")
        else:
            print("    None")

    # Dump keys mode
    if args.dump_keys:
        print("\n" + "-" * 70)
        print("  ALL TEMPLATE KEYS:")
        print("-" * 70)
        for k in sorted(tpl_keys.keys()):
            marker = " " if k in gen_keys else "!"
            print(f"  {marker} [{tpl_keys[k]:6s}] {k}")

    # Save sample payload
    sample_path = os.path.join(os.path.dirname(__file__), "results", "sample_generated_payload.json")
    os.makedirs(os.path.dirname(sample_path), exist_ok=True)
    with open(sample_path, "w") as f:
        json.dump(generated, f, indent=2)
    print(f"\n  Sample payload saved: {sample_path}")

    # Exit code
    sys.exit(1 if critical_issues > 0 else 0)


if __name__ == "__main__":
    main()
