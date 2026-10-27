"""Extract GS1 (21) serial and (240) additional product ID from *OCR evidence*.

Preserve OCR provenance. We NEVER infer an identifier from the form or the
filename; both are prohibited as evidence. Strict GS1 AI tags prevent accidental
match of a GTIN (01), production batch, or housing serial to an insert serial.
"""
import re

_AI = re.compile(r'\(\s*(21|240)\s*\)\s*[:#-]?\s*([A-Z0-9][A-Z0-9.\-]{3,27})',re.I)


def augment_gs1_rows(rows):
    output=list(rows)
    seen={(str(r.get('text','')).upper(),str(r.get('variant','original'))) for r in rows}
    for row in rows:
        line=str(row.get('text') or '')
        for match in _AI.finditer(line):
            ai,raw=match.groups()
            # OCR can join the subsequent right-hand descriptor directly to code.
            token=raw.strip('.,;:')
            if not (4 <= len(token) <= 24):continue
            derived=('SERIAL ' if ai=='21' else 'MODEL ')+token
            variant=str(row.get('variant') or 'original')
            if (derived.upper(),variant) in seen:continue
            seen.add((derived.upper(),variant))
            output.append({**row,'text':derived,'variant':variant,
                           'gs1_ai':ai,'derived_from_ocr':line})
    return output
