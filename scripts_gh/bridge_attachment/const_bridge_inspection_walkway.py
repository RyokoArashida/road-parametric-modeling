# ruff: noqa: E402
import math
from typing import Union

from my_project.config.file_names import Filenames
from my_project.config.locale_compat import normalize_lc_time
from my_project.config.paths import get_output_dir
from my_project.config.schemas.bridge_inspection_walkway_schemas import (
    MainInfo,
)
from my_project.config.util_schemas import (
    Point2D,
    Point3D,
    Vector2D,
)
from my_project.utils.dataframe import flatten_any
from my_project.utils.geometry.points import get_point_by_xy_offset
from my_project.utils.geometry_gh.attributes import (
    get_distance_along_crv,
    get_point_on_crv_at_distance,
)
from my_project.utils.geometry_gh.const import (
    const_3Dpoint,
    const_brep_from_point_lists,
    const_point_obj,
    const_polycurve_obj,
    const_srf_from_2crvs,
    const_z_extruded_box_from_4points,
)
from my_project.utils.geometry_gh.intersect import get_closest_point_on_srf_with_point
from my_project.utils.io import load_from_pickle

normalize_lc_time()

DISTANCE_TOL = 0.01

def get_closest_point_on_nearest_srf(surfs, point: Union[Point2D, Point3D]):
    point_3D = const_3Dpoint(point)
    candidates = []
    for srf in surfs:
        try:
            srf_point = get_closest_point_on_srf_with_point(srf, point_3D)
        except Exception as e:
            print(f"Error finding closest point on surface: {e}")
            continue
        distance = math.hypot(srf_point.x - point_3D.x, srf_point.y - point_3D.y)
        candidates.append((distance, srf_point))
    if not candidates:
        raise ValueError(f"No closest point found on any slab top surface. point: {point_3D}")
    return min(candidates, key=lambda item: item[0])[1]

def get_direction_point_from_base_to_cl(
    center_point: Union[Point2D, Point3D],
    direction_base_point: Union[Point2D, Point3D],
    cl_point: Union[Point2D, Point3D],
) -> Point3D:
    center = const_3Dpoint(center_point)
    base = const_3Dpoint(direction_base_point)
    cl = const_3Dpoint(cl_point)
    dx = cl.x - base.x
    dy = cl.y - base.y
    length = math.hypot(dx, dy)
    if length == 0:
        raise ValueError("direction_base_point and cl_point have the same XY coordinates")
    return Point3D(
        x=center.x + dx / length,
        y=center.y + dy / length,
        z=center.z,
    )

def get_slab_top_surface_dict(
    slab_top_points_UP,
    slab_top_points_DOWN,
):
    slab_top_surface_dict = {}
    for unique_slab_name, UP_dict in slab_top_points_UP.items():
        DOWN_dict = slab_top_points_DOWN[unique_slab_name]
        bridge_name = unique_slab_name.split("_")[0]
        if bridge_name not in slab_top_surface_dict:
            slab_top_surface_dict[bridge_name] = []
        UP_points = []
        DOWN_points = []
        for CG_name, UP_point in UP_dict.items():
            DOWN_point = DOWN_dict[CG_name]
            UP_points.append(UP_point)
            DOWN_points.append(DOWN_point)
        UP_polyline = const_polycurve_obj(UP_points)
        DOWN_polyline = const_polycurve_obj(DOWN_points)
        srf = const_srf_from_2crvs([UP_polyline, DOWN_polyline])
        slab_top_surface_dict[bridge_name].append(srf)
    return slab_top_surface_dict

def get_polylines_2D(
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
                "points_2D": points_2D,
            }
    return polyline_2D_dict

