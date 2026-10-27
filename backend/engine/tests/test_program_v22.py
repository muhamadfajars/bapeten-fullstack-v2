import unittest
from src.extraction.program_documents import _approval

def pages(*texts): return [{'page':i+1,'text':v} for i,v in enumerate(texts)]
class TestApproval(unittest.TestCase):
 def test_simple(self): self.assertEqual(_approval(pages('LEMBAR PENGESAHAN\nRS Jiwa Aceh'))[0]['page'],1)
 def test_toc(self): self.assertEqual(_approval(pages('DAFTAR ISI\nLembar Pengesahan .... ii\nBAB I .... 1')),[])
 def test_merged_heading(self): self.assertEqual(_approval(pages('LEMBAR PENGESAHAN RUMAH SAKIT JIWA ACEH\nDisetujui oleh Kepala'))[0]['page'],1)
 def test_spaced(self): self.assertEqual(_approval(pages('L E M B A R  P E N G E S A H A N\nRS Jiwa Aceh'))[0]['page'],1)
 def test_non_heading_sentence(self): self.assertEqual(_approval(pages('Pada bagian ini dijelaskan lembar pengesahan dokumen.')),[])
if __name__=='__main__':unittest.main()
