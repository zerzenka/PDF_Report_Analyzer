from rapidfuzz import process, fuzz
from typing import List, Optional, Tuple


def resolve_with_db(
    ocr_candidates: List[str],
    valid_ids: List[str],
    score_cutoff: int = 75
) -> Optional[Tuple[str, float]]:

    if not ocr_candidates:
        return None

    best_match = None
    best_score = 0

    for candidate in ocr_candidates:
        match, score, _ = process.extractOne(
            candidate,
            valid_ids,
            scorer=fuzz.ratio
        )

        if score > best_score:
            best_score = score
            best_match = match

    if best_score >= score_cutoff:
        return best_match, best_score / 100

    return None