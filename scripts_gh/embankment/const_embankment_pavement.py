# ruff: noqa: E402
from my_project.config.locale_compat import normalize_lc_time

normalize_lc_time()

from my_project.config.constants import DISTANCE_TOL
from my_project.config.file_names import Filenames
from my_project.config.paths import get_output_dir
from my_project.config.schemas.embankment_pavement_schemas import (
    EmbankmentPaveInfo,
    PointsInfo,
)
from my_project.config.util_schemas import Point3D
from my_project.domain.embankment import get_edge_structure
from my_project.utils.bake import get_keys_and_values_for_bake
from my_project.utils.geometry.points import (
    get_point_by_xy_offset_with_z_delta,
)
from my_project.utils.geometry_gh.attributes import (
    get_curve_distance,
    get_curve_polyline_points,
    get_value_at_point_on_polyline,
)
from my_project.utils.geometry_gh.const import (
    const_brep_from_all_crvs,
    const_point_obj,
    const_polycurve_obj,
)
from my_project.utils.geometry_gh.document import get_named_curves_on_layer
from my_project.utils.geometry_gh.intersect import (
    get_cut_point_on_polyline_with_vertical_plane,
    get_intersect_point_on_crvs_in_the_same_plane,
    split_brep_by_vertical_srf_from_two_points_keep_near_point,
)
from my_project.utils.geometry_gh.road_surface import (
    get_center_sample_at_STA,
    get_indiv_center_line_points,
    get_slope_at_STA,
)
from my_project.utils.io import load_from_pickle, save_json_and_pickle

PAVEMENT_EDGE_EXTENSION_RATIO = 0.2


def get_slope_value(slope) -> float:
    return float(slope.value if hasattr(slope, "value") else slope) / 100


def get_pavement_curve_name(pavement_info: EmbankmentPaveInfo, side: str) -> str:
    side_name = "上り" if side == "U" else "下り"
    return f"舗装_{pavement_info.name}_{pavement_info.num}_{side_name}"


def get_pavement_edge_curve(
    pavement_info: EmbankmentPaveInfo,
    named_curves: dict[str, object],
    side: str,
):
    candidates = [
        get_pavement_curve_name(pavement_info, side),
        f"舗装_{pavement_info.name}_{pavement_info.num}_{side}",
    ]
    for name in candidates:
        if name in named_curves:
            return named_curves[name]
    raise ValueError(
        "Pavement edge curve was not found. "
        f"candidates={candidates}, available={sorted(named_curves.keys())}"
    )


def get_point_on_curve_at_fraction(curve, fraction: float):
    length = curve.GetLength()
    ok, parameter = curve.LengthParameter(length * min(max(fraction, 0.0), 1.0))
    if not ok:
        raise ValueError(f"Failed to get curve parameter at fraction: {fraction}")
    point = curve.PointAt(parameter)
    return type(point)(point.X, point.Y, 0.0)


def get_unique_fractions(fractions: list[float]) -> list[float]:
    unique_fractions = []
    for fraction in sorted(fractions):
        fraction = min(max(fraction, 0.0), 1.0)
        if not unique_fractions or abs(fraction - unique_fractions[-1]) > 1e-6:
            unique_fractions.append(fraction)
    return unique_fractions


def orient_edge_point_lists_by_nearest_ends(
    U_points: list,
    D_points: list,
) -> tuple[list, list]:
    same_direction_distance = (
        const_point_obj(U_points[0]).DistanceTo(const_point_obj(D_points[0]))
        + const_point_obj(U_points[-1]).DistanceTo(const_point_obj(D_points[-1]))
    )
    reverse_direction_distance = (
        const_point_obj(U_points[0]).DistanceTo(const_point_obj(D_points[-1]))
        + const_point_obj(U_points[-1]).DistanceTo(const_point_obj(D_points[0]))
    )
    if reverse_direction_distance < same_direction_distance:
        return U_points, list(reversed(D_points))
    return U_points, D_points


