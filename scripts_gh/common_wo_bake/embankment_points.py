from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import Optional

import Rhino.Geometry as rg

from my_project.config.constants import DISTANCE_TOL
from my_project.config.file_names import Filenames
from my_project.config.locale_compat import normalize_lc_time
from my_project.config.paths import get_output_dir
from my_project.config.schemas.embankment_pavement_schemas import EmbankmentPaveInfo
from my_project.config.schemas.embankment_schemas import (
    CrossSectionInfo,
    EdgePoints,
    LocalTopBottomPointInfo,
)
from my_project.config.util_schemas import Point3D
from my_project.domain.abutment import get_abut_wing_named_points
from my_project.utils.bake import get_keys_and_values_for_bake
from my_project.domain.embankment import (
    get_edge_info,
    get_edge_structure,
)
from my_project.utils.geometry.points import (
    center_point_pair,
    get_distance_2D,
    get_distance_3D,
    get_xy_distance_to_segment,
    interpolate_point_3d,
    is_unknown_z_marker,
    point_with_unknown_z_marker,
    remove_near_duplicate_points,
    transform_local_point_to_world_vertical_plane,
)
from my_project.utils.geometry_gh.attributes import (
    get_curve_distance,
    get_curve_polyline_points,
    get_value_at_point_on_polyline,
    point3d_from_rg,
)
from my_project.utils.geometry_gh.const import (
    const_curve_obj,
    const_point_obj,
    const_vertical_srf_from_two_points,
)
from my_project.utils.geometry_gh.document import get_named_curves_on_layer
from my_project.utils.geometry_gh.intersect import (
    get_curve_intersections_with_vertical_plane,
    get_intersections_with_vertical_plane,
    get_nearest_projected_intersection_with_vertical_plane,
    get_polyline_intersections_with_vertical_plane,
)
from my_project.utils.io import load_from_pickle, save_json_and_pickle

normalize_lc_time()

CURVE_NAME_RE = re.compile(r"^(?P<embankment_key>.+_\d+)_(?P<tier>\d+)_(?P<kind>shoulder|toe)$")


@dataclass(frozen=True)
class EdgeAbutContext:
    edge: str
    edge_info: object
    structure: object
    wing_points: dict[str, Point3D]
    soil_line: tuple[Point3D, Point3D]
    side_lines: dict[str, tuple[Point3D, Point3D]]


def get_embankment_key(pavement_info: EmbankmentPaveInfo) -> str:
    return f"{pavement_info.name}_{pavement_info.num}"


def get_edge_abut_context(
    pavement_info: EmbankmentPaveInfo,
    abut_points_dict: dict,
    edge: str,
) -> Optional[EdgeAbutContext]:
    edge_info = get_edge_info(pavement_info, edge)
    structure = get_edge_structure(pavement_info, edge)
    if edge_info is None or structure is None or structure.structure_type != "abutment":
        return None
    wing_dict = abut_points_dict[structure.structure_name]["wing_dict"]
    wing_points = get_abut_wing_named_points(wing_dict)
    return EdgeAbutContext(
        edge=edge,
        edge_info=edge_info,
        structure=structure,
        wing_points=wing_points,
        soil_line=(wing_points["U_soil"], wing_points["D_soil"]),
        side_lines={
            "U": (wing_points["U_bridge"], wing_points["U_soil"]),
            "D": (wing_points["D_bridge"], wing_points["D_soil"]),
        },
    )


def get_bottom_points_at_sta(
    bottom_points_info: dict,
    STA: float,
) -> tuple[Point3D, Point3D]:
    STAs = [float(sta) for sta in bottom_points_info["STAs"]]
    U_points = bottom_points_info["U_points"]
    D_points = bottom_points_info["D_points"]
    if len(STAs) != len(U_points) or len(STAs) != len(D_points):
        raise ValueError(
            f"Pavement bottom point length mismatch: STAs={len(STAs)}, "
            f"U={len(U_points)}, D={len(D_points)}"
        )
    if len(STAs) < 2:
        raise ValueError("Need at least 2 pavement bottom STAs")
    if STA < STAs[0] - DISTANCE_TOL or STA > STAs[-1] + DISTANCE_TOL:
        raise ValueError(f"STA {STA} is outside pavement bottom range {STAs[0]} to {STAs[-1]}")

    for i in range(len(STAs) - 1):
        sta0 = STAs[i]
        sta1 = STAs[i + 1]
        if sta0 - DISTANCE_TOL <= STA <= sta1 + DISTANCE_TOL:
            if sta1 == sta0:
                raise ValueError(f"Duplicate pavement bottom STA: {sta0}")
            ratio = (STA - sta0) / (sta1 - sta0)
            return (
                interpolate_point_3d(U_points[i], U_points[i + 1], ratio),
                interpolate_point_3d(D_points[i], D_points[i + 1], ratio),
            )
    raise ValueError(f"Failed to find pavement bottom interval for STA {STA}")


def find_named_curve(
    named_curves: dict[str, rg.Curve],
    embankment_key: str,
    side: str,
    tier: int,
    point_kind: str,
) -> tuple[Optional[str], Optional[rg.Curve]]:
    candidates = [
        f"{embankment_key}_{side}_{tier}_{point_kind}",
        f"{embankment_key}_{tier}_{side}_{point_kind}",
        f"{embankment_key}_{tier}_{point_kind}",
    ]
    for name in candidates:
        if name in named_curves:
            return name, named_curves[name]
    return None, None


def get_wall_points_for_curve(
    pavement_info: EmbankmentPaveInfo,
    curve_spec: dict,
    wall_points_dict: dict,
) -> list[Point3D]:
    wall_points = []
    point_kind_by_position = {"法肩": "shoulder", "法尻": "toe"}
    point_prefix_by_attr = {"berm": "小段", "top": "上", "bottom": "下"}
    for wall_interference in pavement_info.wall_interferences or []:
        for target_attr in ["berm", "top", "bottom"]:
            target = getattr(wall_interference, target_attr)
            if target is None:
                continue
            target_key = f"{target.target_name}_{target.target_num}"
            if target_key != curve_spec["embankment_key"]:
                continue
            if target.target_tier != curve_spec["tier"]:
                continue
            if point_kind_by_position.get(target.target_position) != curve_spec["kind"]:
                continue
            prefix = (
                f"{wall_interference.wall_main_name}_"
                f"{wall_interference.wall_name}_"
                f"{point_prefix_by_attr[target_attr]}_"
            )
            matched = [
                (int(name.replace(prefix, "")), point)
                for name, point in wall_points_dict.items()
                if name.startswith(prefix)
            ]
            wall_points.extend(point for _, point in sorted(matched, key=lambda item: item[0]))
    return wall_points


