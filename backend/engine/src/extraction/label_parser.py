import re
from rapidfuzz import fuzz

# =========================================================
# MANUFACTURER ALIASES
# =========================================================

MANUFACTURER_ALIASES = {
    "GE": [
        "GENERAL ELECTRIC COMPANY",
        "GENERAL ELECTRIC",
        "GE MEDICAL SYSTEMS",
        "GE HEALTHCARE",
    ],

    "CANON": [
        "CANON ELECTRON TUBES & DEVICES CO., LTD.",
        "CANON ELECTRON TUBES & DEVICES",
        "CANON ELECTRON TUBES AND DEVICES",
        "CANON",
    ],

    "PHILIPS": [
        "PHILIPS",
        "PHILIPS MEDICAL SYSTEMS",
        "PHILIPS MEDICAL SYSTEMS DMC GMBH",
    ],

    "SIEMENS": [
        "SIEMENS",
        "SIEMENS HEALTHINEERS",
        "SIEMENS MEDICAL",
    ],

    "TOSHIBA": [
        "TOSHIBA",
        "TOSHIBA CORPORATION",
    ],

    "SHIMADZU": [
        "SHIMADZU",
        "SHIMADZU CORPORATION",
    ],
}


# =========================================================
# BASIC HELPERS
# =========================================================

def normalize_text(text):
    if not text:
        return None

    text = str(text).strip()

    text = re.sub(
        r"\s+",
        " ",
        text
    )

    return text


def normalize_serial(value):
    if not value:
        return None

    value = normalize_text(value)

    # serial biasanya tidak perlu spasi
    value = re.sub(
        r"\s+",
        "",
        value
    )

    return value.upper()


def normalize_manufacturer(text):
    if not text:
        return None

    upper = normalize_text(text).upper()

    for canonical, aliases in MANUFACTURER_ALIASES.items():

        for alias in aliases:

            if alias.upper() in upper:
                return canonical

    return upper


def clean_unit_type(value):
    """
    Contoh:
    OPTIMA XR200AMX 30KW
    ->
    OPTIMA XR200AMX
    """

    if not value:
        return None

    value = normalize_text(value)

    value = re.sub(
        r"\s+\d+(?:[.,]\d+)?\s*KW\s*$",
        "",
        value,
        flags=re.IGNORECASE
    )

    return value.strip()


def get_texts(ocr_results):
    return [
        item["text"].strip()
        for item in ocr_results
        if item.get("text")
    ]


def find_result_by_text(
    ocr_results,
    target_text
):
    """
    Mencari OCR item yang text-nya sama persis.
    Berguna untuk mengambil confidence.
    """

    target_text = target_text.strip().upper()

    for item in ocr_results:

        text = item.get(
            "text",
            ""
        ).strip().upper()

        if text == target_text:
            return item

    return None


def find_manufacturer(
    ocr_results
):
    """
    Cari manufacturer berdasarkan alias.
    """

    best_match = None

    for item in ocr_results:

        text = item.get(
            "text",
            ""
        )

        upper = text.upper()

        for canonical, aliases in MANUFACTURER_ALIASES.items():

            for alias in aliases:

                if alias.upper() in upper:

                    candidate = {
                        "raw": text,
                        "normalized": canonical,
                        "confidence": float(
                            item.get(
                                "confidence",
                                0
                            )
                        )
                    }

                    if (
                        best_match is None
                        or candidate["confidence"]
                        > best_match["confidence"]
                    ):
                        best_match = candidate

    return best_match


# =========================================================
# GENERIC ANCHOR HELPERS
# =========================================================

def find_value_after_anchor(
    ocr_results,
    anchors,
    max_distance=2,
    fuzzy=False,
    fuzzy_threshold=75
):
    """
    Cari value berdasarkan anchor.

    Bisa exact match maupun fuzzy match.
    """

    texts = get_texts(
        ocr_results
    )


    for i, text in enumerate(texts):

        upper = text.upper()


        for anchor in anchors:

            anchor_upper = anchor.upper()


            # =================================================
            # EXACT MATCH
            # =================================================

            exact_match = (
                anchor_upper in upper
            )


            # =================================================
            # FUZZY MATCH
            # =================================================

            fuzzy_match = False

            if fuzzy:

                fuzzy_match = fuzzy_anchor_match(
                    text,
                    anchor,
                    threshold=fuzzy_threshold
                )


            if not (
                exact_match
                or fuzzy_match
            ):
                continue


            # =================================================
            # VALUE DALAM BARIS YANG SAMA
            # =================================================

            # Hanya lakukan regex same-line
            # jika exact anchor benar-benar ditemukan.
            if exact_match:

                escaped = re.escape(
                    anchor
                )

                pattern = (
                    escaped
                    + r"\s*:?\s*(.+)$"
                )


                match = re.search(
                    pattern,
                    text,
                    flags=re.IGNORECASE
                )


                if match:

                    value = match.group(
                        1
                    ).strip()


                    # Jangan terima value hanya berupa simbol
                    if (
                        value
                        and
                        re.search(
                            r"[A-Z0-9]",
                            value,
                            flags=re.IGNORECASE
                        )
                    ):

                        return {
                            "value":
                                value,

                            "anchor":
                                text,

                            "index":
                                i,

                            "match_type":
                                "exact"
                        }


            # =================================================
            # VALUE DI BARIS BERIKUTNYA
            # =================================================

            for offset in range(
                1,
                max_distance + 1
            ):

                next_index = (
                    i + offset
                )


                if next_index >= len(
                    texts
                ):
                    break


                candidate = texts[
                    next_index
                ].strip()


                if (
                    candidate
                    and
                    re.search(
                        r"[A-Z0-9]",
                        candidate,
                        flags=re.IGNORECASE
                    )
                ):

                    return {
                        "value":
                            candidate,

                        "anchor":
                            text,

                        "index":
                            i,

                        "match_type":
                            (
                                "exact"
                                if exact_match
                                else "fuzzy"
                            )
                    }


    return None


