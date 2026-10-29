"""Adapter preserving v46 engine decisions and provenance; no result fabrication."""
from __future__ import annotations
import os,re,sys,time
from pathlib import Path
from typing import Any
from . import storage
from .identity_policy_v065 import address_decision, clean_evidence, facility_decision, candidate_lines, select_candidate
from .unit_model_v068 import decide as _v068_unit_decision
from .reference_evidence_v069 import improve_rows as _v069_improve_rows
from .facility_guard_v070 import guard_rows as _v070_guard_rows
from .identity_consistency_v071 import finalize_identity as _v071_finalize_identity
from .evidence_cohesion_v072 import improve as _v072_improve
from .field_evidence_v073 import improve as _v073_improve
ENGINE=Path(__file__).resolve().parents[1]/'engine'
if str(ENGINE) not in sys.path:sys.path.insert(0,str(ENGINE))

NAMES={'proteksi':'Program Proteksi Radiasi','perawatan':'Program Perawatan','manajemen':'Sistem Manajemen',
       'teknis':'Dokumen Teknis','personel':'Dokumen Personel','tld':'Dokumen Petugas TLD',
       'spesifikasi':'Spesifikasi Alat','label':'Label Unit dan Tabung','impor':'Persetujuan Impor',
       'kesesuaian':'Uji Kesesuaian','fungsi':'Uji Fungsi / Acceptance Test',
       'paparan':'Uji Paparan Radiasi','kebocoran':'Uji Kebocoran Tabung'}
PROG={'proteksi':'program_protection_upload','perawatan':'program_maintenance_upload',
      'manajemen':'management_system_upload','teknis':'technical_documents_upload'}
SUPP={'tld':'tld_upload','paparan':'radiation_exposure_upload','kebocoran':'tube_leakage_upload'}
FIELDS={'merk_unit':'Merek Unit','tipe_unit':'Tipe Unit','nomor_seri_unit':'Nomor Seri Unit',
        'merk_tabung':'Merek Tabung','tipe_tabung':'Tipe Tabung','nomor_seri_tabung':'No. Seri Insersi Tabung'}


def _text(value):return str(value).strip() if value is not None else ''
def _status(v):
    s=_text(v).upper()
    return {'VALID':'MATCH','ACTIVE':'MATCH','DETECTED':'MATCH','INCOMPLETE':'MISSING','EXPIRED':'MISMATCH'}.get(s,s if s in {'MATCH','REVIEW','MISMATCH','MISSING'} else 'REVIEW')

def _row(field,expected,observed='',status='REVIEW',score=None,page=None,note='',document_id=None,quote='',detail=None):
    if re.search(r'(?i)alamat|tempat praktik', _text(field)):
        from .address_cleanup_v052 import clean_address_evidence
        observed = clean_evidence(clean_address_evidence(observed), 'address')
        status, score, address_note = address_decision(expected, observed, _status(status), score)
        if address_note:
            note = (' '.join(filter(None, [_text(note), address_note])))[:300]
    elif re.match(r'(?i)^nama\s+(?:fasilitas|rumah\s+sakit|rs|instansi)\b', _text(field)):
        observed = clean_evidence(observed, 'facility')
        status, score, facility_note = facility_decision(expected, observed, _status(status), score)
        if facility_note:
            note = (' '.join(filter(None, [_text(note), facility_note])))[:300]
    # v068: only Tipe Unit; NEVER change Merek Unit, Tipe Tabung or serials.
    status,score,model_note=_v068_unit_decision(field,expected,observed,_status(status),score)
    if model_note:
        note=(' '.join(filter(None,[_text(note),model_note])))[:300]
    return {'id':f'f{int(time.time_ns())}-{abs(hash((field,expected,observed)))%99999}',
            'field':_text(field),'expected':_text(expected) or '—','observed':_text(observed) or '—',
            'status':_status(status),'score':round(float(score),1) if isinstance(score,(int,float)) else None,
            'page':page if isinstance(page,int) and page>0 else None,'note':_text(note)[:300],
            'document_id':document_id,'quote':_text(quote)[:380], 'detail': detail if isinstance(detail,dict) else None}

def _from_match(field,expected,matcher,doc_id=None):
    m=matcher or {};ev=(m.get('evidence') or [{}])[0] if isinstance(m.get('evidence'),list) else {}
    return _row(field,expected,m.get('observed') or m.get('actual') or m.get('value'),m.get('status','REVIEW'),
                m.get('score'),ev.get('page') or m.get('page'),m.get('reason') or m.get('method',''),doc_id,ev.get('quote',''))

def _facility_from_general(g):
    address=_text(g.get('alamat_proyek'))
    name=_text(g.get('nama_fasilitas'))
    if not name:
        head=address.split(',')[0].strip()
        if re.search(r'(?i)\b(?:RSUD|RS\.?|rumah\s+sakit|rumkit|klinik)\b',head): name=head
    return name or _text(g.get('instansi'))

def _to_form(app):
    g=app.get('general') or {}; persons=app.get('personnel') or [];tools=app.get('equipment') or []
    personnel=[]
    for p in persons:
        if isinstance(p,dict):
            person=_text(next((p.get(k) for k in ('nama','nama_petugas','name','nama_personel') if p.get(k)),''))
            role=_text(next((p.get(k) for k in ('keahlian_klasifikasi','keahlian','profesi','jabatan','role') if p.get(k)),''))
        else:person,role=_text(p),''
        if person:personnel.append({'name':person,'role':role})
    equipment=[]
    for i,t in enumerate(tools):
        if isinstance(t,dict):equipment.append({'label':f'Peralatan {i+1}',**{k:_text(t.get(k)) for k in FIELDS}})
    return {'facility':_facility_from_general(g),'address':_text(g.get('alamat_proyek')),
            'applicationNumber':_text(g.get('nomor_registrasi')) or None,'personnel':personnel,'equipment':equipment}

