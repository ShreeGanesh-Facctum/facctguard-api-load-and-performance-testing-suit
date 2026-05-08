"""
Data Generator Module - Transaction Payload Generation
=======================================================
Generates randomized but realistic transaction payloads
matching the EXACT structure expected by the FacctGuard API.

Rules targeted:
  1. HIGH_RISK_COUNTRY - Sender in high-risk country + amount > threshold
  2. HIGH_RISK_CUSTOMER - CustomerRiskRating=HIGH + amount > threshold
  3. HIGH_FREQUENCY_NATURAL_PERSON - Same customer, multiple txns in 3 days
  4. HIGH_AMOUNT_LEGAL_PERSON - Corporate + amount > threshold
  5. HIGH_AMOUNT_NATURAL_PERSON - Individual + amount > threshold
  6. MULTIPLE_ORIGINATORS_SAME_BENEFICIARY - Different senders, same beneficiary in 7 days
"""

from faker import Faker
import random
import uuid
import json
from datetime import datetime, timedelta

fake = Faker()
random.seed(42)

# Countries the FacctGuard engine considers HIGH RISK
HIGH_RISK_COUNTRIES = ["LBY", "AFG", "SYR", "IRN", "IRQ", "TUR"]
LOW_RISK_COUNTRIES = ["ARE", "IND", "USA", "GBR", "SGP"]

FRAUD_RULES = [
    "HIGH_RISK_COUNTRY",
    "HIGH_RISK_CUSTOMER",
    "HIGH_FREQUENCY_NATURAL_PERSON",
    "HIGH_AMOUNT_LEGAL_PERSON",
    "HIGH_AMOUNT_NATURAL_PERSON",
    "MULTIPLE_ORIGINATORS_SAME_BENEFICIARY",
]

BASE_DATE = datetime.now()


def random_date(offset_days=0):
    """Generate a date that is today or in the recent past (up to 7 days ago)."""
    dt = BASE_DATE - timedelta(
        days=random.randint(0, max(offset_days, 7)),
    )
    return dt


# Shared beneficiary for MULTIPLE_ORIGINATORS rule
shared_beneficiaries = [
    {
        "name": "RASHID KHAN",
        "customer_id": "BENF1234006",
        "account_number": "LBY98986100",
        "nationality": "LBY",
        "country": "LBY",
        "bic": "LBYCAAFKAXXX",
    },
    {
        "name": "SADIQ KHAN",
        "customer_id": "BENF1234001",
        "account_number": "NGA989860987",
        "nationality": "USD",
        "country": "USD",
        "bic": "USCAAFKAXXX",
    },
]

# Track frequency customers for HIGH_FREQUENCY rule
frequency_customers = {}


def generate_amount(is_fraud, fraud_type):
    """Generate amount based on rule thresholds."""
    if not is_fraud:
        # Clean transactions: below all thresholds
        return round(random.uniform(500, 45000), 2)

    if fraud_type == "HIGH_RISK_COUNTRY":
        # Threshold: > 100,000 AED
        return round(random.uniform(100002, 300000), 2)

    if fraud_type == "HIGH_RISK_CUSTOMER":
        # Threshold: > 50,000 AED
        return round(random.uniform(50001, 200000), 2)

    if fraud_type == "HIGH_FREQUENCY_NATURAL_PERSON":
        # Each txn > threshold (cumulative matters)
        return round(random.uniform(50000, 100000), 2)

    if fraud_type == "HIGH_AMOUNT_LEGAL_PERSON":
        # Threshold: > 250,000 AED for corporate
        return round(random.uniform(250001, 500000), 2)

    if fraud_type == "HIGH_AMOUNT_NATURAL_PERSON":
        # Threshold: > 99,999 AED for individual
        return round(random.uniform(99999.01, 300000), 2)

    if fraud_type == "MULTIPLE_ORIGINATORS_SAME_BENEFICIARY":
        # Amount per sender (cumulative in a week)
        return round(random.uniform(5000, 50000), 2)

    return round(random.uniform(25000, 150000), 2)


