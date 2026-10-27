import re
import unicodedata

from rapidfuzz import fuzz


OCR_AMBIGUITY_GROUPS = [
    {"0", "O"},
    {"1", "I", "L"},
    {"5", "S"},
    {"8", "B"},
    {"2", "Z"},
]


def normalize_text(value):
    if value is None:
        return ""

    value = unicodedata.normalize(
        "NFKC",
        str(value),
    )

    value = value.upper()

    value = re.sub(
        r"[^A-Z0-9]+",
        " ",
        value,
    )

    value = re.sub(
        r"\s+",
        " ",
        value,
    )

    return value.strip()


def compact_text(value):
    return re.sub(
        r"[^A-Z0-9]",
        "",
        normalize_text(value),
    )

def normalize_serial_candidate(
    value,
):
    if value is None:
        return ""

    value = str(
        value
    ).strip()

    value = re.sub(
        r"^\s*\(\s*21\s*\)\s*",
        "",
        value,
        flags=re.IGNORECASE,
    )

    value = re.sub(
        r"^\s*"
        r"(?:"
        r"SER(?:IAL)?\.?\s*NO\.?"
        r"|SERIAL(?:\s+NUMBER)?"
        r"|S/N"
        r"|SN"
        r")"
        r"\s*[:#.\-]?\s*",
        "",
        value,
        flags=re.IGNORECASE,
    )

    return compact_text(
        value
    )


def is_serial_labeled_line(
    value,
):
    if not value:
        return False

    value = str(value).strip()

    return bool(
        re.search(
            r"^\s*"
            r"(?:"
            r"\(\s*21\s*\)"
            r"|SER(?:IAL)?\.?\s*NO\.?"
            r"|SERIAL(?:\s+NUMBER)?"
            r"|S/N"
            r"|SN"
            r")",
            value,
            flags=re.IGNORECASE,
        )
    )


def split_expected_type(value):
    if not value:
        return []

    parts = re.split(
        r"\s*/\s*",
        str(value),
    )

    return [
        part.strip()
        for part in parts
        if part.strip()
    ]


def same_ocr_ambiguity_group(
    left,
    right,
):
    for group in OCR_AMBIGUITY_GROUPS:
        if (
            left in group
            and right in group
        ):
            return True

    return False


def serial_ocr_ambiguity(
    expected,
    candidate,
):
    expected = compact_text(
        expected
    )

    candidate = compact_text(
        candidate
    )

    if (
        not expected
        or not candidate
        or len(expected) != len(candidate)
    ):
        return False

    ambiguity_groups = [
        {"0", "O"},
        {"1", "I", "L"},
        {"5", "S"},
        {"8", "B"},
        {"2", "Z"},
        {"6", "G"},
    ]

    differences = 0

    for left, right in zip(
        expected,
        candidate,
    ):
        if left == right:
            continue

        is_ambiguous = any(
            left in group
            and right in group
            for group in ambiguity_groups
        )

        if is_ambiguous:
            differences += 1
            continue

        return False

    return differences > 0


def get_source_metadata(
    page_data,
):
    return {
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
    }


def find_exact_line(
    expected,
    page_data,
):
    expected_normalized = (
        normalize_text(
            expected
        )
    )

    expected_compact = (
        compact_text(
            expected
        )
    )

    if not expected_normalized:
        return None

    for item in page_data.get(
        "ocr",
        []
    ):
        candidate = item.get(
            "text"
        )

        if not candidate:
            continue

        candidate_normalized = (
            normalize_text(
                candidate
            )
        )

        candidate_compact = (
            compact_text(
                candidate
            )
        )

        if (
            candidate_normalized
            == expected_normalized
        ):
            return candidate

        if (
            candidate_compact
            == expected_compact
        ):
            return candidate

    return None


def find_contained_line(
    expected,
    page_data,
):
    expected_normalized = (
        normalize_text(
            expected
        )
    )

    expected_compact = (
        compact_text(
            expected
        )
    )

    if not expected_normalized:
        return None

    pattern = (
        r"(?:^|\s)"
        + re.escape(
            expected_normalized
        )
        + r"(?:\s|$)"
    )

    for item in page_data.get(
        "ocr",
        []
    ):
        candidate = item.get(
            "text"
        )

        if not candidate:
            continue

        candidate_normalized = (
            normalize_text(
                candidate
            )
        )

        candidate_compact = (
            compact_text(
                candidate
            )
        )

        if re.search(
            pattern,
            candidate_normalized,
        ):
            return candidate

        if (
            len(expected_compact) >= 4
            and expected_compact
            in candidate_compact
        ):
            return candidate

    return None


def find_best_fuzzy_line(
    expected,
    page_data,
):
    expected_normalized = (
        normalize_text(
            expected
        )
    )

    if not expected_normalized:
        return {
            "score": 0.0,
            "text": None,
        }

    best_score = 0.0
    best_text = None

    minimum_length = max(
        3,
        int(
            len(
                expected_normalized
            )
            * 0.4
        ),
    )

    for item in page_data.get(
        "ocr",
        []
    ):
        candidate = item.get(
            "text"
        )

        if not candidate:
            continue

        candidate_normalized = (
            normalize_text(
                candidate
            )
        )

        if not candidate_normalized:
            continue

        if (
            len(
                candidate_normalized
            )
            < minimum_length
        ):
            continue

        score = max(
            fuzz.ratio(
                expected_normalized,
                candidate_normalized,
            ),
            fuzz.token_set_ratio(
                expected_normalized,
                candidate_normalized,
            ),
        )

        if score > best_score:
            best_score = score
            best_text = candidate

    return {
        "score":
            round(
                best_score,
                2,
            ),

        "text":
            best_text,
    }