def _program(doc,app,ref):
    from src.extraction.program_documents import analyze
    kind=PROG[doc['category']];raw=analyze(str(storage.file_path(doc)),kind,ref)
    rows=[_from_match('Nama Fasilitas',ref['nama_fasilitas'],raw.get('hospital'),doc['id']),
          _from_match('Alamat Fasilitas',ref['alamat_proyek'],raw.get('address'),doc['id'])]
    ap=raw.get('approval') or {};proof=(ap.get('evidence') or [{}])[0]
    rows.append(_row('Lembar Pengesahan','Keberadaan halaman berjudul Lembar Pengesahan',
                     f"PDF halaman {proof.get('page')}" if proof.get('page') else '',ap.get('status','REVIEW'),
                     100 if ap.get('status')=='MATCH' else None,proof.get('page'),
                     'Halaman pengesahan ditemukan; tanda tangan/stempel tetap diperiksa secara visual',doc['id'],proof.get('quote'),
                     {'type':'approval','pages':[x.get('page') for x in ap.get('evidence',[]) if isinstance(x.get('page'),int)],'heading':'Lembar Pengesahan'}))
    if doc['category']=='perawatan':
        maintenance=raw.get('maintenance') or {};secs=maintenance.get('section') or []
        sec=secs[0] if secs else {}
        rows.append(_row('Klausul Uji Kesesuaian','Subbab Uji Kesesuaian','Ditemukan' if sec else '',
                         'MATCH' if sec and sec.get('frequencies') and sec.get('parameters') else 'REVIEW',
                         100 if sec and sec.get('frequencies') and sec.get('parameters') else None,
                         sec.get('page'),
                         'Subbab terbaca lintas halaman; periksa rincian di bawah tabel',doc['id'],
                         detail={'type':'maintenance','pages':sec.get('source_pages') or ([sec['page']] if sec.get('page') else []),
                                 'heading':sec.get('heading') or 'Uji Kesesuaian',
                                 'frequencies':sec.get('frequencies') or [], 'parameters':sec.get('parameters') or []}))
    if doc['category']=='proteksi':
        for p in raw.get('personnel') or []:
            rows.append(_row('Petugas: '+_text(p.get('name')),p.get('name'),p.get('observed'),p.get('status'),p.get('score'),
                             ((p.get('evidence') or [{}])[0]).get('page'),document_id=doc['id']))
    for i,group in enumerate(raw.get('equipment') or [],1):
        for field in group:
            if field.get('field') not in FIELDS:continue
            ev=(field.get('evidence') or [{}])[0]
            rows.append(_row(f"Alat {i}: {field.get('label_override') or FIELDS[field['field']]}",field.get('expected'),field.get('observed'),
                             field.get('status'),field.get('score'),ev.get('page'),field.get('reason') or '',doc['id'],ev.get('quote')))
    return rows

def _supp(doc,app,ref):
    from src.extraction.supplementary_matching_v46 import analyze
    raw=analyze(str(storage.file_path(doc)),SUPP[doc['category']],ref)
    rows=[]
    for x in (raw.get('rows') or []):
        evidence=(x.get('evidence') or [{}])[0]
        page=x.get('page') or evidence.get('page')
        is_approval='pengesahan' in _text(x.get('field')).casefold()
        field_name=_text(x.get('field'))
        status=x.get('status');score=x.get('score')
        # A model suffix is material, never silently accept E7894X as E7894.
        if 'tipe' in field_name.lower() and (x.get('expected') and x.get('observed')):
            from src.matching.import_approval_matcher import compare_field
            kind='tipe_tabung' if 'tabung' in field_name.lower() else 'tipe_unit'
            check=compare_field(kind,x['expected'],x['observed'])
            if check['status']=='MISMATCH':status='MISMATCH';score=check['score']
        # Paparan / kebocoran: compare only equipment fields evidenced in this document.
        # Keep facility and approval checks even when absent: their completeness matters.
        # A literal dash, null or empty OCR reading is not evidence of a mismatch.
        if doc['category'] in ('paparan', 'kebocoran') and re.match(
                r'(?i)^\s*alat\s*\d+\s*:', field_name) and _v055_absent_value(x.get('observed')):
            continue
        rows.append(_row(x.get('field'),x.get('expected'),x.get('observed'),status,score,page,
                         x.get('reason') or '',doc['id'],x.get('quote') or evidence.get('quote'),
                         {'type':'approval','pages':[page] if isinstance(page,int) and page>0 else [],
                          'heading':'Pengesahan Dokumen'} if is_approval else None))
    return rows


def _suitability(doc,app,ref):
    from src.extraction.suitability_test import parse_suitability_test
    from src.matching.suitability_matcher import match_suitability
    parsed=parse_suitability_test(str(storage.file_path(doc)))
    if not app.get('equipment'):return [_row('Data peralatan','Ada peralatan pada formulir','','REVIEW',document_id=doc['id'])]
    # One suitability certificate may describe only one device. Do not fabricate rows for other devices.
    results=[match_suitability(app,parsed,i) for i in range(len(app.get('equipment') or []))]
    statuses={'MATCH':3,'REVIEW':2,'MISMATCH':1,'MISSING':0}
    # Conservative: select strong serial match only, else first device with REVIEW label.
    confirmed=[i for i,r in enumerate(results) if r['unit']['nomor_seri'].get('status')=='MATCH']
    idx=confirmed[0] if len(confirmed)==1 else 0
    result=results[idx];equipment=app['equipment'][idx]
    rows=[_from_match('Nama Fasilitas',result['instansi'].get('expected'),result['instansi'],doc['id']),
          _from_match('Alamat Fasilitas',ref['alamat_proyek'],{**result['alamat'],'observed':parsed.get('alamat')},doc['id'])]
    for section,prefix in [('unit','unit'),('tabung','tabung')]:
        for f,key in [('merk','merk'),('tipe','tipe'),('nomor_seri','nomor_seri')]:
            formkey={'merk':'merk','tipe':'tipe','nomor_seri':'nomor_seri'}[f]+'_'+prefix
            match=result[section][f]
            rows.append(_from_match(f'Alat {idx+1}: {FIELDS.get(formkey,formkey)}',equipment.get(formkey),
                                    {**match,'observed':(parsed.get(section) or {}).get(f)},doc['id']))
    if len(confirmed)!=1 and len(results)>1:
        for row in rows[2:]:
            row.update(status='REVIEW',note='Pemilihan peralatan ambigu; nomor seri unit tidak unik',score=None)
    return rows

