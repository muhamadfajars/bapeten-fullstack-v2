import json

from src.extraction.label_pipeline import (
    extract_label_auto,
)


IMAGE_PATH = (
    "data/sample/labeltabung2.jpg"
)

LABEL_TYPE = "tube"


CROP_CONFIG = {
    "top": 0.45,
    "bottom": 1.0,
    "left": 0.0,
    "right": 1.0
}


result = extract_label_auto(
    image_path=IMAGE_PATH,
    label_type=LABEL_TYPE,
    crop_config=CROP_CONFIG,
)


print("\n")
print("=" * 80)
print("AUTO LABEL PIPELINE")
print("=" * 80)


print(
    f"Selected Method : "
    f"{result['method']}"
)

print(
    f"Score           : "
    f"{result['score']:.3f}"
)


print("\n")
print("=" * 80)
print("FINAL RESULT")
print("=" * 80)


print(
    json.dumps(
        result["result"],
        indent=4,
        ensure_ascii=False
    )
)


print("\n")
print("=" * 80)
print("METHODS TESTED")
print("=" * 80)


for candidate in result[
    "candidates"
]:

    print(
        f"{candidate['method']:35}"
        f" score={candidate['score']:.3f}"
        f" complete={candidate['complete']}"
        f" min_conf="
        f"{candidate['minimum_confidence']:.3f}"
    )