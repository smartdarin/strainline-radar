"""Earthdata-authenticated, resumable streaming download with integrity checks."""
from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path
from urllib.parse import urlparse


def load_local_env() -> None:
    """Load project-local KEY=VALUE settings without printing their values."""
    env_file = Path(__file__).resolve().parents[1] / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key, value = key.strip(), value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value

    # Also accept the user's project-local, single-line token file. Never emit
    # its contents; the value remains in the backend process environment only.
    token_file = env_file.with_name("EARTHDATA_TOKEN.env")
    if "EARTHDATA_TOKEN" not in os.environ and token_file.is_file():
        token = token_file.read_text(encoding="utf-8").strip()
        if token.startswith("EARTHDATA_TOKEN="):
            token = token.partition("=")[2].strip().strip('"').strip("'")
        if token and re.fullmatch(r"[A-Za-z0-9._~+/=-]+", token):
            os.environ["EARTHDATA_TOKEN"] = token


load_local_env()


def _download_with_earthaccess(url: str, temporary: Path) -> dict:
    """Stream one Earthdata file; append only when the server honors HTTP Range."""
    import earthaccess

    auth = earthaccess.login(strategy="environment")
    offset = temporary.stat().st_size if temporary.exists() else 0
    headers = {"Range": f"bytes={offset}-"} if offset else {}
    sha256 = hashlib.sha256()
    md5 = hashlib.md5()
    written = 0

    with auth.get_session() as session:
        with session.get(url, headers=headers, stream=True, timeout=(30, 120)) as response:
            response.raise_for_status()
            status = int(response.status_code)
            content_range = response.headers.get("Content-Range", "")
            if offset and status == 206:
                match = re.fullmatch(r"bytes (\d+)-(\d+)/(\d+|\*)", content_range.strip(), re.IGNORECASE)
                if not match or int(match.group(1)) != offset:
                    raise OSError("Server returned an invalid range response; partial file retained.")
                range_end = int(match.group(2))
                expected_chunk_bytes = range_end - offset + 1
                mode = "ab"
            elif status == 200:
                # A server that ignores Range must be restarted from byte zero.
                offset = 0
                expected_chunk_bytes = None
                mode = "wb"
            else:
                raise OSError("Server did not return a complete or valid partial-content response.")

            if offset:
                with temporary.open("rb") as prefix:
                    for chunk in iter(lambda: prefix.read(1024 * 1024), b""):
                        sha256.update(chunk)
                        md5.update(chunk)

            raw_content_length = response.headers.get("Content-Length")
            content_length = int(raw_content_length) if raw_content_length else None
            with temporary.open(mode) as target:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if not chunk:
                        continue
                    target.write(chunk)
                    sha256.update(chunk)
                    md5.update(chunk)
                    written += len(chunk)
                target.flush()
                os.fsync(target.fileno())

            if content_length is not None and written != content_length:
                raise OSError("Transfer ended before the advertised response length; partial file retained for resume.")
            if expected_chunk_bytes is not None and written != expected_chunk_bytes:
                raise OSError("Partial response ended early; partial file retained for resume.")

    return {
        "size_bytes": temporary.stat().st_size,
        "sha256": sha256.hexdigest(),
        "md5": md5.hexdigest(),
        "http_status": status,
    }


def _trusted_data_url(value: str) -> bool:
    parsed = urlparse(value)
    host = (parsed.hostname or "").lower()
    return (
        parsed.scheme == "https"
        and parsed.username is None
        and parsed.password is None
        and parsed.port in (None, 443)
        and (host == "nasa.gov" or host.endswith(".nasa.gov")
             or host == "asf.alaska.edu" or host.endswith(".asf.alaska.edu"))
    )


def download_product(
    url: str,
    destination: Path,
    expected_sha256: str | None = None,
    *,
    expected_md5: str | None = None,
    expected_size_bytes: int | None = None,
    expected_granule_id: str | None = None,
) -> dict:
    """Download one trusted product, verify CMR integrity metadata and publish atomically.

    Interrupted transfers leave ``<destination>.part`` for a later Range request.
    Supplying ``expected_granule_id`` additionally requires a readable GUNW HDF5
    with that embedded granule identity before it can replace the destination.
    """
    if not os.getenv("EARTHDATA_TOKEN"):
        raise RuntimeError("Set EARTHDATA_TOKEN in the project .env after Earthdata authentication.")
    if not _trusted_data_url(url):
        raise ValueError("Only HTTPS NASA/ASF data URLs are accepted.")
    if expected_sha256 is not None and not re.fullmatch(r"[a-fA-F0-9]{64}", expected_sha256):
        raise ValueError("Expected SHA-256 must contain exactly 64 hexadecimal characters.")
    if expected_md5 is not None and not re.fullmatch(r"[a-fA-F0-9]{32}", expected_md5):
        raise ValueError("Expected MD5 must contain exactly 32 hexadecimal characters.")
    if expected_size_bytes is not None and expected_size_bytes <= 0:
        raise ValueError("Expected file size must be a positive byte count.")

    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".part")
    try:
        receipt = _download_with_earthaccess(url, temporary)
        size = receipt["size_bytes"]
        if expected_size_bytes is not None and size != expected_size_bytes:
            if size > expected_size_bytes:
                temporary.unlink(missing_ok=True)
                raise ValueError("Downloaded size exceeds the CMR-reported file size; partial file removed.")
            raise OSError("Download is incomplete; partial file retained for resume.")
        if expected_md5 and receipt["md5"].lower() != expected_md5.lower():
            temporary.unlink(missing_ok=True)
            raise ValueError("Downloaded MD5 does not match NASA CMR; partial file removed.")
        if expected_sha256 and receipt["sha256"].lower() != expected_sha256.lower():
            temporary.unlink(missing_ok=True)
            raise ValueError("Downloaded SHA-256 does not match the expected checksum; partial file removed.")

        hdf5_metadata = None
        if expected_granule_id:
            try:
                from backend.gunw_metadata import inspect_gunw
                hdf5_metadata = inspect_gunw(temporary, "HH")
            except Exception:
                temporary.unlink(missing_ok=True)
                raise ValueError("Downloaded file is not a readable NISAR GUNW HDF5 product; partial file removed.") from None
            if hdf5_metadata.get("granule_id") != expected_granule_id:
                temporary.unlink(missing_ok=True)
                raise ValueError("HDF5 granule identity does not match the selected CMR record; partial file removed.")
            hdf5_metadata["source_file_name"] = destination.name

        os.replace(temporary, destination)
        return {
            **receipt,
            "checksum_verified": bool(expected_sha256),
            "cmr_checksum_verified": bool(expected_md5),
            "size_verified": expected_size_bytes is not None,
            "hdf5_verified": bool(expected_granule_id),
            "hdf5_metadata": hdf5_metadata,
        }
    except (ValueError, RuntimeError):
        raise
    except Exception:
        # Keep an incomplete .part file so a retry can continue with Range.
        raise
