from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterable

from django.conf import settings

if TYPE_CHECKING:
    from PIL.Image import Image as PILImage


@dataclass(frozen=True)
class _AzureWord:
    idx: int
    text: str
    polygon: tuple[float, float, float, float, float, float, float, float]  # 4 points x/y

    @property
    def x_left(self) -> float:
        return float(self.polygon[0])

    @property
    def y_top(self) -> float:
        return float(self.polygon[1])

    @property
    def x_right(self) -> float:
        return float(max(self.polygon[0], self.polygon[2], self.polygon[4], self.polygon[6]))

    @property
    def y_center(self) -> float:
        ys = (self.polygon[1], self.polygon[3], self.polygon[5], self.polygon[7])
        return float(sum(ys) / 4.0)

    @property
    def y_bottom(self) -> float:
        return float(max(self.polygon[1], self.polygon[3], self.polygon[5], self.polygon[7]))

    @property
    def height(self) -> float:
        return self.y_bottom - self.y_top


def _iter_page_words(azure_result: dict, page_index: int = 0) -> Iterable[_AzureWord]:
    pages = azure_result.get("pages") or []
    if page_index >= len(pages):
        return
    page = pages[page_index] or {}
    for idx, w in enumerate(page.get("words") or []):
        text = str(w.get("content") or "").strip()
        poly = w.get("polygon") or []
        if not text or len(poly) < 8:
            continue
        poly8 = tuple(float(poly[i]) for i in range(8))
        yield _AzureWord(idx=idx, text=text, polygon=poly8)  # type: ignore[arg-type]


def _clean_id_digits(raw: str) -> str:
    """
    Clean the extracted ID per spec:
    - strip SA / SAC / SALG / SAID prefixes (in practice: keep digits only)
    - remove spaces (e.g. "100 740" -> "100740")
    - return 6 digits if valid, else empty
    """
    raw = (raw or "").strip()
    # Remove everything up to the first digit, then remove spaces.
    digits_only = re.sub(r"^[^0-9]+", "", raw)
    digits_only = re.sub(r"\s+", "", digits_only)
    return digits_only if len(digits_only) == 6 and digits_only.isdigit() else ""


def _digits_only(raw: str) -> str:
    # keep only digits (used for concatenating split tokens)
    return re.sub(r"[^0-9]", "", raw or "")


def _word_inch_bbox(w: _AzureWord) -> tuple[float, float, float, float]:
    xs = (w.polygon[0], w.polygon[2], w.polygon[4], w.polygon[6])
    ys = (w.polygon[1], w.polygon[3], w.polygon[5], w.polygon[7])
    return min(xs), min(ys), max(xs), max(ys)


def _union_inch_bbox(words: list[_AzureWord]) -> tuple[float, float, float, float] | None:
    if not words:
        return None
    bbs = [_word_inch_bbox(w) for w in words]
    return (
        min(b[0] for b in bbs),
        min(b[1] for b in bbs),
        max(b[2] for b in bbs),
        max(b[3] for b in bbs),
    )


def _cap_inch_bbox_height_from_bottom(
    bbox: tuple[float, float, float, float],
    max_height_inches: float,
) -> tuple[float, float, float, float]:
    """If union box is taller than ``max_height_inches``, clip from the bottom (lower max_y)."""
    min_x, min_y, max_x, max_y = bbox
    h = max_y - min_y
    if h <= max_height_inches:
        return bbox
    return (min_x, min_y, max_x, min_y + max_height_inches)


def _inch_bbox_to_crop_pixels(
    inch_bbox: tuple[float, float, float, float],
    dpi: float,
    img_w: int,
    img_h: int,
    pad_px: int = 10,
) -> tuple[int, int, int, int] | None:
    """Azure polygons are in inches; pixel = inch * DPI. Add padding in pixels."""
    min_x, min_y, max_x, max_y = inch_bbox
    x0 = math.floor(min_x * dpi - pad_px)
    y0 = math.floor(min_y * dpi - pad_px)
    x1 = math.ceil(max_x * dpi + pad_px)
    y1 = math.ceil(max_y * dpi + pad_px)
    x0 = max(0, min(x0, img_w - 1))
    y0 = max(0, min(y0, img_h - 1))
    x1 = max(x0 + 1, min(x1, img_w))
    y1 = max(y0 + 1, min(y1, img_h))
    if x1 <= x0 or y1 <= y0:
        return None
    return (x0, y0, x1, y1)


