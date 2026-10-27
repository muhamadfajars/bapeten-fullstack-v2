import ast
from pathlib import Path
import unittest

SRC=Path(__file__).resolve().parents[1]/'app'/'app.py'
S=SRC.read_text(encoding='utf-8')

class UnifiedUI(unittest.TestCase):
    def test_syntax(self): ast.parse(S)
    def test_two_tabs_kept(self): self.assertIn('tab_form, tab_matching = st.tabs(',S)
    def test_single_click_callback_kept(self): self.assertIn('on_click=_toggle',S)
    def test_metrics(self):
        for val in ["'Kecocokan terbukti'", "'MATCH'", "'REVIEW'", "'MISMATCH'"]:
            self.assertIn(val,S)
    def test_fixed_table(self): self.assertIn('table-layout:fixed',S)
    def test_shared_renderer(self):
        self.assertIn('def _unified_matching_table(rows):',S)
        self.assertIn('def _extra_display_field_table(fields):',S)
        self.assertIn('_unified_matching_metrics(statuses)',S)
        self.assertIn('_unified_matching_table(rows)',S)
    def test_personnel_conversion(self):
        for t in ['SIP','SIB','SPRINT']:
            self.assertIn(f'_unified_personnel_table(validation, "{t}")',S)
        self.assertIn("item.get('Detail'",S)
    def test_category_order(self):
        positions=[S.index("'program_protection_upload': 0"),S.index("'program_maintenance_upload': 1"),S.index("'management_system_upload': 2"),S.index("'technical_documents_upload': 3")]
        self.assertEqual(positions,sorted(positions))
    def test_no_group_title(self): self.assertNotIn('Validasi Program & Dokumen Teknis',S)
    def test_support_evidence(self):
        self.assertIn("Lihat halaman Lembar Pengesahan",S)
        self.assertIn("Lihat pemeriksaan hasil uji (PDF)",S)
    def test_no_nested_expander_added(self):
        self.assertIn('_matching_panel_toggle(',S)

if __name__=='__main__':unittest.main()
