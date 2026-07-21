# ruff: noqa: E402
from __future__ import annotations

import re

import Rhino.Geometry as rg

from my_project.config.file_names import Filenames
from my_project.config.locale_compat import normalize_lc_time

normalize_lc_time()

import pandas as pd

from my_project.config.constants import DEFAULT_GEOMETRY_EXTENT, DISTANCE_TOL, STANDARD_BASE_Z
from my_project.config.paths import get_output_dir
from my_project.config.schemas.embankment_pavement_schemas import EmbankmentPaveInfo
from my_project.config.schemas.embankment_schemas import (
    EdgePoints,
)
from my_project.config.util_schemas import Point3D
from my_project.utils.bake import get_keys_and_values_for_bake
from my_project.utils.geometry.points import (
    center_point_pair,
    get_distance_2D,
    get_xy_distance_to_segment,
    interpolate_value_by_distance,
)
from my_project.utils.geometry_gh.attributes import (
    get_closest_point_on_curve_2D,
    get_curve_distance,
    get_curve_polyline_points,
    point3d_from_rg,
)
from my_project.utils.geometry_gh.const import (
    const_curve_obj,
    const_extended_line_from_two_points,
    const_point_obj,
    const_planer_srf_obj_from_points,
    const_polycurve_obj,
    const_brep_from_two_closed_point_lists,
    join_breps_or_raise,
)
from my_project.utils.geometry_gh.document import get_named_curves_on_layer
from my_project.utils.geometry_gh.intersect import (
    get_intersections_with_vertical_plane,
    split_brep_by_vertical_srf_from_two_points_keep_near_point,
    split_curve_by_lines_and_match_endpoints,
)
from my_project.utils.io import load_from_pickle, save_json_and_pickle

CURVE_NAME_RE = re.compile(r"^(?P<embankment_key>.+_\d+)_(?P<tier>\d+)_(?P<kind>shoulder|toe)$")
EMBANKMENT_SPLIT_DEBUG = []


def normalize_embankment_curve_name(name: str) -> str:
    return (
        str(name)
        .lower()
        .replace("＿", "_")
        .replace("\\", "_")
        .replace("/", "_")
        .replace(" ", "")
        .replace("　", "")
        .replace("*", "")
        .replace("_", "")
    )


def find_named_curve_by_normalized_name(
    named_curves: dict[str, rg.Curve],
    target_name: str,
) -> rg.Curve | None:
    normalized_target_name = normalize_embankment_curve_name(target_name)
    for name, curve in named_curves.items():
        if normalize_embankment_curve_name(name) == normalized_target_name:
            return curve
    return None


def get_curve_end_point_pair(curve: rg.Curve) -> tuple[Point3D, Point3D]:
    points = get_curve_polyline_points(curve)
    if len(points) >= 2:
        return points[0], points[-1]
    curve = const_curve_obj(curve)
    return point3d_from_rg(curve.PointAtStart), point3d_from_rg(curve.PointAtEnd)


def get_tier_position_from_curve_name(curve_name: str) -> tuple[int, str]:
    match = CURVE_NAME_RE.match(curve_name)
    if match is None:
        raise ValueError(f"Invalid embankment curve name: {curve_name}")
    return int(match.group("tier")), match.group("kind")


def is_embankment_tier_curve_name(
    curve_name: str,
    pavement_name: str,
    pavement_num: str,
) -> bool:
    if not str(curve_name).startswith(f"{pavement_name}_{pavement_num}_"):
        return False
    return CURVE_NAME_RE.match(str(curve_name)) is not None


def get_curve_between_start_end_lines(
    curve: rg.Curve,
    start_edge_points: tuple[Point3D, Point3D],
    end_edge_points: tuple[Point3D, Point3D],
) -> dict:
    target_line_points = {
        "start": start_edge_points,
        "end": end_edge_points,
    }
    split_items = split_open_embankment_boundary_curve_by_lines(
        curve=curve,
        split_line_points=[start_edge_points, end_edge_points],
        target_line_points=target_line_points,
    )
    target_item = None
    for item in split_items:
        start_matches = item["start_matches"]
        end_matches = item["end_matches"]
        if (
            ("start" in start_matches and "end" in end_matches)
            or ("end" in start_matches and "start" in end_matches)
        ):
            if target_item is not None:
                raise ValueError("Multiple curves found between start and end edge lines")
            target_item = item
    if target_item is None:
        target_item = min(
            split_items,
            key=lambda item: (
                min(
                    get_xy_distance_to_segment(item["start"], start_edge_points)
                    + get_xy_distance_to_segment(item["end"], end_edge_points),
                    get_xy_distance_to_segment(item["start"], end_edge_points)
                    + get_xy_distance_to_segment(item["end"], start_edge_points),
                )
            ),
        )

    result_curve = target_item["curve"]
    result_start = target_item["start"]
    result_end = target_item["end"]
    should_reverse = (
        "end" in target_item["start_matches"] and "start" in target_item["end_matches"]
    )
    if not target_item["start_matches"] and not target_item["end_matches"]:
        current_score = get_xy_distance_to_segment(result_start, start_edge_points)
        current_score += get_xy_distance_to_segment(result_end, end_edge_points)
        reverse_score = get_xy_distance_to_segment(result_start, end_edge_points)
        reverse_score += get_xy_distance_to_segment(result_end, start_edge_points)
        should_reverse = reverse_score < current_score
    if should_reverse:
        result_curve.Reverse()
        result_start = target_item["end"]
        result_end = target_item["start"]
    return {
        "curve": result_curve,
        "start_point": result_start,
        "end_point": result_end,
    }


def split_open_embankment_boundary_curve_by_lines(
    curve: rg.Curve,
    split_line_points: list[tuple[Point3D, Point3D]],
    target_line_points: dict[str, tuple[Point3D, Point3D]],
    cutter_length: float = DEFAULT_GEOMETRY_EXTENT,
) -> list[dict]:
    curve = const_curve_obj(curve)
    curve_on_reference_z = curve.DuplicateCurve()
    curve_on_reference_z.Transform(rg.Transform.PlanarProjection(rg.Plane.WorldXY))
    curve_on_reference_z.Transform(
        rg.Transform.Translation(rg.Vector3d(0, 0, STANDARD_BASE_Z))
    )
    extended_target_line_points = {}
    for key, points in target_line_points.items():
        extended_line = const_extended_line_from_two_points(
            *points,
            length=cutter_length,
        )
        extended_target_line_points[key] = (
            point3d_from_rg(extended_line.PointAtStart),
            point3d_from_rg(extended_line.PointAtEnd),
        )

    split_params = []
    for line_points in split_line_points:
        for point in get_intersections_with_vertical_plane(
            curve,
            line_points,
            cutter_length=cutter_length,
        ):
            ok, t = curve_on_reference_z.ClosestPoint(const_point_obj(point))
            if not ok:
                raise ValueError(f"Failed to get curve parameter at split point: {point}")
            if all(abs(t - existing) > DISTANCE_TOL for existing in split_params):
                split_params.append(t)

    split_params = sorted(split_params)

    split_curve_items = []
    domain = curve.Domain
    if not split_params:
        split_curve_items.append(
            {
                "curve": curve.DuplicateCurve(),
                "start": point3d_from_rg(curve.PointAtStart),
                "end": point3d_from_rg(curve.PointAtEnd),
            }
        )
    else:
        if curve.IsClosed:
            trim_ranges = [
                (t0, split_params[(i + 1) % len(split_params)])
                for i, t0 in enumerate(split_params)
            ]
        else:
            params = [domain.T0] + split_params + [domain.T1]
            params = sorted({
                param
                for param in params
                if domain.T0 - DISTANCE_TOL <= param <= domain.T1 + DISTANCE_TOL
            })
            trim_ranges = [
                (t0, t1)
                for t0, t1 in zip(params, params[1:])
                if abs(t1 - t0) > DISTANCE_TOL
            ]
        for t0, t1 in trim_ranges:
            if curve.IsClosed and t0 > t1:
                part1 = curve.Trim(t0, domain.T1)
                part2 = curve.Trim(domain.T0, t1)
                if part1 is not None and part2 is not None:
                    split_curve = rg.PolyCurve()
                    split_curve.Append(part1)
                    split_curve.Append(part2)
                else:
                    split_curve = None
            else:
                split_curve = curve.Trim(t0, t1)
            if split_curve is None:
                raise ValueError(f"Failed to trim embankment curve between parameters: {t0}, {t1}")
            split_curve_items.append(
                {
                    "curve": split_curve,
                    "start": point3d_from_rg(split_curve.PointAtStart),
                    "end": point3d_from_rg(split_curve.PointAtEnd),
                }
            )

    items = []
    for split_curve_item in split_curve_items:
        split_curve = split_curve_item["curve"]
        start = split_curve_item["start"]
        end = split_curve_item["end"]
        items.append(
            {
                "curve": const_curve_obj(split_curve).DuplicateCurve(),
                "start": start,
                "end": end,
                "start_matches": {
                    key
                    for key, points in extended_target_line_points.items()
                    if get_xy_distance_to_segment(start, points) <= DISTANCE_TOL
                },
                "end_matches": {
                    key
                    for key, points in extended_target_line_points.items()
                    if get_xy_distance_to_segment(end, points) <= DISTANCE_TOL
                },
            }
        )
    return items


