import unittest
from src.extraction.program_documents import (_extract_personnel, _field_evidence,
    _retrieve_address, _clean_address_fragment)

class V29Regressions(unittest.TestCase):
    def test_personnel_typo_candidate(self):
        pages=[{'page':8,'text':'Nama Petugas: dr. Adimas Okto Anugrah, Sp.Rad'}]
        r=_extract_personnel(pages,[{'nama':'dr. Adimas Okto Nugroho, Sp.Rad'}])[0]
        self.assertEqual(r['status'],'REVIEW')
        self.assertIn('Anugrah',r['observed'])
        self.assertIsNotNone(r['score'])
    def test_personnel_exact(self):
        pages=[{'page':8,'text':'Nama: dr. Adimas Okto Nugroho, Sp.Rad'}]
        r=_extract_personnel(pages,[{'nama':'dr. Adimas Okto Nugroho, Sp.Rad'}])[0]
        self.assertEqual(r['status'],'MATCH')
    def test_bare_merk_in_tube_block(self):
        pages=[{'page':12,'text':'''Merek/Pabrikan : Alerio/ Iatome Electric India Pvt Ltd.
Tipe/Model : Smart 4000
Serial Number Generator : S04KC0425475
Serial Number Tube Head Sinar-X : TH022504
Serial Number Insersi : NI04912
Model/type : KL10-0.6/1.8-125
Merk : Kailong
Tegangan Maksimum : 110 kV'''}]
        r=_field_evidence(pages,'merk_tabung','Kailong')
        self.assertEqual(r['status'],'MATCH')
        self.assertEqual(r['observed'],'Kailong')
    def test_bare_merk_without_tube_context_not_auto_match(self):
        pages=[{'page':12,'text':'Merk : Kailong'}]
        r=_field_evidence(pages,'merk_tabung','Kailong')
        self.assertEqual(r['status'],'REVIEW')
    def test_address_metadata_is_removed(self):
        self.assertEqual(_clean_address_fragment('Jl. Mayor TNI AD Ahmad Saili RT. 56 No. 24A, Kecamatan Balikpapan Halaman Tengah, Kota Balikpapan'),
            'Jl. Mayor TNI AD Ahmad Saili RT. 56 No. 24A, Kecamatan Balikpapan Tengah, Kota Balikpapan')
    def test_address_multiline(self):
        pages=[{'page':1,'text':'KLINIK INSAN UTAMA BALIKPAPAN\nJl. Mayor TNI AD Ahmad Saili (Imat Saili) RT. 56 No. 24A,\nKelurahan Sumber Rejo, Kecamatan Balikpapan Tengah,\nKota Balikpapan.\nHalaman 1 dari 25'}]
        r=_retrieve_address(pages,'Jl. Mayor TNI AD Ahmad Saili, Kota Balikpapan Kalimantan Timur 76124')
        self.assertIn('Kota Balikpapan',r[0][3])
        self.assertNotIn('Halaman',r[0][3])
if __name__=='__main__':unittest.main()
