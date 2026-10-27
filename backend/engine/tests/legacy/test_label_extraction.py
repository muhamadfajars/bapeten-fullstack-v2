import json

from src.extraction.label_ocr import (
    extract_ocr,
    print_ocr_results,
)

from src.extraction.label_parser import (
    parse_unit_label,
    parse_tube_label,
)

from src.extraction.image_preprocess import (
    create_ocr_variants,
)


# =========================================================
# CONFIG
# =========================================================

IMAGE_PATH = "data/sample/labeltabung4.jpg"

# "unit" atau "tube"
LABEL_TYPE = "tube"

# Pilihan:
# original
# crop
# crop_upscaled
# crop_upscaled_clahe
# crop_upscaled_clahe_sharpen
OCR_METHOD = "original"


# Untuk gambar Siemens ini
CROP_CONFIG = {
    "top": 0.45,
    "bottom": 1.0,
    "left": 0.0,
    "right": 1.0
}


# =========================================================
# MAIN
# =========================================================

def main():

    print("\n" + "=" * 80)
    print("LABEL EXTRACTION TEST")
    print("=" * 80)

    print(f"Image      : {IMAGE_PATH}")
    print(f"Label type : {LABEL_TYPE}")
    print(f"OCR method : {OCR_METHOD}")


    # =====================================================
    # 1. PREPROCESS
    # =====================================================

    variants = create_ocr_variants(
        IMAGE_PATH,
        crop_config=CROP_CONFIG
    )


    if OCR_METHOD not in variants:

        raise ValueError(
            f"OCR_METHOD '{OCR_METHOD}' tidak tersedia.\n"
            f"Pilihan: {list(variants.keys())}"
        )


    selected_image = variants[
        OCR_METHOD
    ]


    # =====================================================
    # 2. OCR
    # =====================================================

    print("\nMenjalankan OCR...")

    ocr_results = extract_ocr(
        selected_image
    )


    print_ocr_results(
        ocr_results,
        title="RAW OCR"
    )


    # =====================================================
    # 3. PARSER
    # =====================================================

    if LABEL_TYPE.lower() == "unit":

        extracted = parse_unit_label(
            ocr_results
        )

    elif LABEL_TYPE.lower() == "tube":

        extracted = parse_tube_label(
            ocr_results
        )

    else:

        raise ValueError(
            "LABEL_TYPE harus 'unit' atau 'tube'"
        )


    # =====================================================
    # 4. STRUCTURED RESULT
    # =====================================================

    print("\n" + "=" * 80)
    print("EXTRACTED DATA")
    print("=" * 80)

    print(
        json.dumps(
            extracted,
            indent=4,
            ensure_ascii=False
        )
    )


    # =====================================================
    # 5. HUMAN READABLE
    # =====================================================

    print("\n" + "=" * 80)
    print("RINGKASAN")
    print("=" * 80)


    manufacturer = extracted.get(
        "manufacturer"
    )


    # -----------------------------------------------------
    # Manufacturer
    # -----------------------------------------------------

    if manufacturer:

        print(
            f"Manufacturer : "
            f"{manufacturer.get('normalized')}"
        )

        print(
            f"  Raw        : "
            f"{manufacturer.get('raw')}"
        )

        confidence = manufacturer.get(
            "confidence"
        )

        if confidence is not None:

            print(
                f"  Confidence : "
                f"{confidence:.3f}"
            )

    else:

        print(
            "Manufacturer : Tidak ditemukan"
        )


    # -----------------------------------------------------
    # UNIT
    # -----------------------------------------------------

    if LABEL_TYPE.lower() == "unit":

        unit_type = extracted.get(
            "unit_type",
            {}
        )

        serial = extracted.get(
            "serial_number",
            {}
        )


        print(
            f"\nUnit Type    : "
            f"{unit_type.get('value')}"
        )

        if unit_type.get(
            "confidence"
        ) is not None:

            print(
                f"  Confidence : "
                f"{unit_type.get('confidence'):.3f}"
            )


        print(
            f"\nSerial Number: "
            f"{serial.get('value')}"
        )

        if serial.get(
            "confidence"
        ) is not None:

            print(
                f"  Confidence : "
                f"{serial.get('confidence'):.3f}"
            )


    # -----------------------------------------------------
    # TUBE
    # -----------------------------------------------------

    elif LABEL_TYPE.lower() == "tube":

        tube_type = extracted.get(
            "tube_type",
            {}
        )

        serial = extracted.get(
            "serial_number",
            {}
        )

        candidates = extracted.get(
            "candidates",
            {}
        )


        print(
            f"\nTube Type    : "
            f"{tube_type.get('value')}"
        )

        if tube_type.get(
            "confidence"
        ) is not None:

            print(
                f"  Confidence : "
                f"{tube_type.get('confidence'):.3f}"
            )


        print(
            f"\nSerial Number: "
            f"{serial.get('value')}"
        )

        if serial.get(
            "confidence"
        ) is not None:

            print(
                f"  Confidence : "
                f"{serial.get('confidence'):.3f}"
            )


        if candidates:

            print(
                "\nAdditional Candidates:"
            )

            for key, value in (
                candidates.items()
            ):

                print(
                    f"  {key}: {value}"
                )


    print("\n" + "=" * 80)
    print("SELESAI")
    print("=" * 80)


if __name__ == "__main__":
    main()