"""Quick OpenCL COP cook test with minimal changes."""
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
        result["error"] = "ocl not found"
    else:
        # Just check state - no changes
        result["errors"] = [str(e) for e in ocl.errors()] if ocl.errors() else []
        result["warnings"] = [str(w) for w in ocl.warnings()] if ocl.warnings() else []

        # Check bindings
        for pname in ("input1_name", "input1_type", "input1_optional",
                       "output1_name", "output1_type", "output1_precision",
                       "options_runover", "options_precision"):
            p = ocl.parm(pname)
            if p:
                result[pname] = str(p.eval())

        # Check inputs
        result["input_count"] = len(ocl.inputs())
        result["output_count"] = len(ocl.outputs())

print("RESULT_JSON:")
print(json.dumps(result, indent=2, default=str))
"""

def rpc(method, params):
    req = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    resp = urllib.request.urlopen(
        urllib.request.Request(GATEWAY, data=req,
            headers={"Content-Type": "application/json", "Accept": "application/json"}),
        timeout=60)
    return json.loads(resp.read())

print("Sending...")
resp = rpc("tools/call", {
    "name": "call",
    "arguments": {
        "tool_slug": "houdini.fc80640a.houdini_scripting__execute_python",
        "arguments": {"code": CODE}
    }
})
print("Response received")

text = resp["result"]["content"][0]["text"]
outer = json.loads(text)
stdout = outer["output"]["context"]["stdout"]

if "RESULT_JSON:" in stdout:
    json_text = stdout.split("RESULT_JSON:\n", 1)[1].strip()
    result = json.loads(json_text)
    print(json.dumps(result, indent=2))
else:
    print(stdout[:2000])
