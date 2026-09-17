"""Image parser — extracts printed and handwritten text via preprocessed OCR and Vision fallback."""

from __future__ import annotations

import base64
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple

import requests

from app.core.config import settings
from app.core.logging import get_logger
from app.utils.text import clean_text

log = get_logger(__name__)

# Strict forbidden placeholder strings that must NEVER be saved as chunk text
FORBIDDEN_PLACEHOLDERS = [
    "ocr processing complete",
    "visual content",
    "[image:",
    "processing complete",
]


def _is_forbidden_placeholder(text: str) -> bool:
    """Check if text is a generic placeholder or status message."""
    t_lower = text.lower().strip()
    for ph in FORBIDDEN_PLACEHOLDERS:
        if ph in t_lower:
            return True
    return False


def _preprocess_image(filepath: Path) -> List[Any]:
    """Generate multiple preprocessed OpenCV image variants to maximize OCR accuracy."""
    import cv2
    import numpy as np
    from PIL import Image, ImageOps

    variants = []
    try:
        # Load image & correct EXIF orientation if needed
        pil_img = Image.open(str(filepath))
        try:
            pil_img = ImageOps.exif_transpose(pil_img)
        except Exception:
            pass
        pil_img = pil_img.convert("RGB")
        img_bgr = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)

        # Scale up small images for better OCR resolution
        h, w = img_bgr.shape[:2]
        if min(h, w) < 1000:
            scale = 1200.0 / float(min(h, w))
            img_bgr = cv2.resize(img_bgr, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_CUBIC)

        gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
        variants.append(gray)

        # Variant 1: CLAHE Contrast Limited Adaptive Histogram Equalization (great for handwritten paper)
        clahe = cv2.createCLAHE(clipLimit=3.5, tileGridSize=(8, 8))
        enhanced = clahe.apply(gray)
        variants.append(enhanced)

        # Variant 2: Fast NlMeans Denoising + Otsu Thresholding
        denoised = cv2.fastNlMeansDenoising(enhanced, None, 10, 7, 21)
        _, otsu = cv2.threshold(denoised, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        variants.append(otsu)

        # Variant 3: Adaptive Gaussian Thresholding
        adaptive_thresh = cv2.adaptiveThreshold(
            denoised, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 21, 11
        )
        variants.append(adaptive_thresh)
    except Exception as e:
        log.warning("OpenCV image preprocessing error for %s: %s", filepath.name, e)

    return variants


def _run_tesseract(variants: List[Any]) -> str:
    """Run pytesseract across image variants using multiple Page Segmentation Modes (PSMs)."""
    try:
        import pytesseract

        extracted_lines = []
        psms = [6, 4, 3, 11]

        for img in variants:
            for psm in psms:
                config = f"--psm {psm}"
                try:
                    txt = pytesseract.image_to_string(img, config=config)
                    cleaned = txt.strip()
                    if cleaned:
                        for line in cleaned.split("\n"):
                            line_str = line.strip()
                            if len(line_str) > 2 and not _is_forbidden_placeholder(line_str) and line_str not in extracted_lines:
                                extracted_lines.append(line_str)
                except Exception:
                    continue

        return "\n".join(extracted_lines)
    except Exception as e:
        log.debug("Tesseract OCR unavailable or failed: %s", e)
        return ""


def _run_easyocr(variants: List[Any]) -> str:
    """Run EasyOCR reader across preprocessed image variants."""
    try:
        import easyocr
        reader = easyocr.Reader(["en"], gpu=False)

        lines = []
        for img in variants[:2]:
            results = reader.readtext(img, detail=0)
            for text in results:
                t_str = str(text).strip()
                if len(t_str) > 2 and not _is_forbidden_placeholder(t_str) and t_str not in lines:
                    lines.append(t_str)

        return "\n".join(lines)
    except Exception as e:
        log.debug("EasyOCR failed: %s", e)
        return ""


def _call_ollama_vision_fallback(filepath: Path) -> str:
    """Call Ollama local vision endpoint to accurately transcribe handwritten/printed image text."""
    try:
        url = f"{settings.OLLAMA_BASE_URL.rstrip('/')}/api/generate"
        with open(filepath, "rb") as f:
            b64_img = base64.b64encode(f.read()).decode("utf-8")

        prompt = (
            "You are an expert OCR transcription assistant. Transcribe ALL handwritten and printed text in this image accurately. "
            "Preserve headings, paragraphs, numbered lists, bullet points, and key formatting exactly as written. "
            "Do NOT summarize or omit any written details."
        )

        payload = {
            "model": "gemma3:4b",
            "prompt": prompt,
            "images": [b64_img],
            "stream": False,
        }

        resp = requests.post(url, json=payload, timeout=20)
        if resp.status_code == 200:
            data = resp.json()
            raw_res = data.get("response", "").strip()
            if raw_res and not _is_forbidden_placeholder(raw_res):
                return raw_res
    except Exception as e:
        log.debug("Ollama vision fallback failed: %s", e)
    return ""


def parse(filepath: str | Path) -> List[Tuple[str, Dict[str, Any]]]:
    """Parse image using multi-stage OCR (Tesseract + EasyOCR + Vision LLM Fallback)."""
    filepath = Path(filepath)
    log.info("Parsing image file: %s", filepath.name)

    variants = _preprocess_image(filepath)

    # 1. Run Tesseract OCR
    tess_text = _run_tesseract(variants)

    # 2. Run EasyOCR
    easy_text = _run_easyocr(variants)

    # Combine & deduplicate line by line
    combined_lines = []
    seen = set()
    for source_text in [tess_text, easy_text]:
        if source_text:
            for line in source_text.split("\n"):
                cleaned_line = line.strip()
                if _is_forbidden_placeholder(cleaned_line):
                    continue
                norm_key = re.sub(r"\s+", " ", cleaned_line.lower())
                if len(cleaned_line) > 2 and norm_key not in seen:
                    seen.add(norm_key)
                    combined_lines.append(cleaned_line)

    extracted_text = "\n".join(combined_lines).strip()

    # 3. Vision LLM Fallback if OCR produced minimal text (< 30 characters)
    if len(extracted_text) < 30:
        log.info("OCR output for %s is minimal (%d chars). Attempting vision fallback...", filepath.name, len(extracted_text))
        vision_text = _call_ollama_vision_fallback(filepath)
        if vision_text and len(vision_text) > len(extracted_text):
            extracted_text = vision_text

    cleaned_final = clean_text(extracted_text)

    # Sanity filter against placeholders
    if _is_forbidden_placeholder(cleaned_final):
        cleaned_final = ""

    # 4. Strict guard: If actual extraction failed, return empty list so document is marked as failed, NOT placeholder text
    if not cleaned_final or len(cleaned_final) < 5:
        log.warning("No readable text could be extracted from image %s", filepath.name)
        return []

    confidence = "high" if len(cleaned_final) > 100 else ("medium" if len(cleaned_final) > 30 else "low")

    log.info("✓ Successfully extracted %d chars from image %s (OCR confidence: %s)", len(cleaned_final), filepath.name, confidence)

    return [(cleaned_final, {
        "source_type": "image",
        "file_name": filepath.name,
        "ocr_confidence": confidence,
        "page_number": 1,
        "image_number": 1,
        "slide_number": 1,
    })]
