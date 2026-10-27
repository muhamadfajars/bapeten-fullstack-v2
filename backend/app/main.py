"""Authenticated FastAPI bridge for the original BAPETEN Python engine.

This is an internal single-workspace prototype. Configure trusted reverse proxy,
authentication and access controls before any multi-tenant production deployment.
"""
from __future__ import annotations
import hashlib, hmac, os, re, shutil, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Lock
from fastapi import Request, FastAPI, UploadFile, File, Form, Depends, HTTPException, Header, BackgroundTasks
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from . import storage
from . import vpn_access

CATEGORIES={'formulir','proteksi','perawatan','manajemen','teknis','personel','tld','spesifikasi','label','impor','kesesuaian','fungsi','paparan','kebocoran'}
EXT={'.pdf','.png','.jpg','.jpeg','.bmp','.webp','.tif','.tiff','.docx'}
MAX_FILE=int(os.environ.get('BAPETEN_MAX_FILE_MB','40'))*1024*1024
MAX_DOCS=int(os.environ.get('BAPETEN_MAX_DOCUMENTS','120'))
TOKEN=os.environ.get('BAPETEN_API_TOKEN','')
app=FastAPI(title='BAPETEN AI Evaluator API',version='0.2.0',docs_url=None,redoc_url=None)
origins=[v.strip() for v in os.environ.get('BAPETEN_CORS_ORIGINS','http://localhost:5173,http://127.0.0.1:5173').split(',') if v.strip()]
app.add_middleware(CORSMiddleware,allow_origins=origins,allow_credentials=False,allow_methods=['GET','POST','DELETE'],allow_headers=['Authorization','Content-Type'])
POOL=ThreadPoolExecutor(max_workers=max(1,int(os.environ.get('BAPETEN_ANALYSIS_WORKERS','1'))))
SUBMIT_LOCK=Lock()


def authorize(authorization: str | None=Header(default=None)):
    if not TOKEN:
        # Development-only, explicit opt-in. Never bypass authentication by default.
        if os.environ.get('BAPETEN_ALLOW_UNAUTHENTICATED_LOCAL_DEV')=='1': return
        raise HTTPException(503,'BAPETEN_API_TOKEN belum disetel pada server')
    candidate=authorization.removeprefix('Bearer ').strip() if authorization and authorization.startswith('Bearer ') else ''
    if not hmac.compare_digest(candidate,TOKEN):raise HTTPException(401,'Token akses tidak valid')


def must_app(aid):
    if not re.fullmatch(r'[0-9a-f]{32}',aid) or not storage.app_exists(aid):raise HTTPException(404,'Permohonan tidak ditemukan')


@app.get('/api/v1/health')
def health():return {'status':'ok','api_version':'v2','engine':'BAPETEN v46','authentication_configured':bool(TOKEN)}


@app.post('/api/v1/applications',dependencies=[Depends(authorize)])
def create_application(request: Request):
    aid = storage.create_application()
    if vpn_access.enabled():
        vpn_access.register_new(aid, request.headers.get('x-bapeten-vpn-user', '').strip())
    return {'application_id': aid}


@app.get('/api/v1/applications/{aid}/documents',dependencies=[Depends(authorize)])
def list_documents(aid:str):
    must_app(aid)
    return {'documents':storage.documents(aid)}


