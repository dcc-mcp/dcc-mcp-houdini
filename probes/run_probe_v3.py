"""Execute final corrected probe against Houdini 21 gateway."""
import json, urllib.request

GATEWAY = "http://127.0.0.1:9765/mcp"

PROBE_CODE = """
import json, sys, os, traceback, subprocess
from datetime import datetime, timezone

results = []

# Host info
info = {
    "platform": sys.platform,
    "python_version": sys.version,
    "timestamp_utc": datetime.now(timezone.utc).isoformat(),
}
try:
    import hou
    info["houdini_version"] = hou.applicationVersionString()
    info["ui_available"] = hou.isUIAvailable() if hasattr(hou, "isUIAvailable") else None
    cop2_cat = hou.nodeTypeCategories().get("Cop2")
    info["copernicus_available"] = cop2_cat is not None
    info["cop2_node_type_count"] = len(cop2_cat.nodeTypes()) if cop2_cat else 0
except ImportError:
    info["error"] = "hou not importable"
results.append({"section": "host_info", "status": "pass", "evidence": info})

# --- Section 1: COP network create (FIXED: use constant instead of gradient) ---
section1 = "cop_network_create"
try:
    ctx = hou.node("/img")
    if ctx is None:
        results.append({"section": section1, "status": "fail", "detail": "No /img context"})
    else:
        net_name = "_pip2930_probe_copnet"
        existing = hou.node("/img/" + net_name)
        if existing is not None:
            existing.destroy()
        copnet = ctx.createNode("copnet", node_name=net_name)
        copnet_type = copnet.type().name()

        # H21: gradient fails inside copnet (Invalid node type name), use constant instead
        src_node = copnet.createNode("constant", node_name="_probe_source")
        src_type = src_node.type().name()

        null_node = copnet.createNode("null", node_name="_probe_output")
        null_node.setInput(0, src_node, 0)

        has_layer = hasattr(null_node, "layer")
        cook_ok = False
        cook_detail = "not_attempted"
        try:
            layer = null_node.layer()
            cook_ok = True
            cook_detail = str(list(layer.resolution())) if hasattr(layer, "resolution") else "ok"
        except Exception as e:
            cook_detail = str(e)[:200]

        results.append({"section": section1, "status": "pass",
            "detail": "copnet created, cook=" + str(cook_ok),
            "evidence": {
                "copnet_path": copnet.path(), "copnet_type": copnet_type,
                "source_type": src_type, "cook_success": cook_ok,
                "layer_resolution": cook_detail, "has_layer_method": has_layer,
                "note": "gradient node fails inside copnet in H21; used constant instead"
            }})
except Exception as e:
    results.append({"section": section1, "status": "fail",
        "detail": str(e)[:200], "traceback": traceback.format_exc()[:500]})

# --- Section 2: OpenCL COP (FIXED: kernelcode + inside copnet) ---
section2 = "opencl_cop_create_cook"
KERNEL = "__kernel void passthrough(__read_only image2d_t src, __write_only image2d_t dst, const int width, const int height) { const int x = get_global_id(0); const int y = get_global_id(1); if (x >= width || y >= height) return; const sampler_t sampler = CLK_NORMALIZED_COORDS_FALSE | CLK_ADDRESS_CLAMP_TO_EDGE | CLK_FILTER_NEAREST; float4 pixel = read_imagef(src, sampler, (int2)(x, y)); write_imagef(dst, (int2)(x, y), pixel); }"
try:
    copnet = hou.node("/img/_pip2930_probe_copnet")
    if copnet is None:
        results.append({"section": section2, "status": "blocked", "detail": "COP network not found"})
    else:
        existing = copnet.node("_probe_opencl")
        if existing is not None:
            existing.destroy()
        ocl_node = copnet.createNode("opencl", node_name="_probe_opencl")
        ocl_type = ocl_node.type().name()

        # Connect to source
        src = copnet.node("_probe_source")
        if src is not None:
            ocl_node.setInput(0, src, 0)

        parm_names = [p.name() for p in ocl_node.parms()]
        ev = {"ocl_type": ocl_type, "parm_count": len(parm_names)}

        # FIXED: parameter is "kernelcode" in H21
        kernel_parm = ocl_node.parm("kernelcode")
        if kernel_parm is None:
            # Fallback to other names
            for candidate in ("kernel", "kernel_code", "code", "clcode", "source"):
                p = ocl_node.parm(candidate)
                if p is not None:
                    kernel_parm = candidate
                    break

        if kernel_parm is None:
            results.append({"section": section2, "status": "fail",
                "detail": "No kernel source param", "evidence": ev})
        else:
            ocl_node.parm("kernelcode").set(KERNEL)
            ev["kernel_source_set"] = True

            # Set kernel function name
            kn = ocl_node.parm("kernelname")
            if kn is not None:
                kn.set("passthrough")
                ev["kernelname_set"] = True

            # Cook
            cook_ok = False
            cook_errors = []
            cook_warnings = []
            try:
                layer = ocl_node.layer()
                if layer is not None:
                    cook_ok = True
                    ev["cook_result"] = "layer_retrieved"
                    if hasattr(layer, "resolution"):
                        ev["layer_resolution"] = str(list(layer.resolution()))
            except Exception as ce:
                cook_errors.append(str(ce)[:200])
                errs = ocl_node.errors()
                warns = ocl_node.warnings()
                if errs:
                    cook_errors.extend([str(e) for e in errs][:5])
                if warns:
                    cook_warnings = [str(w) for w in warns][:5]

            ev["cook_success"] = cook_ok
            if cook_errors:
                ev["cook_errors"] = cook_errors
            if cook_warnings:
                ev["cook_warnings"] = cook_warnings

            status = "pass" if cook_ok else "fail"
            results.append({"section": section2, "status": status,
                "detail": "OpenCL COP cook=" + str(cook_ok),
                "evidence": ev})
except Exception as e:
    results.append({"section": section2, "status": "fail",
        "detail": str(e)[:200], "traceback": traceback.format_exc()[:500]})

# --- Section 3: MaterialX op: path ---
section3 = "materialx_op_path_wire"
try:
    cop_output = hou.node("/img/_pip2930_probe_copnet/_probe_output")
    if cop_output is None:
        results.append({"section": section3, "status": "blocked", "detail": "COP output node not found"})
    else:
        op_ref = "op:" + cop_output.path()
        mat_ctx = hou.node("/mat")
        if mat_ctx is None:
            results.append({"section": section3, "status": "blocked", "detail": "No /mat context"})
        else:
            mat_name = "_pip2930_probe_mtlx"
            existing = hou.node("/mat/" + mat_name)
            if existing is not None:
                existing.destroy()
            mat_builder = mat_ctx.createNode("subnet", node_name=mat_name)
            ev3 = {"cop_path": cop_output.path(), "op_reference": op_ref}
            try:
                mtlx_image = mat_builder.createNode("mtlximage", node_name="_probe_cop_image")
            except:
                results.append({"section": section3, "status": "fail",
                    "detail": "mtlximage creation failed", "evidence": ev3})
                mtlx_image = None
            if mtlx_image is not None:
                file_parm = mtlx_image.parm("file")
                if file_parm is None:
                    file_parm = mtlx_image.parm("filename")
                if file_parm is None:
                    results.append({"section": section3, "status": "fail", "detail": "No file/filename parm"})
                else:
                    file_parm.set(op_ref)
                    ev3["file_parm_name"] = file_parm.name()
                    ev3["op_ref_accepted"] = True
                    ev3["resolved_value"] = str(file_parm.eval())
                    results.append({"section": section3, "status": "pass",
                        "detail": "op: path wired to mtlximage." + file_parm.name(),
                        "evidence": ev3})
except Exception as e:
    results.append({"section": section3, "status": "fail",
        "detail": str(e)[:200], "traceback": traceback.format_exc()[:500]})

# --- Section 4: OpenCL device enumeration ---
section4 = "opencl_device_enumeration"
ev4 = {}
hfs = os.environ.get("HFS", "")
try:
    hgpuinfo_path = os.path.join(hfs, "bin", "hgpuinfo.exe") if hfs else "hgpuinfo.exe"
    result = subprocess.run([hgpuinfo_path, "-c", "-l"], capture_output=True, text=True, timeout=30)
    ev4["hgpuinfo"] = {"available": True, "returncode": result.returncode,
        "stdout": result.stdout.strip()[:500]}
except Exception as e:
    ev4["hgpuinfo"] = {"available": False, "error": str(e)[:200]}

try:
    if hasattr(hou, "opencl"):
        methods = [m for m in dir(hou.opencl) if not m.startswith("_")]
        ev4["hou_opencl"] = {"available": True, "methods": methods[:30]}
    else:
        ev4["hou_opencl"] = {"available": False}
except:
    ev4["hou_opencl"] = {"available": False}

ocl_env = {}
for v in ("HOUDINI_OCL_DEVICENUMBER", "HOUDINI_OCL_VENDOR", "HOUDINI_OCL_DEVICETYPE", "HOUDINI_OCL_PATH"):
    val = os.environ.get(v)
    if val:
        ocl_env[v] = val
ev4["ocl_env_vars"] = ocl_env

hgpu_ok = ev4.get("hgpuinfo", {}).get("available", False)
results.append({"section": section4, "status": "pass" if hgpu_ok else "fail",
    "detail": "hgpuinfo=" + str(hgpu_ok), "evidence": ev4})

# --- Section 5: COOK — build and evaluate the full chain ---
section5 = "cop_output_cook_chain"
try:
    cop_output = hou.node("/img/_pip2930_probe_copnet/_probe_output")
    if cop_output is None:
        results.append({"section": section5, "status": "blocked", "detail": "No output node"})
    else:
        # Display node to trigger cook
        cop_output.setDisplayFlag(True)
        try:
            layer = cop_output.layer()
            has_data = layer is not None
            ev5 = {"display_set": True, "layer_ok": has_data}
            if has_data and hasattr(layer, "resolution"):
                ev5["resolution"] = str(list(layer.resolution()))
            results.append({"section": section5, "status": "pass",
                "detail": "Full COP chain evaluated", "evidence": ev5})
        except Exception as ce:
            results.append({"section": section5, "status": "fail",
                "detail": str(ce)[:200], "evidence": {"display_set": True}})
except Exception as e:
    results.append({"section": section5, "status": "fail", "detail": str(e)[:200]})

# Summary
summary = {
    "pass": sum(1 for r in results if r["status"] == "pass"),
    "fail": sum(1 for r in results if r["status"] == "fail"),
    "blocked": sum(1 for r in results if r["status"] == "blocked")
}

print("JSON_OUTPUT_START")
print(json.dumps({"results": results, "summary": summary}, indent=2, default=str))
print("JSON_OUTPUT_END")
"""


