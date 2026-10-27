"""Conservative field matching compatible with app.py suitability UI."""
import re
from difflib import SequenceMatcher


def _norm(s):
    return re.sub(r'[^a-z0-9]','',str(s or '').casefold())

def _words(s):
    t=str(s or '').casefold()
    t=re.sub(r'\brsud\b','rumah sakit umum daerah',t)
    t=re.sub(r'\brsj\b','rumah sakit jiwa',t)
    t=re.sub(r'\brs\b|\brumkit\b','rumah sakit',t)
    t=re.sub(r'\btk\b','tingkat',t)
    t=re.sub(r'\bjl\b|\bjln\b','jalan',t)
    t=re.sub(r'\bno\b','nomor',t)
    return re.findall(r'[a-z0-9]+',t)

def _score(a,b):
    wa,wb=set(_words(a)),set(_words(b))
    if not wa or not wb:return 0.0
    containment=len(wa&wb)/min(len(wa),len(wb))*100
    similarity=SequenceMatcher(None,' '.join(_words(a)),' '.join(_words(b))).ratio()*100
    return round(max(similarity,containment*.92),1)

def _result(status, score=0.0, reason=None):
    d={'status':status,'score':round(score,2)}
    if reason:d['reason']=reason
    return d

def _street_number(s):
    t=' '.join(_words(s))
    nums=re.findall(r'\b(?:nomor|no)\s*(\d+[a-z]?)\b',t)
    return nums[0] if nums else None

def _facility_from_project(project):
    if not project:return None
    head=str(project).split(',')[0].strip()
    return head if re.search(r'(?i)\b(?:rs\.?|rumah sakit|rumkit|klinik)\b',head) else None

def compare_institution(form_value,suitability_value):
    if not form_value or not suitability_value:return _result('MISSING')
    a,b=_words(form_value),_words(suitability_value)
    aa,bb=set(a),set(b)
    score=_score(form_value,suitability_value)
    # Extra suffix/registry code is fine, but core name must be supported.
    if aa==bb or (min(len(aa),len(bb))>=2 and len(aa&bb)/min(len(aa),len(bb))>=.85):
        return _result('MATCH',max(score,90))
    return _result('REVIEW' if score>=65 else 'MISMATCH',score)

def _address_features(value):
    s = str(value or '').lower()
    s = re.split(r'(?i)\b(?:telp|telepon|fax|phone)\s*[.:]', s)[0]
    s = re.sub(r'(?i)\b(?:rumah\s+sakit|rs\.?|rumkit|klinik)[^,]{0,85},\s*(?=(?:jl|jln|jalan)\b)', '', s)
    s = re.sub(r'(?i)\b(?:jl|jln)\.?', 'jalan', s)
    s = re.sub(r'(?i)\bno\b\.?\s*', 'nomor ', s)
    s = re.sub(r'(?i)\b(?:rt|rw)\s*\.?\s*\d+(?:\s*/\s*\d+)?', ' ', s)
    s = re.sub(r'(?i)\b(?:kp|kampung|kec|kecamatan|kel|kelurahan)\s*[. ]', ' ', s)
    s = re.sub(r'(?i)\b(?:kode\s*pos)\s*[:.]?', ' ', s)
    return s

def _number_from_street(s):
    s=_address_features(s)
    m=re.search(r'(?i)\bjalan\s+.{1,85}?\bnomor\s*(\d+[a-z]?)\b',s)
    return m.group(1) if m else None

def _street_tokens(s):
    s=_address_features(s)
    m=re.search(r'(?i)\bjalan\s+(.+?)(?:\bnomor\b|,|$)',s)
    if not m:return set()
    return set(re.findall(r'[a-z0-9]+', m.group(1))) - {'dr','tni','ad','mayor'}

def compare_address(form_value,suitability_value):
    if not form_value or not suitability_value:return _result('MISSING')
    a,b=_address_features(form_value),_address_features(suitability_value)
    n1,n2=_number_from_street(a),_number_from_street(b)
    street1,street2=_street_tokens(a),_street_tokens(b)
    score=_score(a,b)
    if n1 and n2 and n1!=n2:
        return _result('REVIEW',score,'Nomor bangunan berbeda')
    if street1 and street2:
        overlap=len(street1&street2)/max(1,min(len(street1),len(street2)))
        if overlap >= .75 and n1 and n2 and n1==n2:
            # Score measures verified components, rather than unclean whole text.
            return _result('MATCH',max(90,round(90+10*overlap,1)))
        if overlap>=.75:return _result('REVIEW',max(score,75),'Nomor bangunan belum sama-sama tersedia')
        if overlap < .40:return _result('REVIEW',score,'Nama jalan tampak berbeda')
    if score>=90:return _result('REVIEW',score,'Alamat mirip tetapi komponen inti belum cukup terverifikasi')
    return _result('REVIEW',score,'Verifikasi alamat pada dokumen asli')

