from typing import Optional

import Rhino.Geometry as rg

from my_project.config.constants import CENTER_CUTTER_EXTENSION_RATIO, DISTANCE_TOL
from my_project.config.file_names import Filenames
from my_project.config.paths import get_output_dir
from my_project.utils.dataframe import flatten_any
from my_project.utils.geometry.points import get_point_by_xy_offset
from my_project.utils.geometry_gh.const import (
    const_3Dpoint,
    const_closed_polycurve_obj,
    const_point_obj,
    const_polycurve_obj,
    const_srf_from_2crvs,
    const_z_extruded_brep_from_srf,
)
from my_project.utils.geometry_gh.intersect import trim_srf_by_closed_curve
from my_project.utils.io import load_from_pickle


def extend_point_list_ends(points: list[rg.Point3d]) -> list[rg.Point3d]:
    if len(points) < 2:
        raise ValueError(f"Need at least 2 points to extend center cutter, got {len(points)}")
    start_extension = points[0].DistanceTo(points[1]) * CENTER_CUTTER_EXTENSION_RATIO
    end_extension = points[-1].DistanceTo(points[-2]) * CENTER_CUTTER_EXTENSION_RATIO
    start_point = const_point_obj(get_point_by_xy_offset(const_3Dpoint(points[1]), const_3Dpoint(points[0]), start_extension))
    end_point = const_point_obj(get_point_by_xy_offset(const_3Dpoint(points[-2]), const_3Dpoint(points[-1]), end_extension))
    return [start_point] + points + [end_point]


def get_center_cutter_curve(center_base_points_dict: dict) -> rg.PolylineCurve:
    U_in_points = [const_point_obj(point_dict["Uin"]) for point_dict in center_base_points_dict["points"]]
    D_in_points = [const_point_obj(point_dict["Din"]) for point_dict in center_base_points_dict["points"]]
    return const_closed_polycurve_obj(extend_point_list_ends(U_in_points + D_in_points[::-1]))


def get_slab_indiv_pavement_brep(base_points_dict: dict, center_base_points_dict: Optional[dict]):
    pavement_height = base_points_dict["pavement_height"]
    bottom_points = base_points_dict["points"]
    U_points = [const_point_obj(point_dict["U"]) for point_dict in bottom_points]
    D_points = [const_point_obj(point_dict["D"]) for point_dict in bottom_points]
    srf = const_srf_from_2crvs([
        const_polycurve_obj(U_points),
        const_polycurve_obj(D_points),
    ])
    if center_base_points_dict is not None:
        center_cutter_curve = get_center_cutter_curve(center_base_points_dict)
        trimmed_srfs = trim_srf_by_closed_curve(srf, center_cutter_curve, keep="outside")
        if len(trimmed_srfs) != 1:
            raise ValueError(f"Expected exactly one pavement surface, got {len(trimmed_srfs)}")
        srf = trimmed_srfs[0]
    return const_z_extruded_brep_from_srf(srf, pavement_height, tol=DISTANCE_TOL)


def get_abut_indiv_pavement_brep(base_points_dict: dict):
    pavement_height = base_points_dict["pavement_height"]
    points = base_points_dict["points"]
    U_points = [
        const_point_obj(points["UB_backwall"]),
        const_point_obj(points["UE_backwall"]),
        const_point_obj(points["UE_wing"]),
    ]
    D_points = [
        const_point_obj(points["DB_backwall"]),
        const_point_obj(points["DE_backwall"]),
        const_point_obj(points["DE_wing"]),
    ]
    srf = const_srf_from_2crvs([
        const_polycurve_obj(U_points),
        const_polycurve_obj(D_points),
    ])
    return const_z_extruded_brep_from_srf(srf, pavement_height, tol=DISTANCE_TOL)


def main(initial_or_final: str):
    DIR = get_output_dir(initial_or_final)

    bridge_barrier_base_points_dict = load_from_pickle(
        file_path=DIR / f"{Filenames.WORLD}_{Filenames.SLAB}_{Filenames.BARRIER}_{Filenames.BASE_POINT}.pickle",
    )
    center_barrier_base_points_dict = load_from_pickle(
        file_path=DIR / f"{Filenames.WORLD}_{Filenames.SLAB}_{Filenames.CENTER}_{Filenames.BARRIER}_{Filenames.BASE_POINT}.pickle",
    )
    abut_barrier_base_points_dict = load_from_pickle(
        file_path=DIR / f"{Filenames.WORLD}_{Filenames.ABUT}_{Filenames.BARRIER}_{Filenames.BASE_POINT}.pickle",
    )
    world_items_dict_for_bake = {}

    for unique_slab_name, _dict in bridge_barrier_base_points_dict.items():
        center_dict = center_barrier_base_points_dict.get(unique_slab_name)
        world_items_dict_for_bake[unique_slab_name] = get_slab_indiv_pavement_brep(
            base_points_dict=_dict,
            center_base_points_dict=center_dict,
        )
    for abut_name, _dict in abut_barrier_base_points_dict.items():
        world_items_dict_for_bake[abut_name] = get_abut_indiv_pavement_brep(
            base_points_dict=_dict,
        )

    def get_keys_and_values_for_bake(world_items_dict):
        flatten_dict_for_bake = flatten_any(world_items_dict)
        items = [(k, v) for k, v in flatten_dict_for_bake.items() if v is not None]
        keys = [k for k, _ in items]
        values = [v for _, v in items]
        return keys, values

    return get_keys_and_values_for_bake(world_items_dict_for_bake)


if __name__ == "__main__":
    bake_keys, bake_objs = main("initial")
