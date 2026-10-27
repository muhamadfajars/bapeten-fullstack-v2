import re

from datetime import date

from src.extraction.label_document import (
    prepare_label_document,
)

# PaddleOCR is initialized lazily inside image-processing functions.


MONTHS = {
    "januari": 1,
    "january": 1,
    "jan": 1,

    "februari": 2,
    "february": 2,
    "feb": 2,

    "maret": 3,
    "march": 3,
    "mar": 3,

    "april": 4,
    "apr": 4,

    "mei": 5,
    "may": 5,

    "juni": 6,
    "june": 6,
    "jun": 6,

    "juli": 7,
    "july": 7,
    "jul": 7,

    "agustus": 8,
    "august": 8,
    "aug": 8,

    "september": 9,
    "sep": 9,
    "sept": 9,

    "oktober": 10,
    "october": 10,
    "oct": 10,

    "november": 11,
    "nov": 11,

    "desember": 12,
    "december": 12,
    "dec": 12,
}


def normalize_text(value):
    if value is None:
        return ""

    value = str(value).lower()

    value = value.replace(
        "\n",
        " "
    )

    value = re.sub(
        r"([a-z])-\s+([a-z])",
        r"\1\2",
        value,
    )

    value = re.sub(
        r"[^a-z0-9]+",
        " ",
        value,
    )

    value = re.sub(
        r"\s+",
        " ",
        value,
    )

    return value.strip()


def _read_docx_without_libreoffice(path, source_name=None, source_id=None):
    """Native text and embedded images for DOCX when Office converter unavailable.

    This is a useful but less layout-faithful fallback; scanned drawings in DOCX
    may be unreadable. DOC (binary) still requires LibreOffice.
    """
    import zipfile
    import xml.etree.ElementTree as ET
    import numpy as np
    import cv2
    ns={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
    with zipfile.ZipFile(path) as archive:
        xml=archive.read('word/document.xml')
        root=ET.fromstring(xml)
        paragraphs=[]
        for paragraph in root.findall('.//w:p',ns):
            words=[(node.text or '') for node in paragraph.findall('.//w:t',ns)]
            if words:paragraphs.append(''.join(words))
        native='\n'.join(paragraphs)
        # one synthetic page with text, preserving source-specific references
        result=[{'source_id':source_id,'source_name':source_name,
                 'source_type':'docx','page':1,'image':None,'ocr':[],
                 'native_text':native}]
        for member in archive.namelist():
            if not member.startswith('word/media/') or not member.lower().endswith(('.png','.jpg','.jpeg','.bmp','.webp')):
                continue
            raw=archive.read(member)
            image=cv2.imdecode(np.frombuffer(raw,dtype=np.uint8),cv2.IMREAD_COLOR)
            if image is None:continue
            try:
                from src.extraction.label_ocr import extract_ocr
                ocr=extract_ocr(image)
            except Exception:ocr=[]
            result.append({'source_id':source_id,'source_name':source_name,
                           'source_type':'docx-image','page':len(result)+1,
                           'image':image,'ocr':ocr,'native_text':''})
        return result


def ocr_personnel_document(
    file_path,
    source_name=None,
    source_id=None,
    pdf_dpi=200,
):
    if str(file_path).lower().endswith('.docx'):
        return _read_docx_without_libreoffice(file_path,source_name,source_id)
    from src.extraction.label_ocr import extract_ocr
    pages = prepare_label_document(
        file_path,
        pdf_dpi=pdf_dpi,
    )
    native_by_page={}
    if str(file_path).lower().endswith('.pdf'):
        try:
            import pymupdf
            with pymupdf.open(file_path) as document:
                for index,page in enumerate(document):
                    native=page.get_text('text',sort=True)
                    if len(native.strip())>=25:
                        native_by_page[index+1]=native
        except (OSError,ValueError,RuntimeError):
            pass

    results = []

    for page_data in pages:

        ocr_result = extract_ocr(
            page_data["image"]
        )

        results.append({
            "source_id":
                source_id,

            "source_name":
                source_name,

            "source_type":
                page_data[
                    "source_type"
                ],

            "page":
                page_data[
                    "page"
                ],

            "image":
                page_data[
                    "image"
                ],

            "ocr":
                ocr_result,
            "native_text":native_by_page.get(page_data['page'],''),
        })

    return results


def ocr_personnel_documents(
    documents,
):
    results = []

    for index, document in enumerate(
        documents
    ):

        source_name = (
            document.get(
                "name"
            )
            or f"dokumen_{index + 1}"
        )

        file_results = (
            ocr_personnel_document(
                file_path=document[
                    "path"
                ],

                source_name=
                    source_name,

                source_id=(
                    document.get(
                        "source_id"
                    )
                    or index + 1
                ),
            )
        )

        results.extend(
            file_results
        )

    return results


def get_page_text(
    page_data,
):
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
                str(text)
            )

    native=page_data.get('native_text') or ''
    ocr_text='\n'.join(lines)
    if native.strip():
        # Keep both extraction paths: PDFs with embedded text can preserve
        # correct table/spelling, while OCR still reads images and stamps.
        return native+'\n'+ocr_text
    return ocr_text


