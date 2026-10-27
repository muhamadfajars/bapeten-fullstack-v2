import os

import cv2
import fitz
import numpy as np

from src.extraction.label_ocr import extract_ocr


IMAGE_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".bmp",
    ".webp",
}


def decode_image(path):
    data = np.fromfile(
        path,
        dtype=np.uint8,
    )

    image = cv2.imdecode(
        data,
        cv2.IMREAD_COLOR,
    )

    if image is None:
        raise ValueError(
            f"Gambar tidak dapat dibaca: {path}"
        )

    return image


def get_ocr_lines(image):
    results = extract_ocr(image)

    lines = []

    for item in results:
        value = str(
            item.get("text") or ""
        ).strip()

        if value:
            lines.append(value)

    return lines


def extract_pdf_pages(path, dpi=180):
    from src.extraction.document_reader import read_pages
    return [{k: p[k] for k in ('page','method','lines','text')}
            for p in read_pages(path, dpi=dpi)]


def extract_image_page(path):
    image = decode_image(path)
    lines = get_ocr_lines(image)

    return [{
        "page": 1,
        "method": "OCR",
        "lines": lines,
        "text": "\n".join(lines),
    }]


def parse_equipment_specification(path):
    extension = os.path.splitext(
        path
    )[1].lower()

    if extension == ".pdf":
        pages = extract_pdf_pages(path)

    elif extension in IMAGE_EXTENSIONS:
        pages = extract_image_page(path)

    else:
        raise ValueError(
            f"Format dokumen tidak didukung: {extension}"
        )

    return {
        "source_name": os.path.basename(path),
        "total_pages": len(pages),
        "pages": pages,
    }