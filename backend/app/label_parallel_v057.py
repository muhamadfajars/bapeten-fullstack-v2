"""CPU quality-OCR fanout for label documents, using the EXISTING shared pool.

OCR strategy deliberately identical to label_document_ocr v0.5.1 with
BAPETEN_LABEL_FULL_RETRIES=1. The difference is only task placement:
  Stage A: original per file concurrently
  Stage B: grayscale and CLAHE per file concurrently (if original gate asks)
  Stage C: assemble rows in original, grayscale, CLAHE order and match ONCE.
No subprocess pool is ever created here. No fast/mobile model is used.
"""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
import re
import sys
import tempfile
import time
from concurrent.futures import as_completed
from pathlib import Path

from . import storage

VARIANTS = ('original', 'gray', 'clahe')
CACHE_FORMAT = 'label-ocr-stage-v057-1'


def _source_path(doc):
    return str(storage.file_path(doc))


def _model_signature():
    try:
        v = importlib.metadata.version('paddleocr')
    except importlib.metadata.PackageNotFoundError:
        v = 'not-installed'
    try:
        paddle_runtime = importlib.metadata.version('paddlepaddle')
    except importlib.metadata.PackageNotFoundError:
        paddle_runtime = 'not-installed'
    return {
        'paddle_runtime_version': paddle_runtime,
        'paddleocr_version': v,
        'engine': os.getenv('BAPETEN_OCR_ENGINE', 'auto'),
        'profile': 'quality',
        'cpu_threads': os.getenv('BAPETEN_OCR_CPU_THREADS', '4'),
        'pdx_mkldnn': '0',
    }


def _variant_cache_path(doc, variant, source_digest, selected, pdf_dpi):
    for key in ('id', 'app_id'):
        if not re.fullmatch(r'[a-f0-9]{32}', str(doc.get(key, ''))):
            raise ValueError(f'Invalid uploaded document {key}')
    # Scoped to the exact uploaded file AND application: no cross-user evidence leakage.
    payload = {
        'format': CACHE_FORMAT, 'sha256': doc['sha256'],
        'doc_id': doc['id'], 'category': 'label',
        'variant': variant, 'selected': selected,
        'source_digest': source_digest, 'dpi': pdf_dpi,
        'model': _model_signature(),
    }
    key = hashlib.sha256(json.dumps(payload, sort_keys=True).encode('utf-8')).hexdigest()
    return storage.ROOT / 'label_variant_cache_v057' / doc['app_id'] / doc['id'] / (key + '.json')


def _read_variant_cache(path, doc, variant):
    try:
        with path.open('r', encoding='utf-8') as fp:
            result = json.load(fp)
        if result.get('cache_format') != CACHE_FORMAT or result.get('doc_id') != doc['id']:
            return None
        if result.get('variant') != variant or not isinstance(result.get('pages'), list):
            return None
        if any(p.get('source_id') != doc['id'] for p in result['pages']):
            return None
        return result['pages']
    except (OSError, ValueError, TypeError):
        return None


