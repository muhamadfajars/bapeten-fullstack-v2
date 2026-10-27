import re
import unicodedata

from rapidfuzz import fuzz


BRAND_ALIASES = {
    "GE": [
        "GE",
        "GE Healthcare",
        "GE Medical Systems",
    ],
    "SIEMENS": [
        "Siemens",
        "Siemens Healthcare",
        "Siemens Healthineers",
    ],
    "PHILIPS": [
        "Philips",
        "Philips Medical Systems",
    ],
    "CANON": [
        "Canon",
        "Canon Medical",
        "Canon Medical Systems",
    ],
    "TOSHIBA": [
        "Toshiba",
        "Toshiba Medical Systems",
    ],
    "SHIMADZU": [
        "Shimadzu",
    ],
    "FUJIFILM": [
        "Fujifilm",
        "Fuji Film",
    ],
    "CARESTREAM": [
        "Carestream",
        "Carestream Health",
    ],
}


def normalize_text(value):
    if value is None:
        return ""

    value = unicodedata.normalize(
        "NFKC",
        str(value),
    ).casefold()

    value = re.sub(
        r"[^a-z0-9]+",
        " ",
        value,
    )

    return " ".join(
        value.split()
    )


def compact_text(value):
    return re.sub(
        r"[^a-z0-9]",
        "",
        normalize_text(value),
    )


def brand_variants(value):
    normalized = normalize_text(value)

    if not normalized:
        return []

    for canonical, aliases in BRAND_ALIASES.items():
        variants = [
            normalize_text(alias)
            for alias in aliases
        ]

        if normalized in variants:
            return variants

        if normalized == normalize_text(canonical):
            return variants

    return [normalized]

def find_exact_phrase(text, phrase):
    phrase_tokens = normalize_text(phrase).split()

    if not phrase_tokens:
        return None

    tokens = list(re.finditer(
        r"[^\W_]+",
        str(text),
        flags=re.UNICODE,
    ))

    size = len(phrase_tokens)

    for start in range(len(tokens) - size + 1):
        selected = tokens[start:start + size]

        values = [
            normalize_text(match.group())
            for match in selected
        ]

        if values == phrase_tokens:
            return str(text)[
                selected[0].start():
                selected[-1].end()
            ]

    return None


def get_evidence_lines(text):
    return [
        line.strip()
        for line in str(text).splitlines()
        if line.strip()
        and not re.search(
            r"https?://|www\.",
            line,
            flags=re.IGNORECASE,
        )
    ]


def phrase_present(phrase, text):
    phrase_tokens = normalize_text(
        phrase
    ).split()

    text_tokens = normalize_text(
        text
    ).split()

    if not phrase_tokens:
        return False

    size = len(phrase_tokens)

    for index in range(
        len(text_tokens) - size + 1
    ):
        if (
            text_tokens[index:index + size]
            == phrase_tokens
        ):
            return True

    return False


def compare_brand(expected, text):
    variants = brand_variants(expected)

    if not variants:
        return {
            "status": "MISSING",
            "score": 0.0,
            "evidence": None,
        }

    lines = get_evidence_lines(text)

    variants = sorted(
        variants,
        key=lambda value: len(normalize_text(value)),
        reverse=True,
    )

    for variant in variants:
        for line in lines:
            evidence = find_exact_phrase(
                line,
                variant,
            )

            if evidence:
                return {
                    "status": "MATCH",
                    "score": 100.0,
                    "evidence": evidence,
                }

    return {
        "status": "MISSING",
        "score": 0.0,
        "evidence": None,
    }


def build_text_windows(text):
    lines = [
        line.strip()
        for line in str(text).splitlines()
        if line.strip()
    ]

    windows = []

    for index, line in enumerate(lines):
        windows.append(line)

        if index + 1 < len(lines):
            windows.append(
                line + " " + lines[index + 1]
            )

    return windows


def _compare_model_single(expected, text):
    expected_tokens = normalize_text(
        expected
    ).split()

    if not expected_tokens:
        return {
            "status": "MISSING",
            "score": 0.0,
            "evidence": None,
        }

    expected_compact = "".join(
        expected_tokens
    )

    windows = build_text_windows(text)

    best_score = 0.0
    best_evidence = None

    for window in windows:
        tokens = normalize_text(
            window
        ).split()

        if not tokens:
            continue

        min_size = max(
            1,
            len(expected_tokens) - 2,
        )

        max_size = min(
            len(tokens),
            len(expected_tokens) + 2,
        )

        if min_size > max_size:
            continue

        for size in range(
            min_size,
            max_size + 1,
        ):
            for start in range(
                len(tokens) - size + 1
            ):
                candidate_tokens = tokens[
                    start:start + size
                ]

                candidate_compact = "".join(
                    candidate_tokens
                )

                if candidate_compact == expected_compact:
                    evidence = find_exact_phrase(
                        window,
                        expected,
                    )

                    if evidence is None:
                        evidence = " ".join(
                            candidate_tokens
                        )

                    return {
                        "status": "MATCH",
                        "score": 100.0,
                        "evidence": evidence,
                    }

                score = fuzz.ratio(
                    expected_compact,
                    candidate_compact,
                )

                if score > best_score:
                    best_score = score
                    best_evidence = window

    if best_score >= 85:
        status = "REVIEW"
    else:
        status = "MISSING"

    return {
        "status": status,
        "score": round(best_score, 2),
        "evidence": (
            best_evidence
            if status == "REVIEW"
            else None
        ),
    }


