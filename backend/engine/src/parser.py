import pymupdf
import pdfplumber

from .extraction.general_info import (
    extract_general_info,
)

from .extraction.technical_tables import (
    is_personnel_table,
    parse_personnel_table,
    is_equipment_table,
    parse_equipment_table,
    is_equipment_continuation_table,
    parse_equipment_continuation_table,
)

def extract_full_text(pdf_path):
    from .extraction.document_reader import read_pages
    return '\n'.join(page['text'] for page in read_pages(pdf_path, min_chars=70))

def parse_application(pdf_path):
    full_text = extract_full_text(
        pdf_path
    )

    result = {
        "general": extract_general_info(
            full_text
        ),

        "personnel": [],

        "equipment": [],
    }

    with pdfplumber.open(
        pdf_path
    ) as pdf:

        for page in pdf.pages:

            tables = page.extract_tables()


            for table in tables:

                if not table:
                    continue

                if is_personnel_table(
                    table
                ):

                    result[
                        "personnel"
                    ].extend(
                        parse_personnel_table(
                            table
                        )
                    )

                    continue

                if is_equipment_table(
                    table
                ):

                    result[
                        "equipment"
                    ].extend(
                        parse_equipment_table(
                            table
                        )
                    )

                    continue
                
                if is_equipment_continuation_table(
                    table
                ):

                    result[
                        "equipment"
                    ].extend(
                        parse_equipment_continuation_table(
                            table
                        )
                    )

                    continue

    if not result['equipment']:
        # A scanned table requires an independently validated OCR-table parser.
        # Refuse a false success: the text OCR is still useful for general info.
        result.setdefault('warnings', []).append(
            'Tabel peralatan tidak terdeteksi. Jika Formulir berupa scan, '
            'hasil OCR teks belum cukup untuk menyimpulkan data alat; perlu pemeriksaan tabel.'
        )
    return result