def interpolate_unknown_z(points: list[dict]) -> list[Point3D]:
    if not points:
        return []
    polyline = rg.PolylineCurve([const_point_obj(item["point"]) for item in points])
    distances = [get_curve_distance(polyline, item["point"]) for item in points]
    known_distance_points = sorted(
        [
            (distance, item["point"])
            for distance, item in zip(distances, points)
            if item["z_known"]
        ],
        key=lambda item: item[0],
    )
    if not known_distance_points:
        return [item["point"] for item in points]
    output = []
    for distance, item in zip(distances, points):
        if item["z_known"]:
            output.append(item["point"])
            continue
        prev_known = max(
            [known for known in known_distance_points if known[0] <= distance],
            default=None,
            key=lambda known: known[0],
        )
        next_known = min(
            [known for known in known_distance_points if known[0] >= distance],
            default=None,
            key=lambda known: known[0],
        )
        if prev_known is None:
            z = next_known[1].z
        elif next_known is None:
            z = prev_known[1].z
        else:
            denom = next_known[0] - prev_known[0]
            ratio = 0 if abs(denom) < DISTANCE_TOL else (distance - prev_known[0]) / denom
            z0 = prev_known[1].z
            z1 = next_known[1].z
            z = z0 + (z1 - z0) * ratio
        point = item["point"]
        output.append(Point3D(point.x, point.y, z))
    return output


def get_abut_intersections_on_mixed_curve(
    curve_items: list[dict],
    wing_points: tuple[Point3D, Point3D],
) -> list[dict]:
    if len(curve_items) < 2:
        return []
    mixed_points = [point_with_unknown_z_marker(item) for item in curve_items]
    mixed_curve = rg.PolylineCurve([const_point_obj(point) for point in mixed_points])
    plane_srf = const_vertical_srf_from_two_points(
        wing_points[0],
        wing_points[1],
    )
    intersection_events = rg.Intersect.Intersection.CurveBrep(
        mixed_curve,
        plane_srf,
        DISTANCE_TOL,
    )
    if not intersection_events or len(intersection_events[2]) == 0:
        return []
    intersections = []
    for rg_point in intersection_events[2]:
        point = point3d_from_rg(rg_point)
        closest_segment_index = min(
            range(len(mixed_points) - 1),
            key=lambda i: rg.LineCurve(
                const_point_obj(mixed_points[i]),
                const_point_obj(mixed_points[i + 1]),
            ).PointAt(
                rg.LineCurve(
                    const_point_obj(mixed_points[i]),
                    const_point_obj(mixed_points[i + 1]),
                ).ClosestPoint(const_point_obj(point))[1]
            ).DistanceTo(const_point_obj(point)),
        )
        has_known_z = (
            curve_items[closest_segment_index]["z_known"]
            and curve_items[closest_segment_index + 1]["z_known"]
            and not is_unknown_z_marker(point.z)
        )
        intersections.append({"point": point, "has_known_z": has_known_z})
    return intersections


def get_abut_intersection_items_after_wall(
    *,
    curve_items: list[dict],
    curve: rg.Curve,
    pavement_info: EmbankmentPaveInfo,
    abut_points_dict: dict,
    curve_spec: dict,
) -> list[dict]:
    items = []
    for edge in ["start", "end"]:
        edge_context = get_edge_abut_context(pavement_info, abut_points_dict, edge)
        if edge_context is None:
            continue
        for side, side_points in edge_context.side_lines.items():
            intersections = get_abut_intersections_on_mixed_curve(curve_items, side_points)
            if not intersections:
                intersections = [
                    {"point": point, "has_known_z": False}
                    for point in get_intersections_with_vertical_plane(
                        curve,
                        side_points,
                    )
                ]
            intersection = min(
                intersections,
                key=lambda item: get_xy_distance_to_segment(item["point"], side_points),
                default=None,
            )
            if intersection is None:
                continue
            point = intersection["point"]
            items.append(
                {
                    "point": point,
                    "edge": edge,
                    "side": side,
                    "location": "abut",
                    "curve_spec": curve_spec,
                    "has_known_z": intersection["has_known_z"],
                    "source": f"{edge}_abut",
                }
            )
    return items


def get_section_kind_point(
    section: CrossSectionInfo,
    side: str,
    curve_spec: dict,
) -> Point3D:
    edge_points = section.U_points if side == "U" else section.D_points
    point_info = edge_points.points[curve_spec["tier"] - 1]
    return point_info.top if curve_spec["kind"] == "shoulder" else point_info.bottom


def get_parallel_edge_items(
    *,
    sections: list[CrossSectionInfo],
    curve: rg.Curve,
    curve_spec: dict,
    edge: str,
    edge_parallel_points: dict,
) -> list[dict]:
    section = sections[0] if edge == "start" else sections[-1]
    U_provisional = get_section_kind_point(section, "U", curve_spec)
    U_parallel_point = get_nearest_projected_intersection_with_vertical_plane(
        curve=curve,
        plane_points=(edge_parallel_points["U_point"], edge_parallel_points["D_point"]),
        z=U_provisional.z,
        anchor_point=edge_parallel_points["U_point"],
        context=f"{curve_spec['embankment_key']}/{edge}/U/{curve_spec['tier']}/{curve_spec['kind']}/parallel",
    )
    D_provisional = get_section_kind_point(section, "D", curve_spec)
    D_parallel_point = get_nearest_projected_intersection_with_vertical_plane(
        curve=curve,
        plane_points=(edge_parallel_points["U_point"], edge_parallel_points["D_point"]),
        z=D_provisional.z,
        anchor_point=edge_parallel_points["D_point"],
        context=f"{curve_spec['embankment_key']}/{edge}/D/{curve_spec['tier']}/{curve_spec['kind']}/parallel",
    )
    return [
        {
            "point": U_parallel_point,
            "z_known": True,
            "source": f"{edge}_parallel",
            "edge": edge,
            "side": "U",
            "location": "parallel",
        },
        {
            "point": D_parallel_point,
            "z_known": True,
            "source": f"{edge}_parallel",
            "edge": edge,
            "side": "D",
            "location": "parallel",
        },
    ]


def get_curve_segment_between_items(
    *,
    curve: rg.Curve,
    curve_items: list[dict],
    item0: dict,
    item1: dict,
    direction: str,
) -> list[dict]:
    curve_length = const_curve_obj(curve).GetLength()
    distance_items = [
        (get_curve_distance(curve, item["point"]), item)
        for item in curve_items
    ]
    distance0 = get_curve_distance(curve, item0["point"])
    distance1 = get_curve_distance(curve, item1["point"])
    if direction == "forward":
        span = (distance1 - distance0) % curve_length

        def get_offset(distance: float) -> float:
            return (distance - distance0) % curve_length

    elif direction == "backward":
        span = (distance0 - distance1) % curve_length

        def get_offset(distance: float) -> float:
            return (distance0 - distance) % curve_length

    else:
        raise ValueError(f"Invalid curve segment direction: {direction}")

    segment = [
        (get_offset(distance), item)
        for distance, item in distance_items
        if get_offset(distance) <= span + DISTANCE_TOL
    ]
    return [item for _, item in sorted(segment, key=lambda pair: pair[0])]


