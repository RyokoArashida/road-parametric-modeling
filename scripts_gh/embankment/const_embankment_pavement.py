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
    EdgeStructureInfo,
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
    transform_local_point_by_corresponding_points,
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


def get_world_point_from_ref_points(
    target_point: Point3D,
    ref_points,
) -> Point3D:
    return transform_local_point_by_corresponding_points(
        local_points=[ref_point.local for ref_point in ref_points],
        world_points=[ref_point.world for ref_point in ref_points],
        local_target_point=target_point,
    )


def transform_top_bottom_points_by_ref_points(
    point_info: LocalTopBottomPointInfo,
    ref_points,
) -> LocalTopBottomPointInfo:
    return LocalTopBottomPointInfo(
        top=get_world_point_from_ref_points(point_info.top, ref_points),
        bottom=get_world_point_from_ref_points(point_info.bottom, ref_points),
    )


def transform_edge_points_by_ref_points(
    edge_points: EdgePoints,
    ref_points,
) -> EdgePoints:
    return EdgePoints(
        points=[
            transform_top_bottom_points_by_ref_points(point_info, ref_points)
            for point_info in edge_points.points
        ],
        wall_points=[
            transform_top_bottom_points_by_ref_points(point_info, ref_points)
            for point_info in edge_points.wall_points
        ] if edge_points.wall_points is not None else [],
        wall_positions=edge_points.wall_positions if edge_points.wall_positions is not None else [],
        is_wall_only=edge_points.is_wall_only if edge_points.is_wall_only is not None else [],
        wall_names=edge_points.wall_names if edge_points.wall_names is not None else [],
    )


def transform_abut_embankment_points(
    edge_structure_info: EdgeStructureInfo,
) -> dict[str, dict[str, EdgePoints]]:
    start_section = edge_structure_info.start_section
    end_section = edge_structure_info.end_section
    return {
        "start_section": {
            "U_points": transform_edge_points_by_ref_points(
                edge_points=start_section.U_points,
                ref_points=start_section.U_ref_points,
            ),
            "D_points": transform_edge_points_by_ref_points(
                edge_points=start_section.D_points,
                ref_points=start_section.D_ref_points,
            ),
        },
        "end_section": {
            "U_points": transform_edge_points_by_ref_points(
                edge_points=end_section.U_points,
                ref_points=end_section.U_ref_points,
            ),
            "D_points": transform_edge_points_by_ref_points(
                edge_points=end_section.D_points,
                ref_points=end_section.D_ref_points,
            ),
        },
    }


def get_section_center_point(section_info: CrossSectionInfo) -> Point3D:
    U_point = section_info.U_points.points[0].top
    D_point = section_info.D_points.points[0].top
    return Point3D(
        x=(U_point.x + D_point.x) / 2,
        y=(U_point.y + D_point.y) / 2,
        z=(U_point.z + D_point.z) / 2,
    )


def get_side_value(
    point: Point3D,
    cutter_points: list[Point3D],
) -> float:
    cutter_U = cutter_points[0]
    cutter_D = cutter_points[1]
    return (
        (cutter_D.x - cutter_U.x) * (point.y - cutter_U.y)
        - (cutter_D.y - cutter_U.y) * (point.x - cutter_U.x)
    )


def is_on_keep_side(
    point: Point3D,
    cutter_points: list[Point3D],
    keep_point: Point3D,
) -> bool:
    point_side = get_side_value(point, cutter_points)
    keep_side = get_side_value(keep_point, cutter_points)
    return point_side * keep_side >= 0


def get_plane_cross_ratio(
    point0: Point3D,
    point1: Point3D,
    cutter_points: list[Point3D],
) -> float:
    side0 = get_side_value(point0, cutter_points)
    side1 = get_side_value(point1, cutter_points)
    denom = side0 - side1
    if abs(denom) < 1e-12:
        return 0
    return side0 / denom


