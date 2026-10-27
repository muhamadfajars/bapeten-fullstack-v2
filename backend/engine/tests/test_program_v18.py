import os
import tempfile
import unittest
import fitz
from src.extraction.program_documents import analyze

class ProgramDocumentTests(unittest.TestCase):
    def create_pdf(self, pages):
        handle=tempfile.NamedTemporaryFile(suffix='.pdf',delete=False)
        handle.close()
        doc=fitz.open()
        for txt in pages:
            page=doc.new_page()
            page.insert_textbox(fitz.Rect(40,50,550,750),txt,fontsize=10)
        doc.save(handle.name)
        doc.close()
        self.addCleanup(lambda: os.unlink(handle.name))
        return handle.name

    def test_maintenance_frequency_varies_by_document(self):
        pages=['DAFTAR ISI\n4.4 Pemeriksaan dan Pengujian Teknis ........ 27',
               '4.4 Pemeriksaan dan Pengujian Teknis\n4.4.3 Uji Kesesuaian (Constancy Test)\nTujuan: Memastikan performa pesawat.\nFrekuensi:\nSetelah pemasangan alat baru.\nSetelah perbaikan atau penggantian tabung.\nSetiap 4 tahun sekali.\nParameter yang diuji meliputi:\n1. Konsistensi kV dan mA terhadap nilai set.\n2. Waktu eksposi dan kesesuaian pengaturan.']
        res=analyze(self.create_pdf(pages),'program_maintenance_upload')
        self.assertEqual(res['maintenance']['toc_status'],'FOUND')
        self.assertEqual(res['maintenance']['section_status'],'FOUND')
        self.assertIn('4 tahun',str(res['maintenance']['section']))
        self.assertNotIn('12 bulan',str(res['maintenance']['section']))
    def test_approval_just_keyword_not_certified(self):
        res=analyze(self.create_pdf(['Lembar Pengesahan\nDirektur RS','Dokumen Sistem Manajemen']), 'management_system_upload')
        self.assertEqual(res['approval']['status'],'INDIKASI')
        self.assertEqual(res['hospital']['status'],'REVIEW')
    def test_no_false_match_in_empty(self):
        res=analyze(self.create_pdf(['Sistem manajemen\n Tidak ada data instansi pada halaman ini.']), 'management_system_upload',{'instansi':'RS Fiktif','alamat_proyek':'Jl. Fiktif'})
        self.assertEqual(res['hospital']['status'],'REVIEW')
        self.assertEqual(res['approval']['status'],'REVIEW')

if __name__=='__main__': unittest.main()
