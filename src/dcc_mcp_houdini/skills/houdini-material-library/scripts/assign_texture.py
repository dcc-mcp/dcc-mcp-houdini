"""Assign a texture through a bounded, typed Houdini node contract."""

from __future__ import annotations

import re
from contextlib import nullcontext
from pathlib import Path
from typing import Any, Optional

from _library_common import get_node, hou_import_error, node_summary  # noqa: E402
from dcc_mcp_core.skill import skill_entry, skill_error, skill_success

_PRINCIPLED_SHADER_TYPES = frozenset({"principledshader", "principledshader::2.0"})
_DIRECT_TEXTURE_NODE_TYPES = frozenset({"arnold::image", "mtlximage"})
_WIRED_MATERIAL_NODE_TYPES = {
    "arnold::standard_surface": "arnold::image",
    "mtlxstandard_surface": "mtlximage",
}
_IMAGE_FILE_PARMS = ("filename", "file", "texturefile", "tex0")
_PARAMETER_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
_OWNER_USER_DATA_KEY = "dcc_mcp.assign_texture.owner"


def _detect_colorspace(texture_path: str) -> Optional[str]:
    """Best-effort color space detection from file extension."""
    return {
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
    }.get(Path(texture_path).suffix.lower())


def _undo_group(hou: Any, label: str) -> Any:
    undos = getattr(hou, "undos", None)
    group = getattr(undos, "group", None)
    return group(label) if callable(group) else nullcontext()


def _rollback_parms(snapshots: list[tuple[Any, Any]]) -> bool:
    try:
        for parm, value in reversed(snapshots):
            parm.set(value)
        return all(parm.eval() == value for parm, value in snapshots)
    except Exception:  # noqa: BLE001
        return False


def _assign_principled(
    material_node: Any,
    parameter_name: str,
    texture_path: str,
    colorspace: Optional[str],
    undo_label: str,
) -> dict:
    use_texture_parm = material_node.parm("{}_useTexture".format(parameter_name))
    texture_parm = material_node.parm("{}_texture".format(parameter_name))
    if use_texture_parm is None or texture_parm is None:
        return skill_error(
            "Unsupported Principled Shader texture parameter",
            "UNSUPPORTED_TEXTURE_PARAMETER",
        )

    try:
        snapshots = [(texture_parm, texture_parm.eval()), (use_texture_parm, use_texture_parm.eval())]
        texture_parm.set(texture_path)
        use_texture_parm.set(1)
        texture_readback = texture_parm.eval()
        enabled_readback = use_texture_parm.eval()
        if texture_readback != texture_path or not bool(enabled_readback):
            raise RuntimeError("readback mismatch")
    except Exception:  # noqa: BLE001
        if "snapshots" not in locals() or not _rollback_parms(snapshots):
            return skill_error(
                "Texture assignment failed and rollback could not be verified",
                "TEXTURE_ROLLBACK_FAILED",
            )
        return skill_error("Texture assignment failed", "TEXTURE_ASSIGNMENT_FAILED")

    return skill_success(
        "Assigned texture to Principled Shader parameter",
        material=node_summary(material_node),
        parameter=parameter_name,
        texture_path=texture_path,
        detected_colorspace=_detect_colorspace(texture_path),
        verified=True,
        undo_label=undo_label,
        readback={"texture_enabled": bool(enabled_readback), "texture_path": str(texture_readback)},
    )


