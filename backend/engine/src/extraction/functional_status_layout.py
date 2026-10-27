"""Conservative visual layout OCR and one-to-one label/status matching.

A matched FAIL is an alert; a collection of matched PASS rows is never proof
that the whole document passed. Unchecked option labels are not results.
"""
from __future__ import annotations
import re
from statistics import median
import numpy as np
import cv2
import fitz

STATUS = re.compile(r'^(?:PASS|PASSED|FAIL|FAILED|OK|NG|N/?A|NOT OK|NOT PASS|NOT APPLICABLE|NOT INSTALLED|NOT AVAILABLE)$',re.I)
FAIL = re.compile(r'^(?:FAIL|FAILED|NG|NOT OK|NOT PASS)$',re.I)
EXCEPTION = re.compile(r'^(?:N/?A|NOT APPLICABLE|NOT INSTALLED|NOT AVAILABLE)$',re.I)

def center(box):
    if box is None: return None
    a=np.asarray(box,dtype=float)
    if a.ndim==2 and a.shape[1]>=2:return float(a[:,0].mean()),float(a[:,1].mean())
    if a.ndim==1 and len(a)==4:return float((a[0]+a[2])/2),float((a[1]+a[3])/2)
    return None

def normalize(text): return re.sub(r'[^a-z0-9]+','',str(text).casefold())

def pair_records(records, expected=None):
    """Pair OCR items with results, enforcing uniqueness and axis consistency.

    Each record: {text, x, y, confidence}. OCR orientation may be rotated in
    reading order: try both axes, then require coherent separation and scores.
    """
    tokens=[dict(t) for t in records if str(t.get('text','')).strip()]
    statuses=[t for t in tokens if STATUS.fullmatch(str(t['text']).strip())]
    if expected:
        labels=[]
        for name in expected:
            n=normalize(name)
            matches=[t for t in tokens if n in normalize(t['text']) or (len(normalize(t['text']))>8 and normalize(t['text']) in n)]
            if matches:labels.append((name,max(matches,key=lambda t:len(str(t['text'])))))
    else:
        # Generic labels exclude titles/headers and serial/table metadata.
        labels=[(t['text'],t) for t in tokens if len(str(t['text']))>=12 and not STATUS.fullmatch(str(t['text']).strip())
                and not re.search(r'^(?:status|result|remarks|check item|standard|page|table|section|serial|model|date|subsystem)\b',str(t['text']),re.I)]
    if not labels or not statuses:return {'axis':None,'rows':[],'unpaired_labels':[a for a,_ in labels]}
    solutions=[]
    for axis in ('x','y'):
        cross='y' if axis=='x' else 'x'
        coords=sorted(set(float(t[axis]) for _,t in labels))
        diffs=[b-a for a,b in zip(coords,coords[1:]) if b>a+1]
        spacing=median(diffs) if diffs else 35
        tolerance=min(15,max(5,spacing*.32))
        edges=[]
        for li,(label,t) in enumerate(labels):
            for si,s in enumerate(statuses):
                same=abs(float(t[axis])-float(s[axis]))
                across=abs(float(t[cross])-float(s[cross]))
                if same<=tolerance and across>=12:
                    # Prefer status to right/below label; allow rotated page.
                    edges.append((same+across*.002,li,si))
        used_l=set();used_s=set();paired=[]
        for _,li,si in sorted(edges):
            if li in used_l or si in used_s:continue
            used_l.add(li);used_s.add(si)
            label,record=labels[li];s=statuses[si]
            raw=s['text'].strip().upper()
            status='FAIL' if FAIL.fullmatch(raw) else ('EXCEPTION' if EXCEPTION.fullmatch(raw) else 'PASS')
            paired.append({'item':label,'status':status,'raw_status':raw,'confidence':min(float(record.get('confidence',0)),float(s.get('confidence',0))), 'item_x':float(record[axis]),'status_x':float(s[axis])})
        # prefer more matched entries, lower shared-axis distance, less ambiguity
        solutions.append((len(paired),paired,axis,used_l))
    _,rows,axis,used=max(solutions,key=lambda item:item[0])
    return {'axis':axis,'rows':rows,'unpaired_labels':[name for i,(name,_) in enumerate(labels) if i not in used]}

GLOMEDA_ITEMS=[
    'Patient Touch Leakage Test','System Chasis Leakage Test',
    'Emergency Status Test','Ground Continuity','Door Switch','Xray Warning lamp'
]

