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
from my_project.utils.geometry.points import get_distance_2D, get_point_by_xy_offset
from my_project.utils.geometry_gh.attributes import (
    get_distance_along_crv,
    get_point_on_crv_at_distance,
)
from my_project.utils.geometry_gh.const import (
    const_3Dpoint,
    const_pipe_brep_from_curve,
    const_point_obj,
    const_polycurve_obj,
    const_rectangular_pipe_brep_from_curve,
)
from my_project.utils.geometry_gh.intersect import (
    get_intersect_point_on_crv_and_points_in_the_same_plane,
)
from my_project.utils.io import load_from_pickle

DISTANCE_TOL = 0.01


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
                "points_2D": points_2D,
            }
    return polyline_2D_dict


def interpolate_value(v0: float, v1: float, ratio: float) -> float:
    return v0 + ratio * (v1 - v0)


def get_distances_between(d0: float, d1: float, base_distances: list[float]) -> list[float]:
    if abs(d0 - d1) <= DISTANCE_TOL:
        return []
    d_min = min(d0, d1)
    d_max = max(d0, d1)
    distances = [
        d for d in base_distances
        if d_min + DISTANCE_TOL < d < d_max - DISTANCE_TOL
    ]
    distances = sorted(distances)
    unique_distances = []
    for distance in distances:
        if not unique_distances or abs(distance - unique_distances[-1]) > DISTANCE_TOL:
            unique_distances.append(distance)
    distances = unique_distances
    if d1 < d0:
        distances = distances[::-1]
    return distances


def insert_base_polyline_points(
    polyline_dict: dict[tuple[str, str], dict[str, Union[rg.PolylineCurve, list[rg.Point3d], list[str], list[float]]]],
    bridge_name: str,
    drainage_name: str,
    y_distances: list[tuple[str, float]],
    zs: list[float],
    x_base_polylines: list[str],
    x_zero_base_polylines: list[str],
    x_offsets: list[float],
    pipe_infos: list,
):
    new_y_distances = []
    new_zs = []
    new_x_base_polylines = []
    new_x_zero_base_polylines = []
    new_x_offsets = []
    new_pipe_infos = []
    old_idx_to_new_idx = {}

    def append_existing_point(idx: int) -> None:
        if idx in old_idx_to_new_idx:
            return
        old_idx_to_new_idx[idx] = len(new_y_distances)
        new_y_distances.append(y_distances[idx])
        new_zs.append(zs[idx])
        new_x_base_polylines.append(x_base_polylines[idx])
        new_x_zero_base_polylines.append(x_zero_base_polylines[idx])
        new_x_offsets.append(x_offsets[idx])

    def append_intermediate_points(idx0: int, idx1: int, pipe_name: str) -> None:
        y_base_polyline0, d0 = y_distances[idx0]
        y_base_polyline1, d1 = y_distances[idx1]
        if y_base_polyline0 != y_base_polyline1:
            return

        x_base_polyline0 = x_base_polylines[idx0]
        x_base_polyline1 = x_base_polylines[idx1]
        if x_base_polyline0 != x_base_polyline1:
            return
        x_zero_base_polyline0 = x_zero_base_polylines[idx0]
        x_zero_base_polyline1 = x_zero_base_polylines[idx1]
        if x_zero_base_polyline0 != x_zero_base_polyline1:
            return

        base_distances = polyline_dict[(bridge_name, y_base_polyline0)]["distances"]
        for distance in get_distances_between(d0, d1, base_distances):
            if any(
                y_base == y_base_polyline0 and abs(existing_distance - distance) <= DISTANCE_TOL
                for y_base, existing_distance in new_y_distances
            ):
                continue
            ratio = (distance - d0) / (d1 - d0)
            new_y_distances.append((y_base_polyline0, distance))
            new_zs.append(interpolate_value(zs[idx0], zs[idx1], ratio))
            new_x_base_polylines.append(x_base_polyline0)
            new_x_zero_base_polylines.append(x_zero_base_polyline0)
            new_x_offsets.append(interpolate_value(x_offsets[idx0], x_offsets[idx1], ratio))

    for start_idx, end_idx, pipe_spec in pipe_infos:
        start_idx = int(start_idx)
        end_idx = int(end_idx)
        append_existing_point(start_idx)
        new_start_idx = old_idx_to_new_idx[start_idx]
        for idx in range(start_idx, end_idx):
            append_intermediate_points(idx, idx + 1, pipe_spec.name)
            append_existing_point(idx + 1)
        new_end_idx = old_idx_to_new_idx[end_idx]
        new_pipe_infos.append((new_start_idx, new_end_idx, pipe_spec))

    return new_y_distances, new_zs, new_x_base_polylines, new_x_zero_base_polylines, new_x_offsets, new_pipe_infos


