"""Denoise one existing EXR with Houdini's official utility, preserving its source."""

from __future__ import annotations

import os
import re
import struct
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Optional, Sequence

from dcc_mcp_core.skill import skill_entry, skill_exception, skill_success

from dcc_mcp_houdini import _render_artifacts as artifacts

_MAX_BYTES = 512 * 1024 * 1024
_MAX_HEADER = 64 * 1024
_MAX_PIXELS = 4096 * 4096
_PLANE = re.compile(r"[A-Za-z][A-Za-z0-9_.:-]{0,63}\Z")


def _exr_dimensions(path: Path) -> list:
    """Read a bounded flat single-part EXR header; this is not pixel decoding."""
    size = path.stat().st_size
    if not 8 < size <= _MAX_BYTES:
        raise ValueError("EXR size must be between 9 bytes and 512 MiB")
    with path.open("rb") as stream:
        header = stream.read(_MAX_HEADER)
    if header[:4] != b"\x76\x2f\x31\x01":
        raise ValueError("Image must have an OpenEXR header")
    version = struct.unpack_from("<I", header, 4)[0]
    if version & 0xFF != 2 or version & (0x800 | 0x1000):
        raise ValueError("Only flat single-part OpenEXR version 2 is supported")
    cursor, dimensions = 8, None

    def text() -> str:
        nonlocal cursor
        end = header.find(b"\0", cursor)
        if end < 0 or end - cursor > 255:
            raise ValueError("Invalid or oversized EXR header field")
        value = header[cursor:end].decode("ascii")
        cursor = end + 1
        return value

    while cursor < len(header):
        name = text()
        if not name:
            if dimensions is None or size <= cursor + 8:
                raise ValueError("Incomplete EXR header or pixel payload")
            return dimensions
        kind = text()
        if cursor + 4 > len(header):
            break
        count = struct.unpack_from("<I", header, cursor)[0]
        cursor += 4
        if cursor + count > len(header):
            break
        if name == "dataWindow":
            if dimensions is not None or kind != "box2i" or count != 16:
                raise ValueError("Invalid EXR dataWindow")
            x0, y0, x1, y1 = struct.unpack_from("<4i", header, cursor)
            width, height = x1 - x0 + 1, y1 - y0 + 1
            if not 1 <= width <= 8192 or not 1 <= height <= 8192 or width * height > _MAX_PIXELS:
                raise ValueError("EXR dimensions exceed 8192 per side or 16 megapixels")
            dimensions = [width, height]
        cursor += count
    raise ValueError("EXR header is incomplete or exceeds 64 KiB")


def _plane_name(value: Optional[str], field: str) -> Optional[str]:
    if value is not None and (not isinstance(value, str) or _PLANE.fullmatch(value) is None):
        raise ValueError("{} must be one bounded image-plane name".format(field))
    return value


def _utility() -> Path:
    root = os.environ.get("HFS")
    if not root or not Path(root).is_absolute():
        raise ValueError("An absolute host HFS is required to resolve the official utility")
    executable = Path(root) / "bin" / ("idenoise.exe" if os.name == "nt" else "idenoise")
    executable = executable.absolute()
    artifacts.assert_no_links_or_reparse(executable)
    if not executable.is_file():
        raise FileNotFoundError("Houdini's official idenoise utility is unavailable under HFS/bin")
    return executable