def _render_pdf_page1_pil(pdf_path: str, dpi: float = 200):
    """Render first PDF page to a PIL RGB image at ``dpi`` (default 200)."""
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(pdf_path)
    if len(pdf) < 1:
        pdf.close()
        raise ValueError("PDF has no pages to render.")
    page = pdf[0]
    scale = dpi / 72.0
    bitmap = page.render(scale=scale)
    try:
        pil_image = bitmap.to_pil()
    finally:
        closer = getattr(bitmap, "close", None)
        if callable(closer):
            closer()
        pdf.close()
    if pil_image.mode != "RGB":
        pil_image = pil_image.convert("RGB")
    return pil_image


def _save_crop_png(
    page_img: "PILImage",
    crop_box: tuple[int, int, int, int],
    job_id: str,
    row_index: int,
    kind: str,
) -> str:
    """Write PNG under MEDIA_ROOT/crops/ and return path relative to MEDIA_ROOT."""
    crops_dir = Path(settings.MEDIA_ROOT) / "crops"
    crops_dir.mkdir(parents=True, exist_ok=True)
    fname = f"{job_id}_row{row_index}_{kind}.png"
    out_path = crops_dir / fname
    page_img.crop(crop_box).save(out_path, "PNG")
    return f"crops/{fname}"


def _find_task_leader_anchor(words: list[_AzureWord]) -> _AzureWord | None:
    """Locate the printed ``Task Leader`` label (single phrase or adjacent tokens)."""
    for w in words:
        if w.text.strip().lower().replace(" ", "") == "taskleader":
            return w
        if "task" in w.text.strip().lower() and "leader" in w.text.strip().lower():
            return w

    for w in words:
        if w.text.strip().upper() != "TASK":
            continue
        for w2 in words:
            if w2.text.strip().upper() != "LEADER":
                continue
            if abs(w2.y_center - w.y_center) > 0.25:
                continue
            if w2.x_left < w.x_left:
                continue
            if (w2.x_left - w.x_right) > 0.55:
                continue
            return w2
    return None


def _find_header_said_label(band: list[_AzureWord], *, max_x: float = 10.0) -> _AzureWord | None:
    """``SA ID`` label in the DATE/TIME header band (not the team-member table)."""
    for w in band:
        if w.x_left > max_x:
            continue
        tt = w.text.strip().upper().replace(" ", "")
        if "SAID" in tt or tt == "ID":
            return w

    for w in band:
        if w.text.strip().upper() != "SA" or w.x_left > max_x:
            continue
        for w2 in band:
            if w2.text.strip().upper() != "ID":
                continue
            if abs(w2.y_center - w.y_center) > 0.18:
                continue
            if not (0.0 < (w2.x_left - w.x_right) < 0.45):
                continue
            return w2
    return None


def _extract_id_from_band(
    id_band: list[_AzureWord],
    label: _AzureWord,
    used_id_word_idxs: set[int],
) -> tuple[str, str, list[_AzureWord]]:
    """Reuse table-row ID logic for a single SA ID label in ``id_band``."""
    pool = [
        w
        for w in id_band
        if w.idx not in used_id_word_idxs
        and any(ch.isdigit() for ch in w.text)
        and (
            (w.x_left > label.x_left)
            or (
                (0.0 < (w.y_center - label.y_center) <= 0.35)
                and (w.x_left > label.x_left)
            )
        )
    ]
    pool.sort(key=lambda w: (w.x_left, abs(w.y_center - label.y_center)))

    best: tuple[set[int], str, float, float] | None = None
    for i, w in enumerate(pool):
        if w.idx in used_id_word_idxs:
            continue
        digits = _digits_only(w.text)
        if not digits:
            continue
        used = {w.idx}
        x0 = w.x_left
        yc = w.y_center

        for nxt in pool[i + 1 : i + 6]:
            if nxt.idx in used_id_word_idxs:
                continue
            if abs(nxt.y_center - yc) > 0.15:
                continue
            if (nxt.x_left - x0) > 1.2:
                break
            d2 = _digits_only(nxt.text)
            if not d2:
                continue
            digits += d2
            used.add(nxt.idx)
            if len(digits) >= 6:
                break

        if len(digits) == 6:
            best = (used, digits, x0, yc)
            break

        single = _clean_id_digits(w.text)
        if single:
            best = ({w.idx}, single, x0, yc)
            break

    if not best:
        return "", "", []

    used_idxs, digits6, *_ = best
    used_id_word_idxs.update(used_idxs)
    id_words = [w for w in pool if w.idx in used_idxs]
    return digits6, digits6, id_words


