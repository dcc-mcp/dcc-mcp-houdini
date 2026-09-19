"""DOP skeleton authoring and cached diagnostics."""

from contextlib import contextmanager

from dcc_mcp_houdini._domain_graph import node_summary, parameter_edit, validate_parameters

SOLVER_TYPES = {"pyro": "pyrosolver", "flip": "flipsolver", "rbd": "rbdsolver", "vellum": "vellumsolver"}

FRACTURE_TYPES = {
    "voronoi": "voronoifracture",
    "boolean": "booleanfracture",
    "material": "rbdmaterialfracture",
}

CONSTRAINT_TYPES = {
    "glue": "glueconrel",
    "soft": "softconrel",
    "wire": "wireconrel",
    "cone": "conetwistconrel",
}

COLLISION_TYPES = {"static": "staticobject", "deforming": "staticobject"}


def solver_base_type(type_name):
    parts = type_name.split("::")
    if len(parts) > 1 and parts[-1][:1].isdigit():
        parts.pop()
    return parts[-1]


def validate_simulation_type(simulation_type):
    if simulation_type not in SOLVER_TYPES:
        raise ValueError("Unsupported simulation_type: {!r}".format(simulation_type))
    return simulation_type


def validate_choice(value, mapping, label):
    if value not in mapping:
        raise ValueError("Unsupported {}: {!r}".format(label, value))
    return mapping[value]


def children_summary(node):
    return [node_summary(child) for child in node.children()]


def find_solver(network):
    """First child whose base type is a supported DOP solver, else ``None``."""
    solvers = set(SOLVER_TYPES.values())
    for child in network.children():
        if solver_base_type(child.type().name()) in solvers:
            return child
    return None


@contextmanager
def apply_parameters(node, parameters):
    """Apply scalar overrides, reporting names the node does not expose.

    Missing parameters are reported through ``skipped`` instead of failing the
    whole call: node types and Houdini builds differ in which parameters they
    expose, and a missing optional override is not an authoring error.
    """
    validate_parameters(parameters)
    overrides = parameters or {}
    known = {}
    skipped = []
    for name, value in overrides.items():
        if isinstance(value, (str, bool, int, float)) and node.parm(name) is not None:
            known[name] = value
        else:
            skipped.append(name)
    with parameter_edit(node, known) as applied:
        yield applied, sorted(skipped)