def choose_edge_curve_direction(
    *,
    curve: rg.Curve,
    U_parallel: dict,
    U_abut: dict,
    D_abut: dict,
    D_parallel: dict,
) -> str:
    controls = [U_parallel, U_abut, D_abut, D_parallel]
    curve_length = const_curve_obj(curve).GetLength()
    direction_lengths = {}
    for direction in ["forward", "backward"]:
        total = 0
        for item0, item1 in zip(controls, controls[1:]):
            distance0 = get_curve_distance(curve, item0["point"])
            distance1 = get_curve_distance(curve, item1["point"])
            total += (
                (distance1 - distance0) % curve_length
                if direction == "forward"
                else (distance0 - distance1) % curve_length
            )
        direction_lengths[direction] = total
    return min(direction_lengths, key=direction_lengths.get)


def get_edge_segment_items(
    *,
    curve: rg.Curve,
    curve_items: list[dict],
    edge: str,
    context: str,
) -> list[dict]:
    edge_items = [item for item in curve_items if item.get("edge") == edge]

    def find_items(side: str, location: str) -> list[dict]:
        return [
            item for item in edge_items
            if item.get("side") == side and item.get("location") == location
        ]

    def find_item(side: str, location: str) -> Optional[dict]:
        matches = [
            item for item in edge_items
            if item.get("side") == side and item.get("location") == location
        ]
        return matches[0] if matches else None

    U_parallel = find_item("U", "parallel")
    D_parallel = find_item("D", "parallel")
    U_abut_matches = find_items("U", "abut")
    D_abut_matches = find_items("D", "abut")
    U_abut = (
        min(U_abut_matches, key=lambda item: get_distance_2D(item["point"], U_parallel["point"]))
        if U_parallel is not None and U_abut_matches
        else None
    )
    D_abut = (
        min(D_abut_matches, key=lambda item: get_distance_2D(item["point"], D_parallel["point"]))
        if D_parallel is not None and D_abut_matches
        else None
    )
    if None in [U_parallel, U_abut, D_parallel, D_abut]:
        found = [
            f"{item.get('side')}_{item.get('location')}"
            for item in edge_items
            if item.get("location") in ["parallel", "abut"]
        ]
        raise ValueError(
            f"Missing edge control points: {context} {edge}; "
            f"found={found}"
        )

    direction = choose_edge_curve_direction(
        curve=curve,
        U_parallel=U_parallel,
        U_abut=U_abut,
        D_abut=D_abut,
        D_parallel=D_parallel,
    )
    U_segment = get_curve_segment_between_items(
        curve=curve,
        curve_items=curve_items,
        item0=U_parallel,
        item1=U_abut,
        direction=direction,
    )
    middle_segment = get_curve_segment_between_items(
        curve=curve,
        curve_items=curve_items,
        item0=U_abut,
        item1=D_abut,
        direction=direction,
    )
    D_segment = get_curve_segment_between_items(
        curve=curve,
        curve_items=curve_items,
        item0=D_abut,
        item1=D_parallel,
        direction=direction,
    )
    output = []
    for segment in [U_segment, middle_segment, D_segment]:
        for item in segment:
            if output and get_distance_3D(output[-1]["point"], item["point"]) < DISTANCE_TOL:
                continue
            output.append(item)
    return output


def insert_cross_section_points(
    points: list[Point3D],
    *,
    bottom_points_info: dict,
    local_sections: list[CrossSectionInfo],
) -> list[Point3D]:
    if len(points) < 2:
        return points
    curve = rg.PolylineCurve([const_point_obj(point) for point in points])
    inserted = list(points)
    for local_section in local_sections:
        world_U_bottom, world_D_bottom = get_bottom_points_at_sta(
            bottom_points_info=bottom_points_info,
            STA=local_section.STA,
        )
        cutter_srf = const_vertical_srf_from_two_points(world_U_bottom, world_D_bottom)
        intersection_events = rg.Intersect.Intersection.CurveBrep(
            curve,
            cutter_srf,
            DISTANCE_TOL,
        )
        if not intersection_events or len(intersection_events[2]) == 0:
            continue
        inserted.extend(point3d_from_rg(point) for point in intersection_events[2])
    inserted = remove_near_duplicate_points(inserted)
    inserted = sorted(inserted, key=lambda point: get_curve_distance(curve, point))
    return interpolate_unknown_z(
        [
            {"point": point, "z_known": abs(point.z) > DISTANCE_TOL, "source": "section_insert"}
            for point in inserted
        ]
    )


def get_abut_known_points_for_curve(
    *,
    pavement_info: EmbankmentPaveInfo,
    abut_points_dict: dict,
    curve: rg.Curve,
    curve_spec: dict,
    edge: str,
) -> list[dict]:
    edge_context = get_edge_abut_context(pavement_info, abut_points_dict, edge)
    if edge_context is None:
        return []
    intersections = get_intersections_with_vertical_plane(curve, edge_context.soil_line, z=0)
    known_points = []
    for point in intersections:
        U_wing, D_wing = edge_context.soil_line
        if get_distance_2D(point, U_wing) <= get_distance_2D(point, D_wing):
            anchor = U_wing
            slope = edge_context.edge_info.U_slope
        else:
            anchor = D_wing
            slope = edge_context.edge_info.D_slope
        if slope is None:
            continue
        z = anchor.z - get_distance_2D(anchor, point) / slope
        known_points.append(
            {
                "point": Point3D(point.x, point.y, z),
                "z_known": True,
                "source": f"{edge}_abut",
            }
        )
    return known_points


def get_required_curve_specs(local_sections: list[CrossSectionInfo]) -> list[dict]:
    max_tier = max(
        max(len(section.U_points.points), len(section.D_points.points))
        for section in local_sections
    )
    specs = []
    for tier in range(1, max_tier + 1):
        if tier != 1:
            specs.append({"tier": tier, "kind": "shoulder"})
        specs.append({"tier": tier, "kind": "toe"})
    return specs