def _functional(doc,app,ref):
    from src.extraction.functional_test import parse_functional_test
    from src.matching.functional_test_matcher import match_functional_test
    parsed=parse_functional_test(str(storage.file_path(doc)),include_checkboxes=False)
    matched=match_functional_test(app,parsed)
    idx=matched.get('selected_equipment_index')
    data=matched.get('fields') or {};rows=[]
    labels={'nama_rs':'Nama Fasilitas','alamat':'Alamat Fasilitas','merk_unit':'Merek Unit','tipe_unit':'Tipe Unit','nomor_seri_unit':'Nomor Seri Unit',
            'merk_tabung':'Merek Tabung','tipe_tabung':'Tipe Tabung','nomor_seri_tabung':'No. Seri Insersi Tabung'}
    for key,item in data.items():
        if not isinstance(item,dict):continue
        label=labels.get(key,key)
        if key not in ('nama_rs','alamat'):label=f'Alat {(idx+1) if isinstance(idx,int) else "?"}: {label}'
        rows.append(_row(label,item.get('expected'),item.get('actual'),item.get('status'),item.get('score'),item.get('page'),
                         item.get('reason') or '',doc['id'],item.get('evidence')))
    if not rows:rows.append(_row('Identitas alat','Identitas dari formulir','','REVIEW',document_id=doc['id']))
    return rows

def _evidence_span(raw, target, kind='name'):
    """Return an observed text span, NEVER a form-derived value.

    Conservative longest contiguous word-window search handles OCR line breaks
    and punctuation without hiding disagreement in serial numbers or names.
    """
    from difflib import SequenceMatcher
    clean=lambda v:re.sub(r'\s+',' ',str(v or '')).strip()
    text=clean(raw); expected=clean(target)
    if not expected or not text:return ''
    literal=re.search(re.escape(expected),text,re.I)
    if literal:return text[literal.start():literal.end()]
    words=re.findall(r'[a-z0-9]+',expected.casefold())
    stop={'dr','sp','rad','rumah','sakit','jl','jalan','rt','rw','kel','kec','kab','provinsi','dokter'}
    keys=[w for w in words if len(w)>=3 and w not in stop]
    if not keys:return ''
    options=[]
    for original in str(raw).splitlines():
        line=clean(original)
        if not line or len(line)>240:continue
        tokens=re.findall(r'[a-z0-9]+',line.casefold())
        if not tokens:continue
        overlap=sum(any(SequenceMatcher(None,k,w).ratio()>=.87 for w in tokens) for k in keys)/len(keys)
        if overlap >= (.74 if kind=='name' else .65):
            options.append((overlap,-len(line),line))
    if not options:return ''
    return max(options)[2]


def _role_evidence(raw, expected):
    """Professional title evidence must be present in source, not only candidate metadata."""
    text=str(raw or '')
    expected=_text(expected).casefold()
    patterns=[]
    if any(x in expected for x in ('sp.rad','radiologi','dokter spesialis')):
        patterns=[r'(?i)\bdokter\s+spesialis\s+radiologi\b',r'(?i)\bsp\s*\.?\s*rad\b']
    elif 'radiograf' in expected:
        patterns=[r'(?i)\bradiografer(?:\s+level\s*\d+)?\b',r'(?i)\bradiografi\b']
    elif 'proteksi radiasi' in expected or 'ppr' in expected:
        patterns=[r'(?i)\bpetugas\s+proteksi\s+radiasi\b',r'(?i)\bppr\s+medik(?:\s+tk\.?\s*\d+)?']
    else:
        return _evidence_span(text,expected,'role')
    for pat in patterns:
        m=re.search(pat,text)
        if m:return m.group(0)
    return ''


def _expiry_expected(person, parsed_expiry):
    if isinstance(person,dict):
        for key in ('masa_berlaku_sip','masa_berlaku_sib','masa_berlaku','tanggal_berlaku','expiry_date'):
            if person.get(key):return _text(person[key])
    return 'Masa berlaku izin'


def _format_personnel_rows(parsed, validation, app, doc):
    """Use Streamlit field comparators directly; present the SAME rows."""
    from .parity_personnel import _unified_personnel_table
    dtype=_text(validation.get('document_type') or parsed.get('document_type')).upper()
    if dtype in ('SIP','SIB','SPRINT'):
        original=_unified_personnel_table(validation,dtype,parsed.get('text') or '')
        rows=[]
        for x in original:
            score=x.get('Skor')
            try:score=float(str(score).strip().rstrip('%')) if score not in ('-', '—',None) else None
            except (ValueError,TypeError):score=None
            label=x['Field']
            row=_row(label,x.get('Formulir'),x.get('Dokumen'),x.get('Status'),score,document_id=doc['id'])
            if label=='Pengesahan':
                row['detail']={'type':'approval','pages':[1],'heading':'Pengesahan '+dtype}
                row['note']='Periksa tanda tangan atau stempel pada PDF asli'
            rows.append(row)
        return rows
    if isinstance(validation.get('fields'),list):
        return [_row(x.get('field'),x.get('expected'),x.get('observed'),x.get('status','REVIEW'),
                     x.get('score'),document_id=doc['id']) for x in validation['fields']]
    return [_row('Jenis Dokumen',dtype,'','REVIEW',
                 document_id=doc['id'],note=validation.get('reason') or 'Jenis tidak dikenali')]


