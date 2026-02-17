from typing import List, Tuple

def _subsequence_score(typed: str, candidate: str) -> int:
    """
    Count how many typed digits appear in candidate IN ORDER (subsequence).
    Example typed=074, candidate=100740 -> score 3
    """
    i = 0
    for ch in candidate:
        if i < len(typed) and ch == typed[i]:
            i += 1
    return i

def suggest_ids(typed: str, valid_ids: List[str], limit: int = 10) -> List[Tuple[str, float]]:
    typed = "".join([c for c in typed if c.isdigit()])
    if not typed:
        return []

    scored = []
    for vid in valid_ids:
        s = _subsequence_score(typed, vid)
        # also reward exact digit intersection (unordered) a bit
        inter = sum(1 for c in typed if c in vid)
        score = 0.7 * s + 0.3 * inter

        if score > 0:
            scored.append((vid, score))

    scored.sort(key=lambda x: (-x[1], x[0]))
    return scored[:limit]