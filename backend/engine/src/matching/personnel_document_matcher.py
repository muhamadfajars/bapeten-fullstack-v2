import re
import unicodedata

from rapidfuzz import fuzz

from src.extraction.approval_detector import (
    detect_approval,
)


NAME_PREFIXES = {
    "dr",
    "drg",
    "prof",
    "dokter",
}


NAME_SUFFIX_PATTERNS = [
    r"\bsp\s*rad\b",
    r"\bsp\s*a\b",
    r"\bsp\s*og\b",
    r"\bsp\s*pd\b",
    r"\bsp\s*b\b",
    r"\bsp\s*jp\b",
    r"\bm\s*kes\b",
    r"\bs\s*ked\b",
    r"\bs\s*km\b",
    r"\bs\s*si\b",
    r"\bs\s*kom\b",
    r"\ba\s*md\b",
]


GENERAL_REPLACEMENTS = {
    "rs":
        "rumah sakit",

    "rumkit":
        "rumah sakit",

    "r s":
        "rumah sakit",

    "rsud":
        "rumah sakit umum daerah",

    "rsp":
        "rumah sakit pusat",

    "jl":
        "jalan",

    "jln":
        "jalan",

    "jlnn":
        "jalan",

    "jlnt":
        "jalan",

    "no":
        "nomor",

    "nomor":
        "nomor",

    "kec":
        "kecamatan",

    "kel":
        "kelurahan",

    "kab":
        "kabupaten",

    "kota":
        "kota",

    "prov":
        "provinsi",
}


EXPERTISE_REPLACEMENTS = {
    "ppr":
        "petugas proteksi radiasi",

    "radiographer":
        "radiografer",

    "radiography":
        "radiografer",

    "radiologi diagnostik":
        "radiologi diagnostik",

    "radiodiagnostik":
        "radiologi diagnostik",

    "fisikawan medik":
        "fisikawan medik",

    "fisika medik":
        "fisikawan medik",

    "dokter spesialis radiologi":
        "radiologi",

    "sp rad":
        "radiologi",
}


def normalize_basic(
    value,
):
    if value is None:
        return ""

    value = unicodedata.normalize(
        "NFKC",
        str(value),
    )

    value = value.lower()

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


def apply_replacements(
    value,
    replacements,
):
    value = normalize_basic(
        value
    )

    for source, target in (
        sorted(
            replacements.items(),
            key=lambda item:
                len(item[0]),
            reverse=True,
        )
    ):

        value = re.sub(
            r"\b"
            + re.escape(
                source
            )
            + r"\b",
            target,
            value,
        )

    value = re.sub(
        r"\s+",
        " ",
        value,
    )

    return value.strip()


def normalize_name(
    value,
):
    value = normalize_basic(
        value
    )

    if not value:
        return ""

    tokens = value.split()

    while (
        tokens
        and tokens[0]
        in NAME_PREFIXES
    ):
        tokens.pop(0)

    value = " ".join(
        tokens
    )

    for pattern in (
        NAME_SUFFIX_PATTERNS
    ):
        value = re.sub(
            pattern,
            " ",
            value,
        )

    value = re.sub(
        r"\s+",
        " ",
        value,
    )

    return value.strip()


def normalize_expertise(
    value,
):
    return apply_replacements(
        value,
        EXPERTISE_REPLACEMENTS,
    )


def normalize_hospital(
    value,
):
    return apply_replacements(
        value,
        GENERAL_REPLACEMENTS,
    )


def normalize_address(
    value,
):
    value = apply_replacements(
        value,
        GENERAL_REPLACEMENTS,
    )

    value = re.sub(
        r"\b(rt|rw)\s*\d+[a-z]?\b",
        " ",
        value,
    )

    value = re.sub(
        r"\bkode pos\s*\d+\b",
        " ",
        value,
    )

    value = re.sub(
        r"\s+",
        " ",
        value,
    )

    return value.strip()


def token_set(
    value,
):
    return set(
        normalize_basic(
            value
        ).split()
    )


def token_overlap(
    left,
    right,
):
    left_tokens = token_set(
        left
    )

    right_tokens = token_set(
        right
    )

    if (
        not left_tokens
        or not right_tokens
    ):
        return 0.0

    intersection = (
        left_tokens
        & right_tokens
    )

    return (
        len(intersection)
        /
        min(
            len(left_tokens),
            len(right_tokens),
        )
        * 100
    )


