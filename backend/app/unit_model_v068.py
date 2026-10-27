"""Conservative model-number matching for `Tipe Unit` ONLY.

Product brand must never be inferred from a product family/model descriptor.
Other equipment fields continue using the existing v065 logic.
"""
from __future__ import annotations
import re
import unicodedata

_MODEL_FIELD = re.compile(r'(?i)^\s*(?:alat\s+\d+\s*:\s*)?(?:tipe|type|model)\s+(?:unit|pesawat)\s*$')
_TRAILING_DESCRIPTOR = re.compile(r'^\s*(.*?)\s*[\(\[]\s*([^()\[\]]+)\s*[\)\]]\s*$')


def is_unit_model_field(field):
    return bool(_MODEL_FIELD.fullmatch(str(field or '')))


def _base(value):
    s = unicodedata.normalize('NFKC', str(value or '')).casefold().strip()
    if not s or s in {'-', '—', 'tidak ditemukan', 'none'}:
        return None
    m = _TRAILING_DESCRIPTOR.match(s)
    if m:
        descriptor = m.group(2).strip()
        # Only ignore clearly textual descriptors such as '(FDR Nano)'.
        # Never strip serials, numeric variants, or hardware revisions.
        if re.search(r'[a-zA-Z]', descriptor) and not re.search(r'\d', descriptor):
            s = m.group(1).strip()
    # Slashes between digits can denote competing/compound model numbers and
    # are therefore intentionally NOT normalized to a concatenated string.
    if re.search(r'\d\s*[/\-]\s*\d', s):
        return None
    compact = ''.join(re.findall(r'[a-z0-9]+', s))
    # A strong model identifier must contain letters AND digits; never treat
    # 'FDR Nano' alone as equivalent to a real model number.
    if not (re.search(r'[a-z]', compact) and re.search(r'\d', compact)):
        return None
    return compact


def decide(field, expected, observed, status, score):
    if not is_unit_model_field(field):
        return status, score, ''
    a, b = _base(expected), _base(observed)
    if a and a == b:
        return 'MATCH', 100.0, 'Model unit identik setelah normalisasi tanda baca dan keterangan deskriptif'
    return status, score, ''
