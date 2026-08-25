# Install dcc-mcp-houdini

This is the adapter-owned runbook for installing, verifying, upgrading, and
removing DCC-MCP from a versioned SideFX Houdini profile. The machine-readable
entry point is `dcc-mcp-houdini`.

## Requirements

- SideFX Houdini 18.5 or newer with its Python 3 `hython` interpreter.
- Python 3.7 or newer in that Houdini build for the wheel-first lifecycle.
- `dcc-mcp-core >= 0.20.14,<1.0.0` and the same `dcc-mcp-houdini` version
  installed in the selected `hython` environment.
- Write access to the matching user profile. The installer never edits the
  Houdini application directory.

Install the wheel into the exact embedded interpreter, not an unrelated Python:

```text
<hython> -m ensurepip --upgrade
<hython> -m pip install --upgrade dcc-mcp-houdini
```

`--dcc-path` must name the interactive `houdini`, `houdinifx`, or `hindie`
executable that a readiness remediation can actually launch. Use the matching
`hython` executable only with `--python`; Hython is headless and can never
satisfy the interactive readiness contract.

## Supported versions

The lifecycle supports Windows, macOS, and Linux. Houdini 18.5+ is the host
floor; the selected build must provide Python 3.7+. The released quickinstall
bundles Core 0.20.14 native wheels for Python 3.7+ on Windows/Linux and Python
3.8+ on macOS; Core 0.20.14 publishes no native macOS CPython 3.7 wheel, so that
quickinstall combination fails closed before vendor extraction. SideFX changes the bundled
Python minor between Houdini releases, so preflight executes the chosen
interpreter and, when `hou` is available, checks its reported Houdini version
against `--dcc-path`. It does not guess a Python compatibility row from a
different Houdini installation. Preflight also binds the reported Hython
executable and the imported HOM, adapter, and Core module origins to the
selected Houdini installation and installed distributions.

Typical interpreter locations are:

- Windows: `C:\Program Files\Side Effects Software\Houdini X.Y.ZZZ\bin\hython.exe`
- macOS: `/Applications/Houdini/HoudiniX.Y.ZZZ.app/Contents/Resources/bin/hython`
- Linux: `/opt/hfsX.Y.ZZZ/bin/hython`

## Agent quick path

Planning is the default and performs no writes:

```text
dcc-mcp-houdini install --json --dry-run --dcc-path <houdini> --python <hython>
```

Review the JSON plan, then execute it:

```text
dcc-mcp-houdini install --json --yes --dcc-path <houdini> --python <hython>
```

A cold install does not require Houdini to be running. Once package artifacts
and the receipt pass static verification, the command exits successfully and
keeps them installed. If no matching live registry entry exists, the result
reports `verify.directly_usable: false`, marks the verify step `pending`, and
returns exact `start_selected_houdini` and `verify_selected_houdini`
continuations. The separate `verify` command remains fail closed until its
host-bound typed probe succeeds.

All lifecycle verbs accept `--json`, `--yes`, `--dry-run`, `--dcc-path`, and
`--python`. Stable exits are `0` success/plan, `10` preflight, `20` acquire,
`30` install or rollback, `40` verify, and `50` a Core-proven loaded-file lock
requiring a Houdini restart. JSON follows Install SOP schema v1 and every
recovery action is an argv-array `next_steps[].command`.

The Draft 2020-12 contract is loaded from the canonical schema resource
published by `dcc-mcp-core` 0.20.14 or newer. Source and installed-wheel tests
validate the exact public loader and resource; the adapter carries no fallback
copy of the schema.

The installer writes a receipted package JSON and owned startup hooks to the
matching versioned Houdini profile. `123.py` covers an empty session and
`456.py` covers a loaded scene. Both preserve the existing one-pump,
main-thread execution contract and capture bootstrap errors before a server is
available.

## Manual path

The release quickinstall ZIP remains available for offline-style installation.
Its wheels are immutable release assets, and the bootstrap stages vendor
updates before Core performs lock-aware replacement.

Windows:

