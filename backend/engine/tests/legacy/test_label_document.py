from src.extraction.label_document import (
    prepare_label_document,
)


FILE_PATH = (
    "data/sample/label_unit_tabung.pdf"
)


pages = prepare_label_document(
    FILE_PATH
)


print(
    "Total image/page:",
    len(pages)
)


for item in pages:

    print(
        "Page:",
        item["page"],
        "| Source:",
        item["source_type"],
        "| Size:",
        item["width"],
        "x",
        item["height"]
    )