def get_intersect_point_on_transverse_line(
    polyline_dict,
    bridge_name: str,
    polyline_name: str,
    y_point_2D,
    CL_point_2D,
):
    if (bridge_name, polyline_name) not in polyline_dict:
        raise ValueError(f"Bridge {bridge_name} does not have polyline {polyline_name} in point_infos.")
    crv = polyline_dict[(bridge_name, polyline_name)]["polyline_2D"]
    return get_intersect_point_on_crv_and_points_in_the_same_plane(
        target_crv=crv,
        cutter_points=[y_point_2D, CL_point_2D],
    )


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
    x_zero_base_polylines = []
    x_offsets = []
    unknown_y_idxs = []
    unknown_x_idxs = []
    for i, p in enumerate(points):
        y_base_polyline = p.y_base_polyline
        y_base_CG_name = p.y_base_CG_name
        y_offset = p.y_offset
        y_adj_ratio = p.y_adj_ratio
        x_base_polyline = p.x_base_polyline
        x_zero_base_polyline = getattr(p, "x_zero_base_polyline", None)
        if x_zero_base_polyline is None:
            x_zero_base_polyline = x_base_polyline
        x_offset = p.x_offset
        z = p.z
        if (bridge_name, y_base_polyline) not in polyline_dict:
            raise ValueError(f"Bridge {bridge_name} does not have polyline {y_base_polyline} in point_infos.")
        y_base_polylines.append(y_base_polyline)
        x_base_polylines.append(x_base_polyline)
        x_zero_base_polylines.append(x_zero_base_polyline)
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
            unknown_y_idxs.append((i, y_adj_ratio))
        else:
            raise ValueError(f"Invalid y_offset value: {y_offset}")

        if x_offset == "adjustment":
            unknown_x_idxs.append((i, y_adj_ratio))

    if len(unknown_y_idxs) > 0:
        for idx, adj_ratio in unknown_y_idxs:
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

    if len(unknown_x_idxs) > 0:
        for idx, adj_ratio in unknown_x_idxs:
            prev_idx = None
            for j in range(idx - 1, -1, -1):
                if isinstance(x_offsets[j], Number):
                    prev_idx = j
                    break
            next_idx = None
            for j in range(idx + 1, len(x_offsets)):
                if isinstance(x_offsets[j], Number):
                    next_idx = j
                    break
            if prev_idx is None or next_idx is None:
                raise ValueError(
                    f"Cannot adjust x_offset at index {idx}: "
                    f"previous={prev_idx}, next={next_idx}"
                )
            prev_x_base_polyline = x_base_polylines[prev_idx]
            next_x_base_polyline = x_base_polylines[next_idx]
            if prev_x_base_polyline != next_x_base_polyline:
                raise ValueError(
                    f"Cannot adjust x_offset at index {idx} because previous and next polylines are different: "
                    f"previous={prev_x_base_polyline}, next={next_x_base_polyline}"
                )
            prev_x_offset = x_offsets[prev_idx]
            next_x_offset = x_offsets[next_idx]
            x_offsets[idx] = prev_x_offset + adj_ratio * (next_x_offset - prev_x_offset)
            x_base_polylines[idx] = prev_x_base_polyline
            x_zero_base_polylines[idx] = x_zero_base_polylines[prev_idx]

    CL_polyline = polyline_dict[(bridge_name, "CL")]["polyline_2D"]

    def get_regular_world_point(i: int):
        y_base_polyline, y_distance = y_distances[i]
        x_base_polyline = x_base_polylines[i]
        x_zero_base_polyline = x_zero_base_polylines[i]
        y_base_crv = polyline_dict[(bridge_name, y_base_polyline)]["polyline_2D"]
        y_point_2D = get_point_on_crv_at_distance(y_base_crv, y_distance)
        CL_point_t = CL_polyline.ClosestPoint(y_point_2D)[1]
        CL_point_2D = CL_polyline.PointAt(CL_point_t)
        zero_base_point_2D = get_intersect_point_on_transverse_line(
            polyline_dict,
            bridge_name,
            x_zero_base_polyline,
            y_point_2D,
            CL_point_2D,
        )
        zero_base_point_2D = const_3Dpoint(zero_base_point_2D)
        CL_point_2D = const_3Dpoint(CL_point_2D)
        if x_zero_base_polyline == x_base_polyline:
            direction_point_2D = CL_point_2D
        else:
            x_base_point_2D = get_intersect_point_on_transverse_line(
                polyline_dict,
                bridge_name,
                x_base_polyline,
                y_point_2D,
                CL_point_2D,
            )
            x_base_point_2D = const_3Dpoint(x_base_point_2D)
            direction_point_2D = Point3D(
                x=zero_base_point_2D.x + (zero_base_point_2D.x - x_base_point_2D.x),
                y=zero_base_point_2D.y + (zero_base_point_2D.y - x_base_point_2D.y),
                z=zero_base_point_2D.z,
            )
        try:
            point_2D = get_point_by_xy_offset(
                point1=zero_base_point_2D,
                point2=direction_point_2D,
                offset=x_offsets[i],
            )
        except ValueError as e:
            if get_distance_2D(zero_base_point_2D, direction_point_2D) <= DISTANCE_TOL and abs(float(x_offsets[i])) <= DISTANCE_TOL:
                point_2D = zero_base_point_2D
            else:
                raise ValueError(
                    "[FAILED WORLD POINT] "
                    f"{bridge_name}/{drainage_info.drainage_name}: "
                    f"idx={i}, y_base={y_base_polyline}, y_distance={y_distance}, "
                    f"x_base={x_base_polyline}, x_zero_base={x_zero_base_polyline}, "
                    f"x_offset={x_offsets[i]}, z={zs[i]}, "
                    f"zero_base_point=({zero_base_point_2D.x}, {zero_base_point_2D.y}), "
                    f"direction_point=({direction_point_2D.x}, {direction_point_2D.y})"
                ) from e
        return const_point_obj(Point3D(point_2D.x, point_2D.y, zs[i]))

    if getattr(drainage_info, "is_connection", False):
        start_world_point = const_3Dpoint(get_regular_world_point(0))
        end_world_point = const_3Dpoint(get_regular_world_point(len(y_distances) - 1))
        start_x_base = x_base_polylines[0]
        end_x_base = x_base_polylines[-1]
        start_x_offset = float(x_offsets[0])
        end_x_offset = float(x_offsets[-1])
        world_points = []
        for i in range(len(y_distances)):
            if i == 0:
                point = start_world_point
            elif i == len(y_distances) - 1:
                point = end_world_point
            elif x_base_polylines[i] == start_x_base:
                offset = float(x_offsets[i]) - start_x_offset
                point = get_point_by_xy_offset(start_world_point, end_world_point, offset)
            elif x_base_polylines[i] == end_x_base:
                offset = end_x_offset - float(x_offsets[i])
                point = get_point_by_xy_offset(end_world_point, start_world_point, offset)
            else:
                point = const_3Dpoint(get_regular_world_point(i))
            world_points.append(const_point_obj(Point3D(point.x, point.y, zs[i])))
        return world_points, drainage_info.pipes

    y_distances, zs, x_base_polylines, x_zero_base_polylines, x_offsets, pipe_infos = insert_base_polyline_points(
        polyline_dict=polyline_dict,
        bridge_name=bridge_name,
        drainage_name=drainage_info.drainage_name,
        y_distances=y_distances,
        zs=zs,
        x_base_polylines=x_base_polylines,
        x_zero_base_polylines=x_zero_base_polylines,
        x_offsets=x_offsets,
        pipe_infos=drainage_info.pipes,
    )
    
    world_points = []
    for i, (y_base_polyline, y_distance) in enumerate(y_distances):
        x_base_polyline = x_base_polylines[i]
        x_zero_base_polyline = x_zero_base_polylines[i]
        y_base_crv = polyline_dict[(bridge_name, y_base_polyline)]["polyline_2D"]
        y_point_2D = get_point_on_crv_at_distance(y_base_crv, y_distance)
        CL_point_t = CL_polyline.ClosestPoint(y_point_2D)[1]
        CL_point_2D = CL_polyline.PointAt(CL_point_t)
        zero_base_point_2D = get_intersect_point_on_transverse_line(
            polyline_dict,
            bridge_name,
            x_zero_base_polyline,
            y_point_2D,
            CL_point_2D,
        )
        zero_base_point_2D = const_3Dpoint(zero_base_point_2D)
        CL_point_2D = const_3Dpoint(CL_point_2D)
        if x_zero_base_polyline == x_base_polyline:
            direction_point_2D = CL_point_2D
        else:
            x_base_point_2D = get_intersect_point_on_transverse_line(
                polyline_dict,
                bridge_name,
                x_base_polyline,
                y_point_2D,
                CL_point_2D,
            )
            x_base_point_2D = const_3Dpoint(x_base_point_2D)
            direction_point_2D = Point3D(
                x=zero_base_point_2D.x + (zero_base_point_2D.x - x_base_point_2D.x),
                y=zero_base_point_2D.y + (zero_base_point_2D.y - x_base_point_2D.y),
                z=zero_base_point_2D.z,
            )
        try:
            point_2D = get_point_by_xy_offset(
                point1 = zero_base_point_2D,
                point2 = direction_point_2D,
                offset = x_offsets[i],
            )
        except ValueError as e:
            if get_distance_2D(zero_base_point_2D, direction_point_2D) <= DISTANCE_TOL and abs(float(x_offsets[i])) <= DISTANCE_TOL:
                print(
                    "[SKIP ZERO OFFSET DIRECTION] "
                    f"{bridge_name}/{drainage_info.drainage_name}: "
                    f"idx={i}, y_base={y_base_polyline}, y_distance={y_distance}, "
                    f"x_base={x_base_polyline}, x_zero_base={x_zero_base_polyline}, "
                    f"x_offset={x_offsets[i]}, z={zs[i]}"
                )
                point_2D = zero_base_point_2D
            else:
                raise ValueError(
                    "[FAILED WORLD POINT] "
                    f"{bridge_name}/{drainage_info.drainage_name}: "
                    f"idx={i}, y_base={y_base_polyline}, y_distance={y_distance}, "
                    f"x_base={x_base_polyline}, x_zero_base={x_zero_base_polyline}, "
                    f"x_offset={x_offsets[i]}, z={zs[i]}, "
                    f"zero_base_point=({zero_base_point_2D.x}, {zero_base_point_2D.y}), "
                    f"direction_point=({direction_point_2D.x}, {direction_point_2D.y})"
                ) from e
        point = const_point_obj(Point3D(point_2D.x, point_2D.y, zs[i]))
        world_points.append(point)
    return world_points, pipe_infos