def get_edge_curve_points(
    *,
    pavement_info: EmbankmentPaveInfo,
    sections: list[CrossSectionInfo],
    named_curves: dict[str, rg.Curve],
    wall_points_dict: dict,
    abut_points_dict: dict,
    parallel_points: dict,
) -> dict:
    embankment_key = get_embankment_key(pavement_info)

    prepared_curves = []
    for spec in get_required_curve_specs(sections):
        curve_name, curve = find_named_curve(
            named_curves=named_curves,
            embankment_key=embankment_key,
            side="",
            tier=spec["tier"],
            point_kind=spec["kind"],
        )
        if curve is None:
            candidates = [
                f"{embankment_key}_{spec['tier']}_{spec['kind']}",
                f"{embankment_key}__{spec['tier']}_{spec['kind']}",
                f"{embankment_key}_{spec['tier']}__{spec['kind']}",
            ]
            available = sorted(
                name for name in named_curves
                if name.startswith(f"{embankment_key}_")
            )
            raise ValueError(
                "Missing required embankment edge curve: "
                f"embankment={embankment_key}, tier={spec['tier']}, kind={spec['kind']}, "
                f"candidates={candidates}, available={available}"
            )
        curve_spec = {
            "embankment_key": embankment_key,
            "tier": spec["tier"],
            "kind": spec["kind"],
        }
        curve_items = sorted(
            [
                {"point": point, "z_known": False, "source": "input_vertex"}
                for point in get_curve_polyline_points(curve)
            ],
            key=lambda item: get_curve_distance(curve, item["point"]),
        )
        wall_points = get_wall_points_for_curve(
            pavement_info=pavement_info,
            curve_spec=curve_spec,
            wall_points_dict=wall_points_dict,
        )
        curve_items = curve_items + [
            {"point": point, "z_known": True, "source": "wall"}
            for point in wall_points
        ]
        abut_items = get_abut_intersection_items_after_wall(
            curve_items=curve_items,
            curve=curve,
            pavement_info=pavement_info,
            abut_points_dict=abut_points_dict,
            curve_spec=curve_spec,
        )
        prepared_curves.append(
            {
                "curve_name": curve_name,
                "curve": curve,
                "spec": curve_spec,
                "curve_items": curve_items,
                "abut_items": abut_items,
            }
        )

    edge_curve_points = {}
    for prepared in prepared_curves:
        curve = prepared["curve"]
        for edge in ["start", "end"]:
            parallel_items = get_parallel_edge_items(
                sections=sections,
                curve=curve,
                curve_spec=prepared["spec"],
                edge=edge,
                edge_parallel_points=parallel_points[edge],
            )
            curve_items = prepared["curve_items"] + parallel_items + [
                {
                    "point": item["point"],
                    "z_known": item["has_known_z"],
                    "source": item["source"],
                    "edge": item["edge"],
                    "side": item["side"],
                    "location": "abut",
                }
                for item in prepared["abut_items"]
                if item["edge"] == edge
            ]
            curve_items = sorted(curve_items, key=lambda item: get_curve_distance(curve, item["point"]))
            segment_items = get_edge_segment_items(
                curve=curve,
                curve_items=curve_items,
                edge=edge,
                context=prepared["curve_name"],
            )
            if not segment_items:
                continue
            points = interpolate_unknown_z(segment_items)
            point_sources = [
                {
                    "source": item.get("source"),
                    "location": item.get("location"),
                    "side": item.get("side"),
                }
                for item in segment_items
            ]
            edge_curve_points[f"{prepared['curve_name']}_{edge}"] = {
                "tier": prepared["spec"]["tier"],
                "kind": prepared["spec"]["kind"],
                "edge": edge,
                "points": points,
                "point_sources": point_sources,
            }
    return align_edge_curve_points(
        edge_curve_points=edge_curve_points,
        pavement_info=pavement_info,
        abut_points_dict=abut_points_dict,
    )


def transform_local_point_with_optional_curve_xy(
    *,
    local_U_base: Point3D,
    local_D_base: Point3D,
    world_U_bottom: Point3D,
    world_D_bottom: Point3D,
    local_point: Point3D,
    named_curves: dict[str, rg.Curve],
    embankment_key: str,
    side: str,
    tier: int,
    point_kind: str,
) -> Point3D:
    provisional_point = transform_local_point_to_world_vertical_plane(
        local_points=[local_U_base, local_D_base],
        world_points=[world_U_bottom, world_D_bottom],
        local_target_point=local_point,
        local_z_base_point=local_U_base if side == "U" else local_D_base,
        world_z_base_point=world_U_bottom if side == "U" else world_D_bottom,
    )
    curve_name, curve = find_named_curve(
        named_curves=named_curves,
        embankment_key=embankment_key,
        side=side,
        tier=tier,
        point_kind=point_kind,
    )
    if curve is None:
        return provisional_point
    return get_nearest_projected_intersection_with_vertical_plane(
        curve=curve,
        plane_points=(world_U_bottom, world_D_bottom),
        z=provisional_point.z,
        anchor_point=world_U_bottom if side == "U" else world_D_bottom,
        context=f"{embankment_key}/{side}/{tier}/{point_kind}/{curve_name}",
    )


def transform_local_top_bottom_point(
    *,
    local_U_base: Point3D,
    local_D_base: Point3D,
    world_U_bottom: Point3D,
    world_D_bottom: Point3D,
    local_point_info: LocalTopBottomPointInfo,
    named_curves: dict[str, rg.Curve],
    embankment_key: str,
    side: str,
    tier: int,
) -> LocalTopBottomPointInfo:
    return LocalTopBottomPointInfo(
        top=transform_local_point_with_optional_curve_xy(
            local_U_base=local_U_base,
            local_D_base=local_D_base,
            world_U_bottom=world_U_bottom,
            world_D_bottom=world_D_bottom,
            local_point=local_point_info.top,
            named_curves=named_curves,
            embankment_key=embankment_key,
            side=side,
            tier=tier,
            point_kind="shoulder",
        ),
        bottom=transform_local_point_with_optional_curve_xy(
            local_U_base=local_U_base,
            local_D_base=local_D_base,
            world_U_bottom=world_U_bottom,
            world_D_bottom=world_D_bottom,
            local_point=local_point_info.bottom,
            named_curves=named_curves,
            embankment_key=embankment_key,
            side=side,
            tier=tier,
            point_kind="toe",
        ),
    )


