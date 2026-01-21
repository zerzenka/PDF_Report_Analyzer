import os

EASYOCR_GPU = os.getenv("EASYOCR_GPU", "0") == "1"  # default OFF for RTX 5070 today
EASYOCR_LANGS = ["en"]