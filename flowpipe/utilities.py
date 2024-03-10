"""Utilities for serializing and importing Nodes."""
try:
    import importlib
except ImportError:
    pass
import json
import sys
from hashlib import sha256


def import_class(module_name, cls_name, file_location=None):
    """Import and return the given class from the given module.

    File location can be given to import the class from a location that
    is not accessible through the PYTHONPATH.
    This works from python 2.6 to python 3.
    """
    try:
        module = importlib.import_module(module_name)
    except (ImportError, ModuleNotFoundError):
        spec = importlib.util.spec_from_file_location(module_name, file_location)
        module = importlib.util.module_from_spec(spec)
        # sys.modules[module_name] = module
        spec.loader.exec_module(module)
    try:
        cls = getattr(module, cls_name)
    except AttributeError:
        msg = f"Failed to find class {cls_name} in {module_name} in file {file_location}" if file_location else f"Failed to find class {cls_name} in {module_name}"
        raise Exception(msg)
    return cls


def deserialize_node(data):
    """De-serialize a node from the given json data."""
    node = import_class(data["module"], data["cls"], data["file_location"])(
        graph=None
    )
    node.post_deserialize(data)
    return node


def deserialize_graph(data):
    """De-serialize from the given json data."""
    graph = import_class(data["module"], data["cls"])()
    graph.name = data["name"]
    graph.nodes = []
    for node in data["nodes"]:
        deserialized_node = deserialize_node(node)
        graph.nodes.append(deserialized_node)
        deserialized_node.graph = graph

    nodes = {n.identifier: n for n in graph.nodes}

    all_nodes = list(data["nodes"])

    subgraphs = []
    for sub_data in data.get("subgraphs", []):
        subgraph = import_class(sub_data["module"], sub_data["cls"])()
        subgraph.name = sub_data["name"]
        subgraph.nodes = []
        for node in sub_data["nodes"]:
            deserialized_node = deserialize_node(node)
            subgraph.nodes.append(deserialized_node)
            deserialized_node.graph = subgraph
        all_nodes += sub_data["nodes"]
        subgraphs.append(subgraph)
        nodes.update({n.identifier: n for n in subgraph.nodes})

    for node in all_nodes:  # data['nodes']:
        this = nodes[node["identifier"]]
        for name, input_ in node["inputs"].items():
            for identifier, plug in input_["connections"].items():
                upstream = nodes[identifier]
                upstream.outputs[plug].connect(this.inputs[name])
            for sub_plug_name, sub_plug in input_["sub_plugs"].items():
                sub_plug_name = sub_plug_name.split(".")[-1]
                for identifier, plug in sub_plug["connections"].items():
                    upstream = nodes[identifier]
                    upstream.outputs[plug].connect(
                        this.inputs[name][sub_plug_name]
                    )
    return graph


class NodeEncoder(json.JSONEncoder):
    """Custom JSONEncoder to handle non-json serializable node values.

    If the value is not json serializable, a sha256 hash of its bytes is
    encoded instead.
    """

    def default(self, o):
        """Encode the object, handling type errors by encoding into sha256."""
        try:
            return super().default(o)
        except TypeError:
            try:
                return sha256(o).hexdigest()
            except TypeError:
                return str(o)
            except ValueError:
                return sha256(bytes(o)).hexdigest()


def get_hash(obj, hash_func=lambda x: sha256(x).hexdigest()):
    """Safely get the hash of an object.

    This function tries to compute the hash as safely as possible, dealing with
    json data and strings in a well-defined manner.

    Args:
        obj: The object to hash
        hash_func (func(obj) -> str): The hashing function to use

    Returns:
        (str): A hash of the obj

    """
    try:
        return hash_func(obj)
    except (TypeError, ValueError):
        try:
            json_string = json.dumps(obj, sort_keys=True)
        except TypeError:  # pragma: no cover
            pass
        else:
            obj = json_string
        if isinstance(obj, str):
            return hash_func(obj.encode("utf-8"))
        if sys.version_info.major > 2:  # pragma: no cover
            try:
                return hash_func(bytes(obj))
            except TypeError:
                return None
        else:
            return None  # pragma: no cover
