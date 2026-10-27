"""Conservative comparison of functional/acceptance report with application form.
Selects unit only on sufficiently distinctive evidence; no fake MATCH on missing fields.
"""
import re
import unicodedata
from rapidfuzz import fuzz

KEYS = ('nama_rs','alamat','tipe_unit','nomor_seri_unit','tipe_tabung','nomor_seri_tabung')

def norm(value):
    value=unicodedata.normalize('NFKC',str(value or '')).casefold()
    value=re.sub(r'[^a-z0-9]+',' ',value)
    return ' '.join(value.split())

def compact(value):
    return norm(value).replace(' ','')

def norm_name(value):
    value=norm(value)
    substitutions={r'\brumkit\b':'rumah sakit',r'\brsud\b':'rumah sakit umum daerah',
                   r'\brs\b':'rumah sakit',r'\btk\b':'tingkat'}
    for a,b in substitutions.items():value=re.sub(a,b,value)
    value=re.sub(r'\b\d+(?:\s+\d+){2,}\b',' ',value)
    return ' '.join(value.split())

def norm_address(value):
    value=norm(value)
    value=re.sub(r'\b(?:jl|jln)\b','jalan',value)
    value=re.sub(r'\bno\b','nomor',value)
    return value

def _facility_core(value):
    """Remove a *trailing* geographic descriptor, not meaningful facility words."""
    value = norm_name(value)
    value = re.sub(r'\s+(?:kabupaten|kab|kota)\s+[a-z ]+$', '', value).strip()
    return value


def _facility_status(expected, actual):
    a, b = _facility_core(expected), _facility_core(actual)
    if not a or not b:
        return 0.0, 'MISSING'
    if a == b:
        return 100.0, 'MATCH'
    score = round(fuzz.token_sort_ratio(a, b), 2)
    return score, ('MATCH' if score >= 90 else 'REVIEW' if score >= 70 else 'MISMATCH')


def _street_location(value):
    """Extract the address portion and discard optional phone/fax metadata."""
    value = re.split(r'(?i)\b(?:telp|telepon|telephone|phone|fax)\b', str(value or ''))[0]
    m = re.search(r'(?i)\b(?:jl\.?|jln\.?|jalan)\s+', value)
    if m:
        value = value[m.start():]
    value = norm_address(value)
    value = re.sub(r'\b(?:kab|kabupaten)\b', 'kabupaten', value)
    value = re.sub(r'\b(?:kec|kecamatan)\b', 'kecamatan', value)
    return value.strip()


def _address_status(expected, actual):
    a, b = _street_location(expected), _street_location(actual)
    if not a or not b:
        return 0.0, 'MISSING'
    score = round(fuzz.token_set_ratio(a, b), 2)
    # Explicitly conflicting street numbers must stay for human review,
    # even if the rest of the address looks similar.
    if _address_conflict(expected, actual):
        return score, 'REVIEW'
    # A MATCH requires shared street information, not merely same city.
    if a.startswith('jalan') and b.startswith('jalan') and score >= 90:
        return score, 'MATCH'
    return score, ('REVIEW' if score >= 70 else 'MISMATCH')


def _address_conflict(expected, actual):
    """Different explicit house numbers: high similarity is not enough for MATCH."""
    street_no = re.compile(r'(?i)\b(?:no\.?|nomor)\s*(\d{1,5}[a-z]?)\b')
    expected_numbers = set(x.casefold() for x in street_no.findall(str(expected or '')))
    actual_numbers = set(x.casefold() for x in street_no.findall(str(actual or '')))
    return bool(expected_numbers and actual_numbers and expected_numbers.isdisjoint(actual_numbers))

def _comparator(field,expected,actual):
    if field=='nama_rs':
        return _facility_status(expected, actual)
    if field=='alamat':
        return _address_status(expected, actual)
    a,b=compact(expected),compact(actual)
    if not a or not b:return 0.,'MISSING'
    if a==b:return 100.,'MATCH'
    score=round(fuzz.ratio(a,b),2)
    if 'nomor_seri' in field:
        # OCR O/0, I/1 ambiguity can only be REVIEW, not exact match.
        conf=lambda s:s.translate(str.maketrans({'o':'0','i':'1','l':'1','s':'5','b':'8'}))
        if conf(a)==conf(b):return score,'REVIEW'
        return score,'MISMATCH'
    if score>=90:return score,'REVIEW'
    return score,'MISMATCH'

def _compare_candidates(field,expected,items):
    if not expected or not items:return {'status':'MISSING','score':None,'expected':expected,'actual':None,'page':None,'evidence':None}
    ranked=[]
    for item in items:
        score,status=_comparator(field,expected,item['value'])
        ranked.append(({'MATCH':3,'REVIEW':2,'MISMATCH':1,'MISSING':0}[status],score,status,item))
    ranked.sort(key=lambda x:(x[0],x[1]),reverse=True)
    _,score,status,best=ranked[0]
    return {'status':status,'score':score,'expected':expected,'actual':best['value'],'page':best['page'],'evidence':best['evidence'],'component':best.get('component')}

