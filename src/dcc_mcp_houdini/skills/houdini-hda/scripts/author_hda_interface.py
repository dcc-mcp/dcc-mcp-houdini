"""Author a safe declarative parameter interface on an HDA or subnet."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Sequence, Tuple

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

_PARM_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
_FORBIDDEN_FIELDS = {
    "callback",
    "item_generator_script",
    "python",
    "script",
    "script_callback",
    "script_callback_language",
}
_TYPES = {"folder", "float", "int", "toggle", "string", "menu"}


def _values(value: Any, count: int, cast: Any) -> Tuple[Any, ...]:
    raw = value if isinstance(value, (list, tuple)) else [value] * count
    if len(raw) != count:
        raise ValueError("default must contain exactly {} value(s)".format(count))
    return tuple(cast(item) for item in raw)


def _reject_unsafe_fields(spec: Dict[str, Any]) -> None:
    unsafe = sorted(_FORBIDDEN_FIELDS.intersection(spec))
    if unsafe:
        raise ValueError("Executable parameter fields are not allowed: {}".format(", ".join(unsafe)))
    for child in spec.get("children", []):
        if isinstance(child, dict):
            _reject_unsafe_fields(child)


def _build_template(
    hou: Any,
    spec: Dict[str, Any],
    names: set,
    promotions: List[Dict[str, str]],
) -> Tuple[Any, int]:
    if not isinstance(spec, dict):
        raise ValueError("Each parameter template must be an object")
    _reject_unsafe_fields(spec)
    kind = str(spec.get("type", "")).strip().lower()
    name = str(spec.get("name", "")).strip()
    label = str(spec.get("label") or name).strip()
    if kind not in _TYPES:
        raise ValueError("Unsupported parameter type: {!r}".format(kind))
    if not _PARM_NAME.match(name):
        raise ValueError("Invalid parameter name: {!r}".format(name))
    if name in names:
        raise ValueError("Duplicate parameter name: {}".format(name))
    if not label:
        raise ValueError("Parameter label must not be empty: {}".format(name))
    names.add(name)
    help_text = spec.get("help")

    if kind == "folder":
        if spec.get("promotion") is not None:
            raise ValueError("Folders cannot promote an internal parameter: {}".format(name))
        children = []
        count = 1
        for child in spec.get("children", []):
            template, child_count = _build_template(hou, child, names, promotions)
            children.append(template)
            count += child_count
        return hou.FolderParmTemplate(name, label, parm_templates=tuple(children)), count

    components = int(spec.get("components", 1))
    if components < 1 or components > 4:
        raise ValueError("components must be between 1 and 4: {}".format(name))
    if kind == "float":
        kwargs = {
            "default_value": _values(spec.get("default", 0.0), components, float),
            "help": help_text,
        }
        if "min" in spec:
            kwargs["min"] = float(spec["min"])
            kwargs["min_is_strict"] = bool(spec.get("min_is_strict", False))
        if "max" in spec:
            kwargs["max"] = float(spec["max"])
            kwargs["max_is_strict"] = bool(spec.get("max_is_strict", False))
        if "min" in kwargs and "max" in kwargs and kwargs["min"] > kwargs["max"]:
            raise ValueError("min cannot exceed max: {}".format(name))
        template = hou.FloatParmTemplate(name, label, components, **kwargs)
    elif kind == "int":
        kwargs = {
            "default_value": _values(spec.get("default", 0), components, int),
            "help": help_text,
        }
        if "min" in spec:
            kwargs["min"] = int(spec["min"])
            kwargs["min_is_strict"] = bool(spec.get("min_is_strict", False))
        if "max" in spec:
            kwargs["max"] = int(spec["max"])
            kwargs["max_is_strict"] = bool(spec.get("max_is_strict", False))
        if "min" in kwargs and "max" in kwargs and kwargs["min"] > kwargs["max"]:
            raise ValueError("min cannot exceed max: {}".format(name))
        template = hou.IntParmTemplate(name, label, components, **kwargs)
    elif kind == "toggle":
        if components != 1:
            raise ValueError("Toggle parameters have exactly one component: {}".format(name))
        template = hou.ToggleParmTemplate(name, label, default_value=bool(spec.get("default", False)), help=help_text)
    elif kind == "string":
        template = hou.StringParmTemplate(
            name,
            label,
            components,
            default_value=_values(spec.get("default", ""), components, str),
            help=help_text,
        )
    else:
        if components != 1:
            raise ValueError("Menu parameters have exactly one component: {}".format(name))
        items = spec.get("items", [])
        if not isinstance(items, list) or not items:
            raise ValueError("Menu parameters require at least one item: {}".format(name))
        tokens = [str(item.get("token", "")) for item in items]
        labels = [str(item.get("label") or item.get("token") or "") for item in items]
        if any(not token for token in tokens) or len(tokens) != len(set(tokens)):
            raise ValueError("Menu item tokens must be non-empty and unique: {}".format(name))
        default = spec.get("default", tokens[0])
        if isinstance(default, int):
            default_index = default
        else:
            if str(default) not in tokens:
                raise ValueError("Menu default is not a declared token: {}".format(name))
            default_index = tokens.index(str(default))
        if default_index < 0 or default_index >= len(tokens):
            raise ValueError("Menu default index is out of range: {}".format(name))
        template = hou.MenuParmTemplate(
            name,
            label,
            menu_items=tuple(tokens),
            menu_labels=tuple(labels),
            default_value=default_index,
            help=help_text,
        )

    promotion = spec.get("promotion")
    if promotion is not None:
        if not isinstance(promotion, dict):
            raise ValueError("promotion must be an object: {}".format(name))
        source_path = str(promotion.get("source_node_path", "")).strip()
        source_parm = str(promotion.get("source_parm", "")).strip()
        if not source_path or not source_parm:
            raise ValueError("promotion requires source_node_path and source_parm: {}".format(name))
        promotions.append({"name": name, "source_node_path": source_path, "source_parm": source_parm})
    return template, 1


def author_hda_interface(
    node_path: str,
    templates: Sequence[Dict[str, Any]],
    conflict_policy: str = "error",
) -> dict:
    """Apply safe parameter templates and optional native channel promotions."""
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        if not templates:
            raise ValueError("templates must not be empty")
        if conflict_policy not in {"error", "replace"}:
            raise ValueError("conflict_policy must be 'error' or 'replace'")
        node = hou.node(node_path)
        if node is None:
            raise ValueError("Houdini node not found: {}".format(node_path))
        definition = node.type().definition()
        owner = definition or node
        group = owner.parmTemplateGroup()
        names = set()
        promotions: List[Dict[str, str]] = []
        prepared = []
        parameter_count = 0
        for spec in templates:
            template, count = _build_template(hou, spec, names, promotions)
            prepared.append(template)
            parameter_count += count

        if promotions and definition is not None and node.matchesCurrentDefinition():
            raise ValueError("HDA must be unlocked before promoting internal parameters")
        parent_prefix = node.path().rstrip("/") + "/"
        for promotion in promotions:
            source = hou.node(promotion["source_node_path"])
            if source is None or not source.path().startswith(parent_prefix):
                raise ValueError("Promotion source must be inside the HDA: {}".format(promotion["source_node_path"]))
            if source.parmTuple(promotion["source_parm"]) is None:
                raise ValueError(
                    "Source parameter tuple not found: {}/{}".format(source.path(), promotion["source_parm"])
                )

        for template in prepared:
            existing = group.find(template.name())
            if existing is not None and conflict_policy == "error":
                raise ValueError("Parameter already exists: {}".format(template.name()))
            if existing is None:
                group.append(template)
            else:
                group.replace(template.name(), template)
        owner.setParmTemplateGroup(group)

        promoted = []
        if promotions:
            node = hou.node(node_path)
            if node is None:
                raise RuntimeError("HDA node disappeared while updating its interface: {}".format(node_path))
            for promotion in promotions:
                source = hou.node(promotion["source_node_path"])
                source_tuple = source.parmTuple(promotion["source_parm"]) if source is not None else None
                target_tuple = node.parmTuple(promotion["name"])
                if source_tuple is None or target_tuple is None:
                    raise RuntimeError("Promoted parameter tuple was not created: {}".format(promotion["name"]))
                values = source_tuple.eval()
                target_tuple.set(values)
                source_tuple.set(target_tuple, language=hou.exprLanguage.Hscript)
                promoted.append(
                    {
                        "name": promotion["name"],
                        "source": "{}/{}".format(promotion["source_node_path"], promotion["source_parm"]),
                        "component_count": len(values),
                    }
                )

        return skill_success(
            "Authored HDA parameter interface",
            node_path=node.path(),
            interface_owner="definition" if definition is not None else "node",
            parameter_count=parameter_count,
            top_level_parameters=[template.name() for template in prepared],
            promoted=promoted,
            conflict_policy=conflict_policy,
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to author HDA parameter interface")


@skill_entry
def main(**kwargs) -> dict:
    return author_hda_interface(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
