"""Downloader safety tests use a fake Earthdata session; no credentials or network calls."""
import hashlib
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.download import download_product
from backend.main import DownloadRequest, download
from unittest.mock import patch as mock_patch


def temporary_workspace_directory():
    workspace = Path(__file__).resolve().parents[1] / "data" / "processed"
    return tempfile.TemporaryDirectory(dir=workspace)


class FakeResponse:
    url = "https://datapool.asf.alaska.edu/product.h5"

    def __init__(self, chunks=(b"flight", b" data"), status_code=200, headers=None):
        self.chunks = chunks
        self.status_code = status_code
        self.headers = headers or {"Content-Length": str(sum(map(len, chunks)))}

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def raise_for_status(self):
        return None

    def iter_content(self, chunk_size):
        yield from self.chunks


class FakeSession:
    response = None
    request_headers = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def get(self, url, *, headers=None, stream, timeout):
        if stream is not True or timeout != (30, 120):
            raise AssertionError("Expected streamed request with bounded timeouts.")
        type(self).request_headers = headers or {}
        return type(self).response or FakeResponse()


class FakeAuth:
    @classmethod
    def login(cls, *, strategy):
        if strategy != "environment" or not os.getenv("EARTHDATA_TOKEN"):
            raise AssertionError("Earthdata token environment was not provided to earthaccess.")
        return cls()

    def get_session(self):
        return FakeSession()


