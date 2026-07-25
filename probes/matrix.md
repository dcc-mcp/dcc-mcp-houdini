# PIP-2930 Compatibility Matrix

> Status: H21 Windows GUI — 4/4 primary cells PASS (2026-07-25)

## Primary: Houdini 21.x

| Test | H21 / Windows | H21 / Linux | H21 / macOS |
|------|:------------:|:-----------:|:-----------:|
| **hython import** (hou available) | pass | ? | ? |
| **GUI session** (isUIAvailable) | pass | ? | ? |
| **Copernicus available** (CopNet category) | pass | ? | ? |
| **COP network create** (constant + null) | pass | ? | ? |
| **COP cook** (null.layer()) | pass | ? | ? |
| **OpenCL COP create** (node type exists) | pass | ? | ? |
| **OpenCL kernel source set** (kernelcode parm) | pass | ? | ? |
| **OpenCL COP cook** (ocl_node.layer()) | pass | ? | ? |
| **MaterialX builder** (mtlximage create) | pass | ? | ? |
| **mtlximage op: path set** (file = "op:...") | pass | ? | ? |
| **op: path resolve** (eval at cook time) | pass | ? | ? |
| **OpenCL devices detected** (hgpuinfo -c -l) | pass | ? | ? |
| **hou.opencl module** (exists + methods) | fail | ? | ? |

### H21 / Windows evidence

- **Host**: Houdini 21.0.631, Windows 11, UI available, Python 3.11.7
- **COP network**: `copnet` node type in `CopNet` category; `constant` + `null` nodes created; `hou.CopNode` exposes `layer()`, `geometry()`, `vdb()`, `verb()`
- **OpenCL COP**: `opencl` node in `Cop` category; 38 parameters; kernel source via `kernelcode` parm (Houdini kernel DSL); cook returns valid ImageLayer
- **MaterialX op: path**: `mtlximage.file = "op:/img/_pip2930_probe_copnet/_probe_output"` — accepted and resolves correctly; material cook ok
- **OpenCL devices**: `hgpuinfo -c -l` detects 3 platforms (Intel CPU, NVIDIA RTX 5080 CUDA, AMD iGPU gfx1036); `hou.opencl` module not present; 20 `HOUDINI_OCL_*` config keys via `hconfig`

## Secondary: Houdini 20.5.x

| Test | H20.5 / Windows | H20.5 / Linux | H20.5 / macOS |
|------|:---------------:|:-------------:|:-------------:|
| **hython import** | ? | ? | ? |
| **GUI session** | ? | ? | ? |
| **Copernicus available** | ? | ? | ? |
| **COP network create** | ? | ? | ? |
| **COP cook** | ? | ? | ? |
| **OpenCL COP create** | ? | ? | ? |
| **OpenCL kernel source set** | ? | ? | ? |
| **OpenCL COP cook** | ? | ? | ? |
| **MaterialX builder** | ? | ? | ? |
| **mtlximage op: path set** | ? | ? | ? |
| **op: path resolve** | ? | ? | ? |
| **OpenCL devices detected** | ? | ? | ? |

## macOS Limitations

| Limitation | H21 macOS | H20.5 macOS | Evidence |
|-----------|:---------:|:-----------:|----------|
| **Vulkan viewport** | blocked | blocked | macOS does not support Vulkan; Metal only |
| **GPU OpenCL** | ? | ? | Apple deprecated OpenCL in 10.14; may work CPU-only |
| **OpenCL COP cook** | ? | ? | Depends on OpenCL runtime availability |
| **COP network create** | ? | ? | Copernicus: HOM API, should work |
| **op: MaterialX wire** | ? | ? | Karma/MaterialX: should work (CPU render) |

## H21 API Corrections (vs initial assumptions)

These were discovered during live H21 execution and differ from SideFX documentation and earlier assumptions:

| Original assumption | H21 actual | Impact |
|---|---|---|
| Copernicus check: `Cop2` category | Use `CopNet` category | `_check_copernicus_available()` must check `CopNet` not `Cop2` |
| `gradient` COP node | Use `constant` (or `ramp`) | `gradient` is SOP only; not in Copernicus Cop category |
| `kernel` / `kernel_code` param | Use `kernelcode` | OpenCL source set via `ocl_node.parm("kernelcode").set(...)` |
| Raw OpenCL C kernel | Houdini kernel DSL | `@KERNEL{ @dst.set(@src); }` with `#bind layer` directives |
| `layer.resolution()` | `layer.dataWindow`, `layer.displayWindow` | ImageLayer inspection uses different attrs |
| `hou.CopNode.cable()` | Not available | Use `vdb()` and `verb()` instead; cable ops via separate nodes |
| `hou.opencl` public module | Not available | Fall back to `hgpuinfo -c -l` and `hconfig -a` |

## Uncertain APIs (for implementers)

| API | File | Risk | Verified? |
|-----|------|------|:---------:|
| `hou.CopNode.verb()` → `hou.CopVerb` | hou.CopNode | Headless COP execution; H21 confirmed `hasVerb` + `verb()` exist | H21 ✓ |
| `hou.opencl` module | hou module | **Not available** in H21; use `hgpuinfo` + `hconfig` | H21 ✓ (absent) |
| OpenCL COP node type name | Node registry | Confirmed: `opencl` (Cop category) — stable in H21 | H21 ✓ |
| `mtlximage.file = "op:..."` eval | MaterialX builder | Resolves correctly at cook time; `file_parm.eval()` returns op: string | H21 ✓ |
| `hou.CopNode.layer(output_index=N)` | hou.CopNode | Multi-output indexing — not tested in this probe | ? |
| OpenCL COP on Apple Silicon | COP OpenCL node | Apple deprecated OpenCL; CPU-only fallback possible | ? |
| `hgpuinfo -c -l` output format | CLI | Parseable; structured per-platform output with device details | H21 ✓ |
| Copernicus kernel DSL vs raw OpenCL | `kernelcode` parm | H21 uses `@KERNEL{...}` DSL; raw OpenCL C may work with `kerneloptions` | H21 ✓ (DSL) |

## OFX Safety Assessment

| Aspect | Finding |
|--------|---------|
| Enumeration safe? | YES — `probe_ofx.py` reads only plist/xml text files; no `dlopen`/`LoadLibrary` |
| Loading requires native code? | YES (always — `.ofx.bundle` = shared library) |
| Product decision | OFX remains product-declined for v1 |
