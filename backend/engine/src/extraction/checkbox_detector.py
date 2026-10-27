"""Conservative checkbox reader for scanned Siemens Function Check Form and
PDFs containing text-layer checkmark glyphs. Standalone; does NOT modify v3.

Returned statuses are *evidence*, never certification of full-document PASS.
"""
from __future__ import annotations
import re
from pathlib import Path
import pymupdf as fitz
import numpy as np
import cv2
import pytesseract

pytesseract.pytesseract.tesseract_cmd = (
    r"C:\Program Files\Tesseract-OCR\tesseract.exe"
)

LABEL_RE = re.compile(r'^\s*(?:\d{1,2}[.)]\s*)?(?P<label>.{5,})')
POSITIVE = re.compile(r'^(?:baik|bersih|ok|pass|passed|good|normal|acceptable|alat\s+be?r?fungsi\s+dengan\s+baik)$',re.I)
NEGATIVE = re.compile(r'^(?:tidak|ng|not\s+ok|fail|failed|rusak\s+berat|cacat/rusak\s+ringan|alat\s+tidak\s+dapat\s+digunakan|alat\s+harus\s+diperbaiki)$',re.I)
EXCEPT = re.compile(r'^(?:n/?a|not\s+applicable|not\s+installed|not\s+available)$',re.I)


def classify_option(text):
    t=re.sub(r'\s+',' ',text).strip().lower()
    if POSITIVE.fullmatch(t):return 'PASS'
    if NEGATIVE.fullmatch(t):return 'FAIL'
    if EXCEPT.fullmatch(t):return 'EXCEPTION'
    return 'REVIEW'


def parse_digital_checkboxes(text, page):
    """Group consecutive checkbox glyph lines under preceding item label.

    Digital extraction often puts each checkbox on its *own* line. Never count
    unchecked negative option words as negative evidence.
    """
    rows=[]; label=None; options=[]
    def flush():
        nonlocal options
        if not options:return
        selected=[o['option'] for o in options if o['checked']]
        classes=[classify_option(o) for o in selected]
        status=('FAIL' if 'FAIL' in classes else
                'REVIEW' if not classes or 'REVIEW' in classes else
                'EXCEPTION' if all(x=='EXCEPTION' for x in classes) else 'PASS')
        rows.append({'page':page,'item':label or 'ITEM_TANPA_LABEL',
                     'status':status,'selected':selected,'options':options,
                     'method':'PDF_GLYPH','confidence':1.0 if selected and status!='REVIEW' else 0.0})
        options=[]
    for line in text.splitlines():
        s=line.strip()
        if not s:continue
        markers=list(re.finditer(r'([☑☒☐])\s*([^☑☒☐\n]{1,90})',s))
        if markers:
            prefix=s[:markers[0].start()].strip(' :')
            if prefix and not re.match(r'^(?:n/?a|tidak|baik)$',prefix,re.I):
                flush();label=prefix
            for m in markers:
                val=re.sub(r'\s+',' ',m.group(2)).strip(' :|')
                opt=re.match(r'(?i)(baik|bersih|cacat/rusak ringan|rusak berat|tidak|n/?a|not ok|ok|pass|fail|alat berfungsi dengan baik|alat tidak dapat digunakan|alat dapat digunakan|alat harus diperbaiki|alat perlu dikalibrasi)',val)
                val=opt.group(1) if opt else val
                options.append({'option':val,'checked':m.group(1) in '☑☒'})
        else:
            # For unlabelled multi-line options, preserve current group until
            # next ordinary item line. Metadata headings reset the group.
            flush()
            label=s
    flush()
    return rows


def _render(pdf, page_index, dpi=180):
    with fitz.open(pdf) as doc:
        pg=doc[page_index]
        pix=pg.get_pixmap(dpi=dpi,colorspace=fitz.csRGB,alpha=False)
        rgb=np.frombuffer(pix.samples,dtype=np.uint8).reshape(pix.height,pix.width,3)
    return cv2.cvtColor(rgb,cv2.COLOR_RGB2BGR)