def split_embankment_boundary_curve_by_abut_points(
    curve: rg.Curve,
    start_edge_points: tuple[Point3D, Point3D],
    end_edge_points: tuple[Point3D, Point3D],
    U_parallel_points: tuple[Point3D, Point3D],
    D_parallel_points: tuple[Point3D, Point3D],
    start_U_abut_points: tuple[Point3D, Point3D],
    start_D_abut_points: tuple[Point3D, Point3D],
    end_U_abut_points: tuple[Point3D, Point3D],
    end_D_abut_points: tuple[Point3D, Point3D],
    context: str,
    make_start_edge: bool = True,
    make_end_edge: bool = True,
    start_limit_points: tuple[Point3D, Point3D] | None = None,
    end_limit_points: tuple[Point3D, Point3D] | None = None,
) -> dict[str, rg.Curve]:
    curve = const_curve_obj(curve)

    def get_sample_points(target_curve: rg.Curve) -> list[Point3D]:
        points = get_curve_polyline_points(target_curve)
        if len(points) >= 2:
            return points
        target_curve = const_curve_obj(target_curve)
        samples = []
        domain = target_curve.Domain
        for ratio in [0.25, 0.5, 0.75]:
            t = domain.T0 + (domain.T1 - domain.T0) * ratio
            samples.append(point3d_from_rg(target_curve.PointAt(t)))
        return samples

    def get_average_distance(points: list[Point3D], line_points: tuple[Point3D, Point3D]) -> float:
        return sum(get_xy_distance_to_segment(point, line_points) for point in points) / len(points)

    def classify_curve_by_nearest_line(
        target_curve: rg.Curve,
        line_points_by_name: dict[str, tuple[Point3D, Point3D]],
    ) -> str:
        sample_points = get_sample_points(target_curve)
        distances = {
            name: get_average_distance(sample_points, line_points)
            for name, line_points in line_points_by_name.items()
        }
        return min(distances, key=distances.get)

    def get_axis_alignment(
        sample_points: list[Point3D],
        line_points: tuple[Point3D, Point3D],
    ) -> float:
        if len(sample_points) < 2:
            return 0.0
        curve_start = sample_points[0]
        curve_end = sample_points[-1]
        curve_dx = curve_end.x - curve_start.x
        curve_dy = curve_end.y - curve_start.y
        line_dx = line_points[1].x - line_points[0].x
        line_dy = line_points[1].y - line_points[0].y
        curve_length = (curve_dx ** 2 + curve_dy ** 2) ** 0.5
        line_length = (line_dx ** 2 + line_dy ** 2) ** 0.5
        if curve_length < DISTANCE_TOL or line_length < DISTANCE_TOL:
            return 0.0
        return abs(
            (curve_dx * line_dx + curve_dy * line_dy)
            / (curve_length * line_length)
        )

    def classify_boundary_curve(target_curve: rg.Curve) -> str:
        sample_points = get_sample_points(target_curve)
        edge_lines = {}
        if make_start_edge:
            edge_lines["start_edge"] = start_edge_points
        if make_end_edge:
            edge_lines["end_edge"] = end_edge_points
        parallel_lines = {
            "U_parallel": U_parallel_points,
            "D_parallel": D_parallel_points,
        }
        best_parallel = min(
            parallel_lines,
            key=lambda name: get_average_distance(sample_points, parallel_lines[name]),
        )
        parallel_alignment = max(
            get_axis_alignment(sample_points, points)
            for points in parallel_lines.values()
        )
        if not edge_lines:
            return best_parallel
        best_edge = min(
            edge_lines,
            key=lambda name: get_average_distance(sample_points, edge_lines[name]),
        )
        edge_alignment = max(
            get_axis_alignment(sample_points, points)
            for points in edge_lines.values()
        )
        if parallel_alignment > edge_alignment + 0.15:
            return best_parallel
        if edge_alignment > parallel_alignment + 0.15:
            return best_edge
        return classify_curve_by_nearest_line(
            target_curve,
            {
                **edge_lines,
                **parallel_lines,
            },
        )

    def add_result(key: str, target_curve: rg.Curve):
        if key in result:
            raise ValueError(f"Multiple curves classified as {key}: {context}")
        result[key] = target_curve

    def split_edge_curve(
        edge_curve: rg.Curve,
        *,
        prefix: str,
        U_abut_points: tuple[Point3D, Point3D],
        D_abut_points: tuple[Point3D, Point3D],
    ):
        try:
            edge_items = split_curve_by_lines_and_match_endpoints(
                curve=edge_curve,
                split_line_points=[
                    U_abut_points,
                    D_abut_points,
                ],
                target_line_points={},
                expected_count=3,
            )
            add_result(f"{prefix}_U", edge_items[0]["curve"])
            add_result(f"{prefix}_UD", edge_items[1]["curve"])
            add_result(f"{prefix}_D", edge_items[2]["curve"])
            return
        except ValueError:
            edge_part = classify_curve_by_nearest_line(
                edge_curve,
                {
                    "U": U_abut_points,
                    "D": D_abut_points,
                },
            )
            add_result(f"{prefix}_{edge_part}", edge_curve)

    split_line_points = []
    target_line_points = {}
    if make_start_edge:
        split_line_points.append(start_edge_points)
        target_line_points["start_edge"] = start_edge_points
    elif start_limit_points is not None:
        split_line_points.append(start_limit_points)
        target_line_points["start_limit"] = start_limit_points
    if make_end_edge:
        split_line_points.append(end_edge_points)
        target_line_points["end_edge"] = end_edge_points
    elif end_limit_points is not None:
        split_line_points.append(end_limit_points)
        target_line_points["end_limit"] = end_limit_points
    split_items = split_open_embankment_boundary_curve_by_lines(
        curve=curve,
        split_line_points=split_line_points,
        target_line_points=target_line_points,
    )

    result = {}
    result_candidates = {}
    for split_item in split_items:
        start = split_item["start"]
        end = split_item["end"]
        oriented_curve = split_item["curve"]
        boundary_name = classify_boundary_curve(oriented_curve)
        sample_points = get_sample_points(oriented_curve)
        skip_reason = None
        if start_limit_points is not None and not make_start_edge:
            start_limit_distance = get_average_distance(
                list(start_limit_points),
                end_edge_points,
            )
            if get_average_distance(sample_points, end_edge_points) > start_limit_distance + DISTANCE_TOL:
                skip_reason = "outside_start_limit"
        if end_limit_points is not None and not make_end_edge:
            end_limit_distance = get_average_distance(
                list(end_limit_points),
                start_edge_points,
            )
            if get_average_distance(sample_points, start_edge_points) > end_limit_distance + DISTANCE_TOL:
                skip_reason = "outside_end_limit"
        EMBANKMENT_SPLIT_DEBUG.append(
            {
                "context": context,
                "boundary_name": boundary_name,
                "skip_reason": skip_reason,
                "start": start,
                "end": end,
                "start_matches": split_item["start_matches"],
                "end_matches": split_item["end_matches"],
                "point_count": len(sample_points),
                "distances": {
                    "start_edge": get_average_distance(sample_points, start_edge_points),
                    "end_edge": get_average_distance(sample_points, end_edge_points),
                    "U_parallel": get_average_distance(sample_points, U_parallel_points),
                    "D_parallel": get_average_distance(sample_points, D_parallel_points),
                    "start_limit": (
                        None
                        if start_limit_points is None
                        else get_average_distance(sample_points, start_limit_points)
                    ),
                    "end_limit": (
                        None
                        if end_limit_points is None
                        else get_average_distance(sample_points, end_limit_points)
                    ),
                },
                "alignments": {
                    "start_edge": get_axis_alignment(sample_points, start_edge_points),
                    "end_edge": get_axis_alignment(sample_points, end_edge_points),
                    "U_parallel": get_axis_alignment(sample_points, U_parallel_points),
                    "D_parallel": get_axis_alignment(sample_points, D_parallel_points),
                },
            }
        )
        if skip_reason is not None:
            continue

        if boundary_name == "start_edge":
            if not make_start_edge:
                continue
            if get_distance_2D(end, start_U_abut_points[0]) < get_distance_2D(start, start_U_abut_points[0]):
                oriented_curve.Reverse()
            split_edge_curve(
                oriented_curve,
                prefix="start_edge",
                U_abut_points=start_U_abut_points,
                D_abut_points=start_D_abut_points,
            )
        elif boundary_name == "end_edge":
            if not make_end_edge:
                continue
            if get_distance_2D(end, end_U_abut_points[0]) < get_distance_2D(start, end_U_abut_points[0]):
                oriented_curve.Reverse()
            split_edge_curve(
                oriented_curve,
                prefix="end_edge",
                U_abut_points=end_U_abut_points,
                D_abut_points=end_D_abut_points,
            )
        elif boundary_name in {"U_parallel", "D_parallel"}:
            if get_xy_distance_to_segment(end, start_edge_points) < get_xy_distance_to_segment(start, start_edge_points):
                oriented_curve.Reverse()
            result_candidates.setdefault(boundary_name, []).append(oriented_curve)
        else:
            def line_distances(point: Point3D) -> dict[str, float]:
                return {
                    "start_edge": get_xy_distance_to_segment(point, start_edge_points),
                    "end_edge": get_xy_distance_to_segment(point, end_edge_points),
                    "U_parallel": get_xy_distance_to_segment(point, U_parallel_points),
                    "D_parallel": get_xy_distance_to_segment(point, D_parallel_points),
                    "start_U_abut": get_xy_distance_to_segment(point, start_U_abut_points),
                    "start_D_abut": get_xy_distance_to_segment(point, start_D_abut_points),
                    "end_U_abut": get_xy_distance_to_segment(point, end_U_abut_points),
                    "end_D_abut": get_xy_distance_to_segment(point, end_D_abut_points),
                }

            raise ValueError(
                f"[FAILED EMBANKMENT SPLIT] {context}: "
                f"boundary_name={boundary_name}, "
                f"start={start}, end={end}, "
                f"start_matches={sorted(split_item['start_matches'])}, "
                f"end_matches={sorted(split_item['end_matches'])}, "
                f"start_distances={line_distances(start)}, "
                f"end_distances={line_distances(end)}, "
                f"start_edge_points={start_edge_points}, "
                f"end_edge_points={end_edge_points}, "
                f"start_U_abut_points={start_U_abut_points}, "
                f"start_D_abut_points={start_D_abut_points}, "
                f"end_U_abut_points={end_U_abut_points}, "
                f"end_D_abut_points={end_D_abut_points}"
            )

    for key, curves in result_candidates.items():
        if len(curves) == 1:
            add_result(key, curves[0])
            continue
        if key == "U_parallel":
            reference_points = U_parallel_points
        elif key == "D_parallel":
            reference_points = D_parallel_points
        else:
            reference_points = start_edge_points
        target_curve = min(
            curves,
            key=lambda target_curve: get_average_distance(
                get_sample_points(target_curve),
                reference_points,
            ),
        )
        add_result(key, target_curve)
    if not result:
        raise ValueError(f"No embankment boundary curves were classified: {context}")
    return result

