import unittest
from src.extraction.general_info import extract_general_info

class TestAddressV25b(unittest.TestCase):
    def parse(self, s):
        return extract_general_info('Instansi: Dinas Kesehatan\nAlamat Proyek: '+s+'\nA. Kelengkapan Administrasi')
    def test_examples(self):
        cases=[
            ('Klinik Insan Utama Balikpapan, Jl. Mayor TNI AD Ahmad Saili, Kota Balikpapan Kalimantan Timur 76124, Telp.0857-5232-3293','Klinik Insan Utama Balikpapan','Jl. Mayor TNI AD Ahmad Saili, Kota Balikpapan Kalimantan Timur 76124'),
            ('RS Jiwa Aceh, Jl. Dr. T. Syarief Thayeb No. 25, Kota Banda Aceh 23126, Telp.0651-32010, 0651-32020, Fax.0651-25857','RS Jiwa Aceh','Jl. Dr. T. Syarief Thayeb No. 25, Kota Banda Aceh 23126'),
            ('Klinik A, Jalan Melati No. 2, Telepon: (021) 22133, Faks: 4444','Klinik A','Jalan Melati No. 2'),
            ('Klinik B, Jalan Anggrek 5, No. Telp 08571','Klinik B','Jalan Anggrek 5'),
            ('Klinik C, Jl. Kenanga 9, Fax: 02111','Klinik C','Jl. Kenanga 9'),
        ]
        for raw,name,addr in cases:
            with self.subTest(raw=raw):
                d=self.parse(raw)
                self.assertEqual(d['nama_fasilitas'],name)
                self.assertEqual(d['alamat_proyek'],addr)
                self.assertEqual(d['instansi'],name)
                self.assertEqual(d['alamat_proyek_asli'],raw)
if __name__=='__main__': unittest.main()
