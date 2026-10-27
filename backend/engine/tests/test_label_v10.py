import sys, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.matching import guided_label_matcher as m
# Load only the pure heuristic; runtime PaddleOCR dependencies are unavailable here.
import ast
ocr_src=(ROOT/'src/extraction/label_document_ocr.py').read_text()
func=next(n for n in ast.parse(ocr_src).body if isinstance(n,ast.FunctionDef) and n.name=='_needs_secondary_ocr')
namespace={}
exec(compile(ast.Module(body=[func],type_ignores=[]),'<heuristic>','exec'),namespace)
class e:
    _needs_secondary_ocr=staticmethod(namespace['_needs_secondary_ocr'])

class TestV10(unittest.TestCase):
    def page(self, lines):
        return [{'page':1, 'source_id':1, 'source_name':'example',
                 'ocr':[{'text':x,'variant':v,'confidence':.97} for v in ('original','gray','clahe') for x in lines]}]
    def exp(self, brand):
        return {'unit':{'manufacturer':brand,'type':'Some model','serial_number':'S111'},
                'tabung':{'manufacturer':'Canon','type':'D125-SB','serial_number':'B124125'}}
    def test_negative_alerio_document(self):
        d=self.page(['BRAND: ALERIO','MODEL: ALERIO SMART 4000', 'SER NO: S04KC0425475'])
        r=m.guided_match_label_document(d,self.exp('Fujifilm'))
        self.assertTrue(r['document_identity_conflict'])
        self.assertTrue(all(r[s][f]['status']=='MISMATCH' and r[s][f]['evidence'] is None for s in ('unit','tabung') for f in ('manufacturer','type','serial_number')))
    def test_negative_fujifilm_document(self):
        d=self.page(['FUJIFILM Corporation', 'DR-XD 1000', 'DR-XD 1000PX'])
        r=m.guided_match_label_document(d,self.exp('Alerio'))
        self.assertTrue(r['document_identity_conflict'])
    def test_matching_brand_prevents_rejection(self):
        d=self.page(['FUJIFILM Corporation', 'DR-XD 1000','DR-XD 1000PX','SN 56153901'])
        self.assertIsNone(m._v10_document_rejection(d,self.exp('Fujifilm')))
    def test_retry_glomeda(self):
        self.assertTrue(e._needs_secondary_ocr([{'text':'INSERT MODEL: E7894'},{'text':'SER. NO.: OF1376'}]))
    def test_retry_alerio(self):
        self.assertTrue(e._needs_secondary_ocr([{'text':'MODEL: K110-0.6/1.8-125'},{'text':'SER. NO.: NI04912'}]))
    def test_skip_fujifilm(self):
        self.assertFalse(e._needs_secondary_ocr([{'text':'DR-XD1000'}, {'text':'DR-XD 1000PX'}, {'text':'SN 56153901'}]))

if __name__=='__main__':unittest.main()
