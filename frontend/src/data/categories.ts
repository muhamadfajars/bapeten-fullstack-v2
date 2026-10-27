import type { DocumentCategory } from '../types/models';

export const CATEGORIES: DocumentCategory[] = [
  { id: 'formulir', name: 'Formulir Permohonan', icon: 'file', description: 'Dokumen acuan utama untuk proses matching' },
  { id: 'proteksi', name: 'Dokumen Program Proteksi', icon: 'shield', description: 'Identitas fasilitas, personel, alat, pengesahan' },
  { id: 'perawatan', name: 'Dokumen Program Perawatan', icon: 'wrench', description: 'Fasilitas, pengesahan, klausul uji kesesuaian' },
  { id: 'manajemen', name: 'Dokumen Sistem Manajemen', icon: 'settings', description: 'Identitas fasilitas dan pengesahan' },
  { id: 'teknis', name: 'Dokumen Teknis', icon: 'blueprint', description: 'Data pesawat, tabung, ruangan, pengesahan' },
  { id: 'personel', name: 'Dokumen Personel', icon: 'users', description: 'SIP, SIB, surat perintah, kompetensi, dll.', requiresSubtype: true },
  { id: 'tld', name: 'Dokumen Petugas TLD', icon: 'clipboard', description: 'Fasilitas, alamat, daftar pemakai TLD, pengesahan' },
  { id: 'spesifikasi', name: 'Spesifikasi Alat', icon: 'box', description: 'Merk, tipe, dan data spesifikasi alat' },
  { id: 'label', name: 'Label Unit dan Tabung', icon: 'scan', description: 'Label fisik unit pesawat dan tabung' },
  { id: 'impor', name: 'Persetujuan Impor', icon: 'filecheck', description: 'Identitas alat dalam dokumen impor' },
  { id: 'kesesuaian', name: 'Uji Kesesuaian', icon: 'check', description: 'Identitas fasilitas dan peralatan' },
  { id: 'fungsi', name: 'Uji Fungsi / Acceptance Test', icon: 'flask', description: 'Uploader gabungan, matching identitas saja' },
  { id: 'paparan', name: 'Uji Paparan Radiasi', icon: 'radiation', description: 'Fasilitas, alamat, peralatan, pengesahan' },
  { id: 'kebocoran', name: 'Uji Kebocoran Tabung', icon: 'activity', description: 'Fasilitas, alamat, peralatan, pengesahan' },
];

export const categoryById = (id: string): DocumentCategory | undefined => CATEGORIES.find((cat) => cat.id === id);