def const_indiv_drains(
    polyline_dict: dict[tuple[str, str], dict[str, Union[rg.PolylineCurve, list[rg.Point3d], list[str], list[float]]]],
    drainage_info: DrainageInfo,
):
    world_points, pipe_infos = get_world_points(polyline_dict, drainage_info)
    pipe_brep_dict = {}
    for pipe_idx, pipe_info in enumerate(pipe_infos):
        pipe_name = pipe_info[2].name
        pipe_key = f"{pipe_idx:03d}_{pipe_name}"
        start_idx, end_idx, pipe_spec = pipe_info
        pipe_points = world_points[start_idx:end_idx + 1]
        try:
            pipe_crv = const_polycurve_obj(pipe_points)
        except ValueError as e:
            point_text = [
                f"{i + start_idx}: ({p.X}, {p.Y}, {p.Z})"
                for i, p in enumerate(pipe_points)
            ]
            print(
                "[INVALID DRAIN PIPE] "
                f"{drainage_info.bridge_name}/{drainage_info.drainage_name}/{pipe_name}: "
                f"start_idx={start_idx}, end_idx={end_idx}, points={point_text}, error={e}"
            )
            pipe_brep_dict[pipe_key] = None
            continue
        try:
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
        except Exception as e:
            point_text = [
                f"{i + start_idx}: ({p.X}, {p.Y}, {p.Z})"
                for i, p in enumerate(pipe_points)
            ]
            print(
                "[FAILED DRAIN PIPE] "
                f"{drainage_info.bridge_name}/{drainage_info.drainage_name}/{pipe_name}: "
                f"start_idx={start_idx}, end_idx={end_idx}, spec={pipe_spec}, "
                f"points={point_text}, error={type(e).__name__}: {e}"
            )
            pipe_brep_dict[pipe_key] = None
            continue
        pipe_brep_dict[pipe_key] = pipe_brep
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
        for drainage_info in drainage_infos.values():
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
