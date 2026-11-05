import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';

// Run the browser filename classifier without loading browser-only API initialization.
const source = readFileSync(new URL('../src/lib/classifier.ts', import.meta.url), 'utf8');
const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS } });
const sharedRules = JSON.parse(readFileSync(new URL('../../backend/app/classification_rules.json', import.meta.url), 'utf8'));
const sandbox = { exports: {}, require: name => {
  if (name === '../../../backend/app/classification_rules.json') return { default: sharedRules };
  if (name === '../api') return { classifyFile: () => { throw new Error('Unexpected API call'); } };
  throw new Error(`Unexpected import: ${name}`);
} };
vm.runInNewContext(compiled.outputText, sandbox);
const classify = sandbox.exports.classifyByFilename;

test('shared rules match the filename regression baseline', () => {
  const baseline = JSON.parse(readFileSync(new URL('../../backend/tests/fixtures/classification_filename_baseline.json', import.meta.url), 'utf8'));
  for (const { name, browser } of baseline) {
    assert.deepEqual(JSON.parse(JSON.stringify(classify(name))), browser, name);
  }
});

test('dose reports are personnel documents, while explicit TLD administration stays separate', () => {
  for (const name of ['20260714134027-Laporan Dosis Awal RS Hermina Kepanjen Periode Oktober - Desember 2026.pdf',
    'Laporan_Dosis_OSL.pdf', 'Hasil Pembacaan Dosis TLD.pdf', 'Dosis Awal.pdf', 'Evaluasi Dosis OSL.pdf']) {
    assert.equal(classify(name)?.category, 'personel', name);
    assert.equal(classify(name)?.subtype, 'Evaluasi Dosis / Zero Check', name);
  }
  for (const name of ['Daftar Pemakai TLD.pdf', 'Daftar Pengguna Lencana OSL.pdf', 'Petugas TLD.pdf', 'Kepesertaan Pemantauan OSL.pdf']) {
    assert.equal(classify(name)?.category, 'tld', name);
  }
  for (const name of ['Lencana OSL.pdf', 'TLD.pdf', 'dosimeter.pdf', 'NUKLINDOLAB.pdf']) {
    assert.equal(classify(name), null, name);
  }
  assert.equal(classify('Laporan Dosis dan Daftar Pemakai TLD.pdf')?.category, 'unknown');
});

test('tube label aliases resolve in the browser', () => {
  for (const name of ['20260917112321-sn tube Fix 2.jpg', 'SN_TABUNG_03.png', 'sn-generator.jpeg', 'sn unit Fix 2.jpg']) {
    assert.equal(classify(name)?.category, 'label', name);
  }
});

test('PPR appointment titles take precedence over generic protection terms', () => {
  for (const name of ['20260918090751-Surat Penunjukan PPR FIX 2.jpg', 'Surat_Penunjukan_Sebagai_PPR.pdf',
    'Surat Penunjukan Petugas Proteksi Radiasi.jpg', 'Surat Penunjukan sebagai Petugas Proteksi Radiasi.pdf']) {
    assert.equal(classify(name)?.category, 'personel', name);
    assert.equal(classify(name)?.subtype, 'Surat Penunjukan Tugas', name);
  }
  assert.equal(classify('PROGRAM PROTEKSI RADIASI FIX SIP.pdf')?.category, 'proteksi');
});

test('unrelated names still need a category', () => {
  for (const name of ['sn tubing.jpg', 'Surat Penunjukan Vendor.pdf', 'scan001.jpg']) {
    assert.equal(classify(name), null, name);
  }
});

test('worker appointment and facility maintenance variants are recognized', () => {
  for (const name of ['20260818155148-SK PENETAPAN PEKERJA RADIASI DAN PENUNJUKAN PPR.pdf',
    'SK_PENETAPAN_PEKERJA_RADIASI.pdf', 'Penunjukan Petugas Proteksi Radiasi.pdf']) {
    assert.equal(classify(name)?.category, 'personel', name);
    assert.equal(classify(name)?.subtype, 'Surat Penunjukan Tugas', name);
  }
  for (const name of ['20261005140905-dokumen perawatan Fasilitas Radiodiagnostik MABA mobile.pdf',
    'DOKUMEN_PERAWATAN_MOBILE.pdf', 'perawatan fasilitas.pdf']) {
    assert.equal(classify(name)?.category, 'perawatan', name);
  }
});

test('conflicting categories or personnel subtypes require manual selection', () => {
  for (const name of ['PROGRAM PROTEKSI DAN PROGRAM PERAWATAN.pdf',
    'SIP dan SIB.pdf', 'dokumen perawatan dan spesifikasi alat.pdf']) {
    assert.equal(classify(name)?.category, 'unknown', name);
    assert.equal(classify(name)?.confidence, 0, name);
  }
  assert.equal(classify('HASIL UJI ZERO CHECK TLD.pdf')?.category, 'personel');
});
