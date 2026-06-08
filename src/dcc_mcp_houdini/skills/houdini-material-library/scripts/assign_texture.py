"""Assign a texture file to a material/shader parameter."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from _library_common import get_node, hou_import_error, node_summary  # noqa: E402

# Map of common parameter names → texture node types to create.
_TEXTURE_NODE_TYPE_MAP = {
    "principledshader": "principledtexture",
    "principledshader::2.0": "principledtexture",
}


def _detect_colorspace(texture_path: str) -> Optional[str]:
    """Best-effort color space detection from file extension."""
    ext = Path(texture_path).suffix.lower()
    mapping = {
        ".exr": "linear",
        ".hdr": "linear",
        ".jpg": "sRGB",
        ".jpeg": "sRGB",
        ".png": "sRGB",
        ".tif": "linear",
        ".tiff": "linear",
        ".tga": "sRGB",
        ".bmp": "sRGB",
        ".tx": "auto",
        ".rat": "auto",
    }
    return mapping.get(ext)


def assign_texture(
    material_path: str,
    parameter_name: str,
    texture_path: str,
    colorspace: Optional[str] = None,
) -> dict:
    """Assign a texture file to a material/shader parameter.

    Creates or updates a file-texture VOP node and wires it to the target
    material parameter.  If the parameter is a string file-path parm (e.g.
    on an ``arnold::image`` node), the path is set directly.

    Args:
        material_path: Path to the material/shader node.
        parameter_name: Name of the color/texture parameter to drive.
        texture_path: File path to the texture image on disk.
        colorspace: OCIO color space for the texture.  Auto-detected when omitted.

    Returns:
        ToolResult dict.
    """
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return hou_import_error()

    try:
        # Validate the texture file exists.
        tex_path = Path(texture_path)
        if not tex_path.is_file():
            return skill_error(
                "Texture file not found: {}".format(texture_path),
                "Check the path and try again.",
            )

        material_node = get_node(hou, material_path)
        parm = material_node.parm(parameter_name)

        # Case 1: The parameter is a string (file path on an image node).
        if parm is not None:
            parm_template = parm.parmTemplate()
            try:
                parm_type = parm_template.type()
            except Exception:  # noqa: BLE001
                parm_type = None

            if parm_type == hou.parmTemplateType.String:
                parm.set(str(texture_path))
                if colorspace:
                    cs_parm = material_node.parm("colorspace")
                    if cs_parm is not None:
                        cs_parm.set(colorspace)
                return skill_success(
                    "Assigned texture to material parameter",
                    material=node_summary(material_node),
                    parameter=parameter_name,
                    texture_path=str(texture_path),
                    colorspace=colorspace or _detect_colorspace(texture_path),
                )

        # Case 2: Create a file-texture node and wire it.
        parent = material_node.parent()
        mat_type = material_node.type().name() if hasattr(material_node.type(), "name") else ""

        # Try known texture node types.
        tex_node_type = _TEXTURE_NODE_TYPE_MAP.get(mat_type, "principledtexture")
        tex_node = None

        for candidate in [tex_node_type, "mtlximage", "arnold::image", "file"]:
            try:
                tex_node = parent.createNode(candidate)
                break
            except Exception:  # noqa: BLE001
                continue

        if tex_node is None:
            return skill_error(
                "Could not create texture node under {}".format(parent.path()),
                "No supported texture node type found.",
            )

        # Set the file path on the texture node.
        file_parm_set = False
        for file_parm_name in ("filename", "file", "texturefile", "tex0"):
            fp = tex_node.parm(file_parm_name)
            if fp is not None:
                fp.set(str(texture_path))
                file_parm_set = True
                break

        if not file_parm_set:
            return skill_error(
                "Texture node has no file path parameter",
                "Node type: {}".format(tex_node.type().name()),
            )

        # Set color space if available.
        actual_colorspace = colorspace or _detect_colorspace(texture_path)
        if actual_colorspace:
            cs_parm = tex_node.parm("colorspace")
            if cs_parm is not None:
                cs_parm.set(actual_colorspace)

        # Wire the texture output to the material input.
        try:
            # Find input index for the parameter.
            input_idx = None
            for i, name in enumerate(material_node.inputNames()):
                if parameter_name.lower() in name.lower():
                    input_idx = i
                    break
            if input_idx is None:
                # Default: use input index 0 or try to set by name.
                try:
                    material_node.setNamedInput(parameter_name, tex_node, 0)
                except Exception:  # noqa: BLE001
                    material_node.setInput(0, tex_node, 0)
            else:
                material_node.setInput(input_idx, tex_node, 0)
        except Exception:  # noqa: BLE001
            pass

        return skill_success(
            "Assigned texture to material",
            material=node_summary(material_node),
            parameter=parameter_name,
            texture_node=node_summary(tex_node),
            texture_path=str(texture_path),
            colorspace=actual_colorspace,
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to assign texture")


@skill_entry
def main(**kwargs) -> dict:
    return assign_texture(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
