"""Narrow, conservative Indonesian address orthography normalization.

This augments v065; it does not substitute a document's value with a guess.
No geographic database, OCR, or outside service is used.
"""
from __future__ import annotations
import re
import unicodedata

# House number explicitly tied to a No./Nomor label, not RT/RW, phone or ZIP.
_HOUSE = re.compile(
    r'(?i)(?<![\w])(?:no|nomor)\b\s*[.:/\-]?\s*'
    r'(\d+[a-z]?(?:(?:\s*[/\-]\s*\d+[a-z]?)|(?:\s*[/\-]\s*[a-z]))?)(?!\w)'
)
_STREET = re.compile(r'(?i)\b(?:jln?|jalan|ji|j1)(?:[.:-]\s*|\s+)(?=[a-z0-9])')
_DOTTED = re.compile(r'(?<!\w)(?:[a-zA-Z]\.){2,}')
_RT_RW = re.compile(r'(?i)\brt\b[\s.:/-]*(\d+)(?:\s*/\s*(?:rw[\s.:/-]*)?(\d+))?')
_RW = re.compile(r'(?i)\brw\b[\s.:/-]*(\d+)')


def house_number(value):
    m = _HOUSE.search(str(value or ''))
    if not m:
        return None
    pieces = re.split(r'\s*([/-])\s*', m.group(1).casefold())
    normalized = []
    for index,item in enumerate(pieces):
        if item in ('/', '-'):
            # 'No. 2-A' == 'No. 2A'. But 'No. 2/4' != 'No. 24'.
            if index + 1 < len(pieces) and re.fullmatch('[a-z]', pieces[index + 1]):
                continue
            normalized.append(item)
            continue
        if re.fullmatch('[a-z]', item) and index and pieces[index - 1] in ('/', '-'):
            normalized.append(item)
            continue
        num = re.fullmatch(r'(\d+)([a-z]?)', item)
        if num is None:
            return None
        normalized.append(str(int(num.group(1))) + num.group(2))
    return ''.join(normalized)


def _acronym(m):
    return m.group(0).replace('.', '')


def street_words(value):
    """Street-name tokens, ignoring typographic punctuation, not identities."""
    value = unicodedata.normalize('NFKC', str(value or '')).casefold()
    value = _DOTTED.sub(_acronym, value)
    m = _STREET.search(value)
    if not m:
        return None
    tail = value[m.end():]
    tail = re.split(
        r'(?i)(?<!\w)(?:no|nomor)\b[\s.:/-]*\d|\b(?:rt|rw|kelurahan|kel|kecamatan|kec|kota|kabupaten|kab|provinsi|kode\s+pos)\b|[,;]',
        tail, maxsplit=1
    )[0]
    return {w for w in re.findall(r'[a-z0-9]+', tail)
            if w not in {'dr', 'tni', 'ad', 'mayor', 'jalan'}}


def canonical_text(value):
    """Canonicalize punctuation and explicitly labeled numerical components.

    Crucially, do *not* strip all digits or concatenate all numbers: No 2/4 is
    NOT equivalent to No 24; house suffix 2A is NOT equivalent to 2.
    """
    s = unicodedata.normalize('NFKC', str(value or '')).casefold()
    s = _DOTTED.sub(_acronym, s)
    s = _STREET.sub(' jalan ', s)

    def house_repl(m):
        return ' nomor ' + (house_number(m.group(0)) or m.group(1)) + ' '

    s = _HOUSE.sub(house_repl, s)
    s = _RT_RW.sub(lambda m: ' rt ' + str(int(m.group(1))) + (' rw ' + str(int(m.group(2))) if m.group(2) else ''), s)
    s = _RW.sub(lambda m: ' rw ' + str(int(m.group(1))), s)
    # Slash and hyphen WITHIN a house value are preserved through an alphanumeric
    # sentinel: the pattern was replaced with 'nomor 2/4' above. Keep tokens.
    return ' '.join(re.findall(r'[a-z0-9]+|[/\-]', s))


def shared_locality(left, right):
    """At least one corroborating, non-generic regional token in both texts."""
    generic = {
        'jalan','jl','nomor','no','kota','kabupaten','provinsi','kecamatan',
        'kelurahan','desa','rt','rw','kode','pos','barat','timur','utara',
        'selatan','tengah','raya','indonesia','pusat'
    }
    a = {w for w in re.findall(r'[a-z]+', canonical_text(left)) if len(w) >= 4 and w not in generic}
    b = {w for w in re.findall(r'[a-z]+', canonical_text(right)) if len(w) >= 4 and w not in generic}
    # Do not count street name alone as locality confirmation. Caller only uses
    # this as corroboration for an identical street AND identical house number.
    road = (street_words(left) or set()) | (street_words(right) or set())
    return bool((a & b) - road)


def rt_rw_conflict(left, right):
    """Different explicit RT/RW are not typographic variations."""
    def parts(value):
        value = unicodedata.normalize('NFKC', str(value or '')).casefold()
        result = {}
        m = _RT_RW.search(value)
        if m:
            result['rt'] = int(m.group(1))
            if m.group(2):
                result['rw'] = int(m.group(2))
        m = _RW.search(value)
        if m:
            result['rw'] = int(m.group(1))
        return result
    a,b=parts(left),parts(right)
    return any(a[k] != b[k] for k in a.keys() & b.keys())
