"""Evidence-bound address and multi-device extraction for program documents.

Avoids assigning one device's fields to another device, or a field label as
its value. Fails closed on ambiguous OCR; keeps original source snippets.
"""
import os
import re
import unicodedata
from difflib import SequenceMatcher

FIELD_KEYS=('merk_unit','tipe_unit','nomor_seri_unit','merk_tabung','tipe_tabung','nomor_seri_tabung')


def normalize(value):
    return re.sub(r'[^a-z0-9]+','',unicodedata.normalize('NFKC',str(value or '')).casefold())


def space(value):
    return re.sub(r'\s+',' ',str(value or '')).strip()


def _clean_company(value):
    value=normalize(value)
    value=re.sub(r'(?:pt|limited|ltd|company|coltd|co)$','',value)
    return value


def _labels(line):
    """Identify field strictly from an explicit label, including spaced glyphs."""
    raw=space(line)
    if ':' in raw:
        raw=raw.split(':',1)[0]
    key=normalize(raw)
    # Do not conflate insertion serial with tube housing serial.
    if ('seri' in key or 'serial' in key) and ('insersi' in key or 'insertion' in key or 'insert' in key):
        return 'nomor_seri_insersi'
    if ('seri' in key or 'serial' in key) and ('tabung' in key or 'tube' in key):
        return 'nomor_seri_tabung'
    if ('seri' in key or 'serial' in key) and ('pesawat' in key or 'unit' in key or 'generator' in key):
        return 'nomor_seri_unit'
    if ('merk' in key or 'merek' in key or 'pabrikan' in key or 'brand' in key) and ('tabung' in key or 'tube' in key):
        return 'merk_tabung'
    if ('merk' in key or 'merek' in key or 'pabrikan' in key or 'brand' in key) and ('pesawat' in key or 'unit' in key or 'generator' in key):
        return 'merk_unit'
    if ('tipe' in key or 'type' in key or 'model' in key) and ('tabung' in key or 'tube' in key):
        return 'tipe_tabung'
    if ('tipe' in key or 'type' in key or 'model' in key) and ('pesawat' in key or 'unit' in key or 'generator' in key):
        return 'tipe_unit'
    return None


def _ocr_compact(value):
    value=space(value).strip(':| -')
    # Excessively letter-spaced strings produced by PDF text extraction.
    # Only compact if the majority of whitespace-separated tokens are 1 char.
    parts=value.split()
    if len(parts)>=5 and sum(len(p)==1 for p in parts)/len(parts)>=0.66:
        value=''.join(parts)
    value=re.sub(r'\s*([/,\-])\s*',r'\1',value)
    return value.strip()


def _prettify_value(value, field):
    v=_ocr_compact(value)
    if field in ('tipe_unit','tipe_tabung','nomor_seri_unit','nomor_seri_tabung','nomor_seri_insersi'):
        # Remove letter spacing in short model codes but not ordinary prose.
        if len(v)<50 and re.search(r'(?:\b\w\s+){3}',v):
            v=re.sub(r'(?<=\w)\s+(?=[\w\-])','',v)
    return v


def _visual_rows(page):
    """Group same-baseline spans, preserving spatial column positions.

    Visual rows are used only for equipment table pages, after page validation.
    """
    pieces=[]
    for block in page.get_text('dict')['blocks']:
        for line in block.get('lines',[]):
            for s in line['spans']:
                if not s.get('text','').strip():continue
                x0,y0,x1,y1=s['bbox']
                pieces.append({'text':s['text'],'x0':x0,'x1':x1,'y':(y0+y1)/2})
    pieces.sort(key=lambda p:(p['y'],p['x0']))
    rows=[]
    for part in pieces:
        group=next((g for g in reversed(rows[-5:]) if abs(g['y']-part['y'])<=6.5),None)
        if group is None:
            group={'y':part['y'],'parts':[]};rows.append(group)
        group['parts'].append(part)
    for group in rows:
        group['parts'].sort(key=lambda p:p['x0'])
        group['text']=' '.join(p['text'] for p in group['parts'])
    return sorted(rows,key=lambda r:r['y'])


