import unittest
from src.matching.guided_label_matcher import guided_match_label_document

EXPECTED={'unit':{'manufacturer':'Fujifilm','type':'DR-XD 1000 (FDR Nano)','serial_number':'56153901'},'tabung':{'manufacturer':'Canon','type':'D125-SB','serial_number':'B124125'}}
ROWS=['GENERATOR:','BRAND: ALERIO','MODEL: ALERIO SMART 4000','SER. NO.: S04KC0425475','INSERTION TUBE:','BRAND: KAILONG','MODEL: KL10-0.6/1.8-125','SER. NO.: NI04912','CAUTION','JAN 25','MADE IN INDIA']
def pack(lines):
 return [{'source_id':'a','source_name':'a.pdf','page':1,'ocr':[{'text':v,'confidence':.97,'variant':'gray'} for v in lines]}]
class Check(unittest.TestCase):
 def test_negative_evidence(self):
  out=guided_match_label_document(pack(ROWS), EXPECTED)
  self.assertEqual(out['unit']['manufacturer']['evidence'],'ALERIO')
  self.assertEqual(out['unit']['type']['evidence'],'ALERIO SMART 4000')
  self.assertEqual(out['unit']['serial_number']['evidence'],'S04KC0425475')
  self.assertEqual(out['tabung']['manufacturer']['evidence'],'KAILONG')
  self.assertEqual(out['tabung']['type']['evidence'],'KL10-0.6/1.8-125')
  self.assertEqual(out['tabung']['serial_number']['evidence'],'NI04912')
  self.assertEqual(out['summary']['status'],'MISMATCH')
 def test_unknown_is_review(self):
  out=guided_match_label_document(pack(['CAUTION','JAN 25','MADE IN INDIN']), EXPECTED)
  self.assertEqual(out['unit']['manufacturer']['status'],'REVIEW')
  self.assertIsNone(out['unit']['manufacturer']['evidence'])
 def test_positive_fujifilm_px_not_used(self):
  lines=['FUJIFILM Corporation','DR-XD1000','DR-XD 1000PX','56153901','CANON ELECTRON TUBES & DEVICES CO., LTD.','D-125SB','B124125']
  out=guided_match_label_document(pack(lines), EXPECTED)
  self.assertEqual(out['unit']['type']['status'],'MATCH')
  self.assertEqual(out['unit']['type']['components'][0]['evidence'],'DR-XD1000')
 def test_px_only_no_match(self):
  out=guided_match_label_document(pack(['FUJIFILM','DR-XD1000PX','56153901']), EXPECTED)
  self.assertNotEqual(out['unit']['type']['status'],'MATCH')
 def test_alerio_positive(self):
  exp={'unit':{'manufacturer':'Alerio','type':'Smart 4000','serial_number':'S04KC0425475'},'tabung':{'manufacturer':'Kailong','type':'KL10-0.6 / 1.8-125','serial_number':'NI04912'}}
  out=guided_match_label_document(pack(ROWS),exp)
  self.assertEqual(out['summary']['status'],'VALID')
if __name__=='__main__':unittest.main()
