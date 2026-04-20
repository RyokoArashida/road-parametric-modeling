from __future__ import annotations

from typing import Any

import Rhino
from System import Guid


def duplicate_attributes(
    name: str,
    layer_index: int | None = None,
    color=None,
) -> Rhino.DocObjects.ObjectAttributes:
    attr = Rhino.DocObjects.ObjectAttributes()
    attr.Name = name

    if layer_index is not None:
        attr.LayerIndex = int(layer_index)

    if color is not None:
        attr.ObjectColor = color
        attr.ColorSource = Rhino.DocObjects.ObjectColorSource.ColorFromObject

    return attr


def ensure_list(obj: Any) -> list[Any]:
    if obj is None:
        return []
    if isinstance(obj, (list, tuple)):
        return list(obj)
    return [obj]


def bake_one_brep(
    brep: Rhino.Geometry.Brep,
    name: str,
    layer_index: int | None = None,
    color=None,
) -> str | None:
    if brep is None:
        return None

    if not isinstance(brep, Rhino.Geometry.Brep):
        raise TypeError(f"brep must be Rhino.Geometry.Brep, got {type(brep)}")

    attr = duplicate_attributes(
        name=name,
        layer_index=layer_index,
        color=color,
    )

    rhdoc = Rhino.RhinoDoc.ActiveDoc
    guid = rhdoc.Objects.AddBrep(brep, attr)

    if guid is None or guid == Guid.Empty:
        return None

    return str(guid)


def bake_flat_brep_dict(
    keys: list[str],
    values: list[Any],
    layer_index: int | None = None,
    color=None,
    redraw: bool = True,
) -> dict[str, list[str]]:

    baked_result: dict[str, list[str]] = {}
    seen_names: set[str] = set()

    for name, value in zip(keys, values):

        # すでに処理済みならスキップ
        if name in seen_names:
            continue
        seen_names.add(name)

        breps = ensure_list(value)
        if not breps:
            continue

        # 最初の1個だけ使う
        brep = breps[0]

        guid = bake_one_brep(
            brep=brep,
            name=name,
            layer_index=layer_index,
            color=color,
        )

        if guid is not None:
            baked_result[name] = [guid]

    if redraw:
        Rhino.RhinoDoc.ActiveDoc.Views.Redraw()

    return baked_result

result = bake_flat_brep_dict(
    keys=keys,
    values=values,
    layer_index=layer_index,
    color=color,
)