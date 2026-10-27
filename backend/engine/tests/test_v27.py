import pathlib
import unittest
from src.extraction.program_documents import _identity_candidates, _retrieve_address, _compare_address_shared, _field_evidence

class EvidenceV27(unittest.TestCase):
    def test_name_rejects_noise(self):
        pages=[{'page':1,'text':'DAFTAR ISI\nRumah Sakit Kebijakan .... 22'},
               {'page':2,'text':'Nama fasilitas: RS Tk. IV Pekanbaru\nJl. Kesehatan No. 2 Pekanbaru Riau'},
               {'page':3,'text':'Direktur Rumah Sakit adalah penanggung jawab utama dan penyedia sumber'}]
        a=_identity_candidates(pages,'RS Tk. IV Pekanbaru')
        self.assertEqual(a[0][4],'RS Tk. IV Pekanbaru')
    def test_address_shared(self):
        a='Jl. Kesehatan No. 2, Kota Pekanbaru Riau'
        self.assertEqual(_compare_address_shared(a,'Jalan Kesehatan Nomor 02 Pekanbaru')['status'],'MATCH')
        self.assertEqual(_compare_address_shared(a,'Jalan Kesehatan No 11 Pekanbaru')['status'],'MISMATCH')
        self.assertNotEqual(_compare_address_shared(a,'Pekanbaru')['status'],'MATCH')
    def test_address_retrieval(self):
        pages=[{'page':1,'text':'III.3 Kebijakan Keselamatan Radiasi Rumah Sakit .. 22'},
               {'page':2,'text':'Alamat : Jl. Kesehatan No. 02 Pekanbaru Riau'}]
        self.assertEqual(_retrieve_address(pages,'Jl. Kesehatan No 2, Kota Pekanbaru')[0][2]['status'],'MATCH')
    def test_equipment_six(self):
        p=[{'page':1,'text':'Merk pesawat sinar-X : FDR Nano\nTipe/model pesawat sinar-X : DR-XD 1000\nNo. Seri pesawat sinar-X : 56153901\nMerk tabung : Canon\nTipe tabung : D125SB\nNo. Seri tabung : B124125'}]
        values={'merk_unit':('Fujifilm','MISMATCH'),'tipe_unit':('DR-XD 1000 (FDR Nano)','MATCH'),'nomor_seri_unit':('56153901','MATCH'),'merk_tabung':('Canon','MATCH'),'tipe_tabung':('D125-SB','MATCH'),'nomor_seri_tabung':('B124125','MATCH')}
        for key,(value,status) in values.items():
            with self.subTest(key=key):self.assertEqual(_field_evidence(p,key,value)['status'],status)
    def test_no_bare_serial_match(self):
        self.assertNotEqual(_field_evidence([{'page':1,'text':'Nomor: 56153901 tercantum di lampiran'}], 'nomor_seri_unit','56153901')['status'],'MATCH')
    def test_bug_metric(self):
        source=pathlib.Path('app/app.py').read_text()
        self.assertIn('mismatched = sum(',source)
        self.assertIn('len(graded) - matched - mismatched',source)
if __name__=='__main__':unittest.main()