def flexible_similarity(
    expected,
    actual,
):
    expected = normalize_basic(
        expected
    )

    actual = normalize_basic(
        actual
    )

    if (
        not expected
        or not actual
    ):
        return 0.0

    if expected in actual:
        return 100.0

    return round(
        max(
            fuzz.token_set_ratio(
                expected,
                actual,
            ),
            fuzz.token_sort_ratio(
                expected,
                actual,
            ),
            fuzz.partial_ratio(
                expected,
                actual,
            ),
            token_overlap(
                expected,
                actual,
            ),
        ),
        2,
    )


def name_similarity(
    expected,
    document_text,
):
    expected = normalize_name(
        expected
    )

    document = normalize_name(
        document_text
    )

    if not expected:
        return 0.0

    if expected in document:
        return 100.0

    return round(
        max(
            fuzz.token_set_ratio(
                expected,
                document,
            ),
            fuzz.partial_ratio(
                expected,
                document,
            ),
        ),
        2,
    )


def expertise_similarity(
    expected,
    document_text,
):
    expected = normalize_expertise(
        expected
    )

    actual = normalize_expertise(
        document_text
    )

    if not expected:
        return 0.0

    if expected in actual:
        return 100.0

    return round(
        max(
            fuzz.token_set_ratio(
                expected,
                actual,
            ),
            fuzz.partial_ratio(
                expected,
                actual,
            ),
            token_overlap(
                expected,
                actual,
            ),
        ),
        2,
    )


def match_personnel_pair(
    document_text,
    personnel_list,
):
    candidates = []

    for index, person in enumerate(
        personnel_list
    ):

        name = person.get(
            "nama"
        )

        expertise = person.get(
            "keahlian_klasifikasi"
        )

        name_score = (
            name_similarity(
                name,
                document_text,
            )
        )

        expertise_score = (
            expertise_similarity(
                expertise,
                document_text,
            )
        )

        pair_score = (
            name_score * 0.55
            +
            expertise_score * 0.45
        )

        if (
            name_score >= 88
            and expertise_score >= 78
        ):
            status = "MATCH"

        elif (
            name_score >= 75
            and expertise_score >= 60
        ):
            status = "REVIEW"

        else:
            status = "MISMATCH"

        candidates.append({
            "personnel_index":
                index,

            "name":
                name,

            "expertise":
                expertise,

            "name_score":
                round(
                    name_score,
                    2,
                ),

            "expertise_score":
                round(
                    expertise_score,
                    2,
                ),

            "pair_score":
                round(
                    pair_score,
                    2,
                ),

            "status":
                status,
        })

    candidates.sort(
        key=lambda item:
            item[
                "pair_score"
            ],
        reverse=True,
    )

    if not candidates:

        return {
            "status":
                "MISSING",

            "selected_personnel_index":
                None,

            "candidates":
                [],
        }

    best = candidates[
        0
    ]

    second = (
        candidates[
            1
        ]
        if len(
            candidates
        ) > 1
        else None
    )

    gap = (
        best[
            "pair_score"
        ]
        -
        (
            second[
                "pair_score"
            ]
            if second
            else 0
        )
    )

    if (
        best[
            "status"
        ] == "MATCH"
        and (
            gap >= 3
            or len(
                candidates
            ) == 1
        )
    ):
        final_status = "MATCH"

    elif (
        best[
            "status"
        ] in {
            "MATCH",
            "REVIEW",
        }
    ):
        final_status = "REVIEW"

    else:
        final_status = "MISMATCH"

    return {
        "status":
            final_status,

        "selected_personnel_index":
            best[
                "personnel_index"
            ],

        "best":
            best,

        "score_gap":
            round(
                gap,
                2,
            ),

        "candidates":
            candidates,
    }


def location_similarity(
    expected,
    document_text,
):
    expected = normalize_address(
        expected
    )

    document = normalize_address(
        document_text
    )

    if (
        not expected
        or not document
    ):
        return 0.0

    if expected in document:
        return 100.0

    token_score = (
        fuzz.token_set_ratio(
            expected,
            document,
        )
    )

    partial_score = (
        fuzz.partial_ratio(
            expected,
            document,
        )
    )

    overlap = token_overlap(
        expected,
        document,
    )

    return round(
        max(
            token_score,
            partial_score,
            overlap,
        ),
        2,
    )


