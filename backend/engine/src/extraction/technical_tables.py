import re

from .utils import clean_text


def normalize_header(value):
    value = clean_text(value)

    if not value:
        return ""

    return value.lower()


def is_personnel_table(table):
    if not table:
        return False

    header = [
        normalize_header(x)
        for x in table[0]
    ]

    joined = " ".join(header)

    return (
        "npr" in joined
        and "nama" in joined
    )


def parse_personnel_table(table):
    header = [
        normalize_header(x)
        for x in table[0]
    ]

    index_npr = None
    index_nama = None
    index_klasifikasi = None

    for index, column in enumerate(header):

        if "npr" in column:
            index_npr = index

        elif "nama" in column:
            index_nama = index

        elif (
            "klasifikasi" in column
            or "keahlian" in column
        ):
            index_klasifikasi = index

    results = []

    for row in table[1:]:

        if not row:
            continue

        npr = (
            clean_text(row[index_npr])
            if index_npr is not None
            else None
        )

        nama = (
            clean_text(row[index_nama])
            if index_nama is not None
            else None
        )

        klasifikasi = (
            clean_text(row[index_klasifikasi])
            if index_klasifikasi is not None
            else None
        )

        if not nama:
            continue

        results.append({
            "npr": npr,
            "nama": nama,
            "keahlian_klasifikasi": klasifikasi
        })

    return results


def is_equipment_table(table):
    if not table:
        return False

    header = [
        normalize_header(x)
        for x in table[0]
    ]

    joined = " ".join(header)

    signals = [
        "merk unit",
        "merk tabung",
        "kondisi maksimal"
    ]

    matches = sum(
        signal in joined
        for signal in signals
    )

    return matches >= 2

def is_equipment_continuation_table(table):
    if not table:
        return False

    if len(table) < 1:
        return False

    first_row = table[0]

    if not first_row:
        return False

    if len(first_row) < 6:
        return False

    first_cell = clean_text(
        first_row[0]
    )

    if not first_cell:
        return False

    return bool(
        re.fullmatch(
            r"\d+",
            first_cell
        )
    )


def parse_type_serial(text):
    if not text:
        return {
            "tipe": None,
            "nomor_seri": None,
            "raw_value": None
        }

    raw_value = clean_text(text)

    type_match = re.search(
        r"(?:Tipe|Type|Model)"
        r"\s*:?\s*"
        r"(.+?)"
        r"(?="
        r"\s*/?\s*"
        r"(?:No\.?\s*Seri|Serial(?:\s+Number)?|S/N)"
        r"|$)",
        raw_value,
        flags=re.IGNORECASE
    )

    serial_match = re.search(
        r"(?:No\.?\s*Seri|Serial(?:\s+Number)?|S/N)"
        r"\s*:?\s*"
        r"([A-Z0-9./_-]+)",
        raw_value,
        flags=re.IGNORECASE
    )

    tipe = None
    nomor_seri = None

    if type_match:
        tipe = clean_text(
            type_match.group(1)
        )

        if tipe:
            tipe = tipe.rstrip("/").strip()

    if serial_match:
        nomor_seri = clean_text(
            serial_match.group(1)
        )

        if nomor_seri:
            nomor_seri = (
                nomor_seri
                .strip("/")
                .strip()
            )

    if tipe or nomor_seri:
        return {
            "tipe": tipe,
            "nomor_seri": nomor_seri,
            "raw_value": raw_value
        }

    if "/" in raw_value:

        parts = [
            clean_text(part)
            for part in raw_value.split("/")
            if clean_text(part)
        ]

        if len(parts) >= 2:

            tipe = " / ".join(
                parts[:-1]
            )

            nomor_seri = parts[-1]

            return {
                "tipe": tipe,
                "nomor_seri": nomor_seri,
                "raw_value": raw_value
            }

    lines = [
        clean_text(line)
        for line in text.split("\n")
        if clean_text(line)
    ]

    lines = [
        line.strip().strip("/").strip()
        for line in lines
        if line
    ]

    if len(lines) >= 2:

        tipe = " ".join(
            lines[:-1]
        )

        nomor_seri = lines[-1]

    elif len(lines) == 1:

        tipe = lines[0]

    return {
        "tipe": tipe,
        "nomor_seri": nomor_seri,
        "raw_value": raw_value
    }


def parse_max_condition(text):
    if not text:
        return {
            "tegangan_maksimum_kv": None,
            "arus_maksimum_ma": None
        }

    normalized = clean_text(text)

    kv_match = re.search(
        r"(\d+(?:[.,]\d+)?)\s*kV",
        normalized,
        flags=re.IGNORECASE
    )

    ma_match = re.search(
        r"(\d+(?:[.,]\d+)?)\s*mA",
        normalized,
        flags=re.IGNORECASE
    )

    kv = (
        float(
            kv_match.group(1).replace(",", ".")
        )
        if kv_match
        else None
    )

    ma = (
        float(
            ma_match.group(1).replace(",", ".")
        )
        if ma_match
        else None
    )

    return {
        "tegangan_maksimum_kv": kv,
        "arus_maksimum_ma": ma
    }

