from collections.abc import Mapping
from dataclasses import is_dataclass
from typing import Any

import Rhino.Geometry as rg

from my_project.config.util_schemas import Point2D, Point3D
from my_project.utils.geometry_gh.const import const_point_obj

RHINO_TYPES = (
    rg.Point3d,
    rg.Vector3d,
    rg.Curve,
    rg.Brep,
    rg.Surface,
    rg.Mesh,
    rg.Line,
    rg.Plane,
)


def is_leaf_for_bake(obj: Any) -> bool:
    return obj is None or isinstance(obj, (RHINO_TYPES, Point2D, Point3D))


def normalize_leaf_for_bake(obj: Any) -> Any:
    if isinstance(obj, (Point2D, Point3D)):
        return const_point_obj(obj)
    return obj


def to_dict_recursive_for_bake(obj: Any) -> Any:
    # Keep Rhino geometry and supported point values as bake leaves.
    if is_leaf_for_bake(obj):
        return normalize_leaf_for_bake(obj)

    if isinstance(obj, Mapping):
        return {
            k: to_dict_recursive_for_bake(v)
            for k, v in obj.items()
        }

    if is_dataclass(obj):
        return {
            k: to_dict_recursive_for_bake(v)
            for k, v in obj.__dict__.items()
        }

    if hasattr(obj, "__dict__"):
        return {
            k: to_dict_recursive_for_bake(v)
            for k, v in obj.__dict__.items()
            if not k.startswith("_")
        }

    if isinstance(obj, (list, tuple)):
        return {
            i: to_dict_recursive_for_bake(v)
            for i, v in enumerate(obj)
        }

    return obj


def flatten_dict_for_bake(
    d: Mapping,
    parent_key: str = "",
    sep: str = "_",
) -> dict[str, Any]:
    result = {}

    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else str(k)

        if isinstance(v, Mapping):
            result.update(flatten_dict_for_bake(v, new_key, sep))
        else:
            result[new_key] = v

    return result


def flatten_any_for_bake(obj: Any, sep: str = "_") -> dict[str, Any]:
    dict_obj = to_dict_recursive_for_bake(obj)

    if not isinstance(dict_obj, Mapping):
        return {"value": dict_obj}

    return flatten_dict_for_bake(dict_obj, sep=sep)


def get_keys_and_values_for_bake(world_items_dict):
    flattened = flatten_any_for_bake(world_items_dict)
    items = list(flattened.items())
    items = [
        (k, v)
        for k, v in items
        if isinstance(v, RHINO_TYPES)
    ]
    keys = [k for k, _ in items]
    values = [v for _, v in items]
    return keys, values