def extend_point_list_ends(points: list) -> list:
    if len(points) < 2:
        raise ValueError(f"Need at least 2 points to extend pavement edge curve, got {len(points)}")
    start_point = const_point_obj(points[0])
    start_next_point = const_point_obj(points[1])
    end_prev_point = const_point_obj(points[-2])
    end_point = const_point_obj(points[-1])
    start_vector = start_point - start_next_point
    end_vector = end_point - end_prev_point
    if not start_vector.Unitize() or not end_vector.Unitize():
        raise ValueError("Pavement edge curve has duplicated end points.")
    start_extension = start_point.DistanceTo(start_next_point) * PAVEMENT_EDGE_EXTENSION_RATIO
    end_extension = end_point.DistanceTo(end_prev_point) * PAVEMENT_EDGE_EXTENSION_RATIO
    extended_start = start_point + start_vector * start_extension
    extended_end = end_point + end_vector * end_extension
    return [extended_start] + points[1:-1] + [extended_end]


def get_paired_edge_points(U_curve, D_curve) -> list[tuple[object, object]]:
    U_points = get_curve_polyline_points(U_curve)
    D_points = get_curve_polyline_points(D_curve)
    U_points, D_points = orient_edge_point_lists_by_nearest_ends(U_points, D_points)
    U_points = extend_point_list_ends(U_points)
    D_points = extend_point_list_ends(D_points)
    U_curve_2D = const_polycurve_obj(U_points)
    D_curve_2D = const_polycurve_obj(D_points)
    U_length = U_curve_2D.GetLength()
    D_length = D_curve_2D.GetLength()
    if U_length <= DISTANCE_TOL or D_length <= DISTANCE_TOL:
        raise ValueError("Pavement edge curve length is too short.")
    fractions = [0.0, 1.0]
    fractions.extend(get_curve_distance(U_curve_2D, point) / U_length for point in U_points)
    fractions.extend(get_curve_distance(D_curve_2D, point) / D_length for point in D_points)
    return [
        (
            get_point_on_curve_at_fraction(U_curve_2D, fraction),
            get_point_on_curve_at_fraction(D_curve_2D, fraction),
        )
        for fraction in get_unique_fractions(fractions)
    ]


def get_center_line_data(road_center_infos: dict, pavement_info: EmbankmentPaveInfo):
    if pavement_info.name not in road_center_infos:
        raise ValueError(
            f"Road center info was not found: {pavement_info.name}. "
            f"available={sorted(road_center_infos.keys())}"
        )
    center_line_points, left_vectors, center_line_STAs = get_indiv_center_line_points(
        road_center_info=road_center_infos[pavement_info.name],
    )
    center_curve_2D = const_polycurve_obj([
        type(point)(point.X, point.Y, 0.0)
        for point in center_line_points
    ])
    return center_line_points, left_vectors, center_line_STAs, center_curve_2D


def get_pavement_top_points_from_curves(
    pavement_info: EmbankmentPaveInfo,
    named_curves: dict[str, object],
    road_center_infos: dict,
) -> PointsInfo:
    U_curve = get_pavement_edge_curve(pavement_info, named_curves, "U")
    D_curve = get_pavement_edge_curve(pavement_info, named_curves, "D")
    center_line_points, left_vectors, center_line_STAs, center_curve_2D = get_center_line_data(
        road_center_infos,
        pavement_info,
    )
    if not pavement_info.cross_slope_infos:
        raise ValueError(f"Pavement cross slope infos are missing: {pavement_info.name}_{pavement_info.num}")
    slope_infos = sorted(pavement_info.cross_slope_infos, key=lambda info: info.STA)
    slope_STAs = [info.STA for info in slope_infos]
    slopes = [get_slope_value(info.slope) for info in slope_infos]

    items = []
    for U_point_2D, D_point_2D in get_paired_edge_points(U_curve, D_curve):
        cross_curve = const_polycurve_obj([U_point_2D, D_point_2D])
        center_intersection = get_intersect_point_on_crvs_in_the_same_plane(
            center_curve_2D,
            cross_curve,
        )
        center_distance = get_curve_distance(center_curve_2D, center_intersection)
        this_STA = center_line_STAs[0] + center_distance
        center_point, _, _ = get_center_sample_at_STA(
            target_STA=this_STA,
            center_line_points=center_line_points,
            left_vectors=left_vectors,
            center_line_STAs=center_line_STAs,
        )
        cross_slope = get_slope_value(get_slope_at_STA(this_STA, slope_STAs, slopes))
        center_point_2D = const_point_obj(center_intersection)
        U_distance = center_point_2D.DistanceTo(const_point_obj(U_point_2D))
        D_distance = center_point_2D.DistanceTo(const_point_obj(D_point_2D))
        items.append(
            (
                this_STA,
                Point3D(
                    x=U_point_2D.X,
                    y=U_point_2D.Y,
                    z=center_point.Z + cross_slope * U_distance,
                ),
                Point3D(
                    x=D_point_2D.X,
                    y=D_point_2D.Y,
                    z=center_point.Z - cross_slope * D_distance,
                ),
            )
        )
    items = sorted(items, key=lambda item: item[0])
    return PointsInfo(
        STAs=[item[0] for item in items],
        Upoint=[item[1] for item in items],
        Dpoint=[item[2] for item in items],
    )