def _personnel(doc,app,ref):
    """Same OCR, parser, subtype override and validator used by Streamlit."""
    from src.extraction.personnel_document import ocr_personnel_documents,parse_personnel_documents
    from src.matching.personnel_document_matcher import validate_personnel_documents
    pages=ocr_personnel_documents([{'path':str(storage.file_path(doc)),'name':doc['filename'],'source_id':doc['id']}])
    parsed=parse_personnel_documents(pages)
    kinds={'Surat Izin Praktik (SIP)':'SIP','Surat Izin Bekerja (SIB)':'SIB',
           'Surat Perintah':'SPRINT','Sertifikat Kompetensi':'COMPETENCE',
           'Surat Izin Kerja':'WORK_PERMIT','Surat Keterangan Kerja':'WORK_LETTER',
           'Surat Penunjukan Tugas':'ASSIGNMENT','Evaluasi Dosis':'DOSE',
           'Evaluasi Dosis / Zero Check':'DOSE'}
    subtype=_text(doc.get('subtype'))
    for source in parsed:
        if subtype in kinds:source['document_type']=kinds[subtype]
    matches=validate_personnel_documents(parsed,app)
    results=[]
    for source,match in zip(parsed,matches):
        results.extend(_format_personnel_rows(source,match.get('validation') or {},app,doc))
    return results or [_row('Dokumen Personel','Bukti identitas/masa berlaku','','REVIEW',
                           note='Tidak ada bukti terbaca',document_id=doc['id'])]


def _specification(doc,app,ref):
    from src.extraction.equipment_specification import parse_equipment_specification
    from src.matching.specification_matcher import match_equipment_specification
    parsed=parse_equipment_specification(str(storage.file_path(doc)))
    match=match_equipment_specification(parsed,app.get('equipment') or [])
    idx=match.get('selected_equipment_index')
    candidates=match.get('candidates') or []
    if not isinstance(idx,int) or idx>=len(app.get('equipment') or []):
        return [_row('Pemilihan peralatan','Identitas merek dan tipe unik','',
                     'REVIEW',note=match.get('reason'),document_id=doc['id'])]
    chosen=next((c for c in candidates if c.get('equipment_index')==idx),{})
    rows=[]
    for key,matchkey in [('merk_unit','brand'),('tipe_unit','model')]:
        field=chosen.get(matchkey) or {}
        proof=field.get('evidence') or field.get('actual') or ''
        if isinstance(proof,(dict,list)):proof=str(proof)[:160]
        rows.append(_row(f'Alat {idx+1}: {FIELDS[key]}',
                         (app['equipment'][idx]).get(key),proof,
                         field.get('status','REVIEW'),field.get('score'),chosen.get('best_page'),
                         'Bukti berasal dari halaman spesifikasi',doc['id']))
    return rows

def _v055_absent_value(value):
    """Only empty evidence, never a real conflicting value, is omitted."""
    value = _text(value)
    return not value or value.casefold() in {'—', '-', '–', 'n/a', 'na', 'none', 'null', 'tidak ada', 'tidak ditemukan'}


def _v055_trim_model_spec(expected, observed):
    """Split an *explicit electrical rating* from a unit model; no fuzzy model edits.

    E7894X != E7894. OPTIMA XR200AMX 30KW is model OPTIMA XR200AMX plus 30KW rating.
    Preserve the original OCR text outside the displayed value for evidence traceability.
    """
    if _v055_absent_value(expected) or _v055_absent_value(observed):
        return None
    full = _text(observed)
    # Accept one/two clearly separated electrical specification tokens at the end.
    # Each rating must have a numeric amount and a *unit*, not just a model suffix.
    match = re.fullmatch(
        r'(?is)(?P<model>.+?)\s+(?P<ratings>\d+(?:[.,]\d+)?\s*(?:kW|kVp|kV|mAs|mA|Hz|W|V)'
        r'(?:\s*[/,;]\s*\d+(?:[.,]\d+)?\s*(?:kW|kVp|kV|mAs|mA|Hz|W|V))?)\s*',
        full)
    if not match:
        return None
    from src.matching.import_approval_matcher import compact
    model = match.group('model').strip(' :;,')
    # Exact model characters must be preserved; only punctuation/spacing normalization.
    if compact(expected) != compact(model):
        return None
    return model, match.group('ratings').strip()


def _import(doc,app,ref):
    from src.extraction.import_approval import parse_import_approval
    from src.matching.import_approval_matcher import match_import_approval
    parsed=parse_import_approval(str(storage.file_path(doc)))
    result=match_import_approval(app,parsed);rows=[]
    imported_rows=parsed.get('equipment') or []
    for item in result.get('results',[]):
        cmp=item.get('best_candidate') or {};idx=item.get('form_equipment_index',0)
        source_idx=item.get('import_row_index')
        src=imported_rows[source_idx] if isinstance(source_idx,int) and 0<=source_idx<len(imported_rows) else {}
        # An ordinary Tube S/N is not proof of an *insert* S/N; never compare them.
        # This also prevents fabricated REVIEW percentages for unrelated components.
        insert_explicit=bool(re.search(
            r'(?i)\b(?:insert|insersi|insertion)\b',
            ' '.join(_text(src.get(k)) for k in ('raw_unit','raw_tabung'))))
        for key in FIELDS:
            expected=(item.get('expected') or {}).get(key)
            actual=(item.get('actual') or {}).get(key)
            if _v055_absent_value(actual) or _v055_absent_value(expected):
                continue  # Not comparable, do not show or score.
            if key=='nomor_seri_tabung' and not insert_explicit:
                continue  # 20G225 is Tube S/N, not insert S/N 0F1376.
            f=(cmp.get('fields') or {}).get(key) or {}
            status=f.get('status','REVIEW');score=f.get('score')
            rows.append(_row(f'Alat {idx+1}: {FIELDS[key]}',expected,actual,
                             status,score,item.get('source_page'),f.get('reason',''),document_id=doc['id']))
    return rows or [_row('Peralatan impor pada formulir','Nomor seri unit yang sama','',
                         'REVIEW',note='Tidak ada baris impor dengan bukti identitas yang dapat dibandingkan',document_id=doc['id'])]