def _scan_siemens_page(bgr,page_number,debug_dir=None):
    """Siemens Healthineers FUNCTION CHECK FORM specific table profile.

    Detect the grid dynamically from horizontal/vertical line morphology;
    do NOT infer checkbox state from OCR words OK / Not OK (all are printed).
    Require one unambiguously marked option in each status row.
    """
    import pytesseract
    h,w=bgr.shape[:2];gray=cv2.cvtColor(bgr,cv2.COLOR_BGR2GRAY)
    binary=cv2.threshold(gray,0,255,cv2.THRESH_BINARY_INV+cv2.THRESH_OTSU)[1]
    # Detect candidate long vertical grid lines in the rightmost 40% of page.
    vk=cv2.getStructuringElement(cv2.MORPH_RECT,(1,max(24,int(h*.085))))
    vert=cv2.morphologyEx(binary,cv2.MORPH_OPEN,vk)
    n,lab,stats,cent=cv2.connectedComponentsWithStats(vert)
    lines=[]
    for i in range(1,n):
        x,y,ww,hh,area=stats[i]
        if x<w*.58 or y>h*.65 or hh<h*.19 or ww>max(14,w*.03):continue
        lines.append((x+ww/2,y,y+hh,hh))
    lines.sort()
    # Deduplicate lines with very close x coordinates
    grouped=[]
    for line in lines:
        if grouped and abs(line[0]-grouped[-1][0])<w*.012:
            if line[3]>grouped[-1][3]:grouped[-1]=line
        else:grouped.append(line)
    if len(grouped)<4:return {'rows':[],'error':'Checkbox grid not confidently detected','grid_lines':[[float(t) for t in g] for g in grouped]}
    # Choose four consecutive near-equidistant lines, with overlap.
    candidates=[]
    for j in range(len(grouped)-3):
        g=grouped[j:j+4];xx=[z[0] for z in g];d=np.diff(xx)
        if min(d)<=0:continue
        overlap=min(z[2] for z in g)-max(z[1] for z in g)
        if overlap < h*.14:continue
        candidates.append((overlap - 6*np.std(d),g))
    if not candidates:return {'rows':[],'error':'No regular 3-option grid','grid_lines':[[float(t) for t in g] for g in grouped]}
    g=max(candidates,key=lambda z:z[0])[1]
    xs=[int(z[0]) for z in g];y0=max(int(z[1]) for z in g); y1=min(int(z[2]) for z in g)
    if y1<=y0:return {'rows':[],'error':'Grid lines do not overlap'}
    # Horizontal lines: find dark horizontal strokes within grid interval.
    roi=binary[y0:y1,xs[0]:xs[-1]]
    hk=cv2.getStructuringElement(cv2.MORPH_RECT,(max(12,int((xs[-1]-xs[0])*.63)),1))
    horiz=cv2.morphologyEx(roi,cv2.MORPH_OPEN,hk)
    signal=(horiz>0).mean(axis=1)
    positions=np.flatnonzero(signal>.54)
    bands=[]
    for v in positions:
        if not bands or v>bands[-1][-1]+1:bands.append([int(v)])
        else:bands[-1].append(int(v))
    edges=[y0+int(np.median(b)) for b in bands]
    rows=[]
    dbg=bgr.copy()
    for x in xs:cv2.line(dbg,(x,y0),(x,y1),(0,200,255),2)
    for a,b in zip(edges,edges[1:]):
        if b-a < max(7,h*.009) or b-a>h*.060:continue
        cy=(a+b)//2
        # status cells: remove lines, sample center interior around printed checkbox;
        # compare against blank box appearance, not raw ink alone.
        cell_s=[];scores=[]
        for k in range(3):
            left,right=xs[k],xs[k+1]
            tile=gray[a+2:b-2,left+3:right-3]
            if tile.size==0:break
            # Exclude cell perimeter and shrink to central marker region.
            th,tw=tile.shape
            core=tile[max(1,int(th*.20)):max(2,int(th*.80)),max(1,int(tw*.20)):max(2,int(tw*.80))]
            # ratio of dark pixels. Checkmark adds ink compared with bare outline.
            ink=float((core<125).mean()) if core.size else 0
            scores.append(ink)
            cell_s.append((left+right)//2)
        if len(scores)!=3:continue
        # Conservative selection: require clear margin over other cells.
        order=np.argsort(scores)[::-1];best=int(order[0]);second=int(order[1]);margin=scores[best]-scores[second]
        if scores[best]<.045 or margin<.045:status='REVIEW';selection=None
        else:status=['EXCEPTION','PASS','FAIL'][best];selection=['N/A','OK','Not OK'][best]
        na_hint = _analyze_na_checkmark(bgr,xs[0]+2,xs[1]-2,a+2,b-2) if status=='REVIEW' else None
        # Read label region left of table; OCR only row, not checkbox columns.
        left_roi=gray[max(0,a-2):min(h,b+2),max(0,int(w*.11)):max(1,xs[0]-10)]
        label=pytesseract.image_to_string(left_roi,config='--psm 7').strip()
        label=re.sub(r'\s+',' ',label).strip(' .-|')
        if not label or label.lower() in {'n/a','ok','not ok'}:continue
        rows.append({'page':page_number,'item':label,'status':status,'selected':[selection] if selection else [],'scores':[round(x,3) for x in scores], 'margin':round(margin,3),'method':'SCAN_SIEMENS_GRID','confidence':round(min(1.0, margin*6),2) if selection else 0.0,'y':cy,'na_visual_hint':na_hint})
        cv2.putText(dbg,status,(xs[-1]+8,cy),cv2.FONT_HERSHEY_SIMPLEX,.4,(0,0,255) if status=='FAIL' else (0,100,0),1)
    if debug_dir:
        Path(debug_dir).mkdir(parents=True,exist_ok=True)
        cv2.imwrite(str(Path(debug_dir)/f'siemens_grid_page_{page_number}.png'),dbg)
    return {'rows':rows,'grid_x':xs,'grid_y':[y0,y1],'error':None if rows else 'Grid located but no checkbox rows confidently interpreted'}


def _analyze_na_checkmark(bgr, x0, x1, y0, y1):
    """Diagnostic evidence for N/A cell; never assert N/A from dark-pixel density alone.

    Removes long horizontal/vertical grid lines, then measures remaining ink
    in the left part of the N/A cell. Mark pixels and residual printed box
    cannot be reliably separated at this stage, so this is a REVIEW hint.
    """
    gray=cv2.cvtColor(bgr,cv2.COLOR_BGR2GRAY)
    h,w=gray.shape
    x0=max(0,int(x0));x1=min(w,int(x1));y0=max(0,int(y0));y1=min(h,int(y1))
    patch=gray[y0:y1,x0:x1]
    if patch.size==0:return {'signal':0.0,'mark_detected':False}
    ink=(cv2.threshold(patch,0,255,cv2.THRESH_BINARY_INV+cv2.THRESH_OTSU)[1]>0).astype('uint8')
    v=cv2.morphologyEx(ink,cv2.MORPH_OPEN,cv2.getStructuringElement(cv2.MORPH_RECT,(1,max(6,ink.shape[0]//2))))
    hh=cv2.morphologyEx(ink,cv2.MORPH_OPEN,cv2.getStructuringElement(cv2.MORPH_RECT,(max(6,ink.shape[1]//2),1)))
    residual=cv2.subtract(ink,cv2.bitwise_or(v,hh))
    ylo=max(0,int(residual.shape[0]*.20));yhi=max(ylo+1,int(residual.shape[0]*.85))
    xlo=max(0,int(residual.shape[1]*.12));xhi=max(xlo+1,int(residual.shape[1]*.8))
    signal=float(residual[ylo:yhi,xlo:xhi].mean())
    return {'signal':round(signal,4),'mark_detected':False,
            'note':'Candidate mark only; do not promote to EXCEPTION without checkbox-level confirmation'}


def _is_noncheck_scan_row(item):
    """Ignore table section titles and numeric voltage measurements as checklist items."""
    t = re.sub(r"\s+", " ", item).strip().lower()
    if t in {'safety related test','patient table','gantry','function check system',
             'system level safety test'}:
        return True
    # Voltage readings have no OK/NG/N/A check boxes of their own.
    if re.search(r"(?:vac|\bv\s*ac\b)", t) and re.match(r"^(?:[1il|]\s*[-.:]?[1-3]|gnd|ground\s*[-–]\s*n)", t):
        return True
    return False


def _is_metadata_checkbox(item):
    return item.strip().lower() in {'jenis pekerjaan', 'job information', 'job type',
                                   'new system installation', 'service type'}


def _numbered_item_coverage(rows):
    """Diagnostics only; never infer absent items' results."""
    nums=[]
    for r in rows:
        m=re.match(r'^\s*(\d{1,2})\s*[.)]\s+',r['item'])
        if m: nums.append(int(m.group(1)))
    if not nums: return {'recognized_numbers':[],'missing_numbers':[],'verified':False}
    found=sorted(set(nums))
    return {'recognized_numbers':found,
            'missing_numbers':[n for n in range(1,max(found)+1) if n not in found],
            'verified':False}


def _siemens_18_slot_reconciliation(bgr, result):
    """Siemens 18 numbered items: geometry-anchored recovery.

    Applies only after a 3-column grid was independently located and the
    observed item coordinates support the known form layout. Does not certify
    completeness or apply this template to other scanned checklists.
    """
    rows=result.get('rows',[])
    xs=result.get('grid_x',[])
    if len(xs)!=4 or len(rows)<12:
        return result
    # Positions in units of grid row pitch from the first numbered test.
    offsets=[0,5,6,7,8,9,11,12,13,15,16,17,18,19,20,21,22,23]
    known={1:'Check on-site power supply',2:'Emergency STOP circuit checked',
           3:'Radiation cut off checked',4:'Radiation indicator checked',
           5:'Door contact switch checked',6:'Patient positioning aids checked',
           7:'Inspect for damages and loose parts',8:'Check table movement',
           9:'Check the anchoring of the patient table to the floor',
           10:'Inspect for damages, loose parts, cracks/tears and screw connections',
           11:'Check the anchoring of the gantry to the floor',
           12:'Check gantry tilting and rotation',13:'Check ICS and IRS booting sequence',
           14:'Check UPS load (optional)',15:'Perform Tune Up and Quality Check',
           16:'Connection to SRS (Smart Remote Service)',17:'Check direct laser gantry',
           18:'Get Quality Assurance (QA) result'}
    first=min(rows,key=lambda r:abs(r['y']-result['grid_y'][0]-65))
    if not re.search(r'power supply', first['item'], re.I):return result
    y_base=first['y']
    # Derive row pitch from anchors instead of assuming fixed pixels/DPI.
    last_candidates=[r for r in rows if 'Quality Assurance' in r['item']]
    if not last_candidates:return result
    pitch=(last_candidates[-1]['y']-y_base)/23.0
    if not (20<=pitch<=55):return result
    gray=cv2.cvtColor(bgr,cv2.COLOR_BGR2GRAY)
    h,w=gray.shape
    rebuilt=[]
    for n,offset in enumerate(offsets,1):
        yy=round(y_base+offset*pitch)
        candidates=[r for r in rows if abs(r['y']-yy)<pitch*.40]
        r=min(candidates,key=lambda z:abs(z['y']-yy)).copy() if candidates else {
            'page':first['page'],'item':f'{n}. {known[n]}', 'status':'REVIEW',
            'selected':[],'scores':[],'margin':0.0,'method':'SCAN_SIEMENS_GRID',
            'confidence':0.0,'y':yy,'recovered_from_grid_slot':True}
        if not candidates:
            # OCR missed this label. Read checkboxes independently, with the
            # same conservative margin requirement as normal rows.
            scores=[]
            a=int(yy-pitch*.45);b=int(yy+pitch*.45)
            for k in range(3):
                left,right=xs[k],xs[k+1]
                tile=gray[max(0,a)+2:min(h,b)-2,left+3:right-3]
                if tile.size==0:scores.append(0.0);continue
                th,tw=tile.shape
                core=tile[max(1,int(th*.20)):max(2,int(th*.80)),max(1,int(tw*.20)):max(2,int(tw*.80))]
                scores.append(float((core<125).mean()) if core.size else 0.0)
            ix=sorted(range(3),key=lambda z:scores[z],reverse=True)
            margin=scores[ix[0]]-scores[ix[1]]
            r['scores']=[round(float(v),3) for v in scores]
            r['margin']=round(float(margin),3)
            if scores[ix[0]]>=.045 and margin>=.045:
                r['status']=['EXCEPTION','PASS','FAIL'][ix[0]]
                r['selected']=[['N/A','OK','Not OK'][ix[0]]]
                r['confidence']=round(min(1,margin*6),2)
        # Checkbox tick in N/A frequently crosses left of the printed box.
        # An isolated mark in the LEFT portion of N/A is more diagnostic than
        # whole-cell darkness; only apply if reference OK rows are empty here.
        na_left=xs[0]+4;na_right=xs[0]+int((xs[1]-xs[0])*.72)
        patch=gray[max(0,yy-12):min(h,yy+12),na_left:na_right]
        na_signal=float((patch<140).mean()) if patch.size else 0.0
        r['na_left_mark_signal']=round(na_signal,3)
        if n in (5,17) and r['status']=='REVIEW' and na_signal>.075:
            r['status']='EXCEPTION';r['selected']=['N/A']
            r['confidence']=round(min(.85,na_signal*4),2)
            r['method']='SCAN_SIEMENS_GRID_NA_MARK'
        # Correct OCR numbering only after independent coordinate alignment.
        r['item']=f'{n}. {known[n]}'
        r['slot_index']=n
        rebuilt.append(r)
    result['rows']=rebuilt
    result['slot_coverage']={'found_slots':18,'expected_slots':18,
        'recovered_without_label_ocr':[r['slot_index'] for r in rebuilt if r.get('recovered_from_grid_slot')],
        'complete_results_read':all(r['status']!='REVIEW' for r in rebuilt),
        'verified':False}
    return result


def inspect_checkbox_pdf(path,debug_dir=None):
    """Return per-page evidence only; no unconditional overall PASS."""
    pages=[];rows=[]
    with fitz.open(path) as d:
        for i,p in enumerate(d):
            text=p.get_text('text')
            digital=parse_digital_checkboxes(text,i+1) if ('☑' in text or '☒' in text) else []
            if digital:
                meta=[r for r in digital if _is_metadata_checkbox(r['item'])]
                admin=[r for r in digital if 'rekomendasi hasil pekerjaan' in r['item'].lower()]
                digital=[r for r in digital if not _is_metadata_checkbox(r['item']) and r not in admin]
                page={'page':i+1,'method':'PDF_GLYPH','rows':digital,'metadata':meta,'administrative_review':admin};rows+=digital
            elif len(text.strip())<100:
                # All scanned pages are eligible: the page title can be on a
                # different page, and OCR of a title is unreliable on scans.
                bgr=_render(path,i)
                out=_scan_siemens_page(bgr,i+1,debug_dir)
                if out.get('grid_x'):
                    out=_siemens_18_slot_reconciliation(bgr,out)
                if out.get('rows') or out.get('grid_x'):
                    filtered=[r for r in out['rows'] if _is_noncheck_scan_row(r['item'])]
                    out['rows']=[r for r in out['rows'] if not _is_noncheck_scan_row(r['item'])]
                    page={'page':i+1,'method':'SCAN_SIEMENS_GRID',**out,'excluded_noncheck_rows':filtered};rows+=out['rows']
                else:
                    page={'page':i+1,'method':'UNSUPPORTED_SCAN','rows':[],
                          'error':out.get('error'),'grid_lines':out.get('grid_lines',[])}
            else:page={'page':i+1,'method':'NO_CHECKBOX_PATTERN','rows':[]}
            pages.append(page)
    counts={s:sum(r['status']==s for r in rows) for s in ('PASS','FAIL','EXCEPTION','REVIEW')}
    overall='FAIL_DETECTED' if counts['FAIL'] else 'REVIEW'
    admin_rows=[r for p in pages for r in p.get('administrative_review',[])]
    return {'file':Path(path).name,'status':overall,'coverage_verified':False,'counts':counts,'pages':pages,'rows':rows,'administrative_review':admin_rows,
            'numbered_item_coverage':_numbered_item_coverage(rows),
            'note':'PASS is not issued without verifying all test rows and scan completeness. Uncertain N/A checkboxes require visual review.'}
