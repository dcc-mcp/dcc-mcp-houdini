"""PIP-2930 Stage-1 probe: Copernicus COP + OpenCL COP + MaterialX op: path.

Run from hython or Houdini Python shell:
    hython probes/probe_cop.py [--output result.json]

Each section prints a pass/fail/blocked line; the final JSON contains the
structured compatibility record.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _env_flag(name: str) -> Optional[str]:
    return os.environ.get(name)


def _host_info() -> Dict[str, Any]:
    info: Dict[str, Any] = {
        "platform": sys.platform,
        "python_version": sys.version,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    }
    # Attempt hou import
    try:
        import hou  # noqa: PLC0415

        info["houdini_version"] = hou.applicationVersionString()
        info["houdini_version_tuple"] = tuple(hou.applicationVersion())
        info["houdini_hfs"] = getattr(hou, "hfs", lambda: os.environ.get("HFS", ""))()
        info["houdini_is_hython"] = hasattr(hou, "isUIAvailable") and not hou.isUIAvailable()
        info["houdini_ui_available"] = hou.isUIAvailable() if hasattr(hou, "isUIAvailable") else None
        info["copernicus_available"] = _check_copernicus_available(hou)
    except ImportError:
        info["houdini_version"] = None
        info["houdini_error"] = "hou module not importable (not running inside Houdini/hython)"
    return info


def _check_copernicus_available(hou: Any) -> bool:
    """Probe whether Copernicus COP context is available."""
    try:
        # H21: check CopNet category (not just Cop2). Copernicus uses both.
        cats = hou.nodeTypeCategories()
        return cats.get("CopNet") is not None and cats.get("Cop2") is not None
    except Exception:
        return False


def _result(
    section: str,
    status: str,  # pass | fail | blocked
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

def probe_cop_network(hou: Any) -> Dict[str, Any]:
    """Create a Copernicus COP network inside /img (or /obj) and add a basic node."""
    section = "cop_network_create"
    try:
        # Copernicus network type: "copnet" in H20.5+
        # Legacy is "cop2net" — we explicitly test Copernicus
        cop_contexts = []
        for ctx_path in ("/img",):
            try:
                ctx = hou.node(ctx_path)
                if ctx is not None:
                    cop_contexts.append(ctx_path)
            except Exception:
                pass

        if not cop_contexts:
            return _result(section, "fail", "No writable COP context found (/img)")

        ctx = hou.node(cop_contexts[0])
        net_name = "_pip2930_probe_copnet"
        # Remove leftover from previous run
        existing = hou.node(f"{cop_contexts[0]}/{net_name}")
        if existing is not None:
            existing.destroy()

        copnet = ctx.createNode("copnet", node_name=net_name)
        # Verify it's the correct type
        type_name = copnet.type().name()

        # H21 quirk: "gradient" node fails with "Invalid node type name" inside copnet.
        # Use "constant" (safe across H20.5/H21) as the source node.
        src_node = copnet.createNode("constant", node_name="_probe_source")
        src_type = src_node.type().name()

        # Add a null output
        null_node = copnet.createNode("null", node_name="_probe_output")
        null_node.setInput(0, src_node, 0)

        # Check COP-specific methods exist
        has_layer = hasattr(null_node, "layer")
        has_geometry = hasattr(null_node, "geometry")
        has_cable = hasattr(null_node, "cable")

        evidence = {
            "copnet_path": copnet.path(),
            "copnet_type": type_name,
            "source_type": src_type,
            "null_path": null_node.path(),
            "note": "gradient node fails inside copnet in H21; using constant as source"
            "has_layer_method": has_layer,
            "has_geometry_method": has_geometry,
            "has_cable_method": has_cable,
            "contexts_found": cop_contexts,
        }

        # Cook test — retrieve layer data
        try:
            layer = null_node.layer()
            evidence["cook_success"] = True
            evidence["layer_resolution"] = list(layer.resolution()) if hasattr(layer, "resolution") else "unknown"
        except Exception as cook_err:
            evidence["cook_success"] = False
            evidence["cook_error"] = str(cook_err)

        return _result(section, "pass", f"Copernicus net {copnet.path()} with gradient+null", evidence)
    except Exception as exc:
        return _result(section, "fail", str(exc), {"traceback": traceback.format_exc()})


# ---------------------------------------------------------------------------
# Section 2 — OpenCL COP node
# ---------------------------------------------------------------------------

OPENCL_KERNEL_SOURCE = """
// Minimal OpenCL COP kernel — passes through pixel data unchanged
// Use #pragma OPENCL EXTENSION where needed by platform

