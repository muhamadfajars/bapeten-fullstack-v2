"""CPU-bound evidence extraction workers for BAPETEN.

One shared *process* pool across all submissions. An OCR model is imported lazily
and retained for the lifetime of a worker. This avoids N thread pools all
fighting over the same CPU or repeatedly initializing the model.
"""
from __future__ import annotations
import atexit
import hashlib
import json
import multiprocessing as mp
import os
import re
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor
from functools import lru_cache
from pathlib import Path
from threading import Lock
from threading import Condition, Timer
from contextlib import contextmanager

from . import storage

POOL_LOCK=Lock()
POOL=None


def settings():
    available=len(os.sched_getaffinity(0)) if hasattr(os,'sched_getaffinity') else (os.cpu_count() or 1)
    # 80 logical CPUs: 20 workers x 4 model threads by default.
    threads=max(1,int(os.getenv('BAPETEN_OCR_CPU_THREADS','4')))
    target=max(1,int(os.getenv('BAPETEN_OCR_PROCESSES',str(max(1,(available+threads-1)//threads)))))
    workers=min(target,available)
    return workers,threads,available


def _worker_initialize(threads):
    for name in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS',
                 'VECLIB_MAXIMUM_THREADS','NUMEXPR_NUM_THREADS','PADDLE_NUM_THREADS'):
        os.environ[name]=str(threads)
    os.environ['BAPETEN_OCR_CPU_THREADS']=str(threads)
    os.environ['BAPETEN_LABEL_PARALLEL']='0'  # nested multiprocessing leads to oversubscription
    try:
        import cv2
        cv2.setNumThreads(1)
    except ImportError:
        pass


# BAPETEN OCR IDLE v063: recycle heavy workers after 10 minutes with no active analyses.
# Keep FastAPI running; only the CPU process pool is retired.
POOL_STATE=Condition(POOL_LOCK)
ACTIVE_ANALYSES=0
POOL_CLOSING=False
IDLE_TIMER=None
IDLE_GENERATION=0


def _idle_seconds():
    # Set from backend/.env. Default is 600 seconds (10 minutes).
    try:
        return max(1, int(os.getenv('BAPETEN_OCR_IDLE_SECONDS', '600')))
    except ValueError:
        return 600


def _cancel_idle_timer_locked():
    global IDLE_TIMER, IDLE_GENERATION
    IDLE_GENERATION += 1
    old_timer, IDLE_TIMER = IDLE_TIMER, None
    if old_timer is not None:
        old_timer.cancel()


def _idle_retire(expected_generation):
    global POOL, POOL_CLOSING, IDLE_TIMER
    with POOL_STATE:
        # A new job cancels the previous timer, even if its callback started.
        if (expected_generation != IDLE_GENERATION or ACTIVE_ANALYSES != 0
                or POOL is None or POOL_CLOSING):
            return
        retiring, POOL = POOL, None
        IDLE_TIMER = None
        POOL_CLOSING = True

    try:
        # wait=True: existing worker processes really exit before the new pool is allowed.
        # Never send SIGTERM to a pool while an analysis is still active.
        retiring.shutdown(wait=True, cancel_futures=False)
        print('BAPETEN OCR: idle 10 menit, pool pekerja ditutup dan RAM dilepas.', flush=True)
    finally:
        with POOL_STATE:
            POOL_CLOSING = False
            POOL_STATE.notify_all()


def _schedule_idle_timer_locked():
    global IDLE_TIMER
    _cancel_idle_timer_locked()
    if POOL is None:
        return
    generation = IDLE_GENERATION
    timer = Timer(_idle_seconds(), _idle_retire, args=(generation,))
    timer.daemon = True
    IDLE_TIMER = timer
    timer.start()


@contextmanager
def analysis_session():
    """Keep the OCR pool alive while any evaluator analysis is executing."""
    global ACTIVE_ANALYSES
    with POOL_STATE:
        while POOL_CLOSING:
            POOL_STATE.wait()
        ACTIVE_ANALYSES += 1
        _cancel_idle_timer_locked()
    try:
        yield
    finally:
        with POOL_STATE:
            ACTIVE_ANALYSES -= 1
            if ACTIVE_ANALYSES == 0:
                _schedule_idle_timer_locked()


def get_pool():
    global POOL
    with POOL_STATE:
        while POOL_CLOSING:
            POOL_STATE.wait()
        if POOL is None:
            # Ensure forkserver/spawn resolves the same private data dir as API process.
            os.environ['BAPETEN_DATA_DIR'] = str(storage.ROOT)
            workers, threads, _ = settings()
            mode = 'forkserver' if 'forkserver' in mp.get_all_start_methods() else 'spawn'
            POOL = ProcessPoolExecutor(
                max_workers=workers, mp_context=mp.get_context(mode),
                initializer=_worker_initialize, initargs=(threads,))
        return POOL


def shutdown():
    global POOL
    with POOL_STATE:
        _cancel_idle_timer_locked()
        p, POOL = POOL, None
    if p is not None:
        # Preserve existing fast exit behavior; patch v062 stops the process group.
        p.shutdown(wait=False, cancel_futures=True)

atexit.register(shutdown)


def _safe_id(s):
    if not re.fullmatch(r'[0-9a-f]{32}',str(s)):raise ValueError('Invalid storage identifier')
    return s


def code_digest():
    # Invalidate results after any engine source change, not just OCR changes.
    root=Path(__file__).resolve().parents[1]/'engine'/'src'
    digest=hashlib.sha256(b'BAPETEN-v049-streamlit-parity')
    for path in sorted(root.rglob('*.py')):
        digest.update(str(path.relative_to(root)).encode())
        digest.update(path.read_bytes())
    adapter=Path(__file__).resolve().with_name('engine_adapter.py')
    digest.update(adapter.read_bytes())
    return digest.hexdigest()


def cache_key(doc,reference_digest,source_digest):
    payload={'sha256':doc['sha256'],'category':doc['category'],
             'subtype':doc.get('subtype'),'ref':reference_digest,'source':source_digest,
             'ocr_profile':os.getenv('BAPETEN_OCR_PROFILE','fast'),
             'engine':os.getenv('BAPETEN_OCR_ENGINE','auto')}
    return hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()


def _cache_file(doc,key):
    return storage.ROOT/'extraction_cache'/_safe_id(doc['app_id'])/_safe_id(doc['id'])/(key+'.json')


def _read_cache(path,doc):
    try:
        data=json.loads(path.read_text(encoding='utf-8'))
        if data['cache_format']!=2 or not isinstance(data['rows'],list):return None
        # Every row is bound to this specific document (never re-use another user's ID).
        if any(r.get('document_id')!=doc['id'] for r in data['rows']):return None
        return data['rows']
    except (OSError,ValueError,KeyError,TypeError):
        return None


def _write_cache(path,rows):
    path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    payload={'cache_format':2,'rows':rows}
    fd,tmp=tempfile.mkstemp(prefix='.cache_',dir=path.parent)
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as fp:
            os.fchmod(fp.fileno(),0o600)
            json.dump(payload,fp,ensure_ascii=False)
        os.replace(tmp,path)
    finally:
        Path(tmp).unlink(missing_ok=True)


def process_form(form_doc):
    import sys
    root=Path(__file__).resolve().parents[1]/'engine'
    if str(root) not in sys.path:sys.path.insert(0,str(root))
    from src.parser import parse_application
    start=time.perf_counter()
    result=parse_application(str(storage.file_path(form_doc)))
    return result,round(time.perf_counter()-start,3)


def process_support(doc,application,reference,key):
    """Worker isolated entrypoint. Preserve original handler semantics."""
    from .engine_adapter import HANDLERS
    start=time.perf_counter()
    path=_cache_file(doc,key)
    if os.getenv('BAPETEN_EXTRACTION_CACHE','1')=='1':
        cached=_read_cache(path,doc)
        if cached is not None:
            return {'rows':cached,'cached':True,'seconds':round(time.perf_counter()-start,3)}
    path_override=None
    effective_doc=doc
    try:
        if Path(doc['filename']).suffix.lower()=='.docx':
            from src.extraction.office_conversion import convert_word_to_pdf,has_converter
            if has_converter():
                path_override=convert_word_to_pdf(str(storage.file_path(doc)))
                effective_doc={**doc,'_analysis_path':path_override}
            elif doc['category']!='personel':
                raise RuntimeError('DOCX membutuhkan LibreOffice di HPC untuk kategori ini (sudo apt install libreoffice-writer)')
        rows=HANDLERS[doc['category']](effective_doc,application,reference)
    finally:
        if path_override:Path(path_override).unlink(missing_ok=True)
    duration=round(time.perf_counter()-start,3)
    if rows and os.getenv('BAPETEN_EXTRACTION_CACHE','1')=='1':
        try:_write_cache(path,rows)
        except OSError:pass  # cache failure must never discard fresh evidence
    return {'rows':rows,'cached':False,'seconds':duration}


def cache_key_label_group(documents,reference_digest,source_digest):
    """Atomic key: any changed label invalidates the combined extraction."""
    payload={'documents':[(d['id'],d['sha256'],d['filename']) for d in documents],
             'ref':reference_digest,'source':source_digest,
             'ocr_profile':os.getenv('BAPETEN_OCR_PROFILE','fast'),
             'engine':os.getenv('BAPETEN_OCR_ENGINE','auto'),
             'label_profile':os.getenv('BAPETEN_LABEL_OCR_PROFILE','quality'),'group_version':2}
    return hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()


def process_label_group(documents,application,reference,key):
    from .engine_adapter import _label_group
    start=time.perf_counter()
    first=documents[0]
    path=_cache_file(first,'labels_'+key)
    if os.getenv('BAPETEN_EXTRACTION_CACHE','1')=='1':
        cached=_read_cache_label_group(path,documents)
        if cached is not None:
            return {'rows':cached,'cached':True,'seconds':round(time.perf_counter()-start,3)}
    rows=_label_group(documents,application,reference)
    duration=round(time.perf_counter()-start,3)
    if rows and os.getenv('BAPETEN_EXTRACTION_CACHE','1')=='1':
        try:_write_cache(path,rows)
        except OSError:pass
    return {'rows':rows,'cached':False,'seconds':duration}


def _read_cache_label_group(path,documents):
    try:
        data=json.loads(path.read_text(encoding='utf-8'))
        valid_ids={d['id'] for d in documents}
        if data.get('cache_format')!=2 or not isinstance(data.get('rows'),list):return None
        if any(row.get('document_id') not in (None,*valid_ids) for row in data['rows']):return None
        return data['rows']
    except (OSError,ValueError,KeyError,TypeError):
        return None


def get_label_cached(documents,key):
    if os.getenv('BAPETEN_EXTRACTION_CACHE','1')!='1':return None
    start=time.perf_counter()
    path=_cache_file(documents[0],'labels_'+key)
    rows=_read_cache_label_group(path,documents)
    if rows is None:return None
    return {'rows':rows,'seconds':round(time.perf_counter()-start,3),'cached':True}


def ocr_label_piece(doc,equipment):
    """Runs on existing shared process pool; parallelizes files without nested pools."""
    from src.extraction.label_document_ocr import ocr_label_documents
    start=time.perf_counter()
    # Use Streamlit-quality profile, never the degraded mobile-only fast pass.
    previous=os.environ.get('BAPETEN_OCR_PROFILE')
    os.environ['BAPETEN_OCR_PROFILE']='quality'
    try:
        pages=ocr_label_documents([{'path':str(storage.file_path(doc)),
                                   'name':doc['filename'],'source_id':doc['id']}],
                                  equipment_list=equipment)
    finally:
        if previous is None:os.environ.pop('BAPETEN_OCR_PROFILE',None)
        else:os.environ['BAPETEN_OCR_PROFILE']=previous
    return {'pages':pages,'seconds':round(time.perf_counter()-start,3)}


def finalize_label_group(documents,application,reference,key,pages):
    from .engine_adapter import _label_group
    rows=_label_group(documents,application,reference,prefetched_pages=pages)
    if rows and os.getenv('BAPETEN_EXTRACTION_CACHE','1')=='1':
        try:_write_cache(_cache_file(documents[0],'labels_'+key),rows)
        except OSError:pass
    return {'rows':rows,'cached':False}