def match_simple_field_on_page(
    expected,
    page_data,
    fuzzy_threshold=90,
):
    metadata = get_source_metadata(
        page_data
    )

    if not expected:
        return {
            "status":
                "MISSING",

            "expected":
                expected,

            "evidence":
                None,

            "score":
                0.0,

            **metadata,
        }

    evidence = find_exact_line(
        expected,
        page_data,
    )

    if evidence:
        return {
            "status":
                "MATCH",

            "expected":
                expected,

            "evidence":
                evidence,

            "score":
                100.0,

            **metadata,
        }

    evidence = find_contained_line(
        expected,
        page_data,
    )

    if evidence:
        return {
            "status":
                "MATCH",

            "expected":
                expected,

            "evidence":
                evidence,

            "score":
                100.0,

            **metadata,
        }

    fuzzy = find_best_fuzzy_line(
        expected,
        page_data,
    )

    if (
        fuzzy["score"]
        >= fuzzy_threshold
    ):
        status = "REVIEW"

    else:
        status = "MISMATCH"

    return {
        "status":
            status,

        "expected":
            expected,

        "evidence":
            fuzzy["text"],

        "score":
            fuzzy["score"],

        **metadata,
    }


def _match_parenthetical_type(expected, page_data):
    """Respect model aliases explicitly provided by the form, not suffix guessing."""
    if not expected or '(' not in str(expected) or ')' not in str(expected):
        return None
    raw = str(expected)
    primary = raw[:raw.index('(')].strip()
    alias = raw[raw.index('(') + 1:raw.rindex(')')].strip()
    variants = [x for x in (primary, alias) if x]
    if not variants:
        return None
    meta = get_source_metadata(page_data)
    items = [str(x.get('text', '')) for x in page_data.get('ocr', [])]
    for variant in variants:
        # Contiguous model codes may be split by spaces/hyphens in OCR.
        tokens = re.findall(r'[A-Za-z0-9]+', variant)
        if not tokens: continue
        pattern = r'(?<![A-Za-z0-9])' + r'[\s\-]*'.join(map(re.escape, tokens)) + r'(?![A-Za-z0-9])'
        for line in items:
            match = re.search(pattern, line, re.I)
            if match:
                return {'status':'MATCH', 'expected':expected,
                        'components':[{'component':variant,'found':True,'score':100.0,
                                       'evidence':match.group(0), 'variant':next((x.get('variant', 'original') for x in page_data.get('ocr', []) if str(x.get('text', '')) == line), 'original')}], **meta}
    # Keep true model extensions visible: DR-XD1000PX is not DR-XD1000.
    closest = max((fuzz.ratio(compact_text(v), compact_text(line)) for v in variants
                   for line in items if line), default=0.0)
    near = None
    for line in items:
        for v in variants:
            if compact_text(v) and compact_text(v) in compact_text(line):
                near = line
                break
        if near: break
    if near:
        return {'status':'REVIEW','expected':expected,
                'components':[{'component':primary,'found':False,'score':closest,
                               'evidence':near}],
                'reason':'Kode model memiliki sufiks/varian tambahan, perlu verifikasi', **meta}
    return None


def match_type_field_on_page(
    expected,
    page_data,
):
    parenthetical_result = _match_parenthetical_type(expected, page_data)
    if parenthetical_result is not None:
        return parenthetical_result

    metadata = get_source_metadata(
        page_data
    )

    if not expected:
        return {
            "status": "MISSING",
            "expected": expected,
            "components": [],
            **metadata,
        }

    components = split_expected_type(
        expected
    )

    ocr_items = page_data.get(
        "ocr",
        [],
    )

    # A full compound model may be printed on one row (e.g. KL10-0.6/1.8-125).
    # First compare the WHOLE code, not pieces independently; no suffix deletion.
    normalized_expected = compact_text(expected)
    if normalized_expected and not ('(' in str(expected) and ')' in str(expected)):
        for item in ocr_items:
            raw = str(item.get("text") or "")
            extracted = normalize_type_candidate(raw)
            if compact_text(extracted) == normalized_expected:
                return {"status": "MATCH", "expected": expected,
                        "components": [{"component": expected, "found": True,
                                        "score": 100.0, "evidence": extracted}], **metadata}

    component_results = []

    for component in components:

        component_normalized = (
            normalize_text(
                component
            )
        )

        component_compact = (
            compact_text(
                component
            )
        )

        found_result = None

        # 1. Prioritaskan line yang memang punya label MODEL/TYPE
        for item in ocr_items:

            candidate = item.get(
                "text"
            )

            if not candidate:
                continue

            if not is_type_labeled_line(
                candidate
            ):
                continue

            candidate_value = (
                normalize_type_candidate(
                    candidate
                )
            )

            candidate_compact = (
                compact_text(
                    candidate_value
                )
            )

            if (
                candidate_value
                == component_normalized
                or candidate_compact
                == component_compact
            ):

                found_result = {
                    "component":
                        component,

                    "found":
                        True,

                    "score":
                        100.0,

                    "evidence":
                        candidate,
                }

                break

        if found_result:
            component_results.append(
                found_result
            )
            continue

        # 2. Exact OCR line
        for item in ocr_items:

            candidate = item.get(
                "text"
            )

            if not candidate:
                continue

            candidate_normalized = (
                normalize_text(
                    candidate
                )
            )

            candidate_compact = (
                compact_text(
                    candidate
                )
            )

            if (
                candidate_normalized
                == component_normalized
                or candidate_compact
                == component_compact
            ):

                found_result = {
                    "component":
                        component,

                    "found":
                        True,

                    "score":
                        100.0,

                    "evidence":
                        candidate,
                }

                break

        if found_result:
            component_results.append(
                found_result
            )
            continue

        # 3. Whole-token containment.
        # E7894 boleh cocok dengan "MODEL E7894"
        # tapi tidak dengan E7894X.
        pattern = (
            r"(?:^|\s)"
            + re.escape(
                component_normalized
            )
            + r"(?:\s|$)"
        )

        for item in ocr_items:

            candidate = item.get(
                "text"
            )

            if not candidate:
                continue

            candidate_normalized = (
                normalize_text(
                    candidate
                )
            )

            if re.search(
                pattern,
                candidate_normalized,
            ):

                found_result = {
                    "component":
                        component,

                    "found":
                        True,

                    "score":
                        100.0,

                    "evidence":
                        candidate,
                }

                break

        if found_result:
            component_results.append(
                found_result
            )
            continue

        # 4. Fuzzy sebagai fallback terakhir
        best_score = 0.0
        best_candidate = None

        for item in ocr_items:

            candidate = item.get(
                "text"
            )

            if not candidate:
                continue

            candidate_value = (
                normalize_type_candidate(
                    candidate
                )
            )

            if not candidate_value:
                continue

            minimum_length = max(
                3,
                int(
                    len(
                        component_normalized
                    )
                    * 0.6
                ),
            )

            if (
                len(
                    candidate_value
                )
                < minimum_length
            ):
                continue

            score = max(
                fuzz.ratio(
                    component_normalized,
                    candidate_value,
                ),
                fuzz.token_set_ratio(
                    component_normalized,
                    candidate_value,
                ),
            )

            if is_type_labeled_line(
                candidate
            ):
                score += 5

            if score > best_score:
                best_score = score
                best_candidate = candidate

        component_results.append({
            "component":
                component,

            "found":
                best_score >= 90,

            "score":
                round(
                    min(
                        best_score,
                        100.0,
                    ),
                    2,
                ),

            "evidence":
                best_candidate,
        })

    found_count = sum(
        item["found"]
        for item in component_results
    )

    if (
        components
        and found_count
        == len(components)
    ):
        status = "MATCH"

    elif found_count > 0:
        status = "REVIEW"

    else:
        status = "MISMATCH"

    return {
        "status":
            status,

        "expected":
            expected,

        "components":
            component_results,

        **metadata,
    }


