from src.extraction.image_preprocess import (
    create_ocr_variants,
)

from src.extraction.label_ocr import (
    extract_ocr,
)

from src.extraction.label_parser import (
    parse_unit_label,
    parse_tube_label,
)


# =========================================================
# PARSER WRAPPER
# =========================================================

def parse_label(
    ocr_results,
    label_type
):
    if label_type == "unit":
        return parse_unit_label(
            ocr_results
        )

    if label_type == "tube":
        return parse_tube_label(
            ocr_results
        )

    raise ValueError(
        "label_type harus 'unit' atau 'tube'"
    )


# =========================================================
# HELPER
# =========================================================

def get_type_data(
    parsed,
    label_type
):
    if label_type == "unit":
        return parsed.get(
            "unit_type",
            {}
        )

    return parsed.get(
        "tube_type",
        {}
    )


def is_valid_value(value):
    if value is None:
        return False

    value = str(value).strip()

    if not value:
        return False

    return True


# =========================================================
# SCORE RESULT
# =========================================================

def score_extraction(
    parsed,
    label_type
):
    """
    Score maksimum kurang lebih 6.

    Setiap field:
    +1 jika ditemukan
    +confidence OCR jika tersedia

    manufacturer
    type
    serial
    """

    score = 0.0


    # -----------------------------------------------------
    # MANUFACTURER
    # -----------------------------------------------------

    manufacturer = parsed.get(
        "manufacturer"
    )

    if manufacturer:

        normalized = manufacturer.get(
            "normalized"
        )

        if is_valid_value(normalized):

            score += 1.0

            confidence = manufacturer.get(
                "confidence"
            )

            if confidence is not None:
                score += float(
                    confidence
                )


    # -----------------------------------------------------
    # TYPE
    # -----------------------------------------------------

    type_data = get_type_data(
        parsed,
        label_type
    )

    type_value = type_data.get(
        "value"
    )

    if is_valid_value(
        type_value
    ):

        score += 1.0

        confidence = type_data.get(
            "confidence"
        )

        if confidence is not None:
            score += float(
                confidence
            )


    # -----------------------------------------------------
    # SERIAL
    # -----------------------------------------------------

    serial_data = parsed.get(
        "serial_number",
        {}
    )

    serial_value = serial_data.get(
        "value"
    )

    if is_valid_value(
        serial_value
    ):

        score += 1.0

        confidence = serial_data.get(
            "confidence"
        )

        if confidence is not None:
            score += float(
                confidence
            )


    return score


# =========================================================
# CHECK COMPLETENESS
# =========================================================

def is_complete(
    parsed,
    label_type
):
    """
    Hasil dianggap lengkap jika:
    manufacturer + type + serial tersedia.
    """

    manufacturer = parsed.get(
        "manufacturer"
    )

    if not manufacturer:
        return False


    manufacturer_value = manufacturer.get(
        "normalized"
    )

    type_data = get_type_data(
        parsed,
        label_type
    )

    serial_data = parsed.get(
        "serial_number",
        {}
    )


    return all([
        is_valid_value(
            manufacturer_value
        ),

        is_valid_value(
            type_data.get("value")
        ),

        is_valid_value(
            serial_data.get("value")
        ),
    ])


# =========================================================
# CONFIDENCE CHECK
# =========================================================

def minimum_confidence(
    parsed,
    label_type
):
    """
    Ambil confidence terendah dari 3 field utama.

    Jika salah satu confidence None,
    abaikan field tersebut dalam minimum.
    """

    confidences = []


    manufacturer = parsed.get(
        "manufacturer"
    )

    if manufacturer:

        confidence = manufacturer.get(
            "confidence"
        )

        if confidence is not None:
            confidences.append(
                float(confidence)
            )


    type_data = get_type_data(
        parsed,
        label_type
    )

    confidence = type_data.get(
        "confidence"
    )

    if confidence is not None:
        confidences.append(
            float(confidence)
        )


    serial_data = parsed.get(
        "serial_number",
        {}
    )

    confidence = serial_data.get(
        "confidence"
    )

    if confidence is not None:
        confidences.append(
            float(confidence)
        )


    if not confidences:
        return 0.0


    return min(
        confidences
    )


# =========================================================
# AUTO EXTRACTION
# =========================================================

def extract_label_auto(
    image_path,
    label_type,
    crop_config=None,
    confidence_threshold=0.90
):

    variants = create_ocr_variants(
        image_path,
        crop_config=crop_config
    )

    method_order = [
        "original",
        "crop",
        "crop_upscaled",
        "crop_upscaled_clahe",
        "crop_upscaled_clahe_sharpen",
    ]

    candidates = []

    best_method = None
    best_score = -1
    best_result = None
    best_ocr = None


    for method in method_order:

        if method not in variants:
            continue


        image = variants[
            method
        ]


        # OCR
        ocr_results = extract_ocr(
            image
        )


        # Parser
        parsed = parse_label(
            ocr_results,
            label_type
        )


        # Score
        score = score_extraction(
            parsed,
            label_type
        )

        complete = is_complete(
            parsed,
            label_type
        )

        min_conf = minimum_confidence(
            parsed,
            label_type
        )


        candidate = {
            "method":
                method,

            "score":
                score,

            "complete":
                complete,

            "minimum_confidence":
                min_conf,

            "result":
                parsed,

            "ocr_results":
                ocr_results,
        }


        candidates.append(
            candidate
        )


        if score > best_score:

            best_score = score
            best_method = method
            best_result = parsed
            best_ocr = ocr_results


    return {
        "method":
            best_method,

        "score":
            best_score,

        "result":
            best_result,

        "ocr_results":
            best_ocr,

        "candidates":
            candidates,
    }