def _extract_ocr_records(img):
    try:
        from src.extraction.label_ocr import extract_ocr
        items=extract_ocr(img)
        out=[]
        for item in items:
            p=center(item.get('box'))
            if p is not None:
                out.append({'text':str(item.get('text','')).strip(), 'x':p[0], 'y':p[1], 'confidence':float(item.get('confidence',0) or 0)})
        return out
    except (ModuleNotFoundError, ImportError):
        import pytesseract
        # Group words into lines to recover multiword item labels.
        dat=pytesseract.image_to_data(img,config='--psm 6',output_type=pytesseract.Output.DICT)
        groups={}
        for i,text in enumerate(dat['text']):
            text=text.strip()
            if not text:continue
            key=(dat['block_num'][i],dat['par_num'][i],dat['line_num'][i])
            groups.setdefault(key,[]).append(i)
        out=[]
        for indexes in groups.values():
            left=min(dat['left'][i] for i in indexes);right=max(dat['left'][i]+dat['width'][i] for i in indexes)
            top=min(dat['top'][i] for i in indexes);bottom=max(dat['top'][i]+dat['height'][i] for i in indexes)
            phrase=' '.join(dat['text'][i] for i in indexes)
            conf=[float(dat['conf'][i]) for i in indexes if float(dat['conf'][i])>=0]
            out.append({'text':phrase,'x':(left+right)/2,'y':(top+bottom)/2,'confidence':(sum(conf)/len(conf)/100 if conf else 0)})
        return out

def detect_glomeda_safety(pdf_path):
    """Verified profile for scanned GLOMEDA one-page report.

    The profile is gated by report text. Coordinates are relative to the page
    and matching is independent of fixed text coordinates. Not a universal parser.
    """
    with fitz.open(str(pdf_path)) as doc:
        page=doc[0];r=page.rect
        clip=fitz.Rect(r.width*.065,r.height*.650,r.width*.280,r.height*.795)
        pix=page.get_pixmap(matrix=fitz.Matrix(4,4),clip=clip,colorspace=fitz.csRGB,alpha=False)
    rgb=np.frombuffer(pix.samples,dtype=np.uint8).reshape(pix.height,pix.width,3)
    gray=cv2.cvtColor(rgb,cv2.COLOR_RGB2GRAY)
    th=cv2.threshold(gray,0,255,cv2.THRESH_BINARY+cv2.THRESH_OTSU)[1]
    variants=[('OTSU',th),('CLAHE',cv2.createCLAHE(clipLimit=2.0,tileGridSize=(8,8)).apply(gray)),('ORIGINAL',gray)]
    runs=[]
    for method,arr in variants:
        rec=_extract_ocr_records(cv2.cvtColor(arr,cv2.COLOR_GRAY2BGR))
        matched=pair_records(rec,GLOMEDA_ITEMS)
        rows=matched['rows']
        runs.append({'method':method,'axis':matched['axis'],'rows':rows,'unpaired_labels':matched['unpaired_labels']})
    # A confirmed failure takes precedence even if other image variants miss it.
    # Require both item and status to be recognized and correctly paired.
    best=max(runs,key=lambda x:(sum(r['status']=='FAIL' and r['confidence']>=.4 for r in x['rows']),len(x['rows'])))
    return {'profile':'GLOMEDA_SAFETY','runs':runs,'selected_method':best['method'],'axis':best['axis'],'rows':best['rows'], 'unpaired_labels':best['unpaired_labels']}

def enrich_test_status(path,pages,test_status):
    """Supplement existing line OCR, without replacing it or certifying coverage."""
    from pathlib import Path
    p=Path(path)
    if p.suffix.lower()!='.pdf' or not pages:return test_status
    text='\n'.join(pg['text'] for pg in pages).lower()
    is_glomeda=('safety check' in text and ('glomeda' in text or ('functional test report' in text and 'xr200 amx' in text)))
    if not is_glomeda:return test_status
    try:layout=detect_glomeda_safety(path)
    except Exception as exc:
        test_status.setdefault('layout_warnings',[]).append(f'Layout OCR unavailable: {type(exc).__name__}: {exc}')
        return test_status
    test_status['layout_evidence']=[layout]
    existing={(r['page'],normalize(r['text'])) for r in test_status['rows']}
    for r in layout['rows']:
        key=(1,normalize(r['item']))
        if key in existing:continue
        test_status['rows'].append({'page':1,'text':r['item']+' -> '+r['raw_status'],'item':r['item'], 'status':r['status'], 'method':'LAYOUT_'+layout['selected_method'], 'confidence':r['confidence']})
        existing.add(key)
    test_status['counts']={status:sum(r['status']==status for r in test_status['rows']) for status in ('PASS','FAIL','EXCEPTION')}
    test_status['status']='FAIL_DETECTED' if test_status['counts']['FAIL'] else 'REVIEW'
    test_status['coverage_verified']=False
    # remove previously uncertain entries only for positively mapped named items
    verified={normalize(r['item']) for r in layout['rows']}
    test_status['uncertain_rows']=[u for u in test_status['uncertain_rows'] if normalize(u.get('text','')) not in verified]
    return test_status
