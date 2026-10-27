import re

from .utils import clean_text


ADMIN_REQUIREMENTS = [
    "Dokumen Program Proteksi dan Keselamatan Radiasi",
    "Dokumen Sistem Manajemen",
    "Dokumen Program Perawatan"
]


def extract_document_number(text):
    if not text:
        return None

    normalized = clean_text(text)

    pattern = (
        r"No\.?\s*Dokumen"
        r"\s*:?\s*"
        r"(.+?)"
        r"(?=\s*-?\s*Tanggal\b|$)"
    )

    match = re.search(
        pattern,
        normalized,
        flags=re.IGNORECASE
    )

    if not match:
        return None

    value = match.group(1).strip()

    value = value.strip(" :-")

    return value


def extract_approval_date(text):
    if not text:
        return None

    normalized = clean_text(text)

    pattern = (
        r"Tanggal"
        r"\s*:?\s*"
        r"(\d{1,2}\s*[/.-]\s*\d{1,2}\s*[/.-]\s*\d{4})"
    )

    match = re.search(
        pattern,
        normalized,
        flags=re.IGNORECASE
    )

    if not match:
        return None

    date = match.group(1)

    date = re.sub(r"\s+", "", date)

    return date


def parse_admin_table(table):
    results = []

    for row in table:

        if not row or len(row) < 3:
            continue

        no = clean_text(row[0])
        requirement = clean_text(row[1])

        description = row[2] if row[2] else ""

        if not requirement:
            continue

        if requirement.lower() == "persyaratan":
            continue

        known_requirement = None

        for target in ADMIN_REQUIREMENTS:
            if target.lower() in requirement.lower():
                known_requirement = target
                break

        if not known_requirement:
            continue

        results.append({
            "no": no,
            "persyaratan": known_requirement,
            "nomor_dokumen": extract_document_number(
                description
            ),
            "tanggal_pengesahan": extract_approval_date(
                description
            )
        })

    return results