def compare_equipment_value(left,right,kind='type'):
    if not left or not right:return _result('MISSING')
    aa,bb=_norm(left),_norm(right)
    if aa==bb:return _result('MATCH',100)
    if kind=='serial':
        return _result('MISMATCH',SequenceMatcher(None,aa,bb).ratio()*100)
    score=_score(left,right)
    if kind=='brand':
        words_left=set(_words(left));words_right=set(_words(right))
        if len(words_left)==1 and words_left<=words_right:return _result('MATCH',100)
    if kind=='type' and len(aa)>=5 and len(bb)>=5 and (aa in bb or bb in aa):
        return _result('MATCH',100)
    return _result('MATCH' if score>=95 else 'REVIEW' if score>=65 else 'MISMATCH',score)

def summarize_suitability_match(result):
    statuses=[result.get('instansi',{}).get('status'),result.get('alamat',{}).get('status')]
    for section in ('unit','tabung'):
        statuses += [result.get(section,{}).get(k,{}).get('status') for k in ('merk','tipe','nomor_seri')]
    # Incomplete evidence cannot support a conclusive mismatch for the document.
    if 'MISSING' in statuses:overall='INCOMPLETE'
    elif 'MISMATCH' in statuses:overall='MISMATCH'
    elif 'REVIEW' in statuses:overall='REVIEW'
    else:overall='VALID'
    return {'status':overall,'total_fields':len(statuses),'match':statuses.count('MATCH'),
            'review':statuses.count('REVIEW'),'mismatch':statuses.count('MISMATCH'),
            'missing':statuses.count('MISSING')}

def match_suitability(application,suitability,equipment_index=0):
    equipment=application.get('equipment') or []
    if not equipment:raise ValueError('Formulir tidak memiliki data peralatan.')
    if not 0<=equipment_index<len(equipment):raise IndexError('equipment_index di luar rentang')
    form=equipment[equipment_index]
    general=application.get('general') or {}
    project=general.get('alamat_proyek')
    facility=_facility_from_project(project)
    # Compare against facility candidate from project, not only corporate applicant.
    candidate_names=[x for x in (facility,general.get('instansi')) if x]
    document_names=[x for x in (suitability.get('nama_fasilitas'),suitability.get('instansi')) if x]
    comparisons=[(candidate,doc_name,compare_institution(candidate,doc_name))
                 for candidate in candidate_names for doc_name in document_names]
    if comparisons:
        # Match status dominates fuzzy similarity. Prefer a facility-to-facility comparison.
        priority={'MATCH':3,'REVIEW':2,'MISMATCH':1,'MISSING':0}
        form_name, doc_name, name_result=max(
            comparisons,key=lambda item:(priority.get(item[2]['status'],0),
                                         item[2]['score'],item[0]==facility))
        name_result=dict(name_result, expected=form_name, actual=doc_name)
    else:
        name_result=_result('MISSING')
        name_result.update(expected=facility or general.get('instansi'),actual=suitability.get('nama_fasilitas') or suitability.get('instansi'))
    unit=suitability.get('unit') or {};tube=suitability.get('tabung') or {}
    result={'instansi':name_result,
      'alamat':compare_address(project,suitability.get('alamat')),
      'unit':{k:compare_equipment_value(form.get(form_field),unit.get(k),kind)
          for k,form_field,kind in [('merk','merk_unit','brand'),('tipe','tipe_unit','type'),('nomor_seri','nomor_seri_unit','serial')]},
      'tabung':{k:compare_equipment_value(form.get(form_field),tube.get(k),kind)
          for k,form_field,kind in [('merk','merk_tabung','brand'),('tipe','tipe_tabung','type'),('nomor_seri','nomor_seri_tabung','serial')]}}
    result['summary']=summarize_suitability_match(result)
    return result