def get_route_brep_points(
    bottom_center_points_3D: Point3D,
    center_points_2D: Point3D,
    direction_base_point_2D: Point3D,
    CL_point_2D: Point3D,
    width: float,
    height: float,
    thickness: float,
):
    bottom_z = bottom_center_points_3D.z
    floor_top_z = bottom_z + thickness
    top_z = bottom_z + height
    plus_direction_2D = get_direction_point_from_base_to_cl(
        center_point = center_points_2D,
        direction_base_point = direction_base_point_2D,
        cl_point = CL_point_2D,
    )
    outer_edge_plus_2D = get_point_by_xy_offset(
        point1 = center_points_2D,
        point2 = plus_direction_2D,
        offset = width / 2,
    )
    outer_edge_minus_2D = get_point_by_xy_offset(
        point1 = center_points_2D,
        point2 = plus_direction_2D,
        offset = -width / 2,
    )
    inner_edge_plus_2D = get_point_by_xy_offset(
        point1 = center_points_2D,
        point2 = plus_direction_2D,
        offset = width / 2 - thickness,
    )
    inner_edge_minus_2D = get_point_by_xy_offset(
        point1 = center_points_2D,
        point2 = plus_direction_2D,
        offset = -width / 2 + thickness,
    )
    floor_points = (
        const_3Dpoint(Point3D(outer_edge_plus_2D.x, outer_edge_plus_2D.y, bottom_z)),
        const_3Dpoint(Point3D(outer_edge_minus_2D.x, outer_edge_minus_2D.y, bottom_z)),
        const_3Dpoint(Point3D(outer_edge_minus_2D.x, outer_edge_minus_2D.y, floor_top_z)),
        const_3Dpoint(Point3D(outer_edge_plus_2D.x, outer_edge_plus_2D.y, floor_top_z)),
    )
    plus_fence_points = (
        const_3Dpoint(Point3D(outer_edge_plus_2D.x, outer_edge_plus_2D.y, floor_top_z)),
        const_3Dpoint(Point3D(outer_edge_plus_2D.x, outer_edge_plus_2D.y, top_z)),
        const_3Dpoint(Point3D(inner_edge_plus_2D.x, inner_edge_plus_2D.y, top_z)),
        const_3Dpoint(Point3D(inner_edge_plus_2D.x, inner_edge_plus_2D.y, floor_top_z)),
    )
    minus_fence_points = (
        const_3Dpoint(Point3D(outer_edge_minus_2D.x, outer_edge_minus_2D.y, floor_top_z)),
        const_3Dpoint(Point3D(outer_edge_minus_2D.x, outer_edge_minus_2D.y, top_z)),
        const_3Dpoint(Point3D(inner_edge_minus_2D.x, inner_edge_minus_2D.y, top_z)),
        const_3Dpoint(Point3D(inner_edge_minus_2D.x, inner_edge_minus_2D.y, floor_top_z)),
    )
    return floor_points, plus_fence_points, minus_fence_points

