import re
from typing import List

import pdfplumber
import pytesseract
import numpy as np
from PIL import Image, ImageOps, ImageFilter

# Explicit path to Tesseract (no admin / no PATH dependency)
pytesseract.pytesseract.tesseract_cmd = (
    r"C:\Users\sa101685\AppData\Local\Programs\Tesseract-OCR\tesseract.exe"
)


def _remove_horizontal_lines(binary_image: Image.Image) -> Image.Image:
    """
    Remove horizontal ruled lines by clearing rows dominated by black pixels.
    Preserves handwritten strokes.
    """
    arr = np.array(binary_image)
    height, width = arr.shape

    for y in range(height):
        black_pixels = np.sum(arr[y] == 0)
        if black_pixels > width * 0.1:  # relaxed threshold (validated)
            arr[y] = 255               # clear row

    return Image.fromarray(arr)


def extract_numbers_from_box(pdf_path: str, bbox: tuple) -> List[str]:
    """
    Extract handwritten ID numbers from a fixed region in a scanned PDF.

    Args:
        pdf_path: Path to PDF file
        bbox: (x0, top, x1, bottom) in PDF coordinates

    Returns:
        List of detected ID strings (digits only)
    """

    with pdfplumber.open(pdf_path) as pdf:
        page = pdf.pages[0]

        # 1. Crop region
        cropped = page.crop(bbox)

        # 2. Render to image
        image = cropped.to_image(resolution=400).original

        # 3. Preprocessing (validated path)
        image = image.convert("L")                    # grayscale
        image = ImageOps.autocontrast(image)          # boost contrast
        image = image.filter(ImageFilter.MedianFilter(size=3))  # reduce noise

        # Gentle binarization (keeps ink intact)
        binary = image.point(lambda x: 0 if x < 160 else 255, "1")

        # 4. Remove horizontal lines
        cleaned = _remove_horizontal_lines(binary)
        cleaned.show()

        # 5. OCR (sparse handwritten content)
        raw_text = pytesseract.image_to_string(
        cleaned,
        config="--oem 3 --psm 10 -c tessedit_char_whitelist=0123456789"
        )

        # 6. Normalize common OCR confusions
        normalized = (
            raw_text
            .replace("O", "0")
            .replace("o", "0")
            .replace("I", "1")
            .replace("l", "1")
            .replace("S", "5")
            .replace(" ", "")
        )

        # 7. Extract valid IDs (business rule: 5+ digits)
        numbers = re.findall(r"\d{5,}", normalized)

        print("OCR RAW:", repr(raw_text))

        return numbers