def match_serial_field_on_page(
    expected,
    page_data,
):
    metadata = get_source_metadata(
        page_data
    )

    if not expected:
        return {
            "status": "MISSING",
            "expected": expected,
            "evidence": None,
            "score": 0.0,
            **metadata,
        }

    expected_compact = compact_text(
        expected
    )

    ocr_items = page_data.get(
        "ocr",
        [],
    )

    # 1. Prioritaskan baris yang memang berlabel serial
    serial_candidates = []

    for item in ocr_items:

        candidate = item.get(
            "text"
        )

        if not candidate:
            continue

        if is_serial_labeled_line(
            candidate
        ):
            serial_candidates.append(
                candidate
            )

    # 2. Exact match pada serial-labeled line
    for candidate in serial_candidates:

        candidate_serial = (
            normalize_serial_candidate(
                candidate
            )
        )

        if (
            candidate_serial
            == expected_compact
        ):
            return {
                "status": "MATCH",
                "expected": expected,
                "evidence": candidate,
                "score": 100.0,
                **metadata,
            }

    # Check all exact candidates BEFORE allowing OCR ambiguity to trigger REVIEW.
    # The relevant insert serial can be a separate OCR box on the same label.
    for item in ocr_items:
        raw = str(item.get("text") or "")
        if normalize_serial_candidate(raw) == expected_compact:
            return {"status": "MATCH", "expected": expected,
                    "evidence": raw, "score": 100.0, **metadata}

    # 3. OCR ambiguity pada serial-labeled line
    for candidate in serial_candidates:

        candidate_serial = (
            normalize_serial_candidate(
                candidate
            )
        )

        if serial_ocr_ambiguity(
            expected_compact,
            candidate_serial,
        ):
            return {
                "status":
                    "REVIEW",

                "expected":
                    expected,

                "evidence":
                    candidate,

                "score":
                    None,

                "reason":
                    (
                        "Kemungkinan ambiguity OCR "
                        "pada nomor seri."
                    ),

                **metadata,
            }

    # 4. Exact match di baris lain
    for item in ocr_items:

        candidate = item.get(
            "text"
        )

        if not candidate:
            continue

        candidate_serial = (
            normalize_serial_candidate(
                candidate
            )
        )

        if (
            candidate_serial
            == expected_compact
        ):
            return {
                "status": "MATCH",
                "expected": expected,
                "evidence": candidate,
                "score": 100.0,
                **metadata,
            }

    # 5. OCR ambiguity di baris lain
    for item in ocr_items:

        candidate = item.get(
            "text"
        )

        if not candidate:
            continue

        candidate_serial = (
            normalize_serial_candidate(
                candidate
            )
        )

        if serial_ocr_ambiguity(
            expected_compact,
            candidate_serial,
        ):
            return {
                "status": "REVIEW",
                "expected": expected,
                "evidence": candidate,
                "score": None,
                "reason":
                    "Kemungkinan ambiguity OCR pada nomor seri.",
                **metadata,
            }

    # 6. Fuzzy fallback
    best_score = 0.0
    best_candidate = None

    for item in ocr_items:

        candidate = item.get(
            "text"
        )

        if not candidate:
            continue

        candidate_serial = (
            normalize_serial_candidate(
                candidate
            )
        )

        if not candidate_serial:
            continue

        minimum_length = max(
            3,
            int(
                len(
                    expected_compact
                )
                * 0.7
            ),
        )

        if (
            len(candidate_serial)
            < minimum_length
        ):
            continue

        score = fuzz.ratio(
            expected_compact,
            candidate_serial,
        )

        # Bonus jika baris memang berlabel serial
        if is_serial_labeled_line(
            candidate
        ):
            score += 10

        if score > best_score:

            best_score = score
            best_candidate = candidate

    return {
        "status": "MISMATCH",
        "expected": expected,
        "evidence": best_candidate,
        "score": round(
            min(
                best_score,
                100.0
            ),
            2
        ),
        **metadata,
    }


def score_field_status(
    result,
    match_weight,
    review_weight,
):
    status = result.get(
        "status"
    )

    if status == "MATCH":
        return match_weight

    if status == "REVIEW":
        return review_weight

    return 0