def _model_aliases(value):
    """Form compound model labels: outer model and parenthesized trade name."""
    raw = str(value or '')
    inner = re.findall(r'\(([^()]+)\)', raw)
    outer = re.sub(r'\([^()]*\)', ' ', raw).strip()
    return [v for v in [outer, *inner] if compact(v)]


def _type_alias_match(expected_alias, actual):
    """Exact alias or a distinctive model code followed by configuration text.

    Never use arbitrary token-overlap / fuzzy substring to assert a MATCH.
    """
    a, b = compact(expected_alias), compact(actual)
    if not a or not b:
        return False, None
    if a == b and len(a) >= 6:
        return True, 'EXACT_ALIAS'
    # E.g. DR-XD 1000 vs DR-XD1000 MBL WIN10 E.
    if len(a) >= 8 and any(ch.isdigit() for ch in a) and b.startswith(a) and len(b) > len(a):
        return True, 'MODEL_CODE_PREFIX'
    return False, None


def _compare_type_candidates(expected, items):
    """Require corroborating evidence for both parts of a compound model name.

    Single partial alias remains REVIEW even if it is an exact alias; a model
    name consisting of just one phrase retains the original comparator logic.
    """
    result = _compare_candidates('tipe_unit', expected, items)
    aliases = _model_aliases(expected)
    if len(aliases) < 2 or not items:
        return result

    supports = []
    for alias in aliases:
        matched = []
        for item in items:
            ok, method = _type_alias_match(alias, item.get('value'))
            if ok:
                matched.append((item, method))
        if matched:
            # Prefer an exact label rather than a configuration-code prefix.
            matched.sort(key=lambda pair: pair[1] != 'EXACT_ALIAS')
            item, method = matched[0]
            supports.append({'form_alias': alias, 'value': item['value'],
                             'page': item.get('page'), 'evidence': item.get('evidence'),
                             'method': method})

    if len(supports) == len(aliases):
        primary = supports[0]
        return {'status': 'MATCH', 'score': 100.0, 'expected': expected,
                'actual': primary['value'], 'page': primary['page'],
                'evidence': primary['evidence'], 'component': None,
                'match_method': 'COMPOUND_MODEL_CORROBORATED',
                'supporting_candidates': supports}
    if supports:
        primary = supports[0]
        return {'status': 'REVIEW', 'score': None, 'expected': expected,
                'actual': primary['value'], 'page': primary['page'],
                'evidence': primary['evidence'], 'component': None,
                'match_method': 'PARTIAL_MODEL_ALIAS',
                'supporting_candidates': supports}
    return result


def _compare_simple_model(expected, items, confirmed_unit_serial):
    """Allow optional alphabetic product-family prefix only with same unit serial.

    E.g. Optima XR200AMX / XR200AMX, Smart4000 / Alerio Smart4000.
    This is not a substring or generic fuzzy-match rule.
    """
    initial = _compare_candidates('tipe_unit', expected, items)
    if initial['status'] == 'MATCH' or not expected or not items:
        return initial
    matches = []
    a_tokens = norm(expected).split()
    for item in items:
        b_tokens = norm(item.get('value')).split()
        for longer, shorter in ((a_tokens, b_tokens), (b_tokens, a_tokens)):
            for n in range(1, min(3, len(longer)-1) + 1):
                extra = longer[:n]
                if not all(x.isalpha() and len(x) >= 3 for x in extra):
                    continue
                model = ''.join(shorter)
                if (''.join(longer[n:]) == model and len(model) >= 7
                        and any(c.isdigit() for c in model)
                        and len(''.join(extra)) <= 24):
                    matches.append(item)
                    break
            else:
                continue
            break
    if not matches:
        return initial
    best = matches[0]
    return {'status': 'MATCH' if confirmed_unit_serial else 'REVIEW',
            'score': 100.0 if confirmed_unit_serial else initial.get('score'),
            'expected': expected, 'actual': best.get('value'),
            'page': best.get('page'), 'evidence': best.get('evidence'),
            'component': best.get('component'),
            'match_method': 'MODEL_FAMILY_PREFIX_WITH_SERIAL' if confirmed_unit_serial else 'MODEL_FAMILY_PREFIX_UNCONFIRMED'}


def _facility_from_project_address(address):
    """Only extract explicit facility prefix preceding street in project address.

    Do not treat applicant/badan hukum as the facility's legal name.
    """
    raw = str(address or '').strip()
    parts = re.split(r'(?i),?\s+\b(?:jl\.?|jln\.?|jalan)\s+', raw, maxsplit=1)
    if len(parts) < 2:
        return None
    prefix = parts[0].strip(' ,.;')
    if len(prefix) < 5 or not re.search(r'(?i)\b(?:rs|rsud|rumah sakit|rumkit|klinik|hospital)\b', prefix):
        return None
    return prefix