def build_transaction(index, is_fraud=False):
    fraud_type = random.choice(FRAUD_RULES) if is_fraud else None
    txn_date = random_date()
    transaction_id = f"TXN{txn_date.strftime('%Y%m%d%H%M%S')}{index:04d}"

    amount = generate_amount(is_fraud, fraud_type)

    # Determine party type based on rule
    if fraud_type == "HIGH_AMOUNT_LEGAL_PERSON":
        party_type = "Corporate"
    else:
        party_type = "Individual"

    # Determine nationality/country based on rule
    if fraud_type == "HIGH_RISK_COUNTRY":
        ordering_nationality = random.choice(HIGH_RISK_COUNTRIES)
        ordering_country = ordering_nationality
        risk_rating = "Low"  # Country risk is separate from customer risk
    elif fraud_type == "HIGH_RISK_CUSTOMER":
        ordering_nationality = random.choice(HIGH_RISK_COUNTRIES)
        ordering_country = ordering_nationality
        risk_rating = "HIGH"
    else:
        ordering_nationality = random.choice(LOW_RISK_COUNTRIES + ["TUR", "AFG"])
        ordering_country = ordering_nationality
        risk_rating = random.choice(["Low", "MEDIUM"])

    # Customer ID
    ordering_customer_id = f"CUST{random.randint(100000, 999999)}"

    if fraud_type == "HIGH_FREQUENCY_NATURAL_PERSON":
        # Reuse same customer ID to simulate frequency
        ordering_customer_id = f"FREQ{random.randint(1, 5):03d}"
        frequency_customers.setdefault(ordering_customer_id, 0)
        frequency_customers[ordering_customer_id] += 1
        # Use dates within 3 days of each other (recent past)
        txn_date = datetime.now() - timedelta(
            days=random.randint(0, 2),
        )
        transaction_id = f"TXN{txn_date.strftime('%Y%m%d%H%M%S')}{index:04d}"

    # Beneficiary details
    if fraud_type == "MULTIPLE_ORIGINATORS_SAME_BENEFICIARY":
        ben = random.choice(shared_beneficiaries)
        beneficiary_name = ben["name"]
        beneficiary_customer_id = ben["customer_id"]
        beneficiary_account = ben["account_number"]
        beneficiary_nationality = ben["nationality"]
        beneficiary_country = ben["country"]
        beneficiary_bic = ben["bic"]
        # Use dates within 7 days (recent past)
        txn_date = datetime.now() - timedelta(
            days=random.randint(0, 6),
        )
        transaction_id = f"TXN{txn_date.strftime('%Y%m%d%H%M%S')}{index:04d}"
    else:
        beneficiary_name = fake.name().upper()
        beneficiary_customer_id = f"BENF{random.randint(100000, 999999)}"
        beneficiary_account = f"LBY{random.randint(10000000, 99999999)}"
        beneficiary_nationality = random.choice(HIGH_RISK_COUNTRIES + LOW_RISK_COUNTRIES)
        beneficiary_country = beneficiary_nationality
        beneficiary_bic = "LBYCAAFKAXXX"

    # Determine geographic focus
    geo_focus = f"UAE_{beneficiary_country}"

    name = fake.name().upper()

    transaction = {
        "transactionPayment": {
            "InterbankPaymentTransaction": {
                "TransactionHeader": {
                    "TransctionType": "FX",
                    "TransactionSubType": "FOREX RETAIL",
                    "ProcessingDate": txn_date.strftime("%Y-%m-%d %H:%M:%S"),
                },
                "TransactionIdentification": {
                    "TransactionID": transaction_id,
                },
                "BeneficiaryDetails": {
                    "BeneficiaryAccountNumber": beneficiary_account,
                    "BeneficiaryCustomerID": beneficiary_customer_id,
                },
                "OrderingPartyDetails": {
                    "OrderingPartyAccountNumber": f"AE{random.randint(1000000000, 9999999999)}",
                    "OrderingPartyCustomerID": ordering_customer_id,
                },
                "Amount": {
                    "InstructedAmount": {
                        "@Currency": "AED",
                        "cdata": f"{amount:.2f}",
                    },
                },
            },
            "TenantDetails": {"tenant_id": "Facctum"},
            "OrderingParty": {
                "PartyIdentification": {
                    "Name": name,
                    "PartyType": party_type,
                },
                "PersonalDetails": {
                    "Nationality": ordering_nationality,
                    "ResidenceCountry": "ARE",
                    "Occupation": random.choice(
                        ["Construction Supervisor", "Teacher", "Engineer", "Trader", "Business Owner"]
                    ),
                },
                "IdentificationDocuments": {
                    "DocumentType": "Passport",
                    "IssuingCountry": ordering_nationality,
                },
                "AdditionalIdentification": {
                    "DocumentType": "Residence Visa",
                },
                "Address": {
                    "Country": ordering_country,
                },
            },
            "Beneficiary": {
                "PartyIdentification": {
                    "Name": beneficiary_name,
                    "PartyType": "INDIVIDUAL",
                },
                "PersonalDetails": {
                    "Nationality": beneficiary_nationality,
                },
                "IdentificationDocuments": {
                    "DocumentType": "National ID",
                    "IssuingCountry": beneficiary_nationality,
                },
                "Account": {
                    "AccountName": beneficiary_name,
                },
                "Address": {
                    "Country": beneficiary_country,
                },
                "Bank": {
                    "BIC": beneficiary_bic,
                },
            },
            "PaymentDetails": {
                "PaymentPurpose": {
                    "CategoryCode": "PERS",
                },
            },
            "OperationalData": {
                "ChannelInformation": {
                    "ChannelType": random.choice(["MOBILE_BANKING", "INTERNET_BANKING", "BRANCH"]),
                },
            },
            "HistoricalContext": {
                "CustomerProfile": {
                    "GeographicFocus": geo_focus,
                },
            },
            "ComplianceData": {
                "RiskAssessment": {
                    "CustomerRiskRating": risk_rating,
                },
            },
        }
    }

    # expectedOutcome is kept separate for verification, not sent as payload
    transaction["_expectedOutcome"] = {
        "isFraud": is_fraud,
        "triggeredRules": [fraud_type] if fraud_type else [],
    }

    return transaction


