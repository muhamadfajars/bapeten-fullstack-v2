import ast
import pathlib
import unittest

APP = pathlib.Path(__file__).resolve().parents[1] / 'app' / 'app.py'
SOURCE = APP.read_text(encoding='utf-8')
TREE = ast.parse(SOURCE)

class ParallelAllCategories(unittest.TestCase):
    def test_all_six_categories_registered(self):
        method = next(n for n in TREE.body if isinstance(n, ast.FunctionDef) and n.name == '_hpc_start_categories')
        src = ast.get_source_segment(SOURCE, method)
        for name in ('label', 'specification', 'import', 'personnel', 'suitability', 'functional'):
            self.assertIn(repr(name) + ':', src)

    def test_worker_definitions_present(self):
        names = {n.name for n in TREE.body if isinstance(n, ast.FunctionDef)}
        for job in ('_hpc_label_category_job', '_hpc_personnel_job', '_hpc_suitability_job', '_hpc_functional_job'):
            self.assertIn(job, names)

    def test_worker_has_no_streamlit_state(self):
        for node in TREE.body:
            if isinstance(node, ast.FunctionDef) and node.name in ('_hpc_personnel_job', '_hpc_suitability_job', '_hpc_functional_job'):
                self.assertNotIn('st.session_state', ast.get_source_segment(SOURCE, node))

    def test_matching_kept_in_main(self):
        for worker in ('_hpc_personnel_job', '_hpc_suitability_job', '_hpc_functional_job'):
            node = next(n for n in TREE.body if isinstance(n, ast.FunctionDef) and n.name == worker)
            self.assertNotIn('match_', ast.get_source_segment(SOURCE, node))

    def test_fallbacks(self):
        for category in ('personnel', 'suitability', 'functional'):
            self.assertIn('f"[HPC-V16]', SOURCE) if False else None
            self.assertIn(f'[HPC-V16] {category} fallback:', SOURCE)

if __name__ == '__main__':
    unittest.main()