def compare_model(expected, text):
    """Require explicit full-model or explicitly parenthesized alias evidence.

    Alias is derived from the form itself, not a manufacturer-specific mapping.
    """
    full=_compare_model_single(expected,text)
    if full['status']=='MATCH':return full
    for alt in re.findall(r'\(([^()]{3,80})\)',str(expected or '')):
        alias=_compare_model_single(alt,text)
        if alias['status']=='MATCH':
            alias['alias_from_form']=alt
            alias['matching_basis']='FORM_PARENTHESES'
            return alias
    return full


def compare_page(expected, page):
    text = page.get(
        "text"
    ) or ""

    brand = compare_brand(
        expected.get("merk_unit"),
        text,
    )

    model = compare_model(
        expected.get("tipe_unit"),
        text,
    )

    brand_score = (
        100.0
        if brand["status"] == "MATCH"
        else 0.0
    )

    if model["status"] == "MATCH":
        model_score = 100.0

    elif model["status"] == "REVIEW":
        model_score = (
            model["score"] * 0.5
        )

    else:
        model_score = 0.0

    score = (
        brand_score + model_score
    ) / 2

    return {
        "page": page.get("page"),
        "method": page.get("method"),
        "brand": brand,
        "model": model,
        "score": round(score, 2),
    }


def aggregate_match(page_results):
    if not page_results:
        return "MISSING"

    for item in page_results:
        if (
            item["brand"]["status"] == "MATCH"
            and item["model"]["status"] == "MATCH"
        ):
            return "MATCH"

    for item in page_results:
        if (
            item["brand"]["status"] == "MATCH"
            or item["model"]["status"] in {
                "MATCH",
                "REVIEW",
            }
        ):
            return "REVIEW"

    return "MISSING"


def match_one_equipment(
    specification,
    equipment,
    index,
):
    expected = {
        "merk_unit": equipment.get(
            "merk_unit"
        ),
        "tipe_unit": equipment.get(
            "tipe_unit"
        ),
    }

    page_results = [
        compare_page(
            expected,
            page,
        )
        for page in specification.get(
            "pages",
            [],
        )
    ]

    page_results.sort(
        key=lambda item: item["score"],
        reverse=True,
    )

    status = aggregate_match(
        page_results
    )

    exact_pairs = [
        item
        for item in page_results
        if (
            item["brand"]["status"] == "MATCH"
            and item["model"]["status"] == "MATCH"
        )
    ]

    if exact_pairs:
        best = exact_pairs[0]

    elif page_results:
        best = page_results[0]

    else:
        best = None

    return {
        "equipment_index": index,
        "expected": expected,
        "status": status,
        "best_page": (
            best["page"]
            if best
            else None
        ),
        "score": (
            best["score"]
            if best
            else 0.0
        ),
        "brand": (
            best["brand"]
            if best
            else {}
        ),
        "model": (
            best["model"]
            if best
            else {}
        ),
        "page_results": page_results,
    }


def match_equipment_specification(
    specification,
    equipment_list,
):
    candidates = [
        match_one_equipment(
            specification,
            equipment,
            index,
        )
        for index, equipment in enumerate(
            equipment_list
        )
    ]

    candidates.sort(
        key=lambda item: (
            item["status"] == "MATCH",
            item["score"],
        ),
        reverse=True,
    )

    if not candidates:
        return {
            "status": "MISSING",
            "selected_equipment_index": None,
            "reason": (
                "Data peralatan pada Formulir "
                "Permohonan tidak ditemukan."
            ),
            "candidates": [],
        }

    exact_matches = [
        item
        for item in candidates
        if item["status"] == "MATCH"
    ]

    if len(exact_matches) == 1:
        selected = exact_matches[0]

        return {
            "status": "MATCH",
            "selected_equipment_index":
                selected["equipment_index"],
            "reason": (
                "Satu pasangan merk dan tipe "
                "ditemukan dalam dokumen spesifikasi."
            ),
            "candidates": candidates,
        }

    if len(exact_matches) > 1:
        return {
            "status": "REVIEW",
            "selected_equipment_index": None,
            "reason": (
                "Beberapa peralatan memiliki pasangan "
                "merk dan tipe yang cocok. "
                "Diperlukan pemeriksaan evaluator."
            ),
            "candidates": candidates,
        }

    best = candidates[0]

    if best["status"] == "REVIEW":
        status = "REVIEW"
        reason = (
            "Ditemukan sebagian informasi yang sesuai, "
            "tetapi pasangan merk dan tipe belum "
            "dapat dikonfirmasi."
        )

    else:
        status = "MISSING"
        reason = (
            "Tidak ditemukan pasangan merk dan tipe "
            "yang dapat dikonfirmasi dari dokumen."
        )

    return {
        "status": status,
        "selected_equipment_index": None,
        "reason": reason,
        "candidates": candidates,
    }