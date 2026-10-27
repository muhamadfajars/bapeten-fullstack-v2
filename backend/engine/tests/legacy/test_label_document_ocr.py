from src.extraction.label_document_ocr import (
    ocr_label_document,
    document_ocr_to_text,
)


FILE_PATH = (
    "data/sample/label_unit_tabung.pdf"
)


document_ocr = ocr_label_document(
    FILE_PATH
)


print(
    "Total halaman:",
    len(document_ocr)
)


pages_text = document_ocr_to_text(
    document_ocr
)


for page in pages_text:

    print(
        "\n"
        "=============================="
    )

    print(
        "PAGE",
        page["page"]
    )

    print(
        "=============================="
    )

    print(
        page["text"]
    )