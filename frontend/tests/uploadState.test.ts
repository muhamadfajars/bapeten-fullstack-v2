import { test } from 'node:test';
import assert from 'node:assert/strict';
import { applyClassification, classificationBlocker } from '../src/lib/uploadState.ts';
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
