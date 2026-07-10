from dataclasses import fields
from typing import Any

import Rhino.Geometry as rg

from my_project.config.schemas.cross_girder_schemas import MainGirderPointInfo_IO
from my_project.config.util_schemas import Point3D
from my_project.utils.geometry.points import get_point_by_xy_offset
from my_project.utils.geometry_gh.const import const_line_obj, const_polycurve_obj


def get_polyline_from_points(infos: list[Any]) -> dict[str, rg.Polyline]:
    points = {}
    names = [f.name for f in fields(infos[0])]
    for name in names:
        points[name] = []
    for info in infos:
        d = {f.name: getattr(info, f.name) for f in fields(info)}
        for name, point in d.items():
            points[name].append(point)
    polylines = {}
    for name, pts in points.items():
        if isinstance(pts[0], Point3D):
            start_distance = const_line_obj(pts[0], pts[1]).Length
            end_distance = const_line_obj(pts[-1], pts[-2]).Length
            extended_start_point = get_point_by_xy_offset(
                point1=pts[0],
                point2=pts[1],
                offset=-start_distance * 0.1,
            )
            extended_end_point = get_point_by_xy_offset(
                point1=pts[-1],
                point2=pts[-2],
                offset=-end_distance * 0.1,
            )
            extended_pts = [extended_start_point] + pts[1:-1] + [extended_end_point]
            polylines[name] = const_polycurve_obj(extended_pts)
    return polylines


def get_MG_polylines(
    MG_point_dict_for_CG_for_MG: list[MainGirderPointInfo_IO],
):
    MG_type = "I" if MG_point_dict_for_CG_for_MG[0].I_points is not None else "Box"
    if MG_type == "I":
        info_list = [mg_point_info.I_points for mg_point_info in MG_point_dict_for_CG_for_MG]
    else:
        info_list = [mg_point_info.Box_points for mg_point_info in MG_point_dict_for_CG_for_MG]
    return get_polyline_from_points(info_list)