def select_best_source_page(
    document_ocr,
    expected,
):
    candidates = []

    for page_data in document_ocr:

        manufacturer = (
            match_simple_field_on_page(
                expected.get(
                    "manufacturer"
                ),
                page_data,
            )
        )

        type_result = (
            match_type_field_on_page(
                expected.get(
                    "type"
                ),
                page_data,
            )
        )

        serial_result = (
            match_serial_field_on_page(
                expected.get(
                    "serial_number"
                ),
                page_data,
            )
        )

        manufacturer_status = (
            manufacturer.get(
                "status"
            )
        )

        type_status = (
            type_result.get(
                "status"
            )
        )

        serial_status = (
            serial_result.get(
                "status"
            )
        )

        score = 0

        score += score_field_status(
            serial_result,
            match_weight=5,
            review_weight=3,
        )

        score += score_field_status(
            type_result,
            match_weight=3,
            review_weight=1,
        )

        score += score_field_status(
            manufacturer,
            match_weight=2,
            review_weight=0.5,
        )

        if (
            manufacturer_status
            == "MISMATCH"
        ):
            score -= 3

        complete_match = (
            manufacturer_status == "MATCH"
            and type_status == "MATCH"
            and serial_status
            in {
                "MATCH",
                "REVIEW",
            }
        )

        if complete_match:
            score += 3

        candidate = {
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

            "score":
                score,

            "complete_match":
                complete_match,

            "manufacturer_status":
                manufacturer_status,

            "type_status":
                type_status,

            "serial_status":
                serial_status,

            "fields": {
                "manufacturer":
                    manufacturer,

                "type":
                    type_result,

                "serial_number":
                    serial_result,
            },
        }

        candidates.append(
            candidate
        )

    if not candidates:

        return {
            "source_id": None,
            "source_name": None,
            "page": None,
            "score": 0,

            "fields": {
                "manufacturer": {},
                "type": {},
                "serial_number": {},
            },

            "candidate_scores": [],
        }

    candidates.sort(
        key=lambda item: (
            item[
                "complete_match"
            ],

            item[
                "manufacturer_status"
            ] == "MATCH",

            item[
                "serial_status"
            ] == "MATCH",

            item[
                "serial_status"
            ] == "REVIEW",

            item[
                "type_status"
            ] == "MATCH",

            item[
                "score"
            ],
        ),
        reverse=True,
    )

    best = candidates[0]

    candidate_scores = []

    for item in candidates:

        candidate_scores.append({
            "source_id":
                item[
                    "source_id"
                ],

            "source_name":
                item[
                    "source_name"
                ],

            "page":
                item[
                    "page"
                ],

            "score":
                item[
                    "score"
                ],

            "complete_match":
                item[
                    "complete_match"
                ],

            "manufacturer_status":
                item[
                    "manufacturer_status"
                ],

            "type_status":
                item[
                    "type_status"
                ],

            "serial_status":
                item[
                    "serial_status"
                ],
        })

    return {
        "source_id":
            best[
                "source_id"
            ],

        "source_name":
            best[
                "source_name"
            ],

        "page":
            best[
                "page"
            ],

        "score":
            best[
                "score"
            ],

        "fields":
            best[
                "fields"
            ],

        "candidate_scores":
            candidate_scores,
    }


def summarize_guided_result(
    result,
):
    statuses = []

    for section in [
        "unit",
        "tabung",
    ]:
        for field in [
            "manufacturer",
            "type",
            "serial_number",
        ]:
            statuses.append(
                result
                .get(
                    section,
                    {},
                )
                .get(
                    field,
                    {},
                )
                .get(
                    "status"
                )
            )

    if "MISMATCH" in statuses:
        overall = "MISMATCH"

    elif "MISSING" in statuses:
        overall = "INCOMPLETE"

    elif "REVIEW" in statuses:
        overall = "REVIEW"

    else:
        overall = "VALID"

    return {
        "status":
            overall,

        "match":
            statuses.count(
                "MATCH"
            ),

        "review":
            statuses.count(
                "REVIEW"
            ),

        "mismatch":
            statuses.count(
                "MISMATCH"
            ),

        "missing":
            statuses.count(
                "MISSING"
            ),

        "total_fields":
            len(statuses),
    }


def guided_match_label_document(
    document_ocr,
    expected,
):
    unit_expected = expected.get(
        "unit",
        {},
    )

    tube_expected = expected.get(
        "tabung",
        {},
    )

    unit_match = (
        select_best_source_page(
            document_ocr,
            unit_expected,
        )
    )

    tube_match = (
        select_best_source_page(
            document_ocr,
            tube_expected,
        )
    )

    result = {
        "unit": {
            "selected_source_id":
                unit_match[
                    "source_id"
                ],

            "selected_source_name":
                unit_match[
                    "source_name"
                ],

            "selected_page":
                unit_match[
                    "page"
                ],

            "page_score":
                unit_match[
                    "score"
                ],

            "manufacturer":
                unit_match[
                    "fields"
                ][
                    "manufacturer"
                ],

            "type":
                unit_match[
                    "fields"
                ][
                    "type"
                ],

            "serial_number":
                unit_match[
                    "fields"
                ][
                    "serial_number"
                ],

            "candidate_scores":
                unit_match[
                    "candidate_scores"
                ],
        },

        "tabung": {
            "selected_source_id":
                tube_match[
                    "source_id"
                ],

            "selected_source_name":
                tube_match[
                    "source_name"
                ],

            "selected_page":
                tube_match[
                    "page"
                ],

            "page_score":
                tube_match[
                    "score"
                ],

            "manufacturer":
                tube_match[
                    "fields"
                ][
                    "manufacturer"
                ],

            "type":
                tube_match[
                    "fields"
                ][
                    "type"
                ],

            "serial_number":
                tube_match[
                    "fields"
                ][
                    "serial_number"
                ],

            "candidate_scores":
                tube_match[
                    "candidate_scores"
                ],
        },
    }

    # Optional trace: compare displayed evidence with actual OCR variants.
    import os as _label_os
    if _label_os.environ.get("BAPETEN_LABEL_OCR_DEBUG", "").lower() in ("1", "true", "yes"):
        for _sec in ("unit", "tabung"):
            for _field in ("manufacturer", "type", "serial_number"):
                _entry = result.get(_sec, {}).get(_field, {})
                _evidence = _entry.get("evidence")
                if _evidence is None:
                    _comps = _entry.get("components", [])
                    _evidence = [_c.get("evidence") for _c in _comps]
                print(f"[LABEL-MATCH] {_sec}.{_field}: {_entry.get('status')} | expected={_entry.get('expected')} | evidence={_evidence}", flush=True)

    result["summary"] = (
        summarize_guided_result(
            result
        )
    )

    result["matching_score"] = (
        max(
            0,
            unit_match["score"],
        )
        +
        max(
            0,
            tube_match["score"],
        )
    )

    return result


def equipment_to_expected(
    equipment,
):
    return {
        "unit": {
            "manufacturer":
                equipment.get(
                    "merk_unit"
                ),

            "type":
                equipment.get(
                    "tipe_unit"
                ),

            "serial_number":
                equipment.get(
                    "nomor_seri_unit"
                ),
        },

        "tabung": {
            "manufacturer":
                equipment.get(
                    "merk_tabung"
                ),

            "type":
                equipment.get(
                    "tipe_tabung"
                ),

            "serial_number":
                equipment.get(
                    "nomor_seri_tabung"
                ),
        },
    }