def interpolate_point(
    point0: Point3D,
    point1: Point3D,
    ratio: float,
) -> Point3D:
    return Point3D(
        x=point0.x + (point1.x - point0.x) * ratio,
        y=point0.y + (point1.y - point0.y) * ratio,
        z=point0.z + (point1.z - point0.z) * ratio,
    )


def interpolate_top_bottom_point(
    point_info0: LocalTopBottomPointInfo,
    point_info1: LocalTopBottomPointInfo,
    ratio: float,
) -> LocalTopBottomPointInfo:
    return LocalTopBottomPointInfo(
        top=interpolate_point(point_info0.top, point_info1.top, ratio),
        bottom=interpolate_point(point_info0.bottom, point_info1.bottom, ratio),
    )


def interpolate_edge_points(
    edge_points0: EdgePoints,
    edge_points1: EdgePoints,
    ratio: float,
) -> EdgePoints:
    wall_points0 = edge_points0.wall_points or []
    wall_points1 = edge_points1.wall_points or []
    return EdgePoints(
        points=[
            interpolate_top_bottom_point(p0, p1, ratio)
            for p0, p1 in zip(edge_points0.points, edge_points1.points)
        ],
        wall_points=[
            interpolate_top_bottom_point(p0, p1, ratio)
            for p0, p1 in zip(wall_points0, wall_points1)
        ],
        wall_positions=edge_points0.wall_positions or [],
        is_wall_only=edge_points0.is_wall_only or [],
        wall_names=edge_points0.wall_names or [],
    )


def interpolate_cross_section(
    section0: CrossSectionInfo,
    section1: CrossSectionInfo,
    ratio: float,
) -> CrossSectionInfo:
    return CrossSectionInfo(
        STA=section0.STA + (section1.STA - section0.STA) * ratio,
        U_points=interpolate_edge_points(section0.U_points, section1.U_points, ratio),
        D_points=interpolate_edge_points(section0.D_points, section1.D_points, ratio),
    )


def get_cut_cross_section(
    section_infos: list[CrossSectionInfo],
    cutter_points: list[Point3D],
    keep_point: Point3D,
    *,
    use_start_end: bool,
) -> CrossSectionInfo:
    ordered_infos = section_infos if use_start_end else list(reversed(section_infos))
    for section0, section1 in zip(ordered_infos, ordered_infos[1:]):
        center0 = get_section_center_point(section0)
        center1 = get_section_center_point(section1)
        if is_on_keep_side(center0, cutter_points, keep_point) != is_on_keep_side(center1, cutter_points, keep_point):
            ratio = get_plane_cross_ratio(center0, center1, cutter_points)
            return interpolate_cross_section(section0, section1, ratio)

    if len(ordered_infos) < 2:
        raise ValueError("Need at least 2 cross sections to extend to abutment cut plane")
    section0 = ordered_infos[0]
    section1 = ordered_infos[1]
    center0 = get_section_center_point(section0)
    center1 = get_section_center_point(section1)
    ratio = get_plane_cross_ratio(center0, center1, cutter_points)
    return interpolate_cross_section(section0, section1, ratio)


def trim_cross_sections_by_abutment_plane(
    section_infos: list[CrossSectionInfo],
    cutter_points: list[Point3D],
    keep_point: Point3D,
    *,
    use_start_end: bool,
) -> list[CrossSectionInfo]:
    cut_section = get_cut_cross_section(
        section_infos=section_infos,
        cutter_points=cutter_points,
        keep_point=keep_point,
        use_start_end=use_start_end,
    )
    kept_sections = [
        section_info
        for section_info in section_infos
        if is_on_keep_side(get_section_center_point(section_info), cutter_points, keep_point)
    ]
    kept_sections.append(cut_section)
    return sorted(kept_sections, key=lambda section_info: section_info.STA)


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
                wall_names=U_points.wall_names if U_points.wall_names is not None else [],
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
                wall_names=D_points.wall_names if D_points.wall_names is not None else [],
            )
        ))
    if start_abut_points is not None:
        infos = trim_cross_sections_by_abutment_plane(
            section_infos=infos,
            cutter_points=[start_abut_points["U"], start_abut_points["D"]],
            keep_point=road_srf_points.Upoint[-1],
            use_start_end=True,
        )
    if end_abut_points is not None:
        infos = trim_cross_sections_by_abutment_plane(
            section_infos=infos,
            cutter_points=[end_abut_points["U"], end_abut_points["D"]],
            keep_point=road_srf_points.Upoint[0],
            use_start_end=False,
        )
    return raw_brep, infos