def get_crossing_brep_points(
    edge_point_2D: Point3D,
    next_point_2D: Point3D,
    edge_minus_point_2D: Point3D,
    crossing_z: float,
    length: float,
    width: float,
    height: float,
    thickness: float,
):
    bottom_z = crossing_z
    floor_top_z = crossing_z + thickness
    main_outer_outer_point = edge_point_2D
    main_outer_inner_point = get_point_by_xy_offset(
        point1 = edge_point_2D,
        point2 = next_point_2D,
        offset = thickness,
    )
    main_inner_inner_point = get_point_by_xy_offset(
        point1 = edge_point_2D,
        point2 = next_point_2D,
        offset = width - thickness,
    )
    main_inner_outer_point = get_point_by_xy_offset(
        point1 = edge_point_2D,
        point2 = next_point_2D,
        offset = width,
    )
    edge_outer_outer_point = get_point_by_xy_offset(
        point1 = main_outer_outer_point,
        point2 = edge_minus_point_2D,
        offset = -length
    )
    vector_from_edge_to_main = Vector2D(
        x = edge_outer_outer_point.x - main_outer_outer_point.x,
        y = edge_outer_outer_point.y - main_outer_outer_point.y
    )
    edge_outer_inner_point = Point2D(
        x = main_outer_inner_point.x + vector_from_edge_to_main.x,
        y = main_outer_inner_point.y + vector_from_edge_to_main.y,
    )
    edge_inner_inner_point = Point2D(
        x = main_inner_inner_point.x + vector_from_edge_to_main.x,
        y = main_inner_inner_point.y + vector_from_edge_to_main.y,
    )
    edge_inner_outer_point = Point2D(
        x = main_inner_outer_point.x + vector_from_edge_to_main.x,
        y = main_inner_outer_point.y + vector_from_edge_to_main.y,
    )
    floor_bottom_points = (
        const_3Dpoint(Point3D(main_outer_outer_point.x, main_outer_outer_point.y, bottom_z)),
        const_3Dpoint(Point3D(main_inner_outer_point.x, main_inner_outer_point.y, bottom_z)),
        const_3Dpoint(Point3D(edge_inner_outer_point.x, edge_inner_outer_point.y, bottom_z)),
        const_3Dpoint(Point3D(edge_outer_outer_point.x, edge_outer_outer_point.y, bottom_z)),
    )
    floor_brep = const_z_extruded_box_from_4points(floor_bottom_points, thickness)
    outer_fence_bottom_points = (
        const_3Dpoint(Point3D(main_outer_outer_point.x, main_outer_outer_point.y, floor_top_z)),
        const_3Dpoint(Point3D(main_outer_inner_point.x, main_outer_inner_point.y, floor_top_z)),
        const_3Dpoint(Point3D(edge_outer_inner_point.x, edge_outer_inner_point.y, floor_top_z)),
        const_3Dpoint(Point3D(edge_outer_outer_point.x, edge_outer_outer_point.y, floor_top_z)),
    )
    outer_fence_brep = const_z_extruded_box_from_4points(outer_fence_bottom_points, height - thickness)
    inner_fence_bottom_points = (
        const_3Dpoint(Point3D(main_inner_inner_point.x, main_inner_inner_point.y, floor_top_z)),
        const_3Dpoint(Point3D(main_inner_outer_point.x, main_inner_outer_point.y, floor_top_z)),
        const_3Dpoint(Point3D(edge_inner_outer_point.x, edge_inner_outer_point.y, floor_top_z)),
        const_3Dpoint(Point3D(edge_inner_inner_point.x, edge_inner_inner_point.y, floor_top_z)),
    )
    inner_fence_brep = const_z_extruded_box_from_4points(inner_fence_bottom_points, height - thickness)
    return floor_brep, outer_fence_brep, inner_fence_brep

def get_brep_from_4point_lists(points: list[tuple[Point3D, Point3D, Point3D, Point3D]]):
    return const_brep_from_point_lists(points)

def is_minus_side(side: str) -> bool:
    return str(side).strip().lower() == "minus"

def move_section_points_along_route(
    points: tuple[Point3D, Point3D, Point3D, Point3D],
    direction_start: Point3D,
    direction_end: Point3D,
    distance: float,
) -> tuple[Point3D, Point3D, Point3D, Point3D]:
    moved_points = []
    for point in points:
        direction_point = Point3D(
            x=point.x + direction_end.x - direction_start.x,
            y=point.y + direction_end.y - direction_start.y,
            z=point.z,
        )
        moved_point = get_point_by_xy_offset(
            point1=point,
            point2=direction_point,
            offset=distance,
        )
        moved_points.append(Point3D(moved_point.x, moved_point.y, point.z))
    return tuple(moved_points)

def get_main_end_closure_brep(
    floor_points: tuple[Point3D, Point3D, Point3D, Point3D],
    height: float,
    thickness: float,
    direction_start: Point3D,
    direction_end: Point3D,
):
    top_z = floor_points[0].z + height
    end_section = (
        floor_points[3],
        Point3D(floor_points[3].x, floor_points[3].y, top_z),
        Point3D(floor_points[2].x, floor_points[2].y, top_z),
        floor_points[2],
    )
    inner_section = move_section_points_along_route(
        points=end_section,
        direction_start=direction_start,
        direction_end=direction_end,
        distance=thickness,
    )
    return get_brep_from_4point_lists([end_section, inner_section])

def get_crossing_base_points(
    floor_points: tuple[Point3D, Point3D, Point3D, Point3D],
    adjacent_floor_points: tuple[Point3D, Point3D, Point3D, Point3D],
    side: str,
) -> tuple[Point3D, Point3D, Point3D]:
    if is_minus_side(side):
        return floor_points[1], adjacent_floor_points[1], floor_points[0]
    return floor_points[0], adjacent_floor_points[0], floor_points[1]