def _label_group(documents, app, ref, prefetched_pages=None):
    """EXACT Streamlit v46 semantics: OCR ALL label files, match ONCE.

    In particular, do NOT classify the six fields for a unit-only photo as
    six mismatches. A tube-only photo supplies evidence to the SAME result.
    """
    from src.extraction.label_document_ocr import ocr_label_documents
    from src.matching.guided_label_matcher import auto_match_equipment
    from .parity_label import _label_evidence_view
    equipments = app.get('equipment') or []
    if not equipments:
        return [_row('Label', 'Peralatan pada formulir', '', 'REVIEW')]
    if not documents:
        return []
    # source_id remains unique for independent files; display provenance from
    # selected_source_id in the actual matcher (never guess source from text).
    inputs = [dict(path=str(storage.file_path(d)), name=d['filename'], source_id=d['id'])
              for d in documents]
    # Adaptive OCR: start with mobile models to avoid several-minute full-page
    # quality passes. Escalate only when identities remain insufficient.
    profile_before=os.environ.get('BAPETEN_OCR_PROFILE')
    label_profile=os.environ.get('BAPETEN_LABEL_OCR_PROFILE','fast').lower().strip()
    if label_profile not in {'quality','fast'}:
        raise ValueError('BAPETEN_LABEL_OCR_PROFILE harus quality atau fast')
    try:
        os.environ['BAPETEN_OCR_PROFILE']=label_profile
        pages=(prefetched_pages if prefetched_pages is not None
               else ocr_label_documents(inputs,equipment_list=equipments))
        selected=auto_match_equipment(pages,equipments)
        current=selected.get('match') or selected.get('suggested_match') or {}
        current_matches=(current.get('summary') or {}).get('match',0)
        if (prefetched_pages is None and label_profile=='fast' and
            os.getenv('BAPETEN_LABEL_QUALITY_RESCUE','1')=='1' and
            (selected.get('status')!='AUTO_SELECTED' or current_matches < 6)):
            # Isolated process worker: no state or model leaks between jobs.
            os.environ['BAPETEN_OCR_PROFILE']='quality'
            quality_pages=ocr_label_documents(inputs,equipment_list=equipments)
            quality=auto_match_equipment(quality_pages,equipments)
            quality_result=quality.get('match') or quality.get('suggested_match') or {}
            quality_matches=(quality_result.get('summary') or {}).get('match',0)
            if (quality_matches, quality.get('best_score',0)) > (current_matches,selected.get('best_score',0)):
                selected=quality
    finally:
        if profile_before is None:os.environ.pop('BAPETEN_OCR_PROFILE',None)
        else:os.environ['BAPETEN_OCR_PROFILE']=profile_before
    idx = selected.get('selected_equipment_index')
    if selected.get('status') != 'AUTO_SELECTED' or not isinstance(idx,int) or idx >= len(equipments):
        return [_row('Pemilihan Peralatan Label', 'Satu peralatan yang teridentifikasi', '', 'REVIEW',
                     note='Dokumen label telah digabung, tetapi kandidat alat masih ambigu')]
    result = selected.get('match') or {}
    source_by_name = {d['filename']: d['id'] for d in documents}
    source_by_id = {d['id']: d['id'] for d in documents}
    rows=[]
    fields=[('unit','manufacturer','merk_unit','Merek Unit'),
            ('unit','type','tipe_unit','Tipe Unit'),
            ('unit','serial_number','nomor_seri_unit','Nomor Seri Unit'),
            ('tabung','manufacturer','merk_tabung','Merek Tabung'),
            ('tabung','type','tipe_tabung','Tipe Tabung'),
            ('tabung','serial_number','nomor_seri_tabung','No. Seri Insersi Tabung')]
    for section,key,formkey,display in fields:
        group=result.get(section) or {}
        matched=group.get(key) or {}
        evidence=matched.get('evidence')
        if not isinstance(evidence,str) or not evidence.strip():
            components=matched.get('components') or []
            evidence=' / '.join(str(c.get('evidence') or '') for c in components
                                if isinstance(c,dict) and c.get('evidence'))
        # Streamlit's table uses the true field-level decision as returned by
        # guided_match_label_document. MISSING evidence cannot become MISMATCH.
        status=matched.get('status','REVIEW')
        if not evidence and status=='MATCH':status='REVIEW'
        correction_note=''
        if key=='serial_number' and evidence and status in ('REVIEW','MATCH'):
            from .serial_ocr_v053 import _ambiguity_only, verify_image_serial
            wanted=equipments[idx].get(formkey)
            if _ambiguity_only(wanted,evidence):
                # Different O/0 glyph: only independent image OCR can prove MATCH.
                origin=(source_by_id.get(matched.get('source_id')) or
                        source_by_name.get(matched.get('source_name')) or
                        source_by_id.get(group.get('selected_source_id')) or
                        source_by_name.get(group.get('selected_source_name')))
                target_doc=next((d for d in documents if d['id']==origin),None)
                proof=(verify_image_serial(str(storage.file_path(target_doc)),wanted,evidence,
                                           matched.get('page') or 1) if target_doc else None)
                if proof:
                    evidence=proof['observed'];status='MATCH'
                    correction_note=proof['note']
                else:
                    # Normalized possible reading displayed, but not automatic MATCH.
                    status='REVIEW'; correction_note=f'Kemungkinan 0/O pada OCR: {evidence}; periksa label asli'
        # Do not accept a different alphanumeric model just because fuzzy ratio is 90%+.
        if key=='type' and evidence and status=='MATCH':
            from src.matching.import_approval_matcher import compact as model_code
            expected_model=equipments[idx].get(formkey)
            if expected_model and model_code(evidence).startswith(model_code(expected_model)) \
               and len(model_code(evidence))>len(model_code(expected_model)):
                status='REVIEW';correction_note='Kode tipe memiliki karakter tambahan pada bukti'
        raw_evidence=evidence
        # Optical OCR can include extra electrical capacity after the unit model.
        # Trim ONLY when the complete expected model matches and the suffix has
        # a clear numeric physical unit (e.g. 30KW). Preserve the full raw quote.
        model_spec = (_v055_trim_model_spec(equipments[idx].get(formkey), evidence)
                      if formkey == 'tipe_unit' else None)
        if model_spec:
            evidence = model_spec[0]
            status = 'MATCH'
            correction_note = f"Nilai OCR asli: {raw_evidence}; spesifikasi tambahan: {model_spec[1]}"
        field_name=formkey
        evidence,exact_score=_label_evidence_view(equipments[idx].get(formkey),evidence,status,field_name)
        score=100.0 if model_spec else exact_score
        if score is None:
            score=matched.get('score')
            if score is None and key=='type':
                scores=[x.get('score') for x in matched.get('components') or []
                        if isinstance(x,dict) and isinstance(x.get('score'),(int,float))]
                score=min(scores) if scores else None
        if status=='REVIEW' and (not raw_evidence or correction_note):score=None
        doc_id=(source_by_id.get(matched.get('source_id')) or
                source_by_name.get(matched.get('source_name')) or
                source_by_id.get(group.get('selected_source_id')) or
                source_by_name.get(group.get('selected_source_name')))
        page=matched.get('page') or group.get('selected_page') or matched.get('selected_page')
        rows.append(_row('Alat %d: %s'%(idx+1,display),equipments[idx].get(formkey),evidence,
                         status,score,page,correction_note or matched.get('reason') or '',doc_id,
                         raw_evidence if isinstance(raw_evidence,str) else ''))
    return rows