def denoise_image(
    input_path: str,
    output_path: str,
    denoiser: str = "oidn",
    albedo_plane: Optional[str] = None,
    normal_plane: Optional[str] = None,
    aovs: Optional[Sequence[str]] = None,
    force_cpu: bool = False,
    timeout_secs: int = 120,
) -> dict:
    """Run one bounded official image operation and publish a new EXR without replacing files."""
    staged = None
    try:
        if denoiser not in ("oidn", "optix"):
            raise ValueError("denoiser must be oidn or optix")
        if not isinstance(force_cpu, bool) or (force_cpu and denoiser != "oidn"):
            raise ValueError("force_cpu is a boolean available only for oidn")
        if isinstance(timeout_secs, bool) or not isinstance(timeout_secs, int) or not 1 <= timeout_secs <= 300:
            raise ValueError("timeout_secs must be an integer from 1 to 300")
        albedo_plane = _plane_name(albedo_plane, "albedo_plane")
        normal_plane = _plane_name(normal_plane, "normal_plane")
        if aovs is not None:
            if not isinstance(aovs, (list, tuple)) or not 1 <= len(aovs) <= 8:
                raise ValueError("aovs must contain one to eight image-plane names")
            for value in aovs:
                if value is None:
                    raise ValueError("aovs cannot contain null")
                _plane_name(value, "aovs")
        source, target = Path(input_path), Path(output_path)
        if not source.is_absolute() or not target.is_absolute():
            raise ValueError("Input and output must be absolute paths")
        if source.suffix.lower() != ".exr" or target.suffix.lower() != ".exr":
            raise ValueError("Input and output must be EXR files")
        artifacts.assert_no_links_or_reparse(source)
        artifacts.assert_no_links_or_reparse(target)
        if not target.parent.is_dir():
            raise ValueError("Output directory must already exist")
        if os.path.lexists(str(target)):
            raise FileExistsError("Output already exists; in-place denoising and replacement are not supported")
        if not source.is_file():
            raise FileNotFoundError("Input EXR is unavailable")
        dimensions = _exr_dimensions(source)
        original = artifacts.stable_file_identity(source)
        utility = _utility()
        descriptor, name = tempfile.mkstemp(prefix=".dcc-mcp-denoise-", suffix=".partial.exr", dir=str(target.parent))
        os.close(descriptor)
        staged = Path(name)
        command = [str(utility), str(source), str(staged), "-d", denoiser]
        for flag, plane in (("-a", albedo_plane), ("-n", normal_plane)):
            if plane is not None:
                command.extend((flag, plane))
        if aovs is not None:
            command.extend(["--aovs", *aovs])
        if force_cpu:
            command.append("--oidn-cpu")
        started = time.monotonic()
        with tempfile.TemporaryFile() as diagnostics:
            process = subprocess.run(
                command,
                stdin=subprocess.DEVNULL,
                stdout=diagnostics,
                stderr=subprocess.STDOUT,
                shell=False,
                check=False,
                timeout=timeout_secs,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            diagnostics.seek(0, os.SEEK_END)
            diagnostics.seek(max(0, diagnostics.tell() - 8192))
            log_tail = diagnostics.read().decode("utf-8", errors="replace")
        if process.returncode != 0:
            raise RuntimeError("Official idenoise exited {}: {}".format(process.returncode, log_tail))
        artifacts.assert_no_links_or_reparse(staged)
        if _exr_dimensions(staged) != dimensions:
            raise ValueError("Denoised EXR dimensions do not match the source")
        if artifacts.stable_file_identity(source) != original:
            raise ValueError("Source EXR changed during denoising; output was not published")
        identity = artifacts.stable_file_identity(staged)
        artifacts.fsync_file(staged)
        publication = artifacts.publish_no_clobber(staged, target, expected_identity=identity)
        artifacts.fsync_parent(target)
        final_identity = artifacts.stable_file_identity(target)
        if final_identity != identity:
            raise ValueError("Published output identity changed")
        return skill_success(
            "Denoised EXR with Houdini's official utility",
            source_path=str(source),
            output_path=str(target),
            written_files=[str(target)],
            source_identity=original,
            output_identity=final_identity,
            source_unchanged=True,
            dimensions=dimensions,
            verification="official_exit_zero_and_exr_header_and_hash",
            pixel_decode_verified=False,
            denoiser=denoiser,
            force_cpu=force_cpu,
            albedo_plane=albedo_plane,
            normal_plane=normal_plane,
            aovs=list(aovs) if aovs is not None else None,
            utility_path=str(utility),
            elapsed_secs=round(time.monotonic() - started, 3),
            publication=publication,
            diagnostic_tail=log_tail,
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to denoise EXR")
    finally:
        if staged is not None:
            try:
                staged.unlink()
            except FileNotFoundError:
                pass


@skill_entry
def main(**kwargs) -> dict:
    return denoise_image(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
