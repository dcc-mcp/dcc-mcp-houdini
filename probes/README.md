# PIP-2930 Stage-1 Probes

> **Audience: Developer / QA only.** These are spike verification scripts, not
> product features. They create temporary Houdini nodes and produce
> engineering diagnostics. End users should use marketplace extension
> packages instead (see PIP-2932, PIP-2933).

Scripts to validate Houdini HOM APIs for marketplace extensions (COP shader,
OpenCL GPU, MaterialX `op:` path).

## Quick Start

```powershell
# Canonical command (H21-corrected):
hython probes/probe_cop_v2.py

# Standalone OpenCL device enumeration (safe, no scene changes):
hython probes/probe_opencl_devices.py

# OFX safety probe (optional, read-only):
hython probes/probe_ofx.py
```

## Agent / Gateway Execution

Agents connecting through the dcc-mcp gateway can materialize and execute
probes without local `hython`:

1. Discover the target Houdini instance via `GET http://127.0.0.1:9765/instances`
2. Use `execute_python` tool with `exec(open(".../probe_cop_v2.py").read())`
   against the instance's MCP endpoint
3. Collect stdout and the JSON output file

### JSON Output Contract

Every probe writes a structured JSON file. Schema:

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
      "evidence": { "...": "structured evidence dict" }
    }
  ],
  "summary": {"pass": 4, "fail": 1, "blocked": 0}
}
```

Exit code: `0` = all sections pass; `1` = at least one `fail`.

## Scripts

| Script | Purpose | Side effects |
|--------|---------|--------------|
| `probe_cop_v2.py` | **Canonical.** Create Copernicus COP network, OpenCL COP node, MaterialX `op:` wire, cook test, OpenCL device listing. Corrected for H21 API surface. | Creates `/img/_pip2930_probe_copnet` and `/mat/_pip2930_probe_mtlx` |
| `probe_cop.py` | Original (pre-H21) probe. Retained for H20.5 fallback only; may fail on H21 due to `gradient`/`kernel_code` assumptions. | Same as v2 |
| `probe_opencl_devices.py` | Enumerate OpenCL devices via 7 methods | None (read-only) |
| `probe_ofx.py` | Enumerate OFX bundles safely (reads plist/xml only, never loads DLLs) | None (read-only) |
| `matrix.md` | Compatibility matrix — H21 Windows filled, others pending | N/A |

## Side Effects & Cleanup

`probe_cop_v2.py` and `probe_cop.py` create Houdini nodes:
- `/img/_pip2930_probe_copnet` — Copernicus COP network (constant, null, opencl)
- `/mat/_pip2930_probe_mtlx` — MaterialX builder subnet with mtlximage

Probes attempt to destroy leftover nodes from prior runs before creating new
ones. To manually clean up:

```python
import hou
for path in ("/img/_pip2930_probe_copnet", "/mat/_pip2930_probe_mtlx"):
    n = hou.node(path)
    if n: n.destroy()
```

## H21 Verified Results

| Section | Status |
|---------|:------:|
| COP network create | pass |
| COP cook | pass |
| OpenCL COP create | pass |
| OpenCL kernel source set | pass |
| OpenCL COP cook | **fail** — CPU-only OpenCL on this host |
| MaterialX `op:` path wire | pass |
| OpenCL device enumeration | pass |
| `hou.opencl` module | **fail** — not available in H21 |

Host: `houdini@21.0.631`, Windows 11 GUI. OpenCL COP cook failure is
platform-specific: Intel OpenCL 1.2 on AMD Ryzen 9 9950X (CPU only, no
GPU OpenCL runtime). May pass on a GPU-enabled machine. See `matrix.md`
for full evidence.

## Running Specific Sections

```powershell
hython probes/probe_cop_v2.py --sections cop_network,opencl_devices
```

## macOS Notes

- Vulkan viewport: **blocked** — macOS doesn't support Vulkan; Houdini uses Metal
- OpenCL: **likely blocked** — Apple deprecated OpenCL in macOS 10.14; GPU OpenCL unavailable on Apple Silicon
- Run `probe_opencl_devices.py` on macOS to confirm the actual state

## OFX Safety Decision

- **Enumeration**: SAFE — reading `.ofx.bundle/Contents/Info.plist` and directory walking doesn't load binaries
- **Loading**: UNSAFE — any `.ofx.bundle` loading involves `dlopen`/`LoadLibrary` of third-party native code
- **Product decision**: OFX remains product-declined for v1 per PIP-2925
