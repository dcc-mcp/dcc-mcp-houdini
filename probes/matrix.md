# PIP-2930 Compatibility Matrix

> Fill each cell: `pass` / `fail` / `blocked` + one-line evidence.
> Run the probe scripts (see `probes/README.md`) and paste results.

## Primary: Houdini 21.x

| Test | H21 / Windows | H21 / Linux | H21 / macOS |
|------|:------------:|:-----------:|:-----------:|
| **hython import** (hou available) | ? | ? | ? |
| **GUI session** (isUIAvailable) | ? | ? | ? |
| **Copernicus available** (copnet create) | ? | ? | ? |
| **COP network create** (gradient + null) | ? | ? | ? |
| **COP cook** (null.layer()) | ? | ? | ? |
| **OpenCL COP create** (node type exists) | ? | ? | ? |
| **OpenCL kernel source set** (parm.set(cl_code)) | ? | ? | ? |
| **OpenCL COP cook** (ocl_node.layer()) | ? | ? | ? |
| **MaterialX builder** (voptoolutils) | ? | ? | ? |
| **mtlximage op: path set** (file = "op:...") | ? | ? | ? |
| **op: path resolve** (eval at cook time) | ? | ? | ? |
| **OpenCL devices detected** (hgpuinfo -c -l) | ? | ? | ? |
| **hou.opencl module** (exists + methods) | ? | ? | ? |

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

## Uncertain APIs (for implementers)

| API | File | Risk | Verified? |
|-----|------|------|:---------:|
| `hou.CopNode.verb()` → `hou.CopVerb` | hou.CopNode | Headless COP execution; H20.5 vs H21 availability | ? |
| `hou.opencl` module | hou module | Not in public HOM reference; methods unknown | ? |
| OpenCL COP node type name | Node registry | May be `opencl` or `opencl::2.0`; version-dependent | ? |
| `mtlximage.file = "op:..."` eval | MaterialX builder | May only resolve at render time, not interactive cook | ? |
| `hou.CopNode.layer(output_index=N)` | hou.CopNode | Multi-output indexing matches UI ordering | ? |
| OpenCL COP on Apple Silicon | COP OpenCL node | Apple deprecated OpenCL; CPU-only fallback possible | ? |
| `hgpuinfo -c -l` output format | CLI | Parseability of device listing for structured readiness report | ? |

## OFX Safety Assessment

| Aspect | Finding |
|--------|---------|
| Enumeration safe? | ? |
| Loading requires native code? | YES (always — .ofx.bundle = shared library) |
| Product decision | OFX remains product-declined for v1 |
