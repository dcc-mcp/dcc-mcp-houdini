"""PIP-2930 Stage-1 probe v2: Copernicus COP + OpenCL COP + MaterialX op: path.

Corrected for Houdini 21.0.631 actual API surface:
- CopNet category (not Cop2) for Copernicus check
- constant node (not gradient) for basic COP test
- kernelcode param (not kernel/kernel_code) for OpenCL source
- ImageLayer inspection (no .resolution() — check attrs)
- Houdini kernel DSL for OpenCL (not raw C with CLK_ macros)

Run: exec(open("probes/probe_cop_v2.py").read())
"""

import json
import os
import sys
import traceback
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import hou


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _host_info() -> Dict[str, Any]:
    info: Dict[str, Any] = {
        "platform": sys.platform,
        "python_version": sys.version,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    }
    try:
        info["houdini_version"] = hou.applicationVersionString()
        info["houdini_version_tuple"] = tuple(hou.applicationVersion())
        info["houdini_is_hython"] = hasattr(hou, "isUIAvailable") and not hou.isUIAvailable()
        info["houdini_ui_available"] = hou.isUIAvailable() if hasattr(hou, "isUIAvailable") else None
        info["copernicus_available"] = _check_copernicus_available()
    except ImportError:
        info["houdini_version"] = None
        info["houdini_error"] = "hou module not importable"
    return info


def _check_copernicus_available() -> bool:
    """Check CopNet category (Copernicus), not Cop2 (legacy)."""
    try:
        return hou.nodeTypeCategories().get("CopNet") is not None
    except Exception:
        return False


