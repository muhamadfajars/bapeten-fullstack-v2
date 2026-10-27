import os
import re
import unicodedata
from pathlib import Path

import cv2
import fitz
import numpy as np
import pdfplumber

from src.extraction.label_ocr import extract_ocr

IMAGE_SUFFIXES = {'.jpg', '.jpeg', '.png', '.webp', '.bmp'}


def clean(value):
    if value is None:
        return ''
    value = unicodedata.normalize('NFKC', str(value))
    return re.sub(r'\s+', ' ', value).strip()


def norm(value):
    return re.sub(r'[^a-z0-9]+', ' ', clean(value).casefold()).strip()


def is_header(row):
    values = [norm(x) for x in row]
    joined = ' '.join(values)
    separate = ('merk unit' in joined and ('tipe no seri unit' in joined or 'tipe seri unit' in joined))
    combined = ('nama sumber' in joined and ('tipe no seri' in joined or 'tipe seri' in joined))
    return separate or combined


def indexes(header):
    values = [norm(x) for x in header]

    def find(*terms):
        for i, value in enumerate(values):
            if all(term in value for term in terms):
                return i
        return None

    combined = find('nama', 'sumber') is not None
    return {
        'schema': 'COMBINED' if combined else 'SEPARATE',
        'no': next((i for i, v in enumerate(values) if v in ('no', 'no.', 'nomor')), None),
        'kode': find('kode', 'sumber'),
        'merk_unit': find('nama', 'sumber') if combined else find('merk', 'unit'),
        'unit': next((i for i, v in enumerate(values)
                      if ('tipe' in v or 'seri' in v) and (combined or 'unit' in v)), None),
        'merk_tabung': None if combined else find('merk', 'tabung'),
        'tabung': None if combined else next((i for i, v in enumerate(values)
                                            if ('tipe' in v or 'seri' in v) and 'tabung' in v), None),
    }


def get_cell(row, ix):
    return clean(row[ix]) if ix is not None and ix < len(row) else ''


def split_unit(value):
    raw = clean(value)
    if not raw:
        return None, None, None
    match = re.search(
        r'\b(?:System\s*S\s*/?\s*N|Unit\s*S\s*/?\s*N|S\s*/?\s*N|Serial\s*(?:No\.?|Number))\s*[:.]?\s*([A-Z0-9-]+)',
        raw, re.I
    )
    if match:
        serial = match.group(1)
        model = re.sub(r'\s*/?\s*System\s*/?\s*$', '', raw[:match.start()], flags=re.I)
        model = re.sub(r'\s*/\s*$', '', model).strip()
        return model or None, serial, 'EXPLICIT_SN'
    parts = [clean(p) for p in re.split(r'\s*/\s*', raw) if clean(p)]
    if len(parts) == 2:
        return parts[0], parts[1], 'SLASH'
    return raw, None, 'AMBIGUOUS'


def split_tube(value):
    raw = clean(value)
    if not raw:
        return None, None, None
    match = re.search(r'\b(?:Tube\s*S\s*/?\s*N|S\s*/?\s*N|Serial\s*(?:No\.?|Number))\s*[:.]?\s*([A-Z0-9-]+)', raw, re.I)
    if match:
        return clean(raw[:match.start()]) or None, match.group(1), 'EXPLICIT_SN'
    parts = [clean(p) for p in re.split(r'\s*/\s*', raw) if clean(p)]
    if len(parts) == 2:
        return parts[0], parts[1], 'SLASH'
    return raw, None, 'AMBIGUOUS'


def extract_inline_tube(unit_cell):
    text = clean(unit_cell)
    match = re.search(r'\bTube\s*S\s*/?\s*N\s*[:.]?\s*([A-Z0-9-]+)', text, re.I)
    if not match:
        return text, None
    return clean(text[:match.start()]), match.group(1)