def combine_source_text(
    pages,
):
    return "\n".join(
        get_page_text(
            page
        )
        for page in pages
    )


def classify_document(
    text,
):
    normalized = normalize_text(
        text
    )

    scores = {
        "SIP": 0,
        "SIB": 0,
        "SPRINT": 0,
        "COMPETENCE": 0, "WORK_PERMIT": 0, "WORK_LETTER": 0,
        "ASSIGNMENT": 0, "DOSE": 0,
    }

    patterns = {
        "SIP": [
            (
                "surat izin praktik",
                10,
            ),
            (
                "izin praktik",
                6,
            ),
            (
                "tempat praktik",
                4,
            ),
        ],

        "SIB": [
            (
                "surat izin bekerja",
                10,
            ),
            (
                "izin bekerja",
                6,
            ),
            (
                "surat izin bekerja petugas",
                5,
            ),
        ],

        "COMPETENCE": [("sertifikat kompetensi",12),("sertifikat keahlian",9),("dinyatakan kompeten",5)],
        "WORK_PERMIT": [("surat izin kerja",12),("izin kerja",7)],
        "WORK_LETTER": [("surat keterangan kerja",12),("keterangan bekerja",7)],
        "ASSIGNMENT": [("surat penunjukan tugas",12),("surat penunjukan",9),("ditunjuk sebagai",5)],
        "DOSE": [("evaluasi dosis",12),("pemantauan dosis",9),("laporan dosis",8)],
        "SPRINT": [
            (
                "surat perintah",
                10,
            ),
            (
                "memerintahkan",
                6,
            ),
            (
                "memberi perintah",
                5,
            ),
        ],
    }

    for document_type, values in (
        patterns.items()
    ):

        for phrase, weight in values:

            if normalize_text(
                phrase
            ) in normalized:

                scores[
                    document_type
                ] += weight

    best_type = max(
        scores,
        key=scores.get,
    )

    if scores[
        best_type
    ] <= 0:

        best_type = "UNKNOWN"

    return {
        "type":
            best_type,

        "scores":
            scores,
    }


def create_date(
    year,
    month,
    day,
):
    try:
        return date(
            int(year),
            int(month),
            int(day),
        )

    except (
        TypeError,
        ValueError,
    ):
        return None


def parse_date_value(
    value,
):
    if not value:
        return None

    value = str(
        value
    ).lower()

    value = value.replace(
        ",",
        " "
    )

    value = re.sub(
        r"(\d{1,2})"
        r"(st|nd|rd|th)\b",
        r"\1",
        value,
        flags=re.IGNORECASE,
    )

    numeric_dmy = re.search(
        r"\b"
        r"(\d{1,2})"
        r"[\/.\-]"
        r"(\d{1,2})"
        r"[\/.\-]"
        r"(\d{4})"
        r"\b",
        value,
    )

    if numeric_dmy:

        result = create_date(
            numeric_dmy.group(3),
            numeric_dmy.group(2),
            numeric_dmy.group(1),
        )

        if result:
            return result

    numeric_ymd = re.search(
        r"\b"
        r"(\d{4})"
        r"[\/.\-]"
        r"(\d{1,2})"
        r"[\/.\-]"
        r"(\d{1,2})"
        r"\b",
        value,
    )

    if numeric_ymd:

        result = create_date(
            numeric_ymd.group(1),
            numeric_ymd.group(2),
            numeric_ymd.group(3),
        )

        if result:
            return result

    textual = re.search(
        r"\b"
        r"(\d{1,2})"
        r"\s+"
        r"([a-z]+)"
        r"\s+"
        r"(\d{4})"
        r"\b",
        value,
        flags=re.IGNORECASE,
    )

    if textual:

        month = MONTHS.get(
            textual
            .group(2)
            .lower()
        )

        if month:

            result = create_date(
                textual.group(3),
                month,
                textual.group(1),
            )

            if result:
                return result

    return None


