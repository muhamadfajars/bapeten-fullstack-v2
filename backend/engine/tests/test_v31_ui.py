import unittest
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / 'app' / 'app.py'

class V31UiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.s = APP.read_text()
    def test_only_two_tabs(self):
        self.assertIn('["📋 Data Formulir", "✅ Matching Semua Dokumen"]', self.s)
    def test_category_visibility(self):
        for key in ('v31_show_group_0','v31_show_group_1','v31_show_group_2','v31_show_spec','v31_show_functional','v31_show_import'):
            self.assertIn(key,self.s)
    def test_document_visibility(self):
        self.assertIn('v31_show_program_', self.s)
    def test_batch_not_skipped(self):
        self.assertIn('or batch_requested:', self.s)
    def test_no_expander_wrapper(self):
        self.assertNotIn('with st.expander("Tampilkan',self.s)
    def test_valid_python(self):
        compile(self.s, str(APP), 'exec')
if __name__ == '__main__': unittest.main()
