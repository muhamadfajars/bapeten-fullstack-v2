"""Conservative display cleanup for extracted facility addresses.

Trim following document headings, never add absent location components and never
turn an absent address into a MATCH. Matcher status is intentionally unchanged.
"""
import re

_STOP = re.compile(r"(?ix)\s*(?:\bII\s*[.]\s*detail\s+pengajuan\b|"
                   r"\bsurat\s+izin\s+(?:kerja|praktik)\b|"
                   r"\b(?:masa\s+berlaku|nomor\s+izin|tanggal\s+(?:terbit|ditetapkan))\s*:|"
                   r"\b(?:nama\s+petugas|nomor\s+transaksi|ID\s+transaksi)\s*:|"
                   r"\b(?:pengesahan|diterbitkan\s+oleh)\s*:)")

def clean_address_evidence(value):
    if value is None:return value
    original=str(value)
    if original.strip() in ('','—','-'):return original
    cleaned=_STOP.split(original,maxsplit=1)[0]
    cleaned=re.sub(r'\s+', ' ',cleaned).strip(' ,;:-')
    # Don't silently replace data or guess missing RT/RW, zip etc.
    return cleaned or original
