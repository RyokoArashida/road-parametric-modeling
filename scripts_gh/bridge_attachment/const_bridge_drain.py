from typing import Union

import Rhino.Geometry as rg

from my_project.config.locale_compat import normalize_lc_time

normalize_lc_time()


from numbers import Number

from my_project.config.file_names import Filenames
from my_project.config.paths import (
    FINAL_OUTPUT_DIR,
    INITIAL_OUTPUT_DIR,
)
from my_project.config.schemas.bridge_drainage_schemas import (
    DrainageInfo,
)
from my_project.config.util_schemas import (
    Point2D,
    Point3D,
)
from my_project.utils.dataframe import flatten_any
from my_project.utils.geometry.points import (
    get_point_by_xy_offset,
)
from my_project.utils.geometry_gh.attributes import get_distance_along_crv
from my_project.utils.geometry_gh.const import (
    const_pipe_brep_from_curve,
    const_point_obj,
    const_polycurve_obj,
    const_rectangular_pipe_brep_from_curve,
)
from my_project.utils.geometry_gh.intersect import (
    get_intersect_point_on_crv_and_points_in_the_same_plane,
)
from my_project.utils.io import load_from_pickle


def get_polilines_2D(
    point_infos: dict[str, dict[str, dict[str, Union[list[Point3D], list[str]]]]]
):
    polyline_2D_dict = {}
    for bridge_name, bridge_info in point_infos.items():
        for polyline_name, polyline_info in bridge_info.items():
            points = polyline_info["points"]
            points_2D = [const_point_obj(Point2D(p.x, p.y)) for p in points]
            polyline_2D= const_polycurve_obj(points_2D)
            distances = get_distance_along_crv(polyline_2D, points_2D)
            polyline_2D_dict[(bridge_name, polyline_name)] = {
                "polyline_2D": polyline_2D,
                "point_names": polyline_info["point_names"],
                "distances": distances,
            }
    return polyline_2D_dict


def get_world_points(
    polyline_dict: dict[tuple[str, str], dict[str, Union[rg.PolylineCurve, list[rg.Point3d], list[str], list[float]]]],
    drainage_info: DrainageInfo,
):
    bridge_name = drainage_info.bridge_name
    points = drainage_info.points

    y_distances = []
    zs = []
    y_base_polylines = []
    x_base_polylines = []
    x_offsets = []
    unkwnown_idxs = []
    for i, p in enumerate(points):
        y_base_polyline = p.y_base_polyline
        y_base_CG_name = p.y_base_CG_name
        y_offset = p.y_offset
        y_adj_ratio = p.y_adj_ratio
        x_base_polyline = p.x_base_polyline
        x_offset = p.x_offset
        z = p.z
        if (bridge_name, y_base_polyline) not in polyline_dict:
            raise ValueError(f"Bridge {bridge_name} does not have polyline {y_base_polyline} in point_infos.")
        y_base_polylines.append(y_base_polyline)
        x_base_polylines.append(x_base_polyline)
        x_offsets.append(x_offset)
        y_base_point_names = polyline_dict[(bridge_name, y_base_polyline)]["point_names"]
        y_base_distances = polyline_dict[(bridge_name, y_base_polyline)]["distances"]
        if y_base_CG_name not in y_base_point_names:
            raise ValueError(f"Polyline {y_base_polyline} does not have point {y_base_CG_name} in point_infos.")
        y_base_CG_index = y_base_point_names.index(y_base_CG_name)
        y_base_CG_distance = y_base_distances[y_base_CG_index]
        if isinstance(y_offset, Number):
            y_distance = y_base_CG_distance + y_offset
            y_distances.append((y_base_polyline, y_distance))
            zs.append(z)
        elif y_offset == "adjustment":
            y_distances.append((None, None))
            zs.append(None)
            unkwnown_idxs.append((i, y_adj_ratio))
        else:
            raise ValueError(f"Invalid y_offset value: {y_offset}")
    if len(unkwnown_idxs) > 0:
        for idx, adj_ratio in unkwnown_idxs:
            prev_idx = None
            for j in range(idx - 1, -1, -1):
                if y_distances[j][1] is not None:
                    prev_idx = j
                    break
            next_idx = None
            for j in range(idx + 1, len(y_distances)):
                if y_distances[j][1] is not None:
                    next_idx = j
                    break
            if prev_idx is None or next_idx is None:
                raise ValueError(
                    f"Cannot adjust y_distance at index {idx}: "
                    f"previous={prev_idx}, next={next_idx}"
                )
            prev_polyline, prev_y_distance = y_distances[prev_idx]
            next_polyline, next_y_distance = y_distances[next_idx]
            if prev_polyline != next_polyline:
                raise ValueError(
                    f"Cannot adjust y_distance at index {idx} because previous and next polylines are different: "
                    f"previous={prev_polyline}, next={next_polyline}"
                )
            prev_z = zs[prev_idx]
            next_z = zs[next_idx]
            y_distance = prev_y_distance + adj_ratio * (next_y_distance - prev_y_distance)
            z = prev_z + adj_ratio * (next_z - prev_z)
            y_distances[idx] = (prev_polyline, y_distance)
            zs[idx] = z
    
    CL_polyline = polyline_dict[(bridge_name, "CL")]["polyline_2D"]
    world_points = []
    for i, (y_base_polyline, y_distance) in enumerate(y_distances):
        if (bridge_name, x_base_polyline) not in polyline_dict:
            raise ValueError(f"Bridge {bridge_name} does not have polyline {x_base_polyline} in point_infos.")
        y_base_crv = polyline_dict[(bridge_name, y_base_polyline)]["polyline_2D"]
        y_point_2D = y_base_crv.PointAtDistance(y_distance)
        CL_point_t = CL_polyline.ClosestPoint(y_point_2D)[1]
        CL_point_2D = CL_polyline.PointAt(CL_point_t)
        # 2点を通る線分がx_base_crvと交差する点を求める。
        x_base_crv = polyline_dict[(bridge_name, x_base_polyline)]["polyline_2D"]
        x_base_point_2D = get_intersect_point_on_crv_and_points_in_the_same_plane(
            target_crv = x_base_crv,
            cutter_points = [y_point_2D, CL_point_2D],
        )
        point_2D = get_point_by_xy_offset(
            point1 = x_base_point_2D,
            point2 = CL_point_2D,
            offset = x_offsets[i],
        )
        point = const_point_obj(Point3D(point_2D.X, point_2D.Y, zs[i]))
        world_points.append(point)
    return world_points

