# 今のところ橋台で区切られる土工部の舗装しか扱っていない。


from my_project.config.locale_compat import normalize_lc_time

normalize_lc_time()



from typing import Optional

from my_project.config.file_names import Filenames
from my_project.config.paths import get_output_dir
from my_project.config.schemas.embankment_pavement_schemas import EmbankmentPaveInfo
from my_project.config.schemas.embankment_schemas import (
    CrossSectionInfo,
    EdgePoints,
    LocalTopBottomPointInfo,
)
from my_project.config.schemas.wall_schemas import (
    RefPointInfo,
)
from my_project.config.util_schemas import (
    Point3D,
)
from my_project.utils.bake import get_keys_and_values_for_bake
from my_project.utils.geometry.points import (
    get_point_by_xy_offset_with_z_delta,
    transform_local_point_to_world_vertical_plane,
)
from my_project.utils.geometry_gh.attributes import (
    get_point_on_crv_at_distance,
)
from my_project.utils.geometry_gh.const import (
    const_3Dpoint,
    const_brep_from_all_crvs,
    const_point_obj,
    const_polycurve_obj,
)
from my_project.utils.geometry_gh.intersect import (
    split_brep_by_vertical_srf_from_two_points_keep_near_point,
)
from my_project.utils.io import load_from_pickle, save_json_and_pickle


def get_indiv_brep(
    pavement_info: EmbankmentPaveInfo,
    local_points: list[CrossSectionInfo],
    start_abut_points: Optional[RefPointInfo] = None,
    end_abut_points: Optional[RefPointInfo] = None
):
    road_srf_points = pavement_info.points
    pavement_thickness = pavement_info.thickness
    pavement_offset = pavement_thickness * pavement_info.slope.value
    U_embankment_points = []
    D_embankment_points = []
    for STA, Upoint, Dpoint in zip(road_srf_points.STAs, road_srf_points.Upoint, road_srf_points.Dpoint):
        Ubottom = get_point_by_xy_offset_with_z_delta(
            point1=Upoint,
            point2=Dpoint,
            offset_xy=-1*pavement_offset, #広がる
            offset_z=-1*pavement_thickness, #下がる
        )
        Dbottom = get_point_by_xy_offset_with_z_delta(
            point1=Dpoint,
            point2=Upoint,
            offset_xy=-1*pavement_offset, #広がる
            offset_z=-1*pavement_thickness, #下がる
        )
        U_embankment_points.append(Ubottom)
        D_embankment_points.append(Dbottom)

    # まずブレップ
    U_top_crv = const_polycurve_obj([const_point_obj(p) for p in road_srf_points.Upoint])
    D_top_crv = const_polycurve_obj([const_point_obj(p) for p in road_srf_points.Dpoint])
    U_bottom_crv = const_polycurve_obj([const_point_obj(p) for p in U_embankment_points])
    D_bottom_crv = const_polycurve_obj([const_point_obj(p) for p in D_embankment_points])
    raw_brep = const_brep_from_all_crvs([U_top_crv, D_top_crv, D_bottom_crv, U_bottom_crv])

    if start_abut_points is not None:
        raw_brep = split_brep_by_vertical_srf_from_two_points_keep_near_point(
            target_brep=raw_brep,
            cutter_points = [start_abut_points["U"], start_abut_points["D"]],
            keep_point = road_srf_points.Upoint[-1],
            cut_point = road_srf_points.Upoint[0], #スタートに近いほうはabut側なので、カットする
        )
    if end_abut_points is not None:
        raw_brep = split_brep_by_vertical_srf_from_two_points_keep_near_point(
            target_brep=raw_brep,
            cutter_points = [end_abut_points["U"], end_abut_points["D"]],
            keep_point = road_srf_points.Upoint[0],
            cut_point = road_srf_points.Upoint[-1], #エンドに近いほうはabut側なので、カットする
        )
    
    # 次にポイント情報
    infos = []
    world_U_top_polyline = U_bottom_crv
    world_D_top_polyline = D_bottom_crv
    world_start_STA = road_srf_points.STAs[0]
    for local_point_info in local_points:
        STA = local_point_info.STA
        U_points = local_point_info.U_points
        D_points = local_point_info.D_points
        local_U_top_point = U_points.points[0].top
        local_D_top_point = D_points.points[0].top
        world_U_top_point = get_point_on_crv_at_distance(
            curve=world_U_top_polyline,
            distance=STA - world_start_STA,
        )
        world_D_top_point = get_point_on_crv_at_distance(
            curve=world_D_top_polyline,
            distance=STA - world_start_STA,
        )
        world_U_top_point = const_3Dpoint(world_U_top_point)
        world_D_top_point = const_3Dpoint(world_D_top_point)

        def get_world_point(
            target_point: Point3D,
            local_z_base_point: Point3D,
            world_z_base_point: Point3D,
        ) -> Point3D:
            return transform_local_point_to_world_vertical_plane(
                local_points=[local_U_top_point, local_D_top_point],
                world_points=[world_U_top_point, world_D_top_point],
                local_target_point=target_point,
                local_z_base_point=local_z_base_point,
                world_z_base_point=world_z_base_point,
            )
        infos.append(CrossSectionInfo(
            STA=STA,
            U_points=EdgePoints(
                points=[LocalTopBottomPointInfo(
                    top=get_world_point(U_points.points[i].top, local_U_top_point, world_U_top_point),
                    bottom=get_world_point(U_points.points[i].bottom, local_U_top_point, world_U_top_point)
                    ) for i in range(len(U_points.points))],
                wall_points=[LocalTopBottomPointInfo(
                    top=get_world_point(U_points.wall_points[i].top, local_U_top_point, world_U_top_point),
                    bottom=get_world_point(U_points.wall_points[i].bottom, local_U_top_point, world_U_top_point)
                    ) for i in range(len(U_points.wall_points))] if U_points.wall_points is not None else [],
                wall_positions=U_points.wall_positions if U_points.wall_positions is not None else [],
                is_wall_only=U_points.is_wall_only if U_points.is_wall_only is not None else [],
            ),
            D_points=EdgePoints(
                points=[LocalTopBottomPointInfo(
                    top=get_world_point(D_points.points[i].top, local_D_top_point, world_D_top_point),
                    bottom=get_world_point(D_points.points[i].bottom, local_D_top_point, world_D_top_point)
                    ) for i in range(len(D_points.points))],
                wall_points=[LocalTopBottomPointInfo(
                    top=get_world_point(D_points.wall_points[i].top, local_D_top_point, world_D_top_point),
                    bottom=get_world_point(D_points.wall_points[i].bottom, local_D_top_point, world_D_top_point)
                    ) for i in range(len(D_points.wall_points))] if D_points.wall_points is not None else [],
                wall_positions=D_points.wall_positions if D_points.wall_positions is not None else [],
                is_wall_only=D_points.is_wall_only if D_points.is_wall_only is not None else [],
            )
        ))
    return raw_brep, infos


