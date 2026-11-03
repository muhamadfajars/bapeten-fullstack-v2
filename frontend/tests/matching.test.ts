import { test } from 'node:test';
import assert from 'node:assert/strict';
import { matchingTotals, sortMatchingSections } from '../src/lib/matching.ts';
import type { CategoryId, MatchSection } from '../src/types/models.ts';

const order: CategoryId[] = [
  'proteksi', 'manajemen', 'personel', 'tld', 'teknis', 'spesifikasi',
  'label', 'impor', 'perawatan', 'kesesuaian', 'fungsi', 'paparan', 'kebocoran',
];
const section = (category: CategoryId, id = category): MatchSection => ({
  id, category, name: category,
  rows: [{ id: `${id}-row`, field: 'Nama fasilitas', expected: 'A', observed: 'B', score: 0, status: 'MISMATCH' }],
});

test('matching follows the agreed category order regardless of upload order without altering results', () => {
  const input = order.toReversed().map(category => section(category));
  const original = structuredClone(input);
  const sorted = sortMatchingSections(input);
  assert.deepEqual(sorted.map(item => item.category), order);
  assert.deepEqual(input, original);
  assert.deepEqual(matchingTotals(sorted), matchingTotals(input));
  for (const item of sorted) assert.equal(item, input.find(source => source.id === item.id));
  assert.deepEqual(sortMatchingSections([]), []);
});

test('multiple sections stay together and filtering preserves category order', () => {
  const personnelA = section('personel');
  const personnelB = { ...section('personel'), id: 'personel-b' };
  const sorted = sortMatchingSections([section('perawatan'), personnelA, section('proteksi'), personnelB]);
  assert.deepEqual(sorted.map(item => item.id), ['proteksi', 'personel', 'personel-b', 'perawatan']);
  assert.deepEqual(sorted.filter(item => item.category !== 'personel').map(item => item.category), ['proteksi', 'perawatan']);
});
