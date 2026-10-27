import unittest
from pathlib import Path

class UnifiedTabs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (Path(__file__).parents[1] / 'app' / 'app.py').read_text()

    def test_only_two_tabs(self):
        self.assertIn('tab_form, tab_matching = st.tabs(', self.source)
        self.assertIn('Matching Semua Dokumen', self.source)
        self.assertNotIn('with tab_program:', self.source)
        self.assertNotIn('with tab_label:', self.source)

    def test_program_after_other_categories(self):
        self.assertLess(self.source.index('show_import_approval_ui(result)'), self.source.index("with tab_matching:\n                st.subheader('Validasi Program & Dokumen Teknis')"))

    def test_preserves_results(self):
        for key in ("Validasi Dokumen Personel", "Validasi Uji Kesesuaian", 'show_functional_test_ui(result)', 'show_import_approval_ui(result)', 'show_specification_section(equipment)', 'v18_program_results'):
            self.assertIn(key, self.source)