def main(initial_or_final: str, debug: bool = False):
    DIR = get_output_dir(initial_or_final)
    embankment_pave_info = load_from_pickle(
        file_path=DIR / f"{Filenames.INPUT}_{Filenames.EMBANKMENT}_{Filenames.PAVEMENT}.pickle",
    )
    embankment_local_points = load_from_pickle(
        file_path=DIR / f"{Filenames.INPUT}_{Filenames.LOCAL}_{Filenames.EMBANKMENT}_{Filenames.POINTS}.pickle",
    )

    # 今のところ橋台で区切られる土工部の舗装しか扱っていないので、橋台の情報を取得する
    abut_points_dict = load_from_pickle(
        file_path=DIR / f"{Filenames.WORLD}_{Filenames.ABUT}_wing_outer_points.pickle",
    )

    world_embankment_points_dict = {}
    world_items_dict_for_bake = {}
    world_items_dict_for_bake_2 = {}
    world_items_dict_for_bake_3 = {}

    for pavement_info in embankment_pave_info:
        name = pavement_info.name
        num = pavement_info.num
        local_points = embankment_local_points[f"{name}_{num}"]
        start_edge_structure = pavement_info.start_edge_structure
        end_edge_structure = pavement_info.end_edge_structure
        start_abut_points = None
        end_abut_points = None
        if start_edge_structure is not None:
            if start_edge_structure.structure_type == "abutment":
                start_abut_points = abut_points_dict[start_edge_structure.structure_name]
        if end_edge_structure is not None:
            if end_edge_structure.structure_type == "abutment":
                end_abut_points = abut_points_dict[end_edge_structure.structure_name]
        pavement_brep, points_info = get_indiv_brep(
            pavement_info=pavement_info,
            local_points=local_points,
            start_abut_points=start_abut_points,
            end_abut_points=end_abut_points
        )
        world_embankment_points_dict[f"{name}_{num}"] = points_info
        world_items_dict_for_bake[f"{name}_{num}"] = pavement_brep
        world_items_dict_for_bake_2[f"{name}_{num}"] = points_info

    save_json_and_pickle(
        data = world_embankment_points_dict,
        folder_path = DIR,
        name = f"{Filenames.INPUT}_{Filenames.WORLD}_{Filenames.EMBANKMENT}_{Filenames.POINTS}"
    )
    
    if not debug:
        return get_keys_and_values_for_bake(world_items_dict_for_bake)
    if debug:
        point_bake_items = get_keys_and_values_for_bake(world_items_dict_for_bake_2)
        if len(point_bake_items[1]) == 0:
            raise ValueError("No embankment pavement points were generated for bake_objs_2")
        return (
            get_keys_and_values_for_bake(world_items_dict_for_bake),
            point_bake_items,
        )




if __name__ == "__main__":
    (bake_keys, bake_objs), (bake_keys2, bake_objs2) = main("initial", debug=True)
