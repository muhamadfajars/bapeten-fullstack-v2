import unittest
from src.extraction.program_documents import _approval

class TestV19(unittest.TestCase):
    def test_toc_does_not_count_as_approval(self):
        pages=[{'page':3,'text':'DAFTAR ISI\nLembar Pengesahan ................. i\nBab I Pendahuluan ....... 1'}]
        self.assertEqual(_approval(pages),[])
    def test_real_candidate_requires_supporting_text(self):
        pages=[{'page':2,'text':'LEMBAR PENGESAHAN\nDokumen Program Perawatan\nDisahkan oleh: Direktur Rumah Sakit\nTanggal: 12 Oktober 2026'}]
        self.assertEqual(_approval(pages)[0]['page'],2)
    def test_bare_keyword_not_enough(self):
        self.assertEqual(_approval([{'page':2,'text':'Referensi Lembar Pengesahan saja'}]),[])

if __name__=='__main__': unittest.main()
