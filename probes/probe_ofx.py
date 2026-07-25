"""PIP-2930 Stage-1: Optional OFX plugin enumeration safety probe.

**IMPORTANT SAFETY NOTE:**
OFX plugins (.ofx.bundle) are native shared libraries (DLL/dylib/so).
Loading one into the Houdini process constitutes executing arbitrary code in
the agent's trust boundary. This probe ONLY enumerates *metadata* (file names,
paths, OFX-standard directories) WITHOUT calling dlopen/LoadLibrary on any
plugin binary.

If no safe enumeration method exists, this probe documents that fact and
recommends OFX remain product-declined.

Run from hython or Houdini Python shell:
    hython probes/probe_ofx.py
"""

from __future__ import annotations

import json
import os
import struct
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


# OFX plugin bundle structure (macOS):
#   MyPlugin.ofx.bundle/
#     Contents/
#       Info.plist  — XML plist with OFX plugin metadata
#       MacOS/      — the actual dylib
#       Resources/  — icons, etc.
#
# OFX plugin structure (Windows/Linux):
#   MyPlugin.ofx.bundle/
#     Contents/
#       Info.plist or Plugin.xml  — metadata
#       Win64/ or Linux-x86_64/   — the actual .dll/.so
#
# Standard OFX plugin search paths:
#   - Houdini: $HFS/pic/OFX (shipped plugins)
#   - User: $HOUDINI_PATH/OFX or $HOUDINI_USER_PREF_DIR/OFX
#   - System macOS: /Library/OFX/Plugins
#   - Common: $OFX_PLUGIN_PATH environment variable

OFX_SEARCH_PATHS_WINDOWS = [
    "%HFS%/pic/OFX",
    "%HOUDINI_USER_PREF_DIR%/OFX",
    "C:/Program Files/Common Files/OFX/Plugins",
]

OFX_SEARCH_PATHS_MACOS = [
    "$HFS/pic/OFX",
    "$HOUDINI_USER_PREF_DIR/OFX",
    "/Library/OFX/Plugins",
    os.path.expanduser("~/Library/OFX/Plugins"),
]

OFX_SEARCH_PATHS_LINUX = [
    "$HFS/pic/OFX",
    "$HOUDINI_USER_PREF_DIR/OFX",
    "/usr/OFX/Plugins",
    os.path.expanduser("~/.OFX/Plugins"),
]


def _resolve_path(raw: str) -> Optional[str]:
    """Resolve a path with environment variable expansion."""
    # Expand HFS and common vars
    expanded = raw
    for var in ("HFS", "HOUDINI_USER_PREF_DIR", "OFX_PLUGIN_PATH", "HOME"):
        placeholder = f"${var}" if sys.platform != "win32" else f"%{var}%"
        if placeholder in expanded:
            val = os.environ.get(var, "")
            expanded = expanded.replace(placeholder, val)
    expanded = os.path.expandvars(expanded)
    return expanded if os.path.isdir(expanded) else None


def _is_ofx_bundle(path: Path) -> bool:
    """Check if a path looks like an OFX bundle without loading any code.

    An OFX bundle is a directory ending in .ofx.bundle containing either:
      - Contents/Info.plist (macOS bundle style)
      - A top-level XML metadata file
    """
    if not path.is_dir():
        return False
    if not path.name.endswith(".ofx.bundle"):
        return False

    # Check for metadata files — these are text/XML, safe to enumerate
    contents = path / "Contents"
    meta_candidates = [
        path / "Plugin.xml",
        path / "OFXPlugin.xml",
        contents / "Info.plist",
        contents / "Plugin.xml",
    ]
    for candidate in meta_candidates:
        if candidate.exists():
            return True
    return False


