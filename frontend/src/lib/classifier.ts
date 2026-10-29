import type { CategoryId } from '../types/models';
import { classifyFile as apiClassifyFile } from '../api';

export type ClassificationResult = {
  category: CategoryId | 'unknown';
  subtype?: string;
  layer: 1 | 2 | 0;
  reason: string;
  confidence: number;
};

// Layer 1: Browser-side instant regex matching
const NAME_PATTERNS: Array<[RegExp, CategoryId, string | undefined]> = [
  // Formulir
  [/formulir|form[\s_-]*permohonan|ktun.*permohonan|permohonan[\s_-]*\d{5,7}/i, 'formulir', undefined],

  // Proteksi
  [/program[\s_-]*proteksi|proteksi[\s_-]*radiasi|ppkr|keselamatan[\s_-]*radiasi/i, 'proteksi', undefined],

  // Perawatan
  [/program[\s_-]*perawatan|perawatan[\s_-]*pesawat|maintenance[\s_-]*program|pemeliharaan/i, 'perawatan', undefined],

  // Manajemen
  [/sistem[\s_-]*manajemen|manajemen[\s_-]*fasilitas|quality[\s_-]*management/i, 'manajemen', undefined],

  // Teknis
  [/dokumen[\s_-]*teknis|rencana[\s_-]*teknis|gedung[\s_-]*penahan|penahan[\s_-]*radiasi|denah[\s_-]*ruang/i, 'teknis', undefined],

  // Personel
  [/surat[\s_-]*keterangan[\s_-]*kerja|skk\b/i, 'personel', 'Surat Keterangan Kerja'],
  [/surat[\s_-]*penunjukan[\s_-]*tugas|sk[\s_-]*penunjukan|pengangkatan.*ppr/i, 'personel', 'Surat Penunjukan Tugas'],
  [/sprint|surat[\s_-]*perintah|surat[\s_-]*tugas/i, 'personel', 'Surat Perintah'],
  [/sertifikat.*(?:kompetensi|ppr|lulus)/i, 'personel', 'Sertifikat Kompetensi'],
  [/sikr\b|surat[\s_-]*izin[\s_-]*kerja/i, 'personel', 'Surat Izin Kerja'],
  [/data[\s_-]*sib|kartu[\s_-]*sib|sib\b|izin[\s_-]*bekerja/i, 'personel', 'Surat Izin Bekerja (SIB)'],
  [/sipr?\b|dr\.?[\s_-]*[a-z]+[\s_-]*sp\.?rad|surat[\s_-]*izin[\s_-]*prakt?ik/i, 'personel', 'Surat Izin Praktik (SIP)'],
  [/evaluasi[\s_-]*dosis|zero[\s_-]*check|zerocheck|zero[\s_-]*cek/i, 'personel', 'Evaluasi Dosis / Zero Check'],

  // TLD / Petugas TLD
  [/dosis[\s_-]*awal|laporan[\s_-]*dosis|petugas[\s_-]*tld|tld\b|dosimeter|osl\b/i, 'tld', undefined],

  // Spesifikasi
  [/spesifikasi|brochure|brosur|manual[\s_-]*book|datasheet|data[\s_-]*sheet/i, 'spesifikasi', undefined],

  // Impor
  [/persetujuan[\s_-]*impor|persetujuan[\s_-]*import|izin[\s_-]*impor|izin[\s_-]*import/i, 'impor', undefined],

  // Kesesuaian
  [/uji[\s_-]*kesesuaian|sertifikat[\s_-]*uk|ktun.*uk|lhu\b|resume[\s_-]*bapeten/i, 'kesesuaian', undefined],

  // Uji Fungsi / Acceptance
  [/uji[\s_-]*fungsi|ujifungsi|acceptance[\s_-]*test|accepatance|caf\b|bauf\b|bast\b|service[\s_-]*report|installation.*record|installation.*verification/i, 'fungsi', undefined],

  // Paparan & Kebocoran
  [/kebocoran[\s_-]*tabung|pengukuran[\s_-]*kebocoran|uji[\s_-]*kebocoran/i, 'kebocoran', undefined],
  [/pengukuran[\s_-]*paparan|paparan[\s_-]*radiasi|upar\b|uji[\s_-]*paparan|survey[\s_-]*radiasi/i, 'paparan', undefined],

  // Label
  [/foto[\s_-]*label|label[\s_-]*generator|label[\s_-]*tabung|label[\s_-]*unit|sn[\s_-]*unit|foto[\s_-]*tube|foto[\s_-]*nomor[\s_-]*seri|foto[\s_-]*keseluruhan/i, 'label', undefined],
];

export function classifyByFilename(filename: string): ClassificationResult | null {
  for (const [pattern, category, subtype] of NAME_PATTERNS) {
    if (pattern.test(filename)) {
      return {
        category,
        subtype,
        layer: 1,
        reason: 'Pola nama berkas terdeteksi',
        confidence: 0.95,
      };
    }
  }
  return null;
}

export async function classifyFile(file: File): Promise<ClassificationResult> {
  // Layer 1: Instant client-side check
  const layer1 = classifyByFilename(file.name);
  if (layer1 && layer1.category !== 'unknown') {
    return layer1;
  }

  // Layer 2: Send to backend for content inspection (digital text / OCR)
  try {
    const res = await apiClassifyFile(file);
    return {
      category: (res.category as CategoryId) || 'unknown',
      subtype: res.subtype,
      layer: (res.layer as 1 | 2 | 0) || 2,
      reason: res.reason || 'Pemeriksaan isi teks dokumen',
      confidence: res.confidence || 0.9,
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