@app.post('/api/v1/applications/{aid}/documents',dependencies=[Depends(authorize)])
async def upload(aid:str,category:str=Form(...),subtype:str|None=Form(None),file:UploadFile=File(...)):
    must_app(aid)
    if category not in CATEGORIES:raise HTTPException(422,'Kategori tidak dikenal')
    if len(storage.documents(aid))>=MAX_DOCS:raise HTTPException(413,'Batas jumlah dokumen tercapai')
    filename=Path(file.filename or '').name[:180]
    ext=Path(filename).suffix.lower()
    if not filename or ext not in EXT:raise HTTPException(415,'Format dokumen tidak didukung')
    if category=='formulir' and ext!='.pdf':raise HTTPException(415,'Formulir acuan saat ini harus PDF')
    if category=='personel' and not subtype:raise HTTPException(422,'Pilih subjenis dokumen personel')
    temp_name=storage.make_id()+ext
    folder=storage.ROOT/'uploads'/aid;folder.mkdir(parents=True,exist_ok=True,mode=0o700)
    target=folder/temp_name
    digest=hashlib.sha256();size=0
    try:
        with target.open('xb') as out:
            while chunk:=await file.read(1024*1024):
                size+=len(chunk)
                if size>MAX_FILE:raise HTTPException(413,f'File melebihi {MAX_FILE//(1024*1024)} MB')
                digest.update(chunk);out.write(chunk)
        if size==0:raise HTTPException(422,'File kosong')
        with target.open('rb') as src:
            head=src.read(16)
        if ext=='.pdf' and not head.startswith(b'%PDF-'):raise HTTPException(415,'File bukan PDF valid')
        if ext=='.docx' and not head.startswith(b'PK'):raise HTTPException(415,'File bukan DOCX valid')
        # Do not deduplicate different categories or uploads silently.
        did=storage.add_document(aid,category,subtype,filename,size,digest.hexdigest(),temp_name)
        return {'document':next(d for d in storage.documents(aid) if d['id']==did)}
    except BaseException:
        target.unlink(missing_ok=True);raise
    finally:await file.close()


@app.delete('/api/v1/applications/{aid}/documents/{did}',dependencies=[Depends(authorize)])
def remove_document(aid:str,did:str):
    must_app(aid)
    j=storage.get_job_latest_running(aid) if hasattr(storage,'get_job_latest_running') else None
    if j:raise HTTPException(409,'Tidak dapat menghapus saat analisis aktif')
    if not storage.delete_document(did,aid):raise HTTPException(404,'Berkas tidak ditemukan')
    return {'deleted':True}


@app.get('/api/v1/applications/{aid}/documents/{did}/file',dependencies=[Depends(authorize)])
def get_document(aid:str,did:str):
    must_app(aid)
    d=storage.document(did,aid)
    if not d:raise HTTPException(404,'Berkas tidak ditemukan')
    path=storage.file_path(d)
    if not path.is_file():raise HTTPException(404,'Berkas fisik tidak ditemukan')
    return FileResponse(path,media_type='application/pdf' if d['filename'].lower().endswith('.pdf') else 'application/octet-stream',filename=d['filename'],content_disposition_type='inline' if d['filename'].lower().endswith('.pdf') else 'attachment',headers={'Cache-Control':'private, no-store','X-Content-Type-Options':'nosniff'})



@app.get('/api/v1/applications/{aid}/documents/{did}/evidence-page/{page_number}',dependencies=[Depends(authorize)])
def get_evidence_page(aid:str,did:str,page_number:int):
    """Private rendering of EXACTLY ONE source page; never stream the full PDF."""
    from fastapi.responses import Response
    import fitz
    must_app(aid)
    doc=storage.document(did,aid)
    if not doc:raise HTTPException(404,'Dokumen tidak ditemukan')
    source=storage.file_path(doc)
    if not source.is_file():raise HTTPException(404,'File tidak tersedia')
    # No arbitrary paths, no guessing page number, bounded image memory.
    if source.suffix.lower()!='.pdf':raise HTTPException(415,'Halaman bukti hanya tersedia untuk PDF')
    if page_number < 1:raise HTTPException(422,'Nomor halaman tidak valid')
    with fitz.open(str(source)) as pdf:
        if page_number>len(pdf):raise HTTPException(404,'Halaman bukti tidak ditemukan')
        pg=pdf[page_number-1]
        factor=min(1.7,2000/max(pg.rect.width,pg.rect.height))
        pix=pg.get_pixmap(matrix=fitz.Matrix(factor,factor),alpha=False,colorspace=fitz.csRGB)
        image=pix.tobytes('jpeg',jpg_quality=80)
    return Response(image,media_type='image/jpeg',headers={'Cache-Control':'private, no-store','X-Content-Type-Options':'nosniff'})


