import type {MatchSection} from '../types/models';
export function matchingTotals(sections:MatchSection[]) {
  const rows=sections.flatMap(x=>x.rows);
  const match=rows.filter(x=>x.status==='MATCH').length;
  const review=rows.filter(x=>x.status==='REVIEW').length;
  const mismatch=rows.filter(x=>x.status==='MISMATCH').length;
  const missing=rows.filter(x=>x.status==='MISSING').length;
  return {match,review,mismatch,missing,total:rows.length,percentage:rows.length?Math.round(match/rows.length*1000)/10:0};
}
