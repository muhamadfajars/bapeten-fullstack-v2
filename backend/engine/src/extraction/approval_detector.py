import cv2
import numpy as np
import re


STRONG_APPROVAL_TEXT_PATTERNS = [
    r"ditandatangani\s+secara\s+elektronik",
    r"tanda\s+tangan\s+elektronik",
    r"telah\s+ditandatangani",
    r"ditandatangani",
    r"tanda\s+tangan",
    r"\bttd\b",
    r"disahkan",
    r"pengesahan",
]

CONTEXT_PATTERNS = [
    r"\bmengetahui\b",
    r"\bkepala\s+rumah\s+sakit\b",
    r"\bdirektur\s+rumah\s+sakit\b",
    r"\bkepala\s+instansi\b",
    r"\bpejabat\s+yang\s+berwenang\b",
]


def detect_qr_code(image):
    detector = cv2.QRCodeDetector()

    try:
        data, points, _ = detector.detectAndDecode(image)
    except Exception:
        return {
            "detected": False,
            "data": None,
        }

    return {
        "detected": points is not None,
        "data": data if data else None,
    }


def detect_barcode(image):
    try:
        detector = cv2.barcode_BarcodeDetector()
    except Exception:
        return {
            "detected": False,
            "values": [],
        }

    try:
        result = detector.detectAndDecode(image)
    except Exception:
        return {
            "detected": False,
            "values": [],
        }

    values = []

    if isinstance(result, tuple):
        for part in result:
            if isinstance(part, str):
                if part:
                    values.append(part)

            elif isinstance(part, (list, tuple)):
                for item in part:
                    if isinstance(item, str) and item:
                        values.append(item)

    return {
        "detected": bool(values),
        "values": values,
    }


def detect_approval_text(text):
    strong_matches = []
    context_matches = []

    for pattern in STRONG_APPROVAL_TEXT_PATTERNS:
        match = re.search(
            pattern,
            text,
            flags=re.IGNORECASE,
        )
        if match:
            strong_matches.append(match.group(0))

    for pattern in CONTEXT_PATTERNS:
        match = re.search(
            pattern,
            text,
            flags=re.IGNORECASE,
        )
        if match:
            context_matches.append(match.group(0))

    return {
        "strong_detected": bool(strong_matches),
        "context_detected": bool(context_matches),
        "strong_matches": strong_matches,
        "context_matches": context_matches,
    }


def get_search_region(image):
    if image is None:
        return None, None

    height, width = image.shape[:2]

    y_start = int(height * 0.50)

    search_region = image[
        y_start:height,
        0:width
    ].copy()

    offset = {
        "x": 0,
        "y": y_start,
    }

    return search_region, offset


def box_area(box):
    return max(0, box["w"]) * max(0, box["h"])


def box_center(box):
    return (
        box["x"] + box["w"] / 2,
        box["y"] + box["h"] / 2,
    )


def boxes_are_near(box_a, box_b, max_distance):
    ax, ay = box_center(box_a)
    bx, by = box_center(box_b)

    distance = ((ax - bx) ** 2 + (ay - by) ** 2) ** 0.5

    return distance <= max_distance


def find_signature_candidates(search_region):
    if search_region is None:
        return []

    gray = cv2.cvtColor(
        search_region,
        cv2.COLOR_BGR2GRAY,
    )

    gray = cv2.GaussianBlur(gray, (3, 3), 0)

    binary = cv2.adaptiveThreshold(
        gray,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV,
        31,
        15,
    )

    contours, _ = cv2.findContours(
        binary,
        cv2.RETR_EXTERNAL,
        cv2.CHAIN_APPROX_SIMPLE,
    )

    height, width = search_region.shape[:2]
    region_area = height * width

    candidates = []

    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        area = cv2.contourArea(contour)

        if area < 60:
            continue

        if w < 25 or h < 10:
            continue

        if w > width * 0.35:
            continue

        if h > height * 0.20:
            continue

        if (w * h) > region_area * 0.05:
            continue

        aspect_ratio = w / h if h else 0

        if aspect_ratio < 1.0 or aspect_ratio > 10.0:
            continue

        candidates.append({
            "x": x,
            "y": y,
            "w": w,
            "h": h,
            "area": round(float(area), 2),
        })

    return candidates