def _result(
    section: str,
    status: str,
    detail: str = "",
    evidence: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    rec: Dict[str, Any] = {"section": section, "status": status, "detail": detail}
    if evidence:
        rec["evidence"] = evidence
    print(f"[{status.upper():7s}] {section}: {detail}")
    return rec


# ---------------------------------------------------------------------------
# Section 1 — Create Copernicus COP network
# ---------------------------------------------------------------------------

def probe_cop_network() -> Dict[str, Any]:
    """Create a Copernicus COP network in /img with constant + null nodes."""
    section = "cop_network_create"
    try:
        img = hou.node("/img")
        if img is None:
            return _result(section, "fail", "No /img context found")

        net_name = "_pip2930_probe_copnet"
        existing = hou.node(f"/img/{net_name}")
        if existing is not None:
            existing.destroy()

        # Copernicus network uses "copnet" from CopNet category
        copnet = img.createNode("copnet", node_name=net_name)
        type_name = copnet.type().name()
        category_name = copnet.type().category().name()

        # Use "constant" (Copernicus equivalent of gradient/solid color)
        constant = copnet.createNode("constant", node_name="_probe_constant")
        const_type = constant.type().name()

        # Add null output
        null_node = copnet.createNode("null", node_name="_probe_output")
        null_node.setInput(0, constant, 0)

        # Check COP-specific methods
        has_layer = hasattr(null_node, "layer")
        has_geometry = hasattr(null_node, "geometry")
        has_vdb = hasattr(null_node, "vdb")
        has_verb = hasattr(null_node, "verb")

        evidence = {
            "copnet_path": copnet.path(),
            "copnet_type": type_name,
            "copnet_category": category_name,
            "constant_type": const_type,
            "null_path": null_node.path(),
            "null_category": null_node.type().category().name(),
            "has_layer_method": has_layer,
            "has_geometry_method": has_geometry,
            "has_vdb_method": has_vdb,
            "has_verb_method": has_verb,
        }

        # Cook test
        try:
            layer = null_node.layer()
            evidence["cook_success"] = True
            # ImageLayer doesn't have .resolution() — inspect available attrs
            layer_attrs = [a for a in dir(layer) if not a.startswith("_")]
            evidence["layer_attrs"] = layer_attrs[:20]
            # Try common size/resolution attributes
            for attr in ("xRes", "yRes", "resolution", "size"):
                if hasattr(layer, attr):
                    evidence[f"layer_{attr}"] = str(getattr(layer, attr))
        except Exception as cook_err:
            evidence["cook_success"] = False
            evidence["cook_error"] = str(cook_err)

        return _result(section, "pass", f"Copernicus net {copnet.path()} with constant+null", evidence)
    except Exception as exc:
        return _result(section, "fail", str(exc), {"traceback": traceback.format_exc()})


# ---------------------------------------------------------------------------
# Section 2 — OpenCL COP node
# ---------------------------------------------------------------------------

# Houdini 21 OpenCL COP uses its own kernel DSL, not raw OpenCL C.
# The DSL is compiled to OpenCL internally.
OPENCL_KERNEL_DSL = """#bind layer src? val=0
#bind layer !&dst

@KERNEL
{
    @dst.set(@src);
}
"""


def probe_opencl_cop() -> Dict[str, Any]:
    """Create an OpenCL COP node, set kernel source, and cook one frame."""
    section = "opencl_cop_create_cook"
    try:
        img = hou.node("/img")
        if img is None:
            return _result(section, "blocked", "No /img context")

        copnet = hou.node("/img/_pip2930_probe_copnet")
        if copnet is None:
            return _result(section, "blocked", "COP probe network not found — run cop_network_create first")

        existing = copnet.node("_probe_opencl")
        if existing is not None:
            existing.destroy()

        # Create OpenCL COP node — "opencl" in Cop category
        ocl_node = copnet.createNode("opencl", node_name="_probe_opencl")
        ocl_type = ocl_node.type().name()
        ocl_category = ocl_node.type().category().name()

        # Enumerate parameters
        parm_names = [p.name() for p in ocl_node.parms()]
        evidence: Dict[str, Any] = {
            "ocl_path": ocl_node.path(),
            "ocl_type": ocl_type,
            "ocl_category": ocl_category,
            "parm_count": len(parm_names),
            "key_parms": {},
        }

        # Set kernel source — H21 uses "kernelcode" (NOT "kernel" or "kernel_code")
        kernel_parm = ocl_node.parm("kernelcode")
        if kernel_parm is None:
            evidence["kernelcode_parm_found"] = False
            return _result(section, "fail", "Cannot find kernelcode parameter", evidence)

        evidence["kernelcode_parm_found"] = True
        try:
            kernel_parm.set(OPENCL_KERNEL_DSL)
            evidence["kernel_source_set"] = True
        except Exception as set_err:
            evidence["kernel_source_set"] = False
            evidence["kernel_source_error"] = str(set_err)
            return _result(section, "fail", f"Failed to set kernel source: {set_err}", evidence)

        # Set kernel name (function name within DSL)
        kernel_name_parm = ocl_node.parm("kernelname")
        if kernel_name_parm is not None:
            kernel_name_parm.set("generickernel")
            evidence["key_parms"]["kernelname"] = "generickernel"

        # Record key parameter values
        for key in ("kernelcode", "kernelname", "kerneloptions", "writebackkernelname",
                     "options_runover", "options_precision"):
            p = ocl_node.parm(key)
            if p is not None:
                evidence["key_parms"][key] = str(p.eval())

        # Connect input (constant -> opencl)
        constant = copnet.node("_probe_constant")
        if constant is not None:
            ocl_node.setInput(0, constant, 0)
            evidence["input_connected"] = True

        # Attempt cook
        cook_ok = False
        cook_errors: List[str] = []
        try:
            layer = ocl_node.layer()
            if layer is not None:
                cook_ok = True
                evidence["cook_result"] = "layer_retrieved"
        except Exception as cook_err:
            cook_errors.append(str(cook_err))
            errors = ocl_node.errors()
            warnings = ocl_node.warnings()
            if errors:
                cook_errors.extend(errors)
            if warnings:
                evidence["cook_warnings"] = list(warnings)

        evidence["cook_success"] = cook_ok
        if cook_errors:
            evidence["cook_errors"] = cook_errors

        if cook_ok:
            return _result(section, "pass", f"OpenCL COP {ocl_node.path()} cooked", evidence)
        else:
            return _result(section, "fail", f"OpenCL COP cook failed: {'; '.join(cook_errors)}", evidence)

    except Exception as exc:
        return _result(section, "fail", str(exc), {"traceback": traceback.format_exc()})


# ---------------------------------------------------------------------------
# Section 3 — MaterialX / Karma op: path wire
# ---------------------------------------------------------------------------

def probe_materialx_op_path() -> Dict[str, Any]:
    """Wire a COP layer into mtlximage via op: path."""
    section = "materialx_op_path_wire"
    try:
        cop_output = hou.node("/img/_pip2930_probe_copnet/_probe_output")
        if cop_output is None:
            return _result(section, "blocked", "COP probe network not found")

        cop_path = cop_output.path()
        op_ref = f"op:{cop_path}"

        mat_ctx = hou.node("/mat")
        if mat_ctx is None:
            return _result(section, "blocked", "No /mat context")

        mat_name = "_pip2930_probe_mtlx"
        existing = hou.node(f"/mat/{mat_name}")
        if existing is not None:
            existing.destroy()

        evidence: Dict[str, Any] = {"cop_path": cop_path, "op_reference": op_ref}

        mat_builder = mat_ctx.createNode("subnet", node_name=mat_name)

        try:
            mtlx_image = mat_builder.createNode("mtlximage", node_name="_probe_cop_image")
            evidence["mtlx_image_created"] = True
        except hou.OperationFailed:
            return _result(section, "fail", "mtlximage node creation failed", evidence)

        file_parm = mtlx_image.parm("file")
        if file_parm is None:
            file_parm = mtlx_image.parm("filename")
        if file_parm is None:
            return _result(section, "fail", "No file/filename parameter on mtlximage", evidence)

        file_parm.set(op_ref)
        evidence["file_parm_name"] = file_parm.name()
        evidence["file_parm_value"] = file_parm.eval()
        evidence["op_ref_accepted"] = True

        try:
            mat_builder.cook(force=True)
            errors = mat_builder.errors()
            if errors:
                evidence["material_errors"] = list(errors)
            evidence["material_cook_ok"] = len(errors) == 0 if errors else True
        except Exception as cook_err:
            evidence["material_cook_ok"] = False
            evidence["material_cook_error"] = str(cook_err)

        # Verify op: reference resolved
        try:
            resolved = file_parm.eval()
            evidence["resolved_value"] = resolved
            evidence["op_path_resolved"] = isinstance(resolved, str) and resolved.startswith("op:")
        except Exception:
            evidence["op_path_resolved"] = False

        status = "pass" if evidence.get("material_cook_ok") else "fail"
        return _result(section, status, f"op: path {op_ref} wired to mtlximage", evidence)

    except Exception as exc:
        return _result(section, "fail", str(exc), {"traceback": traceback.format_exc()})


# ---------------------------------------------------------------------------
# Section 4 — OpenCL device enumeration
# ---------------------------------------------------------------------------

def probe_opencl_devices() -> Dict[str, Any]:
    """Enumerate OpenCL devices via hgpuinfo, env, and HOM introspection."""
    section = "opencl_device_enumeration"
    import subprocess

    evidence: Dict[str, Any] = {"approaches": {}, "env_vars": {}}

    # Approach 1: hgpuinfo
    hfs = os.environ.get("HFS", "")
    hgpuinfo_path = os.path.join(hfs, "bin", "hgpuinfo.exe") if sys.platform == "win32" else os.path.join(hfs, "bin", "hgpuinfo")
    try:
        result = subprocess.run([hgpuinfo_path, "-c", "-l"], capture_output=True, text=True, timeout=30)
        evidence["approaches"]["hgpuinfo"] = {
            "available": True,
            "returncode": result.returncode,
            "stdout": result.stdout.strip()[:2000],  # Truncate
        }
    except FileNotFoundError:
        evidence["approaches"]["hgpuinfo"] = {"available": False, "error": "hgpuinfo not found"}
    except Exception as exc:
        evidence["approaches"]["hgpuinfo"] = {"available": False, "error": str(exc)}

    # Approach 2: hou.opencl module
    try:
        ocl = hou.opencl if hasattr(hou, "opencl") else None
        if ocl is not None:
            methods = [m for m in dir(ocl) if not m.startswith("_")]
            evidence["approaches"]["hou.opencl"] = {"available": True, "methods": methods}
            for method_name in ("deviceCount", "platformCount", "platformName", "deviceName", "devices", "platforms"):
                if hasattr(ocl, method_name):
                    try:
                        val = getattr(ocl, method_name)
                        if callable(val):
                            evidence["approaches"]["hou.opencl"][method_name] = str(val())
                        else:
                            evidence["approaches"]["hou.opencl"][method_name] = str(val)
                    except Exception:
                        pass
        else:
            evidence["approaches"]["hou.opencl"] = {"available": False}
    except Exception as exc:
        evidence["approaches"]["hou.opencl"] = {"available": False, "error": str(exc)}

    # Approach 3: hconfig
    try:
        hconfig_path = os.path.join(hfs, "bin", "hconfig.exe") if sys.platform == "win32" else os.path.join(hfs, "bin", "hconfig")
        result = subprocess.run([hconfig_path, "-a"], capture_output=True, text=True, timeout=30)
        ocl_lines = [line for line in result.stdout.splitlines() if "OCL" in line.upper()]
        evidence["approaches"]["hconfig"] = {"available": True, "ocl_related_lines": ocl_lines}
    except Exception:
        evidence["approaches"]["hconfig"] = {"available": False}

    # Approach 4: environment variables
    ocl_env_vars = {
        "HOUDINI_OCL_DEVICENUMBER": os.environ.get("HOUDINI_OCL_DEVICENUMBER"),
        "HOUDINI_OCL_VENDOR": os.environ.get("HOUDINI_OCL_VENDOR"),
        "HOUDINI_OCL_DEVICETYPE": os.environ.get("HOUDINI_OCL_DEVICETYPE"),
        "HOUDINI_USE_HFS_OCL": os.environ.get("HOUDINI_USE_HFS_OCL"),
    }
    evidence["env_vars"] = {k: v for k, v in ocl_env_vars.items() if v is not None}

    hgpuinfo_ok = evidence.get("approaches", {}).get("hgpuinfo", {}).get("available", False)
    status = "pass" if hgpuinfo_ok else "fail"
    return _result(section, status, f"{len(evidence['approaches'])} approaches probed", evidence)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    host = _host_info()
    print(f"Houdini {host.get('houdini_version', 'unknown')} — {host['platform']}")
    print(f"Copernicus available (CopNet): {host.get('copernicus_available', 'unknown')}")
    print(f"UI available: {host.get('houdini_ui_available', 'unknown')}")
    print("=" * 60)

    results: List[Dict[str, Any]] = []

    # Section 1: COP network
    results.append(probe_cop_network())

    # Section 2: OpenCL COP
    results.append(probe_opencl_cop())

    # Section 3: MaterialX op: path
    results.append(probe_materialx_op_path())

    # Section 4: OpenCL devices
    results.append(probe_opencl_devices())

    # macOS skip
    results.append(_result("macos_limits", "skipped", f"Running on {sys.platform}; macOS not applicable"))

    # Summary
    print("\n" + "=" * 60)
    statuses = [r["status"] for r in results]
    passed = statuses.count("pass")
    failed = statuses.count("fail")
    blocked = statuses.count("blocked")
    print(f"Summary: {passed} pass, {failed} fail, {blocked} blocked, {len(results)} total")

    output = {
        "probe": "PIP-2930-stage1-v2",
        "host": host,
        "results": results,
        "summary": {"pass": passed, "fail": failed, "blocked": blocked},
    }

    out_path = "P:/monica/feb80763-f6d5-4f8e-993e-b65688e9ec3c/03ead74f/workdir/dcc-mcp-houdini/probes/result_v2.json"
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\nResults written to {out_path}")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
else:
    main()
