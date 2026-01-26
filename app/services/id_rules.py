import re
from typing import List


def is_valid_employee_id(digits: str) -> bool:
    """
    Business rule validation only.
    No correction. No guessing.
    """

    if not re.fullmatch(r"\d{6}", digits):
        return False

    # Contractor
    if digits.startswith("9"):
        return True

    # Regular employee
    if digits[0] == "1" and digits[1] == "0" and digits[2] in ("0", "1", "2"):
        return True

    return False


def filter_candidates(candidates: List[str]) -> List[str]:
    """
    Keep only IDs that match business rules.
    """

    return [
        c for c in candidates
        if is_valid_employee_id(c)
    ]