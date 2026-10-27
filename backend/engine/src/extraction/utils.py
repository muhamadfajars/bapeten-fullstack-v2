import re


def clean_text(text):
    if text is None:
        return None

    text = text.replace("\n", " ")

    text = re.sub(r"\s+", " ", text)

    return text.strip()