def _field_candidates_on_page(page,page_num):
    """Read source lines via label geometry, never adjacent-field similarity."""
    rows=_visual_rows(page)
    out=[]
    for i,row in enumerate(rows):
        parts=row['parts']
        # x<=60% page usually corresponds to label column; the value
        # column starts around 43-67% in known templates. First try ':'
        # delimiter in the entire line, then visual-column split.
        text=row['text']
        colon=text.find(':')
        before=text[:colon] if colon>=0 else text
        after=text[colon+1:] if colon>=0 else ''
        field=_labels(before)
        if field and after.strip():
            val=_prettify_value(after,field)
        else:
            field=None;val=''
            # The left label is often in one or several spans ending at x<250,
            # followed by a value at x260/395. Try every spatial gap.
            for k in range(1,len(parts)):
                left=space(' '.join(x['text'] for x in parts[:k]))
                field=_labels(left)
                if not field:continue
                # Avoid cutting label at a space when the rest is itself label.
                xgap=parts[k]['x0']-parts[k-1]['x1']
                if xgap<12 and parts[k]['text'].strip() not in (':','|'):
                    continue
                val=_prettify_value(' '.join(x['text'] for x in parts[k:]),field)
                break
            # Some PDF rows omit the value or have it vertically shifted;
            # choose a nearby right-column span, but not another field label.
            if field and not val:
                for other in rows[max(0,i-1):i+2]:
                    vals=[p for p in other['parts'] if p['x0']>page.rect.width*0.42]
                    if vals and abs(other['y']-row['y'])<=9:
                        value=' '.join(p['text'] for p in vals)
                        if not _labels(value):
                            val=_prettify_value(value,field);break
        if field and val:
            val=val.strip(':|').strip()
            # A PDF field value can be wrapped onto the next visual line
            # in the same right-hand column. Only brands can span several lines.
            if field.startswith('merk') and i+1<len(rows):
                nxt=rows[i+1]
                if 6 < nxt['y']-row['y']<21 and all(p['x0']>page.rect.width*0.40 for p in nxt['parts']):
                    extra=space(' '.join(x['text'] for x in nxt['parts']))
                    if extra and len(extra)<90 and not _labels(extra):val=space(val+' '+extra)
            if len(val)<110 and normalize(val) and normalize(val) not in ('n', 'x', 'data', 'ket'):
                out.append({'key':field,'value':val,'page':page_num,'quote':space(text)[:200],
                            'method':'pdf_visual_table'})
    return out


def _text_candidates_on_page(text,page_num):
    out=[]
    for raw in (text or '').splitlines():
        if ':' not in raw:continue
        before,after=raw.split(':',1)
        key=_labels(before)
        if not key:continue
        value=_prettify_value(after,key)
        if value and len(value)<110:
            out.append({'key':key,'value':value,'page':page_num,'quote':space(raw)[:200],
                        'method':'explicit_field_label'})
    return out


def device_records(path,pages):
    """Segment physical equipment blocks and preserve their device identity."""
    entries=[]
    doc=None
    if path.lower().endswith('.pdf'):
        import fitz
        doc=fitz.open(path)
    try:
        for p in pages:
            text=p.get('text','')
            # Page anchors from equipment declarations, not mentions in prose.
            has_unit_block=bool(re.search(r'(?i)\bdata\s*pesawat\b|\btabel\s*\d+\.\s*data\s+ruang\s+dan\s+alat',text))
            # For highly spaced OCR, labels may appear as adjacent letters.
            contains_device_fields=bool(re.search(r'(?i)(?:merk|merek|tipe|model|no\.?\s*seri|seripesawat)',text))
            if not (has_unit_block or contains_device_fields):continue
            candidates=_text_candidates_on_page(text,p['page'])
            if doc is not None and isinstance(p['page'],int):
                visual=_field_candidates_on_page(doc[p['page']-1],p['page'])
                # Visual evidence wins when both find the same row label.
                existing={(c['key'],normalize(c['value'])) for c in visual}
                candidates=visual+[c for c in candidates if (c['key'],normalize(c['value'])) not in existing and c['key'] not in {q['key'] for q in visual}]
            if not candidates:continue
            # Bad source templates sometimes put a device *model* under the
            # 'No. Seri pesawat' label. Do not mistake uDR380i for a serial;
            # retain the original incorrect label as evidence, and REVIEW.
            if not any(c['key']=='tipe_unit' for c in candidates):
                for c in candidates:
                    if c['key']=='nomor_seri_unit' and re.match(r'(?i)^(?:uDR|DR[- ]?XD|Optima|Smart)\s*[a-z0-9-]+$',c['value']):
                        c['key']='tipe_unit'
                        c['method']='document_field_label_inconsistent'
                        break
            # Start a new device if document starts a new Data Pesawat block,
            # or if new unit type occurs after the previous unit identity.
            if has_unit_block and any(c['key'] in ('tipe_unit','nomor_seri_unit') for c in candidates):
                entries.append({'fields':{},'pages':[]})
            elif not entries:
                entries.append({'fields':{},'pages':[]})
            current=entries[-1]
            current['pages'].append(p['page'])
            for c in candidates:
                # Ignore repeated same-field metadata across narrative pages.
                current['fields'].setdefault(c['key'],c)
        # Remove unidentified objects.
        return [v for v in entries if len(v['fields'])>=2]
    finally:
        if doc:doc.close()


