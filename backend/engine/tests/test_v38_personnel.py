import ast
import datetime
import unittest
from pathlib import Path

SOURCE=Path(__file__).resolve().parents[1]/'app'/'app.py'
TREE=ast.parse(SOURCE.read_text(encoding='utf-8'))
FUNCS={n.name:n for n in TREE.body if isinstance(n,ast.FunctionDef)}

def load_function(name,global_vars=None):
    env={'re':__import__('re')}
    if global_vars: env.update(global_vars)
    exec(compile(ast.Module(body=[FUNCS[name]],type_ignores=[]),str(SOURCE),'exec'),env)
    return env[name]

class PersonnelTests(unittest.TestCase):
    def test_expiry_future_match(self):
        fn=load_function('_personnel_date_status')
        future=(datetime.date.today()+datetime.timedelta(days=30)).isoformat()
        self.assertEqual(fn(future),'MATCH')
    def test_expiry_past_mismatch(self):
        fn=load_function('_personnel_date_status')
        self.assertEqual(fn('2020-01-01'),'MISMATCH')
    def test_expiry_missing_review(self):
        fn=load_function('_personnel_date_status')
        self.assertEqual(fn(None),'REVIEW')
    def test_match_needs_evidence(self):
        fn=load_function('_personnel_field_status',{'_compact_normal_status':lambda x:x})
        self.assertEqual(fn(100,'—','REVIEW'),'REVIEW')
        self.assertEqual(fn(100,'Nama Terbukti','REVIEW'),'MATCH')
    def test_names_separate(self):
        code=ast.get_source_segment(SOURCE.read_text(),FUNCS['_unified_personnel_table'])
        self.assertIn("add('Nama Petugas'",code)
        self.assertIn("add('Keahlian'",code)
    def test_only_uploaded_sections(self):
        code=SOURCE.read_text()
        for key in ('suitability_uploads','label_documents_upload','specification_documents_upload','functional_uploads','extra_import_upload'):
            self.assertIn(f"if _uploaded_items('{key}') and",code)

if __name__=='__main__':unittest.main()
