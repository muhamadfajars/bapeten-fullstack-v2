import os
import unittest
from pathlib import Path
from app.classifier import classify_document, classify_by_filename

class TestClassifier(unittest.TestCase):
    def test_layer1_filename_patterns(self):
        tests = [
            ("Formulir_Permohonan-116843.26.pdf", "formulir", None),
            ("PROGRAM PROTEKSI RADIASI RSH kepanjen FIX SIP.pdf", "proteksi", None),
            ("Program perawatan RSH KEPANJEN.pdf", "perawatan", None),
            ("Dok Sistem manajemen fasilitas rs hermina.pdf", "manajemen", None),
            ("DOKUMEN TEKNIS RSH KEPANJEN.pdf", "teknis", None),
            ("SIP RSH KEPANJEN SITI AZIZAH.pdf", "personel", "Surat Izin Praktik (SIP)"),
            ("SIB New zi.pdf", "personel", "Surat Izin Bekerja (SIB)"),
            ("SK Penunjukan dan Pengangkatan Siti Azizah PPR.pdf", "personel", "Surat Penunjukan Tugas"),
            ("sprint neza.pdf", "personel", "Surat Perintah"),
            ("Sertifikat Lulus Kompetensi PPR.pdf", "personel", "Sertifikat Kompetensi"),
            ("SIKR Junaidi.pdf", "personel", "Surat Izin Kerja"),
            ("surat keterangan kerja Radiografer isra new.docx", "personel", "Surat Keterangan Kerja"),
            ("HASIL UJI (ZERO CHECK) TLD BARC.pdf", "personel", "Evaluasi Dosis / Zero Check"),
            ("zero check dr dan dikna.pdf", "personel", "Evaluasi Dosis / Zero Check"),
            ("zero check isra.pdf", "personel", "Evaluasi Dosis / Zero Check"),
            ("Laporan Dosis Awal RS Hermina Kepanjen.pdf", "tld", None),
            ("Brochure_uDR 566i_EN_HD.pdf", "spesifikasi", None),
            ("Foto label tube uDR 566i.jpeg", "label", None),
            ("Persetujuan Impor UDR566i-A.pdf", "impor", None),
            ("250169011_KTUN_Sertifikat_UK jiwa aceh.pdf", "kesesuaian", None),
            ("Hasil Uji Fungsi RS Tk4 Pku.pdf", "fungsi", None),
            ("UPAR XRAY20260714.pdf", "paparan", None),
            ("UJI KEBOCORAN TABUNG ALAT X-RAY FDR NANO.pdf", "kebocoran", None),
        ]
        for filename, expected_cat, expected_sub in tests:
            res = classify_document(filename)
            self.assertEqual(res["category"], expected_cat, f"Failed on {filename}")
            self.assertEqual(res["subtype"], expected_sub, f"Failed subtype on {filename}")
            self.assertEqual(res["layer"], 1)

    def test_sample_batches_accuracy(self):
        sample_dir = Path(__file__).resolve().parents[2] / "frontend" / "src" / "data" / "sample"
        if not sample_dir.is_dir():
            self.skipTest("Sample directory not found")

        total = 0
        classified = 0
        for batch_dir in sample_dir.iterdir():
            if not batch_dir.is_dir():
                continue
            for root, _, files in os.walk(batch_dir):
                for f in files:
                    total += 1
                    fp = Path(root) / f
                    res = classify_document(f, fp.read_bytes())
                    if res["category"] != "unknown":
                        classified += 1

        self.assertGreater(total, 50)
        self.assertEqual(total, classified, f"Expected 100% classification, got {classified}/{total}")

if __name__ == "__main__":
    unittest.main()

