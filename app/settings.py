import os

def _bool_env(name: str, default: str = "auto") -> str:
    v = os.getenv(name, default).strip().lower()
    if v in ("1", "true", "yes", "y", "on"):
        return "1"
    if v in ("0", "false", "no", "n", "off"):
        return "0"
    return "auto"


_gpu_mode = _bool_env("EASYOCR_GPU", default="auto")
if _gpu_mode == "1":
    EASYOCR_GPU = True
elif _gpu_mode == "0":
    EASYOCR_GPU = False
else:
    # Auto-detect (safe fallback to CPU if torch/cuda isn't available)
    try:
        import torch  # type: ignore

        EASYOCR_GPU = bool(torch.cuda.is_available())
    except Exception:
        EASYOCR_GPU = False

EASYOCR_LANGS = ["en"]