def get_world_embankment_points(
    pavement_info: EmbankmentPaveInfo,
    pavement_bottom_points_dict: dict[str, list[float] | list[Point3D]],
    named_curves: dict[str, rg.Curve],
    wall_points_dict: dict[str, dict[str, list[Point3D]]],
    abut_points_dict: dict,
) -> dict[str, EdgePoints]:
    slope = pavement_info.slope.value
    start_edge_info = pavement_info.start_edge
    end_edge_info = pavement_info.end_edge
    start_edge_structure = None if start_edge_info is None else start_edge_info.structure
    end_edge_structure = None if end_edge_info is None else end_edge_info.structure
    make_start_edge = start_edge_structure is not None
    make_end_edge = end_edge_structure is not None

    def get_edge_slope(edge_info, side: str, tier: int) -> float:
        if edge_info is None:
            return slope
        slopes = edge_info.U_slopes if side == "U" else edge_info.D_slopes
        fallback = edge_info.U_slope if side == "U" else edge_info.D_slope
        if tier in slopes:
            return slopes[tier]
        if fallback is not None:
            return fallback
        return slope

    start_U_slope = lambda tier: get_edge_slope(start_edge_info, "U", tier)
    start_D_slope = lambda tier: get_edge_slope(start_edge_info, "D", tier)
    end_U_slope = lambda tier: get_edge_slope(end_edge_info, "U", tier)
    end_D_slope = lambda tier: get_edge_slope(end_edge_info, "D", tier)

    abut_points = {
        "start": {"U": {}, "D": {}},
        "end": {"U": {}, "D": {}},
    }
    start_U_soil = pavement_bottom_points_dict["U_points"][0]
    start_D_soil = pavement_bottom_points_dict["D_points"][0]
    end_U_soil = pavement_bottom_points_dict["U_points"][-1]
    end_D_soil = pavement_bottom_points_dict["D_points"][-1]
    abut_points["start"]["U"]["wing_soil"] = start_U_soil
    abut_points["start"]["U"]["wing_bridge"] = start_U_soil
    abut_points["start"]["U"]["parapet"] = start_U_soil
    abut_points["start"]["D"]["wing_soil"] = start_D_soil
    abut_points["start"]["D"]["wing_bridge"] = start_D_soil
    abut_points["start"]["D"]["parapet"] = start_D_soil
    abut_points["end"]["U"]["wing_soil"] = end_U_soil
    abut_points["end"]["U"]["wing_bridge"] = end_U_soil
    abut_points["end"]["U"]["parapet"] = end_U_soil
    abut_points["end"]["D"]["wing_soil"] = end_D_soil
    abut_points["end"]["D"]["wing_bridge"] = end_D_soil
    abut_points["end"]["D"]["parapet"] = end_D_soil

    if make_start_edge and start_edge_structure.structure_type == "abutment":
        start_abut_points = abut_points_dict[start_edge_structure.structure_name]
        start_wing_dict = start_abut_points["wing_dict"]
        start_beamseat_dict = start_abut_points["beamseat_dict"]
        start_beamseat_corners = start_beamseat_dict.get(
            "beamseat_top_corners",
            start_beamseat_dict.get("U_beamseat_top_corners"),
        )
        start_D_beamseat_corners = start_beamseat_dict.get(
            "beamseat_top_corners",
            start_beamseat_dict.get("D_beamseat_top_corners"),
        )
        abut_points["start"]["U"]["wing_soil"] = start_wing_dict["U_wing_top_points"]["US"]
        abut_points["start"]["U"]["wing_bridge"] = start_wing_dict["U_wing_top_points"]["UB"]
        abut_points["start"]["U"]["parapet"] = start_beamseat_corners["UB"]
        abut_points["start"]["D"]["wing_soil"] = start_wing_dict["D_wing_top_points"]["DS"]
        abut_points["start"]["D"]["wing_bridge"] = start_wing_dict["D_wing_top_points"]["DB"]
        abut_points["start"]["D"]["parapet"] = start_D_beamseat_corners["DB"]
    elif make_start_edge:
        raise ValueError(f"Unknown start edge structure: {start_edge_structure}")
    if make_end_edge and end_edge_structure.structure_type == "abutment":
        end_abut_points = abut_points_dict[end_edge_structure.structure_name]
        end_wing_dict = end_abut_points["wing_dict"]
        end_beamseat_dict = end_abut_points["beamseat_dict"]
        end_beamseat_corners = end_beamseat_dict.get(
            "beamseat_top_corners",
            end_beamseat_dict.get("U_beamseat_top_corners"),
        )
        end_D_beamseat_corners = end_beamseat_dict.get(
            "beamseat_top_corners",
            end_beamseat_dict.get("D_beamseat_top_corners"),
        )
        abut_points["end"]["U"]["wing_soil"] = end_wing_dict["U_wing_top_points"]["US"]
        abut_points["end"]["U"]["wing_bridge"] = end_wing_dict["U_wing_top_points"]["UB"]
        abut_points["end"]["U"]["parapet"] = end_beamseat_corners["UB"]
        abut_points["end"]["D"]["wing_soil"] = end_wing_dict["D_wing_top_points"]["DS"]
        abut_points["end"]["D"]["wing_bridge"] = end_wing_dict["D_wing_top_points"]["DB"]
        abut_points["end"]["D"]["parapet"] = end_D_beamseat_corners["DB"]
    elif make_end_edge:
        raise ValueError(f"Unknown end edge structure: {end_edge_structure}")

    curves = {
        get_tier_position_from_curve_name(name): curve
        for name, curve in named_curves.items()
        if is_embankment_tier_curve_name(name, pavement_info.name, pavement_info.num)
    }
    start_edge_points = (
        abut_points["start"]["U"]["wing_soil"],
        abut_points["start"]["D"]["wing_soil"],
    )
    end_edge_points = (
        abut_points["end"]["U"]["wing_soil"],
        abut_points["end"]["D"]["wing_soil"],
    )
    U_parallel_points = (
        abut_points["start"]["U"]["wing_soil"],
        abut_points["end"]["U"]["wing_soil"],
    )
    D_parallel_points = (
        abut_points["start"]["D"]["wing_soil"],
        abut_points["end"]["D"]["wing_soil"],
    )
    start_U_abut_points = (
        abut_points["start"]["U"]["wing_soil"],
        abut_points["start"]["U"]["wing_bridge"],
    )
    start_D_abut_points = (
        abut_points["start"]["D"]["wing_soil"],
        abut_points["start"]["D"]["wing_bridge"],
    )
    end_U_abut_points = (
        abut_points["end"]["U"]["wing_soil"],
        abut_points["end"]["U"]["wing_bridge"],
    )
    end_D_abut_points = (
        abut_points["end"]["D"]["wing_soil"],
        abut_points["end"]["D"]["wing_bridge"],
    )

    start_limit_points = None
    if not make_start_edge:
        start_limit_curve = find_named_curve_by_normalized_name(
            named_curves,
            f"{pavement_info.name}_{pavement_info.num}_start_端部",
        )
        if start_limit_curve is not None:
            start_limit_points = get_curve_end_point_pair(start_limit_curve)
    end_limit_points = None
    if not make_end_edge:
        end_limit_curve = find_named_curve_by_normalized_name(
            named_curves,
            f"{pavement_info.name}_{pavement_info.num}_end_端部",
        )
        if end_limit_curve is not None:
            end_limit_points = get_curve_end_point_pair(end_limit_curve)

    crv_dict = {}
    for key, crv in curves.items():
        tier, kind = key
        if tier not in crv_dict:
            crv_dict[tier] = {}
        crv_dict[tier][kind] = split_embankment_boundary_curve_by_abut_points(
            curve=crv,
            start_edge_points=start_edge_points,
            end_edge_points=end_edge_points,
            U_parallel_points=U_parallel_points,
            D_parallel_points=D_parallel_points,
            start_U_abut_points=start_U_abut_points,
            start_D_abut_points=start_D_abut_points,
            end_U_abut_points=end_U_abut_points,
            end_D_abut_points=end_D_abut_points,
            context=f"{pavement_info.name}_{pavement_info.num}/tier={tier}/kind={kind}",
            make_start_edge=make_start_edge,
            make_end_edge=make_end_edge,
            start_limit_points=start_limit_points,
            end_limit_points=end_limit_points,
        )
    
    tier_1_shoulder_U_crv = const_polycurve_obj([const_point_obj(p) for p in pavement_bottom_points_dict["U_points"]])
    tier_1_shoulder_D_crv = const_polycurve_obj([const_point_obj(p) for p in pavement_bottom_points_dict["D_points"]])
    tier_1_shoulder_U_info = get_curve_between_start_end_lines(
        curve=tier_1_shoulder_U_crv,
        start_edge_points=start_edge_points,
        end_edge_points=end_edge_points,
    )
    tier_1_shoulder_D_info = get_curve_between_start_end_lines(
        curve=tier_1_shoulder_D_crv,
        start_edge_points=start_edge_points,
        end_edge_points=end_edge_points,
    )
    tier_1_shoulder_curves = crv_dict.setdefault(1, {}).setdefault("shoulder", {})
    tier_1_shoulder_curves["U_parallel"] = tier_1_shoulder_U_info["curve"]
    tier_1_shoulder_curves["D_parallel"] = tier_1_shoulder_D_info["curve"]
    if make_start_edge:
        tier_1_shoulder_curves["start_edge_UD"] = const_polycurve_obj(start_edge_points)
    if make_end_edge:
        tier_1_shoulder_curves["end_edge_UD"] = const_polycurve_obj(end_edge_points)

    crv_rows = []
    for tier in crv_dict:
        for kind in crv_dict[tier]:
            for name, crv in crv_dict[tier][kind].items():
                points = get_curve_polyline_points(
                    crv,
                    preserve_z=tier == 1 and kind == "shoulder",
                )
                points2D = [Point3D(p.x, p.y, STANDARD_BASE_Z) for p in points]
                curve2D = const_polycurve_obj(points2D)
                distance2D = [get_curve_distance(curve2D, p) for p in points2D]
                crv_rows.append(
                    {
                        "tier": tier,
                        "kind": kind,
                        "name": name,
                        "curve": crv,
                        "points": (
                            points
                            if tier == 1 and kind == "shoulder"
                            else list(points2D)
                        ),
                        "2Dcurve": curve2D,
                        "2Dpoints": points2D,
                        "2Ddistances": distance2D,
                    }
                )
    crv_df = pd.DataFrame(crv_rows)

    U_points_2D = crv_df[
        (crv_df["kind"] == "shoulder")
        & (crv_df["tier"] == 1)
        & (crv_df["name"] == "U_parallel")
    ]["2Dpoints"].iloc[0]
    D_points_2D = crv_df[
        (crv_df["kind"] == "shoulder")
        & (crv_df["tier"] == 1)
        & (crv_df["name"] == "D_parallel")
    ]["2Dpoints"].iloc[0]
    if len(U_points_2D) != len(D_points_2D):
        raise ValueError(
            f"U/D parallel point count mismatch: U={len(U_points_2D)}, D={len(D_points_2D)}"
        )
    center_line_points = [
        center_point_pair(U_point, D_point)
        for U_point, D_point in zip(
            get_curve_polyline_points(
                tier_1_shoulder_U_info["curve"],
                preserve_z=True,
            ),
            get_curve_polyline_points(
                tier_1_shoulder_D_info["curve"],
                preserve_z=True,
            ),
        )
    ]
    center_line_points_2D = [
        Point3D(point.x, point.y, STANDARD_BASE_Z)
        for point in center_line_points
    ]
    center_line_crv_2D = const_polycurve_obj(center_line_points_2D)
    center_line_distances = [
        get_curve_distance(center_line_crv_2D, point)
        for point in center_line_points_2D
    ]

    crv_df["center_match_points"] = None
    for idx, row in crv_df.iterrows():
        points2D = row["2Dpoints"]
        name = row["name"]
        if name == "U_parallel" or name == "D_parallel":
            match_points = [
                get_closest_point_on_curve_2D(center_line_crv_2D, point)
                for point in points2D
            ]
        elif name == "start_edge_U":
            match_points = [abut_points["start"]["U"]["wing_soil"]] * len(points2D)
        elif name == "start_edge_D":
            match_points = [abut_points["start"]["D"]["wing_soil"]] * len(points2D)
        elif name == "end_edge_U":
            match_points = [abut_points["end"]["U"]["wing_soil"]] * len(points2D)
        elif name == "end_edge_D":
            match_points = [abut_points["end"]["D"]["wing_soil"]] * len(points2D)
        elif name == "start_edge_UD":
            match_points = [
                get_closest_point_on_curve_2D(crv_dict[1]["shoulder"]["start_edge_UD"], point)
                for point in points2D
            ]
        elif name == "end_edge_UD":
            match_points = [
                get_closest_point_on_curve_2D(crv_dict[1]["shoulder"]["end_edge_UD"], point)
                for point in points2D
            ]
        else:
            raise ValueError(f"Unknown curve name for center matching: {name}")
        crv_df.at[idx, "center_match_points"] = match_points

    def get_new_points(this_2Dpoints, this_match_points, other_2Dcrv):
        new_points = []
        new_2Dpoints = []
        new_2Ddistances = []
        for k in range(1, len(this_2Dpoints) - 1):  # 両端は切った点
            point = this_2Dpoints[k]
            match_point = this_match_points[k]
            intersection_points = get_intersections_with_vertical_plane(
                other_2Dcrv,
                (point, match_point),
            )
            if not intersection_points:
                match_2Dpoint = get_closest_point_on_curve_2D(other_2Dcrv, point)
            else:
                match_2Dpoint = min(
                    intersection_points,
                    key=lambda p: get_distance_2D(p, point),
                )
            match_2Ddistance = get_curve_distance(other_2Dcrv, match_2Dpoint)
            new_points.append(match_2Dpoint)
            new_2Dpoints.append(match_2Dpoint)
            new_2Ddistances.append(match_2Ddistance)
        return new_points, new_2Dpoints, new_2Ddistances

    edge_names = [
        "U_parallel",
        "D_parallel",
    ]
    if make_start_edge:
        edge_names.extend(["start_edge_U", "start_edge_D", "start_edge_UD"])
    if make_end_edge:
        edge_names.extend(["end_edge_U", "end_edge_D", "end_edge_UD"])
    original_curve_data = {
        idx: {
            "tier": row["tier"],
            "kind": row["kind"],
            "points": list(row["points"]),
            "2Dpoints": list(row["2Dpoints"]),
            "2Ddistances": list(row["2Ddistances"]),
            "center_match_points": list(row["center_match_points"]),
            "2Dcurve": row["2Dcurve"],
        }
        for idx, row in crv_df.iterrows()
    }
    for name in edge_names:
        row_indices = crv_df.index[crv_df["name"] == name].to_list()
        for source_idx in row_indices:
            source_data = original_curve_data[source_idx]
            for target_idx in row_indices:
                if target_idx == source_idx:
                    continue
                new_points, new_2Dpoints, new_2Ddistances = get_new_points(
                    source_data["2Dpoints"],
                    source_data["center_match_points"],
                    original_curve_data[target_idx]["2Dcurve"],
                )
                target_data = original_curve_data[target_idx]
                if target_data["tier"] == 1 and target_data["kind"] == "shoulder":
                    target_z_values = [point.z for point in target_data["points"]]
                    new_points = [
                        Point3D(
                            point.x,
                            point.y,
                            interpolate_value_by_distance(
                                target_data["2Ddistances"],
                                target_z_values,
                                distance,
                            ),
                        )
                        for point, distance in zip(new_2Dpoints, new_2Ddistances)
                    ]
                crv_df.at[target_idx, "points"] = (
                    crv_df.at[target_idx, "points"] + new_points
                )
                crv_df.at[target_idx, "2Dpoints"] = (
                    crv_df.at[target_idx, "2Dpoints"] + new_2Dpoints
                )
                crv_df.at[target_idx, "2Ddistances"] = (
                    crv_df.at[target_idx, "2Ddistances"] + new_2Ddistances
                )

    edge_tier1_shoulder_points = {}
    if make_start_edge:
        edge_tier1_shoulder_points.update(
            {
                "start_edge_U": abut_points["start"]["U"]["wing_soil"],
                "start_edge_D": abut_points["start"]["D"]["wing_soil"],
            }
        )
    if make_end_edge:
        edge_tier1_shoulder_points.update(
            {
                "end_edge_U": abut_points["end"]["U"]["wing_soil"],
                "end_edge_D": abut_points["end"]["D"]["wing_soil"],
            }
        )
    for name, soil_point in edge_tier1_shoulder_points.items():
        reference_rows = crv_df[
            (crv_df["name"] == name)
            & ~((crv_df["tier"] == 1) & (crv_df["kind"] == "shoulder"))
        ]
        if reference_rows.empty:
            raise ValueError(f"No reference points found for {name} tier1 shoulder")
        point_count = len(reference_rows.iloc[0]["points"])
        points = [soil_point] * point_count
        points2D = [Point3D(soil_point.x, soil_point.y, STANDARD_BASE_Z)] * point_count
        crv_df = pd.concat(
            [
                crv_df,
                pd.DataFrame(
                    [
                        {
                            "tier": 1,
                            "kind": "shoulder",
                            "name": name,
                            "curve": "00000",
                            "points": points,
                            "2Dcurve": "00000",
                            "2Dpoints": points2D,
                            "2Ddistances": [0.0] * point_count,
                            "center_match_points": ["00000"] * point_count,
                        }
                    ]
                ),
            ],
            ignore_index=True,
        )

    for idx, row in crv_df.iterrows():
        sorted_items = sorted(
            zip(row["2Ddistances"], row["points"], row["2Dpoints"]),
            key=lambda item: item[0],
        )
        crv_df.at[idx, "2Ddistances"] = [item[0] for item in sorted_items]
        crv_df.at[idx, "points"] = [item[1] for item in sorted_items]
        crv_df.at[idx, "2Dpoints"] = [item[2] for item in sorted_items]
    

    # 次にwallの点から高さを追加する。
    wall_infos = {}
    for wall_interference in pavement_info.wall_interferences or []:
        wall_main_name = wall_interference.wall_main_name
        wall_name = wall_interference.wall_name
        wall_unique_key = f"{wall_main_name}_{wall_name}"
        wall_points = wall_points_dict[wall_unique_key]

        def get_wall_info(small_info):
            if small_info is None:
                return None
            target_tier = small_info.target_tier
            target_position = small_info.target_position
            return (target_tier, target_position)

        def match_wall_info(small_info, location):
            wall_info = get_wall_info(small_info)
            if wall_info is None:
                return {}
            points = wall_points[location]
            polyline = const_polycurve_obj(points)
            return {wall_info: {
                "points": points,
                "polyline": polyline,
            }}

        for matched_info in [
            match_wall_info(wall_interference.berm, "berm"),
            match_wall_info(wall_interference.top, "top"),
            match_wall_info(wall_interference.bottom, "bottom"),
        ]:
            for emb_location, wall_info in matched_info.items():
                if emb_location not in wall_infos:
                    wall_infos[emb_location] = []
                wall_infos[emb_location].append(wall_info)

    for emb_location, wall_info_list in wall_infos.items():
        target_tier, target_position = emb_location
        for wall_info in wall_info_list:
            for points in [start_edge_points, end_edge_points, U_parallel_points, D_parallel_points, start_U_abut_points, start_D_abut_points, end_U_abut_points, end_D_abut_points]:
                intersection_points = get_intersections_with_vertical_plane(wall_info["polyline"], points)
                if intersection_points:
                    for intersection_point in intersection_points:
                        wall_info["points"].append(intersection_point)

        this_tier_position_df = crv_df[(crv_df["tier"] == target_tier) & (crv_df["kind"] == target_position)]
        wall_height_points = [
            wall_point
            for wall_info in wall_info_list
            for wall_point in wall_info["points"]
        ]
        for idx, row in this_tier_position_df.iterrows():
            points = row["points"]
            for i, point in enumerate(points):
                for wall_point in wall_height_points:
                    if get_distance_2D(point, wall_point) < DISTANCE_TOL:
                        points[i] = Point3D(point.x, point.y, wall_point.z)
                        break
            crv_df.at[idx, "points"] = points

    def resolve_slope(slope_or_func, tier: int) -> float:
        return slope_or_func(tier) if callable(slope_or_func) else slope_or_func

    def get_cross_section_slope(name_df, start_slope, end_slope):
        tier1_toe_distances = name_df[(name_df["tier"] == 1) & (name_df["kind"] == "toe")]["2Ddistances"].iloc[0]
        tier1_shoulder_points = name_df[(name_df["tier"] == 1) & (name_df["kind"] == "shoulder")]["points"].iloc[0]
        point_count = len(tier1_toe_distances)
        max_tier = int(name_df["tier"].max())
        all_distance = tier1_toe_distances[-1]
        prescribed_slopes_by_tier = [
            [
                resolve_slope(start_slope, tier)
                + (
                    resolve_slope(end_slope, tier)
                    - resolve_slope(start_slope, tier)
                )
                * (
                    0
                    if abs(all_distance) < DISTANCE_TOL
                    else distance / all_distance
                )
                for distance in tier1_toe_distances
            ]
            for tier in range(1, max_tier + 1)
        ]
        slope_anchors = [
            {
                0: resolve_slope(start_slope, tier),
                point_count - 1: resolve_slope(end_slope, tier),
            }
            for tier in range(1, max_tier + 1)
        ]

        for i in range(point_count):
            tier1_shoulder_point = tier1_shoulder_points[i]
            point_distances = {(1, "shoulder"): 0}
            known_toe_z = {}
            known_shoulder_z = {}
            for tier in range(1, max_tier + 1):
                for kind in ["shoulder", "toe"]:
                    if tier == 1 and kind == "shoulder":
                        continue
                    row_mask = (name_df["tier"] == tier) & (name_df["kind"] == kind)
                    if name_df[row_mask].empty:
                        continue
                    points = name_df[row_mask]["points"].iloc[0]
                    if i >= len(points):
                        continue
                    point = points[i]
                    point_distances[(tier, kind)] = get_distance_2D(
                        tier1_shoulder_point,
                        point,
                    )
                    if abs(point.z - STANDARD_BASE_Z) > DISTANCE_TOL:
                        if kind == "toe":
                            known_toe_z[tier] = point.z
                        elif tier > 1:
                            known_shoulder_z[tier] = point.z
                            known_toe_z[tier - 1] = point.z

            section_distances = {}
            for tier in range(1, max_tier + 1):
                shoulder_distance = point_distances.get((tier, "shoulder"))
                toe_distance = point_distances.get((tier, "toe"))
                if shoulder_distance is None or toe_distance is None:
                    continue
                section_distances[tier] = toe_distance - shoulder_distance
            shoulder_z = tier1_shoulder_point.z
            for tier in range(1, max_tier + 1):
                if tier in known_shoulder_z:
                    shoulder_z = known_shoulder_z[tier]
                if tier not in section_distances:
                    continue
                section_distance = section_distances[tier]
                if tier in known_toe_z:
                    z_gap = shoulder_z - known_toe_z[tier]
                    if (
                        abs(section_distance) > DISTANCE_TOL
                        and abs(z_gap) > DISTANCE_TOL
                    ):
                        slope_anchors[tier - 1][i] = section_distance / z_gap
                    shoulder_z = known_toe_z[tier]
                else:
                    shoulder_z -= section_distance / prescribed_slopes_by_tier[tier - 1][i]

        slopes = [[0.0] * max_tier for _ in range(point_count)]
        for tier_index, anchors in enumerate(slope_anchors):
            anchor_indices = sorted(anchors)
            for start_index, end_index in zip(anchor_indices, anchor_indices[1:]):
                start_distance = tier1_toe_distances[start_index]
                end_distance = tier1_toe_distances[end_index]
                distance_span = end_distance - start_distance
                for i in range(start_index, end_index + 1):
                    distance_ratio = (
                        0
                        if abs(distance_span) < DISTANCE_TOL
                        else (tier1_toe_distances[i] - start_distance) / distance_span
                    )
                    slopes[i][tier_index] = (
                        anchors[start_index]
                        + (anchors[end_index] - anchors[start_index]) * distance_ratio
                    )
        return slopes

    def get_cross_section_height_with_slope(name_df, slopes):
        name_df = name_df.copy()
        tier1_shoulder_points = name_df[(name_df["tier"] == 1) & (name_df["kind"] == "shoulder")]["points"].iloc[0]
        for i in range(len(tier1_shoulder_points)):
            tier1_shoulder_point = tier1_shoulder_points[i]
            point_distances = {(1, "shoulder"): 0}
            max_tier = int(name_df["tier"].max())
            for tier in range(1, max_tier + 1):
                for kind in ["shoulder", "toe"]:
                    if kind == "shoulder" and tier == 1:
                        continue
                    row_mask = (name_df["tier"] == tier) & (name_df["kind"] == kind)
                    if name_df[row_mask].empty:
                        continue
                    points = name_df[row_mask]["points"].iloc[0]
                    if i >= len(points):
                        continue
                    this_point = points[i]
                    point_distances[(tier, kind)] = get_distance_2D(
                        tier1_shoulder_point,
                        this_point,
                    )
            section_distances = {}
            for tier in range(1, max_tier + 1):
                shoulder_distance = point_distances.get((tier, "shoulder"))
                toe_distance = point_distances.get((tier, "toe"))
                if shoulder_distance is None or toe_distance is None:
                    continue
                section_distances[tier] = toe_distance - shoulder_distance
            available_section_tiers = set(section_distances)
            section_distances = [
                section_distances.get(tier, 0.0)
                for tier in range(1, max_tier + 1)
            ]
            section_slopes = slopes[i]

            for tier in range(1, max_tier + 1):
                shoulder_mask = (name_df["tier"] == tier) & (name_df["kind"] == "shoulder")
                toe_mask = (name_df["tier"] == tier) & (name_df["kind"] == "toe")
                if name_df[shoulder_mask].empty or name_df[toe_mask].empty:
                    continue
                shoulder_idx = name_df[shoulder_mask].index[0]
                toe_idx = name_df[toe_mask].index[0]
                shoulder_points = list(name_df.at[shoulder_idx, "points"])
                toe_points = list(name_df.at[toe_idx, "points"])
                if (
                    i >= len(shoulder_points)
                    or i >= len(toe_points)
                    or tier not in available_section_tiers
                ):
                    continue
                shoulder_point = shoulder_points[i]
                toe_point = toe_points[i]
                z_drop_to_shoulder = sum(
                    section_distance / section_slope # 1:1.8とかだから。
                    for section_slope, section_distance in zip(
                        section_slopes[: tier - 1],
                        section_distances[: tier - 1],
                    )
                )
                shoulder_z = tier1_shoulder_point.z - z_drop_to_shoulder
                toe_z = shoulder_z - section_distances[tier - 1] / section_slopes[tier - 1]
                shoulder_points[i] = Point3D(shoulder_point.x, shoulder_point.y, shoulder_z)
                toe_points[i] = Point3D(toe_point.x, toe_point.y, toe_z)
                name_df.at[shoulder_idx, "points"] = shoulder_points
                name_df.at[toe_idx, "points"] = toe_points
        return name_df

    def get_points_with_name_df(name_df, start_slope, end_slope):
        slopes = get_cross_section_slope(name_df, start_slope, end_slope)
        name_df_z = get_cross_section_height_with_slope(name_df, slopes)
        name_points_dict = {}
        for _, row in name_df_z.iterrows():
            tier = row["tier"]
            kind = row["kind"]
            points = row["points"]
            if tier not in name_points_dict:
                name_points_dict[tier] = {}
            if kind not in name_points_dict[tier]:
                name_points_dict[tier][kind] = {}
            name_points_dict[tier][kind] = points
        for tier in list(name_points_dict):
            if {"shoulder", "toe"} - set(name_points_dict[tier]):
                del name_points_dict[tier]
        return name_points_dict

    U_parallel_result = get_points_with_name_df(
        crv_df[crv_df["name"] == "U_parallel"], slope, slope
    )
    D_parallel_result = get_points_with_name_df(
        crv_df[crv_df["name"] == "D_parallel"], slope, slope
    )
    edge_parallel_map = {
        "start_edge_U": U_parallel_result,
        "start_edge_D": D_parallel_result,
        "end_edge_U": U_parallel_result,
        "end_edge_D": D_parallel_result,
    }
    if not make_start_edge:
        edge_parallel_map.pop("start_edge_U")
        edge_parallel_map.pop("start_edge_D")
    if not make_end_edge:
        edge_parallel_map.pop("end_edge_U")
        edge_parallel_map.pop("end_edge_D")
    for edge_name, parallel_result in edge_parallel_map.items():
        for idx, row in crv_df[crv_df["name"] == edge_name].iterrows():
            if row["tier"] == 1 and row["kind"] == "shoulder":
                continue
            points = list(row["points"])
            parallel_points = parallel_result.get(row["tier"], {}).get(row["kind"])
            if parallel_points is None:
                continue
            for i, point in enumerate(points):
                for parallel_point in parallel_points:
                    if get_distance_2D(point, parallel_point) < DISTANCE_TOL:
                        points[i] = Point3D(point.x, point.y, parallel_point.z)
                        break
            crv_df.at[idx, "points"] = points

    result = {
        "U_parallel": U_parallel_result,
        "D_parallel": D_parallel_result,
    }
    if make_start_edge:
        result.update(
            {
                "start_edge_U": get_points_with_name_df(crv_df[crv_df["name"] == "start_edge_U"], slope, start_U_slope),
                "start_edge_UD": get_points_with_name_df(crv_df[crv_df["name"] == "start_edge_UD"], start_U_slope, start_D_slope),
                "start_edge_D": get_points_with_name_df(crv_df[crv_df["name"] == "start_edge_D"], start_D_slope, slope),
            }
        )
    if make_end_edge:
        result.update(
            {
                "end_edge_U": get_points_with_name_df(crv_df[crv_df["name"] == "end_edge_U"], slope, end_U_slope),
                "end_edge_UD": get_points_with_name_df(crv_df[crv_df["name"] == "end_edge_UD"], end_U_slope, end_D_slope),
                "end_edge_D": get_points_with_name_df(crv_df[crv_df["name"] == "end_edge_D"], end_D_slope, slope),
            }
        )

    for parallel_name, parallel_result in {
        "U_parallel": U_parallel_result,
        "D_parallel": D_parallel_result,
    }.items():
        lowest_tier = max(parallel_result)
        top_points = parallel_result[1]["shoulder"]
        lowest_toe_points = parallel_result[lowest_tier]["toe"]
        if len(top_points) != len(lowest_toe_points):
            raise ValueError(
                f"{parallel_name} closure point count mismatch: "
                f"top={len(top_points)}, bottom={len(lowest_toe_points)}"
            )

        center_top_points = []
        for top_point in top_points:
            center_point_2D = get_closest_point_on_curve_2D(
                center_line_crv_2D,
                top_point,
            )
            center_distance = get_curve_distance(center_line_crv_2D, center_point_2D)
            center_top_points.append(
                Point3D(
                    center_point_2D.x,
                    center_point_2D.y,
                    interpolate_value_by_distance(
                        center_line_distances,
                        [point.z for point in center_line_points],
                        center_distance,
                    ),
                )
            )
        center_bottom_points = [
            Point3D(center_point.x, center_point.y, toe_point.z)
            for center_point, toe_point in zip(center_top_points, lowest_toe_points)
        ]
        parallel_result["closure_points"] = {
            "top": center_top_points,
            "bottom": center_bottom_points,
        }

    def get_nearest_parallel_lowest_toe_z(
        parallel_result: dict,
        point: Point3D,
    ) -> float:
        lowest_tier = max(key for key in parallel_result if isinstance(key, int))
        return min(
            parallel_result[lowest_tier]["toe"],
            key=lambda toe_point: get_distance_2D(toe_point, point),
        ).z

    edge_closure_items = []
    if make_start_edge:
        edge_closure_items.extend([
            ("start_edge_U", abut_points["start"]["U"]["wing_soil"], U_parallel_result),
            ("start_edge_D", abut_points["start"]["D"]["wing_soil"], D_parallel_result),
        ])
    if make_end_edge:
        edge_closure_items.extend([
            ("end_edge_U", abut_points["end"]["U"]["wing_soil"], U_parallel_result),
            ("end_edge_D", abut_points["end"]["D"]["wing_soil"], D_parallel_result),
        ])
    for edge_name, soil_point, parallel_result in edge_closure_items:
        point_count = len(result[edge_name][1]["shoulder"])
        lowest_tier = max(key for key in result[edge_name] if isinstance(key, int))
        bottom_points = result[edge_name][lowest_tier]["toe"]
        if point_count != len(bottom_points):
            raise ValueError(
                f"{edge_name} closure point count mismatch: "
                f"top={point_count}, bottom={len(bottom_points)}"
            )
        result[edge_name]["closure_points"] = {
            "bottom": [
                Point3D(
                    soil_point.x,
                    soil_point.y,
                    get_nearest_parallel_lowest_toe_z(parallel_result, bottom_point),
                )
                for bottom_point in bottom_points
            ]
        }

    UD_edge_items = []
    if make_start_edge:
        UD_edge_items.append(("start_edge_UD", "start"))
    if make_end_edge:
        UD_edge_items.append(("end_edge_UD", "end"))
    for edge_name, edge_position in UD_edge_items:
        lowest_tier = max(result[edge_name])
        top_points = result[edge_name][1]["shoulder"]
        bottom_points = result[edge_name][lowest_tier]["toe"]
        if len(top_points) != len(bottom_points):
            raise ValueError(
                f"{edge_name} closure point count mismatch: "
                f"top={len(top_points)}, bottom={len(bottom_points)}"
            )
        result[edge_name]["closure_points"] = {
            "bottom": [
                Point3D(top_point.x, top_point.y, bottom_point.z)
                for top_point, bottom_point in zip(top_points, bottom_points)
            ]
        }
        result[edge_name]["trim_points"] = [
            abut_points[edge_position]["U"]["parapet"],
            abut_points[edge_position]["U"]["wing_soil"],
            abut_points[edge_position]["D"]["wing_soil"],
            abut_points[edge_position]["D"]["parapet"],
        ]

    for name, name_result in result.items():
        section_count = len(name_result[1]["shoulder"])
        for section_index in range(section_count):
            line_start = name_result["closure_points"]["bottom"][section_index]
            line_end = name_result[1]["toe"][section_index]
            dx = line_end.x - line_start.x
            dy = line_end.y - line_start.y
            length_squared = dx ** 2 + dy ** 2
            if length_squared < DISTANCE_TOL ** 2:
                raise ValueError(
                    f"Cannot define vertical section plane ({name}, section={section_index})"
                )
            section_tiers = [
                tier
                for tier in sorted(key for key in name_result if isinstance(key, int))
                if (
                    "shoulder" in name_result[tier]
                    and "toe" in name_result[tier]
                    and section_index < len(name_result[tier]["shoulder"])
                    and section_index < len(name_result[tier]["toe"])
                )
            ]
            for tier in section_tiers:
                for kind in ["shoulder", "toe"]:
                    points = name_result[tier][kind]
                    point = points[section_index]
                    distance_ratio = (
                        (point.x - line_start.x) * dx
                        + (point.y - line_start.y) * dy
                    ) / length_squared
                    points[section_index] = Point3D(
                        line_start.x + distance_ratio * dx,
                        line_start.y + distance_ratio * dy,
                        point.z,
                    )
            for points in name_result["closure_points"].values():
                point = points[section_index]
                distance_ratio = (
                    (point.x - line_start.x) * dx
                    + (point.y - line_start.y) * dy
                ) / length_squared
                points[section_index] = Point3D(
                    line_start.x + distance_ratio * dx,
                    line_start.y + distance_ratio * dy,
                    point.z,
                )

    return result

