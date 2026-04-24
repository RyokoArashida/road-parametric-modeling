
import Rhino.Geometry as rg

from my_project.config.file_names import Filenames
from my_project.config.paths import (
    FINAL_OUTPUT_DIR,
    INITIAL_OUTPUT_DIR,
)
from my_project.config.schemas.slab_schemas import (
    SlabInfo,
)
from my_project.utils.dataframe import flatten_any
from my_project.utils.io import load_from_pickle, save_json_and_pickle


def get_each_barrier(
    slab_info: SlabInfo,
) -> rg.Brep:
    distances, CL_polyline = get_slab_points_length(slab_info.point_infos)
    L_top_point_dict, R_top_point_dict, new_point_infos, new_distances = get_top_points(
        point_infos = slab_info.point_infos,
        point_distances = distances,
        CL_polyline = CL_polyline,
        emergency_lane_infos = slab_info.emergency_lane,
        edge_offset = slab_info.width.edge_offset,
        pavement_thickness= slab_info.height.pavement,
    )
    corner_points = get_bottom_points(
        point_infos = new_point_infos,
        point_distances = new_distances,
        bottom_surface_infos = slab_info.bottom_surface,
        CL_polyline = CL_polyline,
        base_edge_height = slab_info.height.edge,
        base_girder_above_height = slab_info.height.girder_above,
        girder_flange_width = slab_info.width.girder_flange,
        L_top_point_dist = L_top_point_dict,
        R_top_point_dist = R_top_point_dict,
    )
    origin_names = [p.name for p in slab_info.point_infos]
    slab_dict = const_indiv_slab(
        corner_points = corner_points,
        origin_names = origin_names
    )

    # 主桁の上面の点のデータは必要なので返す
    MG_point_dict = {}
    for name in origin_names:
        point_info = next(cps for cps in corner_points if cps.name == name)
        MG_point_dict[name] = point_info.main_girder_top_points
    return slab_dict, MG_point_dict


def main(initial_or_final: str):
    if initial_or_final == "initial":
        DIR = INITIAL_OUTPUT_DIR
    elif initial_or_final == "final":
        DIR = FINAL_OUTPUT_DIR

    slab_infos = load_from_pickle(
        file_path=DIR /  f"{Filenames.INPUT}_{Filenames.SLAB}.pickle",
    )
    MG_top_points_dict = {}
    all_L_top_point_dict = {}
    all_R_top_point_dict = {}
    world_items_dict_for_bake = {}
    world_items_dict_for_bake_2 = {}

    for slab_info in slab_infos:
        unique_slab_name = f"{slab_info.name}_{slab_info.num}"
        slab_dict, MG_point_dict, L_top_point_dict, R_top_point_dict = get_each_slab(
            slab_info = slab_info,
        )
        MG_top_points_dict[unique_slab_name] = MG_point_dict # ここはpickel用
        all_L_top_point_dict[unique_slab_name] = L_top_point_dict # ここはpickel用
        all_R_top_point_dict[unique_slab_name] = R_top_point_dict # ここはpickel用
        world_items_dict_for_bake[unique_slab_name] = slab_dict # ここはbake用
    
    MG_point_dict_name = f"{Filenames.WORLD}_{Filenames.MG}_{Filenames.TOP_POINTS}"
    all_L_top_point_dict_name = f"{Filenames.WORLD}_{Filenames.SLAB}_{Filenames.UP}_{Filenames.TOP_POINTS}"
    all_R_top_point_dict_name = f"{Filenames.WORLD}_{Filenames.SLAB}_{Filenames.DOWN}_{Filenames.TOP_POINTS}"

    for dict, name in zip(
        [MG_top_points_dict, all_L_top_point_dict, all_R_top_point_dict],
        [MG_point_dict_name, all_L_top_point_dict_name, all_R_top_point_dict_name]
    ):
        save_json_and_pickle(
            data = dict,
            folder_path = DIR,
            name = name
        )

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
    bake_keys, bake_objs = main("initial")
