from src.matching.label_matcher import (
    compare_label_data,
)


def build_unit_form_data(
    equipment
):
    """
    Ubah equipment dari parser PDF
    menjadi format standar untuk matcher.
    """

    return {
        "manufacturer":
            equipment.get(
                "merk_unit"
            ),

        "type":
            equipment.get(
                "tipe_unit"
            ),

        "serial_number":
            equipment.get(
                "nomor_seri_unit"
            ),
    }


def build_tube_form_data(
    equipment
):
    """
    Data tabung dari Formulir Permohonan.
    """

    return {
        "manufacturer":
            equipment.get(
                "merk_tabung"
            ),

        "type":
            equipment.get(
                "tipe_tabung"
            ),

        "serial_number":
            equipment.get(
                "nomor_seri_tabung"
            ),
    }


def build_unit_photo_data(
    label_result
):
    """
    Ubah hasil parse label unit
    menjadi format standar matcher.
    """

    manufacturer = label_result.get(
        "manufacturer"
    ) or {}

    unit_type = label_result.get(
        "unit_type"
    ) or {}

    serial = label_result.get(
        "serial_number"
    ) or {}


    return {
        "manufacturer":
            manufacturer.get(
                "normalized"
            ),

        "type":
            unit_type.get(
                "value"
            ),

        "serial_number":
            serial.get(
                "value"
            ),
    }


def build_tube_photo_data(
    label_result
):
    """
    Ubah hasil parse label tabung
    menjadi format standar matcher.
    """

    manufacturer = label_result.get(
        "manufacturer"
    ) or {}

    tube_type = label_result.get(
        "tube_type"
    ) or {}

    serial = label_result.get(
        "serial_number"
    ) or {}


    return {
        "manufacturer":
            manufacturer.get(
                "normalized"
            ),

        "type":
            tube_type.get(
                "value"
            ),

        "serial_number":
            serial.get(
                "value"
            ),
    }


def validate_unit(
    equipment,
    label_result
):
    """
    Compare data unit:
    form vs foto.
    """

    form_data = build_unit_form_data(
        equipment
    )

    photo_data = build_unit_photo_data(
        label_result
    )

    comparison = compare_label_data(
        form_data,
        photo_data
    )


    validation = {
        "form": form_data,
        "photo": photo_data,
        "comparison": comparison
    }

    validation["summary"] = (
        summarize_validation(
            validation
        )
    )

    return validation


def validate_tube(
    equipment,
    label_result
):
    """
    Compare data tabung:
    form vs foto.
    """

    form_data = build_tube_form_data(
        equipment
    )

    photo_data = build_tube_photo_data(
        label_result
    )

    comparison = compare_label_data(
        form_data,
        photo_data
    )


    validation = {
        "form": form_data,
        "photo": photo_data,
        "comparison": comparison
    }

    validation["summary"] = (
        summarize_validation(
            validation
        )
    )

    return validation
    
def summarize_validation(validation):
    """
    Membuat status keseluruhan dari comparison.
    """

    comparison = validation.get(
        "comparison",
        {}
    )

    statuses = []

    for field_result in comparison.values():

        status = field_result.get(
            "status"
        )

        if status:
            statuses.append(
                status
            )


    if "MISSING" in statuses:
        overall_status = "INCOMPLETE"

    elif "MISMATCH" in statuses:
        overall_status = "MISMATCH"

    elif "POSSIBLE_OCR_AMBIGUITY" in statuses:
        overall_status = "REVIEW"

    elif statuses and all(
        status == "MATCH"
        for status in statuses
    ):
        overall_status = "VALID"

    else:
        overall_status = "REVIEW"


    return {
        "status": overall_status,
        "field_statuses": comparison
    }