def parse_row(row, mapping, page, row_number, method):
    row = [clean(item) for item in row]
    brand = get_cell(row, mapping['merk_unit'])
    unit_raw = get_cell(row, mapping['unit'])
    if not brand or not unit_raw:
        return None
    unit_without_tube, inline_tube_serial = extract_inline_tube(unit_raw)
    model, serial, unit_rule = split_unit(unit_without_tube)
    tube_raw = get_cell(row, mapping['tabung'])
    tube_model, tube_serial, tube_rule = split_tube(tube_raw)
    if not tube_serial:
        tube_serial = inline_tube_serial
    result = {
        'page': page,
        'row_number': row_number,
        'method': method,
        'kode_sumber': get_cell(row, mapping['kode']) or None,
        'merk_unit': brand,
        'tipe_unit': model,
        'nomor_seri_unit': serial,
        'merk_tabung': get_cell(row, mapping['merk_tabung']) or None,
        'tipe_tabung': tube_model,
        'nomor_seri_tabung': tube_serial,
        'raw_unit': unit_raw,
        'raw_tabung': tube_raw or None,
        'parse_notes': [],
        'needs_review': False,
    }
    if mapping.get('schema') == 'COMBINED':
        result['parse_notes'].append('Skema Nama Sumber: merk tabung/tipe tabung tidak tersedia; jangan diasumsikan sama dengan merk unit')
    if unit_rule == 'AMBIGUOUS':
        result['parse_notes'].append('Tipe/nomor seri unit belum dapat dipisahkan secara pasti')
    if tube_raw and tube_rule == 'AMBIGUOUS':
        result['parse_notes'].append('Tipe/nomor seri tabung belum dapat dipisahkan secara pasti')
    if inline_tube_serial and not result['merk_tabung']:
        result['parse_notes'].append('Nomor seri tabung ditemukan, tetapi merk tabung dan tipe tabung tidak tercantum dalam baris')
    result['needs_review'] = bool(result['parse_notes']) or method == 'OCR_LAYOUT'
    return result


def process_table(table, page, method):
    results = []
    header_index = None
    for index, row in enumerate(table):
        if is_header(row):
            header_index = index
            break
    if header_index is None:
        return results
    mapping = indexes(table[header_index])
    if mapping['merk_unit'] is None or mapping['unit'] is None:
        return results
    row_count = 0
    for row in table[header_index + 1:]:
        if not row or is_header(row):
            continue
        if not any(clean(x) for x in row):
            continue
        if not get_cell(row, mapping['merk_unit']) and not get_cell(row, mapping['unit']):
            # Wrapped line continuing the preceding row.
            if results:
                for k, field in [('unit','raw_unit'), ('tabung','raw_tabung')]:
                    extra = get_cell(row, mapping[k])
                    if extra:
                        results[-1][field] = clean((results[-1].get(field) or '') + ' ' + extra)
                results[-1] = rebuild_from_raw(results[-1])
            continue
        row_count += 1
        parsed = parse_row(row, mapping, page, row_count, method)
        if parsed:
            results.append(parsed)
    return results


def rebuild_from_raw(result):
    base, tube_sn = extract_inline_tube(result.get('raw_unit'))
    model, serial, rule = split_unit(base)
    tube_model, tube_serial, tube_rule = split_tube(result.get('raw_tabung'))
    result.update(tipe_unit=model, nomor_seri_unit=serial,
                  tipe_tabung=tube_model, nomor_seri_tabung=tube_serial or tube_sn)
    if rule == 'AMBIGUOUS' or (result.get('raw_tabung') and tube_rule == 'AMBIGUOUS'):
        result['needs_review'] = True
    return result


def image_from_page(page, dpi=180):
    pix = page.get_pixmap(dpi=dpi, colorspace=fitz.csRGB, alpha=False)
    array = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, 3)
    return cv2.cvtColor(array, cv2.COLOR_RGB2BGR)


