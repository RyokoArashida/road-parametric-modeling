# ruff: noqa: E402
from __future__ import annotations

import re

import Rhino.Geometry as rg

from my_project.config.file_names import Filenames
from my_project.config.locale_compat import normalize_lc_time

normalize_lc_time()

import pandas as pd

from my_project.config.constants import DISTANCE_TOL, STANDARD_BASE_Z
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
)
from my_project.utils.geometry_gh.const import (
    const_curve_obj,
    const_point_obj,
    const_polycurve_obj,
)
from my_project.utils.geometry_gh.document import get_named_curves_on_layer
from my_project.utils.geometry_gh.intersect import (
    get_intersections_with_vertical_plane,
    split_curve_by_lines_and_match_endpoints,
)
from my_project.utils.io import load_from_pickle, save_json_and_pickle

CURVE_NAME_RE = re.compile(r"^(?P<embankment_key>.+_\d+)_(?P<tier>\d+)_(?P<kind>shoulder|toe)$")


def get_tier_position_from_curve_name(curve_name: str) -> tuple[int, str]:
    match = CURVE_NAME_RE.match(curve_name)
    if match is None:
        raise ValueError(f"Invalid embankment curve name: {curve_name}")
    return int(match.group("tier")), match.group("kind")


def get_curve_between_start_end_lines(
    curve: rg.Curve,
    start_edge_points: tuple[Point3D, Point3D],
    end_edge_points: tuple[Point3D, Point3D],
) -> dict:
    split_items = split_curve_by_lines_and_match_endpoints(
        curve=curve,
        split_line_points=[start_edge_points, end_edge_points],
        target_line_points={
            "start": start_edge_points,
            "end": end_edge_points,
        },
        expected_count=3,
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
        raise ValueError("No curve found between start and end edge lines")

    result_curve = target_item["curve"]
    result_start = target_item["start"]
    result_end = target_item["end"]
    if "end" in target_item["start_matches"] and "start" in target_item["end_matches"]:
        result_curve.Reverse()
        result_start = target_item["end"]
        result_end = target_item["start"]
    return {
        "curve": result_curve,
        "start_point": result_start,
        "end_point": result_end,
    }


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
) -> dict[str, rg.Curve]:
    curve = const_curve_obj(curve)
    split_items = split_curve_by_lines_and_match_endpoints(
        curve=curve,
        split_line_points=[start_edge_points, end_edge_points],
        target_line_points={
            "start_edge": start_edge_points,
            "end_edge": end_edge_points,
        },
        expected_count=4,
    )

    result = {}
    for split_item in split_items:
        start = split_item["start"]
        end = split_item["end"]
        start_on_start_edge = "start_edge" in split_item["start_matches"]
        end_on_start_edge = "start_edge" in split_item["end_matches"]
        start_on_end_edge = "end_edge" in split_item["start_matches"]
        end_on_end_edge = "end_edge" in split_item["end_matches"]
        oriented_curve = split_item["curve"]

        if start_on_start_edge and end_on_start_edge:
            if get_distance_2D(end, start_U_abut_points[0]) < get_distance_2D(start, start_U_abut_points[0]):
                oriented_curve.Reverse()
            edge_items = split_curve_by_lines_and_match_endpoints(
                curve=oriented_curve,
                split_line_points=[
                    start_U_abut_points,
                    start_D_abut_points,
                ],
                target_line_points={},
                expected_count=3,
            )
            result["start_edge_U"] = edge_items[0]["curve"]
            result["start_edge_UD"] = edge_items[1]["curve"]
            result["start_edge_D"] = edge_items[2]["curve"]
        elif start_on_end_edge and end_on_end_edge:
            if get_distance_2D(end, end_U_abut_points[0]) < get_distance_2D(start, end_U_abut_points[0]):
                oriented_curve.Reverse()
            edge_items = split_curve_by_lines_and_match_endpoints(
                curve=oriented_curve,
                split_line_points=[
                    end_U_abut_points,
                    end_D_abut_points,
                ],
                target_line_points={},
                expected_count=3,
            )
            result["end_edge_U"] = edge_items[0]["curve"]
            result["end_edge_UD"] = edge_items[1]["curve"]
            result["end_edge_D"] = edge_items[2]["curve"]
        elif (
            (start_on_start_edge and end_on_end_edge)
            or (start_on_end_edge and end_on_start_edge)
        ):
            split_points = get_curve_polyline_points(oriented_curve)
            if len(split_points) < 2:
                split_points = [start, end]
            U_distance = sum(get_xy_distance_to_segment(point, U_parallel_points) for point in split_points) / len(split_points)
            D_distance = sum(get_xy_distance_to_segment(point, D_parallel_points) for point in split_points) / len(split_points)
            key = "U_parallel" if U_distance <= D_distance else "D_parallel"
            if get_xy_distance_to_segment(end, start_edge_points) < get_xy_distance_to_segment(start, start_edge_points):
                oriented_curve.Reverse()
            result[key] = oriented_curve
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

    expected_keys = {
        "start_edge_U",
        "start_edge_UD",
        "start_edge_D",
        "end_edge_U",
        "end_edge_UD",
        "end_edge_D",
        "U_parallel",
        "D_parallel",
    }
    missing_keys = expected_keys - set(result)
    if missing_keys:
        raise ValueError(f"Missing split boundary curves: {sorted(missing_keys)}")
    return result

