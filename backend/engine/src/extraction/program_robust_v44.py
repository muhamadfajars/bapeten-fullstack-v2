"""Conservative, provenance-first parser for BAPETEN program/technical documents.

v44 extends the installed v43 engine. A difference in a device identifier is
never normalized away. Insertion serial numbers remain a distinct component.
No missing evidence is ever copied from the application form.
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher

from src.extraction import program_robust_v43 as base

FIELD_KEYS = base.FIELD_KEYS
space = base.space
normalize = base.normalize

_META = re.compile(
    r'(?i)\b(?:revisi|rev\.?|tanggal|tgl\.?|halaman|hal\.?|no\.?\s*dok(?:umen)?|'
    r'nomor\s*dokumen|website|telepon|telp\.?|fax|email|berlaku)\s*[:|]?'
)
_FACILITY_PREFIX = re.compile(
    r'(?i)\b(?:rumah\s+sakit\s+(?:umum\s+daerah\s+)?|rumkit\b|rsud\b|rsu\b|rsd\b|'
    r'rs\.?\b|klinik\b|puskesmas\b|hospital\b)'
)
_STOP_NARRATIVE = re.compile(
    r'(?i)\b(?:adalah|berkewajiban|mempunyai|menjamin|dalam|untuk|pelaksanaan|'
    r'memberikan|menetapkan|menerapkan|berdasarkan|melalui|tersebut|kegiatan|'
    r'sebagai|telah|terhadap|pemanfaatan|berikut|dengan|disusun|diatur|'
    r'menggunakan|dilakukan|diagnostik|intervensional)\b'
)


def _clean_facility_line(line):
    """Trim layout metadata while preserving exactly what the source asserts."""
    v = space(str(line)).strip(' \"“”\'`[]')
    v = re.sub(r'(?i)^(?:nama\s+(?:rumah\s+sakit|fasilitas|instansi|pelayanan)|'
               r'nama\s*rs|fasilitas\s*kesehatan)\s*[:|]\s*', '', v)
    m = _FACILITY_PREFIX.search(v)
    if not m:
        return ''
    v = v[m.start():]
    meta = _META.search(v)
    if meta:
        v = v[:meta.start()]
    v = re.split(r'(?i)(?:\b(?:jl\.?|jalan)\s+|\s*[|]\s*(?=\w)|\s{4,})', v)[0]
    v = v.strip(' ,.:;\"“”\'`-')
    if not (4 <= len(v) <= 105) or len(v.split()) > 12:
        return ''
    if _STOP_NARRATIVE.search(v):
        return ''
    # A generic mention such as 'RS' is not enough evidence for a facility.
    if len(_name_key(v)) <= 3 or len(normalize(_FACILITY_PREFIX.sub('', v, count=1))) < 4:
        return ''
    return v


def _name_key(value):
    v = space(value).casefold()
    v = re.sub(r'(?i)\b(?:rumah\s+sakit\s+umum\s+daerah|rsud|rsu|rsd|rumah\s+sakit|rumkit|rs\.)\b', ' rs ', v)
    v = re.sub(r'(?i)\b(?:dr|dokter|prof|ir|h|hj)\.?\s+', ' ', v)
    return normalize(v)


def facility_result(pages, expected, path=None):
    """Choose the strongest *actual* mention, never reconstruct from expected."""
    if not expected:
        return {'status':'REVIEW','score':None,'observed':'','evidence':[],
                'reason':'Tidak ada nama fasilitas pada formulir'}
    candidates=[]
    # Scan first pages and explicit facility labels elsewhere. Header candidates
    # are preferred to text occurrences in body/appendices.
    for p in pages:
        pg=p.get('page') or 9999
        if pg>14:
            continue
        lines=[space(s) for s in (p.get('text') or '').splitlines() if s.strip()]
        for j,line in enumerate(lines):
            label=bool(re.match(r'(?i)^\s*(?:nama\s+(?:rs|rumah\s+sakit|fasilitas|instansi)|fasilitas\s+kesehatan)\s*[:|]',line))
            candidate=_clean_facility_line(line)
            # Facility headers sometimes split the organization type and its
            # distinctive name into two separate PDF baselines.
            if not candidate and _FACILITY_PREFIX.search(line) and j+1<len(lines):
                following=lines[j+1]
                if (len(following)<80 and not _META.search(following) and
                    not re.search(r'(?i)\b(?:jl\.?|jalan|tanggal|alamat)\b',following)):
                    candidate=_clean_facility_line(line+' '+following)
            if not candidate:
                continue
            ea,ob=_name_key(expected),_name_key(candidate)
            score=round(100*SequenceMatcher(None,ea,ob).ratio(),1) if ea and ob else 0
            # Require at least a distinctive shared name token; prevents a
            # generic 'rumah sakit' heading from becoming a match.
            aw=set(re.findall(r'[a-z0-9]{4,}',space(expected).casefold()))-{'sakit','rumah','umum','daerah','rumkit'}
            bw=set(re.findall(r'[a-z0-9]{4,}',candidate.casefold()))
            overlap=bool(aw & bw)
            if not overlap and score<73:
                continue
            header=label or j<15 or (pg<=2 and j<28)
            rank=(1 if header else 0, 1 if overlap else 0, score, -pg, -j)
            candidates.append((rank,candidate,pg,line,score,header))
    if not candidates:
        return {'status':'REVIEW','score':None,'observed':'','evidence':[],
                'reason':'Nama fasilitas tidak ditemukan secara meyakinkan pada teks sumber'}
    candidates.sort(key=lambda x:x[0],reverse=True)
    _,value,page,quote,score,header=candidates[0]
    match=_name_key(expected)==_name_key(value)
    if not match and score>=97:
        # Variations like Zainal/Zainoel are potential spelling differences;
        # not auto-certified in the absence of an official alias registry.
        status='REVIEW'
    else:
        status='MATCH' if match and header else 'REVIEW'
    return {'status':status, 'score':score, 'observed':value,
            'evidence':[{'page':page,'quote':quote,'method':'v44_facility_header'}],
            'method':'v44_facility_header',
            'reason':('Nama fasilitas tampak pada header/label sumber' if status=='MATCH'
                      else 'Periksa penamaan resmi, ejaan, atau sumber nama fasilitas')}


def address_result(pages, expected, path=None):
    """Restore the v43 address verdict: exact street + civic number is MATCH.

    The v44 second-stage anchor requirement incorrectly downgraded full
    street/number matches when a document omitted district/city wording.
    Conflicting street/number/RT/RW still follow v43's conservative rules.
    """
    return base.address_result(pages, expected, path)


def _serial_row(ref, fields):
    """Resolve component identity without hiding a second, conflicting serial."""
    expected=space(ref.get('nomor_seri_tabung'))
    standard=fields.get('nomor_seri_tabung')
    insertion=fields.get('nomor_seri_insersi')
    explicit_ins_ref=ref.get('nomor_seri_insersi')
    if not expected:
        return None
    evidence=[]
    for obs in (standard,insertion):
        if obs:
            evidence.append({'page':obs.get('page'), 'quote':obs.get('quote'), 'value':obs.get('value'),
                             'field_component':obs.get('key'), 'method':obs.get('method')})
    chosen=standard
    status='REVIEW'
    reason='Identitas nomor seri tabung tidak ditemukan pada blok alat'
    label='No. seri tabung'
    if insertion and normalize(insertion['value'])==normalize(expected):
        chosen=insertion
        label='No. seri tabung (nilai pada insersi)'
        if standard and normalize(standard['value'])!=normalize(expected):
            reason=('Nomor seri insersi cocok dengan formulir, tetapi dokumen juga menuliskan '
                    'nomor seri tabung lain. Identitas komponen berbeda; verifikasi ke label fisik.')
        elif explicit_ins_ref and normalize(explicit_ins_ref)==normalize(expected):
            status='MATCH'
            reason='Formulir dan dokumen secara eksplisit menyatakan serial insersi yang sama'
        else:
            reason=('Nomor seri cocok hanya pada komponen insersi. Formulir menulis nomor seri tabung '
                    'tanpa penegasan komponen; perlu konfirmasi apakah referensi menunjuk insersi.')
    elif standard:
        status,score=base._compare_value(expected,standard['value'],'nomor_seri_tabung')
        reason=('Nomor seri tabung dinyatakan berbeda dari formulir' if status=='MISMATCH' else
                'Nomor seri tabung cocok secara eksplisit' if status=='MATCH' else
                'Perbedaan karakter serial memerlukan verifikasi')
    elif insertion:
        chosen=insertion
        label='No. seri tabung (ditemukan hanya insersi)'
        reason='Hanya ditemukan serial insersi yang berbeda; serial housing/tabung tidak diketahui'
    observed=space(chosen['value']) if chosen else ''
    if insertion and standard and normalize(insertion['value'])==normalize(expected) and normalize(standard['value'])!=normalize(expected):
        observed=f"{space(insertion['value'])} [insersi]; {space(standard['value'])} [tabung/housing]"
    score=None if not chosen else base._compare_value(expected,chosen['value'],'nomor_seri_tabung')[1]
    return {'field':'nomor_seri_tabung','expected':expected,'observed':observed,
            'status':status,'score':score,'evidence':evidence,
            'reason':reason,'label_override':label,
            'method':'v44_component_specific_serial',
            'evidence_strength':'explicit_subcomponent' if chosen else 'missing'}


def _better_device_records(path,pages):
    """v43 geometry, plus split repeated machine declarations on the same page."""
    records=base.device_records(path,pages)
    # Keep v43 records when they are valid; its geometry algorithm already
    # handles multi-line tables and OCR-letter spacing in actual documents.
    # For one-page multi-unit statements, detect repeated explicit Data Pesawat
    # sections and parse each section independently with locally clipped pages.
    if not path.lower().endswith('.pdf'):
        return records
    try:
        import fitz
        with fitz.open(path) as doc:
            for p in pages:
                n=p.get('page')
                if not isinstance(n,int):continue
                page=doc[n-1]
                lines=[x for x in page.get_text('blocks') if isinstance(x[4],str)]
                anchors=[]
                for bb in lines:
                    for m in re.finditer(r'(?im)^\s*Data\s+pesawat(?:\s+sinar\s*[-–]?\s*x)?\s*$',bb[4]):
                        anchors.append(bb[1])
                anchors=sorted(set(round(y,1) for y in anchors))
                if len(anchors)<2:continue
                # Split only if there are multiple substantial labeled blocks;
                # do not replace reliable existing records with weaker ones.
                fresh=[]
                for k,y in enumerate(anchors):
                    bottom=anchors[k+1] if k+1<len(anchors) else page.rect.height
                    clip=fitz.Rect(0,y,page.rect.width,bottom)
                    txt=page.get_text(clip=clip,sort=True)
                    cand=base._text_candidates_on_page(txt,n)
                    fields={c['key']:c for c in cand}
                    if len(fields)>=2 and ('tipe_unit' in fields or 'nomor_seri_unit' in fields):
                        fresh.append({'fields':fields,'pages':[n]})
                if len(fresh)>=2:
                    records=[r for r in records if n not in r.get('pages',[])]+fresh
    except Exception:
        # A malformed document must never drop the existing v43 evidence.
        pass
    return records



def _scoped_generic_candidates(scoped_pages):
    """Recognize *explicit* unqualified Merk / Model-Type rows by local section.

    Some hospitals label equipment sections 'Data pesawat'/'Data tabung',
    followed by bare 'Merk:' and 'Model/Type:'. v43 discarded these labels;
    do not guess which component they describe outside those sections.
    """
    found=[]
    for p in scoped_pages:
        raw_lines=(p.get('text') or '').splitlines()
        section=None;distance=999
        for line in raw_lines:
            ln=space(line)
            if not ln: continue
            if re.search(r'(?i)\b(?:data|identitas|spesifikasi)\s+(?:tabung|tube)\b', ln):
                section='tabung';distance=0
            elif re.search(r'(?i)\b(?:data|identitas|spesifikasi)\s+(?:pesawat|unit)(?:\s+sinar[- ]?x)?\b',ln):
                section='unit';distance=0
            elif re.match(r'(?i)^(?:serial|nomor|no\.?)\s*(?:number|seri)\s*(?:insersi|insert|insertion)',ln):
                section='tabung';distance=0
            elif re.match(r'(?i)^(?:bab|lampiran|daftar\s+isi|kesimpulan|tata\s+cara)\b',ln):
                section=None;distance=999
            if section is None or distance>38:
                continue
            distance+=1
            match=re.match(r'(?i)^\s*(merk|merek|brand|pabrikan|model\s*/\s*type|type\s*/\s*model|model|tipe|type)\s*[:|]\s*(\S.{0,98})$',ln)
            if not match:continue
            label=normalize(match.group(1))
            key=('merk_' if label in ('merk','merek','brand','pabrikan') else 'tipe_')+section
            val=space(match.group(2)).strip(' :|-')
            if not val or re.search(r'(?i)^(?:data\s+|revisi|tanggal|nomor\s+dokumen)',val):continue
            found.append({'key':key,'value':val,'page':p.get('page'),
                          'quote':ln[:200], 'method':'section_labeled_generic_v45'})
    return found


def _recover_missing_rows(path,pages,ref,group,selected_record,records):
    """Use the older extractor only for fields lost by v43/44.

    Bound recovery to the selected physical device pages and reject pages
    containing two devices. Never overwrite a field that already has evidence,
    particularly true MISMATCH for model suffixes and serials.
    """
    if not group:return group
    from src.extraction.program_documents import _field_evidence
    if selected_record is not None:
        allowed=set(selected_record.get('pages',[]))
        chosen=[p for p in pages if p.get('page') in allowed]
    else:
        chosen=list(pages)
    # Never use broad fallback on a page assigned to multiple physical records.
    counts={}
    for rec in records:
        for pg in set(rec.get('pages',[])):
            counts[pg]=counts.get(pg,0)+1
    chosen=[p for p in chosen if counts.get(p.get('page'),0)<=1]
    if not chosen:return group
    generic=_scoped_generic_candidates(chosen)
    for row in group:
        if row.get('observed') or row.get('status')!='REVIEW':continue
        key=row.get('field')
        if key not in ('merk_unit','tipe_unit','nomor_seri_unit','merk_tabung','tipe_tabung'):
            continue  # serial insert / tube identity stays subcomponent-specific
        expected=space(ref.get(key))
        if not expected:continue
        options=[c for c in generic if c['key']==key]
        # Require a unique labeled candidate for generic source labels.
        if len({normalize(c['value']) for c in options})==1:
            opt=options[0]
            status,score=base._compare_value(expected,opt['value'],key)
            if status in ('MATCH','MISMATCH'):
                row.update({'status':status,'score':score,'observed':opt['value'],
                            'evidence':[{'page':opt['page'],'quote':opt['quote'],
                                         'value':opt['value'],'method':opt['method']}],
                            'method':'v45_section_generic_recovery','reason':''})
                continue
        # The original v42/v43 program extractor handles more variants of
        # fully qualified labels. Run only inside this uniquely scoped device.
        legacy=_field_evidence(chosen,key,expected)
        if legacy.get('observed') and legacy.get('status') == 'MATCH':
            # Reject broad form-guided matches unless anchored to the field.
            if legacy.get('method')=='form_guided_context_fallback':
                continue
            evidence=legacy.get('evidence') or []
            if not evidence:continue
            row.update({'status':legacy['status'],'score':legacy.get('score'),
                        'observed':legacy['observed'],'evidence':evidence,
                        'method':'v45_legacy_labeled_recovery','reason':''})
    return group

def match_equipment(path,pages,references):
    records=_better_device_records(path,pages)
    # One physical record cannot validate two reference devices.
    ordered=sorted(((base._identity_weight(r,d),ri,di)
                    for ri,r in enumerate(references) for di,d in enumerate(records)),
                   reverse=True)
    assigned={};used=set()
    # Brand-only matches must not arbitrarily connect two physical devices.
    # Tied candidates are insufficient evidence for a 1:1 mapping.
    matrix={(ri,di):base._identity_weight(ref,rec)
            for ri,ref in enumerate(references) for di,rec in enumerate(records)}
    for weight,ri,di in ordered:
        if weight<10 or ri in assigned or di in used:continue
        contenders=[j for j in range(len(records)) if matrix[(ri,j)]==weight]
        rival_refs=[k for k in range(len(references)) if matrix[(k,di)]==weight]
        if len(contenders)>1 or len(rival_refs)>1:
            continue
        assigned[ri]=di;used.add(di)
    out=[]
    for ri,ref in enumerate(references):
        fields=records[assigned[ri]]['fields'] if ri in assigned else {}
        group=[]
        for key in FIELD_KEYS:
            expected=space(ref.get(key))
            if not expected:continue
            if key=='nomor_seri_tabung':
                group.append(_serial_row(ref,fields))
                continue
            obs=fields.get(key)
            if not obs:
                group.append({'field':key,'expected':expected,'observed':'','status':'REVIEW',
                              'score':None,'evidence':[], 'method':'v44_device_block',
                              'reason':'Tidak ditemukan nilai dengan label yang sesuai untuk alat ini'})
                continue
            status,score=base._compare_value(expected,obs['value'],key)
            if obs.get('method')=='document_field_label_inconsistent' and status=='MATCH':
                status='REVIEW'
            group.append({'field':key,'expected':expected,'observed':obs['value'],
                          'status':status,'score':score,
                          'evidence':[{'page':obs['page'],'quote':obs['quote'],
                                       'value':obs['value'],'field_component':obs['key'],
                                       'method':obs['method']}],
                          'method':'v44_device_block',
                          'reason':('Label sumber mengindikasikan nomor seri, sedangkan isinya menyerupai model. '
                                    'Perlu konfirmasi tipe/serial dari dokumen yang otoritatif.'
                                    if obs.get('method')=='document_field_label_inconsistent' else
                                    'Kode model/serial berbeda; suffix dan digit tetap signifikan'
                                    if status=='MISMATCH' and key.startswith(('tipe','nomor_seri')) else '')})
        # For documents with one reference, the legacy extractor is safe only
        # if at most one physical equipment record exists. For multiple refs,
        # scope to its uniquely selected record and never share a page.
        selected_record=records[assigned[ri]] if ri in assigned else None
        if selected_record is not None or (len(references)==1 and len(records)<=1):
            group=_recover_missing_rows(path,pages,ref,group,selected_record,records)
        out.append(group)
    return out


def maintenance_sections(pages, previous):
    """Broader section-heading recognition; only explicit frequencies count."""
    prior=previous or {'toc':[],'section':[]}
    sections=list(prior.get('section') or [])
    if any(x.get('frequencies') and x.get('parameters') for x in sections):
        return prior
    head=re.compile(r'(?i)^\s*(?:(?:bab|bagian)\s+[IVX0-9]+\s*[:.\-]?\s*|'
                    r'(?:[0-9]+\s*[.)]\s*){1,5})?\s*'
                    r'(?:uji\s+(?:kesesuaian|rutin|konstansi)|constancy\s+test|quality\s+control)\b')
    freq=re.compile(r'(?i)\b(?:setiap|per|tiap|berkala|sekali\s+setiap)\s*'
                    r'(?:\d+\s*)?(?:hari|minggu|bulan|tahun)|\b(?:harian|mingguan|bulanan|tahunan)\b')
    for i,p in enumerate(pages):
        txt=p.get('text') or ''
        from src.extraction.program_documents import _is_toc_page
        if _is_toc_page(txt):continue
        lines=txt.splitlines()
        for j,line in enumerate(lines):
            if not head.match(space(line)):continue
            window='\n'.join(lines[j:j+95])
            if i+1<len(pages) and j+70>len(lines):
                window+='\n'+'\n'.join((pages[i+1].get('text') or '').splitlines()[:40])
            frequencies=list(dict.fromkeys(space(m.group()) for m in freq.finditer(window)))[:8]
            parameters=[]
            for raw in window.splitlines()[1:]:
                ln=space(raw)
                if re.match(r'(?i)^(?:[\-•]|\d+[.)])\s*(?:akurasi|kebocoran|kesesuaian|tegangan|arus|kolimasi|waktu|output|reproduks|linear|uji)',ln):
                    parameters.append(ln[:150])
                if len(parameters)>=16:break
            if not any(s.get('page')==p.get('page') and s.get('heading')==space(line) for s in sections):
                sections.append({'page':p.get('page'),'heading':space(line),
                                 'frequencies':frequencies,'parameters':parameters,
                                 'excerpt':space(window[:450]),'method':'v44_maintenance_heading'})
    prior['section']=sections
    prior['section_status']='FOUND' if sections else 'REVIEW'
    return prior
