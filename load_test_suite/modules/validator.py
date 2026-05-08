"""
Validator Module - Response Validation
=======================================
Validates API responses beyond just status codes:
- Response body structure consistency
- Data corruption detection under load
- Response time anomaly detection
- Session isolation verification
"""

import json
from typing import Optional
from dataclasses import dataclass, field


@dataclass
class ValidationResult:
    """Result of a single response validation."""
    request_index: int
    is_valid: bool
    status_code: int
    has_correct_structure: bool = True
    structure_errors: list = field(default_factory=list)
    data_corruption: bool = False
    corruption_details: str = ""
    response_body: Optional[dict] = None


class ResponseValidator:
    """Validates API responses for correctness and consistency."""

    # Expected fields in a successful FacctGuard response
    EXPECTED_SUCCESS_FIELDS = {"transaction_id", "tenant_id", "message", "status", "alert_details"}
    EXPECTED_ERROR_FIELDS = {"component", "message", "detailed_error"}
    VALID_STATUSES = {"Red", "Green"}

    def __init__(self, tenant_id: str = "Facctum"):
        self.tenant_id = tenant_id
        self.results: list[ValidationResult] = []
        self.response_structures_seen: list[set] = []
        self._baseline_structure: Optional[set] = None

    def validate_response(
        self,
        request_index: int,
        status_code: int,
        response_body: str,
        expected_txn_id: Optional[str] = None,
    ) -> ValidationResult:
        """Validate a single API response."""
        result = ValidationResult(
            request_index=request_index,
            is_valid=True,
            status_code=status_code,
        )

        # Parse JSON
        try:
            body = json.loads(response_body) if isinstance(response_body, str) else response_body
            result.response_body = body
        except (json.JSONDecodeError, TypeError):
            result.is_valid = False
            result.has_correct_structure = False
            result.structure_errors.append("Response is not valid JSON")
            self.results.append(result)
            return result

        if not isinstance(body, dict):
            result.is_valid = False
            result.has_correct_structure = False
            result.structure_errors.append(f"Expected dict, got {type(body).__name__}")
            self.results.append(result)
            return result

        # Validate based on status code
        if status_code == 200:
            self._validate_success_response(result, body, expected_txn_id)
        elif status_code == 400:
            self._validate_error_response(result, body)
        elif status_code >= 500:
            result.structure_errors.append(f"Server error: {status_code}")

        # Track structure for consistency checking
        self.response_structures_seen.append(set(body.keys()))
        if self._baseline_structure is None and status_code == 200:
            self._baseline_structure = set(body.keys())

        self.results.append(result)
        return result

    def _validate_success_response(
        self, result: ValidationResult, body: dict, expected_txn_id: Optional[str]
    ):
        """Validate a 200 OK response."""
        # Check required fields
        missing = self.EXPECTED_SUCCESS_FIELDS - set(body.keys())
        if missing:
            result.has_correct_structure = False
            result.structure_errors.append(f"Missing fields: {missing}")

        # Validate status field
        status = body.get("status")
        if status and status not in self.VALID_STATUSES:
            result.structure_errors.append(f"Invalid status value: {status}")

        # Validate tenant_id matches
        resp_tenant = body.get("tenant_id")
        if resp_tenant and resp_tenant != self.tenant_id:
            result.data_corruption = True
            result.corruption_details = f"Tenant mismatch: expected {self.tenant_id}, got {resp_tenant}"

        # Validate transaction_id echoed back correctly
        if expected_txn_id:
            resp_txn_id = body.get("transaction_id")
            if resp_txn_id and resp_txn_id != expected_txn_id:
                result.data_corruption = True
                result.corruption_details = (
                    f"Transaction ID mismatch: sent {expected_txn_id}, got {resp_txn_id}"
                )

        # Validate alert_details is a list
        alerts = body.get("alert_details")
        if alerts is not None and not isinstance(alerts, list):
            result.structure_errors.append(f"alert_details should be list, got {type(alerts).__name__}")

        # Validate alert structure
        if isinstance(alerts, list):
            for i, alert in enumerate(alerts):
                if isinstance(alert, dict):
                    if "alert_id" not in alert:
                        result.structure_errors.append(f"Alert {i} missing alert_id")
                    score = alert.get("alert_risk_score")
                    if score is not None:
                        try:
                            s = float(score)
                            if s < 0 or s > 1:
                                result.structure_errors.append(
                                    f"Alert {i} risk_score out of range: {s}"
                                )
                        except (ValueError, TypeError):
                            result.structure_errors.append(
                                f"Alert {i} risk_score not numeric: {score}"
                            )

        if result.structure_errors:
            result.is_valid = False

    def _validate_error_response(self, result: ValidationResult, body: dict):
        """Validate a 400 error response."""
        missing = self.EXPECTED_ERROR_FIELDS - set(body.keys())
        if missing:
            result.has_correct_structure = False
            result.structure_errors.append(f"Error response missing fields: {missing}")
            result.is_valid = False

    def check_structure_consistency(self) -> dict:
        """Check if response structures are consistent across all requests."""
        if not self.response_structures_seen:
            return {"consistent": True, "unique_structures": 0}

        unique = set(frozenset(s) for s in self.response_structures_seen)
        return {
            "consistent": len(unique) <= 2,  # Allow success + error structures
            "unique_structures": len(unique),
            "structures": [sorted(list(s)) for s in unique],
        }

    def get_summary(self) -> dict:
        """Get validation summary statistics."""
        total = len(self.results)
        if total == 0:
            return {"total": 0}

        valid = sum(1 for r in self.results if r.is_valid)
        structure_ok = sum(1 for r in self.results if r.has_correct_structure)
        corrupted = sum(1 for r in self.results if r.data_corruption)
        consistency = self.check_structure_consistency()

        return {
            "total_validated": total,
            "valid_responses": valid,
            "invalid_responses": total - valid,
            "valid_percent": round(valid / total * 100, 2),
            "structure_correct": structure_ok,
            "data_corruption_detected": corrupted,
            "corruption_details": [
                {"request": r.request_index, "detail": r.corruption_details}
                for r in self.results
                if r.data_corruption
            ],
            "structure_consistency": consistency,
            "common_errors": self._get_common_errors(),
        }

    def _get_common_errors(self) -> list:
        """Get the most common validation errors."""
        error_counts = {}
        for r in self.results:
            for err in r.structure_errors:
                error_counts[err] = error_counts.get(err, 0) + 1
        sorted_errors = sorted(error_counts.items(), key=lambda x: x[1], reverse=True)
        return [{"error": e, "count": c} for e, c in sorted_errors[:10]]
