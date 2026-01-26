from typing import List, Optional, Tuple
import re

from app.services.mock_db import EMPLOYEE_IDS


# -----------------------------
# Utilities
# -----------------------------

def normalize_id(text: str) -> str:
    """
    Normalize OCR text:
    - remove non-digits
    - strip leading C (for contractors)
    """

    text = text.upper().strip()

    if text.startswith("C"):
        text = text[1:]

    digits = re.sub(r"\D", "", text)

    return digits


def edit_distance(a: str, b: str) -> int:
    """
    Simple Levenshtein distance (manual for speed & no deps)
    """
    dp = [[0] * (len(b) + 1) for _ in range(len(a) + 1)]

    for i in range(len(a) + 1):
        dp[i][0] = i
    for j in range(len(b) + 1):
        dp[0][j] = j

    for i in range(1, len(a) + 1):
        for j in range(1, len(b) + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            dp[i][j] = min(
                dp[i - 1][j] + 1,
                dp[i][j - 1] + 1,
                dp[i - 1][j - 1] + cost
            )

    return dp[-1][-1]


def prefix_bonus(candidate: str, real_id: str) -> int:
    """
    Reward correct prefix matches (important business rule)
    """

    bonus = 0

    if candidate[:1] == real_id[:1]:
        bonus += 1

    if candidate[:2] == real_id[:2]:
        bonus += 1

    if candidate[:3] == real_id[:3]:
        bonus += 2   # strongest weight

    return bonus


# -----------------------------
# Resolver
# -----------------------------

def resolve_row(candidates: List[str]) -> Optional[Tuple[str, float]]:
    best_id = None
    best_confidence = 0.0

    for raw in candidates:
        cand = normalize_id(raw)

        if len(cand) != 6:
            continue

        for real_id in EMPLOYEE_IDS:

            dist = edit_distance(cand, real_id)

            # Base confidence from edit distance
            base_conf = 1 - (dist / 6)

            # Prefix bonus (soft)
            bonus = prefix_bonus(cand, real_id) * 0.05

            confidence = base_conf + bonus
            confidence = min(1.0, max(0.0, confidence))

            if confidence > best_confidence:
                best_confidence = confidence
                best_id = real_id

    if best_id is None:
        return None

    return best_id, best_confidence



def resolve_all(rows: List[List[str]]) -> List[Optional[Tuple[str, float]]]:
    return [resolve_row(r) for r in rows]