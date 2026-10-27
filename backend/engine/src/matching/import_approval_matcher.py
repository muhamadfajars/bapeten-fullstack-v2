"""Cocokkan SETIAP baris Persetujuan Impor dengan satu unit Formulir.

Hanya kandidat dengan identitas unit kuat dipilih otomatis. Field impor kosong
TIDAK ditampilkan dan tidak dihitung sebagai mismatch, tetapi dicatat dalam
coverage. Status REVIEW digunakan untuk OCR/tipe ambigu dan konflik jenis
nomor seri tabung (housing vs insert).
"""
import re
import unicodedata
from rapidfuzz import fuzz

FIELDS = (
    'merk_unit', 'tipe_unit', 'nomor_seri_unit',
    'merk_tabung', 'tipe_tabung', 'nomor_seri_tabung',
)
SERIAL_FIELDS = {'nomor_seri_unit', 'nomor_seri_tabung'}
WEIGHTS = {'merk_unit': 1, 'tipe_unit': 3, 'nomor_seri_unit': 7,
           'merk_tabung': 1, 'tipe_tabung': 2, 'nomor_seri_tabung': 3}
ALIASES = {
    'ge': 'ge', 'ge mobile': 'ge', 'ge healthcare': 'ge',
    'ge medical systems': 'ge', 'siemens': 'siemens',
    'siemens healthineers': 'siemens', 'siemens healthcare': 'siemens',
    'philips': 'philips', 'philips medical systems': 'philips',
    'canon': 'canon', 'canon medical': 'canon',
    'toshiba': 'toshiba', 'toshiba medical systems': 'toshiba',
    'fujifilm': 'fujifilm', 'fuji film': 'fujifilm',
}


def normalize(value):
    text = unicodedata.normalize('NFKC', str(value or '')).casefold()
    return re.sub(r'\s+', ' ', re.sub(r'[^a-z0-9]+', ' ', text)).strip()


def compact(value):
    return normalize(value).replace(' ', '')


def compare_field(field, expected, actual):
    if not actual or not str(actual).strip():
        return {'status': 'MISSING', 'score': 0., 'expected': expected,
                'actual': actual, 'reason': 'Tidak tercantum pada Persetujuan Impor.'}
    if not expected or not str(expected).strip():
        return {'status': 'MISSING', 'score': 0., 'expected': expected,
                'actual': actual, 'reason': 'Tidak tercantum pada Formulir.'}
    a, b = compact(expected), compact(actual)
    if field.startswith('merk_'):
        a = compact(ALIASES.get(normalize(expected), expected))
        b = compact(ALIASES.get(normalize(actual), actual))
    if a == b:
        return {'status': 'MATCH', 'score': 100., 'expected': expected,
                'actual': actual, 'reason': 'Sesuai setelah normalisasi.'}
    score = round(float(fuzz.ratio(a, b)), 2)
    if field in {'tipe_unit','tipe_tabung'}:
        # Exact model designation. An extra trailing X is a different model.
        # Only a proven OCR O/0 or I/1 confusion is eligible for REVIEW.
        trans=str.maketrans({'o':'0','i':'1','l':'1'})
        ambiguity=len(a)==len(b) and a.translate(trans)==b.translate(trans)
        status='REVIEW' if ambiguity else 'MISMATCH'
        reason='Potensi salah baca karakter OCR; periksa model.' if ambiguity else 'Kode model berbeda.'
    elif field == 'nomor_seri_tabung':
        status = 'REVIEW'
        reason = 'Serial pada persetujuan impor adalah Tube S/N (housing/assembly); bukan bukti serial insersi.'
    elif field in SERIAL_FIELDS:
        trans = str.maketrans({'o': '0', 'i': '1', 'l': '1', 's': '5', 'z': '2', 'b': '8'})
        maybe_ocr = len(a) == len(b) and a.translate(trans) == b.translate(trans)
        status = 'REVIEW' if maybe_ocr else 'MISMATCH'
        reason = 'Kemungkinan ambiguitas OCR.' if maybe_ocr else 'Nomor seri berbeda.'
    elif field == 'tipe_tabung' and 'athlon' in normalize(expected).split() and 'athlon' in normalize(actual).split():
        status, reason = 'REVIEW', 'Keluarga ATHLON sama, tetapi tipe/komponen tidak terbukti ekuivalen.'
    else:
        status = 'REVIEW' if score >= 80 else 'MISMATCH'
        reason = 'Penulisan mirip; perlu verifikasi.' if status == 'REVIEW' else 'Identitas berbeda.'
    return {'status': status, 'score': score, 'expected': expected,
            'actual': actual, 'reason': reason}


