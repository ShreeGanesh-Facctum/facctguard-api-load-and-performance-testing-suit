import sys, json
sys.path.insert(0, '.')
from modules.data_generator import TransactionDataGenerator

gen = TransactionDataGenerator(seed=42)
batch = gen.generate_batch(10, fraud_percentage=60)

frauds = [p for p in batch if p['_expectedOutcome']['isFraud']]
print(f"Fraud count: {len(frauds)}")
print()

for p in frauds:
    rule = p['_expectedOutcome']['triggeredRules'][0]
    amt = p['transactionPayment']['InterbankPaymentTransaction']['Amount']['InstructedAmount']['cdata']
    party = p['transactionPayment']['OrderingParty']['PartyIdentification']['PartyType']
    risk = p['transactionPayment']['ComplianceData']['RiskAssessment']['CustomerRiskRating']
    country = p['transactionPayment']['OrderingParty']['Address']['Country']
    print(f"  {rule}")
    print(f"    Amount={amt} AED, PartyType={party}, Risk={risk}, Country={country}")
    print()