def count_serial_matches(
    match_result,
):
    count = 0

    for section in [
        "unit",
        "tabung",
    ]:
        status = (
            match_result
            .get(
                section,
                {},
            )
            .get(
                "serial_number",
                {},
            )
            .get(
                "status"
            )
        )

        if status == "MATCH":
            count += 1

    return count


def auto_match_equipment(
    document_ocr,
    equipment_list,
):
    if not equipment_list:
        return {
            "status":
                "NO_EQUIPMENT",

            "confidence":
                "NONE",

            "selected_equipment_index":
                None,

            "suggested_equipment_index":
                None,

            "best_score":
                0,

            "second_score":
                0,

            "score_gap":
                0,

            "candidates":
                [],

            "match":
                None,
        }

    candidates = []

    for index, equipment in enumerate(
        equipment_list
    ):
        expected = equipment_to_expected(
            equipment
        )

        match_result = (
            guided_match_label_document(
                document_ocr,
                expected,
            )
        )

        score = match_result.get(
            "matching_score",
            0,
        )

        summary = match_result.get(
            "summary",
            {},
        )

        serial_matches = (
            count_serial_matches(
                match_result
            )
        )

        candidates.append({
            "equipment_index":
                index,

            "equipment_number":
                index + 1,

            "merk_unit":
                equipment.get(
                    "merk_unit"
                ),

            "tipe_unit":
                equipment.get(
                    "tipe_unit"
                ),

            "nomor_seri_unit":
                equipment.get(
                    "nomor_seri_unit"
                ),

            "merk_tabung":
                equipment.get(
                    "merk_tabung"
                ),

            "tipe_tabung":
                equipment.get(
                    "tipe_tabung"
                ),

            "nomor_seri_tabung":
                equipment.get(
                    "nomor_seri_tabung"
                ),

            "score":
                score,

            "match_count":
                summary.get(
                    "match",
                    0,
                ),

            "review_count":
                summary.get(
                    "review",
                    0,
                ),

            "serial_matches":
                serial_matches,

            "validation_status":
                summary.get(
                    "status"
                ),

            "match_result":
                match_result,
        })

    candidates.sort(
        key=lambda item: (
            item[
                "score"
            ],
            item[
                "serial_matches"
            ],
            item[
                "match_count"
            ],
        ),
        reverse=True,
    )

    best = candidates[0]

    second = (
        candidates[1]
        if len(candidates) > 1
        else None
    )

    best_score = best[
        "score"
    ]

    second_score = (
        second["score"]
        if second
        else 0
    )

    score_gap = (
        best_score
        - second_score
    )

    if len(
        equipment_list
    ) == 1:
        status = (
            "AUTO_SELECTED"
        )

        confidence = (
            "HIGH"
        )

        selected_index = (
            best[
                "equipment_index"
            ]
        )

    elif (
        best_score >= 12
        and score_gap >= 4
    ):
        status = (
            "AUTO_SELECTED"
        )

        confidence = (
            "HIGH"
        )

        selected_index = (
            best[
                "equipment_index"
            ]
        )

    elif (
        best_score >= 8
        and score_gap >= 3
    ):
        status = (
            "AUTO_SELECTED"
        )

        confidence = (
            "MEDIUM"
        )

        selected_index = (
            best[
                "equipment_index"
            ]
        )

    else:
        status = "REVIEW"

        confidence = "LOW"

        selected_index = None

    public_candidates = []

    for item in candidates:
        public_candidates.append({
            key: value
            for key, value
            in item.items()
            if key
            != "match_result"
        })

    return {
        "status":
            status,

        "confidence":
            confidence,

        "selected_equipment_index":
            selected_index,

        "suggested_equipment_index":
            best[
                "equipment_index"
            ],

        "best_score":
            best_score,

        "second_score":
            second_score,

        "score_gap":
            score_gap,

        "candidates":
            public_candidates,

        "match":
            (
                best[
                    "match_result"
                ]
                if selected_index
                is not None
                else None
            ),

        "suggested_match":
            best[
                "match_result"
            ],
    }
    
def normalize_type_candidate(
    value,
):
    if value is None:
        return ""

    value = str(value).strip()

    value = re.sub(
        r"^\s*"
        r"(?:"
        r"INSERT\s+MODEL"
        r"|UNIT\s+MODEL"
        r"|MODEL"
        r"|TYPE"
        r"|TIPE"
        r")"
        r"\s*[:#\-]?\s*",
        "",
        value,
        flags=re.IGNORECASE,
    )

    return normalize_text(
        value
    )


def is_type_labeled_line(
    value,
):
    if not value:
        return False

    return bool(
        re.search(
            r"^\s*"
            r"(?:"
            r"INSERT\s+MODEL"
            r"|UNIT\s+MODEL"
            r"|MODEL"
            r"|TYPE"
            r"|TIPE"
            r")"
            r"\s*[:#\-]?",
            str(value),
            flags=re.IGNORECASE,
        )
    )

# ---------------------------------------------------------------------------
# v7: context-grounded negative evidence; positive v6 matches are untouched.
# No fuzzy search of arbitrary page text is allowed as negative evidence.
# ---------------------------------------------------------------------------
_V6_GUIDED_MATCH = guided_match_label_document


def _v7_label_kind(text):
    text = str(text or '').strip()
    if re.search(r'^(?:INSERTION\s+TUB[EI]|INSERT\s+MODEL|TUBE\s+MODEL|X[- ]?RAY\s+TUBE)\s*:', text, re.I):
        return 'tabung'
    if re.search(r'^(?:GENERATOR|UNIT\s+MODEL|MODEL\s+X[- ]?RAY\s+UNIT)\s*:', text, re.I):
        return 'unit'
    return None