def _compare_facility(general, items):
    applicant = general.get('instansi')
    project = general.get('alamat_proyek')
    facility = _facility_from_project_address(project)
    if facility:
        result = _compare_candidates('nama_rs', facility, items)
        result['comparison_basis'] = 'FACILITY_FROM_PROJECT_ADDRESS'
        result['applicant_name'] = applicant
        # Sometimes project prefix gives extra district designation; do not
        # upgrade fuzzy REVIEW to MATCH just because portions overlap.
        return result
    result = _compare_candidates('nama_rs', applicant, items)
    result['comparison_basis'] = 'APPLICANT_NAME_FALLBACK'
    return result


def _strong_unit_cue(fields):
    return fields['nomor_seri_unit']['status']=='MATCH'

def match_functional_test(application, report):
    """application: parse_application() output. report: parse_functional_test() output.
    Only one form unit selected when unique exact unit serial, or unique unit
    model + matched tube serial. A type-only guess remains REVIEW.
    """
    form_general=application.get('general') or {}
    equipments=application.get('equipment') or []
    evidence=report.get('candidates') or {}
    context={
      'nama_rs':_compare_facility(form_general,evidence.get('nama_rs',[])),
      'alamat':_compare_candidates('alamat',form_general.get('alamat_proyek'),evidence.get('alamat',[]))}
    options=[]
    for index,equip in enumerate(equipments):
        fields={}
        for field in ('tipe_unit','nomor_seri_unit','tipe_tabung','nomor_seri_tabung'):
            items=evidence.get(field,[])
            fields[field]=(_compare_type_candidates(equip.get(field),items) if field=='tipe_unit'
                           else _compare_candidates(field,equip.get(field),items))
        fields['tipe_unit'] = _compare_simple_model(equip.get('tipe_unit'), evidence.get('tipe_unit', []), fields['nomor_seri_unit']['status'] == 'MATCH') if fields['tipe_unit']['status'] != 'MATCH' else fields['tipe_unit']
        # housing/insert are separately retained and disclosed
        exact_serial=fields['nomor_seri_unit']['status']=='MATCH'
        tube_exact=fields['nomor_seri_tabung']['status']=='MATCH'
        type_exact=fields['tipe_unit']['status']=='MATCH'
        pts=8*exact_serial + 3*tube_exact + 2*type_exact + (fields['tipe_tabung']['status']=='MATCH')
        options.append({'equipment_index':index,'score':pts,'strong_serial_match':exact_serial,'fields':fields})
    options.sort(key=lambda x:x['score'],reverse=True)
    selected=None; selection_status='REVIEW'; reason='Tidak ada pasangan peralatan unik yang dapat dipastikan.'
    serial_matches=[x for x in options if x['strong_serial_match']]
    if len(serial_matches)==1:
        selected=serial_matches[0]
        selection_status='MATCH'
        reason='Nomor seri unit cocok secara unik dengan Formulir.'
    elif len(serial_matches)>1:
        reason='Nomor seri unit ada pada lebih dari satu peralatan Formulir.'
    elif options:
        corroborated=[x for x in options if x['fields']['tipe_unit']['status']=='MATCH' and x['fields']['nomor_seri_tabung']['status']=='MATCH']
        if len(corroborated)==1 and not evidence.get('nomor_seri_unit'):
            selected=corroborated[0]
            selection_status='REVIEW'
            reason='Model unit dan serial tabung cocok, tetapi nomor seri unit tidak tersedia.'
        elif len(options)==1 and options[0]['fields']['tipe_unit']['status']=='MATCH':
            selected=options[0]
            selection_status='REVIEW'
            reason='Satu kandidat berdasarkan tipe unit saja; perlu konfirmasi identitas.'
    if selected:
        visible={k:v for k,v in {**context,**selected['fields']}.items() if v.get('actual') is not None}
        mismatches=[k for k,v in visible.items() if v['status']=='MISMATCH']
        reviews=[k for k,v in visible.items() if v['status']=='REVIEW']
        if mismatches:
            decision='REVIEW'  # potential component names or document inconsistencies
            reason+=' Terdapat perbedaan field: '+', '.join(mismatches)+'.'
        elif reviews:decision='REVIEW'
        else:decision=selection_status
    else:
        visible={k:v for k,v in context.items() if v.get('actual') is not None}
        decision='REVIEW'
    check_status=(report.get('test_status') or {}).get('status','REVIEW')
    overall_status='FAILED' if check_status=='FAIL_DETECTED' else 'REVIEW'
    return {'selected_equipment_index':selected['equipment_index'] if selected else None,
            'status':overall_status,'identity_status':decision,'selection_status':selection_status,'reason':reason,
            'fields':visible,'test_status':report.get('test_status',{}),
            'candidates_summary':[{'equipment_index':x['equipment_index'],'selection_score':x['score'],'exact_unit_serial':x['strong_serial_match']} for x in options[:5]]}
