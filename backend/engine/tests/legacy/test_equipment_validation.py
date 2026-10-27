import json

from src.parser import (
    parse_application,
)

from src.extraction.label_pipeline import (
    extract_label_auto,
)

from src.matching.equipment_validator import (
    validate_unit,
    validate_tube,
)


# =========================================================
# CONFIG
# =========================================================

FORM_PATH = (
    "data/sample/form_permohonan.pdf"
)

UNIT_IMAGE = (
    "data/sample/label_unit.jpeg"
)

TUBE_IMAGE = (
    "data/sample/label_tabung.jpeg"
)


# =========================================================
# MAIN
# =========================================================

def main():

    # =====================================================
    # 1. PARSE FORMULIR
    # =====================================================

    print(
        "\nParsing Formulir Permohonan..."
    )

    application = parse_application(
        FORM_PATH
    )


    equipments = application.get(
        "equipment",
        []
    )


    if not equipments:

        raise ValueError(
            "Data equipment tidak ditemukan "
            "di Formulir Permohonan."
        )


    # Untuk sementara kita test alat pertama
    equipment = equipments[0]


    print(
        "\nData equipment dari formulir:"
    )

    print(
        json.dumps(
            equipment,
            indent=4,
            ensure_ascii=False
        )
    )


    # =====================================================
    # 2. EXTRACT LABEL UNIT
    # =====================================================

    print(
        "\nMemproses label unit..."
    )


    unit_pipeline = extract_label_auto(
        image_path=UNIT_IMAGE,
        label_type="unit"
    )


    unit_result = unit_pipeline[
        "result"
    ]


    # =====================================================
    # 3. EXTRACT LABEL TABUNG
    # =====================================================

    print(
        "\nMemproses label tabung..."
    )


    tube_pipeline = extract_label_auto(
        image_path=TUBE_IMAGE,
        label_type="tube"
    )


    tube_result = tube_pipeline[
        "result"
    ]


    # =====================================================
    # 4. VALIDATION
    # =====================================================

    unit_validation = validate_unit(
        equipment,
        unit_result
    )


    tube_validation = validate_tube(
        equipment,
        tube_result
    )


    # =====================================================
    # 5. OUTPUT
    # =====================================================

    print(
        "\n"
        + "=" * 80
    )

    print(
        "VALIDASI LABEL UNIT"
    )

    print(
        "=" * 80
    )


    print(
        json.dumps(
            unit_validation,
            indent=4,
            ensure_ascii=False
        )
    )


    print(
        "\n"
        + "=" * 80
    )

    print(
        "VALIDASI LABEL TABUNG"
    )

    print(
        "=" * 80
    )


    print(
        json.dumps(
            tube_validation,
            indent=4,
            ensure_ascii=False
        )
    )


if __name__ == "__main__":
    main()