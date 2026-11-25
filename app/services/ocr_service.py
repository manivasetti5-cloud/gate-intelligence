"""OCR fallback service using OpenCV preprocessing and Tesseract when available."""

import os
from pathlib import Path
import shutil

import cv2
from PIL import Image


def is_tesseract_available() -> bool:
    """Return True if a Tesseract OCR binary is accessible."""
    configured = os.getenv("TESSERACT_CMD", "").strip()
    if configured and Path(configured).exists():
        return True
    return shutil.which("tesseract") is not None


def run_ocr_on_image(image_path: str | Path) -> tuple[str, bool, str | None]:
    """
    Run preprocessed OCR on a scanned page or diagram image.
    Returns (extracted_text, ocr_succeeded, note_or_warning).
    """
    if not is_tesseract_available():
        return "", False, "Tesseract binary not found on system; skipped OCR."

    import pytesseract

    configured = os.getenv("TESSERACT_CMD", "").strip()
    if configured:
        pytesseract.pytesseract.tesseract_cmd = configured

    path = Path(image_path)
    img = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if img is None:
        with Image.open(path) as pil_im:
            text = pytesseract.image_to_string(pil_im)
        return text.strip(), True, None

    denoised = cv2.medianBlur(img, 3)
    _, thresh = cv2.threshold(denoised, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    text = pytesseract.image_to_string(thresh)
    return text.strip(), True, None
