import ast
import textwrap
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

class RegressionTests(unittest.TestCase):
    def test_summary_counts_variable_defined_before_use(self):
        source=(ROOT/'app/app.py').read_text()
        assert 'mismatched = sum(' in source
        snippet=source[source.index('                        graded = [r for r in checks'):source.index('                        with st.container(border=True):',source.index('                        graded = [r for r in checks'))]
        ast.parse(textwrap.dedent(snippet))
        assert snippet.index('mismatched = sum(')<len(snippet)
        self.assertNotIn('for row in rows',snippet)
    def test_exact_matching_and_conflict(self):
        from src.extraction.program_documents import _field_evidence
        page={'page':14,'text':'A. Data Pesawat Sinar-X\nMerk Unit : FDR NANO\nType Unit : DR-XD1000\nNomor Seri : 56153901\nMerk Tabung : Canon\nModel Tabung : D-125SB\nNomor seri Tabung : B124125'}
        cases=[('merk_unit','Fujifilm','MISMATCH'),('tipe_unit','DR-XD 1000 (FDR Nano)','MATCH'),('nomor_seri_unit','56153901','MATCH'),('merk_tabung','Canon','MATCH'),('tipe_tabung','D125-SB','MATCH'),('nomor_seri_tabung','B124125','MATCH')]
        for key,expected,status in cases:
            with self.subTest(key=key):self.assertEqual(_field_evidence([page],key,expected)['status'],status)
    def test_stray_serial_not_match(self):
        from src.extraction.program_documents import _field_evidence
        p={'page':2,'text':'Tagihan no. 56153901\nNomor seri tabung: B124125'}
        self.assertEqual(_field_evidence([p],'nomor_seri_unit','56153901')['status'],'REVIEW')

if __name__=='__main__': unittest.main()