def _v7_extract_scoped_fields(page_data):
    """Extract explicit field-labeled evidence, preserving OCR provenance.

    Do not guess serials from arbitrary bare alphanumeric strings; an unmatched
    field without contextual evidence must remain REVIEW.
    """
    grouped = {}
    for row in page_data.get('ocr', []):
        grouped.setdefault(str(row.get('variant') or 'original'), []).append(row)
    found = {'unit': {'manufacturer': [], 'type': [], 'serial_number': []},
             'tabung': {'manufacturer': [], 'type': [], 'serial_number': []}}
    for variant, rows in grouped.items():
        section = 'unit'
        for ix, row in enumerate(rows):
            raw = str(row.get('text') or '').strip()
            if not raw:
                continue
            heading = _v7_label_kind(raw)
            if heading:
                section = heading
            kind = None
            val = None
            m = re.match(r'^\s*(?:BRAND|MANUFACTURER|MAKE|MERK)\s*[:#-]\s*(.+)$', raw, re.I)
            if m:
                kind, val = 'manufacturer', m.group(1).strip()
            m = re.match(r'^\s*(?:INSERT\s+MODEL|UNIT\s+MODEL|MODEL|TYPE|TIPE)\s*[:#-]\s*(.+)$', raw, re.I)
            if m:
                kind, val = 'type', m.group(1).strip()
            m = re.match(r'^\s*(?:SER(?:IAL)?\.?\s*NO\.?|SERIAL(?:\s+NUMBER)?|S\s*/\s*N|SN)\s*[:#.\-]?\s*(.+)$', raw, re.I)
            if m:
                kind, val = 'serial_number', m.group(1).strip()
            if not kind:
                # Two OCR boxes: 'SER NO' followed by actual serial.
                if re.match(r'^\s*(?:SER(?:IAL)?\.?\s*NO\.?|SN)\s*[:#.\-]?\s*$', raw, re.I):
                    if ix+1 < len(rows):
                        nxt = str(rows[ix+1].get('text') or '').strip()
                        if re.fullmatch(r'[A-Za-z0-9-]{4,30}', nxt):
                            kind, val = 'serial_number', nxt
            if not kind or not val:
                continue
            value = val.strip()
            if kind == 'manufacturer':
                if len(value) > 65 or not re.search(r'[A-Za-z]{2}', value):
                    continue
            elif kind == 'serial_number':
                if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9\-/ ]{2,35}', value):
                    continue
            elif kind == 'type':
                if len(value) > 65:
                    continue
            record = {'value': value, 'raw': raw, 'variant': variant,
                      'confidence': float(row.get('confidence') or 0),
                      'box': row.get('box')}
            found[section][kind].append(record)
    return found


def _v7_negative_field(expected, old, candidates, kind, meta):
    if old.get('status') == 'MATCH' or not expected:
        return old
    if not candidates:
        return {'status':'REVIEW', 'expected':expected, 'evidence':None,
                'score':None, 'reason':'Nilai field tidak teridentifikasi dengan yakin', **meta}
    # A field-specific alternative is useful evidence, but cannot be selected
    # by fuzzy similarity to the submitted form. Prefer OCR agreement and trust.
    by_value = {}
    for x in candidates:
        norm = compact_text(x['value'])
        if norm:
            by_value.setdefault(norm, []).append(x)
    if not by_value:
        return {'status':'REVIEW','expected':expected,'evidence':None,'score':None, **meta}
    expected_compact = compact_text(expected)
    for key, group in by_value.items():
        if key == expected_compact:
            best = max(group, key=lambda x:x['confidence'])
            return {'status':'MATCH','expected':expected,'evidence':best['value'],
                    'score':100.0,'variant':best['variant'], 'box':best['box'], **meta}
    ranked = sorted(by_value.values(), key=lambda g:(len({r['variant'] for r in g}),
                  max(r['confidence'] for r in g)),reverse=True)
    group = ranked[0]
    best = max(group, key=lambda x:x['confidence'])
    val = best['value']
    if kind == 'serial_number':
        ambiguous = serial_ocr_ambiguity(expected, val)
    else:
        ambiguous = serial_ocr_ambiguity(expected, val) if kind == 'type' else False
    # If candidate text could be a misread form value, conservative REVIEW.
    uncertain = ambiguous or (len(ranked)>1 and len({r['variant'] for r in group})<2)
    status = 'REVIEW' if uncertain else 'MISMATCH'
    return {'status':status,'expected':expected,'evidence':val,
            'score':round(fuzz.ratio(expected_compact,compact_text(val)),1),
            'variant':best['variant'],'box':best['box'],
            'reason':'Nilai alternatif diperoleh dari label field dokumen',**meta}


def guided_match_label_document(document_ocr, expected):
    result = _V6_GUIDED_MATCH(document_ocr, expected)
    for section in ('unit','tabung'):
        chosen = result[section]
        page_data = next((p for p in document_ocr
            if p.get('source_id') == chosen.get('selected_source_id')
            and p.get('page') == chosen.get('selected_page')), None)
        if page_data is None:
            continue
        extracted = _v7_extract_scoped_fields(page_data)
        meta = get_source_metadata(page_data)
        for field in ('manufacturer','type','serial_number'):
            chosen[field] = _v7_negative_field(expected.get(section,{}).get(field),
                chosen.get(field,{}), extracted[section][field],field,meta)
    result['summary'] = summarize_guided_result(result)
    result['matching_score'] = sum(score_field_status(result[section][field],
        {'serial_number':5,'type':3,'manufacturer':2}[field],
        {'serial_number':3,'type':1,'manufacturer':0.5}[field])
        for section in ('unit','tabung') for field in ('manufacturer','type','serial_number'))
    return result

# v8: absence is not a mismatch unless a cross-device identity conflict is proven.
_V7_GUIDED_MATCH = guided_match_label_document

def _v8_empty(expected, meta, mismatch=False):
    return {'status': 'MISMATCH' if mismatch else 'REVIEW',
            'expected': expected, 'evidence': None, 'score': None,
            'components': [], 'reason': ('Identitas dokumen bertentangan; field tidak ditemukan'
                if mismatch else 'Field tidak ditemukan pada label'), **meta}

def _v8_usable_labeled_candidates(candidates, kind):
    # Only records extracted from an explicit label, never arbitrary fuzzy snippets.
    vals = {}
    for rec in candidates:
        key = compact_text(rec.get('value'))
        if key:
            vals.setdefault(key, []).append(rec)
    return vals

