from __future__ import annotations

from typing import Any

from rapidfuzz import fuzz

from apps.employees.models import Employee


def clean_id(raw_id: str) -> str:
    """Strip SA prefix, return 6-digit string or empty."""
    cleaned = raw_id.strip().upper().lstrip("SA").strip()
    return cleaned if cleaned.isdigit() and len(cleaned) == 6 else ""


def get_employee_type(clean_id: str) -> str:
    """Determine employee or contractor from first digit."""
    if not clean_id:
        return "unknown"
    return "employee" if clean_id.startswith("1") else "contractor"


def match_row(ocr_name: str, ocr_id_raw: str) -> dict[str, Any]:
    """
    Score formula:
      name_score  = token_sort_ratio on lowercased names (case-insensitive)
      id_score    = rapidfuzz.fuzz.ratio(clean_id, candidate_id)
      total_score = (name_score * 0.65) + (id_score * 0.35)

    Resolution:
      total_score >= 85  → auto_resolved
      total_score < 85   → ambiguous_manual_review
      id exact match but name_score < 60 → number_only_name_mismatch (flag for review)

    Returns top 5 candidates + recommended resolution.
    """
    ocr_name = (ocr_name or "").strip()
    ocr_name_lower = ocr_name.lower()
    raw_id = (ocr_id_raw or "").strip()
    cid = clean_id(raw_id)
    emp_type = get_employee_type(cid)

    qs = Employee.objects.all()
    if emp_type in ("employee", "contractor"):
        qs = qs.filter(type=emp_type)

    candidates: list[dict[str, Any]] = []
    for e in qs.only("employee_id", "full_name", "type"):
        cand_id = str(e.employee_id or "")
        cand_name = str(e.full_name or "")
        cand_name_lower = cand_name.lower()

        name_score = (
            fuzz.token_sort_ratio(ocr_name_lower, cand_name_lower)
            if ocr_name and cand_name
            else 0.0
        )
        id_score = fuzz.ratio(cid, cand_id) if cid and cand_id else 0.0
        total = (name_score * 0.65) + (id_score * 0.35)

        candidates.append(
            {
                "employee_id": cand_id,
                "full_name": cand_name,
                "type": e.type,
                "name_score": float(name_score),
                "id_score": float(id_score),
                "total_score": float(total),
            }
        )

    candidates.sort(key=lambda x: x["total_score"], reverse=True)
    top5 = candidates[:5]

    best = top5[0] if top5 else None
    best_total = float(best["total_score"]) if best else 0.0
    best_name_score = float(best["name_score"]) if best else 0.0
    best_id = str(best["employee_id"]) if best else ""

    match_method = ""
    recommended_status = "needs_review"

    # Special case: exact ID match but name mismatch => always review.
    if cid and best_id and cid == best_id and best_name_score < 60:
        recommended_status = "needs_review"
        match_method = "number_only_name_mismatch"
    elif best_total >= 85:
        recommended_status = "auto_resolved"
        match_method = "auto_resolved"
    else:
        recommended_status = "needs_review"
        match_method = "ambiguous_manual_review"

    return {
        "clean_id": cid,
        "employee_type": emp_type,
        "top_candidates": [
            {
                "employee_id": c["employee_id"],
                "full_name": c["full_name"],
                "type": c["type"],
                "name_score": c["name_score"],
                "id_score": c["id_score"],
                "total_score": c["total_score"],
            }
            for c in top5
        ],
        "confidence": best_total,
        "match_method": match_method,
        "recommended_status": recommended_status,
        "best_employee_id": best_id or None,
    }