def const_indiv_route(
    polyline_dict,
    slab_top_srfs,
    route_info: MainInfo,
):
    bridge_name = route_info.bridge_name
    size = route_info.size_info
    width = size.width
    height = size.height
    thickness = size.thickness
    base_MG_name = route_info.base_MG
    base_MG_polyline_info = polyline_dict[(bridge_name, base_MG_name)]
    CL_polyline = polyline_dict[(bridge_name, "CL")]["polyline_2D"]
    y_points_2D = []
    
    start_point_CG_name = route_info.start_point.y_base_CG
    start_point_CG_idx = base_MG_polyline_info["point_names"].index(start_point_CG_name)
    start_point_CG_distance = base_MG_polyline_info["distances"][start_point_CG_idx]
    start_point_offset = route_info.start_point.y_offset
    start_point_distance = start_point_CG_distance + start_point_offset
    if start_point_offset == 0.0:
        start_point_2D = const_3Dpoint(base_MG_polyline_info["points_2D"][start_point_CG_idx])
    else:
        start_point_2D = const_3Dpoint(get_point_on_crv_at_distance(base_MG_polyline_info["polyline_2D"], start_point_distance))
    end_point_CG_name = route_info.end_point.y_base_CG
    end_point_CG_idx = base_MG_polyline_info["point_names"].index(end_point_CG_name)
    end_point_CG_distance = base_MG_polyline_info["distances"][end_point_CG_idx]
    end_point_offset = route_info.end_point.y_offset
    end_point_distance = end_point_CG_distance + end_point_offset
    if end_point_offset == 0.0:
        end_point_2D = const_3Dpoint(base_MG_polyline_info["points_2D"][end_point_CG_idx])
    else:
        end_point_2D = const_3Dpoint(get_point_on_crv_at_distance(base_MG_polyline_info["polyline_2D"], end_point_distance))

    distance_gap = end_point_distance - start_point_distance
    start_offset_x = route_info.start_point.x_offset
    end_offset_x = route_info.end_point.x_offset
    offset_x_gap = end_offset_x - start_offset_x
    start_offset_z = route_info.start_point.z_offset
    end_offset_z = route_info.end_point.z_offset
    offset_z_gap = end_offset_z - start_offset_z

    # s_distanceとe_distanceの間の点をdistancesから取得する
    y_points_2D = [start_point_2D]
    offset_x = [start_offset_x]
    offset_z = [start_offset_z]
    for distance, center_point_2D in zip(base_MG_polyline_info["distances"], base_MG_polyline_info["points_2D"]):
        if start_point_distance < distance < end_point_distance:
            y_points_2D.append(Point2D(center_point_2D.X, center_point_2D.Y))
            if offset_x_gap != 0:
                offset_x_at_point = start_offset_x + offset_x_gap * (distance - start_point_distance) / distance_gap
            else:
                offset_x_at_point = start_offset_x
            offset_x.append(offset_x_at_point)
            if offset_z_gap != 0:
                offset_z_at_point = start_offset_z + offset_z_gap * (distance - start_point_distance) / distance_gap
            else:
                offset_z_at_point = start_offset_z
            offset_z.append(offset_z_at_point)
    y_points_2D.append(end_point_2D)
    offset_x.append(end_offset_x)
    offset_z.append(end_offset_z)

    floor_points_list = []
    fence_plus_points_list = []
    fence_minus_points_list = []
    for y_point_2D, offset_x, offset_z in zip(y_points_2D, offset_x, offset_z):
        CL_point_t = CL_polyline.ClosestPoint(const_point_obj(y_point_2D))[1]
        CL_point_2D = CL_polyline.PointAt(CL_point_t)
        CL_point_2D = const_3Dpoint(Point2D(CL_point_2D.X, CL_point_2D.Y))
        center_point_2D = get_point_by_xy_offset(
            point1 = y_point_2D,
            point2 = CL_point_2D,
            offset = offset_x,
        )
        intersect_point = get_closest_point_on_nearest_srf(slab_top_srfs, center_point_2D)
        bottom_center_point_3D = const_3Dpoint(
            Point3D(
                x = intersect_point.x,
                y = intersect_point.y,
                z = intersect_point.z - offset_z,
            )
        )
        floor_points, plus_fence_points, minus_fence_points = get_route_brep_points(
            bottom_center_points_3D = bottom_center_point_3D,
            center_points_2D = center_point_2D,
            direction_base_point_2D = y_point_2D,
            CL_point_2D = CL_point_2D,
            width = width,
            height = height,
            thickness = thickness,
        )
        floor_points_list.append(floor_points)
        fence_plus_points_list.append(plus_fence_points)
        fence_minus_points_list.append(minus_fence_points)

    start_crossing_info = route_info.start_crossing
    end_crossing_info = route_info.end_crossing
    start_main_end_closure = None
    end_main_end_closure = None
    if start_crossing_info is not None and len(fence_plus_points_list) >= 2:
        start_fence_points_list = fence_minus_points_list if is_minus_side(start_crossing_info.side) else fence_plus_points_list
        start_fence_points_list[0] = move_section_points_along_route(
            points=start_fence_points_list[0],
            direction_start=floor_points_list[0][0],
            direction_end=floor_points_list[1][0],
            distance=start_crossing_info.size_info.width,
        )
        start_main_end_closure = get_main_end_closure_brep(
            floor_points=floor_points_list[0],
            height=height,
            thickness=thickness,
            direction_start=floor_points_list[0][0],
            direction_end=floor_points_list[1][0],
        )
    if end_crossing_info is not None and len(fence_plus_points_list) >= 2:
        end_fence_points_list = fence_minus_points_list if is_minus_side(end_crossing_info.side) else fence_plus_points_list
        end_fence_points_list[-1] = move_section_points_along_route(
            points=end_fence_points_list[-1],
            direction_start=floor_points_list[-1][0],
            direction_end=floor_points_list[-2][0],
            distance=end_crossing_info.size_info.width,
        )
        end_main_end_closure = get_main_end_closure_brep(
            floor_points=floor_points_list[-1],
            height=height,
            thickness=thickness,
            direction_start=floor_points_list[-1][0],
            direction_end=floor_points_list[-2][0],
        )

    floor_brep = get_brep_from_4point_lists(floor_points_list)
    plus_fence_brep = get_brep_from_4point_lists(fence_plus_points_list)
    minus_fence_brep = get_brep_from_4point_lists(fence_minus_points_list)

    # 横行
    if start_crossing_info is not None:
        size = start_crossing_info.size_info
        width = size.width
        height = size.height
        thickness = size.thickness
        length = start_crossing_info.length
        height_offset = start_crossing_info.height_offset
        start_edge_point, next_point, start_opposite_point = get_crossing_base_points(
            floor_points=floor_points_list[0],
            adjacent_floor_points=floor_points_list[1],
            side=start_crossing_info.side,
        )
        start_edge_point_2D = const_3Dpoint(Point2D(start_edge_point.x, start_edge_point.y))
        next_point_2D = const_3Dpoint(Point2D(next_point.x, next_point.y))
        start_opposite_point_2D = const_3Dpoint(Point2D(start_opposite_point.x, start_opposite_point.y))
        intersect_point = get_closest_point_on_nearest_srf(slab_top_srfs, start_edge_point_2D)
        crossing_height = intersect_point.z - height_offset
        s_crossing_floor_brep, s_crossing_outer_fence_brep, s_crossing_inner_fence_brep = get_crossing_brep_points(
            edge_point_2D = start_edge_point_2D,
            next_point_2D = next_point_2D,
            edge_minus_point_2D = start_opposite_point_2D,
            crossing_z = crossing_height,
            length = length,
            width = width,
            height = height,
            thickness = thickness,
        )
    else:
        s_crossing_floor_brep = None
        s_crossing_outer_fence_brep = None
        s_crossing_inner_fence_brep = None
    if end_crossing_info is not None:
        size = end_crossing_info.size_info
        width = size.width
        height = size.height
        thickness = size.thickness
        length = end_crossing_info.length
        height_offset = end_crossing_info.height_offset
        end_edge_point, prev_point, end_opposite_point = get_crossing_base_points(
            floor_points=floor_points_list[-1],
            adjacent_floor_points=floor_points_list[-2],
            side=end_crossing_info.side,
        )
        end_edge_point_2D = const_3Dpoint(Point2D(end_edge_point.x, end_edge_point.y))
        prev_point_2D = const_3Dpoint(Point2D(prev_point.x, prev_point.y))
        end_opposite_point_2D = const_3Dpoint(Point2D(end_opposite_point.x, end_opposite_point.y))
        intersect_point = get_closest_point_on_nearest_srf(slab_top_srfs, end_edge_point_2D)
        crossing_height = intersect_point.z - height_offset
        e_crossing_floor_brep, e_crossing_outer_fence_brep, e_crossing_inner_fence_brep = get_crossing_brep_points(
            edge_point_2D = end_edge_point_2D,
            next_point_2D = prev_point_2D,
            edge_minus_point_2D = end_opposite_point_2D,
            crossing_z = crossing_height,
            length = length,
            width = width,
            height = height,
            thickness = thickness,
        )
    else:
        e_crossing_floor_brep = None
        e_crossing_outer_fence_brep = None
        e_crossing_inner_fence_brep = None
    return {
        "main_floor": floor_brep,
        "main_plus_fence": plus_fence_brep,
        "main_minus_fence": minus_fence_brep,
        "start_main_end_closure": start_main_end_closure,
        "end_main_end_closure": end_main_end_closure,
        "start_crossing_floor": s_crossing_floor_brep,
        "start_crossing_outer_fence": s_crossing_outer_fence_brep,
        "start_crossing_inner_fence": s_crossing_inner_fence_brep,
        "end_crossing_floor": e_crossing_floor_brep,
        "end_crossing_outer_fence": e_crossing_outer_fence_brep,
        "end_crossing_inner_fence": e_crossing_inner_fence_brep
    }