def transform_edge_points(
    *,
    local_edge_points: EdgePoints,
    local_U_base: Point3D,
    local_D_base: Point3D,
    world_U_bottom: Point3D,
    world_D_bottom: Point3D,
    named_curves: dict[str, rg.Curve],
    embankment_key: str,
    side: str,
) -> EdgePoints:
    points = [
        transform_local_top_bottom_point(
            local_U_base=local_U_base,
            local_D_base=local_D_base,
            world_U_bottom=world_U_bottom,
            world_D_bottom=world_D_bottom,
            local_point_info=point_info,
            named_curves=named_curves,
            embankment_key=embankment_key,
            side=side,
            tier=i + 1,
        )
        for i, point_info in enumerate(local_edge_points.points)
    ]

    wall_points = None
    if local_edge_points.wall_points is not None:
        wall_points = [
            transform_local_top_bottom_point(
                local_U_base=local_U_base,
                local_D_base=local_D_base,
                world_U_bottom=world_U_bottom,
                world_D_bottom=world_D_bottom,
                local_point_info=point_info,
                named_curves={},
                embankment_key=embankment_key,
                side=side,
                tier=i + 1,
            )
            for i, point_info in enumerate(local_edge_points.wall_points)
        ]

    return replace(
        local_edge_points,
        points=points,
        wall_points=wall_points,
    )


def get_world_cross_section(
    *,
    local_section: CrossSectionInfo,
    world_U_bottom: Point3D,
    world_D_bottom: Point3D,
    named_curves: dict[str, rg.Curve],
    embankment_key: str,
) -> CrossSectionInfo:
    local_U_base = local_section.U_points.points[0].top
    local_D_base = local_section.D_points.points[0].top
    return CrossSectionInfo(
        STA=local_section.STA,
        U_points=transform_edge_points(
            local_edge_points=local_section.U_points,
            local_U_base=local_U_base,
            local_D_base=local_D_base,
            world_U_bottom=world_U_bottom,
            world_D_bottom=world_D_bottom,
            named_curves=named_curves,
            embankment_key=embankment_key,
            side="U",
        ),
        D_points=transform_edge_points(
            local_edge_points=local_section.D_points,
            local_U_base=local_U_base,
            local_D_base=local_D_base,
            world_U_bottom=world_U_bottom,
            world_D_bottom=world_D_bottom,
            named_curves=named_curves,
            embankment_key=embankment_key,
            side="D",
        ),
    )


def get_parallel_points(
    pavement_info: EmbankmentPaveInfo,
    bottom_points_info: dict,
    abut_points_dict: dict,
) -> dict:
    parallel_points = {}
    edge_defs = [
        ("start", 0),
        ("end", -1),
    ]
    for edge_name, index in edge_defs:
        edge_context = get_edge_abut_context(pavement_info, abut_points_dict, edge_name)
        if edge_context is None:
            continue
        U_curve = rg.PolylineCurve([const_point_obj(point) for point in bottom_points_info["U_points"]])
        D_curve = rg.PolylineCurve([const_point_obj(point) for point in bottom_points_info["D_points"]])
        fallback_U = bottom_points_info["U_points"][index]
        fallback_D = bottom_points_info["D_points"][index]
        U_intersections = get_curve_intersections_with_vertical_plane(U_curve, edge_context.soil_line)
        D_intersections = get_curve_intersections_with_vertical_plane(D_curve, edge_context.soil_line)
        if not U_intersections or not D_intersections:
            raise ValueError(f"Failed to find parallel point on abut cut: {get_embankment_key(pavement_info)} {edge_name}")
        U_point = min(U_intersections, key=lambda point: get_distance_2D(point, fallback_U))
        D_point = min(D_intersections, key=lambda point: get_distance_2D(point, fallback_D))
        STAs = [float(STA) for STA in bottom_points_info["STAs"]]
        U_STA = get_value_at_point_on_polyline(bottom_points_info["U_points"], STAs, U_point)
        D_STA = get_value_at_point_on_polyline(bottom_points_info["D_points"], STAs, D_point)
        parallel_points[edge_name] = {
            "structure": edge_context.edge_info.structure,
            "STA": (U_STA + D_STA) / 2,
            "U_point": U_point,
            "D_point": D_point,
            "U_slope": edge_context.edge_info.U_slope,
            "D_slope": edge_context.edge_info.D_slope,
        }
    return parallel_points


def get_parallel_point_from_edge_curves(
    edge_curves: dict,
    *,
    edge: str,
    tier: int,
    kind: str,
    side: str,
) -> Optional[Point3D]:
    for edge_curve in edge_curves.values():
        if (
            edge_curve.get("edge") != edge
            or edge_curve.get("tier") != tier
            or edge_curve.get("kind") != kind
        ):
            continue
        for point, source in zip(edge_curve["points"], edge_curve["point_sources"]):
            if source.get("location") == "parallel" and source.get("side") == side:
                return point
    return None


def interpolate_edge_points_by_sta(points0: EdgePoints, points1: EdgePoints, ratio: float) -> EdgePoints:
    point_infos = []
    for point_info0, point_info1 in zip(points0.points, points1.points):
        point_infos.append(
            LocalTopBottomPointInfo(
                top=interpolate_point_3d(point_info0.top, point_info1.top, ratio),
                bottom=interpolate_point_3d(point_info0.bottom, point_info1.bottom, ratio),
            )
        )
    return replace(points0, points=point_infos)


def interpolate_section_by_sta(sections: list[CrossSectionInfo], STA: float) -> CrossSectionInfo:
    sorted_sections = sorted(sections, key=lambda section: section.STA)
    if STA <= sorted_sections[0].STA + DISTANCE_TOL:
        return replace(sorted_sections[0], STA=STA)
    if STA >= sorted_sections[-1].STA - DISTANCE_TOL:
        return replace(sorted_sections[-1], STA=STA)
    for section0, section1 in zip(sorted_sections, sorted_sections[1:]):
        if section0.STA - DISTANCE_TOL <= STA <= section1.STA + DISTANCE_TOL:
            denom = section1.STA - section0.STA
            ratio = 0 if abs(denom) < DISTANCE_TOL else (STA - section0.STA) / denom
            return CrossSectionInfo(
                STA=STA,
                U_points=interpolate_edge_points_by_sta(section0.U_points, section1.U_points, ratio),
                D_points=interpolate_edge_points_by_sta(section0.D_points, section1.D_points, ratio),
            )
    raise ValueError(f"Failed to interpolate section at STA={STA}")


def set_section_point(section: CrossSectionInfo, side: str, tier: int, kind: str, point: Point3D) -> CrossSectionInfo:
    edge_points = section.U_points if side == "U" else section.D_points
    point_infos = list(edge_points.points)
    point_info = point_infos[tier - 1]
    point_infos[tier - 1] = (
        replace(point_info, top=point)
        if kind == "shoulder"
        else replace(point_info, bottom=point)
    )
    new_edge_points = replace(edge_points, points=point_infos)
    return (
        replace(section, U_points=new_edge_points)
        if side == "U"
        else replace(section, D_points=new_edge_points)
    )