def main(initial_or_final: str, debug: bool = False):
    DIR = get_output_dir(initial_or_final)
    embankment_pave_info = load_from_pickle(
        file_path=DIR / f"{Filenames.INPUT}_{Filenames.EMBANKMENT}_{Filenames.PAVEMENT}.pickle",
    )
    embankment_local_points = load_from_pickle(
        file_path=DIR / f"{Filenames.INPUT}_{Filenames.LOCAL}_{Filenames.EMBANKMENT}_{Filenames.POINTS}.pickle",
    )
    abut_embankment_local_points = load_from_pickle(
        file_path=DIR / f"{Filenames.INPUT}_{Filenames.LOCAL}_{Filenames.ABUT}_{Filenames.EMBANKMENT}_{Filenames.POINTS}.pickle",
    )

    # 今のところ橋台で区切られる土工部の舗装しか扱っていないので、橋台の情報を取得する
    abut_points_dict = load_from_pickle(
        file_path=DIR / f"{Filenames.WORLD}_{Filenames.ABUT}_{Filenames.POINTS}.pickle",
    )

    world_embankment_points_dict = {}
    world_items_dict_for_bake = {}
    world_items_dict_for_bake_2 = {}
    world_items_dict_for_bake_3 = {}

    for pavement_info in embankment_pave_info:
        name = pavement_info.name
        num = pavement_info.num
        key = f"{name}_{num}"
        local_points = embankment_local_points[f"{name}_{num}"]
        start_edge_structure = pavement_info.start_edge_structure
        end_edge_structure = pavement_info.end_edge_structure
        start_abut_points = None
        end_abut_points = None
        if start_edge_structure is not None:
            if start_edge_structure.structure_type == "abutment":
                start_abut = abut_points_dict[start_edge_structure.structure_name]
                start_abut_points = {
                    "U": start_abut["wing_dict"]["U_wing_top_points"]["UN"],
                    "D": start_abut["wing_dict"]["D_wing_top_points"]["DN"],
                }
        if end_edge_structure is not None:
            if end_edge_structure.structure_type == "abutment":
                end_abut = abut_points_dict[end_edge_structure.structure_name]
                end_abut_points = {
                    "U": end_abut["wing_dict"]["U_wing_top_points"]["UN"],
                    "D": end_abut["wing_dict"]["D_wing_top_points"]["DN"],
                }
        pavement_brep, points_info = get_indiv_brep(
            pavement_info=pavement_info,
            local_points=local_points,
            start_abut_points=start_abut_points,
            end_abut_points=end_abut_points
        )
        output_points_info = list(points_info)
        if key in abut_embankment_local_points:
            world_abut_points = transform_abut_embankment_points(abut_embankment_local_points[key])
            start_info = {
                "start_name": start_edge_structure.structure_name,
                "U_points": world_abut_points["start_section"]["U_points"],
                "D_points": world_abut_points["start_section"]["D_points"],
            }
            end_info = {
                "end_name": end_edge_structure.structure_name,
                "U_points": world_abut_points["end_section"]["U_points"],
                "D_points": world_abut_points["end_section"]["D_points"],
            }
            output_points_info = [start_info] + output_points_info + [end_info]

        world_embankment_points_dict[key] = output_points_info
        world_items_dict_for_bake[key] = pavement_brep
        world_items_dict_for_bake_2[key] = output_points_info

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