def _label(doc,app,ref):
    """Compatibility only; worker orchestrator calls _label_group once per set."""
    return _label_group([doc],app,ref)

HANDLERS={**{k:_program for k in PROG},**{k:_supp for k in SUPP},'kesesuaian':_suitability,
          'fungsi':_functional,'personel':_personnel,'spesifikasi':_specification,'impor':_import,'label':_label}


def _v065_document_text_pages(doc):
    """Read existing searchable source only, never launch another OCR job.

    Missing text layer = do not guess / retain original extracted evidence.
    """
    try:
        path=storage.file_path(doc)
        ext=path.suffix.lower()
        if ext=='.pdf':
            import fitz
            with fitz.open(str(path)) as pdf:
                return [(i+1,pdf[i].get_text(sort=True)) for i in range(min(len(pdf),8))]
        if ext=='.docx':
            from docx import Document
            d=Document(str(path))
            fragments=[p.text for p in d.paragraphs]
            for table in d.tables:
                for row in table.rows[:80]:
                    fragments.append(' | '.join(c.text for c in row.cells))
            return [(None,'\n'.join(fragments))]
    except (OSError,ValueError,ImportError):
        return []
    return []


def _v065_identity_postprocess(rows,doc):
    """Replace ONLY with stronger on-document, labeled evidence.

    Every changed value has document page/quote provenance. A new score is
    recalculated for the new observation, never reused from an old candidate.
    """
    targets=[r for r in rows if isinstance(r,dict) and (
        re.search(r'(?i)alamat|tempat\s+praktik',_text(r.get('field'))) or
        re.match(r'(?i)^nama\s+(?:fasilitas|rumah\s+sakit|rs|instansi)\b',_text(r.get('field'))))]
    if not targets:return rows
    pages=_v065_document_text_pages(doc)
    if not pages:return rows
    discovered={'address':candidate_lines(pages,'address'),
                'facility':candidate_lines(pages,'facility')}
    for r in targets:
        kind='address' if re.search(r'(?i)alamat|tempat\s+praktik',_text(r.get('field'))) else 'facility'
        expected=r.get('expected')
        original=r.get('observed')
        candidate=select_candidate(discovered[kind],expected,kind,original)
        if not candidate:continue
        value=candidate['value']
        if kind=='address':
            status,score,note=address_decision(expected,value,r.get('status'),candidate['score'])
        else:
            status,score,note=facility_decision(expected,value,r.get('status'),candidate['score'])
        # Do not promote a missing or weak identity based only on superficial similarity.
        if kind=='address' and status!='MATCH' and r.get('status')=='MATCH':continue
        if kind=='facility' and not value:continue
        r['observed']=value
        r['score']=round(score,1) if isinstance(score,(int,float)) else None
        r['status']=status
        if isinstance(candidate.get('page'),int):r['page']=candidate['page']
        r['quote']=candidate.get('quote','')[:380]
        r['note']=(' '.join(x for x in (note,'Bukti identitas: baris sumber yang ditandai') if x))[:300]
    return rows


