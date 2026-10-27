"""Run: python -m unittest discover -s tests -p 'test_shared_reader_patch.py'"""
import sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
import pymupdf
from src.extraction.document_reader import read_pages
from src.matching.specification_matcher import compare_model

class SharedReaderTests(unittest.TestCase):
    def test_alias_in_form(self):
        r=compare_model('DR-XD 1000 (FDR Nano)','SPESIFIKASI FDR NANO')
        self.assertEqual(r['status'],'MATCH')
        self.assertEqual(r['evidence'].upper(),'FDR NANO')
    def test_unrelated_model(self):
        self.assertNotEqual(compare_model('DR-XD 1000 (FDR Nano)','Az urion 5 M20')['status'],'MATCH')
    def test_scan_fallback(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'scan.pdf'
            d=pymupdf.open();d.new_page();d.save(str(p));d.close()
            with patch('src.extraction.document_reader._ocr',return_value='FUJIFILM\nSPESIFIKASI FDR NANO') as mocked:
                pages=read_pages(p)
            self.assertEqual(pages[0]['method'],'OCR')
            self.assertIn('FUJIFILM',pages[0]['text'])
            mocked.assert_called_once()
    def test_digital_pdf_skip_ocr(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'digital.pdf';d=pymupdf.open();pg=d.new_page()
            pg.insert_text((30,50),'Official document data with serial number ' * 4)
            d.save(str(p));d.close()
            with patch('src.extraction.document_reader._ocr',side_effect=AssertionError('Must not OCR')):
                pages=read_pages(p)
            self.assertEqual(pages[0]['method'],'PDF_TEXT')
if __name__=='__main__':unittest.main()
