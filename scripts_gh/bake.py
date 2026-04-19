from __future__ import annotations

from typing import Any

import Rhino
import scriptcontext as sc


def ensure_list(obj: Any) -> list[Any]:
    if obj is None:
        return []
    if isinstance(obj, (list, tuple)):
        return list(obj)
    return [obj]


def duplicate_attributes(
    name: str,
    layer_index: int | None = None,
    color=None,
) -> Rhino.DocObjects.ObjectAttributes:
    attr = Rhino.DocObjects.ObjectAttributes()
    attr.Name = name
    if layer_index is not None:
        attr.LayerIndex = layer_index
    if color is not None:
        attr.ObjectColor = color
        attr.ColorSource = Rhino.DocObjects.ObjectColorSource.ColorFromObject
    return attr


def bake_one_geometry(
    geom: Any,
    name: str,
    layer_index: int | None = None,
    color=None,
) -> str | None:
    """
    geom を1個だけ bake する。
    戻り値は GUID文字列。失敗時は None。
    """
    if geom is None:
        return None

    attr = duplicate_attributes(name=name, layer_index=layer_index, color=color)

    obj_table = sc.doc.Objects

    if isinstance(geom, Rhino.Geometry.Point3d):
        guid = obj_table.AddPoint(geom, attr)

    elif isinstance(geom, Rhino.Geometry.Point):
        guid = obj_table.AddPoint(geom.Location, attr)

    elif isinstance(geom, Rhino.Geometry.Curve):
        guid = obj_table.AddCurve(geom, attr)

    elif isinstance(geom, Rhino.Geometry.LineCurve):
        guid = obj_table.AddCurve(geom, attr)

    elif isinstance(geom, Rhino.Geometry.PolylineCurve):
        guid = obj_table.AddCurve(geom, attr)

    elif isinstance(geom, Rhino.Geometry.ArcCurve):
        guid = obj_table.AddCurve(geom, attr)

    elif isinstance(geom, Rhino.Geometry.Mesh):
        guid = obj_table.AddMesh(geom, attr)

    elif isinstance(geom, Rhino.Geometry.Brep):
        guid = obj_table.AddBrep(geom, attr)

    elif isinstance(geom, Rhino.Geometry.Extrusion):
        guid = obj_table.AddExtrusion(geom, attr)

    elif isinstance(geom, Rhino.Geometry.Surface):
        brep = geom.ToBrep()
        guid = obj_table.AddBrep(brep, attr) if brep else None

    elif isinstance(geom, Rhino.Geometry.SubD):
        guid = obj_table.AddSubD(geom, attr)

    elif isinstance(geom, Rhino.Geometry.Hatch):
        guid = obj_table.AddHatch(geom, attr)

    elif isinstance(geom, Rhino.Geometry.TextDot):
        guid = obj_table.AddTextDot(geom, attr)

    elif isinstance(geom, Rhino.Geometry.AnnotationBase):
        guid = obj_table.Add(geom, attr)

    elif isinstance(geom, Rhino.Geometry.GeometryBase):
        guid = obj_table.Add(geom, attr)

    else:
        return None

    if guid is None or guid == Rhino.System.Guid.Empty:
        return None

    return str(guid)


def bake_flat_dict(
    flat_dict: dict[str, Any],
    layer_index: int | None = None,
    color=None,
    redraw: bool = True,
) -> dict[str, list[str]]:
    """
    フラットな辞書:
        {name: geometry_or_list_of_geometries}
    をまとめて bake する。

    Returns
    -------
    dict[str, list[str]]
        {name: [guid, guid, ...]}
    """
    baked_result: dict[str, list[str]] = {}

    for name, value in flat_dict.items():
        geoms = ensure_list(value)
        baked_guids: list[str] = []

        for geom in geoms:
            guid = bake_one_geometry(
                geom=geom,
                name=name,
                layer_index=layer_index,
                color=color,
            )
            if guid is not None:
                baked_guids.append(guid)

        if baked_guids:
            baked_result[name] = baked_guids

    if redraw:
        sc.doc.Views.Redraw()

    return baked_result

def main():
    # モジュールでflat_dict, layer_index, colorを受け取っている。
    result = bake_flat_dict(
        flat_dict=flat_dict,
        layer_index=layer_index,
        color=color,
    )
    return result

if __name__ == "__main__":
    result = main()

