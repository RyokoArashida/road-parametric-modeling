# ruff: noqa: E402
from my_project.config.locale_compat import normalize_lc_time

normalize_lc_time()

from my_project.config.constants import DISTANCE_TOL
from my_project.config.file_names import Filenames
from my_project.config.paths import get_output_dir
from my_project.config.schemas.embankment_pavement_schemas import EmbankmentPaveInfo
from my_project.config.util_schemas import Point3D
from my_project.domain.abutment import get_abut_wing_named_points
from my_project.domain.embankment import get_edge_structure
from my_project.utils.bake import get_keys_and_values_for_bake
from my_project.utils.geometry.points import (
    get_point_by_xy_offset_with_z_delta,
)
from my_project.utils.geometry_gh.attributes import (
    get_value_at_point_on_polyline,
)
from my_project.utils.geometry_gh.const import (
    const_brep_from_all_crvs,
    const_point_obj,
    const_polycurve_obj,
)
from my_project.utils.geometry_gh.intersect import (
    get_cut_point_on_polyline_with_vertical_plane,
    split_brep_by_vertical_srf_from_two_points_keep_near_point,
)
from my_project.utils.io import load_from_pickle, save_json_and_pickle


def get_pavement_bottom_points(
    pavement_info: EmbankmentPaveInfo,
) -> dict:
    road_srf_points = pavement_info.points
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
    bottom_points_info: dict,
    abut_points_dict: dict,
):
    road_srf_points = pavement_info.points
    U_top_crv = const_polycurve_obj([const_point_obj(p) for p in road_srf_points.Upoint])
    D_top_crv = const_polycurve_obj([const_point_obj(p) for p in road_srf_points.Dpoint])
    U_bottom_crv = const_polycurve_obj([const_point_obj(p) for p in bottom_points_info["U_points"]])
    D_bottom_crv = const_polycurve_obj([const_point_obj(p) for p in bottom_points_info["D_points"]])
    brep = const_brep_from_all_crvs([U_top_crv, D_top_crv, D_bottom_crv, U_bottom_crv])

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
    named_points = get_abut_wing_named_points(wing_dict)
    return [named_points["U_soil"], named_points["D_soil"]]


def main(initial_or_final: str, debug: bool = False):
    DIR = get_output_dir(initial_or_final)
    embankment_pave_info = load_from_pickle(
        file_path=DIR / f"{Filenames.INPUT}_{Filenames.EMBANKMENT}_{Filenames.PAVEMENT}.pickle",
    )
    abut_points_dict = load_from_pickle(
        file_path=DIR / f"{Filenames.WORLD}_{Filenames.ABUT}_{Filenames.POINTS}.pickle",
    )

    pavement_bottom_points_dict = {}
    world_items_dict_for_bake = {}
    world_items_dict_for_bake_2 = {}

    for pavement_info in embankment_pave_info:
        key = f"{pavement_info.name}_{pavement_info.num}"
        bottom_points_info = get_pavement_bottom_points(pavement_info)
        bottom_points_info_for_save = add_abut_cut_points_to_pavement_bottom_points(
            pavement_info,
            bottom_points_info,
            abut_points_dict,
        )
        pavement_bottom_points_dict[key] = bottom_points_info_for_save
        world_items_dict_for_bake[key] = get_pavement_brep(
            pavement_info=pavement_info,
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
