"""Merge independent text, layout, and checkbox evidence without certifying document completeness."""
from __future__ import annotations
import re
from collections import Counter


def _norm(value):
    return re.sub(r'[^a-z0-9]+', '', str(value or '').casefold())


def merge_evidence(text_status, checkbox_result):
    """Checkbox results supersede noisy text for matching *pages*, never override a confirmed FAIL.

    A page with unsupported checkbox layout does not erase text/layout findings.
    The returned status is conservatively REVIEW unless any method confirms FAIL.
    """
    text_status = dict(text_status)
    cb_pages={int(p['page']) for p in checkbox_result.get('pages',[]) if p.get('rows') and p.get('method') in ('PDF_GLYPH','SCAN_SIEMENS_GRID')}
    raw_text_rows=list(text_status.get('rows',[]))
    kept=[]
    for r in raw_text_rows:
        # Keep explicitly confirmed FAIL across methods, even on a checkbox-recognized page.
        if r.get('status')=='FAIL' or r.get('page') not in cb_pages or str(r.get('method','')).startswith('LAYOUT_'):
            kept.append(dict(r))
    # Deduplicate text/layout vs checkbox on same page + normalized item
    seen=set()
    result_rows=[]
    for row in kept:
        key=(row.get('page'),_norm(row.get('item') or row.get('text')))
        if key not in seen:
            seen.add(key); result_rows.append(row)
    for r in checkbox_result.get('rows',[]):
        item=str(r.get('item') or '').strip()
        key=(r.get('page'),_norm(item))
        # Repeated labels (e.g. 'Size' in two different table sections) are distinct checks.
        # Do not deduplicate checkbox rows against each other; text from those pages
        # has already been suppressed above.
        result_rows.append({'page':r.get('page'),'item':item,'text':item+' -> '+','.join(map(str,r.get('selected') or [])),
                            'status':r.get('status','REVIEW'),'method':r.get('method'),'confidence':r.get('confidence'),
                            'selected':r.get('selected',[]),'evidence':r})
    counts={s:sum(row.get('status')==s for row in result_rows) for s in ('PASS','FAIL','EXCEPTION','REVIEW')}
    fail_items=[{'page':r.get('page'),'item':r.get('item') or r.get('text'),'method':r.get('method')} for r in result_rows if r.get('status')=='FAIL']
    text_status.update({'status':'FAIL_DETECTED' if fail_items else 'REVIEW',
                        'counts':counts,'rows':result_rows,'fail_items':fail_items,
                        'coverage_verified':False,'checkbox_evidence':checkbox_result,
                        'administrative_review':checkbox_result.get('administrative_review',[]),
                        'note':'Evidence screening only; no overall PASS until all relevant pages and checklist items are independently verified.'})
    return text_status