```powershell
powershell -ExecutionPolicy Bypass -File install.ps1 -HoudiniVersion 20.5
```

macOS or Linux:

```bash
chmod +x install.sh
./install.sh 20.5
```

Set `DCC_MCP_HOUDINI_PACKAGES_DIR` (or Windows `-PackagesDir`) to select an
isolated package directory. Keep the extracted quickinstall directory in place
while its package JSON references it. Quickinstall is a release path; for the
receipt-driven lifecycle, use the wheel-first commands above.

Default package registration directories are:

- Windows: `~/Documents/houdini<version>/packages`
- Linux: `~/houdini<version>/packages`
- macOS: `~/Library/Preferences/houdini/<version>/packages`

The Core 0.20.14 quickinstall compatibility matrix is Python 3.7+ on Windows
and Linux, and Python 3.8+ on macOS. Use a later Core release only when its
native wheel tags satisfy the same declared platform floor.

## Verify

Inspect files without starting Houdini:

```text
dcc-mcp-houdini status --json --dcc-path <houdini> --python <hython>
```

Then start the selected Houdini build and run:

```text
dcc-mcp-houdini verify --json --dcc-path <houdini> --python <hython>
```

Verification checks receipt/file digests, the exact target interpreter import,
captured bootstrap errors, one selected instance/PID/start identity, the live
host executable and module origins, and the typed read-only
`houdini_scripting__get_session_info` main-thread probe. A copied
package or healthy transport alone is not `directly_usable: true`. Headless
`hython` uses `hython -m dcc_mcp_houdini`; it does not prove GUI readiness.

## Upgrade

Upgrade the exact interpreter first, close Houdini when native files are
loaded, review the plan, and execute:

```text
<hython> -m pip install --upgrade dcc-mcp-houdini
dcc-mcp-houdini upgrade --json --dry-run --dcc-path <houdini> --python <hython>
dcc-mcp-houdini upgrade --json --yes --dcc-path <houdini> --python <hython>
```

The adapter stages a complete replacement and preserves the prior package and
receipt until artifact, receipt, import, and bootstrap verification succeed.
It restores the exact prior bytes when those static commit checks fail. Live
readiness is a separate continuation and never discards an otherwise valid
upgrade merely because Houdini is not running.

## Uninstall

Close Houdini, preview receipt-owned removal, then execute it:

```text
dcc-mcp-houdini uninstall --json --dry-run --dcc-path <houdini> --python <hython>
dcc-mcp-houdini uninstall --json --yes --dcc-path <houdini> --python <hython>
<hython> -m pip uninstall dcc-mcp-houdini
```

Uninstall consumes an exact typed ownership manifest for files, directories,
links, and package registration. It refuses to delete modified, linked,
unexpected, or ambiguous unreceipted paths, and restores the complete prior
state if an atomic move or removal fails. A second uninstall is safe. For a legacy quickinstall,
remove `dcc_mcp_houdini.json` from the matching profile before deleting the
extracted directory; the legacy installer predates receipts.

## Troubleshooting

- `host` or `host_version`: pass the exact `houdini` executable or application
  with `--dcc-path`; do not point at another installed version.
- `python`: pass that build's exact `hython` with `--python`, and install the
  wheel into that interpreter.
- `partial`: preserve the reported unreceipted files. Reconcile or remove the
  legacy package registration explicitly before retrying.
- `bootstrap`: inspect the reported `.host-errors.log` under the versioned
  profile `.dcc-mcp/logs` directory; the original exception also remains in
  the Houdini console.
- `readiness`: start Houdini, confirm `DCC_MCP_HOUDINI_AUTOSTART` is not `0`,
  and use `dcc-mcp-cli list` to confirm exactly one live Houdini instance.
- Exit `50`: close every Houdini process using the reported locked artifact and
  repeat the exact command. The installer never terminates Houdini itself.
- Background renders set `DCC_MCP_BACKGROUND_RENDER=1`; their startup hooks
  intentionally do not launch another adapter.

The catalog target for this runbook is:
`https://raw.githubusercontent.com/dcc-mcp/dcc-mcp-houdini/main/install.md`.
