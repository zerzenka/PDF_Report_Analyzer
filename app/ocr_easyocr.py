import threading
import re
from typing import List

import cv2
import easyocr
import numpy as np
from PIL import Image, ImageOps, ImageFilter

from app.settings import EASYOCR_GPU, EASYOCR_LANGS


# --------------------------------------------------
# CONFIG
# --------------------------------------------------
DEBUG_OCR = True   # set to False once verified


# --------------------------------------------------
# EasyOCR singleton (FastAPI-safe)
# --------------------------------------------------
_reader = None
_lock = threading.Lock()


def get_reader():
    global _reader
    if _reader is None:
        with _lock:
            if _reader is None:
                _reader = easyocr.Reader(
                    EASYOCR_LANGS,
                    gpu=EASYOCR_GPU
                )
    return _reader


# --------------------------------------------------
# Line removal (pixel-level, handwriting-safe)
# --------------------------------------------------
def _remove_horizontal_lines(gray_np: np.ndarray) -> np.ndarray:
    """
    Remove thin horizontal table lines without damaging handwriting.
    """

    _, bw = cv2.threshold(
        gray_np,
        200,
        255,
        cv2.THRESH_BINARY_INV
    )

    kernel = cv2.getStructuringElement(
        cv2.MORPH_RECT,
        (45, 1)
    )

    lines = cv2.morphologyEx(
        bw,
        cv2.MORPH_OPEN,
        kernel,
        iterations=1
    )

    cleaned = gray_np.copy()
    cleaned[lines > 0] = 255

    return cleaned


# --------------------------------------------------
# Main OCR function (CANDIDATES ONLY)
# --------------------------------------------------
def read_ids_from_crop(crop_rgb: np.ndarray, row_index: int | None = None) -> List[str]:
    """
    OCR a single cropped row containing ONE handwritten employee ID.

    Returns:
        List of digit-only OCR candidates (length 5–6).
        No validation, no correction, no business rules.
    """

    reader = get_reader()

    # --- DEBUG: raw crop ---
    if DEBUG_OCR and row_index is not None:
        Image.fromarray(crop_rgb).save(f"debug_sa_id_raw_row_{row_index}.png")

    # --- Preprocessing ---
    img = Image.fromarray(crop_rgb)

    gray = img.convert("L")
    gray = ImageOps.autocontrast(gray)
    gray = gray.filter(ImageFilter.MedianFilter(3))

    gray_np = np.array(gray, dtype=np.uint8)

    cleaned_np = _remove_horizontal_lines(gray_np)

    if DEBUG_OCR:
        Image.fromarray(cleaned_np).save("debug_sa_id_cleaned.png")

    # --- Multi-pass OCR (robust to handwriting / contrast) ---
    variants = [
        cleaned_np,
        cv2.convertScaleAbs(cleaned_np, alpha=1.15, beta=0),
        cv2.convertScaleAbs(cleaned_np, alpha=0.90, beta=0),
    ]

    candidates: List[str] = []

    for v in variants:
        texts = reader.readtext(
            v,
            detail=0,
            allowlist="0123456789",
            paragraph=False,
        )

        for t in texts:
            digits = re.sub(r"\D", "", t)
            if len(digits) in (5, 6):
                candidates.append(digits)

    # --- De-duplicate (keep order) ---
    seen = set()
    unique_candidates: List[str] = []

    for c in candidates:
        if c not in seen:
            seen.add(c)
            unique_candidates.append(c)

    return unique_candidates






