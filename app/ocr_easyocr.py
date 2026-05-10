import threading
import re
from typing import List, Optional, Sequence

import cv2
import easyocr
import numpy as np
from PIL import Image, ImageOps, ImageFilter

from app.settings import EASYOCR_GPU, EASYOCR_LANGS


# --------------------------------------------------
# CONFIG
# --------------------------------------------------
DEBUG_OCR = False   # set False once verified


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
# Line removal (handwriting-safe)
# --------------------------------------------------
def _remove_horizontal_lines(gray_np: np.ndarray) -> np.ndarray:
    """
    Remove thin horizontal table lines without damaging handwriting.
    """
    _, bw = cv2.threshold(gray_np, 200, 255, cv2.THRESH_BINARY_INV)

    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (45, 1))
    lines = cv2.morphologyEx(bw, cv2.MORPH_OPEN, kernel, iterations=1)

    cleaned = gray_np.copy()
    cleaned[lines > 0] = 255
    return cleaned


def _reader_readtext_batch(reader, images: Sequence[np.ndarray], *, allowlist: str) -> List[List[str]]:
    """
    Return list-of-texts per image (one list of strings per input crop).

    Note: easyocr.Reader.readtext_batched requires every image to have the same
    H×W (unless n_width/n_height resize all inputs). Row crops differ in size,
    so we always use readtext per image here to avoid NumPy inhomogeneous-shape
    errors inside EasyOCR.
    """
    if not images:
        return []

    results: List[List[str]] = []
    for img in images:
        texts = reader.readtext(
            img,
            detail=0,
            allowlist=allowlist,
            paragraph=False,
        )
        results.append(list(texts or []))
    return results


def _extract_id_candidates_from_texts(texts: Sequence[str]) -> List[str]:
    candidates: List[str] = []
    for t in texts:
        digits = re.sub(r"\D", "", t)
        if len(digits) == 6:
            candidates.append(digits)
        elif len(digits) == 5:
            candidates.append(digits)

    # De-duplicate (preserve order), prefer 6-digit first
    seen = set()
    unique: List[str] = []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            unique.append(c)
    unique6 = [c for c in unique if len(c) == 6]
    unique5 = [c for c in unique if len(c) == 5]
    return unique6 + unique5


def read_ids_from_crops(crops_rgb: Sequence[np.ndarray]) -> List[List[str]]:
    """
    OCR multiple cropped rows containing handwritten employee IDs.

    Returns:
        A list per crop: digit-only OCR candidates (prefer 6 digits; keep 5-digit fallback).
    """
    reader = get_reader()
    if not crops_rgb:
        return []

    # Preprocess all crops once
    cleaned_list: List[np.ndarray] = []
    bw_list: List[np.ndarray] = []
    for crop in crops_rgb:
        img = Image.fromarray(crop)
        gray = img.convert("L")
        gray = ImageOps.autocontrast(gray)
        gray = gray.filter(ImageFilter.MedianFilter(3))
        gray_np = np.array(gray, dtype=np.uint8)

        cleaned_np = _remove_horizontal_lines(gray_np)
        cleaned_list.append(cleaned_np)

        bw = cv2.adaptiveThreshold(
            cleaned_np, 255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            21, 10
        )
        bw = cv2.resize(bw, None, fx=1.5, fy=1.5, interpolation=cv2.INTER_CUBIC)
        bw_list.append(bw)

    # Pass 1 (fast): cleaned grayscale
    cleaned_texts = _reader_readtext_batch(reader, cleaned_list, allowlist="0123456789")
    out: List[List[str]] = [_extract_id_candidates_from_texts(t) for t in cleaned_texts]

    # Pass 2 (fallback only where needed): binarized
    need_idx = [i for i, cands in enumerate(out) if not cands]
    if need_idx:
        bw_images = [bw_list[i] for i in need_idx]
        bw_texts = _reader_readtext_batch(reader, bw_images, allowlist="0123456789")
        for j, texts in enumerate(bw_texts):
            i = need_idx[j]
            out[i] = _extract_id_candidates_from_texts(texts)

    return out


def read_names_from_crops(crops_rgb: Sequence[np.ndarray]) -> List[str]:
    """
    OCR multiple cropped rows containing handwritten employee names.
    """
    reader = get_reader()
    if not crops_rgb:
        return []

    cleaned_list: List[np.ndarray] = []
    for crop in crops_rgb:
        img = Image.fromarray(crop)
        gray = img.convert("L")
        gray = ImageOps.autocontrast(gray)
        gray = gray.filter(ImageFilter.MedianFilter(3))
        gray_np = np.array(gray, dtype=np.uint8)

        cleaned_np = _remove_horizontal_lines(gray_np)
        cleaned_np = cv2.resize(
            cleaned_np,
            None,
            fx=2.0,
            fy=2.0,
            interpolation=cv2.INTER_CUBIC
        )
        cleaned_list.append(cleaned_np)

    texts_per = _reader_readtext_batch(
        reader,
        cleaned_list,
        allowlist="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ -",
    )
    raw_names = [" ".join(t).strip() for t in texts_per]
    return [_clean_name_text(x) for x in raw_names]


# --------------------------------------------------
# OCR: Handwritten EMPLOYEE ID (numbers)
# --------------------------------------------------
def read_ids_from_crop(crop_rgb: np.ndarray, row_index: Optional[int] = None) -> List[str]:
    """
    OCR a single cropped row containing ONE handwritten employee ID.

    Returns:
        List of digit-only OCR candidates (prefer 6 digits; keep 5-digit as fallback)
    """
    if DEBUG_OCR and row_index is not None:
        Image.fromarray(crop_rgb).save(f"debug_sa_id_raw_row_{row_index}.png")

    out = read_ids_from_crops([crop_rgb])[0]
    return out


# --------------------------------------------------
# OCR: Handwritten EMPLOYEE NAME
# --------------------------------------------------
def _clean_name_text(s: str) -> str:
    s = s.lower()
    s = re.sub(r"[^a-z ]", " ", s)
    s = " ".join(s.split())
    return s


def read_name_from_crop(crop_rgb: np.ndarray, row_index: Optional[int] = None) -> str:
    """
    OCR a single cropped row containing ONE handwritten employee name.

    Returns:
        Cleaned name string (lowercase letters + spaces)
    """
    # -------------------------------
    # DEBUG: raw crop
    # -------------------------------
    if DEBUG_OCR and row_index is not None:
        Image.fromarray(crop_rgb).save(f"debug_name_raw_row_{row_index}.png")

    out = read_names_from_crops([crop_rgb])[0]
    return out