def match_practice_address(
    expected,
    document_text,
):
    score = location_similarity(
        expected,
        document_text,
    )

    if score >= 78:
        status = "MATCH"

    elif score >= 58:
        status = "REVIEW"

    else:
        status = "MISMATCH"

    return {
        "status":
            status,

        "expected":
            expected,

        "score":
            score,
    }


def match_hospital_name(
    expected,
    document_text,
):
    expected = normalize_hospital(
        expected
    )

    actual = normalize_hospital(
        document_text
    )

    if (
        not expected
        or not actual
    ):
        return {
            "status":
                "MISSING",

            "expected":
                expected,

            "score":
                0,
        }

    score = max(
        fuzz.token_set_ratio(
            expected,
            actual,
        ),
        fuzz.partial_ratio(
            expected,
            actual,
        ),
        token_overlap(
            expected,
            actual,
        ),
    )

    if score >= 82:
        status = "MATCH"

    elif score >= 65:
        status = "REVIEW"

    else:
        status = "MISMATCH"

    return {
        "status":
            status,

        "expected":
            expected,

        "score":
            round(
                score,
                2,
            ),
    }


def match_address(
    expected,
    document_text,
):
    score = location_similarity(
        expected,
        document_text,
    )

    if score >= 75:
        status = "MATCH"

    elif score >= 55:
        status = "REVIEW"

    else:
        status = "MISMATCH"

    return {
        "status":
            status,

        "expected":
            expected,

        "score":
            score,
    }


def expiry_result(
    parsed_document,
):
    expiry = parsed_document.get(
        "expiry",
        {},
    )

    state = expiry.get(
        "status"
    )

    if state == "ACTIVE":
        status = "MATCH"

    elif state == "EXPIRED":
        status = "MISMATCH"

    else:
        status = "REVIEW"

    return {
        "status":
            status,

        "expiry_status":
            state,

        "expiry_date":
            expiry.get(
                "expiry_date"
            ),

        "evidence":
            expiry.get(
                "evidence"
            ),

        "reason":
            expiry.get(
                "reason"
            ),
    }


def aggregate_status(
    statuses,
):
    if "MISMATCH" in statuses:
        return "MISMATCH"

    if "REVIEW" in statuses:
        return "REVIEW"

    if "MISSING" in statuses:
        return "INCOMPLETE"

    return "VALID"


def validate_sip(
    document,
    application,
):
    text = document[
        "text"
    ]

    personnel = application.get(
        "personnel",
        [],
    )

    general = application.get(
        "general",
        {},
    )

    employee = (
        match_personnel_pair(
            text,
            personnel,
        )
    )

    # SIP terbaru: cocokan TEMPAT PRAKTIK
    # dengan alamat proyek, bukan nama instansi.
    from src.matching.personnel_evidence_v40 import find_address
    expected_address=general.get('alamat_proyek')
    if isinstance(expected_address,dict):expected_address=expected_address.get('value')
    found_address,found_score=find_address(text,expected_address)
    practice_place={
        'expected':expected_address, 'observed':found_address,
        'score':found_score,
        'status':('MATCH' if found_score is not None and found_score>=85 else 'REVIEW'),
    }

    validity = expiry_result(
        document
    )
    approval = detect_approval(document.get("pages") or [], text)

    overall = aggregate_status(
        [
            employee[
                "status"
            ],
            practice_place[
                "status"
            ],
            validity[
                "status"
            ],
        ]
    )

    return {
        "document_type":
            "SIP",

        "employee":
            employee,

        "practice_place":
            practice_place,

        "validity":
            validity,

        "approval": approval,

        "status":
            overall,
    }


def validate_sib(
    document,
    application,
):
    text = document[
        "text"
    ]

    employee = (
        match_personnel_pair(
            text,
            application.get(
                "personnel",
                [],
            ),
        )
    )

    validity = expiry_result(
        document
    )

    overall = aggregate_status(
        [
            employee[
                "status"
            ],
            validity[
                "status"
            ],
        ]
    )

    return {
        "document_type":
            "SIB",

        "employee":
            employee,

        "validity":
            validity,

        "status":
            overall,
    }

