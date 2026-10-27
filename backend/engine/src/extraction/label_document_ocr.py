from src.extraction.label_document import (
    prepare_label_document,
)

from src.extraction.label_ocr import (
    extract_ocr,
)
from src.extraction.image_preprocess import label_roi_variants
import re
from src.extraction.label_gs1_v051 import augment_gs1_rows
from src.extraction.label_panel_v051 import detect_sticker_panels




def _needs_secondary_ocr(rows):
    """Conservative fast path: retry when a critical code could be misread.

    Never use OCR content to declare a document mismatch. This only decides
    whether to spend CPU on enhanced reads.
    """
    import re
    lines = [str(x.get("text") or "").upper() for x in rows]
    if not lines:
        return True
    has_model = any(re.search(r"(?:MODEL|DR\s*-?\s*XD|SMART\s*4000)", x) for x in lines)
    has_serial = any(re.search(r"(?:SER\.?\s*NO|\bSN\b|\(21\))", x) for x in lines)
    # Empty or partially recognized equipment information needs a retry.
    if has_model != has_serial:
        return True
    if not (has_model or has_serial):
        return False  # no primary device label on this page; other pages are scanned separately
    # Ambiguous serial tokens 0/O (e.g. OF1376), tube models I/L/1 (K110)
    for line in lines:
        if re.search(r"(?:SER\.?\s*NO|\bSN\b)", line):
            rhs = re.split(r"(?:SER\.?\s*NO\.?|\bSN\b)\s*[:#.-]?\s*", line, maxsplit=1)
            token = re.sub(r"[^A-Z0-9]", "", rhs[-1] if rhs else "")
            if len(token) >= 5 and re.search(r"[OIL][A-Z0-9]*\d", token):
                return True
        if re.search(r"(?:MODEL|TYPE|TIPE)", line):
            if re.search(r"\b[A-Z]{0,3}[1IL][1IL0-9]{1,4}[-./]", line):
                return True
    # If OCR already saw two distinct complete Fujifilm codes, do not retry.
    if any(re.search(r"DR\s*-\s*XD\s*1000\b", x) for x in lines) and any(
        re.search(r"DR\s*-\s*XD\s*1000PX\b", x) for x in lines
    ):
        return False
    # Uncertain label content: retry to avoid losing positive matches.
    return True


def _full_page_ocr_variants(image, original_rows):
    """Use the same full-page treatments that succeeded in the benchmark.

    Unlike v5, ROI bounding box selection cannot exclude the crucial line.
    Original OCR is never replaced and variant origin is retained.
    """
    import os
    import cv2
    from src.extraction.image_preprocess import apply_clahe, ensure_bgr

    debug = os.environ.get("BAPETEN_LABEL_OCR_DEBUG", "").lower() in ("1", "true", "yes")
    original_rows = [{**row, "variant": "original", "rescanned": False} for row in original_rows]
    variants = (
        ("gray", ensure_bgr(cv2.cvtColor(ensure_bgr(image), cv2.COLOR_BGR2GRAY))),
        ("clahe", apply_clahe(image)),
    )
    output = list(original_rows)
    for name, processed in variants:
        try:
            found = extract_ocr(processed)
        except Exception as exc:
            if debug:
                print(f"[LABEL-OCR] {name}: gagal: {type(exc).__name__}: {exc}", flush=True)
            continue
        output.extend({**row, "variant": name, "rescanned": True} for row in found)
        if debug:
            print(f"[LABEL-OCR] {name}: {len(found)} baris", flush=True)
    if debug:
        import re
        code = re.compile(r"(?:SER\.?\s*NO|MODEL|INSERT|DR\s*[- ]\s*XD|KL10|K110|KI10|0F1376|OF1376)", re.I)
        for row in output:
            value = str(row.get('text') or '')
            if code.search(value):
                print(f"[LABEL-OCR] {row.get('variant','?'):>8}: {value} ({row.get('confidence',0):.3f})", flush=True)
    return output


