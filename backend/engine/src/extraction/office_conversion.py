"""LibreOffice headless conversion, isolated per document and bounded in time.

No macros are executed through LibreOffice's --convert-to operation. Still only
accept Office files from trusted users of this internal application.
"""
import os
import shutil
import subprocess
import tempfile

OFFICE_EXTENSIONS={'.doc','.docx'}

def has_converter():
    return bool(shutil.which('libreoffice') or shutil.which('soffice'))

def convert_word_to_pdf(path, timeout=120):
    if os.path.splitext(path)[1].lower() not in OFFICE_EXTENSIONS:
        return path
    binary=shutil.which('libreoffice') or shutil.which('soffice')
    if not binary:
        raise RuntimeError('Konversi Word memerlukan LibreOffice (libreoffice-writer) di HPC. Minta admin instal atau unggah versi PDF terlebih dahulu.')
    folder=tempfile.mkdtemp(prefix='bapeten_word_')
    profile=os.path.join(folder,'lo_profile')
    try:
        completed=subprocess.run([binary,'-env:UserInstallation=file://'+profile,'--headless','--nologo','--nodefault','--nolockcheck', '--convert-to','pdf:writer_pdf_Export', '--outdir',folder,path],capture_output=True,text=True,timeout=timeout,check=False)
        output=os.path.join(folder,os.path.splitext(os.path.basename(path))[0]+'.pdf')
        if completed.returncode!=0 or not os.path.exists(output) or os.path.getsize(output)==0:
            raise RuntimeError('Konversi dokumen Word gagal: '+(completed.stderr or completed.stdout)[-400:])
        # keep only conversion file; caller owns returned path and should unlink it
        handle=tempfile.NamedTemporaryFile(delete=False,suffix='.pdf')
        handle.close();shutil.copyfile(output,handle.name)
        return handle.name
    finally:
        shutil.rmtree(folder,ignore_errors=True)