def get_pavement_top_points(
    pavement_info: EmbankmentPaveInfo,
    named_curves: dict[str, object],
    road_center_infos: dict,
) -> PointsInfo:
    if pavement_info.points is not None:
        return pavement_info.points
    return get_pavement_top_points_from_curves(
        pavement_info=pavement_info,
        named_curves=named_curves,
        road_center_infos=road_center_infos,
    )


def get_pavement_bottom_points(
    pavement_info: EmbankmentPaveInfo,
    road_srf_points: PointsInfo,
) -> dict:
    pavement_thickness = pavement_info.thickness
    pavement_offset = pavement_thickness * pavement_info.slope.value
    U_bottom_points = []
    D_bottom_points = []
    for U_top, D_top in zip(road_srf_points.Upoint, road_srf_points.Dpoint):
        U_bottom_points.append(
            get_point_by_xy_offset_with_z_delta(
                point1=U_top,
                point2=D_top,
                offset_xy=-1 * pavement_offset,
                offset_z=-1 * pavement_thickness,
            )
        )
        D_bottom_points.append(
            get_point_by_xy_offset_with_z_delta(
                point1=D_top,
                point2=U_top,
                offset_xy=-1 * pavement_offset,
                offset_z=-1 * pavement_thickness,
            )
        )
    return {
        "STAs": road_srf_points.STAs,
        "U_points": U_bottom_points,
        "D_points": D_bottom_points,
    }


def insert_bottom_cut_points(
    bottom_points_info: dict,
    *,
    cutter_points: list[Point3D],
) -> dict:
    U_cut_point = get_cut_point_on_polyline_with_vertical_plane(
        bottom_points_info["U_points"],
        cutter_points,
        cutter_points[0],
    )
    D_cut_point = get_cut_point_on_polyline_with_vertical_plane(
        bottom_points_info["D_points"],
        cutter_points,
        cutter_points[1],
    )
    U_cut_STA = get_value_at_point_on_polyline(
        bottom_points_info["U_points"],
        bottom_points_info["STAs"],
        U_cut_point,
    )
    D_cut_STA = get_value_at_point_on_polyline(
        bottom_points_info["D_points"],
        bottom_points_info["STAs"],
        D_cut_point,
    )
    cut_STA = (U_cut_STA + D_cut_STA) / 2

    items = [
        (float(STA), U_point, D_point)
        for STA, U_point, D_point in zip(
            bottom_points_info["STAs"],
            bottom_points_info["U_points"],
            bottom_points_info["D_points"],
        )
    ]
    if all(abs(STA - cut_STA) > DISTANCE_TOL for STA, _, _ in items):
        items.append((cut_STA, U_cut_point, D_cut_point))
    items = sorted(items, key=lambda item: item[0])
    return {
        "STAs": [item[0] for item in items],
        "U_points": [item[1] for item in items],
        "D_points": [item[2] for item in items],
    }


def add_abut_cut_points_to_pavement_bottom_points(
    pavement_info: EmbankmentPaveInfo,
    bottom_points_info: dict,
    abut_points_dict: dict,
) -> dict:
    output = bottom_points_info
    for edge in ["start", "end"]:
        abut_line = get_abut_cut_line(pavement_info, abut_points_dict, edge=edge)
        if abut_line is not None:
            output = insert_bottom_cut_points(output, cutter_points=abut_line)
    return output


