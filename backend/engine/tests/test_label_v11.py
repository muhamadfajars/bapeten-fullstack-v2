import sys, types
for name in ('src.extraction.label_document','src.extraction.label_ocr', 'src.extraction.image_preprocess'):
    m = types.ModuleType(name)
    if name.endswith('.label_document'): m.prepare_label_document = lambda *a, **k: []
    if name.endswith('.label_ocr'): m.extract_ocr = lambda *a, **k: []
    if name.endswith('.image_preprocess'): m.label_roi_variants = lambda *a, **k: []
    sys.modules[name] = m
import unittest
from src.extraction.label_document_ocr import _original_exact_hit, _original_match_count
from src.matching.guided_label_matcher import equipment_to_expected, guided_match_label_document

class TestV11(unittest.TestCase):
    def setUp(self):
        self.fujifilm={'merk_unit':'Fujifilm','tipe_unit':'DR-XD 1000 (FDR Nano)','nomor_seri_unit':'56153901','merk_tabung':'Canon','tipe_tabung':'D125-SB','nomor_seri_tabung':'B124125'}
        self.alerio={'merk_unit':'Alerio','tipe_unit':'Smart 4000','nomor_seri_unit':'S04KC0425475','merk_tabung':'Kailong','tipe_tabung':'KL10-0.6 / 1.8-125','nomor_seri_tabung':'NI04912'}
    def test_reject_foreign_original(self):
        p=[{'ocr':[{'text':'ALERIO'},{'text':'MODEL: SMART 4000'},{'text':'NI04912'}]}]
        self.assertEqual(_original_match_count(p,[self.fujifilm]),0)
    def test_no_px_truncation(self):
        self.assertFalse(_original_exact_hit([{'text':'DR-XD 1000PX'}],'type','DR-XD 1000'))
        self.assertTrue(_original_exact_hit([{'text':'DR-XD 1000'},{'text':'DR-XD 1000PX'}],'type','DR-XD 1000'))
    def test_partial_correct_triggers_secondary(self):
        p=[{'ocr':[{'text':'FUJIFILM Corporation'},{'text':'DR-XD1000'}]}]
        self.assertGreater(_original_match_count(p,[self.fujifilm]),0)
    def test_zero_output_blank(self):
        r=guided_match_label_document([{'original_zero_match':True,'ocr':[{'text':'ALERIO'}]}],equipment_to_expected(self.fujifilm))
        self.assertEqual(r['summary']['status'],'MISMATCH')
        for s in ('unit','tabung'):
            for f in ('manufacturer','type','serial_number'):
                self.assertIsNone(r[s][f]['evidence'])
                self.assertIsNone(r[s][f]['score'])
    def test_alerio_original_brand_detected(self):
        p=[{'ocr':[{'text':'ALERIO'},{'text':'MODEL: K110-0.6/1.8-125'}]}]
        self.assertGreater(_original_match_count(p,[self.alerio]),0)
if __name__=='__main__': unittest.main()

class TestPipeline(unittest.TestCase):
    def test_zero_gate_skips_variants(self):
        from unittest.mock import patch
        from src.extraction import label_document_ocr as m
        f={'merk_unit':'Fujifilm','tipe_unit':'DR-XD 1000','nomor_seri_unit':'56153901','merk_tabung':'Canon','tipe_tabung':'D125-SB','nomor_seri_tabung':'B124125'}
        with patch.object(m,'prepare_label_document',return_value=[{'image':'mock','source_type':'pdf','page':1,'width':800,'height':600}]), \
             patch.object(m,'extract_ocr',return_value=[{'text':'ALERIO','confidence':0.98}]), \
             patch.object(m,'_full_page_ocr_variants',side_effect=AssertionError('secondary OCR called')):
            got=m.ocr_label_documents([{'path':'a.pdf','name':'a.pdf'}],equipment_list=[f])
        self.assertTrue(got[0]['original_zero_match'])
        self.assertEqual(len(got[0]['ocr']),1)
    def test_positive_gate_keeps_original(self):
        from unittest.mock import patch
        from src.extraction import label_document_ocr as m
        a={'merk_unit':'Alerio','tipe_unit':'Smart 4000','nomor_seri_unit':'S04KC0425475','merk_tabung':'Kailong','tipe_tabung':'KL10-0.6 / 1.8-125','nomor_seri_tabung':'NI04912'}
        with patch.object(m,'prepare_label_document',return_value=[{'image':'mock','source_type':'pdf','page':1,'width':800,'height':600}]), \
             patch.object(m,'extract_ocr',return_value=[{'text':'ALERIO','confidence':0.98}]), \
             patch.object(m,'_full_page_ocr_variants',return_value=[{'text':'ALERIO','variant':'original'}]):
            got=m.ocr_label_documents([{'path':'a.pdf','name':'a.pdf'}],equipment_list=[a])
        self.assertNotIn('original_zero_match',got[0])
