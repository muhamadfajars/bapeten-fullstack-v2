import unittest
from src.extraction.program_documents import _approval

def pages(*texts):return [{'page':i+1,'text':t} for i,t in enumerate(texts)]

class TestApprovalHeadingV21(unittest.TestCase):
    def test_heading_only_accepted(self):
        self.assertEqual(_approval(pages('LEMBAR PENGESAHAN\nNama RS: Rumah Sakit Jiwa Aceh'))[0]['page'],1)
    def test_toc_rejected(self):
        self.assertEqual(_approval(pages('DAFTAR ISI\nLembar Pengesahan ............... ii\nBAB I ........ 1')),[])
    def test_actual_page_after_toc(self):
        actual=_approval(pages('DAFTAR ISI\nLembar Pengesahan ............... ii\nBAB I ........ 1', 'LEMBAR PENGESAHAN\nNama: Direktur'))
        self.assertEqual(actual[0]['page'],2)
    def test_body_mentions_not_heading(self):
        self.assertEqual(_approval(pages('Pada bagian ini dijelaskan lembar pengesahan dokumen.')),[])

if __name__=='__main__':unittest.main()