def const_indiv_drains(
    polyline_dict: dict[tuple[str, str], dict[str, Union[rg.PolylineCurve, list[rg.Point3d], list[str], list[float]]]],
    drainage_info: DrainageInfo,
):
    world_points = get_world_points(polyline_dict, drainage_info)
    pipe_infos = drainage_info.pipes
    pipe_brep_dict = {}
    for pipe_info in pipe_infos:
        pipe_name = pipe_info[2].name
        start_idx, end_idx, pipe_spec = pipe_info
        pipe_points = []
        for idx in [start_idx, end_idx]:
            pipe_points.append(world_points[idx])
        pipe_crv = const_polycurve_obj(pipe_points)
        if pipe_spec.diameter is not None:
            if pipe_spec.thickness is None:
                raise ValueError(f"Pipe {pipe_spec.name} has diameter but no thickness.")
            pipe_brep = const_pipe_brep_from_curve(
                curve = pipe_crv,
                outer_radius = pipe_spec.diameter / 2,
                inner_radius = pipe_spec.diameter / 2 - pipe_spec.thickness,
            )
        else:
            if pipe_spec.width is None or pipe_spec.height is None:
                raise ValueError(f"Pipe {pipe_spec.name} has no diameter but width or height is not specified.")
            pipe_brep = const_rectangular_pipe_brep_from_curve(
                curve = pipe_crv,
                width = pipe_spec.width,
                height = pipe_spec.height,
                thickness = pipe_spec.thickness,
            )
        pipe_brep_dict[pipe_name] = pipe_brep
    return pipe_brep_dict


def main(initial_or_final: str):
    if initial_or_final == "initial":
        DIR = INITIAL_OUTPUT_DIR
    elif initial_or_final == "final":
        DIR = FINAL_OUTPUT_DIR
    
    point_infos = load_from_pickle(DIR / f"{Filenames.INPUT}_{Filenames.DRAINAGE}_{Filenames.POINTS}.pickle")
    poliline_dict = get_polilines_2D(point_infos)

    main_drainage_infos = load_from_pickle(DIR / f"{Filenames.INPUT}_{Filenames.DRAINAGE}_{Filenames.MAIN}.pickle")
    road_drainage_infos = load_from_pickle(DIR / f"{Filenames.INPUT}_{Filenames.DRAINAGE}_{Filenames.ROAD}.pickle")
    substructure_drainage_infos = load_from_pickle(DIR / f"{Filenames.INPUT}_{Filenames.DRAINAGE}_{Filenames.SUBSTRUCTURE}.pickle")

    DRAINAGE_GROUP_MAIN = "main"
    DRAINAGE_GROUP_ROAD = "road"
    DRAINAGE_GROUP_SUBSTRUCTURE = "substructure"

    drainage_info_dict = {}

    for group_name, drainage_infos in [
        (DRAINAGE_GROUP_MAIN, main_drainage_infos),
        (DRAINAGE_GROUP_ROAD, road_drainage_infos),
        (DRAINAGE_GROUP_SUBSTRUCTURE, substructure_drainage_infos),
    ]:
        for drainage_info in drainage_infos:
            key = (
                group_name,
                drainage_info.bridge_name,
                drainage_info.drainage_name,
            )
            drainage_info_dict[key] = drainage_info
        

    world_items_dict_for_bake = {}
    world_items_dict_for_bake_2 = {}

    for (group_name, bridge_name, drain_name), indiv_info in drainage_info_dict.items():
        name = f"{group_name}_{bridge_name}_{drain_name}"
        drain_dict = const_indiv_drains(
            polyline_dict = poliline_dict,
            drainage_info = indiv_info,
        )
        world_items_dict_for_bake[name] = drain_dict
    
    def get_keys_and_values_for_bake(world_items_dict):
        flatten_dict_for_bake = flatten_any(world_items_dict)
        items = list(flatten_dict_for_bake.items())
        # valueがNoneのものはbakeできないので除外
        items = [(k,v) for k,v in items if v is not None]
        keys = [k for k, _ in items]
        values = [v for _, v in items]
        return keys, values
    return get_keys_and_values_for_bake(world_items_dict_for_bake)

if __name__ == "__main__":
    (bake_keys, bake_objs) = main("initial")