def get_brep_from_points(point_dict) -> dict[str, rg.Brep]:
    def has_point(name_dict, tier, kind, index):
        return (
            tier in name_dict
            and kind in name_dict[tier]
            and index < len(name_dict[tier][kind])
        )

    def get_section_items(name_dict, index, *, include_top_closure: bool):
        points = []
        signature = []
        if include_top_closure:
            top_points = name_dict["closure_points"]["top"]
            if index >= len(top_points):
                return (), []
            points.append(top_points[index])
            signature.append(("closure", "top"))
        for tier in sorted(key for key in name_dict if isinstance(key, int)):
            if not (
                has_point(name_dict, tier, "shoulder", index)
                and has_point(name_dict, tier, "toe", index)
            ):
                continue
            points.extend([
                name_dict[tier]["shoulder"][index],
                name_dict[tier]["toe"][index],
            ])
            signature.extend([(tier, "shoulder"), (tier, "toe")])
        bottom_points = name_dict["closure_points"]["bottom"]
        if index >= len(bottom_points):
            return (), []
        points.append(bottom_points[index])
        signature.append(("closure", "bottom"))
        return tuple(signature), points

    def get_section_count(name_dict):
        return max(
            len(points)
            for tier in [key for key in name_dict if isinstance(key, int)]
            for points in name_dict[tier].values()
        )

    def get_name_sections(name_dict, *, include_top_closure: bool):
        sections = []
        for index in range(get_section_count(name_dict)):
            signature, points = get_section_items(
                name_dict,
                index,
                include_top_closure=include_top_closure,
            )
            if signature and len(points) >= 3:
                sections.append({"signature": signature, "points": points})
            else:
                sections.append(None)
        return sections

    def get_same_signature_segments(sections):
        segments = []
        current = []
        current_signature = None
        for section in sections:
            signature = None if section is None else section["signature"]
            if signature is None:
                if len(current) >= 2:
                    segments.append(current)
                current = []
                current_signature = None
                continue
            if current_signature is not None and signature != current_signature:
                if len(current) >= 2:
                    segments.append(current)
                current = [section]
                current_signature = signature
                continue
            current.append(section)
            current_signature = signature
        if len(current) >= 2:
            segments.append(current)
        return segments

    def get_cap_breps(section_points):
        unique_points = []
        for point in section_points:
            if all(
                const_point_obj(point).DistanceTo(const_point_obj(existing)) > DISTANCE_TOL
                for existing in unique_points
            ):
                unique_points.append(point)
        if len(unique_points) < 3:
            raise ValueError(f"Need at least 3 section cap points, got {len(unique_points)}")
        try:
            return [const_planer_srf_obj_from_points(unique_points)]
        except ValueError:
            breps = []
            anchor = const_point_obj(unique_points[0])
            for point1, point2 in zip(unique_points[1:-1], unique_points[2:]):
                point1_obj = const_point_obj(point1)
                point2_obj = const_point_obj(point2)
                if (
                    anchor.DistanceTo(point1_obj) <= DISTANCE_TOL
                    or anchor.DistanceTo(point2_obj) <= DISTANCE_TOL
                    or point1_obj.DistanceTo(point2_obj) <= DISTANCE_TOL
                ):
                    continue
                brep = rg.Brep.CreateFromCornerPoints(
                    anchor,
                    point1_obj,
                    point2_obj,
                    DISTANCE_TOL,
                )
                if brep is not None:
                    breps.append(brep)
            if not breps:
                raise ValueError(f"Failed to create section cap breps. points={unique_points}")
            return breps

    def get_face_breps(points, *, fan_from_first: bool = False):
        unique_points = []
        for point in points:
            if all(
                const_point_obj(point).DistanceTo(const_point_obj(existing)) > DISTANCE_TOL
                for existing in unique_points
            ):
                unique_points.append(point)
        if len(unique_points) < 3:
            return []
        point_objs = [const_point_obj(point) for point in unique_points]
        if len(point_objs) == 3:
            brep = rg.Brep.CreateFromCornerPoints(
                point_objs[0],
                point_objs[1],
                point_objs[2],
                DISTANCE_TOL,
            )
            return [] if brep is None else [brep]
        if len(point_objs) == 4 and not fan_from_first:
            brep = rg.Brep.CreateFromCornerPoints(
                point_objs[0],
                point_objs[1],
                point_objs[2],
                point_objs[3],
                DISTANCE_TOL,
            )
            if brep is not None:
                return [brep]
        if not fan_from_first:
            try:
                return [const_planer_srf_obj_from_points(unique_points)]
            except ValueError:
                pass
        breps = []
        anchor = point_objs[0]
        for point1, point2 in zip(point_objs[1:-1], point_objs[2:]):
            if (
                anchor.DistanceTo(point1) <= DISTANCE_TOL
                or anchor.DistanceTo(point2) <= DISTANCE_TOL
                or point1.DistanceTo(point2) <= DISTANCE_TOL
            ):
                continue
            brep = rg.Brep.CreateFromCornerPoints(
                anchor,
                point1,
                point2,
                DISTANCE_TOL,
            )
            if brep is not None:
                breps.append(brep)
        return breps

    def get_segment_brep(name, segment, *, require_solid: bool):
        breps = []
        section_points = [section["points"] for section in segment]
        for i in range(len(section_points) - 1):
            next_points = section_points[i + 1]
            breps.append(
                const_brep_from_two_closed_point_lists(
                    section_points[i],
                    next_points,
                    cap=False,
                )
            )
        end_caps = get_cap_breps(section_points[0]) + get_cap_breps(section_points[-1])
        joined = rg.Brep.JoinBreps(breps + end_caps, DISTANCE_TOL)
        if not joined:
            raise ValueError(f"Failed to join breps ({name})")
        for brep in joined:
            if require_solid and not brep.IsSolid:
                raise ValueError(f"Joined embankment brep is not solid ({name})")
        return list(joined)

    def get_edge_section_items(name_dict, index):
        if not has_point(name_dict, 1, "shoulder", index):
            return (), None
        bottom_points = name_dict["closure_points"]["bottom"]
        if index >= len(bottom_points):
            return (), None
        tiers = [
            tier
            for tier in sorted(key for key in name_dict if isinstance(key, int))
            if (
                has_point(name_dict, tier, "shoulder", index)
                and has_point(name_dict, tier, "toe", index)
            )
        ]
        if not tiers:
            return (), None
        signature = tuple((tier, "shoulder", "toe") for tier in tiers)
        layers = [
            {
                "shoulder": name_dict[tier]["shoulder"][index],
                "toe": name_dict[tier]["toe"][index],
            }
            for tier in tiers
        ]
        return signature, {
            "signature": signature,
            "layers": layers,
            "bottom": bottom_points[index],
        }

    def get_edge_sections(name_dict):
        sections = []
        for index in range(get_section_count(name_dict)):
            signature, section = get_edge_section_items(name_dict, index)
            if signature and section is not None:
                sections.append(section)
            else:
                sections.append(None)
        return sections

    def get_edge_segment_brep(name, segment):
        breps = []
        for section, next_section in zip(segment, segment[1:]):
            layers = section["layers"]
            next_layers = next_section["layers"]
            for tier_index, layer in enumerate(layers):
                next_layer = next_layers[tier_index]
                breps.extend(get_face_breps([
                    layer["shoulder"],
                    next_layer["shoulder"],
                    next_layer["toe"],
                    layer["toe"],
                ]))
                if tier_index + 1 < len(layers):
                    lower_layer = layers[tier_index + 1]
                    next_lower_layer = next_layers[tier_index + 1]
                    breps.extend(get_face_breps([
                        layer["toe"],
                        next_layer["toe"],
                        next_lower_layer["shoulder"],
                        lower_layer["shoulder"],
                    ]))
            breps.extend(get_face_breps([
                layers[-1]["toe"],
                next_layers[-1]["toe"],
                next_section["bottom"],
                section["bottom"],
            ]))
        for section in [segment[0], segment[-1]]:
            cap_points = [section["bottom"]]
            for layer in section["layers"]:
                cap_points.extend([layer["shoulder"], layer["toe"]])
            breps.extend(get_face_breps(
                cap_points,
                fan_from_first=True,
            ))
        joined = rg.Brep.JoinBreps(breps, DISTANCE_TOL)
        if not joined:
            raise ValueError(f"Failed to join edge breps ({name})")
        return list(joined)

    parallel_names = ["U_parallel", "D_parallel"]
    edge_names = []
    UD_edge_names = []
    if "start_edge_U" in point_dict:
        edge_names.extend(["start_edge_U", "start_edge_D"])
    if "end_edge_U" in point_dict:
        edge_names.extend(["end_edge_U", "end_edge_D"])
    if "start_edge_UD" in point_dict:
        UD_edge_names.append("start_edge_UD")
    if "end_edge_UD" in point_dict:
        UD_edge_names.append("end_edge_UD")
    all_names = parallel_names + UD_edge_names
    brep_dict = {}
    for name in edge_names:
        name_dict = point_dict[name]
        sections = get_edge_sections(name_dict)
        segments = get_same_signature_segments(sections)
        for segment_index, segment in enumerate(segments, start=1):
            segment_breps = get_edge_segment_brep(name, segment)
            for brep_index, brep in enumerate(segment_breps, start=1):
                key_parts = [name]
                if len(segments) > 1:
                    key_parts.append(str(segment_index))
                if len(segment_breps) > 1:
                    key_parts.append(str(brep_index))
                brep_dict["_".join(key_parts)] = brep
    for name in all_names:
        name_dict = point_dict[name]
        sections = get_name_sections(
            name_dict,
            include_top_closure=name in parallel_names,
        )
        segments = get_same_signature_segments(sections)
        for segment_index, segment in enumerate(segments, start=1):
            segment_breps = get_segment_brep(
                name,
                segment,
                require_solid=True,
            )
            for brep_index, brep in enumerate(segment_breps, start=1):
                if name in UD_edge_names:
                    trim_points = list(name_dict["trim_points"])
                    bridge_mid_point = center_point_pair(
                        trim_points[0],
                        trim_points[3],
                    )
                    soil_mid_point = center_point_pair(
                        trim_points[1],
                        trim_points[2],
                    )
                    keep_point = Point3D(
                        2 * bridge_mid_point.x - soil_mid_point.x,
                        2 * bridge_mid_point.y - soil_mid_point.y,
                        STANDARD_BASE_Z,
                    )
                    cut_point = Point3D(
                        soil_mid_point.x,
                        soil_mid_point.y,
                        STANDARD_BASE_Z,
                    )
                    brep = split_brep_by_vertical_srf_from_two_points_keep_near_point(
                        target_brep=brep,
                        cutter_points=[trim_points[0], trim_points[3]],
                        keep_point=keep_point,
                        cut_point=cut_point,
                        cap=True,
                        tol=DISTANCE_TOL,
                    )
                    if not brep.IsSolid:
                        raise ValueError(f"Trimmed UD embankment brep is not solid ({name})")
                key_parts = [name]
                if len(segments) > 1:
                    key_parts.append(str(segment_index))
                if len(segment_breps) > 1:
                    key_parts.append(str(brep_index))
                brep_dict["_".join(key_parts)] = brep

    return brep_dict


