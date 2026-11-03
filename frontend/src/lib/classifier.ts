import sharedRules from '../../../backend/app/classification_rules.json';
import type { CategoryId } from '../types/models';
import { classifyFile as apiClassifyFile } from '../api';

export type ClassificationResult = {
  category: CategoryId | 'unknown';
  subtype?: string;
  layer: 1 | 2 | 0;
  reason: string;
  confidence: number;
};

// Bundle the backend's shared rules for instant browser-side matching.
const NAME_PATTERNS: Array<[RegExp, CategoryId, string | undefined]> = sharedRules.filenamePatterns.map(
  rule => [new RegExp(rule.pattern, sharedRules.flags), rule.category as CategoryId, rule.subtype ?? undefined],
);
const weakHints = new Set(sharedRules.weakNameHints);

export function classifyByFilename(filename: string): ClassificationResult | null {
  const matches: Array<{ category: CategoryId; subtype?: string; strong: boolean }> = [];
  for (const [pattern, category, subtype] of NAME_PATTERNS) {
    const match = pattern.exec(filename);
    if (match) {
      const hint = match[0].replace(/[\s_-]+/g, ' ').toLowerCase().trim();
      matches.push({ category, subtype, strong: !weakHints.has(hint) });
    }
  }
  const strong = matches.filter(match => match.strong);
  const candidates = strong.length ? strong : matches;
  if (new Set(candidates.map(match => `${match.category}:${match.subtype ?? ''}`)).size > 1) {
    return { category: 'unknown', layer: 0, confidence: 0,
      reason: 'Nama berkas mengarah ke beberapa kategori. Perlu Pilih Kategori.' };
  }
  const selected = candidates[0];
  return selected ? { category: selected.category, subtype: selected.subtype,
    layer: 1, reason: 'Pola nama berkas terdeteksi', confidence: 0.95 } : null;
}

export async function classifyFile(file: File): Promise<ClassificationResult> {
  // Layer 1: Instant client-side check
  const layer1 = classifyByFilename(file.name);
  if (layer1) {
    return layer1;
  }

  // Layer 2: Send to backend for content inspection (digital text / OCR)
  try {
    const res = await apiClassifyFile(file);
    return {
      category: (res.category as CategoryId) || 'unknown',
      subtype: res.subtype,
      layer: res.layer ?? 0,
      reason: res.reason || 'Pemeriksaan isi teks dokumen',
      confidence: res.confidence ?? 0,
    };
  } catch (err) {
    return {
      category: 'unknown',
      layer: 0,
      reason: err instanceof Error ? err.message : 'Gagal klasifikasi otomatis',
      confidence: 0,
    };
  }
}