@app.get('/api/v1/applications/{aid}/documents/{did}/preview',dependencies=[Depends(authorize)])
def preview_document(aid:str,did:str,background_tasks:BackgroundTasks):
    """Authenticated inline preview. Temporary DOCX conversion never replaces upload."""
    must_app(aid)
    d=storage.document(did,aid)
    if not d:raise HTTPException(404,'Dokumen tidak ditemukan')
    path=storage.file_path(d)
    if not path.is_file():raise HTTPException(404,'Berkas fisik tidak ditemukan')
    ext=path.suffix.lower()
    if ext=='.docx':
        from . import storage as _storage
        import sys
        engine=str(Path(__file__).resolve().parents[1]/'engine')
        if engine not in sys.path:sys.path.insert(0,engine)
        from src.extraction.office_conversion import convert_word_to_pdf
        try:converted=convert_word_to_pdf(str(path))
        except Exception as exc:raise HTTPException(503,f'Pratinjau DOCX memerlukan LibreOffice: {exc}') from exc
        background_tasks.add_task(Path(converted).unlink,missing_ok=True)
        return FileResponse(converted,media_type='application/pdf',content_disposition_type='inline',headers={'Cache-Control':'private, no-store','X-Content-Type-Options':'nosniff'})
    if ext=='.pdf':
        return FileResponse(path,media_type='application/pdf',content_disposition_type='inline',headers={'Cache-Control':'private, no-store','X-Content-Type-Options':'nosniff'})
    if ext in {'.jpg','.jpeg','.png','.webp'}:
        media={'.jpg':'image/jpeg','.jpeg':'image/jpeg','.png':'image/png','.webp':'image/webp'}[ext]
        return FileResponse(path,media_type=media,content_disposition_type='inline',headers={'Cache-Control':'private, no-store','X-Content-Type-Options':'nosniff'})
    raise HTTPException(415,'Pratinjau format ini belum didukung')

def _run(jid,aid):
    from .engine_adapter import analyze_application
    from . import performance
    try:
        storage.update_job(jid,status='running',progress=1,message='Memulai parser formulir')
        with performance.analysis_session():
            result=analyze_application(aid,lambda p,msg:storage.update_job(jid,progress=p,message=msg))
            result['job_id']=jid
            storage.update_job(jid,status='completed',progress=100,message='Analisis selesai',result=result)
    except Exception as exc:
        storage.update_job(jid,status='failed',error=f'{type(exc).__name__}: {exc}',message='Analisis gagal')


@app.post('/api/v1/applications/{aid}/analyses',dependencies=[Depends(authorize)])
def start_analysis(aid:str):
    must_app(aid)
    docs=storage.documents(aid)
    if not any(d['category']=='formulir' for d in docs):raise HTTPException(422,'Unggah Formulir Permohonan PDF dahulu')
    with SUBMIT_LOCK:
        with storage.db() as con:
            active=storage.row(con,"SELECT id,status FROM jobs WHERE app_id=? AND status IN ('queued','running') ORDER BY created DESC LIMIT 1",(aid,))
        if active:raise HTTPException(409,'Analisis sudah berjalan untuk permohonan ini')
        jid=storage.create_job(aid)
        POOL.submit(_run,jid,aid)
    return {'job_id':jid,'status':'queued','progress':0}


@app.get('/api/v1/applications/{aid}/jobs/{jid}',dependencies=[Depends(authorize)])
def job(aid:str,jid:str):
    must_app(aid); j=storage.get_job(jid,aid)
    if not j:raise HTTPException(404,'Job tidak ditemukan')
    return {k:j[k] for k in ('id','status','progress','message','error','created','updated')}


@app.get('/api/v1/applications/{aid}/results',dependencies=[Depends(authorize)])
def results(aid:str):
    must_app(aid)
    result=storage.latest_result(aid)
    if result is None:raise HTTPException(404,'Belum ada analisis yang selesai')
    return result


# Optional single-port intranet deployment: a prebuilt React dist/ served by FastAPI.
# This is intentionally registered AFTER every /api route so the API takes priority.
# The static bundle contains no uploaded source documents or authentication tokens.
_frontend_dist = os.environ.get('BAPETEN_FRONTEND_DIST', '').strip()
if _frontend_dist:
    from fastapi.staticfiles import StaticFiles
    _frontend_path = Path(_frontend_dist).expanduser().resolve()
    if not (_frontend_path / 'index.html').is_file():
        raise RuntimeError('BAPETEN_FRONTEND_DIST harus menunjuk frontend/dist berisi index.html')
    app.mount('/', StaticFiles(directory=str(_frontend_path), html=True), name='frontend')

# VPN reverse proxy boundary. Must register before ASGI application starts.
app.middleware('http')(vpn_access.gateway_middleware)