def refine_section_points_on_named_curves(
    section: CrossSectionInfo,
    *,
    named_curves: dict[str, rg.Curve],
    embankment_key: str,
    bottom_points_info: dict,
) -> CrossSectionInfo:
    U_bottom, D_bottom = get_bottom_points_at_sta(bottom_points_info, section.STA)
    output = section
    for spec in get_required_curve_specs([section]):
        for side in ["U", "D"]:
            curve_name, curve = find_named_curve(
                named_curves=named_curves,
                embankment_key=embankment_key,
                side=side,
                tier=spec["tier"],
                point_kind=spec["kind"],
            )
            if curve is None:
                curve_name, curve = find_named_curve(
                    named_curves=named_curves,
                    embankment_key=embankment_key,
                    side="",
                    tier=spec["tier"],
                    point_kind=spec["kind"],
                )
            if curve is None:
                continue
            provisional = get_section_kind_point(output, side, spec)
            point = get_nearest_projected_intersection_with_vertical_plane(
                curve=curve,
                plane_points=(U_bottom, D_bottom),
                z=provisional.z,
                anchor_point=U_bottom if side == "U" else D_bottom,
                context=f"{embankment_key}/{section.STA}/{side}/{spec['tier']}/{spec['kind']}/section-align",
            )
            output = set_section_point(output, side, spec["tier"], spec["kind"], point)
    return output


def insert_parallel_sections_from_curve_vertices(
    sections: list[CrossSectionInfo],
    *,
    named_curves: dict[str, rg.Curve],
    embankment_key: str,
    bottom_points_info: dict,
) -> list[CrossSectionInfo]:
    STAs = [section.STA for section in sections]
    bottom_STAs = [float(STA) for STA in bottom_points_info["STAs"]]
    center_points = [
        Point3D(
            x=(U_point.x + D_point.x) / 2,
            y=(U_point.y + D_point.y) / 2,
            z=0,
        )
        for U_point, D_point in zip(bottom_points_info["U_points"], bottom_points_info["D_points"])
    ]
    vertex_constraints = []
    for spec in get_required_curve_specs(sections):
        curve_name, curve = find_named_curve(
            named_curves=named_curves,
            embankment_key=embankment_key,
            side="",
            tier=spec["tier"],
            point_kind=spec["kind"],
        )
        if curve is None:
            continue
        for point in get_curve_polyline_points(curve):
            STA = get_value_at_point_on_polyline(
                center_points,
                bottom_STAs,
                Point3D(point.x, point.y, 0),
            )
            base_section = interpolate_section_by_sta(sections, STA)
            U_bottom, D_bottom = get_bottom_points_at_sta(bottom_points_info, STA)
            side = "U" if get_distance_2D(point, U_bottom) <= get_distance_2D(point, D_bottom) else "D"
            z_base = get_section_kind_point(base_section, side, spec)
            vertex_constraints.append(
                {
                    "STA": STA,
                    "side": side,
                    "tier": spec["tier"],
                    "kind": spec["kind"],
                    "point": Point3D(point.x, point.y, z_base.z),
                }
            )
            if all(abs(STA - existing_STA) > DISTANCE_TOL for existing_STA in STAs):
                STAs.append(STA)
    output_sections = []
    for STA in sorted(STAs):
        section = interpolate_section_by_sta(sections, STA)
        section = refine_section_points_on_named_curves(
            section,
            named_curves=named_curves,
            embankment_key=embankment_key,
            bottom_points_info=bottom_points_info,
        )
        for constraint in vertex_constraints:
            if abs(constraint["STA"] - STA) > DISTANCE_TOL:
                continue
            section = set_section_point(
                section,
                constraint["side"],
                constraint["tier"],
                constraint["kind"],
                constraint["point"],
            )
        output_sections.append(section)
    return output_sections


def replace_section_edge_with_parallel_points(
    section: CrossSectionInfo,
    *,
    edge_curves: dict,
    edge_parallel_points: dict,
    edge: str,
    STA: float,
) -> CrossSectionInfo:
    def replace_edge_points(edge_points: EdgePoints, side: str) -> EdgePoints:
        points = []
        for i, point_info in enumerate(edge_points.points):
            tier = i + 1
            top = (
                edge_parallel_points.get(f"{side}_point")
                if tier == 1
                else (
                    get_parallel_point_from_edge_curves(
                        edge_curves,
                        edge=edge,
                        tier=tier,
                        kind="shoulder",
                        side=side,
                    )
                    or point_info.top
                )
            )
            bottom = (
                get_parallel_point_from_edge_curves(
                    edge_curves,
                    edge=edge,
                    tier=tier,
                    kind="toe",
                    side=side,
                )
                or point_info.bottom
            )
            points.append(LocalTopBottomPointInfo(top=top, bottom=bottom))
        return replace(edge_points, points=points)

    return replace(
        section,
        STA=STA,
        U_points=replace_edge_points(section.U_points, "U"),
        D_points=replace_edge_points(section.D_points, "D"),
    )


def add_alignment_points_to_edge_curve(edge_curve: dict, alignment_points: list[Point3D]) -> dict:
    base_curve = rg.PolylineCurve([const_point_obj(point) for point in edge_curve["points"]])

    base_items = [
        {
            "point": point,
            "z_known": source.get("source") in ["wall"] or source.get("location") in ["parallel", "abut"],
            "source": source.get("source"),
            "location": source.get("location"),
            "side": source.get("side"),
        }
        for point, source in zip(edge_curve["points"], edge_curve["point_sources"])
    ]
    for point in alignment_points:
        if all(get_distance_3D(point, item["point"]) > DISTANCE_TOL for item in base_items):
            base_items.append(
                {
                    "point": point,
                    "z_known": False,
                    "source": "edge_alignment",
                    "location": "alignment",
                    "side": None,
                }
            )
    U_parallel_items = [
        item for item in base_items
        if item.get("location") == "parallel" and item.get("side") == "U"
    ]
    D_parallel_items = [
        item for item in base_items
        if item.get("location") == "parallel" and item.get("side") == "D"
    ]
    if U_parallel_items and D_parallel_items:
        U_parallel = U_parallel_items[0]
        D_parallel = D_parallel_items[0]
        middle_items = [
            item for item in base_items
            if (
                item is not U_parallel
                and item is not D_parallel
                and get_distance_3D(item["point"], U_parallel["point"]) > DISTANCE_TOL
                and get_distance_3D(item["point"], D_parallel["point"]) > DISTANCE_TOL
            )
        ]
        middle_items = sorted(middle_items, key=lambda item: get_curve_distance(base_curve, item["point"]))
        base_items = [U_parallel] + middle_items + [D_parallel]
    else:
        base_items = sorted(base_items, key=lambda item: get_curve_distance(base_curve, item["point"]))
    points = interpolate_unknown_z(base_items)
    return {
        **edge_curve,
        "points": points,
        "point_sources": [
            {
                "source": item.get("source"),
                "location": item.get("location"),
                "side": item.get("side"),
            }
            for item in base_items
        ],
    }