def extract_sprint_assignment_section(
    text,
):
    if not text:
        return {
            "found": False,
            "text": "",
            "start_marker": None,
            "end_marker": None,
        }

    original = str(
        text
    )

    normalized = normalize_basic(
        original
    )

    start_patterns = [
        r"\bmemerintahkan\s+kepada\b",
        r"\bmemerintahkan\b",
        r"\bkepada\s*:",
        r"\bkepada\b",
    ]

    end_patterns = [
        r"\buntuk\s*:",
        r"\buntuk\b",
        r"\bdengan\s+tugas\b",
        r"\buntuk\s+melaksanakan\b",
    ]

    start_match = None

    for pattern in start_patterns:

        match = re.search(
            pattern,
            normalized,
            flags=re.IGNORECASE,
        )

        if match:

            start_match = match
            break

    if not start_match:

        return {
            "found": False,
            "text": "",
            "start_marker": None,
            "end_marker": None,
        }

    section_start = (
        start_match.end()
    )

    remaining = normalized[
        section_start:
    ]

    end_position = None
    end_marker = None

    for pattern in end_patterns:

        match = re.search(
            pattern,
            remaining,
            flags=re.IGNORECASE,
        )

        if match:

            position = match.start()

            if (
                end_position is None
                or position < end_position
            ):
                end_position = position
                end_marker = match.group(0)

    if end_position is not None:

        section = remaining[
            :end_position
        ]

    else:

        section = remaining[
            :1000
        ]

    return {
        "found": True,
        "text": section.strip(),
        "start_marker":
            start_match.group(0),

        "end_marker":
            end_marker,
    }
    
def sprint_name_similarity(
    expected_name,
    assignment_text,
):
    expected = normalize_name(
        expected_name
    )

    actual = normalize_name(
        assignment_text
    )

    if (
        not expected
        or not actual
    ):
        return 0.0

    if expected in actual:

        return 100.0

    expected_tokens = set(
        expected.split()
    )

    actual_tokens = set(
        actual.split()
    )

    if (
        expected_tokens
        and expected_tokens.issubset(
            actual_tokens
        )
    ):
        return 100.0

    ratio = fuzz.ratio(
        expected,
        actual
    )

    token_score = (
        fuzz.token_set_ratio(
            expected,
            actual,
        )
    )

    partial_score = (
        fuzz.partial_ratio(
            expected,
            actual,
        )
    )

    return round(
        max(
            ratio,
            token_score,
            partial_score,
        ),
        2,
    )
    
def match_sprint_assigned_person(
    document_text,
    personnel_list,
):
    assignment = (
        extract_sprint_assignment_section(
            document_text
        )
    )

    if not assignment[
        "found"
    ]:

        return {
            "status": "REVIEW",

            "selected_personnel_index":
                None,

            "name":
                None,

            "name_score":
                0.0,

            "assignment_section":
                None,

            "reason":
                (
                    "Bagian petugas yang "
                    "ditugaskan pada Surat "
                    "Perintah belum dapat "
                    "diidentifikasi."
                ),

            "candidates":
                [],
        }

    assignment_text = assignment[
        "text"
    ]

    candidates = []

    for index, person in enumerate(
        personnel_list
    ):

        name = person.get(
            "nama"
        )

        score = (
            sprint_name_similarity(
                name,
                assignment_text,
            )
        )

        candidates.append({
            "personnel_index":
                index,

            "name":
                name,

            "name_score":
                score,
        })

    candidates.sort(
        key=lambda item:
            item[
                "name_score"
            ],
        reverse=True,
    )

    if not candidates:

        return {
            "status": "MISSING",

            "selected_personnel_index":
                None,

            "name":
                None,

            "name_score":
                0.0,

            "assignment_section":
                assignment_text,

            "reason":
                (
                    "Data personel pada "
                    "Formulir Permohonan kosong."
                ),

            "candidates":
                [],
        }

    best = candidates[0]

    second = (
        candidates[1]
        if len(candidates) > 1
        else None
    )

    second_score = (
        second[
            "name_score"
        ]
        if second
        else 0
    )

    gap = (
        best[
            "name_score"
        ]
        - second_score
    )

    if (
        best[
            "name_score"
        ] >= 90
        and (
            gap >= 5
            or len(
                candidates
            ) == 1
        )
    ):

        status = "MATCH"
        reason = None

    elif (
        best[
            "name_score"
        ] >= 75
    ):

        status = "REVIEW"

        reason = (
            "Nama petugas mirip dengan "
            "data Formulir, tetapi perlu "
            "konfirmasi evaluator."
        )

    else:

        status = "MISMATCH"

        reason = (
            "Nama petugas yang ditugaskan "
            "tidak sesuai dengan data "
            "personel pada Formulir."
        )

    return {
        "status":
            status,

        "selected_personnel_index":
            best[
                "personnel_index"
            ],

        "name":
            best[
                "name"
            ],

        "name_score":
            best[
                "name_score"
            ],

        "assignment_section":
            assignment_text,

        "score_gap":
            round(
                gap,
                2,
            ),

        "reason":
            reason,

        "candidates":
            candidates,
    }

