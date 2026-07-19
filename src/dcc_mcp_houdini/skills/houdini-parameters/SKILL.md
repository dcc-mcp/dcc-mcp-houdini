---
name: houdini-parameters
description: >-
  Authoring skill — inspect and edit Houdini node parameters, parameter
  templates, spare parameters, and channel expressions through typed atomic
  tools. Use instead of arbitrary Python for reading/setting parms, adding spare
  parms, and managing expressions. For node connections use houdini-node-graph.
license: MIT
compatibility: "dcc-mcp-houdini 0.1+, Houdini 20.5+, dcc-mcp-core 0.19.45+"
allowed-tools: Bash Read Write Edit
metadata:
  dcc-mcp:
    dcc: houdini
    layer: domain
    stage: authoring
    version: "1.0.1"
    tags: [houdini, parameters, parms, spare, expression, channel, authoring]
    search-hint: "list parameters, get parm, set parm, parm template, spare parameter, channel expression, reference"
    tools: tools.yaml
---

# houdini-parameters

Typed parameter tools for agents. All tools are `affinity: main` because they
call `hou`. Prefer these over `houdini-scripting.execute_python` for parameter
and expression work.

## Tool groups

- **`parm-query`** (read-only): `list_parms`, `get_parms`, `get_parm_templates`,
  `get_expression`.
- **`parm-edit`** (mutating): `set_parms` (type-aware coercion + per-parm
  validation while preserving animated channels), `add_spare_parm`,
  `remove_spare_parm`.
- **`parm-expression`** (mutating): `set_expression`, `clear_expression`.

## Suggested flow

1. `list_parms` / `get_parm_templates` to discover names and types
2. `set_parms` for static, type-coerced edits (errors reported per parameter;
   keyframed or expression-driven parms are preserved)
3. `set_expression` / `clear_expression` to drive or freeze a value