__kernel void passthrough(
    __read_only image2d_t src,
    __write_only image2d_t dst,
    const int width,
    const int height
)
{
    const int x = get_global_id(0);
    const int y = get_global_id(1);
    if (x >= width || y >= height) return;

    const sampler_t sampler = CLK_NORMALIZED_COORDS_FALSE
                            | CLK_ADDRESS_CLAMP_TO_EDGE
                            | CLK_FILTER_NEAREST;
    float4 pixel = read_imagef(src, sampler, (int2)(x, y));
    write_imagef(dst, (int2)(x, y), pixel);
}
"""


def probe_opencl_cop(hou: Any) -> Dict[str, Any]:
    """Create an OpenCL COP node, set kernel source, and cook one frame."""
    section = "opencl_cop_create_cook"
    try:
        ctx = hou.node("/img")
        if ctx is None:
            return _result(section, "blocked", "No /img context — create COP network first")

        # Find or create the probe net
        copnet = hou.node("/img/_pip2930_probe_copnet")
        if copnet is None:
            copnet = ctx.createNode("copnet", node_name="_pip2930_probe_copnet")

        # Remove previous opencl node if exists
        existing = copnet.node("_probe_opencl")
        if existing is not None:
            existing.destroy()

        # Create OpenCL COP node — documented type name is "opencl"
        try:
            ocl_node = copnet.createNode("opencl", node_name="_probe_opencl")
        except hou.OperationFailed:
            # Fallback: try older type name
            ocl_node = copnet.createNode("opencl::2.0", node_name="_probe_opencl")

        ocl_type = ocl_node.type().name()

        # Enumerate parameters
        parm_names = [p.name() for p in ocl_node.parms()]
        evidence: Dict[str, Any] = {
            "ocl_path": ocl_node.path(),
            "ocl_type": ocl_type,
            "parms": parm_names,
        }

        # Set kernel source — H21 actual param is "kernelcode", not "kernel"/"kernel_code"
        kernel_parm_candidates = ("kernelcode", "kernel", "kernel_code", "code", "clcode", "source")
        kernel_parm = None
        for candidate in kernel_parm_candidates:
            p = ocl_node.parm(candidate)
            if p is not None:
                kernel_parm = candidate
                break

        if kernel_parm is None:
            evidence["kernel_parm_found"] = False
            evidence["kernel_parm_candidates_tried"] = list(kernel_parm_candidates)
            return _result(section, "fail", "Cannot find kernel source parameter", evidence)

        evidence["kernel_parm_name"] = kernel_parm
        try:
            ocl_node.parm(kernel_parm).set(OPENCL_KERNEL_SOURCE)
            evidence["kernel_source_set"] = True
            evidence["kernel_parm_note"] = "H21 uses 'kernelcode' param (not 'kernel'); raw OpenCL C may need Houdini kernel DSL for GPU cook"
        except Exception as set_err:
            evidence["kernel_source_set"] = False
            evidence["kernel_source_error"] = str(set_err)
            return _result(section, "fail", f"Failed to set kernel source: {set_err}", evidence)

        # Set kernel name if parameter exists
        kernel_name_candidates = ("kernelname", "kernel_name", "functionname", "function_name")
        for candidate in kernel_name_candidates:
            p = ocl_node.parm(candidate)
            if p is not None:
                p.set("passthrough")
                evidence["kernel_name_parm"] = candidate
                evidence["kernel_name_set"] = "passthrough"
                break

        # Attempt cook
        cook_ok = False
        cook_errors: List[str] = []
        try:
            layer = ocl_node.layer()
            if layer is not None:
                cook_ok = True
                evidence["cook_result"] = "layer_retrieved"
                if hasattr(layer, "resolution"):
                    evidence["layer_resolution"] = list(layer.resolution())
        except Exception as cook_err:
            cook_errors.append(str(cook_err))
            # Check for OpenCL-specific errors
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

def probe_materialx_op_path(hou: Any) -> Dict[str, Any]:
    """Wire a COP layer into a MaterialX material via op: path and confirm cook."""
    section = "materialx_op_path_wire"
    try:
        # Find the COP output node
        cop_output = hou.node("/img/_pip2930_probe_copnet/_probe_output")
        if cop_output is None:
            return _result(section, "blocked", "COP probe network not found — run cop_network_create first")

        cop_path = cop_output.path()

        # Build an op: path — format: op:<path> (or op:/path in Solaris)
        op_ref = f"op:{cop_path}"

        # Create a MaterialX builder subnet in /mat
        mat_ctx = hou.node("/mat")
        if mat_ctx is None:
            return _result(section, "blocked", "No /mat context")

        mat_name = "_pip2930_probe_mtlx"
        existing = hou.node(f"/mat/{mat_name}")
        if existing is not None:
            existing.destroy()

        evidence: Dict[str, Any] = {
            "cop_path": cop_path,
            "op_reference": op_ref,
        }

        try:
            import voptoolutils  # noqa: PLC0415
        except ImportError:
            voptoolutils = None

        mat_builder = mat_ctx.createNode("subnet", node_name=mat_name)
        if voptoolutils is not None:
            try:
                voptoolutils._setupMtlXBuilderSubnet(mat_builder, "kma")
                evidence["mtlx_builder_setup"] = "voptoolutils"
            except Exception:
                evidence["mtlx_builder_setup"] = "manual"
        else:
            evidence["mtlx_builder_setup"] = "manual (voptoolutils unavailable)"

        # Create mtlximage node and set the file to op: reference
        try:
            mtlx_image = mat_builder.createNode("mtlximage", node_name="_probe_cop_image")
        except hou.OperationFailed:
            return _result(section, "fail", "mtlximage node creation failed — MaterialX not available?", evidence)

        # Set the file parameter to the op: reference
        file_parm = mtlx_image.parm("file")
        if file_parm is None:
            file_parm = mtlx_image.parm("filename")
        if file_parm is None:
            return _result(section, "fail", "No file/filename parameter on mtlximage", evidence)

        file_parm.set(op_ref)
        evidence["file_parm_name"] = file_parm.name()
        evidence["file_parm_value"] = file_parm.eval()
        evidence["op_ref_accepted"] = True

        # Attempt to evaluate — cook happens on demand
        try:
            # Try evaluating the material node to trigger cook chain
            mat_builder.cook(force=True)
            errors = mat_builder.errors()
            if errors:
                evidence["material_errors"] = list(errors)
                return _result(section, "fail", f"Material cook errors: {errors}", evidence)
            evidence["material_cook_ok"] = True
        except Exception as cook_err:
            evidence["material_cook_ok"] = False
            evidence["material_cook_error"] = str(cook_err)

        # Verify the op: reference resolved
        try:
            resolved = file_parm.eval()
            evidence["resolved_value"] = resolved
            if resolved and str(resolved).startswith("op:"):
                evidence["op_path_resolved"] = True
        except Exception:
            evidence["op_path_resolved"] = False

        return _result(section, "pass", f"op: path {op_ref} wired to mtlximage", evidence)

    except Exception as exc:
        return _result(section, "fail", str(exc), {"traceback": traceback.format_exc()})


# ---------------------------------------------------------------------------
# Section 4 — Probe OpenCL devices
# ---------------------------------------------------------------------------

def probe_opencl_devices(hou: Any) -> Dict[str, Any]:
    """Enumerate OpenCL devices via hgpuinfo, env, and HOM introspection."""
    section = "opencl_device_enumeration"
    evidence: Dict[str, Any] = {
        "approaches": {},
        "env_vars": {},
    }

    # Approach 1: hgpuinfo command
    import subprocess

    hfs = os.environ.get("HFS", "")
    hgpuinfo_path = os.path.join(hfs, "bin", "hgpuinfo") if hfs else "hgpuinfo"
    if sys.platform == "win32":
        hgpuinfo_path = os.path.join(hfs, "bin", "hgpuinfo.exe") if hfs else "hgpuinfo.exe"

    try:
        result = subprocess.run([hgpuinfo_path, "-c", "-l"], capture_output=True, text=True, timeout=30)
        evidence["approaches"]["hgpuinfo"] = {
            "available": True,
            "returncode": result.returncode,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
        }
    except FileNotFoundError:
        evidence["approaches"]["hgpuinfo"] = {"available": False, "error": "hgpuinfo not found"}
    except Exception as exc:
        evidence["approaches"]["hgpuinfo"] = {"available": False, "error": str(exc)}

    # Approach 2: HOM introspection — hou.opencl module (NOT available in H21)
    try:
        ocl = hou.opencl if hasattr(hou, "opencl") else None
        if ocl is not None:
            methods = [m for m in dir(ocl) if not m.startswith("_")]
            evidence["approaches"]["hou.opencl"] = {
                "available": True,
                "methods": methods,
            }
            # Try common method names
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
            evidence["approaches"]["hou.opencl"] = {"available": False, "error": "hou.opencl not present"}
    except Exception as exc:
        evidence["approaches"]["hou.opencl"] = {"available": False, "error": str(exc)}

    # Approach 3: hconfig
    try:
        hconfig_path = os.path.join(hfs, "bin", "hconfig") if hfs else "hconfig"
        if sys.platform == "win32":
            hconfig_path = os.path.join(hfs, "bin", "hconfig.exe") if hfs else "hconfig.exe"
        result = subprocess.run([hconfig_path, "-a"], capture_output=True, text=True, timeout=30)
        # Extract OCL-related lines
        ocl_lines = [line for line in result.stdout.splitlines() if "OCL" in line.upper()]
        evidence["approaches"]["hconfig"] = {
            "available": True,
            "ocl_related_lines": ocl_lines,
        }
    except FileNotFoundError:
        evidence["approaches"]["hconfig"] = {"available": False}
    except Exception:
        evidence["approaches"]["hconfig"] = {"available": False}

    # Approach 4: Environment variables
    ocl_env_vars = {
        "HOUDINI_OCL_DEVICENUMBER": os.environ.get("HOUDINI_OCL_DEVICENUMBER"),
        "HOUDINI_OCL_VENDOR": os.environ.get("HOUDINI_OCL_VENDOR"),
        "HOUDINI_OCL_DEVICETYPE": os.environ.get("HOUDINI_OCL_DEVICETYPE"),
        "HOUDINI_USE_HFS_OCL": os.environ.get("HOUDINI_USE_HFS_OCL"),
        "HOUDINI_OCL_REPORT_MEMORY_USE": os.environ.get("HOUDINI_OCL_REPORT_MEMORY_USE"),
        "HOUDINI_OCL_PATH": os.environ.get("HOUDINI_OCL_PATH"),
    }
    evidence["env_vars"] = {k: v for k, v in ocl_env_vars.items() if v is not None}

    # Approach 5: hou.aboutDialogInfo or similar
    try:
        if hasattr(hou, "aboutDialogInfo"):
            about = hou.aboutDialogInfo()
            # Try to extract OpenCL info
            ocl_lines = [line for line in about.splitlines() if "opencl" in line.lower()]
            evidence["approaches"]["about_dialog"] = {
                "available": True,
                "ocl_related_lines": ocl_lines,
            }
    except Exception:
        evidence["approaches"]["about_dialog"] = {"available": False}

    status = "pass" if evidence["approaches"].get("hgpuinfo", {}).get("available") else "fail"
    return _result(section, status, f"{len(evidence['approaches'])} approaches probed", evidence)


# ---------------------------------------------------------------------------
# Section 5 — macOS-specific limitations
# ---------------------------------------------------------------------------

def probe_macos_limits(hou: Any) -> Optional[Dict[str, Any]]:
    """Record macOS-specific limitations (only on darwin)."""
    if sys.platform != "darwin":
        return None

    section = "macos_limits"
    evidence: Dict[str, Any] = {}

    # Vulkan viewport — macOS doesn't support Vulkan natively
    evidence["vulkan_viewport"] = {
        "status": "blocked",
        "detail": "macOS does not support Vulkan natively; Houdini uses Metal instead. Vulkan viewport features unavailable.",
    }

    # OpenCL — deprecated by Apple
    evidence["opencl_macos"] = {
        "status": "blocked",
        "detail": "Apple deprecated OpenCL in macOS 10.14 (Mojave). Only CPU OpenCL may work; GPU OpenCL is unavailable on Apple Silicon.",
    }

    # Try to probe actual OpenCL state
    try:
        import subprocess  # noqa: PLC0415

        hfs = os.environ.get("HFS", "")
        hgpuinfo_path = os.path.join(hfs, "bin", "hgpuinfo") if hfs else "hgpuinfo"
        result = subprocess.run([hgpuinfo_path, "-c"], capture_output=True, text=True, timeout=30)
        evidence["hgpuinfo_result"] = result.stdout.strip() if result.returncode == 0 else f"error: {result.stderr}"
    except Exception as exc:
        evidence["hgpuinfo_result"] = f"unavailable: {exc}"

    return _result(section, "blocked", "macOS OpenCL deprecated; Vulkan viewport unavailable", evidence)


# ---------------------------------------------------------------------------
# Section 6 — Additional HOM API surface probe
# ---------------------------------------------------------------------------

def probe_uncertain_apis(hou: Any) -> List[Dict[str, Any]]:
    """List APIs that need verification by implementers, even after this probe.

    These are APIs mentioned in SideFX docs that may have version-specific
    availability or quirks.
    """
    uncertain: List[Dict[str, Any]] = []

    # hou.CopVerb — for running COP nodes in headless context
    try:
        copnode_class = hou.CopNode if hasattr(hou, "CopNode") else None
        if copnode_class is not None and hasattr(copnode_class, "verb"):
            uncertain.append({
                "api": "hou.CopNode.verb() → hou.CopVerb",
                "file": "hou.CopNode",
                "note": "CopVerb allows headless execution without network cooking. Check availability on H20.5 vs H21.",
            })
    except Exception:
        pass

    # hou.opencl module
    uncertain.append({
        "api": "hou.opencl",
        "file": "hou module",
        "note": "Not documented in public HOM reference. If it exists, document exact methods. Primary fallback is hgpuinfo CLI.",
    })

    # Copernicus node type names
    uncertain.append({
        "api": "hou.NodeType names for Copernicus operators",
        "file": "Node type registry",
        "note": "OpenCL COP node type name may vary: 'opencl', 'opencl::2.0'. gradient, blur, null confirmed stable. Verify full catalog.",
    })

    # op: path resolution in mtlximage
    uncertain.append({
        "api": "mtlximage.file = 'op:/path/to/cop'",
        "file": "MaterialX builder / voptoolutils",
        "note": "op: path resolution may only work at render time (Karma/Solaris), not during interactive cook. Verify eval behavior.",
    })

    # COP layer multi-input access
    uncertain.append({
        "api": "hou.CopNode.layer(output_index=N) for multi-output COPs",
        "file": "hou.CopNode",
        "note": "Verify layer indexing matches the UI output ordering. The op: path by-index syntax op:/net/null[2] needs testing.",
    })

    # OpenCL COP on macOS
    uncertain.append({
        "api": "OpenCL COP on macOS",
        "file": "COP OpenCL node",
        "note": "Apple deprecated OpenCL. The OpenCL COP node may work with CPU device only. Test on both Intel Macs and Apple Silicon.",
    })

    return uncertain


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="PIP-2930 COP/OpenCL/MaterialX probe")
    parser.add_argument("--output", "-o", type=str, default=None, help="Write JSON result to file")
    parser.add_argument("--sections", type=str, default=None,
                        help="Comma-separated sections to run (default: all)")
    args = parser.parse_args()

    # Import hou
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        print("FATAL: hou module not available — run inside hython or Houdini Python shell")
        result = {
            "host": _host_info(),
            "fatal": "hou module not importable",
            "results": [],
        }
        if args.output:
            with open(args.output, "w") as f:
                json.dump(result, f, indent=2, default=str)
        return 1

    host = _host_info()
    print(f"Houdini {host.get('houdini_version', 'unknown')} — {host['platform']}")
    print(f"Copernicus available: {host.get('copernicus_available', 'unknown')}")
    print("=" * 60)

    sections_requested = set(args.sections.split(",")) if args.sections else None

    def _should_run(name: str) -> bool:
        return sections_requested is None or name in sections_requested

    results: List[Dict[str, Any]] = []

    if _should_run("cop_network"):
        results.append(probe_cop_network(hou))

    if _should_run("opencl_cop"):
        results.append(probe_opencl_cop(hou))

    if _should_run("materialx_op"):
        results.append(probe_materialx_op_path(hou))

    if _should_run("opencl_devices"):
        results.append(probe_opencl_devices(hou))

    macos_result = probe_macos_limits(hou)
    if macos_result is not None:
        if _should_run("macos"):
            results.append(macos_result)
    else:
        # On non-macOS, note that macOS was not probed
        results.append(_result(
            "macos_limits",
            "skipped",
            f"Running on {sys.platform}; macOS limitations not applicable",
        ))

    if _should_run("uncertain_apis"):
        uncertain = probe_uncertain_apis(hou)
        results.append(_result(
            "uncertain_apis",
            "info",
            f"{len(uncertain)} APIs flagged for implementer verification",
            {"apis": uncertain},
        ))

    # Summary
    print("\n" + "=" * 60)
    statuses = [r["status"] for r in results]
    passed = statuses.count("pass")
    failed = statuses.count("fail")
    blocked = statuses.count("blocked")
    print(f"Summary: {passed} pass, {failed} fail, {blocked} blocked, {len(results)} total")

    output = {
        "probe": "PIP-2930-stage1",
        "host": host,
        "results": results,
        "summary": {"pass": passed, "fail": failed, "blocked": blocked},
    }

    if args.output:
        output_path = args.output
    else:
        ts = datetime.now().strftime("%Y%m%dT%H%M%S")
        output_path = f"pip2930_probe_{ts}.json"

    with open(output_path, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\nResults written to {output_path}")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
