import unittest
from src.extraction.program_documents import _field_evidence, _approval, _section_maintenance

def p(text,i=1):return [{'page':i,'text':text}]

class RobustV20(unittest.TestCase):
 def test_no_unlabeled_serial_match(self):
  r=_field_evidence(p('Lampiran nomor seri 56153901 untuk ilustrasi'), 'nomor_seri_unit','56153901')
  self.assertEqual(r['status'],'REVIEW')
 def test_labeled_serial_match(self):
  r=_field_evidence(p('No. Seri pesawat sinar-X: 56153901'), 'nomor_seri_unit','56153901')
  self.assertEqual(r['status'],'MATCH')
 def test_other_labeled_serial_not_match(self):
  r=_field_evidence(p('No. Seri pesawat sinar-X: 999888777'), 'nomor_seri_unit','56153901')
  self.assertEqual(r['status'],'REVIEW')
 def test_approval_toc_only(self):
  self.assertFalse(_approval(p('DAFTAR ISI\nLembar Pengesahan ............. ii\nMengetahui\nDirektur')))
 def test_approval_candidate(self):
  self.assertTrue(_approval(p('LEMBAR PENGESAHAN\nDisahkan oleh:\nDirektur RS\nTanggal: 1 Oktober 2026')))
 def test_generic_uji_not_subsection(self):
  self.assertFalse(_section_maintenance(p('PENDAHULUAN\nSemua alat menjalani uji kesesuaian secara berkala.')))
 def test_actual_subsection(self):
  sample='4.4.3. Uji Kesesuaian (Constancy Test)\nFrekuensi:\n- Setiap 12 bulan sekali.\nParameter yang diuji meliputi:\n1. Konsistensi kV dan mA\n2. Waktu eksposi dan kesesuaian pengaturan'
  rows=_section_maintenance(p(sample))
  self.assertTrue(rows)
  self.assertTrue(rows[0]['frequencies'])
  self.assertGreaterEqual(len(rows[0]['parameters']),2)

if __name__=='__main__':unittest.main()
