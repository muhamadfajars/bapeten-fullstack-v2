import type {CategoryId, MatchSection} from '../types/models';

const MATCHING_CATEGORY_ORDER: readonly CategoryId[] = [
  'proteksi', 'manajemen', 'personel', 'tld', 'teknis', 'spesifikasi',
  'label', 'impor', 'perawatan', 'kesesuaian', 'fungsi', 'paparan', 'kebocoran',
];
const categoryRank = new Map(MATCHING_CATEGORY_ORDER.map((category, index) => [category, index]));

export function sortMatchingSections(sections: readonly MatchSection[]): MatchSection[] {
  // Keep the server result intact, including row order and sections within each category.
  return [...sections].sort((a, b) =>
    (categoryRank.get(a.category) ?? MATCHING_CATEGORY_ORDER.length) -
    (categoryRank.get(b.category) ?? MATCHING_CATEGORY_ORDER.length));
}

export function matchingTotals(sections:MatchSection[]) {
  const rows=sections.flatMap(x=>x.rows);
  const match=rows.filter(x=>x.status==='MATCH').length;
  const review=rows.filter(x=>x.status==='REVIEW').length;
  const mismatch=rows.filter(x=>x.status==='MISMATCH').length;
  const missing=rows.filter(x=>x.status==='MISSING').length;
  return {match,review,mismatch,missing,total:rows.length,percentage:rows.length?Math.round(match/rows.length*1000)/10:0};
}
