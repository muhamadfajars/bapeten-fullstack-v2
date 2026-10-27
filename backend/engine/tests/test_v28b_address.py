import unittest
from src.extraction.program_documents import _retrieve_address, _compare_address_shared, _clean_address_fragment

class TestV28BAddress(unittest.TestCase):
    def test_klinik_multiline(self):
        pages=[{'page':1,'text':'''PROGRAM PERAWATAN
KLINIK INSAN UTAMA BALIKPAPAN
Jl. Mayor TNI AD Ahmad Saili (Imat Saili) RT. 56 No. 24A,
Kelurahan Sumber Rejo, Kecamatan Balikpapan Tengah,
Kota Balikpapan.
Nomor 05/X/SAN/26
Tanggal 01/09/2026'''}]
        candidates=_retrieve_address(pages,'Jl. Mayor TNI AD Ahmad Saili, Kota Balikpapan Kalimantan Timur 76124')
        self.assertTrue(candidates)
        self.assertIn('Kota Balikpapan',candidates[0][3])
        self.assertIn('Kelurahan Sumber Rejo',candidates[0][3])
        self.assertNotIn('Tanggal',candidates[0][3])
    def test_metadata(self):
        self.assertEqual(_clean_address_fragment('Jl. Kesehatan no 2 Pekanbaru Riau Halaman 1 dari 86'), 'Jl. Kesehatan no 2 Pekanbaru Riau')
    def test_no_mismatch_wont_be_hidden(self):
        r=_compare_address_shared('Jl. Kesehatan No. 2, Kota Pekanbaru','Jl. Kesehatan No. 11, Pekanbaru')
        self.assertEqual(r['status'],'MISMATCH')
    def test_optional_province_not_penalized(self):
        r=_compare_address_shared('Jl. Kesehatan No. 2, Kota Pekanbaru Riau','Jalan Kesehatan nomor 2 Pekanbaru')
        self.assertEqual(r['status'],'MATCH')
        self.assertEqual(r['score'],100)
if __name__=='__main__':unittest.main()
