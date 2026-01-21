import threading
import re
import easyocr

from app.settings import EASYOCR_GPU, EASYOCR_LANGS

_reader = None
_lock = threading.Lock()


def get_reader():
    """
    Create the EasyOCR Reader once and reuse it.
    Thread-safe for FastAPI.
    """
    global _reader
    if _reader is None:
        with _lock:
            if _reader is None:
                _reader = easyocr.Reader(
                    EASYOCR_LANGS,
                    gpu=EASYOCR_GPU
                )
    return _reader


def read_id_from_crop(crop_bgr) -> str:
    """
    crop_bgr: OpenCV BGR image (numpy array), tightly cropped to ID region
    returns: digits-only string
    """
    reader = get_reader()

    # OpenCV BGR -> RGB
    crop_rgb = crop_bgr[:, :, ::-1]

    texts = reader.readtext(
        crop_rgb,
        detail=0,
        allowlist="0123456789",
        paragraph=False
    )

    if not texts:
        return ""

    raw = "".join(texts)
    digits = re.sub(r"\D", "", raw)
    return digits