def get_pavement_brep(
    pavement_info: EmbankmentPaveInfo,
    road_srf_points: PointsInfo,
    bottom_points_info: dict,
    abut_points_dict: dict,
):
    U_top_crv = const_polycurve_obj([const_point_obj(p) for p in road_srf_points.Upoint])
    D_top_crv = const_polycurve_obj([const_point_obj(p) for p in road_srf_points.Dpoint])
    U_bottom_crv = const_polycurve_obj([const_point_obj(p) for p in bottom_points_info["U_points"]])
    D_bottom_crv = const_polycurve_obj([const_point_obj(p) for p in bottom_points_info["D_points"]])
    brep = const_brep_from_all_crvs([U_top_crv, U_bottom_crv, D_bottom_crv, D_top_crv])

    start_abut_line = get_abut_cut_line(pavement_info, abut_points_dict, edge="start")
    if start_abut_line is not None:
        brep = split_brep_by_vertical_srf_from_two_points_keep_near_point(
            target_brep=brep,
            cutter_points=start_abut_line,
            keep_point=road_srf_points.Upoint[-1],
            cut_point=road_srf_points.Upoint[0],
        )

    end_abut_line = get_abut_cut_line(pavement_info, abut_points_dict, edge="end")
    if end_abut_line is not None:
        brep = split_brep_by_vertical_srf_from_two_points_keep_near_point(
            target_brep=brep,
            cutter_points=end_abut_line,
            keep_point=road_srf_points.Upoint[0],
            cut_point=road_srf_points.Upoint[-1],
        )

    return brep


def get_abut_cut_line(
    pavement_info: EmbankmentPaveInfo,
    abut_points_dict: dict,
    edge: str,
):
    edge_structure = get_edge_structure(pavement_info, edge)
    if edge_structure is None:
        return None
    if edge_structure.structure_type != "abutment":
        return None

    abut_points = abut_points_dict[edge_structure.structure_name]
    wing_dict = abut_points["wing_dict"]
    if edge in {"start", "end"}:
        return [
            wing_dict["U_wing_top_points"]["US"],
            wing_dict["D_wing_top_points"]["DS"],
        ]
    raise ValueError(f"Unknown edge: {edge}")


def main(initial_or_final: str, debug: bool = False, layer_index=None):
    DIR = get_output_dir(initial_or_final)
    if layer_index is None:
        layer_index = globals().get("layer_index")
    embankment_pave_info = load_from_pickle(
        file_path=DIR / f"{Filenames.INPUT}_{Filenames.EMBANKMENT}_{Filenames.PAVEMENT}.pickle",
    )
    road_center_infos = load_from_pickle(
        file_path=DIR / f"{Filenames.INPUT}_{Filenames.ROAD_SURFACE}.pickle",
    )
    abut_points_dict = load_from_pickle(
        file_path=DIR / f"{Filenames.WORLD}_{Filenames.ABUT}_{Filenames.POINTS}.pickle",
    )
    named_curves = get_named_curves_on_layer(layer_index) if layer_index is not None else {}

    pavement_bottom_points_dict = {}
    world_items_dict_for_bake = {}
    world_items_dict_for_bake_2 = {}

    for pavement_info in embankment_pave_info:
        key = f"{pavement_info.name}_{pavement_info.num}"
        road_srf_points = get_pavement_top_points(
            pavement_info=pavement_info,
            named_curves=named_curves,
            road_center_infos=road_center_infos,
        )
        bottom_points_info = get_pavement_bottom_points(pavement_info, road_srf_points)
        bottom_points_info_for_save = add_abut_cut_points_to_pavement_bottom_points(
            pavement_info,
            bottom_points_info,
            abut_points_dict,
        )
        pavement_bottom_points_dict[key] = bottom_points_info_for_save
        world_items_dict_for_bake[key] = get_pavement_brep(
            pavement_info=pavement_info,
            road_srf_points=road_srf_points,
            bottom_points_info=bottom_points_info,
            abut_points_dict=abut_points_dict,
        )
        world_items_dict_for_bake_2[key] = bottom_points_info_for_save

    save_json_and_pickle(
        data=pavement_bottom_points_dict,
        folder_path=DIR,
        name=f"{Filenames.WORLD}_{Filenames.EMBANKMENT}_{Filenames.PAVEMENT}_{Filenames.BOTTOM}_{Filenames.POINTS}",
    )

    if not debug:
        return get_keys_and_values_for_bake(world_items_dict_for_bake)
    return (
        get_keys_and_values_for_bake(world_items_dict_for_bake),
        get_keys_and_values_for_bake(world_items_dict_for_bake_2),
    )


if __name__ == "__main__":
    (bake_keys, bake_objs), (bake_keys2, bake_objs2) = main("initial", debug=True)