def _detect_task_leader_row(
    words: list[_AzureWord],
    used_id_word_idxs: set[int],
) -> dict[str, Any] | None:
    """
    Task Leader + SA ID in the header (DATE & TIME / SHIFT band), above the team table.

    Returns a row dict with ``row_index=-1``, ``is_task_leader=True``, or None.
    """
    anchor = _find_task_leader_anchor(words)
    if anchor is None:
        return None

    y_slack = 0.18
    y_name_slack = 0.14
    # Header only — team table starts around y > 6.0 on the right side.
    header_band = [
        w
        for w in words
        if abs(w.y_center - anchor.y_center) <= y_slack and w.y_top < 5.5
    ]
    header_band.sort(key=lambda w: (w.x_left, w.y_center))

    id_label = _find_header_said_label(header_band, max_x=10.0)

    name_x_min = max(1.25, anchor.x_right + 0.05)
    name_x_max = 4.25
    if id_label is not None:
        name_x_max = min(name_x_max, id_label.x_left - 0.08)

    exclude_tl = {
        "TASK",
        "LEADER",
        "SA",
        "ID",
        "SAID",
        "SIGNATURE",
        "DATE",
        "TIME",
        "SHIFT",
        "SIGN",
        "PRINTED",
        "SAMPLING",
        "FURNACE",
        "TITLE",
    }

    name_tokens: list[str] = []
    name_words: list[_AzureWord] = []
    for w in header_band:
        if abs(w.y_center - anchor.y_center) > y_name_slack:
            continue
        if not (name_x_min <= w.x_left <= name_x_max):
            continue
        t = w.text.strip()
        if not t:
            continue
        tu = t.upper().replace(" ", "").replace("/", "").replace(".", "")
        if tu in exclude_tl or any(ex in tu for ex in ("NO", "TITLE", "SOP")):
            continue
        if len(t) == 1 and t.isalpha():
            continue
        if any(ch.isdigit() for ch in t):
            continue
        if "/" in t or "." in t:
            continue
        name_tokens.append(t)
        name_words.append(w)
    ocr_name_raw = " ".join(name_tokens).strip()

    ocr_id_raw = ""
    ocr_id_clean = ""
    id_words: list[_AzureWord] = []
    if id_label is not None:
        id_band = [
            w
            for w in words
            if abs(w.y_center - id_label.y_center) <= (y_slack + 0.12)
            and w.y_top < 5.5
        ]
        ocr_id_raw, ocr_id_clean, id_words = _extract_id_from_band(
            id_band, id_label, used_id_word_idxs
        )

    if not ocr_name_raw.strip() and not ocr_id_raw.strip():
        return None

    return {
        "row_index": -1,
        "is_task_leader": True,
        "ocr_name_raw": ocr_name_raw,
        "ocr_id_raw": ocr_id_raw,
        "ocr_id_clean": ocr_id_clean,
        "_name_words": name_words,
        "_id_words": id_words,
    }


