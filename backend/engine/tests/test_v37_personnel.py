import ast
import re
import unittest
import unicodedata
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / 'app' / 'app.py'
TREE = ast.parse(SOURCE.read_text(encoding='utf-8'))
FUNCS = {n.name: n for n in TREE.body if isinstance(n, ast.FunctionDef)}

class PersonnelUI(unittest.TestCase):
    def test_no_unneeded_sections(self):
        fn = ast.get_source_segment(SOURCE.read_text(encoding='utf-8'), FUNCS['show_personnel_document_result'])
        for label in ('Bagian Penugasan yang Dibaca', 'Lihat Hasil OCR Dokumen', 'Lihat Detail Validasi'):
            self.assertNotIn(label, fn)
        self.assertIn('show_approval_evidence', fn)
    def test_actual_evidence_not_expected_value(self):
        node = FUNCS['_personnel_evidence_text']
        code = compile(ast.Module(body=[node],type_ignores=[]),str(SOURCE),'exec')
        scope={'re':re}
        exec(code,scope)
        fun=scope['_personnel_evidence_text']
        self.assertEqual(fun('Neza Fuad Alfarid Damanik','Petugas: Neza Fuad Alfarid Damanik', 'Nama Petugas Ditugaskan',{}),'Neza Fuad Alfarid Damanik')
        self.assertEqual(fun('Neza Fuad Alfarid Damanik','tidak ada data personel', 'Nama Petugas Ditugaskan',{}),'—')
    def test_scores_cannot_override_backend_status(self):
        fn=ast.get_source_segment(SOURCE.read_text(encoding='utf-8'),FUNCS['_unified_personnel_table'])
        self.assertIn("_compact_normal_status(item.get('Status'))",fn)
        self.assertIn('statuses.append(status)',fn)
        self.assertNotIn("status='MATCH'",fn)
    def test_compile(self):
        compile(SOURCE.read_text(encoding='utf-8'),str(SOURCE),'exec')

if __name__=='__main__': unittest.main()
