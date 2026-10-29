"""Integration tests for BAPETEN AI Evaluator FastAPI backend.

Uses synthetic in-memory PDFs for regression testing without
requiring proprietary hospital documents.
"""
from __future__ import annotations

import os
import shutil
import tempfile
import time
import unittest
from pathlib import Path

import pymupdf
from fastapi.testclient import TestClient


def _make_synthetic_form_pdf() -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    text = (
        "FORMULIR EVALUASI PERMOHONAN FASILITAS RADIASI\n"
        "Nomor Registrasi: 9876/REG/2023\n"
        "Tanggal Registrasi: 12/05/2023\n"
        "Lingkup Kegiatan: Radiologi Diagnostik dan Intervensional\n"
        "Instansi: RS Harapan Sehat Sentosa\n"
        "Alamat Instansi: Jl. Kesehatan No. 10 Jakarta\n"
        "Nama Proyek: Pengadaan Pesawat Gigi\n"
        "Alamat Proyek: Jl. Kesehatan No. 10 Jakarta\n"
        "A. Kelengkapan Administrasi\n"
    )
    page.insert_text((50, 50), text)
    return doc.tobytes()


def _make_synthetic_support_pdf(title: str = "LAPORAN PERAWATAN DAN UJI KESESUAIAN") -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    text = (
        f"{title}\n"
        "Instansi: RS Harapan Sehat Sentosa\n"
        "Alamat: Jl. Kesehatan No. 10 Jakarta\n"
        "Hasil Uji: Memenuhi Syarat dan Laik Operasi\n"
        "Catatan: Semua parameter keselamatan radiasi terpantau normal.\n"
    )
    page.insert_text((50, 50), text)
    return doc.tobytes()