def ocr_table(image, page):
    # Conservative reconstruction: identify column headers; group lines by y and x.
    # All OCR-layout rows are REVIEW until checked against the document visually.
    words = []
    for item in extract_ocr(image):
        box = item.get('box')
        text = clean(item.get('text'))
        if not text or box is None:
            continue
        array = np.asarray(box, dtype=float)
        if array.ndim == 1 and len(array) == 4:
            x1, y1, x2, y2 = array
        elif array.ndim == 2 and array.shape[1] >= 2:
            x1, y1 = np.min(array[:, :2], axis=0)
            x2, y2 = np.max(array[:, :2], axis=0)
        else:
            continue
        words.append({'text': text, 'x': (x1+x2)/2, 'y': (y1+y2)/2,
                      'h': max(8, y2-y1), 'x1': x1})
    if not words:
        return []
    words.sort(key=lambda a: (a['y'], a['x']))
    header_words = [w for w in words if 'merk unit' in norm(w['text']) or 'tipe no seri unit' in norm(w['text'])]
    if len(header_words) < 2:
        return []
    header_y = min(w['y'] for w in header_words)
    header_band = [w for w in words if abs(w['y'] - header_y) < max(35, image.shape[0] * .035)]
    labels = []
    for w in header_band:
        n = norm(w['text'])
        if 'merk' in n and 'unit' in n: key = 'merk_unit'
        elif ('tipe' in n or 'seri' in n) and 'unit' in n: key = 'unit'
        elif 'merk' in n and 'tabung' in n: key = 'merk_tabung'
        elif ('tipe' in n or 'seri' in n) and 'tabung' in n: key = 'tabung'
        elif 'kode' in n: key = 'kode'
        else: continue
        labels.append((w['x'], key))
    labels.sort()
    keys = [v for _, v in labels]
    if 'merk_unit' not in keys or 'unit' not in keys:
        return []
    body = [w for w in words if w['y'] > header_y + max(28, image.shape[0] * .022)]
    groups = []
    for word in body:
        if groups and abs(word['y'] - groups[-1][-1]['y']) <= max(13, word['h'] * .75):
            groups[-1].append(word)
        else:
            groups.append([word])
    rows = []
    for group in groups:
        cells = {key: [] for key in keys}
        for word in group:
            nearest = min(labels, key=lambda p: abs(p[0]-word['x']))[1]
            cells[nearest].append(word['text'])
        if cells.get('merk_unit') and cells.get('unit'):
            row = [' '.join(cells[key]) for key in keys]
            mapping = {key: i for i, key in enumerate(keys)}
            mapping.setdefault('no', None)
            mapping.setdefault('kode', None)
            mapping.setdefault('merk_tabung', None)
            mapping.setdefault('tabung', None)
            parsed = parse_row(row, mapping, page, len(rows)+1, 'OCR_LAYOUT')
            if parsed:
                parsed['needs_review'] = True
                parsed['parse_notes'].append('Baris hasil rekonstruksi koordinat OCR; perlu konfirmasi visual')
                rows.append(parsed)
    return rows


def parse_import_approval(path):
    path = str(path)
    suffix = Path(path).suffix.lower()
    if suffix != '.pdf' and suffix not in IMAGE_SUFFIXES:
        raise ValueError('Gunakan PDF, JPG, JPEG, PNG, WEBP, atau BMP')
    equipment = []
    page_info = []
    if suffix == '.pdf':
        with pdfplumber.open(path) as doc, fitz.open(path) as rendered:
            for i, page in enumerate(doc.pages):
                page_number = i+1
                found = []
                for table in page.extract_tables() or []:
                    found.extend(process_table(table, page_number, 'PDF_TABLE'))
                if not found:
                    image = image_from_page(rendered[i])
                    found = ocr_table(image, page_number)
                equipment.extend(found)
                page_info.append({'page': page_number, 'rows': len(found),
                                  'method': found[0]['method'] if found else 'NOT_FOUND'})
    else:
        raw = np.fromfile(path, dtype=np.uint8)
        image = cv2.imdecode(raw, cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError('Gambar tidak dapat dibuka')
        equipment = ocr_table(image, 1)
        page_info.append({'page': 1, 'rows': len(equipment),
                          'method': 'OCR_LAYOUT' if equipment else 'NOT_FOUND'})
    return {
        'document_type': 'PERSETUJUAN_IMPOR',
        'source_name': os.path.basename(path),
        'total_pages': len(page_info),
        'pages': page_info,
        'equipment': equipment,
        'total_equipment': len(equipment),
    }