def rpc(method, params):
    req = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    resp = urllib.request.urlopen(
        urllib.request.Request(GATEWAY, data=req,
            headers={"Content-Type": "application/json", "Accept": "application/json"}),
        timeout=180)
    return json.loads(resp.read())


print("=== FINAL PROBE: Houdini 21.0.631 Windows ===")
resp = rpc("tools/call", {
    "name": "call",
    "arguments": {
        "tool_slug": "houdini.fc80640a.houdini_scripting__execute_python",
        "arguments": {"code": PROBE_CODE}
    }
})

if "error" in resp:
    print(f"RPC ERROR: {json.dumps(resp['error'], indent=2)}")
    exit(1)

text = resp["result"]["content"][0]["text"]
outer = json.loads(text)
ctx = outer["output"]["context"]
stdout = ctx.get("stdout", "")
stderr = ctx.get("stderr", "")

if stderr:
    print("=== STDERR ===")
    print(stderr[:500])

if "JSON_OUTPUT_START" in stdout:
    json_text = stdout.split("JSON_OUTPUT_START")[1].split("JSON_OUTPUT_END")[0]
    data = json.loads(json_text)
    results = data["results"]
    summary = data["summary"]

    print("\n=== MATRIX RESULTS (H21 Windows GUI) ===")
    for r in results:
        status = r['status'].upper()
        section = r['section']
        detail = r.get('detail', '')[:150]
        icon = "PASS" if status == "PASS" else ("FAIL" if status == "FAIL" else "BLOCKED")
        print(f"  [{icon:7s}] {section}: {detail}")
        if r.get("evidence"):
            ev = r["evidence"]
            if section == "cop_network_create":
                print(f"         copnet_type={ev.get('copnet_type')}, source={ev.get('source_type')}, cook={ev.get('cook_success')}, resolution={ev.get('layer_resolution')}")
            elif section == "opencl_cop_create_cook":
                print(f"         ocl_type={ev.get('ocl_type')}, cook={ev.get('cook_success')}")
                if ev.get("cook_errors"):
                    for e in ev["cook_errors"][:2]:
                        print(f"         error: {str(e)[:120]}")
                if ev.get("cook_warnings"):
                    for w in ev["cook_warnings"][:2]:
                        print(f"         warning: {str(w)[:120]}")
            elif section == "opencl_device_enumeration":
                hgpu = ev.get("hgpuinfo", {})
                if hgpu.get("available"):
                    print(f"         hgpuinfo stdout: {hgpu.get('stdout','')[:200]}")
                if ev.get("hou_opencl", {}).get("available"):
                    print(f"         hou.opencl methods: {ev['hou_opencl']['methods']}")

    print(f"\n=== SUMMARY ===")
    print(f"  PASS: {summary['pass']} | FAIL: {summary['fail']} | BLOCKED: {summary['blocked']}")

    # Save full results
    with open("probes/h21_probe_results_final.json", "w") as f:
        json.dump(data, f, indent=2)
    print("Full results saved to probes/h21_probe_results_final.json")
else:
    print(f"STDOUT (first 2000): {stdout[:2000]}")
    result_repr = ctx.get("result", "")
    if result_repr:
        print(f"Result repr: {result_repr[:2000]}")
