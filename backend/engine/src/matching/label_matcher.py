import re


OCR_CONFUSIONS = {
    ("0", "O"),
    ("1", "I"),
    ("1", "L"),
    ("5", "S"),
    ("2", "Z"),
    ("6", "8"),
    ("8", "B"),
}


def normalize_text(value):
    if value is None:
        return None

    value = str(value).strip().upper()

    value = re.sub(
        r"\s+",
        "",
        value
    )

    return value


def is_ocr_confusion(char_a, char_b):
    """
    Cek apakah dua karakter merupakan pasangan
    yang sering tertukar oleh OCR.
    """

    char_a = char_a.upper()
    char_b = char_b.upper()

    return (
        (char_a, char_b) in OCR_CONFUSIONS
        or
        (char_b, char_a) in OCR_CONFUSIONS
    )


def compare_with_ocr_tolerance(
    expected,
    actual
):
    """
    Compare dua string.

    Return:
    MATCH
    POSSIBLE_OCR_AMBIGUITY
    MISMATCH
    """

    expected = normalize_text(
        expected
    )

    actual = normalize_text(
        actual
    )


    if expected is None or actual is None:

        return {
            "status": "MISSING",
            "differences": []
        }


    # Exact match
    if expected == actual:

        return {
            "status": "MATCH",
            "differences": []
        }


    # Panjang berbeda -> bukan simple OCR confusion
    if len(expected) != len(actual):

        return {
            "status": "MISMATCH",
            "differences": []
        }


    differences = []


    for index, (
        expected_char,
        actual_char
    ) in enumerate(
        zip(expected, actual)
    ):

        if expected_char == actual_char:
            continue


        differences.append({
            "index": index,
            "expected": expected_char,
            "actual": actual_char,
            "ocr_confusion":
                is_ocr_confusion(
                    expected_char,
                    actual_char
                )
        })


    if (
        differences
        and
        all(
            item["ocr_confusion"]
            for item in differences
        )
    ):

        return {
            "status":
                "POSSIBLE_OCR_AMBIGUITY",

            "differences":
                differences
        }


    return {
        "status": "MISMATCH",
        "differences": differences
    }


def compare_manufacturer(
    form_value,
    photo_value
):
    """
    Manufacturer sudah dinormalisasi
    oleh label parser.
    """

    form_value = normalize_text(
        form_value
    )

    photo_value = normalize_text(
        photo_value
    )


    if (
        form_value is None
        or
        photo_value is None
    ):

        return {
            "status": "MISSING"
        }


    if form_value == photo_value:

        return {
            "status": "MATCH"
        }


    return {
        "status": "MISMATCH"
    }


def compare_label_data(
    form_data,
    photo_data
):
    """
    form_data:

    {
        "manufacturer": "CANON",
        "type": "E7894",
        "serial_number": "0F1376"
    }

    photo_data:

    {
        "manufacturer": "CANON",
        "type": "E7894",
        "serial_number": "OF1376"
    }
    """

    manufacturer_result = (
        compare_manufacturer(
            form_data.get(
                "manufacturer"
            ),
            photo_data.get(
                "manufacturer"
            )
        )
    )


    type_result = (
        compare_with_ocr_tolerance(
            form_data.get(
                "type"
            ),
            photo_data.get(
                "type"
            )
        )
    )


    serial_result = (
        compare_with_ocr_tolerance(
            form_data.get(
                "serial_number"
            ),
            photo_data.get(
                "serial_number"
            )
        )
    )


    return {
        "manufacturer":
            manufacturer_result,

        "type":
            type_result,

        "serial_number":
            serial_result
    }