"""Speculative, one-wave label quality OCR using the existing shared worker pool.

Important invariant: do not change what evidence is passed to the matcher.
Original OCR and both quality preprocessing variants are submitted together;
only gray/CLAHE pages selected by the original gate are attached, and always
in original, gray, CLAHE order exactly as in v0.5.7.

This module NEVER instantiates a new process pool and never changes OCR/model,
preprocessing, normalization or matching. v0.5.7 module remains installed.
"""
from __future__ import annotations

import os
import sys
import time
from concurrent.futures import as_completed

from . import label_parallel_v057 as legacy


def run_label_group(pool, documents, equipment, source_digest, log=None):
    """Run original/gray/CLAHE for each file in one wave, preserving v057 gates.

    Set BAPETEN_LABEL_EAGER_FANOUT=0 to revert *scheduling only* to v057.
    Results are per-file, per-panel, and deterministically ordered regardless
    of completion order. Original failures remain fatal; selected secondary
    failures are logged and ignored, preserving v057 behaviour.
    """
    if os.getenv('BAPETEN_LABEL_EAGER_FANOUT', '1').strip().lower() in ('0', 'false', 'no'):
        return legacy.run_label_group(pool, documents, equipment, source_digest, log=log)

    if not documents:
        return {'pages': [], 'seconds': 0.0, 'pass_timings': []}

    start = time.perf_counter()
    # Six jobs for two label files. Reuse exactly v057's quality-OCR function,
    # including panel/ROI extraction, GS1, preprocessing, model and private cache.
    tasks = {}
    for index, doc in enumerate(documents):
        for variant in legacy.VARIANTS:
            future = pool.submit(legacy.ocr_variant, doc, variant, source_digest)
            tasks[future] = (index, variant)

    results = {}
    errors = {}
    timings = []
    for future in as_completed(tasks):
        index, variant = tasks[future]
        try:
            result = future.result()
            results[(index, variant)] = result['pages']
            timings.append({
                '_index': index,
                'doc': documents[index]['filename'],
                'variant': variant,
                'seconds': result['seconds'],
                'cache_hit': result['cached'],
            })
        except Exception as exc:
            errors[(index, variant)] = exc

    # Fatal primary errors are not silently replaced by secondary OCR evidence.
    for index in range(len(documents)):
        if (index, 'original') in errors:
            raise errors[(index, 'original')]

    output = []
    used_secondary = 0
    unused_secondary = 0
    for index in range(len(documents)):
        original = results[(index, 'original')]
        selected = set(legacy._retry_indices(original, equipment))
        for variant in ('gray', 'clahe'):
            if not selected:
                unused_secondary += 1
            else:
                used_secondary += 1
                exc = errors.get((index, variant))
                if exc is not None:
                    print(f'[LABEL-V058] secondary {variant} failed for '
                          f'{documents[index]["filename"]}: {type(exc).__name__}: {exc}',
                          file=sys.stderr, flush=True)
                    continue
                if len(results[(index, variant)]) != len(original):
                    raise RuntimeError('Inconsistent label panel layout between OCR variants')

        for page_index, page in enumerate(original):
            # Preserve v057's exact original -> gray -> CLAHE row order.
            for variant in ('gray', 'clahe'):
                if page_index in selected and (index, variant) in results:
                    page['ocr'].extend(results[(index, variant)][page_index]['ocr'])
            output.append(page)

    # Trace only, not used to calculate status or confidence.
    elapsed = round(time.perf_counter() - start, 3)
    timings.sort(key=lambda t: (t['_index'], legacy.VARIANTS.index(t['variant'])))
    for item in timings:
        del item['_index']
    print(f'[LABEL-V058] wall={elapsed:.2f}s documents={len(documents)} '
          f'passes={len(timings)} secondary_used={used_secondary} '
          f'secondary_speculative_unused={unused_secondary} '
          f'cached={sum(t["cache_hit"] for t in timings)}', flush=True)
    return {'pages': output, 'seconds': elapsed, 'pass_timings': timings}
