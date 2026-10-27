"""Section-scoped equipment matching and cross-section consistency checks.

Does not treat every other occurrence of a field as a conflict.  A warning
requires a sufficiently specific shared identifier, not merely a shared brand.
"""
import re
import unicodedata

FIELD_LABELS = {
    'merk_unit': r'(?:(?:merk|merek|pabrikan)\s*(?:unit|pesawat(?:\s*sinar[- ]?x)?|generator)|pabrikan\s*/\s*merk)',
    'tipe_unit': r'(?:tipe|type|model)(?:\s*/\s*(?:tipe|type|model))?\s*(?:unit|pesawat(?:\s*sinar[- ]?x)?)?',
    'nomor_seri_unit': r'(?:nomor|no\.?|serial)\s*(?:seri|number)(?:\s*(?:unit|pesawat(?:\s*sinar[- ]?x)?))?',
    'merk_tabung': r'(?:merk|merek)\s*tabung',
    'tipe_tabung': r'(?:model\s*/\s*tipe|tipe|type|model)\s*tabung',
    'nomor_seri_tabung': r'(?:nomor|no\.?)\s*seri\s*tabung',
}

def norm(s):
    s = unicodedata.normalize('NFKC', str(s or '')).casefold()
    return re.sub('[^a-z0-9]', '', s)

def classify_page(text):
    """Classify using heading-like lines, never a prose keyword mention."""
    lines = [re.sub(r'\s+', ' ', x).strip() for x in str(text or '').splitlines() if x.strip()]
    head = lines[:15]
    for i, line in enumerate(head):
        folded = line.casefold()
        if re.match(r'^sertifikat(?:\s+uji\s+kesesuaian(?:\s+pesawat\s+sinar[- ]?x)?)?\s*$', folded):
            next_line = ' '.join(head[i+1:i+3]).casefold()
            if 'uji kesesuaian' in folded or re.search(r'^uji\s+kesesuaian',next_line):
                return 'suitability_certificate'
        if re.match(r'^laporan\s+evaluasi\s+hasil\s+uji\b', folded):
            return 'suitability_report'
        if re.match(r'^(?:[A-Z0-9. ]{0,8}\s*)?(?:deskripsi\s+pesawat\s+sinar[- ]?x|data\s+pesawat\s+sinar[- ]?x|data\s+unit\s+pesawat)\b', line, re.I):
            return 'equipment_description'
        if re.match(r'^(?:laporan\s+)?uji\s+fungsi\b|^acceptance\s+test\b|^uji\s+paparan\s+radiasi\b|^uji\s+kebocoran\s+tabung\b', folded):
            return 'test_report'
        if re.match(r'^(?:persetujuan\s+impor|izin\s+impor|spesifikasi\s+(?:alat|teknis))\b', folded):
            return 'supporting_document'
    return 'general'

def select_primary_pages(pages, category):
    classified = [(p, classify_page(p.get('text', ''))) for p in pages]
    excluded = {'suitability_certificate', 'suitability_report', 'test_report', 'supporting_document'}
    if category == 'program_protection_upload':
        descriptions = [p for p, section in classified if section == 'equipment_description']
        if descriptions:
            # Prefer the explicit declaration of the device in the current
            # program, while allowing multiple device description pages.
            return descriptions
    return [p for p, section in classified if section not in excluded]

def scan_labeled_fields(text):
    """Capture field-value pairs for evidence, never guess an absent value."""
    pairs = {}
    for raw in str(text or '').splitlines():
        line = re.sub(r'\s+', ' ', raw).strip()
        if not line or ':' not in line:
            continue
        label, value = line.split(':', 1)
        label = label.strip().casefold()
        value = value.strip()
        if not value or len(value) > 100:
            continue
        for key, pat in FIELD_LABELS.items():
            if re.fullmatch(pat, label, re.I):
                # Bare "Nomor Seri" and "Model/Tipe" are meaningful only
                # for unit if not marked as tube; never guess tube identity.
                if key in ('tipe_tabung', 'nomor_seri_tabung') and 'tabung' not in label:
                    continue
                if key == 'merk_unit' and not re.search(r'unit|pesawat|generator', label):
                    continue
                if key == 'tipe_unit' and not re.search(r'unit|pesawat', label):
                    continue
                pairs.setdefault(key, []).append(value)
    return pairs

def equipment_identity(text):
    fields = scan_labeled_fields(text)
    # Primary linking keys must be specific enough to separate multiple X-ray
    # systems sharing the same model or manufacturer.
    return {key: values[0] for key, values in fields.items() if values}

def identity_linked(primary, candidate):
    """Link same equipment using exact serial; model alone is insufficient."""
    for key in ('nomor_seri_unit', 'nomor_seri_tabung'):
        a, b = norm(primary.get(key)), norm(candidate.get(key))
        if a and b:
            if a == b:
                return True, key
            # Contradictory serial for a shared device class is not linked.
    return False, None

def consistency_warnings(pages, primary_pages):
    """Generate general warnings for linked equipment with conflicting fields.

    Warnings do not alter the category MATCH/REVIEW/MISMATCH result.  They
    expose separate sources and source types for evaluator review.
    """
    base = []
    for p in primary_pages:
        ident = equipment_identity(p.get('text', ''))
        if ident:
            base.append((p, ident))
    warnings, seen = [], set()
    for p in pages:
        section = classify_page(p.get('text', ''))
        if section not in ('suitability_certificate','suitability_report','test_report','supporting_document'):
            continue
        other = equipment_identity(p.get('text', ''))
        if not other:
            continue
        for source, ident in base:
            linked, by = identity_linked(ident, other)
            if not linked:
                continue
            for field in ('merk_unit','tipe_unit','merk_tabung','tipe_tabung'):
                left, right = ident.get(field), other.get(field)
                if not left or not right or norm(left) == norm(right):
                    continue
                token=(source.get('page'),p.get('page'),field,norm(left),norm(right))
                if token in seen:
                    continue
                seen.add(token)
                warnings.append({
                    'field':field, 'primary_value':left,'other_value':right,
                    'primary_page':source.get('page'),'other_page':p.get('page'),
                    'other_section':section, 'linked_by':by,
                    'reason':'Nilai berbeda pada dua sumber dengan identitas alat yang terhubung',
                })
    return warnings
