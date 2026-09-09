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
        from PIL import Image
        import pytesseract

        img = Image.open(str(filepath))
        text = pytesseract.image_to_string(img)
        cleaned = clean_text(text)

        if not cleaned or len(cleaned) < 10:
            return [(cleaned or "[Image with minimal text]", {
                "source_type": "image",
                "ocr_confidence": "low",
            })]

        return [(cleaned, {
            "source_type": "image",
            "ocr_confidence": "medium" if len(cleaned) > 50 else "low",
        })]
    except ImportError:
        log.warning("pytesseract not available — cannot OCR %s", filepath.name)
        return [("[Image — OCR not available]", {
            "source_type": "image",
            "ocr_confidence": "none",
        })]
    except Exception as e:
        log.error("Image parse error for %s: %s", filepath.name, e)
        return [("[Image — OCR failed]", {
            "source_type": "image",
            "ocr_confidence": "none",
        })]