def _v060_personnel_title(doc):
    """Only use trusted uploader subtype, never the uploaded filename."""
    if doc.get('category')!='personel':
        return NAMES.get(doc.get('category'),'Dokumen')
    subtype=_text(doc.get('subtype'))
    titles={
        'Surat Izin Praktik (SIP)':'SIP',
        'Surat Izin Bekerja (SIB)':'SIB',
        'Surat Perintah':'Surat Perintah',
        'Sertifikat Kompetensi':'Sertifikat Kompetensi',
        'Surat Izin Kerja':'Surat Izin Kerja',
        'Surat Keterangan Kerja':'Surat Keterangan Kerja',
        'Surat Penunjukan Tugas':'Surat Penunjukan Tugas',
        'Evaluasi Dosis':'Evaluasi Dosis',
        'Evaluasi Dosis / Zero Check':'Evaluasi Dosis / Zero Check',
    }
    title=titles.get(subtype)
    return f'Dokumen Personel - {title}' if title else NAMES['personel']


def _v060_pdf_approval_page(doc):
    """Locate a display page, not signature validity, without additional OCR.

    Prefer an actual heading or signature context over blindly displaying the
    whole PDF. One-page PDF can safely display its only physical page.
    Multi-page scanned PDF without provenance remains unlocated (never guess).
    """
    try:
        from . import storage
        import fitz
        path=storage.file_path(doc)
        if path.suffix.lower()!='.pdf':return None
        with fitz.open(str(path)) as pdf:
            if len(pdf)==1:return 1
            chosen=None
            for i in range(min(len(pdf),35)):
                txt=pdf[i].get_text(sort=True)
                if re.search(r'(?i)\bdaftar\s+isi\b',txt[:1000]):continue
                if re.search(r'(?i)\b(?:lembar|halaman)\s+pengesahan\b',txt):
                    return i+1
                if re.search(r'(?i)\b(?:ditandatangani\s+(?:secara|oleh)|disahkan\s+oleh|menyetujui\s*:)\b',txt):
                    chosen=i+1
            return chosen
    except Exception:
        return None


def _v060_postprocess_evidence(rows,doc):
    """Ensure every approval row can show existing evidence via one-page preview.

    MATCH indicates a textual/detector decision, NOT a verified signature.
    No OCR is repeated, even on scanned docs.
    """
    approval_rows=[r for r in rows if isinstance(r,dict) and
                   re.search(r'(?i)\b(?:pengesahan|tanda\s+tangan)\b',_text(r.get('field')))]
    if not approval_rows:return rows
    needs_page=any(not (r.get('detail') or {}).get('pages') and not r.get('page') for r in approval_rows)
    fallback_page=_v060_pdf_approval_page(doc) if needs_page else None
    for r in approval_rows:
        detail=r.get('detail') if isinstance(r.get('detail'),dict) else {}
        pages=[p for p in (detail.get('pages') or []) if isinstance(p,int) and p>0]
        if not pages:
            p=r.get('page')
            if isinstance(p,int) and p>0:pages=[p]
            elif fallback_page:pages=[fallback_page]
        r['detail']={**detail,'type':'approval','pages':pages,
                     'heading':detail.get('heading') or 'Bukti Pengesahan'}
        if pages and not r.get('page'):r['page']=pages[0]
        if not pages and _text(doc.get('filename')).lower().endswith('.docx'):
            r['note']='Bukti pengesahan dokumen Word perlu diverifikasi secara visual.'
    return rows


