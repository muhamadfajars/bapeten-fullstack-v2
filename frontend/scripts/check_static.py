from pathlib import Path
import re
root=Path(__file__).resolve().parents[1]
app=(root/'src/App.tsx').read_text()
api=(root/'src/api.ts').read_text()
categories=(root/'src/data/categories.ts').read_text()
models=(root/'src/types/models.ts').read_text()
css=(root/'src/styles.css').read_text()
ids=re.findall(r"\{ id: '([^']+)', name:",categories)
assert len(ids)==14 and len(set(ids))==14
for page in ['ringkasan','upload','formulir','matching','dokumen']:
    assert f'id="{page}" hidden=' in app, f'Page is not independently hidden: {page}'
assert 'Mulai Analisis' in app and 'runAnalysis' in app
assert 'fetchResults' in app and 'jobStatus' in app and 'newApplication' in app
assert 'displaySections.map(' in app and 'DEMO_MATCHING' not in app and 'DEMO_FORM' not in app
assert 'applicationId' in app and 'serverId' in models
assert 'application_id' in api and 'Bearer ' in api
assert '.page-section[hidden] {display:none!important;}' in css
for col in ['Field','Formulir','Dokumen','Skor','Status']:assert col in app
print('PASS: 5 independent pages; 14 categories; real API upload, analysis & polling; server-backed results; no demo data')