def _rows_to_output(
    row_build: list[dict[str, Any]],
    *,
    pdf_path: str | None,
    job_id: str | None,
    dpi: float,
) -> list[dict[str, Any]]:
    """Generate crop PNGs and strip internal ``_name_words`` / ``_id_words`` keys."""
    out: list[dict[str, Any]] = []
    page_img = None
    if pdf_path and job_id:
        page_img = _render_pdf_page1_pil(pdf_path, dpi=dpi)
    img_w, img_h = (page_img.size if page_img else (0, 0))
    max_crop_height_in = 0.5

    for row in row_build:
        name_words: list[_AzureWord] = row.pop("_name_words")  # type: ignore[assignment]
        id_words: list[_AzureWord] = row.pop("_id_words")  # type: ignore[assignment]
        ridx = int(row["row_index"])

        name_crop_rel: str | None = None
        id_crop_rel: str | None = None

        if page_img is not None and job_id is not None:
            ub = _union_inch_bbox(name_words)
            if ub is not None:
                ub = _cap_inch_bbox_height_from_bottom(ub, max_crop_height_in)
                box = _inch_bbox_to_crop_pixels(ub, dpi, img_w, img_h, pad_px=10)
                if box is not None:
                    name_crop_rel = _save_crop_png(page_img, box, job_id, ridx, "name")

            ub_id = _union_inch_bbox(id_words)
            if ub_id is not None:
                ub_id = _cap_inch_bbox_height_from_bottom(ub_id, max_crop_height_in)
                box_id = _inch_bbox_to_crop_pixels(ub_id, dpi, img_w, img_h, pad_px=10)
                if box_id is not None:
                    id_crop_rel = _save_crop_png(page_img, box_id, job_id, ridx, "id")

        if name_crop_rel:
            row["name_crop_rel"] = name_crop_rel
        if id_crop_rel:
            row["id_crop_rel"] = id_crop_rel

        out.append(row)

    return out