def generate_transactions(total_transactions=300, fraud_percentage=40.0):
    """
    Generate a list of transactions with the specified fraud ratio.

    Args:
        total_transactions: Total number of transactions to generate.
        fraud_percentage: Percentage of transactions that should be fraudulent (0-100).

    Returns:
        List of transaction dictionaries.
    """
    if total_transactions <= 0:
        raise ValueError("total_transactions must be greater than 0")
    if fraud_percentage < 0 or fraud_percentage > 100:
        raise ValueError("fraud_percentage must be between 0 and 100")

    fraud_count = int(total_transactions * (fraud_percentage / 100))
    clean_count = total_transactions - fraud_count

    transactions = []

    for i in range(clean_count):
        transactions.append(build_transaction(i + 1, False))

    for i in range(fraud_count):
        transactions.append(build_transaction(clean_count + i + 1, True))

    random.shuffle(transactions)
    return transactions


def validate_payload_structure(payload):
    """Basic structural validation of a generated payload."""
    required_keys = [
        "InterbankPaymentTransaction",
        "TenantDetails",
        "OrderingParty",
        "Beneficiary",
    ]
    if "transactionPayment" not in payload:
        return False
    txn = payload["transactionPayment"]
    return all(k in txn for k in required_keys)


class TransactionDataGenerator:
    """
    Compatibility wrapper class for the load test suite.
    Wraps the module-level functions to maintain the same interface
    used by index.py, test_gen.py, and validate_structure.py.
    """

    def __init__(self, tenant_id="Facctum", seed=None):
        self.tenant_id = tenant_id
        if seed is not None:
            Faker.seed(seed)
            random.seed(seed)

    def generate_batch(self, count, include_card=False, fraud_percentage=40.0):
        """
        Generate a batch of transaction payloads.

        Args:
            count: Number of transactions to generate.
            include_card: Ignored (kept for API compatibility).
            fraud_percentage: Percentage of fraud transactions.

        Returns:
            List of transaction dictionaries.
        """
        return generate_transactions(
            total_transactions=count, fraud_percentage=fraud_percentage
        )


# =============================
# STANDALONE EXECUTION
# =============================
if __name__ == "__main__":
    # =============================
    # CONFIGURATION
    # =============================
    total_transactions = 300
    fraud_percentage = 40.0

    fraud_count = int(total_transactions * (fraud_percentage / 100))
    clean_count = total_transactions - fraud_count

    print(f"Generating {total_transactions} transactions...")
    print("Execution Mode: Non-interactive")
    print(f"Fraud Transactions: {fraud_count}")
    print(f"Clean Transactions: {clean_count}")

    transactions = generate_transactions(total_transactions, fraud_percentage)

    output_file = f"facctum_{total_transactions}_transactions.json"
    with open(output_file, "w") as f:
        json.dump(transactions, f, indent=2)

    print(f"Generated {len(transactions)} transactions")
    print(f"Fraud Transactions: {fraud_count}")
    print(f"Clean Transactions: {clean_count}")
    print(f"Output File: {output_file}")