def find_stamp_candidates(search_region):
    if search_region is None:
        return []

    gray = cv2.cvtColor(
        search_region,
        cv2.COLOR_BGR2GRAY,
    )

    gray = cv2.GaussianBlur(
        gray,
        (5, 5),
        1.5,
    )

    height, width = gray.shape[:2]
    region_area = height * width

    min_radius = max(12, int(min(width, height) * 0.02))
    max_radius = max(min_radius + 1, int(min(width, height) * 0.10))

    circles = cv2.HoughCircles(
        gray,
        cv2.HOUGH_GRADIENT,
        dp=1.2,
        minDist=40,
        param1=120,
        param2=28,
        minRadius=min_radius,
        maxRadius=max_radius,
    )

    candidates = []

    if circles is not None:
        circles = np.round(circles[0]).astype(int)

        for x, y, radius in circles:
            w = radius * 2
            h = radius * 2

            if (w * h) > region_area * 0.04:
                continue

            candidates.append({
                "x": int(x - radius),
                "y": int(y - radius),
                "w": int(w),
                "h": int(h),
                "radius": int(radius),
                "area": float(np.pi * (radius ** 2)),
            })

    return candidates


def score_signature_candidate(box, search_region_shape):
    height, width = search_region_shape[:2]

    area_score = min(box_area(box) / 2500.0, 2.0)

    center_x, center_y = box_center(box)

    right_bonus = 1.0 if center_x >= width * 0.45 else 0.0
    lower_bonus = 0.5 if center_y >= height * 0.30 else 0.0

    return 4.0 + area_score + right_bonus + lower_bonus


def score_stamp_candidate(box, search_region_shape):
    height, width = search_region_shape[:2]

    area_score = min(box_area(box) / 3000.0, 1.5)

    center_x, center_y = box_center(box)

    right_bonus = 0.8 if center_x >= width * 0.45 else 0.0
    lower_bonus = 0.4 if center_y >= height * 0.25 else 0.0

    return 2.0 + area_score + right_bonus + lower_bonus


def select_primary_cluster(signature_candidates, stamp_candidates, search_region):
    if search_region is None:
        return None, [], []

    height, width = search_region.shape[:2]
    max_distance = min(width, height) * 0.22

    best_anchor = None
    best_type = None
    best_score = -1

    for signature in signature_candidates:
        score = score_signature_candidate(signature, search_region.shape)

        near_stamps = [
            stamp
            for stamp in stamp_candidates
            if boxes_are_near(signature, stamp, max_distance)
        ]

        if near_stamps:
            score += 1.5

        if score > best_score:
            best_score = score
            best_anchor = signature
            best_type = "signature"

    if best_anchor is None:
        for stamp in stamp_candidates:
            score = score_stamp_candidate(stamp, search_region.shape)

            if score > best_score:
                best_score = score
                best_anchor = stamp
                best_type = "stamp"

    if best_anchor is None:
        return None, [], []

    selected_signatures = []
    selected_stamps = []

    if best_type == "signature":
        selected_signatures.append(best_anchor)

        for stamp in stamp_candidates:
            if boxes_are_near(best_anchor, stamp, max_distance):
                selected_stamps.append(stamp)

    else:
        selected_stamps.append(best_anchor)

        for signature in signature_candidates:
            if boxes_are_near(best_anchor, signature, max_distance):
                selected_signatures.append(signature)

    all_boxes = selected_signatures + selected_stamps

    x1 = min(box["x"] for box in all_boxes)
    y1 = min(box["y"] for box in all_boxes)
    x2 = max(box["x"] + box["w"] for box in all_boxes)
    y2 = max(box["y"] + box["h"] for box in all_boxes)

    combined_box = {
        "x": int(x1),
        "y": int(y1),
        "w": int(x2 - x1),
        "h": int(y2 - y1),
    }

    return combined_box, selected_signatures, selected_stamps


