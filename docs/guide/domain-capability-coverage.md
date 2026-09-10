# Domain coverage and acceptance

This iteration adds 3 on-demand skill packages and 15 tools over main:
4 Copernicus, 4 DOP simulation, 5 PDG/TOP, and 2 geometry data queries.
The catalog contains 38 packages and 260 tools after the primitive-topology follow-up. Minimal startup is unchanged.

| Domain | Implemented | Evidence and remaining work |
| --- | --- | --- |
| Geometry data | Paged attribute values, named intrinsics, and ordered primitive vertex-to-point references | Pagination/truncation tests and a licensed Houdini 22.0.368 topology smoke pass. Full manifoldness analysis remains future work. |
| Copernicus | Modern copnet creation, typed filter graph construction, connections and cached diagnostics | Real constant-to-blur graph created and inspected. Image cooking/export remains a separate verification step. Legacy COP2 is rejected. |
| Pyro / FLIP / RBD / Vellum | DOP containers and typed solver skeletons, parameter readback/rollback, structural diagnostics | All four solver types created in Houdini 22.0.368. Sources, object data, output wiring, and simulated results are still required; these are not runnable effect templates. |
| PDG / TOP | Containers, tasks, checked dependencies, item states, blocking/nonblocking cook outcomes | Real two-item Wedge task completed; failed/canceled/incomplete states covered deterministically. Farm scheduler and distributed job acceptance remain separate. |
| Solaris / USD | Existing composed-stage, prim and attribute inspection | Shared bounded-value serializer reused by geometry tools. General stage authoring still needs expansion. |
| Modeling | Existing loft, bevel, extrusion, array and other typed verbs | Live fixture and parent-equality fix tracked in [PR #289](https://github.com/dcc-mcp/dcc-mcp-houdini/pull/289). |
| VEX, materials, HDA, KineFX, render and pipeline | Existing typed domains retained | This iteration does not claim complete Houdini coverage or revalidate every domain. |

## Reproduce the domain smoke

With this checkout and its declared dependencies installed, run in a fresh
licensed headless process:

```sh
hython .github/scripts/run_houdini_capabilities.py
```

This is a real-HOM skill-entrypoint smoke, not a gateway or visual acceptance
test. It verifies the imported adapter belongs to this checkout, creates only
transient in-memory nodes, and exits nonzero on a failed contract. The final
marker is `HOUDINI_CAPABILITY_PROBE_PASSED`. The MCP transport smoke is
`.github/scripts/run_houdini_e2e.py`.

For the isolated ordered-topology check, run
`hython .github/scripts/run_houdini_topology.py`. It compares paged results with
real HOM vertex order, checks truncation and closure, and destroys its temporary
geometry. The success marker is `HOUDINI_TOPOLOGY_PROBE_PASSED`.

## Issue batch

- [#238](https://github.com/dcc-mcp/dcc-mcp-houdini/issues/238):
  complete stderr scanning is in [PR #287](https://github.com/dcc-mcp/dcc-mcp-houdini/pull/287).
  Real Houdini 22.0.368 acceptance reproduced a zero-exit hair procedural failure
  with a written EXR; the job correctly reports `completed_with_render_errors`.
  PR #287 includes the repeatable licensed fixture.
- [#203](https://github.com/dcc-mcp/dcc-mcp-houdini/issues/203):
  tool pagination is fixed in [PR #288](https://github.com/dcc-mcp/dcc-mcp-houdini/pull/288).
  Licensed local `serve_headless` E2E passed on Houdini 22.0.368 / Core 0.20.14;
  credential-enabled Docker execution remains separate.
- [#266](https://github.com/dcc-mcp/dcc-mcp-houdini/issues/266):
  the live focused fixture in PR #289 used 13 typed authoring calls and no raw
  scripting. It is not the full Apache reference-asset evaluation.
- [#6](https://github.com/dcc-mcp/dcc-mcp-houdini/issues/6):
  the dependency dashboard references Python-update PR #5, which is already
  merged; CI already uses Python 3.14 for lint/build. The bot-managed dashboard
  is not a new adapter defect.

## HOM references

- [TOP cooking](https://www.sidefx.com/docs/houdini/hom/hou/TopNode.html)
  and [work-item properties](https://www.sidefx.com/docs/houdini/tops/pdg/Node.html).
- [Copernicus SOP container](https://www.sidefx.com/docs/houdini/nodes/sop/copnet.html)
  and [ROP Image](https://www.sidefx.com/docs/houdini/nodes/cop/rop_image.html).
- [Geometry access](https://www.sidefx.com/docs/houdini/hom/hou/Geometry.html)
  and [primitive intrinsics](https://www.sidefx.com/docs/houdini/hom/hou/Prim.html).
