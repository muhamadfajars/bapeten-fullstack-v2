"""Exact source evidence display policy from uploaded Streamlit v46 app.py."""
import re

def _label_evidence_view(expected, actual, status, field):
    """Show only evidence-supported span; never manufacture a MATCH."""
    import re
    if not actual or str(actual).strip() == '-':
        return '-', None
    evidence = str(actual).strip()
    exp = str(expected or '').strip()
    if status != 'MATCH' or not exp:
        return evidence, None
    if field.startswith('nomor_seri'):
        # GS1 AI (21) marks a serial. Accept only an exact whole serial token.
        serial = re.sub(r'[^A-Z0-9]', '', exp.upper())
        if serial:
            pattern = r'(?<![A-Z0-9])(?:\(21\)\s*)?(' + re.escape(serial) + r')(?![A-Z0-9])'
            m = re.search(pattern, evidence.upper())
            if m: return evidence[m.start(1):m.end(1)], 100.0
        return evidence, None
    if field.startswith('merk'):
        # Whole-word matching avoids GE matching the word "GEnerator".
        m = re.search(r'(?<![A-Za-z0-9])' + re.escape(exp) + r'(?![A-Za-z0-9])', evidence, re.I)
        if m: return evidence[m.start():m.end()], 100.0
        return evidence, None
    if field.startswith('tipe'):
        # Match core model as a whole code; do not discard the PX suffix.
        variants = [exp]
        if '(' in exp:
            variants = [exp.split('(')[0].strip(), exp[exp.find('(')+1:exp.rfind(')')].strip()]
        for variant in variants:
            if not variant: continue
            pattern = r'(?<![A-Za-z0-9])' + r'\s*[- ]?\s*'.join(map(re.escape, re.split(r'\s*[- ]\s*', variant))) + r'(?![A-Za-z0-9])'
            m = re.search(pattern, evidence, re.I)
            if m: return evidence[m.start():m.end()], 100.0
    return evidence, None
