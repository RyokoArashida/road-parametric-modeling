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


def unwrap_gh_value(obj: Any) -> Any:
    if obj is None:
        return None

    script_variable = getattr(obj, "ScriptVariable", None)
    if callable(script_variable):
        try:
            return script_variable()
        except TypeError:
            pass

    if hasattr(obj, "Value"):
        return obj.Value

    return obj


def bake_one_geometry(
    geometry: Any,
    name: str,
    layer_index: int | None = None,
    color=None,
) -> str | None:
    geometry = unwrap_gh_value(geometry)
    if geometry is None:
        return None

    attr = duplicate_attributes(
        name=name,
        layer_index=layer_index,
        color=color,
    )

    rhdoc = Rhino.RhinoDoc.ActiveDoc

    if isinstance(geometry, Rhino.Geometry.Brep):
        guid = rhdoc.Objects.AddBrep(geometry, attr)
    elif isinstance(geometry, Rhino.Geometry.Curve):
        guid = rhdoc.Objects.AddCurve(geometry, attr)
    elif isinstance(geometry, Rhino.Geometry.Surface):
        guid = rhdoc.Objects.AddSurface(geometry, attr)
    elif isinstance(geometry, Rhino.Geometry.Mesh):
        guid = rhdoc.Objects.AddMesh(geometry, attr)
    elif isinstance(geometry, Rhino.Geometry.Point):
        guid = rhdoc.Objects.AddPoint(geometry.Location, attr)
    elif isinstance(geometry, Rhino.Geometry.Point3d):
        guid = rhdoc.Objects.AddPoint(geometry, attr)
    elif isinstance(geometry, Rhino.Geometry.Line):
        guid = rhdoc.Objects.AddLine(geometry, attr)
    elif isinstance(geometry, Rhino.Geometry.Polyline):
        guid = rhdoc.Objects.AddPolyline(geometry, attr)
    elif isinstance(geometry, Rhino.Geometry.Arc):
        guid = rhdoc.Objects.AddArc(geometry, attr)
    elif isinstance(geometry, Rhino.Geometry.Circle):
        guid = rhdoc.Objects.AddCircle(geometry, attr)
    elif isinstance(geometry, Rhino.Geometry.Extrusion):
        guid = rhdoc.Objects.AddExtrusion(geometry, attr)
    else:
        return None

    if guid is None or guid == Guid.Empty:
        return None

    return str(guid)


def bake_one_brep(
    brep: Any,
    name: str,
    layer_index: int | None = None,
    color=None,
) -> str | None:
    return bake_one_geometry(
        geometry=brep,
        name=name,
        layer_index=layer_index,
        color=color,
    )


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

        geometries = ensure_list(value)
        if not geometries:
            continue

        # 最初の1個だけ使う
        guids = []
        for geometry in geometries:
            guid = bake_one_geometry(
                geometry=geometry,
                name=name,
                layer_index=layer_index,
                color=color,
            )
            if guid is not None:
                guids.append(guid)

        if guids:
            baked_result[name] = guids

    if redraw:
        Rhino.RhinoDoc.ActiveDoc.Views.Redraw()

    return baked_result

result = bake_flat_brep_dict(
    keys=keys,
    values=values,
    layer_index=layer_index,
    color=color,
)


