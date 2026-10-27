import unittest
from src.extraction.equipment_sections import (classify_page,select_primary_pages,consistency_warnings,identity_linked)
from src.extraction.program_documents import _field_evidence

class TestScopedEquipment(unittest.TestCase):
    def setUp(self):
        self.main={'page':14,'text':'''2. Deskripsi Pesawat Sinar-X
Data pesawat
Merk pesawat sinar-X : FDR Nano
Tipe/model pesawat sinar-X : DR-XD 1000
No. Seri pesawat sinar-X : 56153901
Data tabung
Merk tabung : Canon
Tipe tabung : D125SB
No. Seri tabung : B124125'''}
        self.cert={'page':30,'text':'''SERTIFIKAT UJI KESESUAIAN PESAWAT SINAR-X
Data Pesawat
Merk Tabung : Fujifilm
Model/Tipe Tabung : D125-SB
Nomor Seri Tabung : B124125
Generator dan panel Kendali Sinar-X
Pabrikan/Merk : Fujifilm
Model/Tipe : DR-XD 1000
Nomor Seri : 56153901'''}
        self.report={'page':31,'text':'''LAPORAN EVALUASI HASIL UJI
Data Pesawat
Merk Tabung : Fujifilm
Model/Tipe Tabung : D125-SB
Nomor Seri Tabung : B124125'''}
    def test_main_scoped_no_false_review(self):
        main=select_primary_pages([self.main,self.cert,self.report],'program_protection_upload')
        self.assertEqual([p['page'] for p in main],[14])
        result=_field_evidence(main,'merk_tabung','Canon')
        self.assertEqual(result['status'],'MATCH')
    def test_generic_warning_linked_by_serial(self):
        warnings=consistency_warnings([self.main,self.cert,self.report],[self.main])
        self.assertTrue(any(w['field']=='merk_tabung' and w['other_page']==30 for w in warnings))
        self.assertTrue(any(w['field']=='merk_tabung' and w['other_page']==31 for w in warnings))
    def test_unrelated_appendix_no_warning(self):
        other={'page':30,'text':self.cert['text'].replace('B124125','OTHER-3333').replace('56153901','99990000')}
        self.assertFalse(consistency_warnings([self.main,other],[self.main]))
    def test_not_section_keyword_in_prose(self):
        self.assertEqual(classify_page('Bab 1\nKami telah memiliki sertifikat uji kesesuaian nomor XX'), 'general')
    def test_disagreeing_serial_not_linked(self):
        self.assertEqual(identity_linked({'nomor_seri_unit':'123'},{'nomor_seri_unit':'124'}),(False,None))
if __name__=='__main__': unittest.main()
