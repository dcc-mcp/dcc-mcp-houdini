---
name: houdini-vex
description: >-
  Typed VEX creation and diagnosis workflow — create or update Wrangle nodes,
  validate VEX syntax, cook, and collect geometry diagnostics with failure
  localization.  Never degrades to arbitrary script execution; all VEX code
  is set via typed node parameters only.
license: MIT
compatibility: "dcc-mcp-houdini 0.1+, Houdini 20.5+, dcc-mcp-core 0.20.14+"
allowed-tools: Bash Read Write Edit
metadata:
  dcc-mcp:
    dcc: houdini
    layer: domain
    stage: authoring
    version: "1.0.0"
    tags: [houdini, vex, wrangle, attribute, geometry, cook, diagnostics]
    search-hint: >-
      create wrangle, update vex snippet, validate vex syntax, cook wrangle,
      diagnose vex failure, get vex info, list wrangles
    tools: tools.yaml
---

# houdini-vex

Typed VEX authoring and diagnosis for agents.  All tools are `affinity: main`
because they call `hou`.  Prefer these over `houdini-scripting.execute_python`
for VEX creation.

**Hard constraint:** VEX snippets are set via `hou.Parm.set()` on the "snippet"
parameter of Wrangle nodes.  This skill NEVER constructs or evaluates Python
code from VEX strings.  Every VEX snippet is validated client-side (allowlist
and deny-list) before it touches Houdini.

## Tool groups

- **`vex-create`:** create a Wrangle node with optional initial VEX snippet
  (`create_wrangle`).
- **`vex-edit`:** update the VEX snippet on an existing Wrangle
  (`update_vex_snippet`).
- **`vex-validate`:** pre-cook validation of VEX syntax, bindings, and
  parameters (`validate_vex_syntax`).
- **`vex-cook`:** cook a Wrangle and collect diagnostics (`cook_wrangle`,
  `diagnose_wrangle`).
- **`vex-query`** (read-only): inspect an existing Wrangle or list all
  wrangles under a path (`get_vex_info`, `list_wrangles`).

## Tracer-bullet flow

1. `validate_vex_snippet` — check VEX syntax and bindings before committing
2. `create_wrangle(parent_path="/obj/geo1", wrangle_type="pointwrangle", ...)` —
   create a typed Wrangle with the validated snippet
3. `cook_wrangle` — cook the node and get initial diagnostics
4. `get_vex_info` — read back the wrangle metadata (snippet, run-over, cook state)
5. If errors: `diagnose_wrangle` — localize the failure to a specific line or
   attribute binding

For iterative work, use `update_vex_snippet` → `cook_wrangle` → `diagnose_wrangle`
in a loop until the VEX produces the expected geometry.

## Security model

- **Client-side VEX allowlist:** only known VEX builtins, attributes, and
  control flow are permitted.
- **Deny list blocks:** `python`, `exec`, `eval`, `import`, `subprocess`,
  `os.*`, `sys.*`, `hou.*`, and unicode escape sequences.
- **Size limits:** 64KB / 2000 lines per snippet.
- **No Python execution:** VEX code flows through `hou.Parm.set()` — never
  through `exec()` or `eval()` or any HOM Python execution path.
