"""Small explicit HOM doubles: unsupported methods fail instead of auto-mocking."""

from types import SimpleNamespace


class Parm:
    def __init__(self, name, value=0):
        self._name, self.value = name, value
        self.keys = ()
        self.fail_next_set = False

    def name(self):
        return self._name

    def eval(self):
        return self.value

    def keyframes(self):
        return self.keys

    def unexpandedString(self):
        return self.value

    def deleteAllKeyframes(self):
        self.keys = ()

    def setKeyframes(self, keys):
        self.keys = keys

    def set(self, value, follow_parm_reference=False):
        assert follow_parm_reference is False
        if self.fail_next_set:
            self.fail_next_set = False
            raise RuntimeError("parameter rejected")
        self.value = value


def category(name):
    return SimpleNamespace(name=lambda: name) if name else None


class Node:
    def __init__(self, path, type_name="geo", parent=None, child_category=None, node_category="Object"):
        self._path, self._type = path, type_name
        self._parent, self.child_category, self.node_category = parent, child_category, node_category
        self.registry = parent.registry if parent else {}
        self.registry[path] = self
        self._children, self._inputs = {}, {}
        self.parms = {name: Parm(name, value) for name, value in (("timescale", 1), ("size", 1), ("service", "local"))}
        self.error_messages, self.warning_messages = [], []
        self.destroyed = False
        self.pdg_node = None
        self.cooks = []
        self.reject_create = False
        self.reject_input = False
        self.scheduler = False
        if parent:
            parent._children[self.name()] = self

    def path(self):
        return self._path

    def name(self):
        return self._path.rsplit("/", 1)[-1]

    def type(self):
        return SimpleNamespace(name=lambda: self._type, category=lambda: category(self.node_category))

    def childTypeCategory(self):
        return category(self.child_category)

    def parent(self):
        return self._parent

    def node(self, name):
        return self._children.get(name)

    def children(self):
        return tuple(self._children.values())

    def createNode(self, node_type, node_name=None):
        if self.reject_create:
            raise RuntimeError("type unavailable")
        name = node_name or node_type.replace("::", "_") + "1"
        if name in self._children:
            name += "1"
        child_category = {
            "copnet": "Cop",
            "cop2net": "Cop2",
            "topnet": "Top",
            "dopnet": "Dop",
            "popnet": "Dop",
        }.get(node_type)
        return Node(self.path() + "/" + name, node_type, self, child_category, self.child_category)

    def destroy(self):
        self.destroyed = True
        for child in tuple(self._children.values()):
            child.destroy()
        self.registry.pop(self.path(), None)
        if self._parent:
            self._parent._children.pop(self.name(), None)

    def parm(self, name):
        return self.parms.get(name)

    def parmTuple(self, name):
        return None

    def errors(self):
        return self.error_messages

    def warnings(self):
        return self.warning_messages

    def setInput(self, index, node, output_index=0):
        if self.reject_input:
            raise RuntimeError("input rejected")
        if node is None:
            self._inputs.pop(index, None)
        else:
            self._inputs[index] = (node, output_index)

    def inputConnections(self):
        return [
            SimpleNamespace(inputIndex=lambda i=i: i, inputItem=lambda n=n: n, inputItemOutputIndex=lambda o=o: o)
            for i, (n, o) in sorted(self._inputs.items())
        ]

    def inputs(self):
        return tuple(n for n, _ in self._inputs.values())

    def getPDGNode(self):
        return self.pdg_node

    def isScheduler(self):
        return self.scheduler

    def cookWorkItems(self, block=False):
        self.cooks.append(("branch", block))

    def cookOutputWorkItems(self, block=False):
        self.cooks.append(("output", block))

    def cook(self, force=False):
        self.cooks.append(("node", force))


def scene():
    root = Node("/obj", "obj", child_category="Object")
    geo = Node("/obj/geo1", "geo", root, "Sop")
    return root, geo, SimpleNamespace(node=lambda path: root.registry.get(path))
