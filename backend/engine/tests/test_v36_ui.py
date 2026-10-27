import ast
from pathlib import Path
import unittest

SOURCE = Path(__file__).resolve().parents[1] / 'app' / 'app.py'
TEXT = SOURCE.read_text(encoding='utf-8')
TREE = ast.parse(TEXT)

class TestV36UI(unittest.TestCase):
    def test_syntax(self):
        self.assertIsInstance(TREE, ast.Module)

    def test_sibling_panels(self):
        lines = TEXT.splitlines()
        labels = ['_show_group_v31_2 =', '_visible_v31_spec =',
                  '_visible_v31_functional =', '_visible_v31_import =']
        indents = []
        for label in labels:
            candidates = [line for line in lines if label in line]
            self.assertEqual(len(candidates), 1, label)
            indents.append(len(candidates[0]) - len(candidates[0].lstrip()))
        self.assertEqual(indents, [16, 16, 16, 16])

    def test_single_click_panel(self):
        self.assertIn('on_click=_toggle', TEXT)

    def test_personnel_independent_panels(self):
        self.assertIn("_matching_panel_toggle(title, f'personnel_file_{index}_{kind}')", TEXT)
        self.assertNotIn('st.header(\n                                "Hasil Validasi Dokumen Personel"',TEXT)

    def test_approval_is_collapsed(self):
        self.assertIn('with st.expander("Lihat bukti pengesahan", expanded=False):', TEXT)
        approval = next(n for n in TREE.body if isinstance(n,ast.FunctionDef) and n.name=='show_approval_evidence')
        expanders=[]
        for n in ast.walk(approval):
            if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr == 'expander':
                expanders.append(n)
        self.assertEqual(len(expanders), 1)

    def test_results_pdf_closed(self):
        self.assertIn("with st.expander('Lihat pemeriksaan hasil uji (PDF)', expanded=False)",TEXT)
        self.assertNotIn("with st.expander('📄 Lihat dokumen asli per halaman', expanded=True)",TEXT)

    def test_metrics_and_table_for_personnel(self):
        fn = next(n for n in TREE.body if isinstance(n,ast.FunctionDef) and n.name=='_unified_personnel_table')
        content=ast.get_source_segment(TEXT,fn)
        self.assertIn('_unified_matching_metrics(statuses)', content)
        self.assertIn('_unified_matching_table(rows)', content)
        self.assertNotIn("'Dokumen': item.get('Dokumen', item.get('Hasil Dokumen', item.get('Detail'",content)

if __name__=='__main__': unittest.main()