def _same_brand(expected,observed):
    a=_clean_company(expected);b=_clean_company(observed)
    if not a or not b:return False
    if a==b:return True
    # Short brands such as GE must appear as a whole brand token, never
    # merely as letters inside an unrelated manufacturer's name.
    if len(a)<=3:
        return bool(re.match(r'^'+re.escape(space(expected))+r'(?=$|\W)',space(observed),re.I))
    # Manufacturer prefixes and legal company suffixes are ancillary.
    # A random occurrence of a brand inside another word is not sufficient.
    return (len(a)>=5 and (b.startswith(a) or a.startswith(b) or
            b.startswith('shanghai'+a) or b.startswith('pt'+a)))


def _compare_value(expected,observed,field):
    a,b=normalize(expected),normalize(observed)
    if not a or not b:return 'REVIEW',None
    if field.startswith('merk'):
        if _same_brand(expected,observed):return 'MATCH',100.0
        return 'MISMATCH',round(100*SequenceMatcher(None,a,b).ratio(),1)
    if a==b:return 'MATCH',100.0
    similarity=100*SequenceMatcher(None,a,b).ratio()
    # A different type suffix or serial character is NOT an exact match.
    # High similarity from OCR noise warrants review rather than false success.
    if (a.startswith(b) or b.startswith(a)) and a!=b:
        return 'MISMATCH',round(similarity,1)  # E7894 is not E7894X
    if similarity>=88:return 'REVIEW',round(similarity,1)
    return 'MISMATCH',round(similarity,1)


def _identity_weight(reference,record):
    fields=record['fields']
    w=0.0
    for key,weight in [('tipe_unit',10),('nomor_seri_unit',10),('tipe_tabung',5),('nomor_seri_tabung',5),('merk_unit',1)]:
        observed=fields.get(key,{}).get('value')
        expected=reference.get(key)
        if not observed or not expected:continue
        st,_=_compare_value(expected,observed,key)
        if st=='MATCH':w+=weight
        elif st=='MISMATCH' and key in ('tipe_unit','nomor_seri_unit'):w-=weight
    return w


