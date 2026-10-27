import ast
import pathlib
import unittest

APP = pathlib.Path(__file__).resolve().parents[1] / 'app' / 'app.py'

class TestV34UI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.src = APP.read_text()
    def test_syntax(self):
        ast.parse(self.src)
    def test_persistent_navigation(self):
        self.assertIn('bapeten_active_result_view_v34', self.src)
        self.assertIn('st.radio(', self.src)
        self.assertNotIn('tab_form, tab_matching = st.tabs(', self.src)
    def test_panel_preserved(self):
        self.assertIn('def _matching_panel_toggle(', self.src)
        self.assertIn('on_click=_toggle', self.src)
    def test_program_order(self):
        self.assertIn('program_results_slot_v33', self.src)
        self.assertIn('program_protection_upload', self.src)
    def test_summary(self):
        self.assertIn("c1.metric('Kecocokan terbukti'", self.src)
        self.assertIn('def _v34_wrapped_dataframe_table(', self.src)
    def test_no_lost_results_on_batch(self):
        self.assertIn('if batch_requested:\n                st.session_state["bapeten_active_result_view_v34"] = _match_view',self.src)

if __name__=='__main__': unittest.main()
