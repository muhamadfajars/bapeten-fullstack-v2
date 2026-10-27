from src.extraction.image_preprocess import (
    create_ocr_variants
)

from src.extraction.label_ocr import (
    extract_ocr,
    print_ocr_results
)


IMAGE_PATH = (
    "data/sample/labeltabung4.jpg"
)


# =========================================================
# CROP CONFIG
# =========================================================

# Untuk Siemens contoh kita,
# label target berada di bagian bawah.

crop_config = {
    "top": 0.45,
    "bottom": 1.0,
    "left": 0.0,
    "right": 1.0
}


# =========================================================
# CREATE VARIANTS
# =========================================================

variants = create_ocr_variants(
    IMAGE_PATH,
    crop_config=crop_config
)


# =========================================================
# OCR EACH VARIANT
# =========================================================

all_results = {}


for method_name, image in variants.items():

    results = extract_ocr(
        image
    )

    all_results[
        method_name
    ] = results


    print_ocr_results(
        results,
        title=method_name.upper()
    )