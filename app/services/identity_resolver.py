from __future__ import annotations
from dataclasses import dataclass
from typing import List, Tuple, Dict, Any
from rapidfuzz import process, fuzz


# --------------------------------------------------
# Candidate container
# --------------------------------------------------
@dataclass
class Candidate:
    emp_id: str
    name_original: str
    name_clean: str
    name_score: float
    number_score: float
    total_score: float


# --------------------------------------------------
# Helpers
# --------------------------------------------------
def _num_similarity(ocr_num: str, emp_id: str) -> float:
    return float(fuzz.ratio(ocr_num, emp_id))


# --------------------------------------------------
# Main resolver
# --------------------------------------------------
def resolve_identity(
    number_candidates: List[str],
    ocr_name_clean: str,
    dept_records: List[Tuple[str, str, str]],  # (id, name_clean, name_original)
    min_name_score: float = 75.0,
    min_total_score: float = 70.0,
    min_margin: float = 4.0,
) -> Dict[str, Any]:
    """
    Returns:
      {
        "resolved_id": Optional[str],
        "confidence": float,
        "method": str,
        "top_candidates": List[dict]
      }
    """

    id_to_nameclean = {emp_id: name_clean for emp_id, name_clean, _ in dept_records}
    valid_ids = set(id_to_nameclean.keys())

    # ==================================================
    # 1) NUMBER-FIRST LOGIC (always preferred)
    # ==================================================
    for c in number_candidates:
        if c in valid_ids:

            if ocr_name_clean:
                expected = id_to_nameclean[c]
                score = float(fuzz.token_sort_ratio(ocr_name_clean, expected))

                if score >= min_name_score:
                    return {
                        "resolved_id": c,
                        "confidence": min(100.0, 60.0 + 0.4 * score),
                        "method": "number+name_verify",
                        "top_candidates": []
                    }

                return {
                    "resolved_id": c,
                    "confidence": 85.0,
                    "method": "number_only_name_mismatch",
                    "top_candidates": []
                }

            return {
                "resolved_id": c,
                "confidence": 85.0,
                "method": "number_only",
                "top_candidates": []
            }

    # ==================================================
    # 1B) FUZZY NUMBER RECOVERY (when exact number fails)
    # ==================================================
    if number_candidates:
        all_ids = list(valid_ids)

        for ocr_num in number_candidates:

            top_nums = process.extract(
                ocr_num,
                all_ids,
                scorer=fuzz.ratio,
                limit=2
            )

            if not top_nums:
                continue

            best_id, best_score, _ = top_nums[0]
            second_score = top_nums[1][1] if len(top_nums) > 1 else 0

            margin = best_score - second_score

            # Accept strong fuzzy number match
            if best_score >= 80 and margin >= 5:
                return {
                    "resolved_id": best_id,
                    "confidence": best_score,
                    "method": "number_fuzzy_recovery",
                    "top_candidates": [
                        {"emp_id": best_id, "number_score": best_score}
                    ]
                }



    # ==================================================
    # 2) NAME-BASED RECOVERY
    # ==================================================
    if not ocr_name_clean:
        return {
            "resolved_id": None,
            "confidence": 0.0,
            "method": "no_number_no_name",
            "top_candidates": []
        }

    names_list = [name_clean for _, name_clean, _ in dept_records]

    top = process.extract(
        ocr_name_clean,
        names_list,
        scorer=fuzz.token_sort_ratio,
        limit=5
    )

    candidates: List[Candidate] = []

    for matched_name, name_score, _ in top:

        for emp_id, name_clean, name_orig in dept_records:
            if name_clean != matched_name:
                continue

            best_num_score = 0.0
            if number_candidates:
                best_num_score = max(
                    _num_similarity(nc, emp_id) for nc in number_candidates
                )

            total = 0.65 * float(name_score) + 0.35 * float(best_num_score)

            candidates.append(
                Candidate(
                    emp_id=emp_id,
                    name_original=name_orig,
                    name_clean=name_clean,
                    name_score=float(name_score),
                    number_score=float(best_num_score),
                    total_score=float(total),
                )
            )

    if not candidates:
        return {
            "resolved_id": None,
            "confidence": 0.0,
            "method": "name_no_candidates",
            "top_candidates": []
        }

    candidates.sort(key=lambda x: x.total_score, reverse=True)

    best = candidates[0]
    second = candidates[1] if len(candidates) > 1 else None
    margin = best.total_score - (second.total_score if second else 0.0)

    top_out = [
        {
            "emp_id": c.emp_id,
            "name_original": c.name_original,
            "name_score": c.name_score,
            "number_score": c.number_score,
            "total_score": c.total_score,
        }
        for c in candidates[:5]
    ]

    # ==================================================
    # 3) STRONG NAME-ONLY MATCH (SAFE)
    # ==================================================
    # Accept ONLY if clearly better than others (no duplicates risk)

    if best.name_score >= 90 and (second is None or best.name_score - second.name_score >= 5):
        return {
            "resolved_id": best.emp_id,
            "confidence": best.name_score,
            "method": "name_only_strong_match",
            "top_candidates": top_out
        }

    # ==================================================
    # 4) COMBINED SCORE ACCEPTANCE
    # ==================================================
    if best.total_score >= min_total_score and margin >= min_margin:
        return {
            "resolved_id": best.emp_id,
            "confidence": min(100.0, best.total_score),
            "method": "name_recovery",
            "top_candidates": top_out
        }

    # ==================================================
    # 5) AMBIGUOUS
    # ==================================================
    return {
        "resolved_id": None,
        "confidence": min(100.0, best.total_score),
        "method": "ambiguous_manual_review",
        "top_candidates": top_out
    }