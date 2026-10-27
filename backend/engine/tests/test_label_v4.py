import unittest
from src.matching.guided_label_matcher import match_serial_field_on_page, match_type_field_on_page
from src.extraction.image_preprocess import label_roi_variants
import numpy as np

class LabelV4Tests(unittest.TestCase):
    def page(self,*rows):
        return {'source_id':1,'source_name':'example','page':1,'ocr':[{'text':s,'confidence':0.9,'box':[10,10,200,40]} for s in rows]}
    def test_insert_exact_not_housing(self):
        self.assertEqual(match_serial_field_on_page('0F1376',self.page('SER. NO.: 20G225','SER. NO.: 0F1376'))['status'],'MATCH')
    def test_ocr_ambiguity_review(self):
        self.assertEqual(match_serial_field_on_page('0F1376',self.page('SER. NO.: OF1376'))['status'],'REVIEW')
    def test_type_exact_label(self):
        self.assertEqual(match_type_field_on_page('KL10-0.6 / 1.8-125',self.page('MODEL: KL10-0.6/1.8-125'))['status'],'MATCH')
    def test_type_ambiguous_not_forced(self):
        self.assertNotEqual(match_type_field_on_page('KL10-0.6 / 1.8-125',self.page('MODEL: KI10-0.6/1.8-125'))['status'],'MATCH')
    def test_fujifilm_both(self):
        self.assertEqual(match_type_field_on_page('DR-XD 1000 (FDR Nano)',self.page('DR-XD 1000','DR-XD 1000PX'))['status'],'MATCH')
    def test_fujifilm_only_px(self):
        self.assertEqual(match_type_field_on_page('DR-XD 1000 (FDR Nano)',self.page('DR-XD 1000PX'))['status'],'REVIEW')
    def test_roi_variants(self):
        img=np.full((150,300,3),190,dtype=np.uint8)
        self.assertEqual(len(label_roi_variants(img,[25,30,150,65])),2)
if __name__=='__main__': unittest.main()
