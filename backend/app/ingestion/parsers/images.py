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
    import traceback
    from PIL import Image, ImageOps
    from app.ingestion.processor import resolve_document_file_path

    resolved_path = resolve_document_file_path(filepath)
    if not resolved_path.exists():
        log.error("Image file not found at path: %s (original: %s)", resolved_path, filepath)
        return []

    variants = []
    try:
        # Load image & correct EXIF orientation if needed
        pil_img = Image.open(str(resolved_path))
        try:
            pil_img = ImageOps.exif_transpose(pil_img)
        except Exception:
            pass

        # Handle RGBA/CMYK/Palette transparency normalization
        if pil_img.mode in ("RGBA", "LA") or (pil_img.mode == "P" and "transparency" in pil_img.info):
            bg = Image.new("RGB", pil_img.size, (255, 255, 255))
            if pil_img.mode != "RGBA":
                pil_img = pil_img.convert("RGBA")
            bg.paste(pil_img, mask=pil_img.split()[3])
            pil_img = bg
        else:
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
        log.error("OpenCV image preprocessing error for %s: %s\nTraceback:\n%s", filepath.name, e, traceback.format_exc())

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


def _extract_layout_blocks_tesseract(img: Any) -> List[Dict[str, Any]]:
    """Extract layout-aware text blocks with bounding boxes and line numbers using Tesseract image_to_data."""
    blocks: List[Dict[str, Any]] = []
    try:
        import pytesseract

        data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
        n_boxes = len(data["text"])

        lines_map: Dict[Tuple[int, int], List[Dict[str, Any]]] = {}

        for i in range(n_boxes):
            txt = (data["text"][i] or "").strip()
            conf_val = data["conf"][i]

            # Filter out blank entries
            if not txt or _is_forbidden_placeholder(txt):
                continue

            # Flag low confidence words
            if isinstance(conf_val, (int, float)) and 0 < conf_val < 35:
                txt = "[unclear]"

            block_num = data["block_num"][i]
            line_num = data["line_num"][i]
            left = data["left"][i]
            top = data["top"][i]
            w = data["width"][i]
            h = data["height"][i]

            key = (block_num, line_num)
            if key not in lines_map:
                lines_map[key] = []
            lines_map[key].append({
                "word": txt,
                "bbox": [left, top, w, h],
                "conf": conf_val if isinstance(conf_val, (int, float)) else 50.0,
            })

        # Assemble lines into structured blocks
        b_idx = 0
        for (b_num, l_num), words in sorted(lines_map.items(), key=lambda k: (k[0][0], k[0][1])):
            line_text = " ".join([w["word"] for w in words]).strip()
            if not line_text or _is_forbidden_placeholder(line_text):
                continue

            min_x = min(w["bbox"][0] for w in words)
            min_y = min(w["bbox"][1] for w in words)
            max_x = max(w["bbox"][0] + w["bbox"][2] for w in words)
            max_y = max(w["bbox"][1] + w["bbox"][3] for w in words)
            bbox = [min_x, min_y, max_x - min_x, max_y - min_y]

            # Determine line type (heading, bullet, paragraph)
            line_type = "paragraph"
            t_lower = line_text.lower()
            if line_text.startswith(("•", "-", "*")) or re.match(r"^\d+[\.\)]", line_text):
                line_type = "bullet"
            elif any(h_word in t_lower for h_word in ["notes", "introduction", "purpose", "features", "tip", "summary", "heading"]) or line_text.isupper() or line_text.endswith(":"):
                line_type = "heading"

            avg_conf = sum(w["conf"] for w in words if isinstance(w["conf"], (int, float))) / max(1, len(words))

            blocks.append({
                "block_id": f"b{b_idx}",
                "text": line_text,
                "type": line_type,
                "page": 1,
                "bbox": bbox,
                "line_number": l_num,
                "confidence": round(avg_conf / 100.0, 2),
            })
            b_idx += 1

    except Exception as e:
        log.debug("Tesseract layout extraction fallback: %s", e)

    return blocks


def parse(filepath: str | Path) -> List[Tuple[str, Dict[str, Any]]]:
    """Parse image using multi-stage layout-aware OCR (Tesseract + EasyOCR + Vision LLM Fallback)."""
    filepath = Path(filepath)
    log.info("Parsing image file: %s", filepath.name)

    variants = _preprocess_image(filepath)

    # 1. Extract layout-aware positional blocks
    layout_blocks = []
    if variants:
        layout_blocks = _extract_layout_blocks_tesseract(variants[0])
        if not layout_blocks and len(variants) > 1:
            layout_blocks = _extract_layout_blocks_tesseract(variants[1])

    # 2. Run Tesseract OCR
    tess_text = _run_tesseract(variants)

    # 3. Run EasyOCR
    easy_text = _run_easyocr(variants)

    # Combine & deduplicate line by line for raw_ocr
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

    raw_ocr = "\n".join(combined_lines).strip()

    # 4. Vision LLM Fallback if OCR produced minimal text (< 30 characters)
    if len(raw_ocr) < 30:
        log.info("OCR output for %s is minimal (%d chars). Attempting vision fallback...", filepath.name, len(raw_ocr))
        vision_text = _call_ollama_vision_fallback(filepath)
        if vision_text and len(vision_text) > len(raw_ocr):
            raw_ocr = vision_text

    cleaned_final = clean_text(raw_ocr)

    # Sanity filter against placeholders
    if _is_forbidden_placeholder(cleaned_final):
        cleaned_final = ""

    # 5. Strict guard: If actual extraction failed, return empty list
    if not cleaned_final or len(cleaned_final) < 5:
        log.warning("No readable text could be extracted from image %s", filepath.name)
        return []

    # 6. Generate Structured Document OCR (headings, bullet points, paragraph breaks)
    structured_parts = []
    if layout_blocks:
        for b in layout_blocks:
            b_text = b["text"]
            b_type = b.get("type", "paragraph")
            if b_type == "heading":
                structured_parts.append(f"\n### {b_text}\n")
            elif b_type == "bullet":
                structured_parts.append(f"  • {b_text.lstrip('•-* ')}")
            else:
                structured_parts.append(f"{b_text}")
        structured_ocr = "\n".join(structured_parts).strip()
    else:
        structured_ocr = cleaned_final

    confidence = "high" if len(cleaned_final) > 100 else ("medium" if len(cleaned_final) > 30 else "low")

    log.info("✓ Extracted %d chars & %d layout blocks from %s (OCR confidence: %s)",
             len(cleaned_final), len(layout_blocks), filepath.name, confidence)

    return [(structured_ocr, {
        "source_type": "image",
        "file_name": filepath.name,
        "ocr_confidence": confidence,
        "raw_ocr": cleaned_final,
        "structured_ocr": structured_ocr,
        "layout_blocks": json.dumps(layout_blocks),
        "page_number": 1,
        "image_number": 1,
        "slide_number": 1,
    })]
