import re

FIELDS = {
    "instansi": "Instansi",
    "alamat_proyek": "Alamat Proyek",
}

def clean_value(value):
    if value is None:
        return None

    value = re.sub(
        r"\s+",
        " ",
        value
    )

    value = value.strip(
        " :\n\t"
    )

    return value or None

def extract_value(
    text,
    label,
    next_labels
):

    escaped_label = re.escape(
        label
    )

    if next_labels:

        next_pattern = "|".join(
            re.escape(item)
            for item in next_labels
        )

        lookahead = (
            rf"(?=\s*(?:{next_pattern})\s*:?"
            rf"|$)"
        )

    else:

        lookahead = r"(?=$)"

    pattern = (
        rf"{escaped_label}"
        rf"\s*:?\s*"
        rf"(.*?)"
        rf"{lookahead}"
    )

    match = re.search(
        pattern,
        text,
        flags=(
            re.IGNORECASE
            |
            re.DOTALL
        )
    )

    if not match:
        return None

    value = match.group(
        1
    )

    return clean_value(
        value
    )

def extract_general_info(
    text
):
    all_labels = [
        "Nomor Registrasi",
        "Tanggal Registrasi",
        "Lingkup Kegiatan",
        "Instansi",
        "Alamat Instansi",
        "Nama Proyek",
        "Alamat Proyek",
        "A. Kelengkapan Administrasi",
    ]

    result = {}

    instansi_index = all_labels.index(
        "Instansi"
    )

    result[
        "instansi"
    ] = extract_value(
        text=text,
        label="Instansi",
        next_labels=all_labels[
            instansi_index + 1:
        ]
    )

    alamat_proyek_index = (
        all_labels.index(
            "Alamat Proyek"
        )
    )

    result[
        "alamat_proyek"
    ] = extract_value(
        text=text,
        label="Alamat Proyek",
        next_labels=all_labels[
            alamat_proyek_index + 1:
        ]
    )

    # Pisahkan nama fasilitas dari alamat proyek serta buang segmen kontak.
    # Simpan teks asli untuk audit tanpa mempengaruhi matching.
    raw_project = result.get("alamat_proyek") or ""
    result["alamat_proyek_asli"] = raw_project or None
    address_start = re.search(
        r"(?<![A-Za-z])(?:jl\.?|jln\.?|jalan|gg\.?|gang|kompleks|komplek|"
        r"kawasan|dusun|desa|kelurahan|kampung|kp\.?|lorong|lr\.?)\s+",
        raw_project, flags=re.I,
    )
    if address_start:
        facility = raw_project[:address_start.start()].strip(" ,;:-")
        address = raw_project[address_start.start():].strip(" ,;:-")
    elif "," in raw_project:
        facility, address = (part.strip(" ,;:-") for part in raw_project.split(",", 1))
    else:
        facility, address = None, raw_project.strip(" ,;:-")

    # Hapus mulai penanda nomor telepon/faks, termasuk variasi penulisan:
    # Telp., Tel., Telepon, Telephone, Phone, HP, No. Telp, Fax, Faks, Facsimile.
    # Kontak sering ada di akhir alamat dan dapat dipisah koma atau titik koma.
    contact_label = re.compile(
        r"(?i)(?<![a-z])(?:no\.?\s*)?(?:tel(?:p|pon|epon|ephone)?\.?|"
        r"telephone|telepon|phone|handphone|hp\.?|"
        r"fax\.?|faks\.?|facsimile|faksimile)\s*(?:no\.?|nomor)?\s*[:.\-]?\s*(?=\+?\d|\(|:|\-|$)",
    )
    m = contact_label.search(address)
    if m:
        address = address[:m.start()]
    # Buang pemisah tersisa dari akhir alamat, jangan potong angka kode pos.
    address = re.sub(r"[\s,;:/-]+$", "", address).strip()

    result["nama_fasilitas"] = facility or None
    result["alamat_proyek"] = address or None
    result["instansi_asli"] = result.get("instansi")
    # Kunci legacy dipakai oleh matcher lama untuk identitas fasilitas.
    result["instansi"] = result["nama_fasilitas"]
    return result