def validate_sprint(
    document,
    application,
):
    text = document[
        "text"
    ]

    general = application.get(
        "general",
        {},
    )

    personnel = application.get(
        "personnel",
        [],
    )

    assigned_person = (
        match_sprint_assigned_person(
            text,
            personnel,
        )
    )

    hospital = (
        match_hospital_name(
            general.get(
                "instansi"
            ),
            text,
        )
    )

    address = (
        match_address(
            general.get(
                "alamat_proyek"
            ),
            text,
        )
    )

    approval = detect_approval(
        document.get(
            "pages",
            [],
        ),
        text,
    )

    approval_status = (
        "MATCH"
        if approval.get(
            "status"
        ) == "DETECTED"
        else "REVIEW"
    )

    overall = aggregate_status(
        [
            assigned_person[
                "status"
            ],

            hospital[
                "status"
            ],

            address[
                "status"
            ],

            approval_status,
        ]
    )

    return {
        "document_type":
            "SPRINT",

        "assigned_person":
            assigned_person,

        "hospital":
            hospital,

        "address":
            address,

        "approval": {
            **approval,

            "validation_status":
                approval_status,
        },

        "status":
            overall,
    }

# v39: Additional personnel document types. Every field is tied to a real OCR line.
PERSONNEL_FIELDS = {
    'COMPETENCE': [('Nama Petugas','person'),('Masa Berlaku','expiry'),('Status Kompetensi','pass'),('Pengesahan','approval')],
    'WORK_PERMIT': [('Nama Petugas','person'),('Nama Fasilitas','facility'),('Alamat Fasilitas','address'),('Masa Berlaku','expiry'),('Pengesahan','approval')],
    'WORK_LETTER': [('Nama Petugas','person'),('Keahlian','expertise'),('Nama Fasilitas','facility'),('Pengesahan','approval')],
    'ASSIGNMENT': [('Nama Petugas','person'),('Nama Fasilitas','facility'),('Keahlian','expertise'),('Pengesahan','approval')],
    'DOSE': [('Nama Fasilitas','facility'),('Alamat Fasilitas','address'),('Nama Petugas','people'),('Pengesahan','approval')],
}

def _candidate_evidence(text, expected, kind):
    from src.matching.personnel_evidence_v40 import find_evidence
    return find_evidence(text, expected, kind)