def match_equipment(path,pages,references):
    records=device_records(path,pages)
    # Match the entire equipment identity to one source block, never reuse a
    # single record to validate two devices, even if the brands are identical.
    selected={}
    unassigned=set(range(len(records)))
    # Prioritize exact unit serial/type assignments first.
    pairs=sorted([(_identity_weight(ref,rec), ri, di)
                  for ri,ref in enumerate(references) for di,rec in enumerate(records)],reverse=True)
    for weight,ri,di in pairs:
        if ri in selected or di not in unassigned:continue
        if weight<=0:continue
        selected[ri]=di;unassigned.remove(di)
    results=[]
    for ri,ref in enumerate(references):
        fields=records[selected[ri]]['fields'] if ri in selected else {}
        rows=[]
        for key in FIELD_KEYS:
            expected=space(ref.get(key))
            if not expected:continue
            obs=fields.get(key)
            # Explicit insertion serial: distinct from tube housing serial.
            # Do not claim the same physical serial identifier by similarity.
            if key=='nomor_seri_tabung' and fields.get('nomor_seri_insersi'):
                ins=fields['nomor_seri_insersi']
                # The form's generic 'tube serial' sometimes refers to the
                # insertion. Only take this branch on exact evidence; never
                # replace a different housing serial with a guessed identity.
                if normalize(ins['value'])==normalize(expected):obs=ins
            if obs:
                st,sc=_compare_value(expected,obs['value'],key)
                if obs.get('method')=='document_field_label_inconsistent' and st=='MATCH':
                    st='REVIEW'  # Source label calls it a serial, not a model.
                evid={'page':obs['page'],'quote':obs['quote'],'value':obs['value'],
                      'field_component':obs['key'],'method':obs['method']}
                rows.append({'field':key,'expected':expected,'observed':obs['value'],
                             'status':st,'score':sc,'evidence':[evid],
                             'label_override':('No. seri insersi tabung' if obs['key']=='nomor_seri_insersi' else None),
                             'method':'device_scoped_table_v43',
                             'reason':('Label sumber menuliskan nomor seri, tetapi nilainya menyerupai model; perlu verifikasi' if obs.get('method')=='document_field_label_inconsistent' else ('Nilai sesuai seri insersi (bukan seri housing)' if obs['key']=='nomor_seri_insersi' else ''))})
            else:
                rows.append({'field':key,'expected':expected,'observed':'','status':'REVIEW',
                             'score':None,'evidence':[],'method':'device_scoped_table_v43',
                             'reason':'Tidak ditemukan nilai berlabel pada blok perangkat yang sama'})
        results.append(rows)
    return results


STREET=r'\b(?:jl\.?|jln\.?|jalan)\s+'
FURNITURE=r'\b(?:revisi\s*[:.]?|tanggal\s*[:.]?|halaman\s*[:.]?|website\s*[:.]?|telp\.?\s*[:.]?|email\s*[:.]?|nomor\s+dokumen\s*[:.]?|\bno\.\s*dok\s*[:.]?)'


def _addr_parts(raw):
    text=space(raw).casefold()
    text=re.sub(r'\((?:imat|alias)[^)]{0,60}\)', ' ', text)
    text=re.sub(FURNITURE+r'.*$', '',text,flags=re.I)
    # Never treat a 'No.' or 'RT' inside unrelated metadata as a street number.
    street=re.search(STREET+r'(.+?)(?=\b(?:no\.?\s*\d|nomor\s*\d|rt\.?\s*\d|rw\.?\s*\d|kel\.?\b|kelurahan\b|kec\.?\b|kecamatan\b|kota\b|kab\.?\b|kabupaten\b|provinsi\b|$))',text,re.I)
    st=street.group(1).strip(' ,.-') if street else ''
    st=re.sub(r'\b(?:dr\.?|tni|ad)\b','',st)
    st=normalize(st)
    no=re.search(r'\b(?:no\.?|nomor)\s*(\d+[a-z]?)\b',text)
    rt=re.search(r'\brt\.?\s*(\d{1,3})\s*(?:/\s*(?:rw\.?\s*)?(\d{1,3})|rw\.?\s*(\d{1,3}))?',text)
    rw=re.search(r'\brw\.?\s*(\d{1,3})',text)
    district=re.search(r'\b(?:kecamatan\b|kec\.\s*)\s*([a-z ]+?)(?=\b(?:kabupaten|kab\.|kota|provinsi|telp|revisi|halaman)\b|[,;.]|$)',text)
    reg=re.search(r'\b(?:kota\b|kabupaten\b|kab\.\s*)\s*([a-z ]+?)(?=\b(?:provinsi|jawa|kalimantan|riau|aceh|kode|telp|revisi)\b|[,;.]|$)',text)
    return dict(street=st,number=no.group(1).lstrip('0') if no else '',
                rt=rt.group(1).lstrip('0') if rt else '',
                rw=((rt.group(2) or rt.group(3) or '') if rt else (rw.group(1) if rw else '')).lstrip('0'),
                district=normalize(district.group(1)) if district else '',
                region=normalize(reg.group(1)) if reg else '')


def _short_clean_address(value):
    value=space(value)
    value=re.sub(FURNITURE+r'.*$', '',value,flags=re.I)
    value=re.sub(r'(?i)\bAlamat\s*:\s*(?=(?:tengah|utara|selatan|barat|timur)\b)', ' ',value)
    return space(value).strip(' ,.:;-')


