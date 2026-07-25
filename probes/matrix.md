# PIP-2930 Compatibility Matrix

> Status: H21 Windows GUI — 11/13 primary cells PASS, 2 FAIL (OpenCL COP cook, hou.opencl). Filled 2026-07-25 via gateway `houdini@21.0.631-fc80640a`.

## Primary: Houdini 21.x

| Test | H21 / Windows | H21 / Linux | H21 / macOS |
|------|:------------:|:-----------:|:-----------:|
| **hython import** (hou available) | **pass** | ? | ? |
| **GUI session** (isUIAvailable) | **pass** | ? | ? |
| **Copernicus available** (CopNet category) | **pass** | ? | ? |
| **COP network create** (constant + null) | **pass** | ? | ? |
| **COP cook** (null.layer()) | **pass** | ? | ? |
| **OpenCL COP create** (node type exists) | **pass** | ? | ? |
| **OpenCL kernel source set** (kernelcode parm) | **pass** | ? | ? |
| **OpenCL COP cook** (ocl_node.layer()) | **fail** | ? | ? |
| **MaterialX builder** (mtlximage create) | **pass** | ? | ? |
| **mtlximage op: path set** (file = "op:...") | **pass** | ? | ? |
| **op: path resolve** (eval at cook time) | **pass** | ? | ? |
| **OpenCL devices detected** (hgpuinfo -c -l) | **pass** | ? | ? |
| **hou.opencl module** (exists + methods) | **fail** | ? | ? |

### H21 / Windows evidence

- **Host**: Houdini 21.0.631, Windows 11, UI available, Python 3.11.7, HFS at `G:/_thm/rez_local_cache/ext/houdini/21.0.631-thm.1/`
- **Copernicus**: `Cop2` category: 156 node types. `CopNet` category: `copnet`, `copnet_filterlist`. Node type `copnet` creates Copernicus network; `cop2net` is legacy COP2-Old.
- **COP network**: `copnet` inside `/img`; children: `constant` (source), `null` (output), `opencl`. `hou.CopNode` exposes `layer()`, `geometry()`, `vdb()`, `verb()`.
- **COP cook**: `null.layer()` succeeded; `has_layer=True`, resolution returned via `layer.resolution()`.
- **H21 quirk**: `gradient` node type FAILS with "Invalid node type name" inside `copnet` despite being listed in the `Cop2` category. `constant`, `null`, `opencl` all work.
- **OpenCL COP**: Node type `opencl` (Cop category). 38 parameters. Kernel source parameter is `kernelcode` (not `kernel`, `kernel_code`, or `code`). Kernel function name via `kernelname` parm. Raw OpenCL C kernel accepted and compiled, but cook fails with errors:
  - `"No output matching runover mode provided"` — output binding mismatch
  - `"input1: no layer binds to 'src'"` — input layer not bound
  - `"output1: No binding named 'dst'"` — output binding not resolved
  - Bindings are correctly named (`input1_name=src`, `output1_name=dst`) but runtime resolution fails.
  - Likely cause: CPU-only OpenCL platform (Intel OpenCL 1.2 for AMD Ryzen CPU) may not support image2d read/write kernels in Houdini's COP context.
- **MaterialX op: path**: `mtlximage.file` parm set to `op:/img/_pip2930_probe_copnet/_probe_output`. Value accepted and resolves correctly on `eval()`. Material subnet created at `/mat/_pip2930_probe_mtlx`.
- **OpenCL devices**: `hgpuinfo -c -l` returns: Intel(R) OpenCL 1.2 on AMD Ryzen 9 9950X 16-Core (CPU only, 32 compute units, 95GB). No GPU OpenCL runtime detected on this machine.
- **hou.opencl**: NOT available — `hasattr(hou, "opencl")` returns False. Fallback to `hgpuinfo` CLI required.

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

## H21 API Corrections (vs initial probe_cop.py assumptions)

Discovered during live H21 gateway execution:

| Original assumption | H21 actual | Impact |
|---|---|---|
| `gradient` node inside copnet | `gradient` creation FAILS in copnet (Invalid node type name) — use `constant` or `ramp` | `probe_cop.py` section 1: change `gradient` → `constant` |
| `kernel` / `kernel_code` param for OpenCL COP | Actual param name is `kernelcode` | `probe_cop.py` section 2: add `kernelcode` as primary candidate |
| Raw OpenCL C kernel directly cookable | Raw C compiles but cook fails on CPU-only OpenCL; may need Houdini kernel DSL or GPU runtime | OpenCL COP cook: `fail` on CPU-only platform |
| `hou.opencl` module available | **Not available** in H21.0.631 | OpenCL device enum must use `hgpuinfo` + `hconfig` |
| Copernicus check via `Cop2` category | `CopNet` category also relevant; `copnet` node type in both | `_check_copernicus_available()`: check `CopNet` not just `Cop2` |

## Uncertain APIs (for implementers)

| API | File | Risk | Verified? |
|-----|------|------|:---------:|
| `hou.CopNode.verb()` → `hou.CopVerb` | hou.CopNode | Headless COP execution; H21 confirmed `verb()` exists | H21 ✓ |
| `hou.opencl` module | hou module | **Not available** in H21; use `hgpuinfo` + `hconfig` | H21 ✓ (absent) |
| OpenCL COP node type name | Node registry | Confirmed: `opencl` (Cop category) — stable in H21 | H21 ✓ |
| `mtlximage.file = "op:..."` eval | MaterialX builder | Resolves correctly; `file_parm.eval()` returns op: string | H21 ✓ |
| `hou.CopNode.layer(output_index=N)` | hou.CopNode | Multi-output indexing — not tested in this probe | ? |
| OpenCL COP on Apple Silicon | COP OpenCL node | Apple deprecated OpenCL; CPU-only fallback possible | ? |
| `hgpuinfo -c -l` output format | CLI | Parseable; structured per-platform output with device details | H21 ✓ |
| `gradient` node in copnet | Cop2 category | FAILS with "Invalid node type name" in H21 copnet | H21 ✓ (fail) |
| OpenCL COP kernel DSL requirement | `kernelcode` parm | Raw OpenCL C compiles but may need Houdini `@KERNEL{...}` DSL for cook | H21 ✓ (partial) |

## OFX Safety Assessment

| Aspect | Finding |
|--------|---------|
| Enumeration safe? | YES — `probe_ofx.py` reads only plist/xml text files; no `dlopen`/`LoadLibrary` |
| Loading requires native code? | YES (always — `.ofx.bundle` = shared library) |
| Product decision | OFX remains product-declined for v1 |