def align_edge_curve_points(
    edge_curve_points: dict,
    pavement_info: EmbankmentPaveInfo,
    abut_points_dict: dict,
) -> dict:
    aligned = dict(edge_curve_points)
    base_edge_points = {
        name: list(edge_curve["points"])
        for name, edge_curve in edge_curve_points.items()
    }
    for edge in ["start", "end"]:
        edge_context = get_edge_abut_context(pavement_info, abut_points_dict, edge)
        if edge_context is None:
            continue
        wing_points = edge_context.wing_points
        edge_names = [
            name for name, edge_curve in aligned.items()
            if edge_curve.get("edge") == edge
        ]
        if len(edge_names) < 2:
            continue
        U_soil = wing_points["U_soil"]
        D_soil = wing_points["D_soil"]
        cutters = []
        for name in edge_names:
            for point in base_edge_points[name]:
                side_anchor = (
                    U_soil
                    if get_distance_2D(point, U_soil) <= get_distance_2D(point, D_soil)
                    else D_soil
                )
                if get_distance_2D(point, side_anchor) > DISTANCE_TOL:
                    cutters.append((side_anchor, point))

        for name in edge_names:
            additions = []
            for cutter in cutters:
                additions.extend(
                    get_polyline_intersections_with_vertical_plane(
                        base_edge_points[name],
                        cutter,
                    )
                )
            aligned[name] = add_alignment_points_to_edge_curve(aligned[name], additions)
    return aligned


def get_output_sections(
    sections: list[CrossSectionInfo],
    pavement_info: EmbankmentPaveInfo,
    parallel_points: dict,
    edge_curves: dict,
) -> list[CrossSectionInfo]:
    def is_abut_edge(edge: str) -> bool:
        edge_structure = get_edge_structure(pavement_info, edge)
        return edge_structure is not None and edge_structure.structure_type == "abutment"

    output_sections = list(sections)
    if is_abut_edge("start") and "start" in parallel_points:
        cut_STA = parallel_points["start"]["STA"]
        output_sections = [
            section for section in output_sections
            if section.STA >= cut_STA - DISTANCE_TOL
        ]
        if sections:
            output_sections.insert(
                0,
                replace_section_edge_with_parallel_points(
                    sections[0],
                    edge_curves=edge_curves,
                    edge_parallel_points=parallel_points["start"],
                    edge="start",
                    STA=cut_STA,
                ),
            )
    if is_abut_edge("end") and "end" in parallel_points:
        cut_STA = parallel_points["end"]["STA"]
        output_sections = [
            section for section in output_sections
            if section.STA <= cut_STA + DISTANCE_TOL
        ]
        if sections:
            output_sections.append(
                replace_section_edge_with_parallel_points(
                    sections[-1],
                    edge_curves=edge_curves,
                    edge_parallel_points=parallel_points["end"],
                    edge="end",
                    STA=cut_STA,
                )
            )
    return output_sections


def get_world_embankment_points(
    pavement_infos: list[EmbankmentPaveInfo],
    local_embankment_points_dict: dict,
    pavement_bottom_points_dict: dict,
    named_curves: dict[str, rg.Curve],
    wall_points_dict: dict,
    abut_points_dict: dict,
) -> dict:
    world_embankment_points_dict = {}

    for pavement_info in pavement_infos:
        embankment_key = get_embankment_key(pavement_info)
        if embankment_key not in local_embankment_points_dict:
            raise KeyError(f"Missing local embankment points: {embankment_key}")
        if embankment_key not in pavement_bottom_points_dict:
            raise KeyError(f"Missing pavement bottom points: {embankment_key}")

        bottom_points_info = pavement_bottom_points_dict[embankment_key]
        sections = []
        for local_section in local_embankment_points_dict[embankment_key]:
            world_U_bottom, world_D_bottom = get_bottom_points_at_sta(
                bottom_points_info=bottom_points_info,
                STA=local_section.STA,
            )
            sections.append(
                get_world_cross_section(
                    local_section=local_section,
                    world_U_bottom=world_U_bottom,
                    world_D_bottom=world_D_bottom,
                    named_curves=named_curves,
                    embankment_key=embankment_key,
                )
            )
        sections = insert_parallel_sections_from_curve_vertices(
            sections,
            named_curves=named_curves,
            embankment_key=embankment_key,
            bottom_points_info=bottom_points_info,
        )
        parallel_points = get_parallel_points(
            pavement_info=pavement_info,
            bottom_points_info=bottom_points_info,
            abut_points_dict=abut_points_dict,
        )
        edge_curves = get_edge_curve_points(
            pavement_info=pavement_info,
            sections=sections,
            named_curves=named_curves,
            wall_points_dict=wall_points_dict,
            abut_points_dict=abut_points_dict,
            parallel_points=parallel_points,
        )

        abut_wing_points = {}
        for edge in ["start", "end"]:
            edge_context = get_edge_abut_context(pavement_info, abut_points_dict, edge)
            if edge_context is not None:
                abut_wing_points[edge] = edge_context.wing_points
        world_embankment_points_dict[embankment_key] = {
            "sections": get_output_sections(
                sections,
                pavement_info,
                parallel_points,
                edge_curves,
            ),
            "edge_curves": edge_curves,
            "parallel_points": parallel_points,
            "abut_wing_points": abut_wing_points,
        }
    return world_embankment_points_dict


def get_debug_crvs(world_embankment_points_dict: dict) -> list[rg.PolylineCurve]:
    crvs = []
    for embankment_info in world_embankment_points_dict.values():
        for edge_curve in embankment_info.get("edge_curves", {}).values():
            points = edge_curve["points"]
            if len(points) < 3:
                continue
            rg_points = [const_point_obj(point) for point in points]
            rg_points.append(rg_points[0])
            crvs.append(rg.PolylineCurve(rg_points))
        for parallel_info in embankment_info.get("parallel_points", {}).values():
            crvs.append(
                rg.PolylineCurve(
                    [
                        const_point_obj(parallel_info["U_point"]),
                        const_point_obj(parallel_info["D_point"]),
                    ]
                )
            )
        sections = embankment_info.get("sections", [])
        if len(sections) == 0:
            continue
        max_tier = max(
            max(len(section.U_points.points), len(section.D_points.points))
            for section in sections
        )
        for tier_index in range(max_tier):
            for kind in ["shoulder", "toe"]:
                U_points = []
                D_points = []
                for section in sections:
                    if (
                        tier_index >= len(section.U_points.points)
                        or tier_index >= len(section.D_points.points)
                    ):
                        continue
                    if kind == "shoulder":
                        U_points.append(section.U_points.points[tier_index].top)
                        D_points.append(section.D_points.points[tier_index].top)
                    else:
                        U_points.append(section.U_points.points[tier_index].bottom)
                        D_points.append(section.D_points.points[tier_index].bottom)
                if len(U_points) < 2 or len(D_points) < 2:
                    continue
                points = U_points + list(reversed(D_points))
                rg_points = [const_point_obj(point) for point in points]
                rg_points.append(rg_points[0])
                crvs.append(rg.PolylineCurve(rg_points))
    return crvs