def find_serial_after_index(
    ocr_results,
    start_index,
    max_distance=8
):
    """
    Cari serial setelah anchor tipe/model.

    Mendukung:
    - SER. NO.: 0F1376
    - SERIAL-NO: 12345
    - S/N: ABC123

    maupun format dua baris:
    SERIAL-NO
    377289
    """

    texts = get_texts(
        ocr_results
    )

    end = min(
        len(texts),
        start_index
        + max_distance
        + 1
    )


    # =====================================================
    # ANCHOR SERIAL YANG BERDIRI SENDIRI
    # =====================================================

    serial_anchor_patterns = [
        r"SERIAL[\s\-]*NO\.?",
        r"SER\.?\s*NO\.?",
        r"S/N",
        r"S\.N\.?",
        r"SN",
    ]


    for i in range(
        start_index + 1,
        end
    ):

        text = texts[i].strip()


        # =================================================
        # 1. CEK APAKAH BARIS INI HANYA ANCHOR
        #
        # Contoh:
        #
        # SERIAL-NO
        # 377289
        # =================================================

        is_anchor_only = False

        for anchor_pattern in (
            serial_anchor_patterns
        ):

            if re.fullmatch(
                anchor_pattern,
                text,
                flags=re.IGNORECASE
            ):

                is_anchor_only = True
                break


        if is_anchor_only:

            if i + 1 < len(texts):

                candidate = texts[
                    i + 1
                ].strip()

                # Kandidat harus mengandung
                # minimal huruf atau angka
                if (
                    candidate
                    and
                    re.search(
                        r"[A-Z0-9]",
                        candidate,
                        flags=re.IGNORECASE
                    )
                ):

                    return {
                        "value":
                            candidate,

                        "text":
                            candidate,

                        "index":
                            i + 1
                    }


        # =================================================
        # 2. SERIAL DAN VALUE DALAM SATU BARIS
        #
        # Contoh:
        #
        # SER. NO.: 0F1376
        # SERIAL-NO: ABC123
        # =================================================

        same_line_pattern = (
            r"(?:"
            r"SERIAL[\s\-]*NO\.?"
            r"|SER\.?\s*NO\.?"
            r"|S/N"
            r"|S\.N\.?"
            r"|SN"
            r")"
            r"\s*:?\s*"
            r"([A-Z0-9][A-Z0-9._/-]*)"
        )


        match = re.fullmatch(
            same_line_pattern,
            text,
            flags=re.IGNORECASE
        )


        if match:

            candidate = match.group(
                1
            ).strip()


            # Tambahan proteksi
            if candidate.upper() not in {
                "NO",
                "N",
                "SN"
            }:

                return {
                    "value":
                        candidate,

                    "text":
                        text,

                    "index":
                        i
                }


    return None


# =========================================================
# UNIT LABEL
# =========================================================

def parse_unit_label(
    ocr_results
):

    manufacturer = find_manufacturer(
        ocr_results
    )


    # =============================================
    # UNIT TYPE
    # =============================================

    unit_type_result = find_value_after_anchor(
        ocr_results,
        anchors=[
            "DESC",
            "SYSTEM MODEL",
            "PRODUCT MODEL",
            "MODEL NAME",
        ]
    )


    unit_type = None
    unit_type_confidence = None


    if unit_type_result:

        raw_type = unit_type_result[
            "value"
        ]

        unit_type = clean_unit_type(
            raw_type
        )

        result_item = find_result_by_text(
            ocr_results,
            raw_type
        )

        if result_item:
            unit_type_confidence = float(
                result_item.get(
                    "confidence",
                    0
                )
            )


    # =============================================
    # UNIT SERIAL
    # =============================================

    texts = get_texts(
        ocr_results
    )

    serial = None
    serial_confidence = None


    for i, text in enumerate(texts):

        upper = text.upper()

        if upper in {
            "S/N",
            "SN",
            "SERIAL",
            "SERIAL NO",
            "SERIAL-NO"
        }:

            if i + 1 < len(texts):

                candidate = texts[
                    i + 1
                ]

                if re.fullmatch(
                    r"[A-Z0-9._/-]+",
                    candidate.upper()
                ):

                    serial = normalize_serial(
                        candidate
                    )

                    result_item = (
                        find_result_by_text(
                            ocr_results,
                            candidate
                        )
                    )

                    if result_item:

                        serial_confidence = float(
                            result_item.get(
                                "confidence",
                                0
                            )
                        )

                    break


    return {
        "manufacturer": manufacturer,

        "unit_type": {
            "value": unit_type,
            "confidence":
                unit_type_confidence
        },

        "serial_number": {
            "value": serial,
            "confidence":
                serial_confidence
        }
    }


