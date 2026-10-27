from pathlib import Path
import unittest
app = Path(__file__).resolve().parents[1] / 'app' / 'app.py'
s = app.read_text()
class IntakeSmoke(unittest.TestCase):
    def test_category_count(self):
        self.assertEqual(s.count('("Program Proteksi Radiasi",'), 1)
        self.assertIn('("Uji Kebocoran Tabung",',s)
    def test_central_upload_only(self):
        self.assertEqual(s.count('st.file_uploader('), 2)
    def test_fixed_height_panels(self):
        self.assertIn('st.container(height=510', s)
        self.assertIn('st.container(height=690', s)
    def test_form_optional_upload(self):
        self.assertIn('form_pdf_files[0]',s)
    def test_parallel_kept(self):
        self.assertIn("_hpc_start_categories(equipment, result)",s)
if __name__ == '__main__': unittest.main()
