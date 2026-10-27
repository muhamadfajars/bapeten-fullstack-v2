import json

from src.matching.label_matcher import (
    compare_label_data,
)


form_data = {
    "manufacturer": "CANON",
    "type": "E7894",
    "serial_number": "0F1376"
}


photo_data = {
    "manufacturer": "CANON",
    "type": "E7894",
    "serial_number": "OF1376"
}


result = compare_label_data(
    form_data,
    photo_data
)


print(
    json.dumps(
        result,
        indent=4,
        ensure_ascii=False
    )
)