class TestBapetenApi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.mkdtemp(prefix="bapeten_api_test_")
        cls.old_data_dir = os.environ.get("BAPETEN_DATA_DIR")
        os.environ["BAPETEN_DATA_DIR"] = cls.temp_dir

        import sys
        backend_dir = Path(__file__).resolve().parents[1]
        if str(backend_dir) not in sys.path:
            sys.path.insert(0, str(backend_dir))

        import app.storage as storage
        from app.main import app, TOKEN

        cls.storage = storage
        cls.storage.ROOT = Path(cls.temp_dir)
        cls.storage.init_db()

        cls.app = app
        cls.token = TOKEN
        cls.client = TestClient(app)
        cls.headers = {"Authorization": f"Bearer {TOKEN}"} if TOKEN else {}

    @classmethod
    def tearDownClass(cls):
        if cls.old_data_dir is not None:
            os.environ["BAPETEN_DATA_DIR"] = cls.old_data_dir
        else:
            os.environ.pop("BAPETEN_DATA_DIR", None)
        shutil.rmtree(cls.temp_dir, ignore_errors=True)

    def test_01_health(self):
        res = self.client.get("/api/v1/health")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data.get("status"), "ok")
        self.assertIn("engine", data)

    def test_02_authentication_enforcement(self):
        old_dev = os.environ.get("BAPETEN_ALLOW_UNAUTHENTICATED_LOCAL_DEV")
        try:
            os.environ["BAPETEN_ALLOW_UNAUTHENTICATED_LOCAL_DEV"] = "0"
            if self.token:
                # Unauthorized request without token
                res = self.client.post("/api/v1/applications")
                self.assertEqual(res.status_code, 401)

                # Unauthorized request with invalid token
                res = self.client.post(
                    "/api/v1/applications",
                    headers={"Authorization": "Bearer invalid_secret_token_123"},
                )
                self.assertEqual(res.status_code, 401)
        finally:
            if old_dev is not None:
                os.environ["BAPETEN_ALLOW_UNAUTHENTICATED_LOCAL_DEV"] = old_dev
            else:
                os.environ.pop("BAPETEN_ALLOW_UNAUTHENTICATED_LOCAL_DEV", None)

    def test_03_cors_preflight_options(self):
        # OPTIONS preflight request should succeed even without auth
        res = self.client.options(
            "/api/v1/applications",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "Authorization,Content-Type",
            },
        )
        self.assertEqual(res.status_code, 200)
        self.assertIn("access-control-allow-origin", res.headers)

    def _create_app(self) -> str:
        res = self.client.post("/api/v1/applications", headers=self.headers)
        self.assertEqual(res.status_code, 200)
        aid = res.json().get("application_id")
        self.assertTrue(aid and len(aid) == 32)
        return aid

    def test_04_create_application(self):
        aid = self._create_app()
        self.assertTrue(aid)

    def test_05_documents_crud_and_preview(self):
        aid = self._create_app()

        # Upload synthetic form PDF
        form_bytes = _make_synthetic_form_pdf()
        res_form = self.client.post(
            f"/api/v1/applications/{aid}/documents",
            data={"category": "formulir"},
            files={"file": ("formulir.pdf", form_bytes, "application/pdf")},
            headers=self.headers,
        )
        self.assertEqual(res_form.status_code, 200)
        form_doc = res_form.json().get("document")
        self.assertIsNotNone(form_doc)
        self.assertEqual(form_doc["category"], "formulir")
        self.assertEqual(form_doc["filename"], "formulir.pdf")

        # Upload synthetic maintenance PDF
        maint_bytes = _make_synthetic_support_pdf()
        res_maint = self.client.post(
            f"/api/v1/applications/{aid}/documents",
            data={"category": "perawatan"},
            files={"file": ("perawatan.pdf", maint_bytes, "application/pdf")},
            headers=self.headers,
        )
        self.assertEqual(res_maint.status_code, 200)
        maint_doc = res_maint.json().get("document")

        # List documents
        res_list = self.client.get(
            f"/api/v1/applications/{aid}/documents", headers=self.headers
        )
        self.assertEqual(res_list.status_code, 200)
        docs = res_list.json().get("documents", [])
        self.assertEqual(len(docs), 2)

        # Download raw file
        res_file = self.client.get(
            f"/api/v1/applications/{aid}/documents/{form_doc['id']}/file",
            headers=self.headers,
        )
        self.assertEqual(res_file.status_code, 200)
        self.assertTrue(res_file.content.startswith(b"%PDF-"))

        # Evidence single page preview
        res_ev = self.client.get(
            f"/api/v1/applications/{aid}/documents/{form_doc['id']}/evidence-page/1",
            headers=self.headers,
        )
        self.assertEqual(res_ev.status_code, 200)
        self.assertEqual(res_ev.headers.get("content-type"), "image/jpeg")

        # Inline preview endpoint
        res_prev = self.client.get(
            f"/api/v1/applications/{aid}/documents/{form_doc['id']}/preview",
            headers=self.headers,
        )
        self.assertEqual(res_prev.status_code, 200)

        # Delete maintenance document
        res_del = self.client.delete(
            f"/api/v1/applications/{aid}/documents/{maint_doc['id']}",
            headers=self.headers,
        )
        self.assertEqual(res_del.status_code, 200)
        self.assertTrue(res_del.json().get("deleted"))

        # Verify only 1 document remains
        res_list2 = self.client.get(
            f"/api/v1/applications/{aid}/documents", headers=self.headers
        )
        self.assertEqual(len(res_list2.json().get("documents", [])), 1)

    def test_06_analysis_validation_requires_single_form(self):
        aid = self._create_app()

        # No documents at all -> should reject with 422
        res = self.client.post(
            f"/api/v1/applications/{aid}/analyses", headers=self.headers
        )
        self.assertEqual(res.status_code, 422)
        self.assertIn("Formulir", res.json().get("detail", ""))

    def test_07_full_analysis_workflow(self):
        aid = self._create_app()

        # Upload 1 form
        form_bytes = _make_synthetic_form_pdf()
        self.client.post(
            f"/api/v1/applications/{aid}/documents",
            data={"category": "formulir"},
            files={"file": ("formulir.pdf", form_bytes, "application/pdf")},
            headers=self.headers,
        )

        # Upload 1 support doc
        maint_bytes = _make_synthetic_support_pdf()
        self.client.post(
            f"/api/v1/applications/{aid}/documents",
            data={"category": "perawatan"},
            files={"file": ("perawatan.pdf", maint_bytes, "application/pdf")},
            headers=self.headers,
        )

        # Start analysis
        res_an = self.client.post(
            f"/api/v1/applications/{aid}/analyses", headers=self.headers
        )
        self.assertEqual(res_an.status_code, 200)
        jid = res_an.json().get("job_id")
        self.assertTrue(jid)

        # Poll until complete (timeout after 20s)
        completed = False
        for _ in range(40):
            time.sleep(0.5)
            j = self.client.get(
                f"/api/v1/applications/{aid}/jobs/{jid}", headers=self.headers
            ).json()
            if j.get("status") == "completed":
                completed = True
                break
            if j.get("status") == "failed":
                self.fail(f"Job failed unexpectedly: {j.get('error')}")

        self.assertTrue(completed, "Analysis did not complete within timeout")

        # Fetch results
        res_res = self.client.get(
            f"/api/v1/applications/{aid}/results", headers=self.headers
        )
        self.assertEqual(res_res.status_code, 200)
        result_data = res_res.json()
        self.assertIn("matching_sections", result_data)
        self.assertIn("form_reference", result_data)
        self.assertEqual(result_data.get("analyzed_documents"), 1)

    def test_08_recover_stale_jobs(self):
        aid = self._create_app()
        jid = self.storage.create_job(aid)
        self.storage.update_job(jid, status="running", progress=50, message="Memproses")

        # Verify job is running
        job_before = self.storage.get_job(jid, aid)
        self.assertEqual(job_before["status"], "running")

        # Trigger recovery
        self.storage.recover_stale_jobs()

        # Verify job is now marked as failed
        job_after = self.storage.get_job(jid, aid)
        self.assertEqual(job_after["status"], "failed")
        self.assertIn("server restart", job_after["error"].lower())


if __name__ == "__main__":
    unittest.main()