def main(initial_or_final: str, debug: bool = False):
    EMBANKMENT_SPLIT_DEBUG.clear()
    DIR = get_output_dir(initial_or_final)
    pavement_infos = load_from_pickle(
        file_path=DIR / f"{Filenames.INPUT}_{Filenames.EMBANKMENT}_{Filenames.PAVEMENT}.pickle",
    )
    pavement_bottom_points_dict = load_from_pickle(
        file_path=DIR / f"{Filenames.WORLD}_{Filenames.EMBANKMENT}_{Filenames.PAVEMENT}_{Filenames.BOTTOM}_{Filenames.POINTS}.pickle",
    )
    wall_points_dict = load_from_pickle(
        file_path=DIR / f"{Filenames.WORLD}_{Filenames.WALL}_{Filenames.POINTS}.pickle",
    )
    abut_points_dict = load_from_pickle(
        file_path=DIR / f"{Filenames.WORLD}_{Filenames.ABUT}_{Filenames.POINTS}.pickle",
    )
    named_curves = get_named_curves_on_layer(layer_index)

    world_embankment_points_dict = {}
    embankment_brep_dict = {}
    for info in pavement_infos:
        name = info.name
        num = info.num
        unique_key = f"{name}_{num}"
        indiv_dict = get_world_embankment_points(
            pavement_info=info,
            pavement_bottom_points_dict=pavement_bottom_points_dict[unique_key],
            named_curves=named_curves,
            wall_points_dict=wall_points_dict,
            abut_points_dict=abut_points_dict,
        )
        world_embankment_points_dict[unique_key] = indiv_dict
        embankment_brep_dict[unique_key] = get_brep_from_points(indiv_dict)
    save_json_and_pickle(
        data=world_embankment_points_dict,
        folder_path=DIR,
        name=f"{Filenames.EMBANKMENT}_{Filenames.POINTS}",
    )
    save_json_and_pickle(
        data=EMBANKMENT_SPLIT_DEBUG,
        folder_path=DIR,
        name=f"{Filenames.EMBANKMENT}_split_debug",
    )
    bake_keys, bake_objs = get_keys_and_values_for_bake(embankment_brep_dict)
    if debug:
        bake_keys2, bake_objs2 = get_keys_and_values_for_bake(embankment_brep_dict)
        if len(bake_objs) == 0:
            raise ValueError("No embankment points were generated for debug bake")
        return bake_keys, bake_objs, bake_keys2, bake_objs2
    return bake_keys, bake_objs


if __name__ == "__main__":
    # bake_keys, bake_objs, bake_keys2, bake_objs2 = main("initial", debug=True)
    bake_keys, bake_objs = main("initial", debug=False)
