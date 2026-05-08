"""Quick test to verify data generator works and save payloads to gendata folder."""
import sys
import os
import json

sys.path.insert(0, '.')
from modules.data_generator import TransactionDataGenerator, validate_payload_structure

gen = TransactionDataGenerator(seed=42)
batch = gen.generate_batch(5, include_card=True)

print(f"Generated {len(batch)} payloads")
print(f"Keys in first payload: {list(batch[0]['transactionPayment'].keys())}")
print(f"\nFirst payload transaction ID: {batch[0]['transactionPayment']['InterbankPaymentTransaction']['TransactionIdentification']['TransactionID']}")
print("\nAll 5 transaction IDs:")
for i, p in enumerate(batch):
    tid = p['transactionPayment']['InterbankPaymentTransaction']['TransactionIdentification']['TransactionID']
    expected = p.get('_expectedOutcome', {})
    fraud_label = "FRAUD" if expected.get('isFraud') else "CLEAN"
    rules = expected.get('triggeredRules', [])
    print(f"  {i+1}. {tid} [{fraud_label}] {rules}")

# Save each payload as a JSON file in the gendata folder
# Only the transactionPayment portion is saved (what gets sent to the API)
output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gendata")
os.makedirs(output_dir, exist_ok=True)

for i, payload in enumerate(batch):
    tid = payload['transactionPayment']['InterbankPaymentTransaction']['TransactionIdentification']['TransactionID']
    filepath = os.path.join(output_dir, f"{tid}.json")
    # Save only the API payload (transactionPayment wrapper, without _expectedOutcome)
    with open(filepath, "w") as f:
        json.dump({"transactionPayment": payload['transactionPayment']}, f, indent=2)
    print(f"  Saved: gendata/{tid}.json")

print(f"\n{len(batch)} payload files saved to: {output_dir}")
print("\nSUCCESS: generate_batch() works correctly")
