# PIP-2930 Compatibility Gate

> **Audience: Developer / QA only.** These are pre-flight verification
> scripts, not product features. They create temporary Houdini nodes and
> produce engineering diagnostics. End users should use marketplace
> extension packages (PIP-2932, PIP-2933).

Repeatable smoke gate for Houdini COP/OpenCL/MaterialX compatibility.
Run before marketplace extension development or release on any new
Houdini version, OS, or GPU configuration.

## Quick Start

```powershell
# Canonical smoke probe (COP network + OpenCL COP + MaterialX op: path):
hython probes/probe_cop.py

# Standalone OpenCL device enumeration (safe, no scene changes):
hython probes/probe_opencl_devices.py
```

## Scripts

| Script | Purpose | Side effects |
|--------|---------|--------------|
| `probe_cop.py` | **Gate.** Create Copernicus COP network, OpenCL COP node, MaterialX `op:` wire, cook test, OpenCL device listing. Corrected for H21 API surface. | Creates `/img/_pip2930_probe_copnet` and `/mat/_pip2930_probe_mtlx` |
| `probe_opencl_devices.py` | **Gate.** Enumerate OpenCL devices via hgpuinfo, hconfig, env, and HOM introspection. | None (read-only) |
| `matrix.md` | **Record.** Compatibility matrix — H21 Windows filled, others pending. | N/A |

## Agent / Gateway Execution

Agents connecting through the dcc-mcp gateway can execute probes without
local `hython`:

1. Discover target Houdini instance via `GET http://127.0.0.1:9765/instances`
2. Call `execute_python` with `exec(open(".../probe_cop.py").read())`
   against the instance's MCP endpoint
3. Collect stdout and the JSON output file

## JSON Output Contract

Every probe writes a structured JSON file:

```json
{
  "probe": "PIP-2930-stage1",
  "host": {
    "houdini_version": "21.0.631",
    "platform": "win32",
    "copernicus_available": true
  },
  "results": [
    {
      "section": "cop_network_create",
      "status": "pass|fail|blocked|skipped|info",
      "detail": "human-readable one-liner",
      "evidence": { "...": "structured dict" }
    }
  ],
  "summary": {"pass": 4, "fail": 1, "blocked": 0}
}
```

Exit code: `0` = all sections pass; `1` = at least one `fail`.

## Side Effects & Cleanup

`probe_cop.py` creates Houdini nodes:
- `/img/_pip2930_probe_copnet` — Copernicus COP network (constant, null, opencl)
- `/mat/_pip2930_probe_mtlx` — MaterialX builder subnet with mtlximage

Probes attempt to destroy leftovers from prior runs. Manual cleanup:

```python
import hou
for path in ("/img/_pip2930_probe_copnet", "/mat/_pip2930_probe_mtlx"):
    n = hou.node(path)
    if n: n.destroy()
```

## H21 Verified Results (Windows GUI, `houdini@21.0.631`)

**11/13 primary cells PASS, 2 FAIL.**

| Section | Status | Note |
|---------|:------:|------|
| hython import | pass | |
| GUI session | pass | |
| Copernicus available | pass | `CopNet` category |
| COP network create | pass | `copnet` + `constant` + `null` |
| COP cook | pass | `null.layer()` ok |
| OpenCL COP create | pass | `opencl` node type exists |
| OpenCL kernel source set | pass | `kernelcode` param |
| OpenCL COP cook | **fail** | CPU-only OpenCL, raw C kernel binding fails |
| MaterialX builder | pass | `mtlximage` created |
| mtlximage op: path set | pass | `file = "op:/img/..."` |
| op: path resolve | pass | `eval()` returns `op:` string |
| OpenCL devices detected | pass | `hgpuinfo -c -l` |
| hou.opencl module | **fail** | Not in H21.0.631 |

OpenCL COP cook is the **primary gate** for GPU/OpenCL readiness (PIP-2933).
It failed on this CPU-only platform (Intel OpenCL 1.2 on AMD Ryzen 9 9950X).
May pass with GPU OpenCL runtime. See `matrix.md` for full evidence.

**Conclusion**: Copernicus COP + MaterialX `op:` path → ready for stage-2.
GPU/OpenCL COP cook → **not ready**; needs GPU-enabled host re-test.

## H21 API Corrections

Discovered during live H21 gateway execution:

| Assumption | H21 actual |
|---|---|
| `gradient` node inside copnet | FAILS — use `constant` |
| `kernel`/`kernel_code` param | `kernelcode` |
| `hou.opencl` module | Not available; use `hgpuinfo` |
| Copernicus in `Cop2` category | Also in `CopNet` category |

## OFX Safety

Enumeration via `Info.plist`/`Plugin.xml` text reading is safe. Loading any
`.ofx.bundle` involves native code execution — product-declined for v1.
