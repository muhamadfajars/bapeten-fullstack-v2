import unittest
import json
from pathlib import Path
from app.classifier import classify_document, classify_by_filename, classify_by_content

class TestClassifier(unittest.TestCase):
    def test_shared_rules_preserve_backend_results(self):
        fixture = Path(__file__).with_name('fixtures') / 'classification_filename_baseline.json'
        for case in json.loads(fixture.read_text(encoding='utf-8')):
            with self.subTest(name=case['name']):
                self.assertEqual(classify_document(case['name']), case['backend'])

    def test_label_and_appointment_filename_variants(self):
        for name in ('20260917112321-sn tube Fix 2.jpg', 'SN_TABUNG_03.png',
                     'sn-generator.jpeg', 'sn unit Fix 2.jpg'):
            with self.subTest(name=name):
                self.assertEqual(classify_by_filename(name)[:2], ('label', None))
        for name in ('20260918090751-Surat Penunjukan PPR FIX 2.jpg',
                     'Surat_Penunjukan_Sebagai_PPR.pdf',
                     'Surat Penunjukan Petugas Proteksi Radiasi.jpg',
                     'Surat Penunjukan sebagai Petugas Proteksi Radiasi.pdf'):
            with self.subTest(name=name):
                self.assertEqual(classify_by_filename(name)[:2], ('personel', 'Surat Penunjukan Tugas'))
        for name in ('sn tubing.jpg', 'Surat Penunjukan Vendor.pdf', 'scan001.jpg'):
            with self.subTest(name=name):
                self.assertIsNone(classify_by_filename(name)[0])

    def test_appointment_content_variants(self):
        for title in ('SURAT PENUNJUKAN SEBAGAI PETUGAS PROTEKSI RADIASI (PPR)',
                      'Surat Penunjukan PPR', 'SURAT PENUNJUKAN\nSEBAGAI\nPPR',
                      'SURAT PENUNJUKAN PETUGAS PROTEKSI RADIASI',
                      'SURAT PENUNJUKAN TUGAS'):
            with self.subTest(title=title):
                self.assertEqual(classify_by_content(title)[:2], ('personel', 'Surat Penunjukan Tugas'))
        self.assertIsNone(classify_by_content('SURAT PENUNJUKAN VENDOR')[0])

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
            ("Laporan Dosis Awal RS Hermina Kepanjen.pdf", "personel", "Evaluasi Dosis / Zero Check"),
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

    def test_conservative_classification(self):
        cases = [
            ('SK PENETAPAN PEKERJA RADIASI DAN PENUNJUKAN PPR.pdf', 'personel', 'Surat Penunjukan Tugas'),
            ('dokumen perawatan Fasilitas Radiodiagnostik.pdf', 'perawatan', None),
            ('DOKUMEN_PERAWATAN_MOBILE.pdf', 'perawatan', None),
            ('PROGRAM PROTEKSI DAN PROGRAM PERAWATAN.pdf', 'unknown', None),
            ('SIP dan SIB.pdf', 'unknown', None),
            ('dokumen perawatan dan spesifikasi alat.pdf', 'unknown', None),
        ]
        for name, category, subtype in cases:
            with self.subTest(name=name):
                result = classify_document(name)
                self.assertEqual((result['category'], result['subtype']), (category, subtype))
        for text in (
            'Untuk melaksanakan program proteksi dan keselamatan radiasi, petugas ditunjuk.',
            'Memastikan seluruh fungsi alat bekerja sesuai spesifikasi pabrikan.',
            'PROGRAM PROTEKSI RADIASI\nPROGRAM PERAWATAN FASILITAS',
            'SURAT IZIN PRAKTIK\nSURAT IZIN BEKERJA (SIB)',
        ):
            with self.subTest(text=text):
                self.assertIsNone(classify_by_content(text)[0])
        self.assertEqual(classify_by_content(
            'DOKUMEN PROGRAM PERAWATAN FASILITAS RADIOLOGI\n'
            'Alat bekerja sesuai spesifikasi pabrikan.')[:2], ('perawatan', None))
        self.assertEqual(classify_by_content(
            'PENETAPAN PEKERJA RADIASI DAN PENUNJUKAN\nPETUGAS PROTEKSI RADIASI (PPR)\n'
            'Untuk pelaksanaan program proteksi dan keselamatan radiasi.')[:2],
            ('personel', 'Surat Penunjukan Tugas'))

    def test_ambiguous_name_does_not_fall_back_to_a_single_content_category(self):
        from unittest.mock import patch
        with patch('app.classifier.extract_document_text', return_value='PROGRAM PERAWATAN FASILITAS') as extract:
            result = classify_document('program proteksi dan program perawatan.pdf', b'content')
            self.assertEqual(result['category'], 'unknown')
            self.assertEqual(result['confidence'], 0)
            extract.assert_not_called()

    def test_known_sample_categories(self):
        # Measure correctness against labeled examples, not the percentage of
        # files receiving any category. Unknown is preferable to a wrong label.
        sample_dir = Path(__file__).resolve().parents[2] / 'frontend/src/data/sample/Tidak Memenuhi'
        cases = [
            ('122761.26', '20260917112321-sn tube Fix 2.jpg', 'label', None, False),
            ('122761.26', '20260918090751-Surat Penunjukan PPR FIX 2.jpg', 'personel', 'Surat Penunjukan Tugas', True),
            ('124143.26', '20260818155148-SK PENETAPAN PEKERJA RADIASI DAN PENUNJUKAN PPR.pdf', 'personel', 'Surat Penunjukan Tugas', True),
            ('124143.26', '20261005140905-dokumen perawatan Fasilitas Radiodiagnostik MABA mobile.pdf', 'perawatan', None, True),
        ]
        if not all((sample_dir / batch / name).is_file() for batch, name, *_ in cases):
            self.skipTest('Local sample documents not available')
        for batch, name, category, subtype, check_content in cases:
            data = (sample_dir / batch / name).read_bytes()
            with self.subTest(name=name):
                result = classify_document(name, data)
                self.assertEqual((result['category'], result['subtype']), (category, subtype))
            if check_content:
                with self.subTest(content_only=name):
                    result = classify_document('scan001' + Path(name).suffix, data)
                    self.assertEqual((result['category'], result['subtype']), (category, subtype))
                    self.assertEqual(result['layer'], 2)

    def test_dose_reports_and_tld_administration(self):
        for title in ('LAPORAN DOSIS AWAL LENCANA OSL', 'LAPORAN DOSIS TLD',
                      'HASIL PEMBACAAN DOSIS OSL', 'LAPORAN HASIL EVALUASI DOSIS', 'DOSIS AWAL'):
            with self.subTest(title=title):
                self.assertEqual(classify_by_filename(title + '.pdf')[:2], ('personel', 'Evaluasi Dosis / Zero Check'))
                self.assertEqual(classify_by_content('NUKLINDOLAB\nLENCANA OSL\n' + title)[:2], ('personel', 'Evaluasi Dosis / Zero Check'))
        for title in ('DAFTAR PEMAKAI TLD', 'DAFTAR PENGGUNA LENCANA OSL', 'PETUGAS TLD', 'KEPESERTAAN PEMANTAUAN OSL'):
            with self.subTest(title=title):
                self.assertEqual(classify_by_filename(title + '.pdf')[0], 'tld')
                self.assertEqual(classify_by_content(title)[0], 'tld')
        for title in ('LENCANA OSL', 'TLD BETA GAMMA', 'NUKLINDOLAB', 'dosimeter'):
            self.assertIsNone(classify_by_filename(title + '.pdf')[0])
            self.assertIsNone(classify_by_content(title)[0])
        self.assertIsNone(classify_by_filename('Laporan Dosis dan Daftar Pemakai TLD.pdf')[0])
        self.assertIsNone(classify_by_content('LAPORAN DOSIS\nDAFTAR PEMAKAI TLD')[0])

    def test_hermina_initial_dose_sample_by_name_and_content(self):
        path = Path(__file__).resolve().parents[2] / 'frontend/src/data/sample/Batch_116843.26/20260714134027-Laporan Dosis Awal RS Hermina Kepanjen Periode Oktober - Desember 2026.pdf'
        if not path.is_file():
            self.skipTest('Local sample document not available')
        for name, layer in ((path.name, 1), ('scan001.pdf', 2)):
            result = classify_document(name, path.read_bytes())
            self.assertEqual((result['category'], result['subtype'], result['layer']),
                             ('personel', 'Evaluasi Dosis / Zero Check', layer))

if __name__ == "__main__":
    unittest.main()

