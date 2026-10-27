"""Focused v46 repair for program/technical document matching.

v45's address/facility policy is unchanged. This module overrides only
explicit insert-component matching and scoped cross-page maintenance sections.
"""
import re
from . import program_robust_v44 as prior
from .program_robust_v43 import normalize, space

facility_result = prior.facility_result
address_result = prior.address_result


def match_equipment(path, pages, references):
    """Use exactly the labeled insert serial when it is the form's selected serial.

    The user has confirmed the BAPETEN form field means X-ray tube *insert*
    serial in this workflow. Different housing serials are not disagreements
    about the insert's identity. Nonmatching insert values remain MISMATCH.
    """
    groups=prior.match_equipment(path,pages,references)
    records=prior._better_device_records(path,pages)
    # Preserve identity assignment from v45; never borrow insert serial from
    # a different physical device or a page shared by multiple references.
    weights={(i,j):prior.base._identity_weight(ref,record)
             for i,ref in enumerate(references) for j,record in enumerate(records)}
    assigned={};used=set()
    for w,i,j in sorted(((w,i,j) for (i,j),w in weights.items()), reverse=True):
        if w<10 or i in assigned or j in used:continue
        if sum(weights[(i,k)]==w for k in range(len(records)))!=1:continue
        if sum(weights[(k,j)]==w for k in range(len(references)))!=1:continue
        assigned[i]=j;used.add(j)
    for i,rows in enumerate(groups):
        fields=records[assigned[i]]['fields'] if i in assigned else {}
        insert=fields.get('nomor_seri_insersi')
        row=next((r for r in rows if r.get('field')=='nomor_seri_tabung'),None)
        if row is None or insert is None:continue
        expected=space(references[i].get('nomor_seri_tabung'))
        if not expected:continue
        status,score=prior.base._compare_value(expected,insert['value'],'nomor_seri_tabung')
        # Explicit source label required; one device must have a unique insert.
        row.update({'observed':space(insert['value']),'status':status,'score':score,
                    'label_override':'No. seri insersi tabung',
                    'reason':'','method':'v46_insert_serial_only',
                    'evidence':[{'page':insert['page'],'quote':insert['quote'],
                                 'value':insert['value'],'field_component':'nomor_seri_insersi',
                                 'method':insert['method']}]})
    return groups


def maintenance_sections(pages, previous):
    """Keep the true Constancy Test subsection as a contiguous multi-page block.

    Page headers, tables of contents and the preceding 'uji fungsi' section
    cannot contribute the frequency/parameters of Uji Kesesuaian.
    """
    prior_sections=previous or {'toc':[]}
    marker=re.compile(r'(?i)(?:^|\n)\s*(?:\d+(?:\s*[.]\s*\d+){1,4}\s*[.]?\s*)?'
                      r'uji\s+kesesuaian\s*(?:\(\s*constancy\s+test\s*\))?\b')
    next_section=re.compile(r'(?im)^\s*\d+(?:\s*[.]\s*\d+){1,5}\s*[.]?\s+[A-Za-z]')
    freq_heading=re.compile(r'(?im)^\s*frekuensi\s*:')
    param_heading=re.compile(r'(?im)^\s*parameter\s+yang\s+diuji\s*(?:meliputi)?\s*:')
    from .program_documents import _is_toc_page
    sections=[]
    for n,p in enumerate(pages):
        raw=p.get('text') or ''
        if _is_toc_page(raw):continue
        for heading in marker.finditer(raw):
            line=raw[heading.start():raw.find('\n',heading.start()) if '\n' in raw[heading.start():] else len(raw)]
            # Prevent paragraphs mentioning a test from becoming a new heading.
            if len(space(line))>110:continue
            block=raw[heading.end():]
            source_pages=[p.get('page')]
            for follow in pages[n+1:n+4]:
                chunk=follow.get('text') or ''
                block+='\n'+chunk
                source_pages.append(follow.get('page'))
                stop=next_section.search(chunk)
                if stop:
                    # Need enough content before stopping (real later heading).
                    break
            cut=next_section.search(block)
            if cut:block=block[:cut.start()]
            # Some PDFs have chapter text starting on next page and repeat
            # document header/metadata. Strip such lines before extraction.
            clean_lines=[]
            for l in block.splitlines():
                s=space(l)
                if re.search(r'(?i)^(?:no\.\s*dok|tanggal\s*:|halaman\s*:|revisi\s*:|website\s*:|telp\s*:|detaildetail)',s):continue
                if re.fullmatch(r'\d{1,3}',s):continue
                clean_lines.append(s)
            block='\n'.join(clean_lines)
            fm=freq_heading.search(block);pm=param_heading.search(block)
            if not fm or not pm or pm.start()<=fm.end():continue
            frequency_segment=block[fm.end():pm.start()]
            param_segment=block[pm.end():]
            frequencies=[]
            for l in frequency_segment.splitlines():
                v=re.sub(r'^\s*(?:[▪•\-]|\d+[.)])\s*','',l).strip(' .;')
                if (v and len(v)<165 and re.match(r'(?i)^(?:setiap|se(?:cara|telah)|minimal|periodik|rutin|sekali|tiap|\d)',v)):
                    frequencies.append(v)
            parameters=[]
            for l in param_segment.splitlines():
                m=re.match(r'^\s*(?:\d+\s*[.)]|[▪•-])\s*(.{5,185})$',l)
                if m:
                    v=m.group(1).strip(' .;')
                    if not re.match(r'(?i)^(?:bab\b|perawatan\b)',v): parameters.append(v)
            frequencies=list(dict.fromkeys(frequencies))[:12]
            parameters=list(dict.fromkeys(parameters))[:24]
            if frequencies and parameters:
                sections.append({'page':p.get('page'),'source_pages':source_pages,
                                 'heading':space(line),'frequencies':frequencies,
                                 'parameters':parameters,'excerpt':space(block[:350]),
                                 'method':'v46_cross_page_constancy_scoped'})
    if sections:
        prior_sections.update({'section':sections,'section_status':'FOUND'})
    else:
        # Retain legacy support for alternative headings (Uji Konstansi /
        # Quality Control) only when both frequency and parameter are evidenced.
        # Never relabel the preceding Uji Fungsi subsection as Uji Kesesuaian.
        alternate=prior.maintenance_sections(pages,{'toc':prior_sections.get('toc',[]),'section':[]})
        good=[sec for sec in (alternate.get('section') or [])
              if re.search(r'(?i)(?:kesesuaian|constancy|konstansi|uji\s+rutin|quality\s+control)',
                           sec.get('heading',''))
              and sec.get('frequencies') and sec.get('parameters')]
        prior_sections['section']=good
        prior_sections['section_status']='FOUND' if good else 'REVIEW'
    return prior_sections