def analyze_application(aid,progress):
    """Run independent evidence extractors in parallel; preserve original decisions.

    A single process pool is reused across all simultaneous submissions, so
    workers never oversubscribe per-user. Section order remains upload order.
    """
    import concurrent.futures
    import hashlib
    import json
    from . import performance

    started=time.perf_counter()
    docs=storage.documents(aid)
    forms=[d for d in docs if d['category']=='formulir']
    if len(forms)!=1:raise ValueError('Wajib tepat satu Formulir Permohonan PDF untuk acuan analisis')
    pool=performance.get_pool()
    form_doc=storage.document(forms[0]['id'],aid)
    application,form_seconds=pool.submit(performance.process_form,form_doc).result()
    if not isinstance(application,dict):raise ValueError('Parser formulir tidak mengembalikan data')
    if not (application.get('general') or {}).get('alamat_proyek') and not (application.get('general') or {}).get('instansi'):
        raise ValueError('Identitas fasilitas di formulir tidak terbaca; periksa PDF acuan')
    form=_to_form(application)
    reference={'nama_fasilitas':form['facility'],'instansi':(application.get('general') or {}).get('instansi'),
               'alamat_proyek':form['address'],'personnel':application.get('personnel') or [],
               'equipment':application.get('equipment') or [],'general':application.get('general') or {}}
    r_digest=hashlib.sha256(json.dumps(reference,sort_keys=True,ensure_ascii=False,default=str).encode()).hexdigest()
    source_digest=performance.code_digest()
    sections=[]; warnings=list(application.get('warnings') or []); errors=[]
    supports=[storage.document(d['id'],aid) for d in docs if d['category']!='formulir']
    progress(5,f'Formulir selesai ({form_seconds:.1f}s), menyiapkan {len(supports)} dokumen')
    futures={}; label_futures={}
    label_coordinator=None
    label_parallel_future=None
    label_pass_timings=[]
    label_documents=[d for d in supports if d['category']=='label']
    label_index=next((i for i,d in enumerate(supports) if d['category']=='label'),None)
    label_key=None; label_cached=None
    if label_documents:
        label_key=performance.cache_key_label_group(label_documents,r_digest,source_digest)
        label_cached=performance.get_label_cached(label_documents,label_key)
    if label_documents and label_cached is None:
        from concurrent.futures import ThreadPoolExecutor
        from .label_parallel_v058 import run_label_group
        label_coordinator=ThreadPoolExecutor(max_workers=1,thread_name_prefix='bapeten-label-v058')
        label_parallel_future=label_coordinator.submit(
            run_label_group,pool,label_documents,application.get('equipment') or [],source_digest)
    for index,d in enumerate(supports):
        if d['category']=='label':
            if label_cached is None and index==label_index:
                label_futures[label_parallel_future]=(index,d)
            continue
        key=performance.cache_key(d,r_digest,source_digest)
        fut=pool.submit(performance.process_support,d,application,reference,key)
        futures[fut]=(index,d,[d])
    completed={};timings=[]
    group_ocr=[];group_seconds=0.0;group_failures=[]
    if label_cached is not None:
        completed[label_index]={'id':label_documents[0]['id'],'category':'label',
          'name':NAMES['label']+(' · %d file'%len(label_documents)),
          'document_id':label_documents[0]['id'],
          'source_documents':[{'id':d['id'],'filename':d['filename']} for d in label_documents],
          'rows':label_cached['rows'],'info':'Matching gabungan semua label'}
        timings.append({'category':'label','filename':' + '.join(d['filename'] for d in label_documents),
                        'seconds':label_cached['seconds'],'cache_hit':True})
    total_jobs=len(futures)+len(label_futures)
    label_started=time.perf_counter();label_finished=None
    for number,fut in enumerate(concurrent.futures.as_completed([*futures,*label_futures]),1):
        if fut in label_futures:
            _,d=label_futures[fut]
            try:
                detail=fut.result()
                group_ocr.append((0, detail['pages']))
                group_seconds+=detail['seconds']
                label_pass_timings=detail.get('pass_timings',[])
                label_finished=time.perf_counter()
            except Exception as exc:
                group_failures.append((d,f'{type(exc).__name__}: {str(exc)[:240]}'))
        else:
            index,d,group=futures[fut]
            try:
                detail=fut.result();rows=_v065_identity_postprocess(_v060_postprocess_evidence(detail['rows'],d),d)
                rows=_v069_improve_rows(rows, storage.file_path(d))
                rows=_v070_guard_rows(rows)
                rows=_v071_finalize_identity(rows, storage.file_path(d))
                rows=_v072_improve(rows, storage.file_path(d))
                rows=_v073_improve(rows, storage.file_path(d), d.get('category'), d.get('subtype'), d.get('filename'))
                timings.append({'category':d['category'],
                                'filename':' + '.join(item['filename'] for item in group),
                                'seconds':detail['seconds'],'cache_hit':detail['cached']})
                if not rows:
                    errors.append({'document_id':d['id'],'category':d['category'],
                                   'filename':d['filename'],'error':'Tidak ada bukti ekstraksi yang dapat diverifikasi'})
                else:
                    completed[index]={'id':d['id'],'category':d['category'],
                                  'name':_v060_personnel_title(d) if d['category']=='personel' else NAMES[d['category']]+' · '+d['filename'],
                                  'document_id':d['id'],
                                  'source_documents':[{'id':d['id'],'filename':d['filename']}],
                                  'rows':rows,'info':'Hasil pemeriksaan file ini'}
            except Exception as exc:
                errors.append({'document_id':d['id'],'category':d['category'],'filename':d['filename'],
                               'error':f'{type(exc).__name__}: {str(exc)[:240]}'})
        progress(round(5+85*number/max(1,total_jobs)),
                 f'Pemrosesan {number}/{total_jobs} dokumen selesai')
    for d,problem in group_failures:
        errors.append({'document_id':d['id'],'category':'label','filename':d['filename'],'error':problem})
    if label_documents and label_cached is None and not group_failures:
        try:
            import itertools
            # Deterministic source order, not completion order of parallel workers.
            pages=list(itertools.chain.from_iterable(p for _,p in sorted(group_ocr)))
            detail=performance.finalize_label_group(label_documents,application,reference,label_key,pages)
            rows=detail['rows']
            if rows:
                completed[label_index]={'id':label_documents[0]['id'],'category':'label',
                  'name':NAMES['label']+(' · %d file'%len(label_documents)),
                  'document_id':label_documents[0]['id'],
                  'source_documents':[{'id':d['id'],'filename':d['filename']} for d in label_documents],
                  'rows':rows,'info':'OCR berkualitas paralel; hasil label digabung seperti Streamlit'}
                timings.append({'category':'label','filename':' + '.join(d['filename'] for d in label_documents),
                                'seconds':round((label_finished or time.perf_counter())-label_started,2),
                                'cache_hit':False,'pass_timings':label_pass_timings})
            else:
                errors.append({'document_id':label_documents[0]['id'],'category':'label',
                               'filename':' + '.join(d['filename'] for d in label_documents),
                               'error':'Tidak ada hasil label yang dapat diverifikasi'})
        except Exception as exc:
            errors.append({'document_id':label_documents[0]['id'],'category':'label',
                           'filename':' + '.join(d['filename'] for d in label_documents),
                           'error':f'{type(exc).__name__}: {str(exc)[:240]}'})
    if label_coordinator is not None:
        label_coordinator.shutdown(wait=True)
    sections=[completed[i] for i in sorted(completed)]
    duration=round(time.perf_counter()-started,3)
    return {'application_id':aid,'result_version':'BAPETEN-v052-quality-parallel-label-docx-address',
            'source':'backend','form_reference':form,'matching_sections':sections,
            'errors':errors,'warnings':warnings,'analyzed_documents':len(supports),
            'total_documents':len(docs),'finished_at':time.time(),
            'document_fingerprint':sorted((d['id'],d['sha256']) for d in docs),
            'performance':{'wall_seconds':duration,'form_seconds':form_seconds,
                           'documents':timings,'ocr_processes':performance.settings()[0],
                           'ocr_cpu_threads':performance.settings()[1]}}