def detect_table_rows(
    azure_result: dict,
    pdf_path: str | None = None,
    job_id: str | None = None,
    *_args: Any,
    max_rows: int = 12,
    dpi: float = 200,
    **_kwargs: Any,
) -> list[dict[str, Any]]:
    """
    Parse Azure OCR output directly (no re-OCR on crops).

    Strategy (per spec):
    - Document is landscape ~16.5 x 11.7 inches (Azure coords are inches for this file)
    - Team-member table is in right half and lower portion:
        left_x > 7.5 AND top_y > 6.0
    - Find 'NAME' tokens in that region; each marks a row start
    - For each NAME anchor, collect words in same horizontal band (±0.4 inches in y)
    - Name is words with x between ~8.5 and ~11.5
    - ID is 6-digit number after SA ID/SAID label; fallback to any 6-digit token with x > 12.0
    - Return list of dicts: {row_index, ocr_name_raw, ocr_id_raw, ocr_id_clean,
      name_crop_rel?, id_crop_rel?} — crop paths relative to MEDIA_ROOT when
      ``pdf_path`` and ``job_id`` are provided.

    Crop generation:
    - Render page 1 at ``dpi`` (default 200) via pypdfium2 → PIL
    - Union bounding box of Azure word polygons (inches) for tokens that built
      name / ID strings; convert to pixels as ``coord * dpi``, add 10px padding
    - Save under ``media/crops/<job_id>_row<N>_name.png`` (and ``_id.png``)
    """
    words = list(_iter_page_words(azure_result, 0))
    if not words:
        return []

    # Each ID token may only be used once across task leader + table rows.
    used_id_word_idxs: set[int] = set()

    row_build: list[dict[str, Any]] = []
    tl_row = _detect_task_leader_row(words, used_id_word_idxs)
    if tl_row is not None:
        row_build.append(tl_row)

    # Region filter (in inches) — team member table
    region = [w for w in words if (w.x_left > 7.5 and w.y_top > 6.0)]

    # Row anchors (NAME labels)
    anchors = [
        w
        for w in region
        if w.text.strip().upper() == "NAME" and (w.x_left > 7.5)
    ]
    anchors.sort(key=lambda w: w.y_center)
    if not anchors:
        return _rows_to_output(row_build, pdf_path=pdf_path, job_id=job_id, dpi=dpi)

    # Compute row boundaries as midpoints between consecutive NAME anchors.
    mids: list[float] = []
    for a, b in zip(anchors, anchors[1:]):
        mids.append((a.y_center + b.y_center) / 2.0)

    exclude_name = {
        "TEAM",
        "MEMBER",
        "NAME",
        "SA",
        "ID",
        "SAID",
        "SIGNATURE",
        "SIGN",
        "WHAT",
        "IS",
        "THE",
        "WORST",
        "THING",
        "THAT",
    }

    for idx, anchor in enumerate(anchors[:max_rows]):
        y_low = mids[idx - 1] if idx > 0 else float("-inf")
        y_high = mids[idx] if idx < len(mids) else float("inf")
        # Hard maximum cutoff for the table area to prevent the "WHAT IS THE WORST THING"
        # text block below the table from bleeding into the last row.
        y_high = min(y_high, 8.5)

        # All words belong to exactly one row by these boundaries.
        band = [w for w in region if (y_low <= w.y_center < y_high)]
        band.sort(key=lambda w: (w.x_left, w.y_center))

        # For ID label + ID tokens, allow a small y slack so labels/tokens near row borders
        # are still captured by the intended row.
        id_band = [
            w
            for w in region
            if ((y_low - 0.12) <= w.y_center < (y_high + 0.12))
        ]
        id_band.sort(key=lambda w: (w.x_left, w.y_center))

        # Find SA ID label for this row (content contains ID/SAID; roughly right side).
        label: _AzureWord | None = None
        for w in id_band:
            if w.x_left <= 9.5:
                continue
            tt = w.text.strip().upper().replace(" ", "")
            if "SAID" in tt or "ID" in tt:
                label = w
                break
            if tt in {"ID", "SAID"}:
                label = w
                break

        # Extract name (handwritten zone) between NAME anchor and SA ID label.
        name_x_min = max(9.2, anchor.x_right)
        name_x_max = 11.5
        if label is not None:
            name_x_max = min(name_x_max, label.x_left)

        name_tokens: list[str] = []
        name_words: list[_AzureWord] = []
        for w in band:
            x = w.x_left
            if not (name_x_min <= x <= name_x_max):
                continue
            t = w.text.strip()
            if not t:
                continue
            tu = t.upper().replace(" ", "")
            if tu in exclude_name:
                continue
            if any(ch.isdigit() for ch in t):
                continue
            name_tokens.append(t)
            name_words.append(w)
        ocr_name_raw = " ".join(name_tokens).strip()

        ocr_id_raw = ""
        ocr_id_clean = ""
        id_words: list[_AzureWord] = []

        if label is not None:
            # Only consider ID tokens to the RIGHT of label OR immediately below (<= 0.3in) and right of it.
            pool = [
                w
                for w in id_band
                if w.idx not in used_id_word_idxs
                and any(ch.isdigit() for ch in w.text)
                and (
                    (w.x_left > label.x_left)
                    or ((0.0 < (w.y_center - label.y_center) <= 0.35) and (w.x_left > label.x_left))
                )
            ]
            pool.sort(key=lambda w: (w.x_left, abs(w.y_center - label.y_center)))

            # Build candidates allowing split IDs like "100 740" -> "100740"
            # by concatenating adjacent digit tokens (close in x and y).
            best: tuple[set[int], str, float, float] | None = None
            for i, w in enumerate(pool):
                if w.idx in used_id_word_idxs:
                    continue
                digits = _digits_only(w.text)
                if not digits:
                    continue
                used = {w.idx}
                x0 = w.x_left
                yc = w.y_center

                # try extend with following tokens
                for nxt in pool[i + 1 : i + 6]:
                    if nxt.idx in used_id_word_idxs:
                        continue
                    if abs(nxt.y_center - yc) > 0.15:
                        continue
                    if (nxt.x_left - x0) > 1.2:
                        break
                    d2 = _digits_only(nxt.text)
                    if not d2:
                        continue
                    digits += d2
                    used.add(nxt.idx)
                    if len(digits) >= 6:
                        break

                if len(digits) == 6:
                    best = (used, digits, x0, yc)
                    break

                # also accept a single-token 6-digit match
                single = _clean_id_digits(w.text)
                if single:
                    best = ({w.idx}, single, x0, yc)
                    break

            if best:
                used_idxs, digits6, *_ = best
                used_id_word_idxs.update(used_idxs)
                ocr_id_clean = digits6
                ocr_id_raw = digits6
                id_words = [w for w in pool if w.idx in used_idxs]

        if not ocr_name_raw.strip() and not ocr_id_raw.strip():
            continue

        row_build.append(
            {
                "row_index": idx,
                "is_task_leader": False,
                "ocr_name_raw": ocr_name_raw,
                "ocr_id_raw": ocr_id_raw,
                "ocr_id_clean": ocr_id_clean,
                "_name_words": name_words,
                "_id_words": id_words,
            }
        )

    return _rows_to_output(row_build, pdf_path=pdf_path, job_id=job_id, dpi=dpi)
