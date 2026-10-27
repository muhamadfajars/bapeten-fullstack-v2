import unittest
from src.matching.guided_label_matcher import _match_parenthetical_type, match_serial_field_on_page
from src.extraction.image_preprocess import label_roi_variants
import numpy as np

class TestLabelV5(unittest.TestCase):
    def test_two_distinct_models(self):
        page={'page':1,'ocr':[{'text':'DR-XD 1000PX','variant':'original'}, {'text':'DR-XD 1000','variant':'roi_sharpen'}]}
        result=_match_parenthetical_type('DR-XD 1000 (FDR Nano)',page)
        self.assertEqual(result['status'],'MATCH')
        self.assertEqual(result['components'][0]['evidence'],'DR-XD 1000')
    def test_px_alone_is_not_match(self):
        page={'page':1,'ocr':[{'text':'DR-XD 1000PX','variant':'original'}]}
        self.assertNotEqual(_match_parenthetical_type('DR-XD 1000 (FDR Nano)',page)['status'],'MATCH')
    def test_serial_exact_rescan_over_original_ambiguity(self):
        page={'page':1,'ocr':[{'text':'SER. NO.: OF1376','variant':'original'}, {'text':'SER. NO.: 0F1376','variant':'roi_clahe'}]}
        self.assertEqual(match_serial_field_on_page('0F1376',page)['status'],'MATCH')
    def test_serial_review_without_exact(self):
        page={'page':1,'ocr':[{'text':'SER. NO.: OF1376','variant':'original'}]}
        self.assertEqual(match_serial_field_on_page('0F1376',page)['status'],'REVIEW')
    def test_variants(self):
        img=np.zeros((170,380,3),dtype=np.uint8)
        names=[n for n,_ in label_roi_variants(img,[10,20,150,40])]
        self.assertEqual(names,['roi_gray','roi_clahe','roi_sharpen','roi_adaptive'])
if __name__ == '__main__': unittest.main()