def _address_compare(expected, observed):
    a,b=_addr_parts(expected),_addr_parts(observed)
    used={}
    for field in ('street','number','rt','rw','district','region'):
        if a[field] and b[field]:
            if field=='street':
                similarity=SequenceMatcher(None,a[field],b[field]).ratio()
                used[field]=round(100*similarity,1)
            else:used[field]=100.0 if a[field]==b[field] else 0.0
    if not used or not a['street'] or not b['street']:
        return ('REVIEW',None,used)
    weights={'street':5,'number':6,'rt':4,'rw':4,'district':2,'region':2}
    score=round(sum(v*weights[k] for k,v in used.items())/sum(weights[k] for k in used),1)
    # Conflicting civic number/RT/RW are a verifiable conflict.
    if any(used.get(k)==0 for k in ('number','rt','rw')):
        return 'MISMATCH',score,used
    if used['street']<85:return 'REVIEW',score,used
    # One street alone cannot identify a unique facility. A provisional
    # score must not imply 100% certainty without a precise civic locator.
    if any(k in used for k in ('number','rt','rw')) and all(used[k]>=96 for k in used):
        return 'MATCH',score,used
    return 'REVIEW',min(score,89.0),used


def _spatial_header_addresses(path, limit=10):
    """Recover multi-line hospital headers without reading neighboring date cells."""
    if not path.lower().endswith('.pdf'):
        return []
    import fitz
    found=[]
    with fitz.open(path) as doc:
        for pi in range(min(limit,len(doc))):
            page=doc[pi]
            header=[]
            for block in page.get_text('dict')['blocks']:
                for line in block.get('lines',[]):
                    if line['bbox'][1] > min(205, page.rect.height*0.28):continue
                    text=space(' '.join(s['text'] for s in line['spans']))
                    if text:
                        header.append((line['bbox'][1],line['bbox'][0],text))
            header.sort()
            for i,(y,x,text) in enumerate(header):
                mat=re.search(STREET+r'[a-z]',text,re.I)
                if not mat or y<26:continue
                # Only use a constrained header block; on full-page narratives
                # a street mention is not necessarily the facility address.
                preceding=' '.join(t for yy,xx,t in header[max(0,i-7):i]).casefold()
                if not re.search(r'rumah\s+sakit|\brs\b|klinik|program|sistem|teknis|radiologi', preceding):
                    continue
                fragments=[text[mat.start():]]
                last_y=y
                for yy,xx,t in header[i+1:i+5]:
                    if yy-last_y>20:break
                    if abs(xx-x)>95:continue
                    if not re.match(r'(?i)^(?:kecamatan|kec\.|kabupaten|kab\.|kota|kelurahan|kel\.|provinsi|jawa|kalimantan|riau|aceh)\b',t):
                        break
                    fragments.append(t);last_y=yy
                result=_short_clean_address(' '.join(fragments))
                if result:found.append((pi+1,result))
                break
    return found


def address_result(pages,expected,path=None):
    from src.extraction.program_documents import _address_lines, _is_toc_page
    if not expected:return {'status':'REVIEW','score':None,'observed':'','evidence':[]}
    cands=[]
    if path:
        for page,value in _spatial_header_addresses(path):
            status,score,comps=_address_compare(expected,value)
            rank=(status=='MATCH',len(comps),score or 0,-page)
            cands.append((rank,status,score,value,comps,page))
    for p in pages:
        if _is_toc_page(p['text']):continue
        lines=p['text'].splitlines()
        for i,line in enumerate(lines):
            if not re.search(STREET+r'[a-z]',line,re.I):continue
            value=_short_clean_address(_address_lines(lines,i))
            if not value:continue
            status,score,comps=_address_compare(expected,value)
            # Prefer initial pages, which typically carry authoritatively labeled
            # facility headers; do not select a misleading partial address.
            rank=(status=='MATCH',len(comps),score or 0, -p['page'])
            cands.append((rank,status,score,value,comps,p['page']))
    if not cands:
        return {'status':'REVIEW','score':None,'observed':'','evidence':[], 'reason':'Alamat fasilitas tidak ditemukan'}
    cands.sort(key=lambda x:x[0],reverse=True)
    _,status,score,val,comps,page=cands[0]
    return {'status':status,'score':score,'observed':val,
            'evidence':[{'page':page,'quote':val,'method':'v43_address_components','components':comps}],
            'compared_components':list(comps),'method':'v43_address_components'}