def _read_ofx_metadata_safe(bundle_path: Path) -> Dict[str, Any]:
    """Read OFX metadata from Info.plist or Plugin.xml WITHOUT loading dylib.

    This reads TEXT/XML files only. It does NOT import, dlopen, or execute
    any binary code.
    """
    meta: Dict[str, Any] = {"bundle_path": str(bundle_path), "files_found": []}

    # macOS-style Info.plist
    info_plist = bundle_path / "Contents" / "Info.plist"
    if info_plist.is_file():
        meta["files_found"].append("Contents/Info.plist")
        try:
            # Try plistlib for XML plists
            import plistlib  # noqa: PLC0415

            with open(info_plist, "rb") as f:
                plist = plistlib.load(f)
            meta["info_plist"] = {
                "OFXPlugin": plist.get("OFXPlugin", {}).get("Identifier", "unknown")
                if isinstance(plist.get("OFXPlugin"), dict)
                else "unknown",
                "CFBundleIdentifier": plist.get("CFBundleIdentifier", "unknown"),
                "CFBundleName": plist.get("CFBundleName", "unknown"),
                "CFBundleExecutable": plist.get("CFBundleExecutable", "unknown"),
            }
        except Exception as exc:
            meta["info_plist_error"] = str(exc)

    # Plugin.xml (some OFX hosts)
    plugin_xml = bundle_path / "Plugin.xml"
    if not plugin_xml.exists():
        plugin_xml = bundle_path / "Contents" / "Plugin.xml"
    if plugin_xml.is_file():
        meta["files_found"].append(str(plugin_xml.relative_to(bundle_path)))
        try:
            # Safe: read as text, don't parse untrusted XML with entity expansion
            with open(plugin_xml, "r", encoding="utf-8", errors="replace") as f:
                xml_content = f.read(4096)  # first 4KB
            # Extract identifiers via simple string search (not full XML parse)
            import re

            identifiers = re.findall(r'<PluginIdentifier>([^<]+)</PluginIdentifier>', xml_content)
            if identifiers:
                meta["plugin_identifier"] = identifiers[0]
            names = re.findall(r'<PluginName>([^<]+)</PluginName>', xml_content)
            if names:
                meta["plugin_name"] = names[0]
        except Exception as exc:
            meta["xml_read_error"] = str(exc)

    # Catalog non-binary files for transparency
    for root, dirs, files in os.walk(bundle_path):
        # Skip binary-heavy directories from walk listing
        if any(skip in root.lower() for skip in ("macos", "win64", "linux", "resources")):
            for f in files:
                if not any(f.endswith(ext) for ext in (".dylib", ".so", ".dll", ".exe")):
                    meta.setdefault("text_files", []).append(os.path.join(root, f))
            dirs.clear()  # don't recurse deeper
            continue

    return meta


def probe_ofx_enumeration() -> Dict[str, Any]:
    """Enumerate OFX plugin bundles without loading any native code.

    Returns:
        Dict with:
        - safe_enumeration_possible: bool — can we list plugins without loading?
        - bundles_found: List[Dict] — metadata for each bundle
        - recommendation: str — whether OFX can be safely exposed to agents
    """
    result: Dict[str, Any] = {
        "safe_enumeration_possible": True,  # We only read text files
        "can_load_without_execution": False,  # Using an OFX plugin ALWAYS loads native code
        "search_paths_checked": [],
        "bundles_found": [],
        "recommendation": "",
    }

    # Determine search paths
    if sys.platform == "win32":
        search_paths = OFX_SEARCH_PATHS_WINDOWS
    elif sys.platform == "darwin":
        search_paths = OFX_SEARCH_PATHS_MACOS
    else:
        search_paths = OFX_SEARCH_PATHS_LINUX

    # Also check OFX_PLUGIN_PATH
    ofx_env = os.environ.get("OFX_PLUGIN_PATH", "")
    if ofx_env:
        for p in ofx_env.split(os.pathsep):
            if p.strip():
                search_paths.append(p.strip())

    for raw_path in search_paths:
        resolved = _resolve_path(raw_path)
        if resolved is None:
            result["search_paths_checked"].append({"raw": raw_path, "resolved": None, "exists": False})
            continue

        result["search_paths_checked"].append({"raw": raw_path, "resolved": resolved, "exists": True})

        try:
            for entry in sorted(os.listdir(resolved)):
                full = Path(resolved) / entry
                if _is_ofx_bundle(full):
                    meta = _read_ofx_metadata_safe(full)
                    result["bundles_found"].append(meta)
        except PermissionError:
            result["search_paths_checked"][-1]["error"] = "permission denied"
        except Exception as exc:
            result["search_paths_checked"][-1]["error"] = str(exc)

    # Safety assessment
    if result["bundles_found"]:
        result["recommendation"] = (
            "OFX bundles detected. Enumeration by reading metadata text files (Info.plist/Plugin.xml) "
            "IS safe — it does not load native code. However, USING any OFX plugin (calling its "
            "functions) always involves dlopen/LoadLibrary of the .ofx.bundle binary, which means "
            "executing third-party native code in the agent process. "
            "RECOMMENDATION: enumeration can be exposed as a read-only discovery tool; "
            "loading/executing OFX plugins should remain gated behind explicit user opt-in."
        )
    else:
        result["recommendation"] = (
            "No OFX bundles detected on this system. Enumeration by directory walking "
            "and metadata file reading is safe. OFX remains product-declined per PIP-2925 scope."
        )

    return result


