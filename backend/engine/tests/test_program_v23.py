import unittest
from src.extraction.program_documents import _compare_device, _field_evidence, _approval

class TestV23Matching(unittest.TestCase):
    def test_different_brand_is_mismatch(self):
        self.assertEqual(_compare_device('Fujifilm','FDR Nano','merk_unit')['status'],'MISMATCH')
    def test_same_brand_match(self):
        self.assertEqual(_compare_device('Canon','Canon','merk_tabung')['status'],'MATCH')
    def test_model_suffix_match(self):
        self.assertEqual(_compare_device('DR-XD 1000 (FDR Nano)','DR-XD 1000','tipe_unit')['status'],'MATCH')
    def test_model_hyphen_variation(self):
        self.assertEqual(_compare_device('D125-SB','D125SB','tipe_tabung')['status'],'MATCH')
    def test_unknown_is_review(self):
        self.assertEqual(_field_evidence([{'page':1,'text':'An example 56153901 without labels'}],'nomor_seri_unit','56153901')['status'],'REVIEW')
    def test_labeled_mismatch(self):
        self.assertEqual(_field_evidence([{'page':1,'text':'Merk pesawat sinar-X : FDR Nano'}],'merk_unit','Fujifilm')['status'],'MISMATCH')
    def test_approval_heading(self):
        self.assertEqual(_approval([{'page':2,'text':'LEMBAR PENGESAHAN\nDirektur\nNama\nTanggal'}])[0]['page'],2)

if __name__ == '__main__':unittest.main()
