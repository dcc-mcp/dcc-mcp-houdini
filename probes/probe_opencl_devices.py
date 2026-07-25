"""PIP-2930 Stage-1: Standalone OpenCL device enumeration.

Run from hython or Houdini Python shell:
    hython probes/probe_opencl_devices.py

This script tries every available method to discover OpenCL devices without
requiring a COP network. It can be run before any scene work to verify GPU
readiness.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def _hfs_bin(tool: str) -> str:
    """Resolve a Houdini bin tool path."""
    hfs = _env("HFS")
    if not hfs:
        return tool  # hope it's on PATH
    if sys.platform == "win32":
        return os.path.join(hfs, "bin", f"{tool}.exe")
    return os.path.join(hfs, "bin", tool)


def _run(args: List[str], timeout: int = 30) -> Dict[str, Any]:
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return {
            "ok": r.returncode == 0,
            "returncode": r.returncode,
            "stdout": r.stdout.strip(),
            "stderr": r.stderr.strip(),
        }
    except FileNotFoundError:
        return {"ok": False, "error": "binary not found"}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "timeout"}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def probe_hgpuinfo() -> Dict[str, Any]:
    """Run hgpuinfo -c -l for complete device listing."""
    return _run([_hfs_bin("hgpuinfo"), "-c", "-l"])


def probe_hgpuinfo_current() -> Dict[str, Any]:
    """Run hgpuinfo -c for current device only."""
    return _run([_hfs_bin("hgpuinfo"), "-c"])


def probe_hconfig_ocl() -> Dict[str, Any]:
    """Run hconfig -a and extract OpenCL-related config keys."""
    result = _run([_hfs_bin("hconfig"), "-a"])
    if result["ok"]:
        lines = result["stdout"].splitlines()
        ocl_lines = [line for line in lines if "ocl" in line.lower() or "opencl" in line.lower()]
        gpu_lines = [line for line in lines if "gpu" in line.lower()]
        result["ocl_lines"] = ocl_lines
        result["gpu_lines"] = gpu_lines
    return result


def probe_env_vars() -> Dict[str, Any]:
    """Collect all OpenCL-related environment variables."""
    ocl_vars = {}
    for key, value in sorted(os.environ.items()):
        upper = key.upper()
        if any(term in upper for term in ("OCL", "OPENCL", "GPU", "CUDA", "VULKAN", "METAL")):
            ocl_vars[key] = value
    return {"variables": ocl_vars}


def probe_hou_opencl() -> Dict[str, Any]:
    """Introspect hou.opencl module if available."""
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return {"available": False, "error": "hou not importable"}

    if not hasattr(hou, "opencl"):
        return {"available": False, "error": "hou.opencl not present in this Houdini build"}

    ocl = hou.opencl
    result: Dict[str, Any] = {"available": True, "methods": [], "values": {}}

    for name in sorted(dir(ocl)):
        if name.startswith("_"):
            continue
        result["methods"].append(name)
        try:
            attr = getattr(ocl, name)
            if callable(attr):
                try:
                    result["values"][name] = str(attr())
                except Exception as exc:
                    result["values"][name] = f"call failed: {exc}"
            else:
                result["values"][name] = str(attr)
        except Exception:
            pass

    return result


def probe_about_dialog() -> Dict[str, Any]:
    """Try hou.aboutDialogInfo() — may contain OpenCL platform section."""
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return {"available": False}

    if not hasattr(hou, "aboutDialogInfo"):
        return {"available": False}

    try:
        text = hou.aboutDialogInfo()
        ocl_section_start = text.lower().find("opencl")
        if ocl_section_start >= 0:
            snippet = text[ocl_section_start:ocl_section_start + 2000]
            return {"available": True, "opencl_section": snippet}
        return {"available": True, "opencl_section": None, "note": "No OpenCL section found in About dialog"}
    except Exception as exc:
        return {"available": True, "error": str(exc)}


def probe_pyopencl() -> Dict[str, Any]:
    """Try pyopencl if installed."""
    try:
        import pyopencl as cl  # type: ignore[import-untyped] # noqa: PLC0415

        platforms = cl.get_platforms()
        result: Dict[str, Any] = {"available": True, "platform_count": len(platforms), "platforms": []}
        for pi, plat in enumerate(platforms):
            p_info = {
                "index": pi,
                "name": plat.name,
                "vendor": plat.vendor,
                "version": plat.version,
                "devices": [],
            }
            try:
                devices = plat.get_devices()
                for di, dev in enumerate(devices):
                    d_info = {
                        "index": di,
                        "name": dev.name,
                        "type": str(dev.type),
                        "compute_units": getattr(dev, "max_compute_units", None),
                        "global_memory_mb": getattr(dev, "global_mem_size", 0) // (1024 * 1024),
                    }
                    p_info["devices"].append(d_info)
            except Exception as exc:
                p_info["device_error"] = str(exc)
            result["platforms"].append(p_info)
        return result
    except ImportError:
        return {"available": False, "error": "pyopencl not installed"}
    except Exception as exc:
        return {"available": False, "error": str(exc), "traceback": traceback.format_exc()}


def main() -> int:
    print("PIP-2930 OpenCL Device Probe")
    print("=" * 60)

    probes: Dict[str, Dict[str, Any]] = {}

    # 1. hgpuinfo -c -l (full listing)
    print("\n--- hgpuinfo -c -l ---")
    probes["hgpuinfo_list"] = probe_hgpuinfo()
    if probes["hgpuinfo_list"]["ok"]:
        print(probes["hgpuinfo_list"]["stdout"])
    else:
        print(f"  ERROR: {probes['hgpuinfo_list'].get('error')}")

    # 2. hgpuinfo -c (current device)
    print("\n--- hgpuinfo -c (current) ---")
    probes["hgpuinfo_current"] = probe_hgpuinfo_current()
    if probes["hgpuinfo_current"]["ok"]:
        print(probes["hgpuinfo_current"]["stdout"])
    else:
        print(f"  ERROR: {probes['hgpuinfo_current'].get('error')}")

    # 3. hconfig OCL keys
    print("\n--- hconfig OpenCL keys ---")
    probes["hconfig_ocl"] = probe_hconfig_ocl()
    for line in probes["hconfig_ocl"].get("ocl_lines", []):
        print(f"  {line}")

    # 4. Environment variables
    print("\n--- Environment ---")
    probes["env"] = probe_env_vars()
    if probes["env"]["variables"]:
        for k, v in probes["env"]["variables"].items():
            print(f"  {k}={v}")
    else:
        print("  (no OpenCL/GPU-related env vars set)")

    # 5. hou.opencl
    print("\n--- hou.opencl ---")
    probes["hou_opencl"] = probe_hou_opencl()
    if probes["hou_opencl"]["available"]:
        print(f"  Methods: {probes['hou_opencl']['methods']}")
        for k, v in probes["hou_opencl"].get("values", {}).items():
            print(f"  {k} = {v}")
    else:
        print(f"  Not available: {probes['hou_opencl'].get('error')}")

    # 6. About dialog
    print("\n--- About dialog OpenCL section ---")
    probes["about"] = probe_about_dialog()
    if probes["about"].get("opencl_section"):
        print(probes["about"]["opencl_section"])
    else:
        print(f"  {probes['about']}")

    # 7. pyopencl
    print("\n--- pyopencl ---")
    probes["pyopencl"] = probe_pyopencl()
    if probes["pyopencl"]["available"]:
        for plat in probes["pyopencl"]["platforms"]:
            print(f"  Platform: {plat['name']} ({plat['vendor']})")
            for dev in plat.get("devices", []):
                print(f"    Device: {dev['name']} ({dev['type']}, {dev['compute_units']} CU)")
    else:
        print(f"  Not available: {probes['pyopencl'].get('error')}")

    # Write output
    output = {
        "probe": "PIP-2930-opencl-devices",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "platform": sys.platform,
        "probes": probes,
    }

    out_path = f"pip2930_opencl_{datetime.now().strftime('%Y%m%dT%H%M%S')}.json"
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2, default=str)

    # Summary
    print(f"\nResults: {out_path}")
    hgpu_ok = probes["hgpuinfo_list"]["ok"]
    hou_ok = probes["hou_opencl"].get("available", False)
    pyocl_ok = probes["pyopencl"].get("available", False)

    if hgpu_ok:
        print("OpenCL devices: DETECTED (hgpuinfo)")
    elif hou_ok or pyocl_ok:
        print("OpenCL devices: DETECTED (alternative method)")
    else:
        print("OpenCL devices: NOT DETECTED")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