def probe_houdini_ofx_host_support() -> Dict[str, Any]:
    """Check Houdini's own OFX host support configuration.

    Houdini ships with a built-in OFX host (COP2 OFX wrapper nodes).
    This probes the node type registry for available OFX-related nodes
    WITHOUT instantiating any plugin.
    """
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return {"available": False, "error": "hou not importable"}

    result: Dict[str, Any] = {"available": True, "ofx_node_types": []}

    # Check COP2 context for OFX wrapper node types
    cop2_cat = hou.nodeTypeCategories().get("Cop2")
    if cop2_cat is not None:
        for nt_name in sorted(cop2_cat.nodeTypes().keys()):
            nt = cop2_cat.nodeTypes()[nt_name]
            if "ofx" in nt_name.lower():
                result["ofx_node_types"].append({
                    "name": nt_name,
                    "description": nt.description(),
                    "category": "Cop2",
                })

    # Check if hou.OFXManager or similar exists
    for attr_name in dir(hou):
        if "ofx" in attr_name.lower():
            result.setdefault("hou_ofx_attributes", []).append(attr_name)

    return result


def main() -> int:
    print("PIP-2930 OFX Plugin Safety Probe")
    print("=" * 60)

    # 1. Check Houdini OFX host support
    print("\n--- Houdini OFX Host Support ---")
    host_support = probe_houdini_ofx_host_support()
    if host_support.get("ofx_node_types"):
        for nt in host_support["ofx_node_types"]:
            print(f"  COP2 node type: {nt['name']} — {nt['description']}")
    else:
        print("  No OFX-related node types found in COP2 registry")

    if host_support.get("hou_ofx_attributes"):
        print(f"  hou module OFX attributes: {host_support['hou_ofx_attributes']}")

    # 2. Enumerate OFX bundles safely
    print("\n--- OFX Bundle Enumeration ---")
    enum_result = probe_ofx_enumeration()

    print(f"  Search paths checked: {len(enum_result['search_paths_checked'])}")
    for sp in enum_result["search_paths_checked"]:
        status = "EXISTS" if sp.get("exists") else "MISSING"
        error = f" ({sp['error']})" if sp.get("error") else ""
        print(f"    {sp['raw']} -> {sp['resolved'] or 'N/A'} [{status}]{error}")

    print(f"\n  Bundles found: {len(enum_result['bundles_found'])}")
    for bundle in enum_result["bundles_found"]:
        ident = bundle.get("info_plist", {}).get("CFBundleName", bundle.get("plugin_name", "unknown"))
        print(f"    {Path(bundle['bundle_path']).name} — {ident}")

    print(f"\n  Safe enumeration: {enum_result['safe_enumeration_possible']}")
    print(f"  Loading requires native code execution: {not enum_result['can_load_without_execution']}")

    # 3. Safety recommendation
    print(f"\n--- Recommendation ---")
    print(enum_result["recommendation"])

    # Write output
    output = {
        "probe": "PIP-2930-ofx-safety",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "platform": sys.platform,
        "host_support": host_support,
        "enumeration": enum_result,
        "verdict": "OFX_ENUM_SAFE_LOAD_UNSAFE",
        "product_decision": "OFX remains product-declined for v1 per PIP-2925",
    }

    out_path = f"pip2930_ofx_{datetime.now().strftime('%Y%m%dT%H%M%S')}.json"
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\nResults: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
