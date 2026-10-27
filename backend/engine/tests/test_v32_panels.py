import ast, unittest
from pathlib import Path
class TestPanels(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.src=(Path(__file__).resolve().parents[1]/'app'/'app.py').read_text()
    def test_valid_python(self): ast.parse(self.src)
    def test_clickable_headers(self):
        self.assertIn('def _matching_panel_toggle(',self.src)
        self.assertIn('if st.button(f"{arrow}  {title}"', self.src)
        self.assertNotIn('st.checkbox("Tampilkan',self.src)
    def test_all_sections(self):
        for key in ('personnel','suitability','equipment','specification','functional','import','program_'):
            self.assertIn(key,self.src)
    def test_processing_preserved(self):
        self.assertIn('if _show_group_v31_0 or batch_requested:', self.src)
        self.assertIn("_hpc_finish_categories(_rt)",self.src)