def _assign_direct_texture(
    hou: Any,
    texture_node: Any,
    parameter_name: str,
    texture_path: str,
    colorspace: Optional[str],
    undo_label: str,
) -> dict:
    parm = texture_node.parm(parameter_name)
    try:
        parm_type = parm.parmTemplate().type() if parm is not None else None
    except Exception:  # noqa: BLE001
        parm_type = None
    if parm_type != hou.parmTemplateType.String:
        return skill_error(
            "Unsupported texture file parameter",
            "UNSUPPORTED_TEXTURE_PARAMETER",
            node_type=texture_node.type().name(),
        )

    cs_parm = texture_node.parm("colorspace") if colorspace else None
    try:
        cs_parm_type = cs_parm.parmTemplate().type() if cs_parm is not None else None
    except Exception:  # noqa: BLE001
        cs_parm_type = None
    if colorspace is not None and cs_parm_type != hou.parmTemplateType.String:
        return skill_error(
            "Explicit color space is unsupported for this texture target",
            "UNSUPPORTED_COLORSPACE",
            node_type=texture_node.type().name(),
        )
    try:
        snapshots = [(parm, parm.eval())]
        if cs_parm is not None:
            snapshots.append((cs_parm, cs_parm.eval()))
        parm.set(texture_path)
        if cs_parm is not None:
            cs_parm.set(colorspace)
        texture_readback = parm.eval()
        if texture_readback != texture_path:
            raise RuntimeError("readback mismatch")
        if cs_parm is not None and cs_parm.eval() != colorspace:
            raise RuntimeError("colorspace readback mismatch")
    except Exception:  # noqa: BLE001
        if "snapshots" not in locals() or not _rollback_parms(snapshots):
            return skill_error(
                "Texture assignment failed and rollback could not be verified",
                "TEXTURE_ROLLBACK_FAILED",
            )
        return skill_error("Texture assignment failed", "TEXTURE_ASSIGNMENT_FAILED")

    readback = {"parameter": parameter_name, "texture_path": str(texture_readback)}
    context = {"detected_colorspace": _detect_colorspace(texture_path)}
    if colorspace is not None:
        readback["colorspace"] = str(cs_parm.eval())
        context["colorspace_applied"] = colorspace
    return skill_success(
        "Assigned texture to image node parameter",
        material=node_summary(texture_node),
        parameter=parameter_name,
        texture_path=texture_path,
        verified=True,
        undo_label=undo_label,
        readback=readback,
        **context,
    )


def _destroy_created_node(node: Any) -> bool:
    try:
        parent = node.parent()
        name = node.name()
        node.destroy()
        return parent.node(name) is not node
    except Exception:  # noqa: BLE001
        return False


def _owner_marker(material_node: Any, input_index: int) -> str:
    return "v1|{}|{}".format(material_node.path(), input_index)


def _is_owned_texture(node: Any, texture_type: str, owner_marker: str) -> bool:
    try:
        return node.type().name() == texture_type and node.userData(_OWNER_USER_DATA_KEY) == owner_marker
    except Exception:  # noqa: BLE001
        return False


def _assign_wired_material(
    material_node: Any,
    material_type: str,
    parameter_name: str,
    texture_path: str,
    colorspace: Optional[str],
    undo_label: str,
) -> dict:
    texture_type = _WIRED_MATERIAL_NODE_TYPES[material_type]
    try:
        input_names = tuple(material_node.inputNames())
    except Exception:  # noqa: BLE001
        input_names = ()
    input_index = next(
        (index for index, name in enumerate(input_names) if name.lower() == parameter_name.lower()),
        None,
    )
    if input_index is None:
        return skill_error(
            "Unsupported material texture input",
            "UNSUPPORTED_TEXTURE_PARAMETER",
            node_type=material_type,
        )

    try:
        previous_input = material_node.input(input_index)
    except Exception:  # noqa: BLE001
        return skill_error("Material input cannot be read safely", "TEXTURE_WIRING_FAILED")

    owner_marker = _owner_marker(material_node, input_index)
    created = not _is_owned_texture(previous_input, texture_type, owner_marker)
    if created:
        try:
            texture_node = material_node.parent().createNode(texture_type)
            texture_node.setUserData(_OWNER_USER_DATA_KEY, owner_marker)
            if texture_node.userData(_OWNER_USER_DATA_KEY) != owner_marker:
                raise RuntimeError("ownership readback mismatch")
        except Exception:  # noqa: BLE001
            if "texture_node" in locals() and not _destroy_created_node(texture_node):
                return skill_error(
                    "Texture node creation failed and rollback could not be verified",
                    "TEXTURE_ROLLBACK_FAILED",
                )
            return skill_error(
                "Required texture node could not be created",
                "TEXTURE_NODE_CREATION_FAILED",
                node_type=texture_type,
            )
    else:
        texture_node = previous_input

    file_parm = next((texture_node.parm(name) for name in _IMAGE_FILE_PARMS if texture_node.parm(name)), None)
    if file_parm is None:
        if created and not _destroy_created_node(texture_node):
            return skill_error(
                "Texture node validation failed and rollback could not be verified",
                "TEXTURE_ROLLBACK_FAILED",
            )
        return skill_error(
            "Texture node has no file path parameter",
            "UNSUPPORTED_TEXTURE_PARAMETER",
            node_type=texture_node.type().name(),
        )

    try:
        snapshots = [(file_parm, file_parm.eval())]
        file_parm.set(texture_path)
        if created:
            material_node.setInput(input_index, texture_node, 0)
        if file_parm.eval() != texture_path or material_node.input(input_index) is not texture_node:
            raise RuntimeError("readback mismatch")
    except Exception:  # noqa: BLE001
        rollback_ok = _rollback_parms(snapshots) if "snapshots" in locals() else False
        try:
            if created and material_node.input(input_index) is texture_node:
                material_node.setInput(input_index, previous_input, 0)
            rollback_ok = material_node.input(input_index) is previous_input and rollback_ok
        except Exception:  # noqa: BLE001
            rollback_ok = False
        if created:
            rollback_ok = _destroy_created_node(texture_node) and rollback_ok
        if not rollback_ok:
            return skill_error(
                "Texture wiring failed and rollback could not be verified",
                "TEXTURE_ROLLBACK_FAILED",
            )
        return skill_error("Texture could not be wired to the material input", "TEXTURE_WIRING_FAILED")

    return skill_success(
        "Assigned and wired texture to material",
        material=node_summary(material_node),
        parameter=parameter_name,
        texture_node=node_summary(texture_node),
        texture_path=texture_path,
        detected_colorspace=_detect_colorspace(texture_path),
        reused_owned_node=not created,
        verified=True,
        undo_label=undo_label,
        readback={
            "input_index": input_index,
            "texture_node": texture_node.path(),
            "texture_path": str(file_parm.eval()),
        },
    )