def guided_match_label_document(document_ocr, expected):
    result = _V7_GUIDED_MATCH(document_ocr, expected)
    available = {}
    decisive = []
    for section in ('unit','tabung'):
        choice = result[section]
        source = next((p for p in document_ocr if p.get('source_id') == choice.get('selected_source_id')
                       and p.get('page') == choice.get('selected_page')), None)
        extracted = _v7_extract_scoped_fields(source) if source else None
        meta = get_source_metadata(source) if source else {}
        for kind in ('manufacturer','type','serial_number'):
            exp = expected.get(section, {}).get(kind)
            previous = choice.get(kind) or {}
            key = (section, kind)
            candidates = extracted[section][kind] if extracted else []
            groups = _v8_usable_labeled_candidates(candidates, kind)
            available[key] = (exp, previous, groups, meta)
            if not exp or previous.get('status') == 'MATCH':
                continue
            if not groups:
                choice[kind] = _v8_empty(exp, meta)
                continue
            # A recognized BRAND label with a different readable value is a real conflict.
            # Do not infer this for type or serial: OCR ambiguities need REVIEW.
            if kind == 'manufacturer':
                ranked = sorted(groups.values(), key=lambda g:(len({x['variant'] for x in g}),
                          max(x['confidence'] for x in g)), reverse=True)
                best_group = ranked[0]
                best = max(best_group, key=lambda x:x['confidence'])
                val = best['value']
                if compact_text(val) != compact_text(exp) and not serial_ocr_ambiguity(exp, val):
                    choice[kind] = {'status':'MISMATCH','expected':exp,'evidence':val,
                                    'score':round(fuzz.ratio(compact_text(exp), compact_text(val)),1),
                                    'variant':best['variant'], 'box':best['box'], **meta}
                    decisive.append(section)
            # In absence of a reliable alternative: display no made-up document value.
            elif previous.get('status') != 'MATCH':
                # A matching alternative discovered by v7 is retained.
                if previous.get('status') == 'REVIEW' and previous.get('evidence') is not None:
                    # For negative tests, non-exact type/serial candidates may be real,
                    # but keep REVIEW rather than assert MISMATCH.
                    continue
                choice[kind] = _v8_empty(exp, meta)
    # MISMATCH on blank fields requires independent contradictions in unit AND tube.
    cross_device = {'unit','tabung'}.issubset(set(decisive))
    if cross_device:
        for (section, kind), (exp, old, groups, meta) in available.items():
            if not exp:
                continue
            field = result[section][kind]
            if field.get('status') == 'MATCH' or (kind == 'manufacturer' and field.get('status') == 'MISMATCH'):
                continue
            # User's requested compact negative display: no spurious fuzzy percentages.
            result[section][kind] = _v8_empty(exp, meta, mismatch=True)
    result['summary'] = summarize_guided_result(result)
    result['matching_score'] = sum(score_field_status(result[s][f],
        {'serial_number':5,'type':3,'manufacturer':2}[f],
        {'serial_number':3,'type':1,'manufacturer':.5}[f])
        for s in ('unit','tabung') for f in ('manufacturer','type','serial_number'))
    result['cross_device_conflict'] = cross_device
    return result

# v9: document-level identity gate, independent of expected-form field matching.
# Preserve the v8 field-level positive matcher whenever a cross-device conflict is
# not established. In a confirmed document mismatch the evaluator sees a clear,
# compact MISMATCH table; full contradictory evidence remains in metadata.
_V8_GUIDED_MATCH = guided_match_label_document


def _v9_document_unit_brands(document_ocr):
    """Find independently labeled manufacturer evidence, never fuzzy evidence.

    Accept explicit unit BRAND/MANUFACTURER labels or a named company on the
    equipment label. Reject importers, addresses, and tube manufacturers.
    """
    groups = {}
    for page in document_ocr or []:
        rows_by_variant = {}
        for row in page.get('ocr', []):
            rows_by_variant.setdefault(str(row.get('variant') or 'original'), []).append(row)
        for variant, rows in rows_by_variant.items():
            scope = 'unit'
            for row in rows:
                raw = str(row.get('text') or '').strip()
                if not raw:
                    continue
                heading = _v7_label_kind(raw)
                if heading:
                    scope = heading
                if scope != 'unit':
                    continue
                brand = None
                m = re.match(r'^\s*(?:BRAND|MANUFACTURER|MAKE|MERK)\s*[:#-]\s*(.+)', raw, re.I)
                if m:
                    brand = m.group(1).strip()
                elif not re.search(r'\b(?:IMPORTED|DISTRIBUTED|AUSTRALIA\s+BY|ADDRESS)\b', raw, re.I):
                    # Company designation is evidence of a manufacturer's name
                    # even on labels without a BRAND: row (e.g., Fujifilm).
                    m = re.match(r'^\s*([A-Za-z][\w.&\- ]{2,55}?)\s+(?:CORPORATION|CORP\.?|INC\.?|LTD\.?|CO\.?\s*,?\s*LTD\.?)\b', raw, re.I)
                    if m:
                        brand = m.group(1).strip()
                if not brand:
                    continue
                # Keep only a credible name, not a whole address or instruction.
                brand = re.sub(r'\s+', ' ', brand).strip()
                norm = compact_text(brand)
                if len(norm) < 4 or len(norm) > 35:
                    continue
                groups.setdefault(norm, {'value': brand, 'variants': set(), 'evidence': []})
                groups[norm]['variants'].add(variant)
                groups[norm]['evidence'].append({'text':raw,'variant':variant,
                    'page':page.get('page'),'source_id':page.get('source_id')})
    return groups


def _v9_identity_conflict(document_ocr, expected):
    expected_brand = compact_text(expected.get('unit', {}).get('manufacturer'))
    groups = _v9_document_unit_brands(document_ocr)
    if not expected_brand or not groups:
        return None
    # One preprocessing output does not prove an unfamiliar brand; demand OCR
    # agreement across at least two variants to reject a whole document.
    reliable = [g for g in groups.values() if len(g['variants']) >= 2]
    if not reliable:
        return None
    # A confirmed occurrence of the form brand vetoes the global rejection.
    if any(compact_text(g['value']) == expected_brand for g in reliable):
        return None
    # Multiple independently recognized brands may belong to different units
    # on a mixed scan, so do not declare the complete document incorrect.
    if len({compact_text(g['value']) for g in reliable}) != 1:
        return None
    return reliable[0]