def validate_additional_personnel(document, application):
    """One field, one attributable source value; no global-text fuzzy MATCH."""
    from datetime import date
    from dateutil import parser as date_parser
    from src.matching.personnel_evidence_v42 import (
        address_evidence, workplace_address, choose_person_reference,
        personnel_role_quote, explicit_assignment_role, monitored_dose_person,
        related_facility_score, compact_person_quote,
    )
    from src.matching.personnel_evidence_v40 import (
        find_evidence, find_practice_facility, find_pass_status, _facility_score,
    )
    dtype=document.get('document_type')
    text=document.get('text') or ''
    general=application.get('general') or {}
    personnel=application.get('personnel') or []
    facility=general.get('nama_fasilitas') or general.get('nama_rs') or general.get('instansi')
    address=general.get('alamat_proyek')
    if isinstance(facility,dict):facility=facility.get('value')
    if isinstance(address,dict):address=address.get('value')
    role_context=explicit_assignment_role(text) if dtype=='ASSIGNMENT' else None
    best_person=choose_person_reference(text,personnel,role_hint=role_context)
    references=[]
    for person in personnel:
        name=person.get('nama') or person.get('name')
        role=person.get('keahlian') or person.get('keahlian_klasifikasi') or person.get('profesi') or person.get('jabatan')
        if name:references.append((name,role))
    expected_person=best_person[0] if best_person else (references[0][0] if references else None)
    expected_expertise=best_person[3] if best_person else (references[0][1] if references else None)
    expiry=(document.get('expiry') or {}).get('expiry_date')
    workplace=find_practice_facility(text) if dtype=='WORK_PERMIT' else None
    rows=[]
    approval_result = (detect_approval(document.get('pages') or [], text)
                       if any(kind=='approval' for _label,kind in PERSONNEL_FIELDS[dtype])
                       else {})
    def add(label, expected, observed, score, status):
        rows.append({'field':label,'expected':expected or '—',
                     'observed':observed or '—','score':score,'status':status})
    for label,kind in PERSONNEL_FIELDS[dtype]:
        if kind=='people':
            seen=set()
            for name,_ in references:
                key=normalize_name(name)
                if key in seen:continue
                seen.add(key)
                observed,score=monitored_dose_person(text,name)
                if observed is not None and score is not None and score>=85:
                    add(f'Nama Petugas: {name}',name,observed,score,
                        'MATCH' if score>=90 else 'REVIEW')
        elif kind=='person':
            quote=compact_person_quote(text,expected_person)
            if quote is None and best_person:quote=best_person[1]
            # Do not copy a global similarity score if the observed line is absent.
            score=best_person[2] if quote is not None and best_person else None
            add(label,expected_person,quote,score,
                'MATCH' if score is not None and score>=90 else 'REVIEW')
        elif kind=='expertise':
            observed,score=personnel_role_quote(text,expected_expertise,assignment=dtype=='ASSIGNMENT')
            add(label,expected_expertise,observed,score,
                'MATCH' if score is not None and score>=90 else 'REVIEW')
        elif kind=='facility':
            expected=facility
            if dtype=='WORK_PERMIT' and workplace:
                observed=workplace
                score=_facility_score(expected,observed)
                status='MATCH' if score is not None and score>=90 else 'MISMATCH' if score is None else 'REVIEW'
            else:
                observed,score=find_evidence(text,expected,'facility')
                if dtype=='DOSE' and observed:
                    addr_quote,addr_score,_=address_evidence(text,address)
                    score=related_facility_score(expected,observed,addr_quote,addr_score)
                status='MATCH' if score is not None and score>=90 else 'REVIEW'
            add(label,expected,observed,score,status)
        elif kind=='address':
            expected=address
            if dtype=='WORK_PERMIT':
                observed,score,status=workplace_address(text,expected)
            else:
                observed,score,status=address_evidence(text,expected)
            add(label,expected,observed,score,status)
        elif kind=='expiry':
            try:
                parsed=date_parser.parse(str(expiry),dayfirst=False).date() if expiry else None
                state=(document.get('expiry') or {}).get('status')
                status=('MATCH' if parsed>=date.today() else 'MISMATCH') if parsed and state in ('ACTIVE','EXPIRED') else 'REVIEW'
            except (ValueError,TypeError,OverflowError):status='REVIEW'
            add(label,expiry,(document.get('expiry') or {}).get('evidence'),None,status)
        elif kind=='pass':
            observed,passed=find_pass_status(text)
            add(label,'Lulus / Kompeten',observed,100 if passed is True else 0 if passed is False else None,
                'MATCH' if passed is True else 'MISMATCH' if passed is False else 'REVIEW')
        elif kind=='approval':
            detected=approval_result.get('status')=='DETECTED'
            add(label,'Bukti pengesahan',
                'Indikasi pengesahan ditemukan' if detected else None,
                100 if detected else None,'MATCH' if detected else 'REVIEW')
    return {'document_type':dtype,'fields':rows,'approval':approval_result,
            'status':aggregate_status([r['status'] for r in rows])}

def validate_personnel_document(
    document,
    application,
):
    document_type = document.get(
        "document_type"
    )

    if document_type in PERSONNEL_FIELDS:
        return validate_additional_personnel(document, application)

    if document_type == "SIP":

        return validate_sip(
            document,
            application,
        )

    if document_type == "SIB":

        return validate_sib(
            document,
            application,
        )

    if document_type == "SPRINT":

        return validate_sprint(
            document,
            application,
        )

    return {
        "document_type":
            "UNKNOWN",

        "status":
            "REVIEW",

        "reason":
            (
                "Jenis dokumen belum "
                "dapat dikenali."
            ),
    }


def validate_personnel_documents(
    documents,
    application,
):
    results = []

    for document in documents:

        validation = (
            validate_personnel_document(
                document,
                application,
            )
        )

        results.append({
            "source_id":
                document.get(
                    "source_id"
                ),

            "source_name":
                document.get(
                    "source_name"
                ),

            "detected_type":
                document.get(
                    "document_type"
                ),

            "validation":
                validation,
        })

    return results