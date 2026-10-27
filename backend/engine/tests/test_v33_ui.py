import ast, unittest
from pathlib import Path
class TestUnifiedPanelsV33(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.s=(Path(__file__).resolve().parents[1]/'app/app.py').read_text()
    def test_syntax(self): ast.parse(self.s)
    def test_callback_before_rerun(self):
        self.assertIn('on_click=_toggle',self.s)
        self.assertIn('return bool(st.session_state[state_key])',self.s)
        self.assertNotIn('if st.button(f"{arrow}  {title}"',self.s)
    def test_program_first(self):
        self.assertLess(self.s.index('program_results_slot_v33 = st.container()'),self.s.index('_show_group_v31_0 ='))
        self.assertIn('with program_results_slot_v33:',self.s)
    def test_no_filename_in_header(self):
        self.assertIn('_panel_title_v33,',self.s)
        self.assertNotIn("st.subheader('Validasi Program & Dokumen Teknis')", self.s)
    def test_category_order(self):
        values=['program_protection_upload','program_maintenance_upload','management_system_upload','technical_documents_upload']
        snippet=self.s.split('_program_order_v33 = {',1)[1].split('}',1)[0]
        self.assertEqual([x for x in values if x in snippet],values)
    def test_batch_logic_preserved(self):
        self.assertIn('if _show_group_v31_0 or batch_requested:',self.s)
        self.assertIn('if batch_requested:',self.s)