# =========================================================
# TUBE LABEL
# =========================================================

def parse_tube_label(
    ocr_results
):

    manufacturer = find_manufacturer(
        ocr_results
    )


    tube_type_result = find_value_after_anchor(
        ocr_results,
        anchors=[
            "INSERT MODEL",
            "TUBE REF/MODEL",
            "TUBE REF / MODEL",
            "TUBE MODEL",
            "X-RAY TUBE MODEL",
        ],
        max_distance=2,
        fuzzy=False
    )

    if not tube_type_result:

        tube_type_result = find_value_after_anchor(
            ocr_results,
            anchors=[
                "ROHR/TUBE",
                "ROHRE/TUBE",
                "RÖHRE/TUBE",
            ],
            max_distance=2,
            fuzzy=True,
            fuzzy_threshold=70
        )
        
    if not tube_type_result:

        tube_type_result = find_value_after_anchor(
            ocr_results,
            anchors=[
                "PN/SN",
                "PN / SN",
                "P/N",
            ],
            max_distance=1,
            fuzzy=True,
            fuzzy_threshold=90
        )


    tube_type = None
    tube_type_confidence = None
    type_anchor_index = None


    if tube_type_result:

        tube_type = normalize_text(
            tube_type_result[
                "value"
            ]
        )

        type_anchor_index = (
            tube_type_result[
                "index"
            ]
        )


        result_item = find_result_by_text(
            ocr_results,
            tube_type
        )


        if result_item:

            tube_type_confidence = float(
                result_item.get(
                    "confidence",
                    0
                )
            )


    # =============================================
    # SERIAL NUMBER
    # =============================================

    serial = None
    serial_confidence = None


    if type_anchor_index is not None:

        serial_result = (
            find_serial_after_index(
                ocr_results,
                type_anchor_index,
                max_distance=8
            )
        )


        if serial_result:

            serial = normalize_serial(
                serial_result[
                    "value"
                ]
            )


            result_item = find_result_by_text(
                ocr_results,
                serial_result[
                    "text"
                ]
            )


            if result_item:

                serial_confidence = float(
                    result_item.get(
                        "confidence",
                        0
                    )
                )


    # =============================================
    # CANDIDATE FIELDS
    #
    # Berguna untuk Siemens / label kompleks.
    # =============================================

    candidates = {}


    model_number = find_value_after_anchor(
        ocr_results,
        anchors=[
            "MODEL-NO",
            "MODEL-NO.",
            "MODEL NO",
            "MODEL NUMBER",
        ],
        max_distance=2
    )


    if model_number:

        candidates[
            "model_number"
        ] = model_number[
            "value"
        ]


    return {

        "manufacturer":
            manufacturer,

        "tube_type": {
            "value":
                tube_type,

            "confidence":
                tube_type_confidence
        },

        "serial_number": {
            "value":
                serial,

            "confidence":
                serial_confidence
        },

        "candidates":
            candidates
    }
    
    candidates = {}


    if tube_type_result:

        anchor_text = (
            tube_type_result.get(
                "anchor",
                ""
            ).upper()
        )

        if (
            "PN/SN" in anchor_text
            or
            "PN / SN" in anchor_text
        ):

            candidates[
                "part_number"
            ] = tube_type

def normalize_anchor_text(text):
    """
    Normalisasi sederhana untuk membandingkan anchor OCR.

    Contoh:
    RöhraTube
    RöHRE/Tube
    Rohr Tube

    menjadi bentuk yang lebih mudah dibandingkan.
    """

    if not text:
        return ""

    text = text.upper()

    # Normalisasi umlaut
    text = (
        text
        .replace("Ö", "O")
        .replace("Ä", "A")
        .replace("Ü", "U")
    )

    # Buang karakter non alfanumerik
    text = re.sub(
        r"[^A-Z0-9]",
        "",
        text
    )

    return text


def fuzzy_anchor_match(
    text,
    anchor,
    threshold=75
):
    """
    Membandingkan text OCR dengan anchor secara fuzzy.
    """

    text_norm = normalize_anchor_text(
        text
    )

    anchor_norm = normalize_anchor_text(
        anchor
    )

    score = fuzz.ratio(
        text_norm,
        anchor_norm
    )

    return score >= threshold