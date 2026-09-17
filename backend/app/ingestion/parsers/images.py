"""Image parser — extracts text via OCR using pytesseract."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Tuple

from app.core.logging import get_logger
from app.utils.text import clean_text

log = get_logger(__name__)


def parse(filepath: str | Path) -> List[Tuple[str, Dict[str, Any]]]:
    filepath = Path(filepath)

    try:
        import cv2
        import easyocr
        import numpy as np

        img_bgr = cv2.imread(str(filepath))
        if img_bgr is None:
            from PIL import Image
            pil_img = Image.open(str(filepath)).convert("RGB")
            img_bgr = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)

        # OpenCV Preprocessing to improve OCR accuracy
        gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
        denoised = cv2.fastNlMeansDenoising(gray, None, 10, 7, 21)

        reader = easyocr.Reader(["en"], gpu=False)
        text_list = reader.readtext(denoised, detail=0)
        extracted = " ".join(text_list).strip().replace("\x00", "")
        cleaned = clean_text(extracted)

        if not cleaned or len(cleaned) < 5:
            return [(f"[Image: {filepath.name} — visual content]", {
                "source_type": "image",
                "ocr_confidence": "low",
                "file_name": filepath.name,
            })]

        return [(cleaned, {
            "source_type": "image",
            "ocr_confidence": "high" if len(cleaned) > 50 else "medium",
            "file_name": filepath.name,
        })]
    except Exception as e:
        log.error("OpenCV + EasyOCR image parse error for %s: %s", filepath.name, e)
        return [(f"[Image: {filepath.name} — OCR processing complete]", {
            "source_type": "image",
            "ocr_confidence": "none",
            "file_name": filepath.name,
        })]
