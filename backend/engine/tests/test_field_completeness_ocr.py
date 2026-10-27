import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import pymupdf
from src.extraction.document_reader import read_pages, retry_ocr_for_missing


class FieldCompletenessTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.path=Path(self.tmp.name)/'document.pdf'
        doc=pymupdf.open()
        page=doc.new_page()
        page.insert_text((50,70),'General introduction and requirements '*7)
        doc.save(str(self.path));doc.close()

    def tearDown(self):
        self.tmp.cleanup()

    def test_no_missing_no_ocr(self):
        pages=read_pages(self.path)
        with patch('src.extraction.document_reader._ocr',side_effect=AssertionError('unnecessary OCR')):
            out,info=retry_ocr_for_missing(self.path,pages,[])
        self.assertEqual(out,pages)
        self.assertEqual(info['retried_pages'],[])

    def test_missing_trigger_augments_without_losing_text(self):
        pages=read_pages(self.path)
        with patch('src.extraction.document_reader._ocr',return_value='Merk Unit: Fujifilm') as mock:
            out,info=retry_ocr_for_missing(self.path,pages,['merk_unit'])
        self.assertEqual(mock.call_count,1)
        self.assertEqual(info['retried_pages'],[1])
        self.assertIn('Fujifilm',out[0]['text'])
        self.assertIn('General introduction',out[0]['text'])
        self.assertEqual(out[0]['method'],'PDF_TEXT_PLUS_OCR')

    def test_already_ocr_page_not_reprocessed(self):
        pages=[{'page':1,'method':'OCR','text':'value','lines':['value']}]
        with patch('src.extraction.document_reader._ocr',side_effect=AssertionError('duplicate')):
            result,diag=retry_ocr_for_missing(self.path,pages,['merk_unit'])
        self.assertEqual(result,pages)
        self.assertEqual(diag['retried_pages'],[])

if __name__=='__main__':unittest.main()