def expand_box(
    box,
    image_width,
    image_height,
    horizontal_margin=0.18,
    top_margin=0.35,
    bottom_margin=0.45,
):
    if box is None:
        return None

    x = box["x"]
    y = box["y"]
    w = box["w"]
    h = box["h"]

    margin_x = int(w * horizontal_margin)
    margin_top = int(h * top_margin)
    margin_bottom = int(h * bottom_margin)

    x1 = max(0, x - margin_x)
    y1 = max(0, y - margin_top)
    x2 = min(image_width, x + w + margin_x)
    y2 = min(image_height, y + h + margin_bottom)

    return {
        "x": x1,
        "y": y1,
        "w": x2 - x1,
        "h": y2 - y1,
    }


def make_focused_crop(search_region, combined_box):
    if search_region is None or combined_box is None:
        return None, None

    height, width = search_region.shape[:2]

    expanded = expand_box(
        combined_box,
        image_width=width,
        image_height=height,
    )

    x = expanded["x"]
    y = expanded["y"]
    w = expanded["w"]
    h = expanded["h"]

    crop = search_region[
        y:y + h,
        x:x + w
    ].copy()

    return crop, expanded


def fallback_context_crop(search_region):
    if search_region is None:
        return None, None

    height, width = search_region.shape[:2]

    x1 = int(width * 0.55)
    y1 = int(height * 0.08)
    x2 = int(width * 0.98)
    y2 = int(height * 0.78)

    crop = search_region[
        y1:y2,
        x1:x2
    ].copy()

    box = {
        "x": x1,
        "y": y1,
        "w": x2 - x1,
        "h": y2 - y1,
    }

    return crop, box


def analyze_visual_approval(image):
    search_region, offset = get_search_region(image)

    if search_region is None:
        return {
            "detected": False,
            "signature": {},
            "stamp": {},
            "crop": None,
            "crop_box": None,
            "search_offset": None,
        }

    signature_candidates = find_signature_candidates(search_region)
    stamp_candidates = find_stamp_candidates(search_region)

    combined_box, selected_signatures, selected_stamps = select_primary_cluster(
        signature_candidates,
        stamp_candidates,
        search_region,
    )

    crop = None
    crop_box = None

    if combined_box is not None:
        crop, crop_box = make_focused_crop(
            search_region,
            combined_box,
        )

    if crop is None:
        crop, crop_box = fallback_context_crop(search_region)

    signature_detected = len(selected_signatures) >= 1
    stamp_detected = len(selected_stamps) >= 1
    detected = signature_detected or stamp_detected

    return {
        "detected": detected,
        "signature": {
            "detected": signature_detected,
            "candidate_count": len(selected_signatures),
            "candidates": selected_signatures[:10],
        },
        "stamp": {
            "detected": stamp_detected,
            "candidate_count": len(selected_stamps),
            "candidates": selected_stamps[:10],
        },
        "crop": crop,
        "crop_box": crop_box,
        "search_offset": offset,
    }


def approval_page_preview(page, max_width=1000):
    """Keep page context; never present a random document border as a signature.

    Visual previews are for human inspection only and are not authenticity proof.
    """
    image=page.get('image')
    if image is None:return None
    height,width=image.shape[:2]
    if width>max_width:
        image=cv2.resize(image,(max_width,max(1,round(height*max_width/width))),interpolation=cv2.INTER_AREA)
    return image

def _signing_context(page_text):
    """Signing authority near a signature; a generic QR is NOT such evidence."""
    value=str(page_text or '')
    explicit=bool(re.search(r'(?i)(?:tanda\s+tangan|\bttd\b|disetujui\s+oleh|approved\s+by|ditandatangani|mengetahui\s*[:,]|disahkan\s+oleh|pengesahan\s*[:])',value))
    signer=bool(re.search(r'(?i)\b(?:direktur\s*[:,]|kepala\s+(?:rumah\s+sakit|dinas|klinik)|a\.?n\.?\s+(?:direktur|kepala)|ketua\s+tim|penanggung\s+jawab|pengesahan\s*:|pejabat\s+penandatangan)',value))
    electronic=bool(re.search(r'(?i)(?:ditandatangani\s+secara\s+elektronik|tanda\s+tangan\s+elektronik|ttd\s+elektronik|tt\s+elektronik|electronically\s+signed|digital\s+signature|sertifikat\s+elektronik\s+(?:bsre|bssn))',value))
    return explicit,signer,electronic


