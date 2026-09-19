"""Bounded particle readback: counts, attributes and bounds without cooking."""

from dcc_mcp_core.skill import skill_entry, skill_exception, skill_success

from dcc_mcp_houdini._domain_graph import get_node, hou_missing_error, node_summary, validate_identifier


def _requested_attributes(attributes):
    if attributes is None:
        return []
    if not isinstance(attributes, (list, tuple)) or len(attributes) > 32:
        raise ValueError("attributes must contain at most 32 names")
    return [validate_identifier(name, "attribute name") for name in attributes]


def _attribute_report(attribute):
    data_type = attribute.dataType()
    return {
        "name": attribute.name(),
        "size": attribute.size(),
        "type": data_type.name() if hasattr(data_type, "name") else str(data_type),
    }


def _cooked_geometry(node):
    """Return cooked geometry or ``None``; never raise for an unreadable node."""
    try:
        return node.geometry()
    except Exception:
        return None


def inspect_particles(node_path: str, attributes=None, max_attributes: int = 32) -> dict:
    try:
        import hou
    except ImportError:
        return hou_missing_error()
    try:
        if not isinstance(max_attributes, int) or isinstance(max_attributes, bool):
            raise ValueError("max_attributes must be an integer")
        if not 1 <= max_attributes <= 64:
            raise ValueError("max_attributes must be between 1 and 64")
        requested = _requested_attributes(attributes)
        node = get_node(hou, node_path)
        summary = node_summary(node)
        geometry = _cooked_geometry(node)
        if geometry is None:
            return skill_success(
                "Inspected particle node without cooked geometry",
                node=summary,
                geometry_available=False,
                particle_count=None,
                attributes=[],
                requested_attributes=requested,
                bounding_box=None,
                valid=not summary["errors"],
                validation_scope="node_diagnostics_only",
                simulation_verified=False,
            )
        points = list(geometry.points())
        candidates = geometry.pointAttribs()
        if requested:
            wanted = set(requested)
            candidates = [attribute for attribute in candidates if attribute.name() in wanted]
        reports = [_attribute_report(attribute) for attribute in candidates[:max_attributes]]
        bounding_box = None
        box = geometry.boundingBox()
        if box is not None:
            bounding_box = {
                "min": tuple(float(value) for value in box.minvec()),
                "max": tuple(float(value) for value in box.maxvec()),
            }
        return skill_success(
            "Inspected particle node",
            node=summary,
            geometry_available=True,
            particle_count=len(points),
            attribute_count=len(candidates),
            attributes=reports,
            truncated_attributes=len(candidates) > len(reports),
            requested_attributes=requested,
            bounding_box=bounding_box,
            valid=not summary["errors"],
            validation_scope="cached_geometry_readback",
            simulation_verified=False,
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to inspect particles")


@skill_entry
def main(**kwargs):
    return inspect_particles(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
