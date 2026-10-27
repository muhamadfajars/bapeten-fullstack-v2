import unittest
from src.extraction.general_info import extract_general_info
from src.extraction.program_documents import _field_evidence

class TestV25(unittest.TestCase):
    def test_facility_not_institution(self):
        text=('Instansi: Dinas Kesehatan\nAlamat Proyek: Klinik Insan Utama Balikpapan, '
              'Jl. Mayor TNI AD Ahmad Saili, Kota Balikpapan Kalimantan Timur 76124, '
              'Telp.0857-5232-3293\nA. Kelengkapan Administrasi')
        d=extract_general_info(text)
        self.assertEqual(d['nama_fasilitas'],'Klinik Insan Utama Balikpapan')
        self.assertEqual(d['instansi'],d['nama_fasilitas'])
        self.assertEqual(d['alamat_proyek'], 'Jl. Mayor TNI AD Ahmad Saili, Kota Balikpapan Kalimantan Timur 76124')
    def test_equipment_picture(self):
        pages=[{'page':3,'text':'A. Data Pesawat Sinar-X\nMerk Unit : FDR NANO\nType Unit : DR-XD1000\nNomor Seri : 56153901\nMerk Tabung : Canon\nModel Tabung : D-125SB\nNomor seri Tabung : B124125'}]
        cases=[('merk_unit','Fujifilm','MISMATCH'),('tipe_unit','DR-XD 1000 (FDR Nano)','MATCH'),('nomor_seri_unit','56153901','MATCH'),('merk_tabung','Canon','MATCH'),('tipe_tabung','D125-SB','MATCH'),('nomor_seri_tabung','B124125','MATCH')]
        for key,expected,status in cases:
            with self.subTest(key=key):
                self.assertEqual(_field_evidence(pages,key,expected)['status'],status)
    def test_stray_serial_not_auto_match(self):
        pages=[{'page':2,'text':'Invoice 56153901\nNomor seri tabung: B124125'}]
        self.assertEqual(_field_evidence(pages,'nomor_seri_unit','56153901')['status'],'REVIEW')
if __name__=='__main__':unittest.main()