def assign_texture(
    material_path: str,
    parameter_name: str,
    texture_path: str,
    colorspace: Optional[str] = None,
) -> dict:
    """Assign a texture to one explicitly supported material or image target."""
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return hou_import_error()

    if not isinstance(material_path, str) or not material_path.startswith("/"):
        return skill_error("Invalid Houdini material path", "INVALID_MATERIAL_PATH")
    if not isinstance(parameter_name, str) or not _PARAMETER_NAME_RE.fullmatch(parameter_name):
        return skill_error("Invalid texture parameter name", "INVALID_PARAMETER_NAME")
    if not isinstance(texture_path, str) or not texture_path:
        return skill_error("Invalid texture file path", "INVALID_TEXTURE_PATH")
    if colorspace is not None and (not isinstance(colorspace, str) or not colorspace):
        return skill_error("Invalid texture color space", "INVALID_COLORSPACE")
    if not Path(texture_path).is_file():
        return skill_error(
            "Texture file was not found",
            "TEXTURE_FILE_NOT_FOUND",
            prompt="Check the texture path and try again.",
        )

    try:
        target_node = get_node(hou, material_path)
        target_type = target_node.type().name()
    except Exception:  # noqa: BLE001
        return skill_error("Material or texture target was not found", "TEXTURE_TARGET_NOT_FOUND")

    supported_types = _PRINCIPLED_SHADER_TYPES | _DIRECT_TEXTURE_NODE_TYPES | frozenset(_WIRED_MATERIAL_NODE_TYPES)
    if target_type not in supported_types:
        return skill_error(
            "Unsupported texture assignment target",
            "UNSUPPORTED_TEXTURE_TARGET",
            node_type=target_type or "unknown",
        )
    if colorspace is not None and target_type in _PRINCIPLED_SHADER_TYPES:
        return skill_error(
            "Explicit color space is unsupported for this texture target",
            "UNSUPPORTED_COLORSPACE",
            node_type=target_type,
        )
    if colorspace is not None and target_type in _WIRED_MATERIAL_NODE_TYPES:
        return skill_error(
            "Explicit color space is unsupported for this texture target",
            "UNSUPPORTED_COLORSPACE",
            node_type=target_type,
        )

    undo_label = "DCC MCP: assign texture {}".format(parameter_name)
    try:
        with _undo_group(hou, undo_label):
            if target_type in _PRINCIPLED_SHADER_TYPES:
                return _assign_principled(target_node, parameter_name, texture_path, colorspace, undo_label)
            if target_type in _DIRECT_TEXTURE_NODE_TYPES:
                return _assign_direct_texture(hou, target_node, parameter_name, texture_path, colorspace, undo_label)
            return _assign_wired_material(
                target_node,
                target_type,
                parameter_name,
                texture_path,
                colorspace,
                undo_label,
            )
    except Exception:  # noqa: BLE001
        return skill_error("Texture assignment failed", "TEXTURE_ASSIGNMENT_FAILED")


@skill_entry
def main(**kwargs) -> dict:
    return assign_texture(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
