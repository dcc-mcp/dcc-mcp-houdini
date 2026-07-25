"""Diagnose OpenCL COP cook failure in detail."""
import json, urllib.request

GATEWAY = "http://127.0.0.1:9765/mcp"

CODE = """
import hou, json

result = {}

copnet = hou.node("/img/_pip2930_probe_copnet")
if copnet is None:
    result["error"] = "copnet not found"
else:
    ocl = copnet.node("_probe_opencl")
    if ocl is None:
        result["error"] = "opencl node not found"
    else:
        result["ocl_exists"] = True
        result["ocl_path"] = ocl.path()

        # Check current state
        result["errors"] = [str(e) for e in ocl.errors()] if ocl.errors() else []
        result["warnings"] = [str(w) for w in ocl.warnings()] if ocl.warnings() else []

        # Check kernelcode value
        kc = ocl.parm("kernelcode")
        if kc:
            result["kernelcode_set"] = True
            result["kernelcode_len"] = len(kc.eval())
        else:
            result["kernelcode_set"] = False

        # Check kernelname
        kn = ocl.parm("kernelname")
        if kn:
            result["kernelname_value"] = kn.eval()

        # Check all parm values for important ones
        for pname in ("kernelname", "options_runover", "options_precision", "options_time"):
            p = ocl.parm(pname)
            if p:
                result[f"parm_{pname}"] = str(p.eval())

        # Try cooking with more debugging
        try:
            # Set HOUDINI_OCL_REPORT_BUILD_LOGS equivalent
            ocl.parm("displaycode").set(True)  # Show generated code
            layer = ocl.layer()
            result["cook_after_display"] = "succeeded" if layer else "null_layer"
        except Exception as e:
            result["cook_error"] = str(e)[:500]

        # Check generated code
        gc_parm = ocl.parm("generatedcode")
        if gc_parm:
            gc = gc_parm.eval()
            result["generatedcode_available"] = bool(gc)
            result["generatedcode_len"] = len(gc) if gc else 0
            if gc:
                result["generatedcode_first"] = gc[:500]

        # Check compile errors from display
        result["errors_after"] = [str(e) for e in ocl.errors()] if ocl.errors() else []
        result["warnings_after"] = [str(w) for w in ocl.warnings()] if ocl.warnings() else []

print("RESULT_JSON:")
print(json.dumps(result, indent=2, default=str))
"""

def rpc(method, params):
    req = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    resp = urllib.request.urlopen(
        urllib.request.Request(GATEWAY, data=req,
            headers={"Content-Type": "application/json", "Accept": "application/json"}),
        timeout=120)
    return json.loads(resp.read())

resp = rpc("tools/call", {
    "name": "call",
    "arguments": {
        "tool_slug": "houdini.fc80640a.houdini_scripting__execute_python",
        "arguments": {"code": CODE}
    }
})

text = resp["result"]["content"][0]["text"]
outer = json.loads(text)
stdout = outer["output"]["context"]["stdout"]

if "RESULT_JSON:" in stdout:
    json_text = stdout.split("RESULT_JSON:\n", 1)[1].strip()
    result = json.loads(json_text)
    print(json.dumps(result, indent=2))
else:
    print(stdout[:3000])