def _write_variant_cache(path, doc, variant, pages):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    data = {'cache_format': CACHE_FORMAT, 'doc_id': doc['id'],
            'variant': variant, 'pages': pages}
    fd, temp_name = tempfile.mkstemp(prefix='.writing_', suffix='.json', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as fp:
            os.fchmod(fp.fileno(), 0o600)
            json.dump(data, fp, ensure_ascii=False)
        os.replace(temp_name, path)
    finally:
        Path(temp_name).unlink(missing_ok=True)


def _prepare_pages(doc, dpi):
    from src.extraction.label_document import prepare_label_document
    from src.extraction.label_panel_v051 import detect_sticker_panels
    pages = []
    for item in prepare_label_document(_source_path(doc), pdf_dpi=dpi):
        image = item['image']
        panels = detect_sticker_panels(image) if item['source_type'] == 'image' else []
        if panels:
            for n, (xa, ya, xb, yb) in enumerate(panels, 1):
                crop = image[ya:yb, xa:xb].copy()
                pages.append(({
                    'source_id': doc['id'], 'source_name': doc['filename'],
                    'source_type': item['source_type'], 'page': item['page'],
                    'panel': n, 'panel_box': [xa, ya, xb, yb],
                    'width': crop.shape[1], 'height': crop.shape[0],
                }, crop))
        else:
            pages.append(({
                'source_id': doc['id'], 'source_name': doc['filename'],
                'source_type': item['source_type'], 'page': item['page'],
                'width': item['width'], 'height': item['height'],
            }, image))
    return pages


def ocr_variant(doc, variant, source_digest, selected=None, pdf_dpi=200):
    """ProcessPoolExecutor entrypoint. Never returns full image arrays."""
    if variant not in VARIANTS:
        raise ValueError(f'Invalid label OCR variant: {variant!r}')
    if doc['category'] != 'label':
        raise ValueError('Not a label document')
    if selected is not None:
        selected = tuple(sorted(set(int(i) for i in selected)))
    began = time.perf_counter()
    cache = _variant_cache_path(doc, variant, source_digest, selected, pdf_dpi)
    if os.getenv('BAPETEN_LABEL_VARIANT_CACHE', '1') == '1':
        pages = _read_variant_cache(cache, doc, variant)
        if pages is not None:
            return {'pages': pages, 'seconds': round(time.perf_counter()-began, 3),
                    'cached': True, 'variant': variant}

    old_profile = os.environ.get('BAPETEN_OCR_PROFILE')
    os.environ['BAPETEN_OCR_PROFILE'] = 'quality'
    try:
        from src.extraction.label_document_ocr import _ocr_worker
        from src.extraction.label_gs1_v051 import augment_gs1_rows
        pages = []
        for page_index, (meta, image) in enumerate(_prepare_pages(doc, pdf_dpi)):
            if selected is not None and page_index not in selected:
                pages.append({**meta, 'ocr': []})
                continue
            rows = _ocr_worker((image, variant))
            pages.append({**meta, 'ocr': augment_gs1_rows(rows)})
    finally:
        if old_profile is None:
            os.environ.pop('BAPETEN_OCR_PROFILE', None)
        else:
            os.environ['BAPETEN_OCR_PROFILE'] = old_profile
    if os.getenv('BAPETEN_LABEL_VARIANT_CACHE', '1') == '1':
        try:
            _write_variant_cache(cache, doc, variant, pages)
        except OSError:
            pass  # cache never determines correctness
    return {'pages': pages, 'seconds': round(time.perf_counter()-began, 3),
            'cached': False, 'variant': variant}


def _retry_indices(pages, equipment):
    # Preserve EXACT v0.5.1 condition per source document, not across all files.
    from src.extraction.label_document_ocr import _original_match_count, _needs_secondary_ocr
    count = _original_match_count(pages, equipment) if equipment is not None else None
    return [] if count == 6 else [i for i, p in enumerate(pages)
                                   if count == 0 or _needs_secondary_ocr(p['ocr'])]


def run_label_group(pool, documents, equipment, source_digest, log=None):
    """Coordinator runs in a *thread*, not a pool process; no nested processes.

    Submission of independent OCR tasks to the same pool makes 2 image files
    utilize up to 6 CPU workers across the two stages. Results ordered exactly
    like sequential per-file original, gray, CLAHE passes.
    """
    began = time.perf_counter()
    originals = {pool.submit(ocr_variant, doc, 'original', source_digest): i
                 for i, doc in enumerate(documents)}
    original_pages = [None] * len(documents)
    timings = []
    for future in as_completed(originals):
        i = originals[future]
        result = future.result()  # primary OCR errors are never hidden
        original_pages[i] = result['pages']
        timings.append({'doc': documents[i]['filename'], 'variant': 'original',
                        'seconds': result['seconds'], 'cache_hit': result['cached']})

    # Each document keeps its original local gate, as in v0.5.1.
    pending = {}
    selected = {}
    for i, pages in enumerate(original_pages):
        indices = _retry_indices(pages, equipment)
        selected[i] = indices
        if not indices:
            continue
        for variant in ('gray', 'clahe'):
            f = pool.submit(ocr_variant, documents[i], variant, source_digest, indices)
            pending[f] = (i, variant)

    staged = {}
    for future in as_completed(pending):
        i, variant = pending[future]
        try:
            result = future.result()
        except Exception as exc:
            # Legacy _full_page_ocr_variants ignores secondary failures.
            # Preserve its behavior, but log failures visibly for diagnosis.
            print(f'[LABEL-V057] secondary {variant} failed for {documents[i]["filename"]}: '
                  f'{type(exc).__name__}: {exc}', file=sys.stderr, flush=True)
            continue
        staged[(i, variant)] = result['pages']
        timings.append({'doc': documents[i]['filename'], 'variant': variant,
                        'seconds': result['seconds'], 'cache_hit': result['cached']})

    # Deterministic ordering independent of worker completion order.
    output = []
    for i, base in enumerate(original_pages):
        for j, page in enumerate(base):
            for variant in ('gray', 'clahe'):
                if j not in selected[i]:
                    continue
                variants = staged.get((i, variant))
                if variants is not None:
                    if len(variants) != len(base):
                        raise RuntimeError('Inconsistent label panel layout between OCR variants')
                    page['ocr'].extend(variants[j]['ocr'])
            output.append(page)
    wall = round(time.perf_counter()-began, 3)
    print(f'[LABEL-V057] wall={wall:.2f}s documents={len(documents)} '
          f'passes={len(timings)} cached={sum(t["cache_hit"] for t in timings)}', flush=True)
    return {'pages': output, 'seconds': wall, 'pass_timings': timings}
