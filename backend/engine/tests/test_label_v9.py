import unittest
from src.matching.guided_label_matcher import guided_match_label_document

FUJI={'unit':{'manufacturer':'Fujifilm','type':'DR-XD 1000 (FDR Nano)','serial_number':'56153901'},'tabung':{'manufacturer':'Canon','type':'D125-SB','serial_number':'B124125'}}
ALERIO={'unit':{'manufacturer':'Alerio','type':'Smart 4000','serial_number':'S04KC0425475'},'tabung':{'manufacturer':'Kailong','type':'KL10-0.6 / 1.8-125','serial_number':'NI04912'}}
A_ROWS=['GENERATOR:', 'BRAND: ALERIO','MODEL: ALERIO SMART 4000','SER. NO.: S04KC0425475', 'INSERTION TUBE:', 'BRAND: KAILONG','MODEL: KL10-0.6/1.8-125','SER. NO.: NI04912']
F_ROWS=['FUJIFILM Corporation','MOBILE DIGITAL X-RAY SYSTEM','DR-XD1000','MOBILE X-RAY UNIT','DR-XD 1000PX','SN 56153901']
def pack(rows, variants=('original','gray','clahe')):
 return [{'source_id':'test','page':1,'ocr':[{'text':s,'variant':v,'confidence':.97} for v in variants for s in rows]}]
class TestV9(unittest.TestCase):
 def test_fujifilm_form_alerio_doc(self):
  x=guided_match_label_document(pack(A_ROWS),FUJI)
  self.assertTrue(x['document_identity_conflict'])
  self.assertEqual(x['summary']['status'],'MISMATCH')
  for s in ('unit','tabung'):
   for f in ('manufacturer','type','serial_number'):
    self.assertEqual(x[s][f]['status'],'MISMATCH');self.assertIsNone(x[s][f]['evidence']);self.assertIsNone(x[s][f]['score'])
 def test_alerio_form_fujifilm_doc(self):
  x=guided_match_label_document(pack(F_ROWS),ALERIO)
  self.assertTrue(x['document_identity_conflict'])
  self.assertEqual(x['identity_evidence']['detected_unit_brand'],'FUJIFILM')
  self.assertEqual(x['summary']['status'],'MISMATCH')
  self.assertIsNone(x['unit']['manufacturer']['evidence'])
 def test_same_document_not_rejected(self):
  x=guided_match_label_document(pack(A_ROWS),ALERIO)
  self.assertFalse(x['document_identity_conflict'])
  self.assertEqual(x['summary']['status'],'VALID')
 def test_unreadable_not_mismatch(self):
  x=guided_match_label_document(pack(['CAUTION','MADE IN INDIA']),FUJI)
  self.assertFalse(x['document_identity_conflict'])
  self.assertNotEqual(x['summary']['status'],'MISMATCH')
 def test_single_variant_not_enough_to_reject(self):
  x=guided_match_label_document(pack(['FUJIFILM Corporation'],('original',)),ALERIO)
  self.assertFalse(x['document_identity_conflict'])
 def test_mixed_manufacturers_not_globally_rejected(self):
  x=guided_match_label_document(pack(['FUJIFILM Corporation','BRAND: ALERIO']),{'unit':{'manufacturer':'Siemens'},'tabung':{}})
  self.assertFalse(x['document_identity_conflict'])
if __name__=='__main__':unittest.main()
