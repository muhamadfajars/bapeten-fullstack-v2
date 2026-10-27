import ast
import pathlib
import unittest

APP = pathlib.Path(__file__).resolve().parents[1] / 'app' / 'app.py'

class TestHpcBatchV14(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.src = APP.read_text(encoding='utf-8')
        cls.tree = ast.parse(cls.src)
        cls.funcs = {node.name: node for node in cls.tree.body if isinstance(node, ast.FunctionDef)}

    def test_worker_functions_present(self):
        for name in ('_hpc_worker_count', '_hpc_run_file_jobs', '_hpc_spec_job', '_hpc_import_job'):
            self.assertIn(name, self.funcs)

    def test_workers_never_call_streamlit(self):
        for name in ('_hpc_spec_job', '_hpc_import_job'):
            node = self.funcs[name]
            self.assertFalse(any(isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id == 'st' for n in ast.walk(node)))

    def test_both_file_sections_use_workers(self):
        for name in ('show_specification_section', 'show_import_approval_ui'):
            node = self.funcs[name]
            calls = [n.func.id for n in ast.walk(node) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)]
            self.assertIn('_hpc_run_file_jobs', calls)

    def test_file_cleanup(self):
        for name in ('show_specification_section', 'show_import_approval_ui'):
            self.assertIn('safe_delete', ast.get_source_segment(self.src, self.funcs[name]))

    def test_label_parallel_preserved(self):
        label = pathlib.Path(__file__).resolve().parents[1] / 'src' / 'extraction' / 'label_document_ocr.py'
        text = label.read_text()
        self.assertIn('BAPETEN_LABEL_WORKERS', text)
        self.assertIn('BAPETEN_LABEL_PARALLEL', text)

if __name__ == '__main__':
    unittest.main()
