# AGENTS.md — dcc-mcp-houdini

> Navigation map for AI agents. Detailed API → `llms.txt`.
> This file is a **map**, not an encyclopedia — follow the links for depth.

## Build & test

```bash
vx just dev                  # pip install -e ".[dev]"
vx just test                 # pytest tests/ -v --tb=short
vx just test-cov             # pytest with coverage on src/dcc_mcp_houdini
vx just lint-all             # ruff check + ruff format --check + skill lint + py37 syntax
vx just ci                   # test + lint-all (local CI simulation)
vx just prek                 # run every pre-commit/prek hook against all files
```

Windows host debug (recipe names verified in `justfile`):

```bash
vx just houdini-version=20.5 houdini-dev-build-link-core-win  # build core + symlink
vx just houdini-version=20.5 houdini-dev-debug-win            # launch Houdini
vx just build-houdini-package platform=win64                  # release assets
```

Other useful recipes: `houdini-link` / `houdini-link-win` (symlink
`src/dcc_mcp_houdini` into Houdini's Python site-packages), `houdini-status`,
`serve`, `fix`, `format`, `build`, `clean`.

## Agent control path

AI agent runtimes default to the shared gateway through the `dcc-mcp` skill and
`dcc-mcp-cli` REST commands:

```bash
dcc-mcp-cli search --query "<task>" --dcc-type houdini
dcc-mcp-cli describe <tool-slug>
dcc-mcp-cli call <tool-slug> --json '{"key":"value"}'
```

Use `dcc-mcp-cli list` for live instances and `dcc-mcp-cli dcc-types` for
release-catalog support. IDE users may continue to configure the gateway MCP
endpoint; adapter-local Python start APIs are for host bootstrap and tests.

### CLI availability and updates

If `dcc-mcp-cli` is missing, obtain user consent before using the official
install commands in the README Agent workflow. Keep an official build current
with:

```bash
dcc-mcp-cli update check
dcc-mcp-cli update apply
```

`update apply` stages the latest CLI for the next launch; it does not replace a
running server.

## Quick start (inside Houdini)

```python
import dcc_mcp_houdini
server = dcc_mcp_houdini.start_server()
print(server.mcp_url)  # OS-assigned instance endpoint
```

## Skills-first workflow

```
1. search_skills(query="scene") -> find a typed Houdini skill
2. load_skill("houdini-nodes") / load_skill("houdini-hda") when authoring tools are needed
3. call houdini_scene__inspect_selection / houdini_nodes__create_node / houdini_hda__execute_hda
4. use houdini_scripting__execute_python only when no typed skill fits
```

**Default minimal mode** (`DCC_MCP_MINIMAL=1`): only `houdini-scripting` +
`houdini-scene` loaded at startup.

## Repo layout

| Path | Role |
|------|------|
| `src/dcc_mcp_houdini/server.py` | `HoudiniMcpServer`, `start_server` |
| `src/dcc_mcp_houdini/host.py` | Main-thread pump via event loop |
| `src/dcc_mcp_houdini/dispatcher/` | Execution stack factory |
| `src/dcc_mcp_houdini/skills/` | Bundled skill packages |
| `src/dcc_mcp_houdini/skills/SKILLS_INDEX.md` | Authoritative skill + tool index |
| `packaging/assemble_houdini_package.py` | Quickinstall ZIP builder |
| `tools/` | Link/unlink scripts, skill linter, py37 syntax check, CLI installer |
| `probes/` | Host capability probes (`probe_cop.py`, `probe_opencl_devices.py`) |
| `docs/` | ADRs, CI notes, guides, showcase assets |
| `examples/mcp/` | Ready-made MCP client configs (Cursor, etc.) |

## Main-thread execution

Houdini `hou.*` APIs require the UI thread. The adapter wires:

- `HostUiDispatcherBase` + `HostPumpController` + `HoudiniUiPump` → one
  throttled `hou.ui.addEventLoopCallback` with an 8 ms queue budget
- Headless `hython` → inline / standalone dispatcher

## Skill authoring

When adding or changing bundled skills, load the project skill:

- **Cursor:** `.cursor/skills/dcc-mcp-skill-developer/SKILL.md`
- **Checklist:** `references/SKILL_AUTHORING_CHECKLIST.md` in that skill
- **Index:** `src/dcc_mcp_houdini/skills/SKILLS_INDEX.md`

## Reference material (follow, do not inline)

- **Bundled skills + tools (43 packages):** `src/dcc_mcp_houdini/skills/SKILLS_INDEX.md`
- **Environment variables:** [docs/guide/environment.md](docs/guide/environment.md)
- **Local MCP debug:** [docs/guide/local-mcp-debug.md](docs/guide/local-mcp-debug.md)
- **Docker E2E notes:** [docs/ci/houdini-docker.md](docs/ci/houdini-docker.md)
- **Capability coverage:** [docs/guide/domain-capability-coverage.md](docs/guide/domain-capability-coverage.md)
- **ADRs:** `docs/adr/`

## Vendor integration notes

- [docs/integrations/claude.md](docs/integrations/claude.md) — Claude Desktop
  config, minimal-mode progressive loading, viewport + HDA tips.
- [docs/integrations/gemini.md](docs/integrations/gemini.md) — Gemini / Vertex
  setup, code-first SOP chains, lookdev and pipeline workflows.

## Release

- release-please drives versioning from Conventional Commits on `main`.
- Whether a release is cut at all is a changelog question, not a prefix question: if every
  commit in the batch lands in a `hidden: true` section the changelog entry is empty, and
  release-please skips the whole batch — no release pull request, **no version bump**
  (`strategies/base.ts` logs “No user facing commits found since … - skipping” when
  `changelogEmpty()` finds only the heading line).
- For `release-type: python`: `chore:`/`ci:`/`style`/`refactor:`/`test:`/`build:` are
  `hidden: true`; `docs:` is a **visible** `Documentation` section.
- Only once a release *is* cut does the prefix choose the bump: breaking → major,
  `feat:` → minor, anything else → patch
  (`DefaultVersioningStrategy.determineReleaseType()`).
- Use `chore:` when the batch should **not** cut a release; use `docs:` when doc-only work
  should cut a patch release.
- Use `chore:` for config and doc work: a `chore:`-only batch produces an empty changelog
  entry, so release-please skips it and the version stays put.

## Do / Don't

- **Do** single-source agent instructions here. This is the only agent contract
  file at the repo root.
- **Do** keep this file a navigation map — long reference material belongs in
  `docs/` or `llms.txt`.
- **Don't** add `CLAUDE.md` / `GEMINI.md` / `CURSOR.md` / `ANTHROPIC.md` /
  `OPENAI.md` / `COPILOT.md` / `CODEBUDDY.md` / `.cursorrules` / `.clinerules` /
  `.windsurfrules` at the root. Vendor-specific notes live under
  `docs/integrations/`, linked from here.
- **Don't** hardcode an exact version in tests (`assert __version__ == "X.Y.Z"`)
  — release-please bumps will break it. Use `>=` or read package metadata.
- **Don't** commit build artifacts to the repo root (`*.o`, `coverage.json`,
  `audit-result.json`, `clippy_check.txt`, `commit_msg.txt`).
