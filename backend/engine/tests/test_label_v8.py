import unittest
from src.matching.guided_label_matcher import guided_match_label_document
EXP={'unit':{'manufacturer':'Fujifilm','type':'DR-XD 1000 (FDR Nano)','serial_number':'56153901'},'tabung':{'manufacturer':'Canon','type':'D125-SB','serial_number':'B124125'}}
NEG=['GENERATOR:','BRAND: ALERIO','MODEL: ALERIO SMART 4000','SER. NO.: S04KC0425475','INSERTION TUBE:','BRAND: KAILONG','MODEL: KL10-0.6/1.8-125','SER. NO.: NI04912','CAUTION']
def pack(rows): return [{'source_id':'a','page':1,'ocr':[{'text':x,'confidence':.97,'variant':'gray'} for x in rows]}]
class V8(unittest.TestCase):
 def test_negative_document(self):
  out=guided_match_label_document(pack(NEG),EXP)
  self.assertTrue(out['cross_device_conflict'])
  self.assertEqual(out['summary']['status'],'MISMATCH')
  self.assertEqual(out['unit']['manufacturer']['evidence'],'ALERIO')
  self.assertEqual(out['tabung']['manufacturer']['evidence'],'KAILONG')
  for s in ('unit','tabung'):
   for k in ('type','serial_number'):
    f=out[s][k];self.assertEqual(f['status'],'MISMATCH');self.assertIsNone(f['evidence']);self.assertIsNone(f['score'])
 def test_blurred_not_mismatch(self):
  out=guided_match_label_document(pack(['CAUTION','MADE IN INDIA']),EXP)
  self.assertFalse(out['cross_device_conflict'])
  self.assertNotEqual(out['summary']['status'],'MISMATCH')
 def test_positive_alerio(self):
  exp={'unit':{'manufacturer':'Alerio','type':'Smart 4000','serial_number':'S04KC0425475'},'tabung':{'manufacturer':'Kailong','type':'KL10-0.6 / 1.8-125','serial_number':'NI04912'}}
  out=guided_match_label_document(pack(NEG),exp)
  self.assertEqual(out['summary']['status'],'VALID')
 def test_fujifilm_suffix(self):
  out=guided_match_label_document(pack(['FUJIFILM','DR-XD1000PX','56153901']),EXP)
  self.assertNotEqual(out['unit']['type']['status'],'MATCH')
if __name__=='__main__':unittest.main()
