export type MatchStatus = 'MATCH' | 'REVIEW' | 'MISMATCH' | 'MISSING';

export type CategoryId =
  | 'formulir' | 'proteksi' | 'perawatan' | 'manajemen' | 'teknis'
  | 'personel' | 'tld' | 'spesifikasi' | 'label' | 'impor'
  | 'kesesuaian' | 'fungsi' | 'paparan' | 'kebocoran';

export type DocumentCategory = {
  id: CategoryId;
  name: string;
  description: string;
  icon: string;
  requiresSubtype?: boolean;
};

export type UploadItem = {
  id: string;
  name: string;
  size: number;
  category: CategoryId;
  subtype?: string;
  addedAt: string;
  file?: File;
  serverId?: string;
  sha256?: string;
  detectedLayer?: 1 | 2 | 0;
  detectionReason?: string;
  isClassifying?: boolean;
};

export type MatchRow = {
  id: string;
  field: string;
  expected: string;
  observed: string;
  score: number | null;
  status: MatchStatus;
  page?: number;
  note?: string;
  document_id?: string;
  quote?: string;
  detail?: {
    type: 'approval' | 'maintenance';
    pages?: number[];
    heading?: string;
    frequencies?: string[];
    parameters?: string[];
  } | null;
};

export type MatchSection = {
  id: string;
  category: CategoryId;
  name: string;
  rows: MatchRow[];
  info?: string;
};

export type Person = { name: string; role: string };
export type Equipment = {
  label: string;
  merk_unit: string;
  tipe_unit: string;
  nomor_seri_unit: string;
  merk_tabung: string;
  tipe_tabung: string;
  nomor_seri_tabung: string;
};
export type FormReference = {
  facility: string;
  address: string;
  applicationNumber?: string;
  personnel: Person[];
  equipment: Equipment[];
};

export const PERSONNEL_TYPES = [
  'Surat Izin Praktik (SIP)',
  'Surat Izin Bekerja (SIB)',
  'Surat Perintah',
  'Sertifikat Kompetensi',
  'Surat Izin Kerja',
  'Surat Keterangan Kerja',
  'Surat Penunjukan Tugas',
  'Evaluasi Dosis / Zero Check',
] as const;