def guided_match_label_document(document_ocr, expected):
    gate = _v9_identity_conflict(document_ocr, expected)
    result = _V8_GUIDED_MATCH(document_ocr, expected)
    if gate is None:
        result['document_identity_conflict'] = False
        return result
    result['document_identity_conflict'] = True
    result['identity_evidence'] = {'detected_unit_brand':gate['value'],
                                   'sources':gate['evidence']}
    for section in ('unit', 'tabung'):
        for field in ('manufacturer', 'type', 'serial_number'):
            current = result[section].get(field) or {}
            exp = expected.get(section, {}).get(field)
            # An exact match should not be overwritten by a document-level
            # guess: contradictory positive evidence requires REVIEW.
            if current.get('status') == 'MATCH':
                result['document_identity_conflict'] = False
                result['identity_evidence']['reason'] = 'Contradictory exact field match; review required'
                for s in ('unit','tabung'):
                    for f in ('manufacturer','type','serial_number'):
                        if result[s][f].get('status') == 'MISMATCH':
                            result[s][f] = _v8_empty(expected.get(s,{}).get(f), {}, mismatch=False)
                result['summary'] = summarize_guided_result(result)
                return result
            result[section][field] = {'status':'MISMATCH', 'expected':exp,
                'evidence':None,'score':None, 'components':[],
                'reason':'Identitas unit pada label berbeda dari Formulir'}
    result['summary'] = summarize_guided_result(result)
    result['matching_score'] = 0
    result['cross_device_conflict'] = True
    return result


# v10: fast independent document gate. Prevent the expensive multi-stage
# field matching from running for a confirmed foreign equipment label.
_V9_GUIDED_MATCH = guided_match_label_document

def _v10_document_rejection(document_ocr, expected):
    gate = _v9_identity_conflict(document_ocr, expected)
    if gate is None:
        return None
    # Require absence of an exact expected UNIT brand on the label. Keep mixed
    # brand equipment sets out of blanket rejections.
    unit_brand = compact_text(expected.get('unit', {}).get('manufacturer'))
    for page in document_ocr:
        for row in page.get('ocr', []):
            line = str(row.get('text', ''))
            if unit_brand and re.search(r'(?<![A-Z0-9])' + re.escape(unit_brand) + r'(?![A-Z0-9])', compact_text(line)):
                return None
    return gate


def guided_match_label_document(document_ocr, expected):
    gate = _v10_document_rejection(document_ocr, expected)
    if gate is None:
        # Retain v9/v6 validated positive matching, do not alter evidence.
        return _V9_GUIDED_MATCH(document_ocr, expected)
    result = {}
    for section in ('unit', 'tabung'):
        fields = {}
        for field in ('manufacturer', 'type', 'serial_number'):
            fields[field] = {
                'status':'MISMATCH', 'expected':expected.get(section, {}).get(field),
                'evidence':None, 'score':None, 'components':[],
                'reason':'Dokumen memuat identitas peralatan berbeda',
            }
        result[section] = {
            'selected_source_id':None, 'selected_source_name':None,
            'selected_page':None, 'page_score':0, 'candidate_scores':[], **fields
        }
    result['summary'] = summarize_guided_result(result)
    result['matching_score'] = 0
    result['document_identity_conflict'] = True
    result['cross_device_conflict'] = True
    result['identity_evidence'] = {
        'detected_unit_brand':gate['value'], 'sources':gate['evidence']
    }
    return result


# v11: explicit original-only zero-hit gate. Do not inspect or replace fields
# with unrelated labels when the gate has stopped processing.
_V10_GUIDED_MATCH = guided_match_label_document

def guided_match_label_document(document_ocr, expected):
    if document_ocr and all(p.get('original_zero_match') for p in document_ocr):
        result = {}
        for section in ('unit', 'tabung'):
            fields = {field: {
                'status': 'MISMATCH',
                'expected': expected.get(section, {}).get(field),
                'evidence': None, 'score': None, 'components': [],
                'reason': '0 field cocok pada OCR original; dihentikan sesuai kebijakan',
            } for field in ('manufacturer', 'type', 'serial_number')}
            result[section] = {'selected_source_id':None, 'selected_source_name':None,
                'selected_page':None, 'page_score':0, 'candidate_scores':[], **fields}
        result['summary'] = summarize_guided_result(result)
        result['matching_score'] = 0
        result['original_zero_match'] = True
        return result
    return _V10_GUIDED_MATCH(document_ocr, expected)

# v0.5.1: identity codes are not fuzzy text: E7894 != E7894X.
# Leave descriptive model names and aliases on the legacy validated rules.
_V051_GUIDED_BEFORE_STRICT_CODE = guided_match_label_document

def guided_match_label_document(document_ocr, expected):
    result = _V051_GUIDED_BEFORE_STRICT_CODE(document_ocr, expected)
    changed = False
    for section in ('unit', 'tabung'):
        model = str((expected.get(section) or {}).get('type') or '').strip()
        code = compact_text(model)
        # Narrow guard, not a global fuzzy policy change.
        if not re.fullmatch(r'[A-Z]{1,7}[0-9][A-Z0-9]{2,15}', code) or re.search(r'\s|[/()]',model):
            continue
        entry = (result.get(section) or {}).get('type') or {}
        if entry.get('status') != 'MATCH':continue
        values=[str(x.get('evidence') or '').strip() for x in (entry.get('components') or [])
                if isinstance(x,dict) and x.get('evidence')]
        if not values and entry.get('evidence'):values=[str(entry['evidence'])]
        if not values:continue
        # Only compare a stand-alone code, never manufacturer/address prose.
        observed=[compact_text(x) for x in values]
        observed=[x for x in observed if re.fullmatch(r'[A-Z0-9]{3,22}',x)]
        if observed and all(x != code for x in observed):
            entry['status']='MISMATCH'
            entry['evidence']=values[0]
            entry['score']=None
            entry['reason']='Kode tipe/model berbeda, termasuk suffix atau prefix tambahan'
            changed=True
    if changed:
        result['summary']=summarize_guided_result(result)
        result['matching_score']=sum(score_field_status(result[s][f],
            {'serial_number':5,'type':3,'manufacturer':2}[f],
            {'serial_number':3,'type':1,'manufacturer':.5}[f])
            for s in ('unit','tabung') for f in ('manufacturer','type','serial_number'))
    return result