def detect_approval(pages, text):
    """Conservative evidence-based approval status with full-page preview.

    QR/barcode can encode an unrelated regulation, identity, or lab sample;
    neither alone ever establishes approval. Image signatures are heuristic,
    always display the complete selected source page for evaluator inspection.
    """
    qr_results=[]
    barcode_results=[]
    visual_results=[]
    preview_candidates=[]
    all_pages=[]
    for index,page in enumerate(pages or []):
        image=page.get('image')
        lines=[str(row.get('text') or '') for row in (page.get('ocr') or [])]
        page_text=(str(page.get('native_text') or '')+'\n'+'\n'.join(lines)).strip()
        exp,signer,electronic=_signing_context(page_text)
        if image is not None:
            qr=detect_qr_code(image)
            barcode=detect_barcode(image)
            visual=analyze_visual_approval(image)
        else:
            qr={'detected':False,'data':None}
            barcode={'detected':False,'values':[]}
            visual={'detected':False,'signature':{},'stamp':{}}
        if qr.get('detected'):qr_results.append({'page':page.get('page'),**qr})
        if barcode.get('detected'):barcode_results.append({'page':page.get('page'),**barcode})
        if visual.get('detected'):visual_results.append({'page':page.get('page'),**visual})
        all_pages.append((page,exp,signer,electronic,bool(visual.get('detected'))))

    full_text=str(text or '')
    explicit,signer,electronic=_signing_context(full_text)
    # DOCX native fallback: the signature image is an embedded-media pseudo
    # page, separated from the paragraph containing 'Direktur'. Require the
    # entire source to have signer context AND real visual evidence.
    found_electronic=any(row[3] for row in all_pages) or electronic
    has_signer=any(row[2] for row in all_pages) or signer
    strong_visual=[]
    for index,(page,exp,signed,esig,visual_hit) in enumerate(all_pages):
        if page.get('image') is None:continue
        is_docx_image=page.get('source_type')=='docx-image'
        context=exp or signed
        if (visual_hit and context) or esig or (is_docx_image and visual_hit and has_signer):
            # Do not prefer a QR-only appendix to an actual signing page.
            rank=(100 if esig else 50 if exp and visual_hit else 35 if signed and visual_hit else 22)
            # Later pages are usually the signature page when scores tie.
            preview_candidates.append((rank,index,page))
        if visual_hit and (context or (is_docx_image and has_signer)):
            strong_visual.append(page)
    if found_electronic and not preview_candidates:
        # Text statements without attached page context can be used, but
        # choose the relevant source page if available rather than first QR.
        for idx,(page,exp,signed,esig,_) in enumerate(all_pages):
            if page.get('image') is not None and (exp or signed or esig):
                preview_candidates.append((30 if esig else 12,idx,page))
    # Text-only claims may be forged / quoted in a regulation, so explicit
    # electronic context additionally needs a responsible signer reference.
    detected=bool(strong_visual) or bool(found_electronic and has_signer)
    preview_candidates.sort(key=lambda item:(item[0],item[1]),reverse=True)
    selected=preview_candidates[0][2] if preview_candidates else None
    # If not enough evidence for a MATCH, still let the evaluator inspect
    # the most likely signature-context page (not a random barcode page).
    if selected is None:
        for idx,(page,exp,signed,esig,vis) in reversed(list(enumerate(all_pages))):
            if page.get('image') is not None and (exp or signed):
                selected=page;break
    if selected is None and found_electronic and has_signer:
        # Native Word/pdf text may survive even when per-page extraction is
        # empty; keep a human-auditable page, never choose it based on barcode.
        selected=next((p for p in reversed(pages or []) if p.get('image') is not None),None)
    preview=approval_page_preview(selected) if selected is not None else None
    return {
        'status':'DETECTED' if detected else 'REVIEW',
        'page_preview':preview,
        'page_preview_number':selected.get('page') if selected is not None else None,
        'evidence_count':int(bool(strong_visual))+int(bool(found_electronic and has_signer)),
        'qr_codes':qr_results,
        'barcodes':barcode_results,
        'visual_evidence':visual_results,
        'text_evidence':detect_approval_text(full_text),
        'note':('Indikasi pengesahan pada halaman sumber; pemeriksaan keaslian '
                'tanda tangan atau stempel tetap dilakukan evaluator. '
                'QR/barcode sendiri tidak dihitung sebagai pengesahan.'),
    }