def get_world_embankment_points(
    pavement_info: EmbankmentPaveInfo,
    pavement_bottom_points_dict: dict[str, list[float] | list[Point3D]],
    named_curves: dict[str, rg.Curve],
    wall_points_dict: dict[str, dict[str, list[Point3D]]],
    abut_points_dict: dict,
) -> dict[str, EdgePoints]:
    slope = pavement_info.slope.value
    start_U_slope = pavement_info.start_edge.U_slope
    start_D_slope = pavement_info.start_edge.D_slope
    start_edge_structure = pavement_info.start_edge.structure
    end_U_slope = pavement_info.end_edge.U_slope
    end_D_slope = pavement_info.end_edge.D_slope

    abut_points = {
        "start": {"U": {}, "D": {}},
        "end": {"U": {}, "D": {}},
    }
    if start_edge_structure.structure_type == "abutment":
        start_abut_points = abut_points_dict[start_edge_structure.structure_name]
        start_wing_dict = start_abut_points["wing_dict"]
        abut_points["start"]["U"]["wing_soil"] = start_wing_dict["U_wing_top_points"]["US"]
        abut_points["start"]["U"]["wing_bridge"] = start_wing_dict["U_wing_top_points"]["UB"]
        abut_points["start"]["D"]["wing_soil"] = start_wing_dict["D_wing_top_points"]["DS"]
        abut_points["start"]["D"]["wing_bridge"] = start_wing_dict["D_wing_top_points"]["DB"]
    else:
        raise ValueError(f"Unknown start edge structure: {start_edge_structure}")
    end_edge_structure = pavement_info.end_edge.structure
    if end_edge_structure.structure_type == "abutment":
        end_abut_points = abut_points_dict[end_edge_structure.structure_name]
        end_wing_dict = end_abut_points["wing_dict"]
        abut_points["end"]["U"]["wing_soil"] = end_wing_dict["U_wing_top_points"]["US"]
        abut_points["end"]["U"]["wing_bridge"] = end_wing_dict["U_wing_top_points"]["UB"]
        abut_points["end"]["D"]["wing_soil"] = end_wing_dict["D_wing_top_points"]["DS"]
        abut_points["end"]["D"]["wing_bridge"] = end_wing_dict["D_wing_top_points"]["DB"]
    else:
        raise ValueError(f"Unknown end edge structure: {end_edge_structure}")

    curves = {get_tier_position_from_curve_name(name): curve for name, curve in named_curves.items() if name.startswith(f"{pavement_info.name}_{pavement_info.num}_")}
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
        )
    
    tier_1_sholder_U_crv = const_polycurve_obj([const_point_obj(p) for p in pavement_bottom_points_dict["U_points"]])
    tier_1_sholder_D_crv = const_polycurve_obj([const_point_obj(p) for p in pavement_bottom_points_dict["D_points"]])
    tier_1_sholder_U_info = get_curve_between_start_end_lines(
        curve=tier_1_sholder_U_crv,
        start_edge_points=start_edge_points,
        end_edge_points=end_edge_points,
    )
    tier_1_sholder_D_info = get_curve_between_start_end_lines(
        curve=tier_1_sholder_D_crv,
        start_edge_points=start_edge_points,
        end_edge_points=end_edge_points,
    )
    tier_1_shoulder_curves = crv_dict.setdefault(1, {}).setdefault("shoulder", {})
    tier_1_shoulder_curves["U_parallel"] = tier_1_sholder_U_info["curve"]
    tier_1_shoulder_curves["D_parallel"] = tier_1_sholder_D_info["curve"]
    tier_1_shoulder_curves["start_edge_UD"] = const_polycurve_obj(
        [tier_1_sholder_U_info["start_point"], tier_1_sholder_D_info["start_point"]]
    )
    tier_1_shoulder_curves["end_edge_UD"] = const_polycurve_obj(
        [tier_1_sholder_U_info["end_point"], tier_1_sholder_D_info["end_point"]]
    )

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
    center_line_crv_2D = const_polycurve_obj(
        [center_point_pair(U_points_2D[i], D_points_2D[i]) for i in range(len(U_points_2D))]
    )

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
        "start_edge_U",
        "start_edge_D",
        "end_edge_U",
        "end_edge_D",
        "start_edge_UD",
        "end_edge_UD",
    ]
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

    edge_tier1_shoulder_points = {
        "start_edge_U": abut_points["start"]["U"]["wing_soil"],
        "start_edge_D": abut_points["start"]["D"]["wing_soil"],
        "end_edge_U": abut_points["end"]["U"]["wing_soil"],
        "end_edge_D": abut_points["end"]["D"]["wing_soil"],
    }
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

    for name in edge_names:
        points_counts = []
        for _, row in crv_df[crv_df["name"] == name].iterrows():
            points_counts.append(len(row["points"]))
        if len(set(points_counts)) > 1:
            raise ValueError(f"Point count mismatch for {name}: {points_counts}")
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
    
    def get_cross_section_slope(name_df, start_slope, end_slope):
        # tier1のtoeを使う。
        tier1_toe_distances = name_df[(name_df["tier"] == 1) & (name_df["kind"] == "toe")]["2Ddistances"].iloc[0]
        all_distance = tier1_toe_distances[-1]
        slopes = []
        for i in range(len(tier1_toe_distances)):
            distance_ratio = 0 if abs(all_distance) < DISTANCE_TOL else tier1_toe_distances[i] / all_distance
            this_slope = start_slope + (end_slope - start_slope) * distance_ratio
            slopes.append(this_slope)
        return slopes

    def get_cross_section_height_with_slope(name_df, slopes):
        name_df = name_df.copy()
        tier1_shoulder_points = name_df[(name_df["tier"] == 1) & (name_df["kind"] == "shoulder")]["points"].iloc[0]
        for i in range(len(tier1_shoulder_points)):
            tier1_shoulder_point = tier1_shoulder_points[i]
            slope = slopes[i]
            # 全てのtier, kindの点の中でzがstandard_base_z以外の点があるかと、距離の一覧を作る。
            has_known_z_points = []
            cross_section_distances = [0]
            max_tier = name_df["tier"].max()
            ordered_keys = [(1, "shoulder")]
            for tier in range(1, max_tier + 1):
                for kind in ["shoulder", "toe"]:
                    if kind == "shoulder" and tier == 1:
                        continue
                    row_mask = (name_df["tier"] == tier) & (name_df["kind"] == kind)
                    if name_df[row_mask].empty:
                        continue
                    this_point = name_df[row_mask]["points"].iloc[0][i]
                    this_distance = get_distance_2D(tier1_shoulder_point, this_point)
                    cross_section_distances.append(this_distance)
                    ordered_keys.append((tier, kind))
                    if abs(this_point.z - STANDARD_BASE_Z) > DISTANCE_TOL:
                        has_known_z_points.append((tier, kind, this_point))
            # cross_section_distancesは、法肩→のり尻→…の順に入っているが、スロープを持つのは法肩から法尻までのみ。
            section_distances = [
                cross_section_distances[2 * j + 1] - cross_section_distances[2 * j]
                for j in range(len(cross_section_distances) // 2)
            ]
            section_slopes = [slope] * len(section_distances)
            has_known_z_points = sorted(
                has_known_z_points,
                key=lambda x: ordered_keys.index((x[0], x[1])),
            )
            if len(has_known_z_points) > 0:
                start_tier = 1
                start_point = tier1_shoulder_point
                for tier, kind, point in has_known_z_points:
                    if kind == "shoulder":
                        last_tier = tier - 1
                    else:
                        last_tier = tier
                    sum_section_distance = sum(section_distances[start_tier - 1:last_tier])
                    if abs(sum_section_distance) < DISTANCE_TOL:
                        continue
                    z_gap = start_point.z - point.z
                    this_slope = sum_section_distance / z_gap
                    section_slopes[start_tier - 1:last_tier] = [this_slope] * (last_tier - start_tier + 1)
                    start_tier = tier
                    start_point = point

            for tier in range(1, max_tier + 1):
                shoulder_mask = (name_df["tier"] == tier) & (name_df["kind"] == "shoulder")
                toe_mask = (name_df["tier"] == tier) & (name_df["kind"] == "toe")
                if name_df[shoulder_mask].empty or name_df[toe_mask].empty:
                    continue
                shoulder_idx = name_df[shoulder_mask].index[0]
                toe_idx = name_df[toe_mask].index[0]
                shoulder_points = list(name_df.at[shoulder_idx, "points"])
                toe_points = list(name_df.at[toe_idx, "points"])
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
        return name_points_dict
    
    return {
        "U_parallel": get_points_with_name_df(crv_df[crv_df["name"] == "U_parallel"],slope,slope),
        "D_parallel": get_points_with_name_df(crv_df[crv_df["name"] == "D_parallel"],slope,slope),
        "start_edge_U": get_points_with_name_df(crv_df[crv_df["name"] == "start_edge_U"],slope,start_U_slope),
        "start_edge_UD": get_points_with_name_df(crv_df[crv_df["name"] == "start_edge_UD"],start_U_slope,start_D_slope),
        "start_edge_D": get_points_with_name_df(crv_df[crv_df["name"] == "start_edge_D"],start_D_slope,slope),
        "end_edge_U": get_points_with_name_df(crv_df[crv_df["name"] == "end_edge_U"],slope,end_U_slope),
        "end_edge_UD": get_points_with_name_df(crv_df[crv_df["name"] == "end_edge_UD"],end_U_slope,end_D_slope),
        "end_edge_D": get_points_with_name_df(crv_df[crv_df["name"] == "end_edge_D"],end_D_slope,slope),
    }

def main(initial_or_final: str, debug: bool = False):
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
    save_json_and_pickle(
        data=world_embankment_points_dict,
        folder_path=DIR,
        name=f"{Filenames.EMBANKMENT}_{Filenames.POINTS}",
    )

    if debug:
        bake_keys, bake_objs = get_keys_and_values_for_bake(world_embankment_points_dict)
        if len(bake_objs) == 0:
            raise ValueError("No embankment points were generated for debug bake")
        return bake_keys, bake_objs
    return None


if __name__ == "__main__":
    bake_keys, bake_objs = main("initial", debug=True)