def clean_brand(value):
    value = clean_text(value)

    if not value:
        return None

    value = re.sub(
        r"\s*\(\s*penambahan\s*\)\s*",
        " ",
        value,
        flags=re.IGNORECASE
    )

    value = re.sub(
        r"\s+",
        " ",
        value
    )

    return value.strip() or None

def parse_equipment_table(table):
    if not table:
        return []

    header = [
        normalize_header(x)
        for x in table[0]
    ]

    index_merk_unit = None
    index_tipe_unit = None
    index_merk_tabung = None
    index_tipe_tabung = None
    index_kondisi = None

    for index, column in enumerate(header):

        if "merk unit" in column:
            index_merk_unit = index

        elif (
            "tipe" in column
            and "seri" in column
            and "tabung" not in column
        ):
            index_tipe_unit = index

        elif "merk tabung" in column:
            index_merk_tabung = index

        elif (
            "tipe" in column
            and "seri" in column
            and "tabung" in column
        ):
            index_tipe_tabung = index

        elif "kondisi maksimal" in column:
            index_kondisi = index

    results = []

    for row in table[1:]:

        if not row:
            continue

        merk_unit = (
            clean_brand(row[index_merk_unit])
            if index_merk_unit is not None
            else None
        )

        unit_data = (
            parse_type_serial(row[index_tipe_unit])
            if index_tipe_unit is not None
            else {
                "tipe": None,
                "nomor_seri": None,
                "raw_value": None
            }
        )

        merk_tabung = (
            clean_brand(row[index_merk_tabung])
            if index_merk_tabung is not None
            else None
        )

        tabung_data = (
            parse_type_serial(row[index_tipe_tabung])
            if index_tipe_tabung is not None
            else {
                "tipe": None,
                "nomor_seri": None,
                "raw_value": None
            }
        )

        kondisi = (
            parse_max_condition(row[index_kondisi])
            if index_kondisi is not None
            else {
                "tegangan_maksimum_kv": None,
                "arus_maksimum_ma": None
            }
        )

        if not any([
            merk_unit,
            unit_data["tipe"],
            unit_data["nomor_seri"],
            merk_tabung,
            tabung_data["tipe"],
            tabung_data["nomor_seri"]
        ]):
            continue

        results.append({
            "merk_unit": merk_unit,
            "tipe_unit": unit_data["tipe"],
            "nomor_seri_unit": unit_data["nomor_seri"],
            "raw_tipe_no_seri_unit": unit_data["raw_value"],

            "merk_tabung": merk_tabung,
            "tipe_tabung": tabung_data["tipe"],
            "nomor_seri_tabung": tabung_data["nomor_seri"],
            "raw_tipe_no_seri_tabung": tabung_data["raw_value"],

            "tegangan_maksimum_kv":
                kondisi["tegangan_maksimum_kv"],

            "arus_maksimum_ma":
                kondisi["arus_maksimum_ma"]
        })

    return results

def parse_equipment_continuation_table(table):
    results = []

    for row in table:

        if not row or len(row) < 6:
            continue

        nomor = clean_text(
            row[0]
        )

        if not nomor or not re.fullmatch(
            r"\d+",
            nomor
        ):
            continue

        merk_unit = clean_brand(
            row[1]
        )

        unit_data = parse_type_serial(
            row[2]
        )

        merk_tabung = clean_brand(
            row[3]
        )

        tabung_data = parse_type_serial(
            row[4]
        )

        kondisi = parse_max_condition(
            row[5]
        )

        if not any([
            merk_unit,
            unit_data["tipe"],
            unit_data["nomor_seri"],
            merk_tabung,
            tabung_data["tipe"],
            tabung_data["nomor_seri"],
        ]):
            continue

        results.append({
            "merk_unit":
                merk_unit,

            "tipe_unit":
                unit_data["tipe"],

            "nomor_seri_unit":
                unit_data["nomor_seri"],

            "raw_tipe_no_seri_unit":
                unit_data["raw_value"],

            "merk_tabung":
                merk_tabung,

            "tipe_tabung":
                tabung_data["tipe"],

            "nomor_seri_tabung":
                tabung_data["nomor_seri"],

            "raw_tipe_no_seri_tabung":
                tabung_data["raw_value"],

            "tegangan_maksimum_kv":
                kondisi[
                    "tegangan_maksimum_kv"
                ],

            "arus_maksimum_ma":
                kondisi[
                    "arus_maksimum_ma"
                ],
        })

    return results