def get_edge_curve_split_points(edge_curve: dict) -> dict[str, list[Point3D]]:
    points = edge_curve["points"]
    sources = edge_curve["point_sources"]

    def find_index(location: str, side: str) -> Optional[int]:
        for i, source in enumerate(sources):
            if source.get("location") == location and source.get("side") == side:
                return i
        return None

    U_abut_i = find_index("abut", "U")
    D_abut_i = find_index("abut", "D")
    if U_abut_i is None or D_abut_i is None:
        return {
            "U": points,
            "U-D": points,
            "D": points,
        }
    if U_abut_i > D_abut_i:
        U_abut_i, D_abut_i = D_abut_i, U_abut_i
    return {
        "U": points[: U_abut_i + 1],
        "U-D": points[U_abut_i : D_abut_i + 1],
        "D": points[D_abut_i:],
    }


def ensure_tier_dict(parent: dict, tier: int) -> dict:
    tier_key = str(tier)
    if tier_key not in parent:
        parent[tier_key] = {}
    return parent[tier_key]


def build_saved_parallel_points(
    sections: list[CrossSectionInfo],
) -> dict:
    parallel = {}
    if not sections:
        return parallel
    max_tier = max(
        max(len(section.U_points.points), len(section.D_points.points))
        for section in sections
    )
    for tier_index in range(max_tier):
        tier = tier_index + 1
        tier_dict = ensure_tier_dict(parallel, tier)
        U_shoulder_points = []
        U_toe_points = []
        D_shoulder_points = []
        D_toe_points = []
        for section in sections:
            if (
                tier_index >= len(section.U_points.points)
                or tier_index >= len(section.D_points.points)
            ):
                continue
            U_info = section.U_points.points[tier_index]
            D_info = section.D_points.points[tier_index]
            U_shoulder_points.append(U_info.top)
            U_toe_points.append(U_info.bottom)
            D_shoulder_points.append(D_info.top)
            D_toe_points.append(D_info.bottom)
        tier_dict["U_shoulder_points"] = U_shoulder_points
        tier_dict["D_shoulder_points"] = D_shoulder_points
        tier_dict["U_toe_points"] = U_toe_points
        tier_dict["D_toe_points"] = D_toe_points
    return parallel


def format_embankment_points_for_save(world_embankment_points_dict: dict) -> dict:
    formatted = {}
    for embankment_key, embankment_info in world_embankment_points_dict.items():
        wing_points_by_edge = embankment_info.get("abut_wing_points", {})
        embankment_output = {
            "start_edge": {"U": {}, "U-D": {}, "D": {}},
            "end_edge": {"U": {}, "U-D": {}, "D": {}},
            "parallel": build_saved_parallel_points(embankment_info.get("sections", [])),
        }
        for edge in ["start", "end"]:
            edge_key = f"{edge}_edge"
            wing_points = wing_points_by_edge.get(edge, {})
            if wing_points:
                ensure_tier_dict(embankment_output[edge_key]["U"], 1)["shoulder_point"] = wing_points["U_soil"]
                ensure_tier_dict(embankment_output[edge_key]["D"], 1)["shoulder_point"] = wing_points["D_soil"]
        for edge_curve in embankment_info.get("edge_curves", {}).values():
            edge = edge_curve["edge"]
            edge_key = f"{edge}_edge"
            wing_points = wing_points_by_edge.get(edge, {})
            if not wing_points:
                continue
            tier = int(edge_curve["tier"])
            kind = edge_curve["kind"]
            split_points = get_edge_curve_split_points(edge_curve)
            for part in ["U", "U-D", "D"]:
                tier_dict = ensure_tier_dict(embankment_output[edge_key][part], tier)
                if part in ["U", "D"] and tier == 1 and kind == "shoulder":
                    tier_dict["shoulder_point"] = wing_points[f"{part}_soil"]
                    continue
                tier_dict[f"{kind}_points"] = split_points[part]
        formatted[embankment_key] = embankment_output
    return formatted


def main(initial_or_final: str, debug: bool = False):
    DIR = get_output_dir(initial_or_final)
    pavement_infos = load_from_pickle(
        file_path=DIR / f"{Filenames.INPUT}_{Filenames.EMBANKMENT}_{Filenames.PAVEMENT}.pickle",
    )
    local_embankment_points_dict = load_from_pickle(
        file_path=DIR / f"{Filenames.INPUT}_{Filenames.LOCAL}_{Filenames.EMBANKMENT}_{Filenames.POINTS}.pickle",
    )
    pavement_bottom_points_dict = load_from_pickle(
        file_path=DIR / f"{Filenames.INPUT}_{Filenames.WORLD}_{Filenames.EMBANKMENT}_{Filenames.PAVEMENT}_{Filenames.BOTTOM}_{Filenames.POINTS}.pickle",
    )
    wall_points_dict = load_from_pickle(
        file_path=DIR / f"{Filenames.WORLD}_{Filenames.WALL}_{Filenames.POINTS}.pickle",
    )
    abut_points_dict = load_from_pickle(
        file_path=DIR / f"{Filenames.WORLD}_{Filenames.ABUT}_{Filenames.POINTS}.pickle",
    )
    named_curves = get_named_curves_on_layer(layer_index)
    world_embankment_points_dict = get_world_embankment_points(
        pavement_infos=pavement_infos,
        local_embankment_points_dict=local_embankment_points_dict,
        pavement_bottom_points_dict=pavement_bottom_points_dict,
        named_curves=named_curves,
        wall_points_dict=wall_points_dict,
        abut_points_dict=abut_points_dict,
    )
    save_json_and_pickle(
        data=format_embankment_points_for_save(world_embankment_points_dict),
        folder_path=DIR,
        name=f"{Filenames.INPUT}_{Filenames.WORLD}_{Filenames.EMBANKMENT}_{Filenames.POINTS}",
    )

    if debug:
        point_debug_dict = format_embankment_points_for_save(world_embankment_points_dict)
        bake_keys, bake_objs = get_keys_and_values_for_bake(point_debug_dict)
        if len(bake_objs) == 0:
            raise ValueError("No embankment points were generated for debug bake")
        crvs = get_debug_crvs(world_embankment_points_dict)
        return bake_keys, bake_objs, crvs
    return None


if __name__ == "__main__":
    bake_keys, bake_objs, crvs = main("initial", debug=True)
