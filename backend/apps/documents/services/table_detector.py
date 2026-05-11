from __future__ import annotations

import math
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from django.conf import settings
from PIL import Image


@dataclass(frozen=True)
class _Word:
    text: str
    bbox: tuple[float, float, float, float]  # x0,y0,x1,y1 in OCR page coords


def _iter_words(azure_result: dict) -> Iterable[tuple[int, _Word, dict]]:
    """
    Yield (page_index, word, page_dict) for each word.

    Supports Document Intelligence prebuilt-read shapes where words live under:
    - result["pages"][i]["words"][j] with "content" and "polygon"
    """
    pages = azure_result.get("pages") or []
    for page_index, page in enumerate(pages):
        for w in page.get("words") or []:
            text = str(w.get("content") or "").strip()
            poly = w.get("polygon") or []
            if not text or len(poly) < 8:
                continue
            xs = [float(poly[i]) for i in range(0, len(poly), 2)]
            ys = [float(poly[i]) for i in range(1, len(poly), 2)]
            bbox = (min(xs), min(ys), max(xs), max(ys))
            yield page_index, _Word(text=text, bbox=bbox), page


def _page_dims(page: dict) -> tuple[float, float]:
    w = page.get("width")
    h = page.get("height")
    if w is None or h is None:
        raise ValueError("Azure OCR page missing width/height")
    return float(w), float(h)


def _render_pdf_first_page(pdf_path: str) -> Image.Image:
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(pdf_path)
    page = pdf[0]
    # A moderate scale keeps crops legible without huge files.
    bitmap = page.render(scale=2.0)
    return bitmap.to_pil()


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _scale_bbox(
    bbox: tuple[float, float, float, float],
    src_w: float,
    src_h: float,
    dst_w: int,
    dst_h: int,
) -> tuple[int, int, int, int]:
    x0, y0, x1, y1 = bbox
    sx = dst_w / src_w
    sy = dst_h / src_h
    px0 = int(math.floor(_clamp(x0 * sx, 0, dst_w - 1)))
    py0 = int(math.floor(_clamp(y0 * sy, 0, dst_h - 1)))
    px1 = int(math.ceil(_clamp(x1 * sx, 1, dst_w)))
    py1 = int(math.ceil(_clamp(y1 * sy, 1, dst_h)))
    if px1 <= px0:
        px1 = min(dst_w, px0 + 1)
    if py1 <= py0:
        py1 = min(dst_h, py0 + 1)
    return px0, py0, px1, py1


def detect_table_rows(
    azure_result: dict,
    pdf_path: str,
    *,
    job_id: str,
    max_rows: int = 12,
) -> list[dict[str, Any]]:
    """
    Heuristic detector for HP Briefing team-member table (bottom-right).

    Returns list of dicts:
      { ocr_name_raw, ocr_id_raw, name_crop_path, id_crop_path }

    Crops are stored under MEDIA_ROOT/crops/.
    """
    pages = azure_result.get("pages") or []
    if not pages:
        return []

    # For now we assume the table is on the first page.
    page = pages[0]
    ocr_w, ocr_h = _page_dims(page)

    words = [
        word
        for pidx, word, _ in _iter_words(azure_result)
        if pidx == 0
    ]
    if not words:
        return []

    # Focus on bottom-right quadrant to avoid headers/other fields.
    br_words: list[_Word] = []
    for w in words:
        x0, y0, x1, y1 = w.bbox
        cx = (x0 + x1) / 2.0
        cy = (y0 + y1) / 2.0
        if cx >= (0.55 * ocr_w) and cy >= (0.55 * ocr_h):
            br_words.append(w)

    if not br_words:
        return []

    # Cluster into "rows" by y-center using a simple bucketing threshold.
    br_words.sort(key=lambda w: ((w.bbox[1] + w.bbox[3]) / 2.0, w.bbox[0]))
    row_clusters: list[list[_Word]] = []
    y_threshold = max(10.0, 0.018 * ocr_h)  # scale with page height

    for w in br_words:
        y = (w.bbox[1] + w.bbox[3]) / 2.0
        if not row_clusters:
            row_clusters.append([w])
            continue
        last = row_clusters[-1]
        last_y = sum((x.bbox[1] + x.bbox[3]) / 2.0 for x in last) / len(last)
        if abs(y - last_y) <= y_threshold:
            last.append(w)
        else:
            row_clusters.append([w])

    # Render the PDF page once and reuse.
    page_img = _render_pdf_first_page(pdf_path)
    img_w, img_h = page_img.size

    crops_dir = Path(settings.MEDIA_ROOT) / "crops"
    crops_dir.mkdir(parents=True, exist_ok=True)

    out: list[dict[str, Any]] = []
    for row_index, cluster in enumerate(row_clusters[:max_rows]):
        # Split cluster into "name-ish" and "id-ish" by x position (roughly two columns).
        cluster_sorted = sorted(cluster, key=lambda w: w.bbox[0])
        xs = [(w.bbox[0] + w.bbox[2]) / 2.0 for w in cluster_sorted]
        if not xs:
            continue
        split_x = sorted(xs)[len(xs) // 2]

        name_words = [w for w in cluster_sorted if ((w.bbox[0] + w.bbox[2]) / 2.0) <= split_x]
        id_words = [w for w in cluster_sorted if w not in name_words]
        if not id_words:
            # fallback: attempt to separate by digits content
            id_words = [w for w in cluster_sorted if any(ch.isdigit() for ch in w.text)]
            name_words = [w for w in cluster_sorted if w not in id_words]

        def bbox_union(ws: list[_Word]) -> tuple[float, float, float, float] | None:
            if not ws:
                return None
            x0 = min(w.bbox[0] for w in ws)
            y0 = min(w.bbox[1] for w in ws)
            x1 = max(w.bbox[2] for w in ws)
            y1 = max(w.bbox[3] for w in ws)
            # pad slightly
            pad_x = 0.01 * ocr_w
            pad_y = 0.008 * ocr_h
            return (x0 - pad_x, y0 - pad_y, x1 + pad_x, y1 + pad_y)

        name_bbox = bbox_union(name_words) or bbox_union(cluster_sorted)
        id_bbox = bbox_union(id_words) or bbox_union(cluster_sorted)
        if not name_bbox or not id_bbox:
            continue

        name_px = _scale_bbox(name_bbox, ocr_w, ocr_h, img_w, img_h)
        id_px = _scale_bbox(id_bbox, ocr_w, ocr_h, img_w, img_h)

        name_img = page_img.crop(name_px)
        id_img = page_img.crop(id_px)

        token = uuid.uuid4().hex[:10]
        name_rel = Path("crops") / f"{job_id}_row{row_index}_name_{token}.png"
        id_rel = Path("crops") / f"{job_id}_row{row_index}_id_{token}.png"
        name_abs = Path(settings.MEDIA_ROOT) / name_rel
        id_abs = Path(settings.MEDIA_ROOT) / id_rel

        name_img.save(name_abs)
        id_img.save(id_abs)

        ocr_name_raw = " ".join(w.text for w in name_words).strip()
        ocr_id_raw = " ".join(w.text for w in id_words).strip()

        out.append(
            {
                "ocr_name_raw": ocr_name_raw,
                "ocr_id_raw": ocr_id_raw,
                "name_crop_path": str(name_rel).replace("\\", "/"),
                "id_crop_path": str(id_rel).replace("\\", "/"),
            }
        )

    return out