def _original_exact_hit(rows, field, value):
    """Only evidence actually read from ORIGINAL OCR counts at the stop gate.

    This is a screening criterion chosen by the user, NOT evidence that a
    nonmatching document is actually incorrect.
    """
    from src.matching.guided_label_matcher import (
        compact_text, normalize_text, normalize_serial_candidate,
    )
    if not value:
        return False
    candidates = [str(r.get("text") or "") for r in rows]
    variants = [str(value)]
    if field == "type" and "(" in str(value) and ")" in str(value):
        main = str(value).split("(", 1)[0].strip()
        alias = str(value).split("(", 1)[1].rsplit(")", 1)[0].strip()
        variants = [x for x in (main, alias) if x]
    if field == "serial_number":
        expected = compact_text(value)
        for line in candidates:
            actual = normalize_serial_candidate(line)
            if actual == expected:
                return True
            # Optional GS1 identifier at start of the line.
            if line.lstrip().startswith('(21)') and compact_text(line)[2:] == expected:
                return True
        return False
    for wanted in variants:
        tokens = re.findall(r"[A-Z0-9]+", normalize_text(wanted))
        if not tokens:
            continue
        # Exact token boundaries prevent DR-XD1000 from matching DR-XD1000PX.
        pattern = r"(?<![A-Z0-9])" + r"[\s\-./]*".join(map(re.escape, tokens)) + r"(?![A-Z0-9])"
        if any(re.search(pattern, line.upper()) for line in candidates):
            return True
    return False


def _original_match_count(pages, equipment_list):
    """Best original-only exact-hit count for any requested equipment."""
    from src.matching.guided_label_matcher import equipment_to_expected
    best = 0
    rows = [r for page in pages for r in page.get("ocr", [])]
    for equipment in equipment_list or []:
        expected = equipment_to_expected(equipment)
        count = sum(
            bool(_original_exact_hit(rows, field, expected.get(section, {}).get(field)))
            for section in ("unit", "tabung")
            for field in ("manufacturer", "type", "serial_number")
        )
        best = max(best, count)
    return best


def ocr_label_document(file_path, pdf_dpi=200, source_name=None, source_id=None,
                       equipment_list=None):
    return ocr_label_documents([{"path": file_path, "name": source_name,
                                "source_id": source_id}], pdf_dpi=pdf_dpi,
                               equipment_list=equipment_list)


def _ocr_worker(task):
    """Process-isolated PaddleOCR inference (one initialized engine per worker).

    Input: (image, variant). CPU model is loaded lazily once in each worker.
    """
    image, variant = task
    from src.extraction.label_ocr import extract_ocr
    if variant == "gray":
        import cv2
        from src.extraction.image_preprocess import ensure_bgr
        image = ensure_bgr(cv2.cvtColor(ensure_bgr(image), cv2.COLOR_BGR2GRAY))
    elif variant == "clahe":
        from src.extraction.image_preprocess import apply_clahe
        image = apply_clahe(image)
    rows = extract_ocr(image)
    return [{**row, "variant": variant, "rescanned": variant != "original"} for row in rows]


def _hpc_settings():
    """Opt-in because process spawning consumes additional RAM and model init."""
    import os
    enabled = os.getenv("BAPETEN_LABEL_PARALLEL", "0").strip().lower() in ("1", "true", "yes")
    workers = max(1, min(int(os.getenv("BAPETEN_LABEL_WORKERS", "4")), 16))
    return enabled and workers > 1, workers


def _parallel_ocr(tasks, workers, pool):
    """Preserve submitted task order and fail visibly (never hide OCR failure)."""
    from concurrent.futures import ProcessPoolExecutor
    import multiprocessing as mp
    import os
    if not tasks:
        return []
    # With spawn workers do not inherit Streamlit state or initialized Paddle.
    return list(pool.map(_ocr_worker, tasks))