def main(initial_or_final: str, debug=False):
    DIR = get_output_dir(initial_or_final)

    slab_top_points_UP = load_from_pickle(DIR / f"{Filenames.WORLD}_{Filenames.SLAB}_{Filenames.UP}_{Filenames.TOP}_{Filenames.POINTS}.pickle")
    slab_top_points_DOWN = load_from_pickle(DIR / f"{Filenames.WORLD}_{Filenames.SLAB}_{Filenames.DOWN}_{Filenames.TOP}_{Filenames.POINTS}.pickle")
    slab_top_surface_dict = get_slab_top_surface_dict(
        slab_top_points_UP=slab_top_points_UP,
        slab_top_points_DOWN=slab_top_points_DOWN,
    )
    point_infos = load_from_pickle(DIR / f"{Filenames.INPUT}_{Filenames.INSPECTION_WALKWAY}_{Filenames.POINTS}.pickle")
    polyline_dict = get_polylines_2D(point_infos)

    main_route_infos = load_from_pickle(DIR / f"{Filenames.INPUT}_{Filenames.INSPECTION_WALKWAY}_{Filenames.MAIN}.pickle")

    world_items_dict_for_bake = {}
    world_items_dict_for_bake_2 = {}
    if debug:
        for key, slab_top_srfs in slab_top_surface_dict.items():
            for i, slab_top_srf in enumerate(slab_top_srfs):
                world_items_dict_for_bake[f"{key}_slab_top_{i}"] = slab_top_srf
    else:
        for route_info in main_route_infos.values():
            bridge_name = route_info.bridge_name
            route_name = route_info.route_name
            unique_slab_name = f"{bridge_name}_{route_name}"
            print(unique_slab_name)
            slab_top_srfs = slab_top_surface_dict[bridge_name]

            route_brep_dict = const_indiv_route(
                polyline_dict = polyline_dict,
                slab_top_srfs = slab_top_srfs,
                route_info = route_info,
            )
            world_items_dict_for_bake[unique_slab_name] = route_brep_dict


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
    # (bake_keys, bake_objs) = main("initial", debug=True)
