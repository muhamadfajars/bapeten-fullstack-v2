import { test } from 'node:test';
import assert from 'node:assert/strict';
import { applyClassification, classificationBlocker, analysisBlocker } from '../src/lib/uploadState.ts';
import type { UploadItem } from '../src/types/models.ts';

const pending: UploadItem = { id: 'scan', name: 'scan.pdf', size: 100,
  category: 'unknown', isClassifying: true, addedAt: '' };

test('pending and unrecognized documents block analysis until a category is chosen', () => {
  assert.match(classificationBlocker([pending])!, /Sedang mengenali/);
  const unknown = applyClassification(pending, { category: 'unknown', layer: 0, confidence: 0, reason: 'Tidak dikenali' });
  assert.equal(unknown.category, 'unknown');
  assert.equal(unknown.isClassifying, false);
  assert.match(classificationBlocker([unknown])!, /Perlu Pilih Kategori/);
  assert.equal(classificationBlocker([{ ...unknown, category: 'kesesuaian' }]), null);
});

test('recognized content carries its category and personnel subtype', () => {
  const known = applyClassification(pending, { category: 'personel', subtype: 'Surat Perintah', layer: 2, confidence: .9, reason: 'Isi dokumen' });
  assert.equal(known.category, 'personel');
  assert.equal(known.subtype, 'Surat Perintah');
  assert.equal(classificationBlocker([known]), null);
  assert.match(classificationBlocker([known, pending])!, /Sedang mengenali/);
});

test('late recognition success or failure cannot overwrite a manual choice', () => {
  const manual: UploadItem = { ...pending, category: 'paparan', isClassifying: false };
  for (const category of ['teknis', 'unknown'] as const) {
    assert.equal(applyClassification(manual, { category, layer: 0, confidence: 0, reason: 'Late response' }), manual);
  }
});

test('analysis requires exactly one reference form and at least one classified supporting document', () => {
  const form: UploadItem = { ...pending, id: 'form', category: 'formulir', isClassifying: false };
  const support: UploadItem = { ...pending, category: 'perawatan', isClassifying: false };
  assert.match(analysisBlocker([])!, /Unggah/);
  assert.match(analysisBlocker([support])!, /Tambahkan 1 Formulir/);
  assert.match(analysisBlocker([form])!, /dokumen pendukung/);
  assert.match(analysisBlocker([form, { ...form, id: 'form2' }, support])!, /tepat 1/);
  assert.equal(analysisBlocker([form, support]), null);
  assert.match(analysisBlocker([form, support, pending])!, /Sedang mengenali/);
  assert.match(analysisBlocker([form, support, { ...pending, isClassifying: false }])!, /Perlu Pilih Kategori/);
});
