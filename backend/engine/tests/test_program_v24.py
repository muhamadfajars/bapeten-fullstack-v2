import unittest
from src.extraction.program_documents import _field_evidence, _compare_device

class MatchingRegression(unittest.TestCase):
    def test_canon(self):
        pages=[{'page':2,'text':'Merek tabung : Canon\nTipe tabung : D-125SB'}]
        self.assertEqual(_field_evidence(pages,'merk_tabung','Canon')['status'],'MATCH')
    def test_contradictory_strong_values_review(self):
        pages=[{'page':2,'text':'Merk tabung : Canon\nMerk tabung : Fujifilm'}]
        self.assertEqual(_field_evidence(pages,'merk_tabung','Canon')['status'],'REVIEW')
    def test_brand_difference(self):
        self.assertEqual(_compare_device('Fujifilm','FDR Nano','merk_unit')['status'],'MISMATCH')
    def test_type_normalization(self):
        self.assertEqual(_compare_device('DR-XD 1000 (FDR Nano)','DR-XD 1000','tipe_unit')['status'],'MATCH')
if __name__=='__main__':unittest.main()
