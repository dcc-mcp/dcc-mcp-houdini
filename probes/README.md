# PIP-2930 Stage-1 Probes

Scripts to validate Houdini HOM APIs for marketplace extensions (COP shader,
OpenCL GPU, MaterialX op: path).

## Quick Start

```bash
# In hython or Houdini Python shell:

# 1. Full COP + OpenCL + MaterialX probe (the main one)
hython probes/probe_cop.py --output result.json

# 2. OpenCL device enumeration only (safe, no scene changes)
hython probes/probe_opencl_devices.py

# 3. OFX safety probe (optional, read-only)
hython probes/probe_ofx.py
```

## Scripts

| Script | What it does | Side effects |
|--------|-------------|--------------|
| `probe_cop.py` | Create COP network, OpenCL COP node, MaterialX op: wire, cook test, OpenCL device listing | Creates `/img/_pip2930_probe_copnet` and `/mat/_pip2930_probe_mtlx` nodes |
| `probe_opencl_devices.py` | Enumerate OpenCL devices via 7 methods (hgpuinfo, hconfig, env, hou.opencl, pyopencl, About dialog, HOM introspection) | None (read-only) |
| `probe_ofx.py` | Enumerate OFX bundles safely (reads plist/xml only, never loads DLLs) | None (read-only) |
| `matrix.md` | Compatibility matrix template to fill in | N/A |

## Probe output

Each probe prints pass/fail/blocked lines to stdout and writes a JSON file:

```json
{
  "probe": "PIP-2930-stage1",
  "host": {
    "houdini_version": "21.0.512",
    "platform": "win32",
    "copernicus_available": true
  },
  "results": [
    {"section": "cop_network_create", "status": "pass", "detail": "...", "evidence": {...}},
    {"section": "opencl_cop_create_cook", "status": "fail", "detail": "...", "evidence": {...}}
  ],
  "summary": {"pass": 3, "fail": 1, "blocked": 0}
}
```

## Section reference

| Section key | Probe |
|------------|-------|
| `cop_network_create` | Create Copernicus COP network, add gradient+null, cook |
| `opencl_cop_create_cook` | Create OpenCL COP node, set kernel source, cook |
| `materialx_op_path_wire` | Create MaterialX builder, set mtlximage.file to `op:` path, evaluate |
| `opencl_device_enumeration` | hgpuinfo, hou.opencl, hconfig, env, About dialog |
| `macos_limits` | macOS Vulkan/OpenCL limitation record (darwin only) |
| `uncertain_apis` | List of APIs needing implementer verification |

## Running on specific sections

```bash
hython probes/probe_cop.py --sections cop_network,opencl_devices
```

## macOS notes

- Vulkan viewport: **blocked** — macOS doesn't support Vulkan; Houdini uses Metal
- OpenCL: **likely blocked** — Apple deprecated OpenCL in macOS 10.14; GPU OpenCL unavailable on Apple Silicon
- Run `probe_opencl_devices.py` on macOS to confirm the actual state

## OFX Safety Decision

- **Enumeration**: SAFE — reading `.ofx.bundle/Contents/Info.plist` and directory walking doesn't load binaries
- **Loading**: UNSAFE — any `.ofx.bundle` loading involves `dlopen`/`LoadLibrary` of third-party native code
- **Product decision**: OFX remains product-declined for v1 per PIP-2925