def compare_row(form_equipment, import_row):
    fields = {f: compare_field(f, form_equipment.get(f), import_row.get(f)) for f in FIELDS}
    visible = {f: v for f, v in fields.items() if import_row.get(f) is not None and str(import_row.get(f)).strip()}
    serial = fields['nomor_seri_unit']['status']
    brand = fields['merk_unit']['status']
    model = fields['tipe_unit']['status']
    strong_identity = serial == 'MATCH' and brand == 'MATCH' and model in ('MATCH', 'REVIEW')
    if serial == 'MISMATCH' or brand == 'MISMATCH':
        status = 'MISMATCH'
    elif not strong_identity:
        status = 'REVIEW' if any(v['status'] in ('MATCH', 'REVIEW') for v in visible.values()) else 'MISSING'
    else:
        present_statuses = {x['status'] for x in visible.values()}
        if 'MISMATCH' in present_statuses or 'REVIEW' in present_statuses or import_row.get('method') == 'OCR_LAYOUT':
            status = 'REVIEW'
        else:
            status = 'MATCH'
    # Perbedaan insert vs housing adalah REVIEW konteks, bukan penyamaan nilai.
    conflict = fields['nomor_seri_tabung']['status'] == 'MISMATCH'
    if strong_identity and conflict:
        status = 'REVIEW'
        fields['nomor_seri_tabung']['reason'] = (
            'Nomor seri berbeda. Kemungkinan housing/assembly vs insert; '
            'periksa foto label dan jenis komponen secara manual.'
        )
    used = [(f, v) for f, v in visible.items() if v['status'] != 'MISSING']
    score = (sum(WEIGHTS[f] * (1 if v['status'] == 'MATCH' else v['score'] / 200)
                 for f, v in used) / sum(WEIGHTS[f] for f, _ in used) * 100) if used else 0
    return {'status': status, 'score': round(score, 2), 'fields': fields,
            'visible_fields': visible, 'strong_identity': strong_identity,
            'coverage': {'present_in_import': len(visible), 'total_fields': len(FIELDS)},
            'source_page': import_row.get('page'), 'source_row': import_row.get('row_number'),
            'source_method': import_row.get('method'), 'parse_notes': import_row.get('parse_notes', [])}


def match_import_approval(application, approval):
    forms = application.get('equipment', []) or []
    rows = approval.get('equipment', []) or []
    results, unmatched = [], []
    for row_index, row in enumerate(rows):
        candidates = []
        for form_index, form in enumerate(forms):
            comparison = compare_row(form, row)
            # Jangan menjadikan merk+tipe umum sebagai satu-satunya dasar pilihan.
            if comparison['strong_identity']:
                candidates.append((form_index, comparison))
        if len(candidates) == 1:
            form_index, comparison = candidates[0]
            results.append({
                'import_row_index': row_index,
                'form_equipment_index': form_index,
                'expected': {f: forms[form_index].get(f) for f in FIELDS},
                'actual': {f: row.get(f) for f in FIELDS},
                'status': comparison['status'],
                'selected_import_row_index': row_index,
                'best_candidate': comparison,
                'visible_fields': comparison['visible_fields'],
                'source_page': row.get('page'), 'source_row': row.get('row_number'),
                'reason': 'Baris dipasangkan berdasarkan nomor seri unit dan identitas unit.',
            })
        else:
            unmatched.append({
                'import_row_index': row_index,
                'source_page': row.get('page'), 'source_row': row.get('row_number'),
                'status': 'REVIEW',
                'reason': ('Beberapa kandidat dengan identitas unit kuat.' if candidates
                           else 'Tidak ada pasangan unit beridentitas kuat; tidak dipilih otomatis.'),
                'candidate_form_indices': [i for i, _ in candidates],
            })
    return {
        'source_name': approval.get('source_name'),
        'results': results,  # Hanya pasangan yang aman untuk ditampilkan
        'unmatched_import_rows': unmatched,  # Tetap tersimpan untuk audit
        'total_matched_rows': len(results),
        'total_form_equipment': len(forms),
        'total_import_rows': len(rows),
    }