def ocr_label_documents(documents, pdf_dpi=200, equipment_list=None):
    """One original OCR per page, ZERO-hit stop, then optional preprocessing.

    The zero-hit decision is only enabled when the caller supplies the current
    application's equipment list. Do not silently change legacy callers.
    """
    import os
    debug = os.environ.get("BAPETEN_LABEL_OCR_DEBUG", "").lower() in ("1", "true", "yes")
    import time
    start_time = time.perf_counter()
    pages = []
    for index, document in enumerate(documents):
        for item in prepare_label_document(document["path"], pdf_dpi=pdf_dpi):
            image = item["image"]
            panels = detect_sticker_panels(image) if item["source_type"] == "image" else []
            # Two physical labels in one photo must NOT share a page-level field
            # context. The original PDF page number remains unchanged.
            if panels:
                for panel_index,(xa,ya,xb,yb) in enumerate(panels, 1):
                    cropped = image[ya:yb,xa:xb].copy()
                    pages.append({
                        "source_id": document.get("source_id", index + 1),
                        "source_name": document.get("name") or f"dokumen_{index + 1}",
                        "source_type": item["source_type"], "page": item["page"],
                        "panel":panel_index,"panel_box":[xa,ya,xb,yb],
                        "width":cropped.shape[1],"height":cropped.shape[0],
                        "_image":cropped,
                    })
            else:
                pages.append({
                    "source_id": document.get("source_id", index + 1),
                    "source_name": document.get("name") or f"dokumen_{index + 1}",
                    "source_type": item["source_type"],
                    "page": item["page"], "width": item["width"], "height": item["height"],
                    "_image": image,
                })
    enabled, workers = _hpc_settings()
    if debug:
        print(f"[LABEL-PERF] pages={len(pages)} workers={workers if enabled else 1}", flush=True)
    import contextlib
    import multiprocessing as mp
    from concurrent.futures import ProcessPoolExecutor
    manager = (ProcessPoolExecutor(max_workers=workers, mp_context=mp.get_context("spawn"))
               if enabled else contextlib.nullcontext(None))
    with manager as pool:
        if enabled:
            original_results = _parallel_ocr([(p["_image"], "original") for p in pages], workers, pool)
        else:
            original_results = [_ocr_worker((p["_image"], "original")) for p in pages]
        for page, rows in zip(pages, original_results):
            page["ocr"] = augment_gs1_rows(rows)
        if debug:
            print(f"[LABEL-PERF] original={time.perf_counter()-start_time:.1f}s", flush=True)
        count = _original_match_count(pages, equipment_list) if equipment_list is not None else None
        if debug:
            print(f"[LABEL-GATE] original exact field MATCH count (best equipment): {count}", flush=True)
        # Zero hits can mean OCR missed a printed GS1 marker or small font.
        # Never report six MISMATCH values just because the primary OCR is empty.
        # Six verified exact hits need no expensive secondary OCR.
        retry_idx = ([] if count == 6 else
                     [i for i,page in enumerate(pages)
                      if (count == 0 or _needs_secondary_ocr(page["ocr"]))])
        if retry_idx:
            if enabled:
                # On 1-page documents grayscale and CLAHE are independent jobs.
                variants = ("gray", "clahe") if os.getenv("BAPETEN_LABEL_FULL_RETRIES","0")=="1" else ("gray",)
                tasks = [(pages[i]["_image"], variant) for i in retry_idx for variant in variants]
                results = _parallel_ocr(tasks, workers, pool)
                j = 0
                for i in retry_idx:
                    for variant in variants:
                        rows = results[j]
                        j += 1
                        pages[i]["ocr"].extend(augment_gs1_rows(rows))
                        if debug:
                            print(f"[LABEL-OCR] page={pages[i]['page']} {variant}: {len(rows)} baris", flush=True)
            else:
                for i in retry_idx:
                    page = pages[i]
                    variants = ("gray", "clahe") if os.getenv("BAPETEN_LABEL_FULL_RETRIES","0")=="1" else ("gray",)
                    for variant in variants:
                        found=_ocr_worker((page["_image"], variant))
                        page["ocr"].extend(augment_gs1_rows(found))
        for page in pages:
            page.pop("_image", None)
        if debug:
            print(f"[LABEL-PERF] total={time.perf_counter()-start_time:.1f}s", flush=True)
        return pages


def flatten_document_ocr(
    document_ocr,
):
    flattened = []

    for page_data in document_ocr:
        for item in page_data.get(
            "ocr",
            []
        ):
            flattened.append({
                "source_id":
                    page_data.get(
                        "source_id"
                    ),

                "source_name":
                    page_data.get(
                        "source_name"
                    ),

                "page":
                    page_data.get(
                        "page"
                    ),

                "text":
                    item.get(
                        "text"
                    ),

                "confidence":
                    item.get(
                        "confidence"
                    ),

                "box":
                    item.get(
                        "box"
                    ),
            })

    return flattened


def document_ocr_to_text(
    document_ocr,
):
    results = []

    for page_data in document_ocr:
        lines = []

        for item in page_data.get(
            "ocr",
            []
        ):
            text = item.get(
                "text"
            )

            if text:
                lines.append(
                    text
                )

        results.append({
            "source_id":
                page_data.get(
                    "source_id"
                ),

            "source_name":
                page_data.get(
                    "source_name"
                ),

            "page":
                page_data.get(
                    "page"
                ),

            "text":
                "\n".join(
                    lines
                ),
        })

    return results