def find_all_dates(
    text,
):
    cleaned = str(text)

    patterns = [
        r"\b"
        r"\d{1,2}"
        r"[\/.\-]"
        r"\d{1,2}"
        r"[\/.\-]"
        r"\d{4}"
        r"\b",

        r"\b"
        r"\d{4}"
        r"[\/.\-]"
        r"\d{1,2}"
        r"[\/.\-]"
        r"\d{1,2}"
        r"\b",

        r"\b"
        r"\d{1,2}"
        r"(?:st|nd|rd|th)?"
        r"\s+"
        r"[A-Za-z]+"
        r"\s+"
        r"\d{4}"
        r"\b",
    ]

    results = []

    for pattern in patterns:

        for match in re.finditer(
            pattern,
            cleaned,
            flags=re.IGNORECASE,
        ):

            raw = match.group(0)

            parsed = parse_date_value(
                raw
            )

            if parsed:

                results.append({
                    "raw":
                        raw,

                    "date":
                        parsed,

                    "start":
                        match.start(),

                    "end":
                        match.end(),
                })

    return results


def extract_expiry_candidates(
    text,
):
    text_string = str(
        text
    )

    normalized = (
        text_string.lower()
    )

    expiry_keywords = [
        r"berlaku\s+s\.?\s*d\.?",
        r"berlaku\s+sampai",
        r"berlaku\s+hingga",
        r"masa\s+berlaku",
        r"valid\s+until",
        r"valid\s+through",
        r"expiry",
        r"expired?\s+on",
        r"berakhir",
    ]

    results = []

    for pattern in expiry_keywords:

        for match in re.finditer(
            pattern,
            normalized,
            flags=re.IGNORECASE,
        ):

            start = match.start()

            window = (
                text_string[
                    start:
                    start + 300
                ]
            )

            dates = find_all_dates(
                window
            )

            for item in dates:

                results.append({
                    "raw":
                        item[
                            "raw"
                        ],

                    "date":
                        item[
                            "date"
                        ],

                    "keyword":
                        match.group(0),
                })

    return results


def evaluate_expiry(
    text,
):
    candidates = (
        extract_expiry_candidates(
            text
        )
    )

    if not candidates:

        all_dates = find_all_dates(
            text
        )

        future_dates = [
            item
            for item in all_dates
            if item[
                "date"
            ] >= date.today()
        ]

        if future_dates:

            latest = max(
                future_dates,
                key=lambda item:
                    item[
                        "date"
                    ],
            )

            return {
                "status":
                    "REVIEW",

                "expiry_date":
                    latest[
                        "date"
                    ].isoformat(),

                "evidence":
                    latest[
                        "raw"
                    ],

                "reason":
                    (
                        "Tanggal masa berlaku "
                        "ditemukan tetapi label "
                        "masa berlaku tidak terbaca "
                        "secara meyakinkan."
                    ),
            }

        return {
            "status":
                "REVIEW",

            "expiry_date":
                None,

            "evidence":
                None,

            "reason":
                (
                    "Tanggal akhir masa berlaku "
                    "belum dapat ditemukan."
                ),
        }

    best = max(
        candidates,
        key=lambda item:
            item[
                "date"
            ],
    )

    expiry_date = best[
        "date"
    ]

    if expiry_date >= date.today():
        status = "ACTIVE"

    else:
        status = "EXPIRED"

    return {
        "status":
            status,

        "expiry_date":
            expiry_date.isoformat(),

        "evidence":
            best[
                "raw"
            ],

        "keyword":
            best.get(
                "keyword"
            ),
    }


def group_by_source(
    pages,
):
    groups = {}

    for page in pages:

        source_id = page.get(
            "source_id"
        )

        groups.setdefault(
            source_id,
            [],
        ).append(
            page
        )

    return groups


def parse_personnel_documents(
    document_pages,
):
    grouped = group_by_source(
        document_pages
    )

    results = []

    for source_id, pages in (
        grouped.items()
    ):

        text = combine_source_text(
            pages
        )

        classification = (
            classify_document(
                text
            )
        )

        expiry = evaluate_expiry(
            text
        )

        results.append({
            "source_id":
                source_id,

            "source_name":
                pages[
                    0
                ].get(
                    "source_name"
                ),

            "document_type":
                classification[
                    "type"
                ],

            "classification_scores":
                classification[
                    "scores"
                ],

            "expiry":
                expiry,

            "text":
                text,

            "pages":
                pages,
        })

    return results