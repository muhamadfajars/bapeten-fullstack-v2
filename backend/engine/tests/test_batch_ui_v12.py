import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / 'app' / 'app.py').read_text(encoding='utf-8')

class BatchUIRegression(unittest.TestCase):
    def test_valid_python(self):
        compile(SOURCE, 'app/app.py', 'exec')
    def test_single_analysis_button(self):
        self.assertEqual(SOURCE.count('key="run_all_document_analysis"'), 1)
        for key in ('run_personnel_validation','run_suitability','run_label_validation',
                    'run_specification_analysis','extra_functional_run','extra_import_run'):
            self.assertNotIn('key="'+key+'"', SOURCE)
            self.assertNotIn("key='"+key+"'", SOURCE)
    def test_all_six_categories_have_batch_gate(self):
        self.assertGreaterEqual(SOURCE.count('st.session_state.get("_batch_run_active")'), 7)
    def test_label_zero_match_gate_wired(self):
        self.assertIn('equipment_list=equipment', SOURCE)
    def test_suitability_result_persisted(self):
        self.assertIn('st.session_state["batch_suitability_view"]', SOURCE)
        self.assertIn('st.session_state.pop("batch_suitability_view", None)', SOURCE)
    def test_uploaders_remain(self):
        for k in ('personnel_documents_upload','suitability_pdf', 'label_documents_upload',
                  'specification_documents_upload','extra_functional_upload','extra_import_upload'):
            self.assertIn(k, SOURCE)

if __name__ == '__main__':
    unittest.main()