class DownloadTests(unittest.TestCase):
    def setUp(self):
        self.fake_module = types.ModuleType("earthaccess")
        self.fake_module.login = FakeAuth.login

    def test_stages_download_and_publishes_after_checksum_matches(self):
        payload = b"flight data"
        expected = hashlib.sha256(payload).hexdigest()
        with temporary_workspace_directory() as directory:
            destination = Path(directory) / "granule.h5"
            destination.write_bytes(b"older complete file")
            with patch.dict(sys.modules, {"earthaccess": self.fake_module}), \
                 patch.dict(os.environ, {"EARTHDATA_TOKEN": "test-token"}):
                receipt = download_product(
                    "https://datapool.asf.alaska.edu/product.h5", destination, expected)
            self.assertEqual(destination.read_bytes(), payload)
            self.assertFalse(destination.with_name("granule.h5.part").exists())
            self.assertTrue(receipt["checksum_verified"])
            self.assertEqual(receipt["size_bytes"], len(payload))

    def test_checksum_mismatch_keeps_previous_file_and_removes_temporary(self):
        with temporary_workspace_directory() as directory:
            destination = Path(directory) / "granule.h5"
            destination.write_bytes(b"older complete file")
            with patch.dict(sys.modules, {"earthaccess": self.fake_module}), \
                 patch.dict(os.environ, {"EARTHDATA_TOKEN": "test-token"}):
                with self.assertRaisesRegex(ValueError, "SHA-256"):
                    download_product(
                        "https://datapool.asf.alaska.edu/product.h5", destination, "0" * 64)
            self.assertEqual(destination.read_bytes(), b"older complete file")
            self.assertFalse(destination.with_name("granule.h5.part").exists())

    def test_interrupted_transfer_never_replaces_the_last_complete_product(self):
        with temporary_workspace_directory() as directory:
            destination = Path(directory) / "granule.h5"
            destination.write_bytes(b"older complete file")

            def interrupted(url, temporary):
                temporary.write_bytes(b"partial")
                raise OSError("connection interrupted")

            with patch.dict(os.environ, {"EARTHDATA_TOKEN": "test-token"}), \
                 mock_patch("backend.download._download_with_earthaccess", interrupted):
                with self.assertRaisesRegex(OSError, "interrupted"):
                    download_product("https://datapool.asf.alaska.edu/product.h5", destination)
            self.assertEqual(destination.read_bytes(), b"older complete file")
            self.assertEqual(destination.with_name("granule.h5.part").read_bytes(), b"partial")

    def test_resumes_partial_transfer_when_server_honors_range(self):
        payload = b"flight data"
        with temporary_workspace_directory() as directory:
            destination = Path(directory) / "granule.h5"
            partial = destination.with_name("granule.h5.part")
            partial.write_bytes(b"flight")
            FakeSession.response = FakeResponse(
                (b" data",), 206,
                {"Content-Length": "5", "Content-Range": "bytes 6-10/11"},
            )
            try:
                with patch.dict(sys.modules, {"earthaccess": self.fake_module}), \
                     patch.dict(os.environ, {"EARTHDATA_TOKEN": "test-token"}):
                    receipt = download_product(
                        "https://datapool.asf.alaska.edu/product.h5", destination,
                        expected_size_bytes=len(payload),
                    )
            finally:
                FakeSession.response = None
            self.assertEqual(FakeSession.request_headers, {"Range": "bytes=6-"})
            self.assertEqual(destination.read_bytes(), payload)
            self.assertFalse(partial.exists())
            self.assertTrue(receipt["size_verified"])

    def test_selected_product_requires_readable_matching_hdf5_identity(self):
        payload = b"flight data"
        granule_id = "NISAR_L2_PR_GUNW_test"
        metadata = {"granule_id": granule_id, "phase_shape": [4, 5]}
        with temporary_workspace_directory() as directory:
            destination = Path(directory) / "selected.h5"
            with patch.dict(sys.modules, {"earthaccess": self.fake_module}), \
                 patch.dict(os.environ, {"EARTHDATA_TOKEN": "test-token"}), \
                 patch("backend.gunw_metadata.inspect_gunw", return_value=metadata):
                receipt = download_product(
                    "https://datapool.asf.alaska.edu/product.h5", destination,
                    expected_md5=hashlib.md5(payload).hexdigest(),
                    expected_size_bytes=len(payload), expected_granule_id=granule_id,
                )
            self.assertTrue(receipt["hdf5_verified"])
            self.assertEqual(receipt["hdf5_metadata"], metadata)
            self.assertEqual(destination.read_bytes(), payload)

    def test_wrong_embedded_hdf5_identity_is_not_published(self):
        with temporary_workspace_directory() as directory:
            destination = Path(directory) / "selected.h5"
            with patch.dict(sys.modules, {"earthaccess": self.fake_module}), \
                 patch.dict(os.environ, {"EARTHDATA_TOKEN": "test-token"}), \
                 patch("backend.gunw_metadata.inspect_gunw", return_value={"granule_id": "wrong"}):
                with self.assertRaisesRegex(ValueError, "identity"):
                    download_product(
                        "https://datapool.asf.alaska.edu/product.h5", destination,
                        expected_granule_id="NISAR_L2_PR_GUNW_test",
                    )
            self.assertFalse(destination.exists())
            self.assertFalse(destination.with_name("selected.h5.part").exists())

    def test_rejects_untrusted_url_and_missing_token(self):
        with temporary_workspace_directory() as directory:
            destination = Path(directory) / "granule.h5"
            with patch.dict(os.environ, {}, clear=True):
                with self.assertRaisesRegex(RuntimeError, "EARTHDATA_TOKEN"):
                    download_product("https://example.com/product.h5", destination)
            with patch.dict(os.environ, {"EARTHDATA_TOKEN": "test-token"}, clear=True):
                with self.assertRaisesRegex(ValueError, "NASA/ASF"):
                    download_product("https://example.com/product.h5", destination)
            self.assertFalse(destination.exists())

    def test_cmr_record_is_retained_without_signed_query_strings(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch("backend.main.ROOT", root), \
                 patch("backend.main.download_product", return_value={
                     "size_bytes": 11, "sha256": "a" * 64, "checksum_verified": False,
                 }):
                response = download(DownloadRequest(
                    url="https://datapool.asf.alaska.edu/file.h5?token=secret",
                    filename="file.h5",
                    cmr_record={"id": "G-1", "links": [{"href": "https://example.org/file?signature=secret"}],
                                "umm": {"RelatedUrls": [{"URL": "https://example.org/umm?token=secret"}]}},
                ))
            sidecar_path = root / "data" / "raw" / "file.h5.cmr.json"
            record = __import__("json").loads(sidecar_path.read_text(encoding="utf-8"))
            self.assertEqual(response["cmr_sidecar"], "data/raw/file.h5.cmr.json")
            self.assertEqual(record["cmr_record"]["links"][0]["href"], "https://example.org/file")
            self.assertEqual(record["cmr_record"]["umm"]["RelatedUrls"][0]["URL"], "https://example.org/umm")
            self.assertNotIn("secret", sidecar_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
