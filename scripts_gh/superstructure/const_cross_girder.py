
from dataclasses import fields
from typing import Optional, TypeVar

import Rhino.Geometry as rg

from my_project.config.file_names import Filenames
from my_project.config.paths import (
    FINAL_OUTPUT_DIR,
    INITIAL_OUTPUT_DIR,
)
from my_project.config.schemas.cross_girder_schemas import (
    CrossGirderInfo,
    MainGirderPointInfo_IO,
    MGPointSideInfo,
    SlabBottomPoints_IO,
    TaikeikouInfo,
    YokobariInfo,
    YokogetaInfo,
)
from my_project.config.util_schemas import Point3D, Vector2D
from my_project.utils.bake import get_keys_and_values_for_bake
from my_project.utils.geometry.points import (
    get_point_by_xy_offset,
    get_point_by_xyz_offset,
    interpolate_point_3d,
)
from my_project.utils.geometry_gh.const import (
    const_3Dpoint,
    const_brep_from_all_crvs,
    const_line_obj,
    const_normal_srf_from_curve_and_point,
    const_point_along_curve,
    const_point_obj,
    const_polycurve_obj,
    const_srf_from_2crvs,
)
from my_project.utils.geometry_gh.intersect import (
    get_intersect_point_on_crvs,
    get_intersect_point_on_curve_with_xy,
    get_intersect_point_on_srf_with_curve,
    get_intersect_point_on_srf_with_points,
    trim_curve_between_two_points,
)
from my_project.utils.geometry_gh.transform import (
    move_obj,
    offset_line_segment_on_plane_and_get_vectors,
)
from my_project.utils.io import load_from_pickle

T = TypeVar("T")

def get_polyline_from_points(infos: list[T]) -> dict[str, rg.Polyline]:
    points = {}
    names = [f.name for f in fields(infos[0])]
    for name in names:
        points[name] = []
    for info in infos:
        d = {f.name: getattr(info, f.name) for f in fields(info)}
        for name, point in d.items():
            points[name].append(point)
    polylines = {}
    for name, pts in points.items():
        if isinstance(pts[0], Point3D):
            # 端っこを少しだけ伸ばす
            start_distance = const_line_obj(pts[0], pts[1]).Length
            end_distance = const_line_obj(pts[-1], pts[-2]).Length
            extended_start_point = get_point_by_xy_offset(
                point1 = pts[0],
                point2 = pts[1],
                offset = -start_distance * 0.1, # 10%伸ばす
            )
            extended_end_point = get_point_by_xy_offset(
                point1 = pts[-1],
                point2 = pts[-2],
                offset = -end_distance * 0.1, # 10%伸ばす
            )
            extended_pts = [extended_start_point] + pts[1:-1] + [extended_end_point]
            polylines[name] = const_polycurve_obj(extended_pts)
    return polylines

def get_MG_polylines(
    MG_point_dict_for_CG_for_MG: list[MainGirderPointInfo_IO], #あるMGについて
):
    MG_type = "I" if MG_point_dict_for_CG_for_MG[0].I_points is not None else "Box"
    if MG_type == "I":
        info_list = [mg_point_info.I_points for mg_point_info in MG_point_dict_for_CG_for_MG]
    else:
        info_list = [mg_point_info.Box_points for mg_point_info in MG_point_dict_for_CG_for_MG]
    return get_polyline_from_points(info_list)

def get_slab_bottom_polylines(
    slab_bottom_points_for_CG: list[list[SlabBottomPoints_IO]],
):
    slab_bottom_polyline_dict_list = []
    CG_name_list = []
    for slab_bottom_point_for_CG in slab_bottom_points_for_CG:
        slab_bottom_polyline_dict_list.append(get_polyline_from_points(slab_bottom_point_for_CG))
        CG_name_list.append(info.CG_name for info in slab_bottom_point_for_CG)
    return slab_bottom_polyline_dict_list, CG_name_list

def get_MG_point_or_polyline(
    point_name: str,
    MG_point_info: Optional[MainGirderPointInfo_IO] = None,
    MG_polyline_dict: Optional[dict[str, rg.Polyline]] = None,
) -> Point3D:
    shared_point_name = [
        "top_out_I_point",
        "top_out_O_point",
        "top_in_O_point",
        "top_in_I_point",
        "bottom_in_O_point",
        "bottom_out_O_point",
        "bottom_out_I_point",
        "bottom_in_I_point",
    ]
    replace_point_dict = { # keyはMG_point_infoのI_pointsの名前、valueはMG_point_infoのBox_pointsの名前
        "web_top_O_point": "Oweb_top_O_point",
        "web_bottom_O_point": "Oweb_bottom_O_point",
        "web_top_I_point": "Iweb_top_I_point",
        "web_bottom_I_point": "Iweb_bottom_I_point",
    }
    only_Box_point_name = [
        "Oweb_top_I_point",
        "Iweb_top_O_point",
        "Oweb_bottom_I_point",
        "Iweb_bottom_O_point",
    ]
    if MG_point_info is not None:
        if MG_point_info.I_points is not None:
            if point_name in shared_point_name:
                return getattr(MG_point_info.I_points, point_name)
            elif point_name in replace_point_dict:
                return getattr(MG_point_info.I_points, point_name) # kyeはI_pointsの名前なのでOK
            else:
                raise ValueError(f"Error: {point_name}はMainGirderPointInfo_IOのI_pointsに存在しません。")
        elif MG_point_info.Box_points is not None:
            if point_name in shared_point_name:
                return getattr(MG_point_info.Box_points, point_name)
            elif point_name in replace_point_dict:
                Box_point_name = replace_point_dict[point_name]
                return getattr(MG_point_info.Box_points, Box_point_name)
            elif point_name in only_Box_point_name:
                return getattr(MG_point_info.Box_points, point_name)
            else:
                raise ValueError(f"Error: {point_name}はMainGirderPointInfo_IOのBox_pointsに存在しません。")
    elif MG_polyline_dict is not None:
        if point_name in shared_point_name:
            return MG_polyline_dict[point_name]
        elif point_name in replace_point_dict:
            if point_name in MG_polyline_dict:
                return MG_polyline_dict[point_name]
            box_polyline_name = replace_point_dict[point_name]
            if box_polyline_name in MG_polyline_dict:
                return MG_polyline_dict[box_polyline_name]
        elif point_name in only_Box_point_name:
            return MG_polyline_dict[point_name]
        else:
            raise ValueError(f"Error: {point_name}はMG_polyline_dictに存在しません。")

def get_MG_point_side_info(
    MG_point_info: MainGirderPointInfo_IO,
    required_side: str, # "I" or "O"
) -> MGPointSideInfo:
    if required_side == "I":
        return MGPointSideInfo(
            top_out = get_MG_point_or_polyline(point_name="top_out_I_point", MG_point_info=MG_point_info),
            top_in = get_MG_point_or_polyline(point_name="top_in_I_point", MG_point_info=MG_point_info),
            bottom_out = get_MG_point_or_polyline(point_name="bottom_out_I_point", MG_point_info=MG_point_info),
            bottom_in = get_MG_point_or_polyline(point_name="bottom_in_I_point", MG_point_info=MG_point_info),
            web_bottom= get_MG_point_or_polyline(point_name="web_bottom_I_point", MG_point_info=MG_point_info),
            web_top = get_MG_point_or_polyline(point_name="web_top_I_point", MG_point_info=MG_point_info),
        )
    elif required_side == "O":
        return MGPointSideInfo(
            top_out = get_MG_point_or_polyline(point_name="top_out_O_point", MG_point_info=MG_point_info),
            top_in = get_MG_point_or_polyline(point_name="top_in_O_point", MG_point_info=MG_point_info),
            bottom_out = get_MG_point_or_polyline(point_name="bottom_out_O_point", MG_point_info=MG_point_info),
            bottom_in = get_MG_point_or_polyline(point_name="bottom_in_O_point", MG_point_info=MG_point_info),
            web_bottom= get_MG_point_or_polyline(point_name="web_bottom_O_point", MG_point_info=MG_point_info),
            web_top = get_MG_point_or_polyline(point_name="web_top_O_point", MG_point_info=MG_point_info),
        )
    
def get_MG_polyline_side_dict(
    MG_polyline_dict: dict[str, rg.Polyline],
    required_side: str, # "I" or "O"
) -> dict[str, rg.Polyline]:
    if required_side == "I":
        return {
            "top_out": get_MG_point_or_polyline(point_name="top_out_I_point", MG_polyline_dict=MG_polyline_dict),
            "top_in": get_MG_point_or_polyline(point_name="top_in_I_point", MG_polyline_dict=MG_polyline_dict),
            "bottom_out": get_MG_point_or_polyline(point_name="bottom_out_I_point", MG_polyline_dict=MG_polyline_dict),
            "bottom_in": get_MG_point_or_polyline(point_name="bottom_in_I_point", MG_polyline_dict=MG_polyline_dict),
            "web_bottom": get_MG_point_or_polyline(point_name="web_bottom_I_point", MG_polyline_dict=MG_polyline_dict),
            "web_top": get_MG_point_or_polyline(point_name="web_top_I_point", MG_polyline_dict=MG_polyline_dict),
        }
    elif required_side == "O":
        return {
            "top_out": get_MG_point_or_polyline(point_name="top_out_O_point", MG_polyline_dict=MG_polyline_dict),
            "top_in": get_MG_point_or_polyline(point_name="top_in_O_point", MG_polyline_dict=MG_polyline_dict),
            "bottom_out": get_MG_point_or_polyline(point_name="bottom_out_O_point", MG_polyline_dict=MG_polyline_dict),
            "bottom_in": get_MG_point_or_polyline(point_name="bottom_in_O_point", MG_polyline_dict=MG_polyline_dict),
            "web_bottom": get_MG_point_or_polyline(point_name="web_bottom_O_point", MG_polyline_dict=MG_polyline_dict),
            "web_top": get_MG_point_or_polyline(point_name="web_top_O_point", MG_polyline_dict=MG_polyline_dict),
        }
    else:
        raise ValueError("Error: required_sideは'I'か'O'でなければなりません。")

def get_split_crvs_with_base_points_offset(
    base_point_O: Point3D,
    base_point_I: Point3D,
    base_point_O_crv: rg.Polyline,
    base_point_I_crv: rg.Polyline,
    target_crvs: list[rg.Polyline],
    shared_offset: Optional[float] = None,
    prev_offset: Optional[float] = None,
    next_offset: Optional[float] = None,
) -> list[rg.Polyline]:
    prev_point_O = const_point_along_curve(
        curve=base_point_O_crv,
        base_point=base_point_O,
        offset= -shared_offset/2 if shared_offset is not None else -prev_offset,
    )
    prev_point_I = const_point_along_curve(
        curve=base_point_I_crv,
        base_point=base_point_I,
        offset= -shared_offset/2 if shared_offset is not None else -prev_offset,
    )
    next_point_O = const_point_along_curve(
        curve=base_point_O_crv,
        base_point=base_point_O,
        offset= shared_offset/2 if shared_offset is not None else next_offset,
    )
    next_point_I = const_point_along_curve(
        curve=base_point_I_crv,
        base_point=base_point_I,
        offset= shared_offset/2 if shared_offset is not None else next_offset,
    )
    split_crvs = []
    for target_crv in target_crvs:
        if target_crv == base_point_O_crv:
            intersect_pt_next = next_point_O
            intersect_pt_prev = prev_point_O
        elif target_crv == base_point_I_crv:
            intersect_pt_next = next_point_I
            intersect_pt_prev = prev_point_I
        else:
            intersect_pt_next = get_intersect_point_on_crvs(
                target_crv=target_crv,
                cutter_crv_points=[next_point_O, next_point_I]
            )
            intersect_pt_prev = get_intersect_point_on_crvs(
                target_crv=target_crv,
                cutter_crv_points=[prev_point_O, prev_point_I]
            )
        split_crv = trim_curve_between_two_points(
            target_curve=target_crv,
            start_point=intersect_pt_prev,
            end_point=intersect_pt_next,
        )
        split_crvs.append(split_crv)
    return split_crvs

def get_split_crvs_with_base_point_offset_with_plane(
    base_point: Point3D,
    base_point_crv: rg.Polyline,
    target_crvs: list[rg.Polyline],
    shared_offset: Optional[float] = None,
    prev_offset: Optional[float] = None,
    next_offset: Optional[float] = None,
) -> list[rg.Polyline]:
    prev_point = const_point_along_curve(
        curve=base_point_crv,
        base_point=base_point,
        offset= -shared_offset/2 if shared_offset is not None else -prev_offset,
    )
    next_point = const_point_along_curve(
        curve=base_point_crv,
        base_point=base_point,
        offset= shared_offset/2 if shared_offset is not None else next_offset,
    )
    base_point_srf = const_normal_srf_from_curve_and_point(
        curve=base_point_crv,
        point=base_point,
    )
    prev_base_vector = rg.Vector3d(prev_point.X - base_point.x, prev_point.Y - base_point.y, prev_point.Z - base_point.z)
    next_base_vector = rg.Vector3d(next_point.X - base_point.x, next_point.Y - base_point.y, next_point.Z - base_point.z)
    prev_point_srf = move_obj(base_point_srf, prev_base_vector)
    next_point_srf = move_obj(base_point_srf, next_base_vector)
    
    split_crvs = []
    for target_crv in target_crvs:
        if target_crv == base_point_crv:
            intersect_pt_next = next_point
            intersect_pt_prev = prev_point
        else:
            intersect_pt_next = get_intersect_point_on_srf_with_curve(next_point_srf, target_crv)
            intersect_pt_prev = get_intersect_point_on_srf_with_curve(prev_point_srf, target_crv)
        split_crv = trim_curve_between_two_points(
            target_curve=target_crv,
            start_point=intersect_pt_prev,
            end_point=intersect_pt_next,
        )
        split_crvs.append(split_crv)
    return split_crvs

def get_flange_crvs(thickness, TB, base_I_crv, base_O_crv):
    if TB == "top":
        above_I_crv = base_I_crv
        above_O_crv = base_O_crv
        below_I_crv = move_obj(above_I_crv, rg.Vector3d(0, 0, -thickness))
        below_O_crv = move_obj(above_O_crv, rg.Vector3d(0, 0, -thickness))
    elif TB == "bottom":
        below_I_crv = base_I_crv
        below_O_crv = base_O_crv
        above_I_crv = move_obj(below_I_crv, rg.Vector3d(0, 0, thickness))
        above_O_crv = move_obj(below_O_crv, rg.Vector3d(0, 0, thickness))
    else:
        raise ValueError(f"Error: TBは'top'か'bottom'でなければなりません。TB: {TB}")
    return below_I_crv, above_I_crv, above_O_crv, below_O_crv

def debug_curve_on_base(cut_crv, base_crv, name: str):
    print(f"\n===== {name} =====")
    for label, pt in [("start", cut_crv.PointAtStart), ("end", cut_crv.PointAtEnd)]:
        ok, t = base_crv.ClosestPoint(pt)
        if ok:
            base_pt = base_crv.PointAt(t)
            print(f"{label} distance to base:", pt.DistanceTo(base_pt))
            print(f"{label} z delta:", pt.Z - base_pt.Z)
            print(f"{label} cut:", pt)
            print(f"{label} base:", base_pt)
        else:
            print(f"{label} closest point failed")

def get_H_breps(
    top_flange_crvs: list[rg.Polyline], #top_flange_top_O_crv, top_flange_top_I_crv
    bottom_flange_crvs: list[rg.Polyline], #bottom_flange_bottom_O_crv, bottom_flange_bottom_I_crv,
    web_crvs: list[rg.Polyline],
    top_flange_thickness: float,
    bottom_flange_thickness: float,
) -> tuple[rg.Brep]: 
    top_flange_crvs_list = list(get_flange_crvs( 
        thickness = top_flange_thickness,
        TB = "top",
        base_I_crv= top_flange_crvs[1],
        base_O_crv= top_flange_crvs[0],
    ))
    bottom_flange_crvs_list = list(get_flange_crvs(
        thickness = bottom_flange_thickness,
        TB = "bottom",
        base_I_crv= bottom_flange_crvs[1],
        base_O_crv= bottom_flange_crvs[0],
    ))
    top_flange_brep = const_brep_from_all_crvs(top_flange_crvs_list)
    bottom_flange_brep = const_brep_from_all_crvs(bottom_flange_crvs_list)
    web_brep = const_brep_from_all_crvs(web_crvs)
    return top_flange_brep, bottom_flange_brep, web_brep

def get_haridashi_H_breps(slab_bottom_polyline, MG_point_side, MG_polyline_side_dict, info, tol: float = 1e-1, debug_crvs: Optional[list] = None):
    # 上フランジ
    top_base_point = MG_point_side.top_out
    top_base_crv = MG_polyline_side_dict["top_out"]
    slab_bottom_crv = slab_bottom_polyline
    if info.top_flange.width is None:
        top_flange_crvs= get_split_crvs_with_base_point_offset_with_plane(
            base_point = top_base_point,
            base_point_crv= top_base_crv,
            target_crvs = [slab_bottom_crv, top_base_crv],
            prev_offset= info.top_flange.width_minus,
            next_offset= info.top_flange.width_plus
        )
    else:
        top_flange_crvs= get_split_crvs_with_base_point_offset_with_plane(
            base_point = top_base_point,
            base_point_crv= top_base_crv,
            target_crvs = [slab_bottom_crv, top_base_crv],
            shared_offset= info.top_flange.width
        )
    top_flange_thickness = float(info.top_flange.thickness)

    # 下フランジ
    MG_top_flange_thichkness = MG_point_side.top_out.z - MG_point_side.top_in.z
    bottom_flange_thickness = float(info.bottom_flange.thickness)
    edge_height = float(info.web.edge_height)
    web_height = float(info.web.height)
    I_gap = web_height - MG_top_flange_thichkness
    bottom_base_crv_I = move_obj(MG_polyline_side_dict["web_top"], rg.Vector3d(0, 0, -I_gap))
    bottom_base_crv_O = move_obj(slab_bottom_crv, rg.Vector3d(0, 0, -edge_height))
    if info.bottom_flange.width is None:
        bottom_flange_crvs = get_split_crvs_with_base_point_offset_with_plane(
            base_point = top_base_point,
            base_point_crv= top_base_crv,
            target_crvs = [bottom_base_crv_O, bottom_base_crv_I],
            prev_offset= info.bottom_flange.width_minus,
            next_offset= info.bottom_flange.width_plus,
        )
    else:
        bottom_flange_crvs = get_split_crvs_with_base_point_offset_with_plane(
            base_point = top_base_point,
            base_point_crv= top_base_crv,
            target_crvs = [bottom_base_crv_O, bottom_base_crv_I],
            shared_offset= info.bottom_flange.width,
        )
    if debug_crvs is not None:
        debug_crvs.extend(top_flange_crvs)
        debug_crvs.extend(bottom_flange_crvs)
        debug_curve_on_base(
            bottom_flange_crvs[1],
            MG_polyline_side_dict["bottom_out"],
            "haridashi bottom_flange I cut vs MG bottom_out",
        )
    bottom_web_crv_I = move_obj(bottom_flange_crvs[1], rg.Vector3d(0, 0, bottom_flange_thickness))

    # ウェブ
    if abs(MG_top_flange_thichkness - top_flange_thickness) < tol:
        web_polylines = [
            move_obj(top_flange_crvs[0], rg.Vector3d(0, 0, -top_flange_thickness)), # top_in_O
            move_obj(bottom_flange_crvs[0], rg.Vector3d(0, 0, bottom_flange_thickness)), # bottom_in_O
            bottom_web_crv_I, # bottom_in_I
            move_obj(top_flange_crvs[1], rg.Vector3d(0, 0, -top_flange_thickness)), # top_in_I
        ]
    else:
        web_polylines = [
            move_obj(top_flange_crvs[0], rg.Vector3d(0, 0, -top_flange_thickness)), # top_in_O
            move_obj(bottom_flange_crvs[0], rg.Vector3d(0, 0, bottom_flange_thickness)), # bottom_in_O
            bottom_web_crv_I, # bottom_in_I
            MG_polyline_side_dict["web_top"],
            MG_polyline_side_dict["top_in"],
            move_obj(top_flange_crvs[1], rg.Vector3d(0, 0, -top_flange_thickness)), # top_in_I
        ]


    web_crvs = get_split_crvs_with_base_point_offset_with_plane(
        base_point = top_base_point,
        base_point_crv= top_base_crv,
        target_crvs = web_polylines,
        shared_offset= info.web.thickness
    )
    if debug_crvs is not None:
        debug_crvs.extend(web_crvs)
    top_brep, bottom_brep, web_brep = get_H_breps(
        top_flange_crvs=top_flange_crvs,
        bottom_flange_crvs=bottom_flange_crvs,
        web_crvs=web_crvs,
        top_flange_thickness=top_flange_thickness,
        bottom_flange_thickness=bottom_flange_thickness,
    )
    return top_brep, bottom_brep, web_brep

def get_mid_H_breps(
    MG_point_side_O, MG_polyline_side_dict_O, MG_point_side_I, MG_polyline_side_dict_I, info, 
    offset_z_top: Optional[float] = None,
    offset_z_bottom: Optional[float] = None,
    tol: float = 1e-1, # 0.1mmくらいの誤差は許容する
    debug_crvs: Optional[list] = None,
):
    base_point_O = MG_point_side_O.top_out
    base_crv_O = MG_polyline_side_dict_O["top_out"]
    base_point_I = MG_point_side_I.top_out
    base_crv_I = MG_polyline_side_dict_I["top_out"]

    top_flange_thickness = float(info.top_flange.thickness)
    bottom_flange_thickness = float(info.bottom_flange.thickness)
    web_height = float(info.web.height)
    bottom_out_point_O = MG_point_side_O.bottom_out
    bottom_out_crv_O = MG_polyline_side_dict_O["bottom_out"]
    bottom_out_point_I = MG_point_side_I.bottom_out
    bottom_out_crv_I = MG_polyline_side_dict_I["bottom_out"]

    if offset_z_top is not None: #上からの落ちを見るタイプのH鋼
        offset_z_top = float(offset_z_top)
        top_out_point_O = base_point_O
        top_out_crv_O = base_crv_O
        top_out_point_I = base_point_I
        top_out_crv_I = base_crv_I
        top_in_point_O = MG_point_side_O.top_in
        web_top_crv_O = MG_polyline_side_dict_O["web_top"]
        top_in_point_I = MG_point_side_I.top_in
        web_top_crv_I = MG_polyline_side_dict_I["web_top"]
        z_top_gap_O = top_out_point_O.z - top_in_point_O.z
        z_top_gap_I = top_out_point_I.z - top_in_point_I.z
        z_bottom_out_gap_O = top_out_point_O.z - bottom_out_point_O.z
        z_bottom_out_gap_I = top_out_point_I.z - bottom_out_point_I.z
        bottom_gap_z = offset_z_top + web_height
        bottom_based_O = bottom_gap_z >= z_bottom_out_gap_O - tol
        bottom_based_I = bottom_gap_z >= z_bottom_out_gap_I - tol

        def get_top_crv_from_drop(top_out_crv, web_top_crv, drop_z, z_top_gap):
            if drop_z <= 0:
                return top_out_crv
            if drop_z < z_top_gap:
                return move_obj(top_out_crv, rg.Vector3d(0, 0, -drop_z))
            return move_obj(web_top_crv, rg.Vector3d(0, 0, -(drop_z - z_top_gap)))

        if bottom_based_O:
            bottom_crv_O = bottom_out_crv_O
            top_drop_O = max(0, top_out_point_O.z - (bottom_out_point_O.z + web_height))
            top_crv_O = get_top_crv_from_drop(top_out_crv_O, web_top_crv_O, top_drop_O, z_top_gap_O)
        else:
            top_drop_O = offset_z_top
            bottom_crv_O = move_obj(web_top_crv_O, rg.Vector3d(0, 0, -(bottom_gap_z - z_top_gap_O)))
            top_crv_O = get_top_crv_from_drop(top_out_crv_O, web_top_crv_O, top_drop_O, z_top_gap_O)
        if bottom_based_I:
            bottom_crv_I = bottom_out_crv_I
            top_drop_I = max(0, top_out_point_I.z - (bottom_out_point_I.z + web_height))
            top_crv_I = get_top_crv_from_drop(top_out_crv_I, web_top_crv_I, top_drop_I, z_top_gap_I)
        else:
            top_drop_I = offset_z_top
            bottom_crv_I = move_obj(web_top_crv_I, rg.Vector3d(0, 0, -(bottom_gap_z - z_top_gap_I)))
            top_crv_I = get_top_crv_from_drop(top_out_crv_I, web_top_crv_I, top_drop_I, z_top_gap_I)
        bottom_crvs = [bottom_crv_O, bottom_crv_I]
        top_crvs = [top_crv_O, top_crv_I]
    elif offset_z_bottom is not None: #下からの上がりを見るタイプのH鋼
        offset_z_bottom = float(offset_z_bottom)
        web_bottom_point_O = MG_point_side_O.web_bottom
        web_bottom_crv_O = MG_polyline_side_dict_O["web_bottom"]
        web_bottom_point_I = MG_point_side_I.web_bottom
        web_bottom_crv_I = MG_polyline_side_dict_I["web_bottom"]
        z_bottom_gap_O = web_bottom_point_O.z - bottom_out_point_O.z
        z_bottom_gap_I = web_bottom_point_I.z - bottom_out_point_I.z
        top_gap_z = offset_z_bottom + web_height
        top_crvs = [
            move_obj(web_bottom_crv_O, rg.Vector3d(0, 0, top_gap_z - z_bottom_gap_O)),
            move_obj(web_bottom_crv_I, rg.Vector3d(0, 0, top_gap_z - z_bottom_gap_I)),
        ]
        if offset_z_bottom == 0: # 上がりが0の場合、下フランジ脇から
            bottom_crv_O = bottom_out_crv_O
            bottom_crv_I = bottom_out_crv_I
        else:
            if offset_z_bottom < z_bottom_gap_O: # 上がりがフランジ厚より小さい場合、下フランジ脇から
                bottom_crv_O = move_obj(bottom_out_crv_O, rg.Vector3d(0, 0, offset_z_bottom))
            else:
                bottom_crv_O = move_obj(web_bottom_crv_O, rg.Vector3d(0, 0, offset_z_bottom - z_bottom_gap_O))
            if offset_z_bottom < z_bottom_gap_I: # 上がりがフランジ厚より小さい場合、下フランジ脇から
                bottom_crv_I = move_obj(bottom_out_crv_I, rg.Vector3d(0, 0, offset_z_bottom))
            else:
                bottom_crv_I = move_obj(web_bottom_crv_I, rg.Vector3d(0, 0, offset_z_bottom - z_bottom_gap_I))
        bottom_crvs = [bottom_crv_O, bottom_crv_I]
    else: 
        raise ValueError("Error: offset_z_topかoffset_z_bottomのどちらかはNoneであってはなりません。両方とも値がある、または両方ともNoneの場合はエラーです。")
    
    
    if info.top_flange.width is None:
        top_flange_crvs = get_split_crvs_with_base_points_offset(
            base_point_O = base_point_O,
            base_point_I = base_point_I,
            base_point_O_crv = base_crv_O,
            base_point_I_crv = base_crv_I,
            target_crvs = top_crvs,
            prev_offset= info.top_flange.width_minus,
            next_offset= info.top_flange.width_plus,
        )
    else:
        top_flange_crvs = get_split_crvs_with_base_points_offset(
            base_point_O = base_point_O,
            base_point_I = base_point_I,
            base_point_O_crv = base_crv_O,
            base_point_I_crv = base_crv_I,
            target_crvs = top_crvs,
            shared_offset= info.top_flange.width,
        )
    if info.bottom_flange.width is None:
        bottom_flange_crvs = get_split_crvs_with_base_points_offset(
            base_point_O = base_point_O,
            base_point_I = base_point_I,
            base_point_O_crv = base_crv_O,
            base_point_I_crv = base_crv_I,
            target_crvs = bottom_crvs,
            prev_offset= info.bottom_flange.width_minus,
            next_offset= info.bottom_flange.width_plus,
        )
    else:
        bottom_flange_crvs = get_split_crvs_with_base_points_offset(
            base_point_O = base_point_O,
            base_point_I = base_point_I,
            base_point_O_crv = base_crv_O,
            base_point_I_crv = base_crv_I,
            target_crvs = bottom_crvs,
            shared_offset= info.bottom_flange.width,
        )
    if debug_crvs is not None:
        debug_crvs.extend(top_flange_crvs)
        debug_crvs.extend(bottom_flange_crvs)
        debug_curve_on_base(
            bottom_flange_crvs[0],
            bottom_out_crv_O,
            "mid bottom_flange O cut vs MG bottom_out",
        )
        debug_curve_on_base(
            bottom_flange_crvs[1],
            bottom_out_crv_I,
            "mid bottom_flange I cut vs MG bottom_out",
        )

    # ウェブ
    if offset_z_top is not None:
        if top_drop_O > z_top_gap_O:
            O_polylines = [
                move_obj(top_flange_crvs[0], rg.Vector3d(0, 0, -top_flange_thickness)), # top_in_O
                move_obj(bottom_flange_crvs[0], rg.Vector3d(0, 0, bottom_flange_thickness)), # bottom_in_O
            ]
        elif abs(top_drop_O + top_flange_thickness - z_top_gap_O) < tol:
            O_polylines = [
                MG_polyline_side_dict_O["web_top"],
                move_obj(bottom_flange_crvs[0], rg.Vector3d(0, 0, bottom_flange_thickness)), # bottom_in_O
            ]
        else:
            O_polylines = [
                move_obj(top_flange_crvs[0], rg.Vector3d(0, 0, -top_flange_thickness)), # top_in_O
                MG_polyline_side_dict_O["top_in"],
                MG_polyline_side_dict_O["web_top"],
                move_obj(bottom_flange_crvs[0], rg.Vector3d(0, 0, bottom_flange_thickness)), # bottom_in_O
            ]
        if top_drop_I > z_top_gap_I:
            I_polylines = [
                move_obj(bottom_flange_crvs[1], rg.Vector3d(0, 0, bottom_flange_thickness)), # bottom_in_I
                move_obj(top_flange_crvs[1], rg.Vector3d(0, 0, -top_flange_thickness)), # top_in_I
            ]
        elif abs(top_drop_I + top_flange_thickness - z_top_gap_I) < tol:
            I_polylines = [
                move_obj(bottom_flange_crvs[1], rg.Vector3d(0, 0, bottom_flange_thickness)), # bottom_in_I
                MG_polyline_side_dict_I["web_top"],
            ]
        else:
            I_polylines = [
                move_obj(bottom_flange_crvs[1], rg.Vector3d(0, 0, bottom_flange_thickness)), # bottom_in_I
                MG_polyline_side_dict_I["web_top"],
                MG_polyline_side_dict_I["top_in"],
                move_obj(top_flange_crvs[1], rg.Vector3d(0, 0, -top_flange_thickness)), # top_in_I
            ]

    elif offset_z_bottom is not None:
        if offset_z_bottom > z_bottom_gap_O:
            O_polylines = [
                move_obj(top_flange_crvs[0], rg.Vector3d(0, 0, -top_flange_thickness)), # top_in_O
                move_obj(bottom_flange_crvs[0], rg.Vector3d(0, 0, bottom_flange_thickness)), # bottom_in_O
            ]
        elif abs(offset_z_bottom + bottom_flange_thickness - z_bottom_gap_O) < tol:
            O_polylines = [
                move_obj(top_flange_crvs[0], rg.Vector3d(0, 0, -top_flange_thickness)), # top_in_O
                MG_polyline_side_dict_O["web_bottom"],
            ]
        else:
            O_polylines = [
                move_obj(top_flange_crvs[0], rg.Vector3d(0, 0, -top_flange_thickness)), # top_in_O
                MG_polyline_side_dict_O["web_bottom"],
                MG_polyline_side_dict_O["bottom_in"],
                move_obj(bottom_flange_crvs[0], rg.Vector3d(0, 0, bottom_flange_thickness)), # bottom_in_O
            ]
        if offset_z_bottom > z_bottom_gap_I:
            I_polylines = [
                move_obj(bottom_flange_crvs[1], rg.Vector3d(0, 0, bottom_flange_thickness)), # bottom_in_I
                move_obj(top_flange_crvs[1], rg.Vector3d(0, 0, -top_flange_thickness)), # top_in_I
            ]
        elif abs(offset_z_bottom + bottom_flange_thickness - z_bottom_gap_I) < tol:
            I_polylines = [
                move_obj(bottom_flange_crvs[1], rg.Vector3d(0, 0, bottom_flange_thickness)), # bottom_in_I
                MG_polyline_side_dict_I["web_bottom"],
            ]
        else:            
            I_polylines = [
                move_obj(bottom_flange_crvs[1], rg.Vector3d(0, 0, bottom_flange_thickness)), # bottom_in_I
                MG_polyline_side_dict_I["bottom_in"],
                MG_polyline_side_dict_I["web_bottom"],
                move_obj(top_flange_crvs[1], rg.Vector3d(0, 0, -top_flange_thickness)), # top_in_I
            ]
    web_polylines = O_polylines + I_polylines
    web_crvs = get_split_crvs_with_base_points_offset(
        base_point_O = base_point_O,
        base_point_I = base_point_I,
        base_point_O_crv = base_crv_O,
        base_point_I_crv = base_crv_I,
        target_crvs = web_polylines,
        shared_offset= info.web.thickness,
    )
    if debug_crvs is not None:
        debug_crvs.extend(web_crvs)
    top_brep, bottom_brep, web_brep = get_H_breps(
        top_flange_crvs=top_flange_crvs,
        bottom_flange_crvs=bottom_flange_crvs,
        web_crvs=web_crvs,
        top_flange_thickness=top_flange_thickness,
        bottom_flange_thickness=bottom_flange_thickness,
    )

    return top_brep, bottom_brep, web_brep

def get_yokobari_breps(
    CG_info: YokobariInfo,
    MG_point_infos: list[MainGirderPointInfo_IO],
    MG_polyline_dict_for_bridge: dict[str, dict[str, rg.Polyline]],
    slab_bottom_polyline_dict_for_bridge: list[dict[str, rg.Polyline]],
    debug_crvs: Optional[list] = None,
) -> dict[str, rg.Brep]:
    CG_breps = {}
    for i in range(len(MG_point_infos) - 1):
        MG_point_info_I = MG_point_infos[i]
        MG_point_info_O = MG_point_infos[i+1]
        MG_polyline_dict_I = MG_polyline_dict_for_bridge[MG_point_info_I.MG_name]
        MG_polyline_dict_O = MG_polyline_dict_for_bridge[MG_point_info_O.MG_name]
        MG_point_I_side = get_MG_point_side_info(MG_point_info_I, "I")
        MG_point_O_side = get_MG_point_side_info(MG_point_info_O, "O")
        MG_polyline_I_side_dict = get_MG_polyline_side_dict(MG_polyline_dict_I, "I")
        MG_polyline_O_side_dict = get_MG_polyline_side_dict(MG_polyline_dict_O, "O")
        # まずフランジ
        top_base_point_O = MG_point_O_side.top_out
        top_base_point_I = MG_point_I_side.top_out
        bottom_base_point_O = MG_point_O_side.bottom_out
        bottom_base_point_I = MG_point_I_side.bottom_out
        top_base_crv_O = MG_polyline_O_side_dict["top_out"]
        top_base_crv_I = MG_polyline_I_side_dict["top_out"]
        bottom_base_crv_O = MG_polyline_O_side_dict["bottom_out"]
        bottom_base_crv_I = MG_polyline_I_side_dict["bottom_out"]
        [top_flange_top_O_crv, top_flange_top_I_crv]= get_split_crvs_with_base_points_offset(
                base_point_O = top_base_point_O,
                base_point_I = top_base_point_I,
                base_point_O_crv = top_base_crv_O,
                base_point_I_crv = top_base_crv_I,
                target_crvs = [top_base_crv_O, top_base_crv_I],
                prev_offset= CG_info.center_info.top_flange.width_minus,
                next_offset= CG_info.center_info.top_flange.width_plus,
            )
        top_flange_thickness = float(CG_info.center_info.top_flange.thickness)
        top_flange_crvs = get_flange_crvs( # below_I_crv, above_I_crv, above_O_crv, below_O_crv
            thickness = top_flange_thickness,
            TB = "top",
            base_I_crv= top_flange_top_I_crv,
            base_O_crv= top_flange_top_O_crv,
        )
        top_flange_brep = const_brep_from_all_crvs(list(top_flange_crvs))
        [bottom_flange_bottom_O_crv, bottom_flange_bottom_I_crv] = get_split_crvs_with_base_points_offset(
            base_point_O = bottom_base_point_O,
            base_point_I = bottom_base_point_I,
            base_point_O_crv = bottom_base_crv_O,
            base_point_I_crv = bottom_base_crv_I,
            target_crvs = [bottom_base_crv_O, bottom_base_crv_I],
            prev_offset= CG_info.center_info.bottom_flange.width_minus,
            next_offset= CG_info.center_info.bottom_flange.width_plus,
        )
        bottom_flange_thickness = float(CG_info.center_info.bottom_flange.thickness)
        bottom_flange_crvs = get_flange_crvs(
            thickness = bottom_flange_thickness,
            TB = "bottom",
            base_I_crv= bottom_flange_bottom_I_crv,
            base_O_crv= bottom_flange_bottom_O_crv,
        )
        if debug_crvs is not None:
            debug_crvs.extend([top_flange_top_O_crv, top_flange_top_I_crv])
            debug_crvs.extend([bottom_flange_bottom_O_crv, bottom_flange_bottom_I_crv])
        bottom_flange_brep = const_brep_from_all_crvs(list(bottom_flange_crvs))
        CG_breps[f"top_flange_{i}"] = top_flange_brep
        CG_breps[f"bottom_flange_{i}"] = bottom_flange_brep

        # 中間ウェブ
        mid_top_crv_O = move_obj(top_base_crv_O, rg.Vector3d(0, 0, -top_flange_thickness))
        mid_bottom_crv_O = move_obj(bottom_base_crv_O, rg.Vector3d(0, 0, bottom_flange_thickness))
        mid_top_crv_I = move_obj(top_base_crv_I, rg.Vector3d(0, 0, -top_flange_thickness))
        mid_bottom_crv_I = move_obj(bottom_base_crv_I, rg.Vector3d(0, 0, bottom_flange_thickness))
        web_offset = CG_info.web_offset
        target_crv_names = ["top_in", "web_top", "web_bottom", "bottom_in"]
        I_target_crvs = [MG_polyline_I_side_dict[name] for name in target_crv_names]
        O_target_crvs = [MG_polyline_O_side_dict[name] for name in target_crv_names[::-1]] # O側は逆順で処理する
        target_crvs = [
            *I_target_crvs,
            mid_bottom_crv_I,
            mid_bottom_crv_O,
            *O_target_crvs,
            mid_top_crv_O,
            mid_top_crv_I,
        ]
        prev_crvs = get_split_crvs_with_base_points_offset(
            base_point_O = bottom_base_point_O,
            base_point_I = bottom_base_point_I,
            base_point_O_crv = bottom_base_crv_O,
            base_point_I_crv = bottom_base_crv_I,
            target_crvs = target_crvs,
            prev_offset= web_offset + CG_info.center_info.web.thickness / 2,
            next_offset= -(web_offset - CG_info.center_info.web.thickness / 2), # prev側に行くのでマイナス
        )
        next_crvs = get_split_crvs_with_base_points_offset(
            base_point_O = bottom_base_point_O,
            base_point_I = bottom_base_point_I,
            base_point_O_crv = bottom_base_crv_O,
            base_point_I_crv = bottom_base_crv_I,
            target_crvs = target_crvs,
            prev_offset= -(web_offset - CG_info.center_info.web.thickness / 2), # next側に行くのでマイナス
            next_offset= web_offset + CG_info.center_info.web.thickness / 2,
        )
        if debug_crvs is not None:
            debug_crvs.extend(prev_crvs)
            debug_crvs.extend(next_crvs)
        CG_breps[f"web_prev_{i}"] = const_brep_from_all_crvs(prev_crvs)
        CG_breps[f"web_next_{i}"] = const_brep_from_all_crvs(next_crvs)
    
    # 左右の張出
    I_slab_bottom_polyline = slab_bottom_polyline_dict_for_bridge["I"]
    O_slab_bottom_polyline = slab_bottom_polyline_dict_for_bridge["O"]
    MG_point_info_I = MG_point_infos[-1] 
    MG_point_info_O = MG_point_infos[0]
    MG_polyline_dict_I = MG_polyline_dict_for_bridge[MG_point_info_I.MG_name]
    MG_polyline_dict_O = MG_polyline_dict_for_bridge[MG_point_info_O.MG_name]
    MG_point_I_side = get_MG_point_side_info(MG_point_info_I, "I")
    MG_point_O_side = get_MG_point_side_info(MG_point_info_O, "O")
    MG_polyline_I_side_dict = get_MG_polyline_side_dict(MG_polyline_dict_I, "I")
    MG_polyline_O_side_dict = get_MG_polyline_side_dict(MG_polyline_dict_O, "O")

    def get_extended_haridashi_breps(slab_bottom_polyline, MG_point_side, MG_polyline_side_dict, edge_info):
        top_base_point = MG_point_side.top_out
        bottom_base_point = MG_point_side.bottom_out
        top_base_crv = MG_polyline_side_dict["top_out"]
        bottom_base_crv = MG_polyline_side_dict["bottom_out"]
        slab_bottom_crv = slab_bottom_polyline
        [top_flange_top_O_crv, top_flange_top_I_crv]= get_split_crvs_with_base_point_offset_with_plane(
            base_point = top_base_point,
            base_point_crv= top_base_crv,
            target_crvs = [slab_bottom_crv, top_base_crv],
            prev_offset= CG_info.center_info.top_flange.width_minus,
            next_offset= CG_info.center_info.top_flange.width_plus,
        )
        top_flange_thickness = float(CG_info.center_info.top_flange.thickness)
        top_flange_crvs = get_flange_crvs( # below_I_crv, above_I_crv, above_O_crv, below_O_crv
            thickness = top_flange_thickness,
            TB = "top",
            base_I_crv= top_flange_top_I_crv,
            base_O_crv= top_flange_top_O_crv,
        )
        top_flange_brep = const_brep_from_all_crvs(list(top_flange_crvs))
        # 下はslabのbottom_crvを平行移動させたものとする。
        z_gap = bottom_base_point.z - top_base_point.z
        slab_bottom_crv_moved = move_obj(slab_bottom_crv, rg.Vector3d(0, 0, z_gap))
        [bottom_flange_bottom_O_crv, bottom_flange_bottom_I_crv] = get_split_crvs_with_base_point_offset_with_plane(
            base_point = bottom_base_point,
            base_point_crv= bottom_base_crv,
            target_crvs = [slab_bottom_crv_moved, bottom_base_crv],
            prev_offset= CG_info.center_info.bottom_flange.width_minus,
            next_offset= CG_info.center_info.bottom_flange.width_plus,
        )
        bottom_flange_thickness = float(CG_info.center_info.bottom_flange.thickness)
        bottom_flange_crvs = get_flange_crvs(
            thickness = bottom_flange_thickness,
            TB = "bottom",
            base_I_crv= bottom_flange_bottom_I_crv,
            base_O_crv= bottom_flange_bottom_O_crv,
        )
        bottom_flange_brep = const_brep_from_all_crvs(list(bottom_flange_crvs))
        # 中間ウェブ
        mid_top_crv_O = move_obj(slab_bottom_crv, rg.Vector3d(0, 0, -top_flange_thickness))
        mid_bottom_crv_O = move_obj(slab_bottom_crv_moved, rg.Vector3d(0, 0, bottom_flange_thickness))
        mid_top_crv_I = move_obj(top_base_crv, rg.Vector3d(0, 0, -top_flange_thickness))
        mid_bottom_crv_I = move_obj(bottom_base_crv, rg.Vector3d(0, 0, bottom_flange_thickness))
        web_offset = CG_info.web_offset
        target_crv_names = ["top_in", "web_top", "web_bottom", "bottom_in"]
        I_target_crvs = [MG_polyline_side_dict[name] for name in target_crv_names]
        target_crvs = [
            *I_target_crvs,
            mid_bottom_crv_I,
            mid_bottom_crv_O,
            mid_top_crv_O,
            mid_top_crv_I,
        ]
        prev_crvs = get_split_crvs_with_base_point_offset_with_plane(
            base_point = bottom_base_point,
            base_point_crv= bottom_base_crv,
            target_crvs = target_crvs,
            prev_offset= web_offset + CG_info.center_info.web.thickness / 2,
            next_offset= -(web_offset - CG_info.center_info.web.thickness / 2), # prev側に行くのでマイナス
        )
        next_crvs = get_split_crvs_with_base_point_offset_with_plane(
            base_point = bottom_base_point,
            base_point_crv= bottom_base_crv,
            target_crvs = target_crvs,
            prev_offset= -(web_offset - CG_info.center_info.web.thickness / 2), # next側に行くのでマイナス
            next_offset= web_offset + CG_info.center_info.web.thickness / 2,
        )
        if debug_crvs is not None:
            debug_crvs.extend(prev_crvs)
            debug_crvs.extend(next_crvs)
        prev_web_brep = const_brep_from_all_crvs(prev_crvs)
        next_web_brep = const_brep_from_all_crvs(next_crvs)
        # 端っこのウェブ
        edge_offset = edge_info.offset
        edge_thickness = edge_info.thickness
        mid_top_I_prev = prev_crvs[-1].PointAtEnd
        mid_top_I_next = next_crvs[-1].PointAtStart
        mid_top_O_prev = prev_crvs[-2].PointAtEnd
        mid_top_O_next = next_crvs[-2].PointAtStart
        mid_bottom_O_prev = prev_crvs[-3].PointAtEnd
        mid_bottom_O_next = next_crvs[-3].PointAtStart
        mid_bottom_I_prev = prev_crvs[-4].PointAtEnd
        mid_bottom_I_next = next_crvs[-4].PointAtStart
        mid_top_prev_line = const_line_obj(mid_top_O_prev, mid_top_I_prev)
        mid_top_next_line = const_line_obj(mid_top_O_next, mid_top_I_next)
        mid_bottom_prev_line = const_line_obj(mid_bottom_O_prev, mid_bottom_I_prev)
        mid_bottom_next_line = const_line_obj(mid_bottom_O_next, mid_bottom_I_next)
        top_crvs = get_split_crvs_with_base_points_offset(
            base_point_O=mid_top_O_prev,
            base_point_I=mid_top_O_next,
            base_point_O_crv=mid_top_prev_line,
            base_point_I_crv=mid_top_next_line,
            target_crvs=[mid_top_prev_line, mid_top_next_line],
            prev_offset= -(edge_offset - edge_thickness / 2), # I側に行くのでマイナス
            next_offset= edge_offset + edge_thickness / 2,
        )
        bottom_crvs = get_split_crvs_with_base_points_offset(
            base_point_O=mid_bottom_O_prev,
            base_point_I=mid_bottom_O_next,
            base_point_O_crv=mid_bottom_prev_line,
            base_point_I_crv=mid_bottom_next_line,
            target_crvs=[mid_bottom_prev_line, mid_bottom_next_line],
            prev_offset= -(edge_offset - edge_thickness / 2), # I側に行くのでマイナス
            next_offset= edge_offset + edge_thickness / 2,
        )
        if debug_crvs is not None:
            debug_crvs.extend(top_crvs)
            debug_crvs.extend(bottom_crvs)
        edge_web_brep = const_brep_from_all_crvs([
            top_crvs[0],
            top_crvs[1],
            bottom_crvs[1],
            bottom_crvs[0],
        ])
        return top_flange_brep, bottom_flange_brep, prev_web_brep, next_web_brep, edge_web_brep

    if CG_info.outer_extension:
        O_edge_top_flange_brep, O_edge_bottom_flange_brep, O_edge_prev_web_brep, O_edge_next_web_brep, O_edge_edge_web_brep = get_extended_haridashi_breps(O_slab_bottom_polyline, MG_point_O_side, MG_polyline_O_side_dict, CG_info.outer_edge_info)
        CG_breps["O_edge_top_flange"] = O_edge_top_flange_brep
        CG_breps["O_edge_bottom_flange"] = O_edge_bottom_flange_brep
        CG_breps["O_edge_prev_web"] = O_edge_prev_web_brep
        CG_breps["O_edge_next_web"] = O_edge_next_web_brep
        CG_breps["O_edge_edge_web"] = O_edge_edge_web_brep
    if CG_info.inner_extension:
        I_edge_top_flange_brep, I_edge_bottom_flange_brep, I_edge_prev_web_brep, I_edge_next_web_brep, I_edge_edge_web_brep = get_extended_haridashi_breps(I_slab_bottom_polyline, MG_point_I_side, MG_polyline_I_side_dict, CG_info.inner_edge_info)
        CG_breps["I_edge_top_flange"] = I_edge_top_flange_brep
        CG_breps["I_edge_bottom_flange"] = I_edge_bottom_flange_brep
        CG_breps["I_edge_prev_web"] = I_edge_prev_web_brep
        CG_breps["I_edge_next_web"] = I_edge_next_web_brep
        CG_breps["I_edge_edge_web"] = I_edge_edge_web_brep
    
    if CG_info.outer_existence:
        O_edge_top_brep, O_edge_bottom_brep, O_edge_web_brep = get_haridashi_H_breps(O_slab_bottom_polyline, MG_point_O_side, MG_polyline_O_side_dict, CG_info.outer_info, debug_crvs=debug_crvs)
        CG_breps["O_edge_top_flange"] = O_edge_top_brep
        CG_breps["O_edge_bottom_flange"] = O_edge_bottom_brep
        CG_breps["O_edge_web"] = O_edge_web_brep
    if CG_info.inner_existence:
        I_edge_top_brep, I_edge_bottom_brep, I_edge_web_brep = get_haridashi_H_breps(I_slab_bottom_polyline, MG_point_I_side, MG_polyline_I_side_dict, CG_info.inner_info, debug_crvs=debug_crvs)
        CG_breps["I_edge_top_flange"] = I_edge_top_brep
        CG_breps["I_edge_bottom_flange"] = I_edge_bottom_brep
        CG_breps["I_edge_web"] = I_edge_web_brep
    return CG_breps


def get_taikeikou_breps(
    CG_info: TaikeikouInfo,
    MG_point_infos: list[MainGirderPointInfo_IO],
    MG_polyline_dict_for_bridge: dict[str, dict[str, rg.Polyline]],
    slab_bottom_polyline_dict_for_bridge: dict[str, rg.Polyline],
    debug_crvs: Optional[list] = None,
) -> list[rg.Brep]:
    CG_breps = {}
    for i in range(len(MG_point_infos) - 1):
        MG_point_info_I = MG_point_infos[i]
        MG_point_info_O = MG_point_infos[i+1]
        MG_polyline_dict_I = MG_polyline_dict_for_bridge[MG_point_info_I.MG_name]
        MG_polyline_dict_O = MG_polyline_dict_for_bridge[MG_point_info_O.MG_name]
        MG_point_I_side = get_MG_point_side_info(MG_point_info_I, "I")
        MG_point_O_side = get_MG_point_side_info(MG_point_info_O, "O")
        MG_polyline_I_side_dict = get_MG_polyline_side_dict(MG_polyline_dict_I, "I")
        MG_polyline_O_side_dict = get_MG_polyline_side_dict(MG_polyline_dict_O, "O")
        # まず上H鋼
        top_top_brep, top_bottom_brep, top_web_brep = get_mid_H_breps(
            MG_point_side_O=MG_point_O_side,
            MG_polyline_side_dict_O=MG_polyline_O_side_dict,
            MG_point_side_I=MG_point_I_side,
            MG_polyline_side_dict_I=MG_polyline_I_side_dict,
            info=CG_info.center_top_H_info,
            offset_z_top= CG_info.center_top_H_offset_z,
            debug_crvs=debug_crvs,
        )
        # 下H鋼
        bottom_top_brep, bottom_bottom_brep, bottom_web_brep = get_mid_H_breps(
            MG_point_side_O=MG_point_O_side,
            MG_polyline_side_dict_O=MG_polyline_O_side_dict,
            MG_point_side_I=MG_point_I_side,
            MG_polyline_side_dict_I=MG_polyline_I_side_dict,
            info=CG_info.center_bottom_H_info,
            offset_z_bottom= CG_info.center_bottom_H_offset_z,
            debug_crvs=debug_crvs,
        )
        CG_breps[f"top_H_top_flange_{i}"] = top_top_brep
        CG_breps[f"top_H_bottom_flange_{i}"] = top_bottom_brep
        CG_breps[f"top_H_web_{i}"] = top_web_brep
        CG_breps[f"bottom_H_top_flange_{i}"] = bottom_top_brep
        CG_breps[f"bottom_H_bottom_flange_{i}"] = bottom_bottom_brep
        CG_breps[f"bottom_H_web_{i}"] = bottom_web_brep


        # 中L字
        top_web_gap_O = MG_point_O_side.top_out.z - MG_point_O_side.web_top.z
        top_web_gap_I = MG_point_I_side.top_out.z - MG_point_I_side.web_top.z
        top_flange_bottom_gap_z = CG_info.center_top_H_offset_z + CG_info.center_top_H_info.web.height
        bottom_flange_top_gap_z = CG_info.center_bottom_H_offset_z + CG_info.center_bottom_H_info.web.height
        top_flange_bottom_I_point = Point3D(
            MG_point_I_side.web_top.x,
            MG_point_I_side.web_top.y,
            MG_point_I_side.web_top.z - (top_flange_bottom_gap_z - top_web_gap_I),
        )
        top_flange_bottom_O_point = Point3D(
            MG_point_O_side.web_top.x,
            MG_point_O_side.web_top.y,
            MG_point_O_side.web_top.z - (top_flange_bottom_gap_z - top_web_gap_O),
        )
        top_flange_bottom_I_polyline = move_obj(
            MG_polyline_I_side_dict["web_top"],
            rg.Vector3d(0, 0, -(top_flange_bottom_gap_z - top_web_gap_I)),
        )
        top_flange_bottom_O_polyline = move_obj(
            MG_polyline_O_side_dict["web_top"],
            rg.Vector3d(0, 0, -(top_flange_bottom_gap_z - top_web_gap_O)),
        )
        bottom_flange_top_I_polyline = move_obj(
            MG_polyline_I_side_dict["web_bottom"],
            rg.Vector3d(0, 0, bottom_flange_top_gap_z - top_web_gap_I),
        )
        bottom_flange_top_O_polyline = move_obj(
            MG_polyline_O_side_dict["web_bottom"],
            rg.Vector3d(0, 0, bottom_flange_top_gap_z - top_web_gap_O),
        )
        temp_flange_crvs = get_split_crvs_with_base_points_offset(
            base_point_O=top_flange_bottom_O_point,
            base_point_I=top_flange_bottom_I_point,
            base_point_O_crv=top_flange_bottom_O_polyline,
            base_point_I_crv=top_flange_bottom_I_polyline,
            target_crvs=[top_flange_bottom_O_polyline, top_flange_bottom_I_polyline, bottom_flange_top_O_polyline, bottom_flange_top_I_polyline],
            shared_offset= CG_info.center_L_info.web.thickness + 500 #交差するように少し大きく
        )
        top_flange_bottom_srf = const_srf_from_2crvs([temp_flange_crvs[0], temp_flange_crvs[1]])
        bottom_flange_top_srf = const_srf_from_2crvs([temp_flange_crvs[2], temp_flange_crvs[3]])
        L_thickness_crvs = get_split_crvs_with_base_points_offset(
            base_point_O=top_flange_bottom_O_point,
            base_point_I=top_flange_bottom_I_point,
            base_point_O_crv=top_flange_bottom_O_polyline,
            base_point_I_crv=top_flange_bottom_I_polyline,
            target_crvs=[top_flange_bottom_O_polyline, top_flange_bottom_I_polyline, bottom_flange_top_O_polyline, bottom_flange_top_I_polyline],
            shared_offset= CG_info.center_L_info.web.thickness,
        )
        prev_top_point_O = L_thickness_crvs[0].PointAtStart
        prev_top_point_I = L_thickness_crvs[1].PointAtStart
        prev_bottom_point_O = L_thickness_crvs[2].PointAtStart
        prev_bottom_point_I = L_thickness_crvs[3].PointAtStart
        next_top_point_O = L_thickness_crvs[0].PointAtEnd
        next_top_point_I = L_thickness_crvs[1].PointAtEnd
        next_bottom_point_O = L_thickness_crvs[2].PointAtEnd
        next_bottom_point_I = L_thickness_crvs[3].PointAtEnd

        def get_L_top_bottom_vertical_points(top_point_O, top_point_I, bottom_point_O, bottom_point_I):
            [top_point_O, top_point_I, bottom_point_O, bottom_point_I] = [const_3Dpoint(pt) for pt in [top_point_O, top_point_I, bottom_point_O, bottom_point_I]]
            top_points = [top_point_O]
            V_num = CG_info.V_num
            ratio = 1 / V_num #1個Vなら上はそのまま
            for j in range(1, V_num + 1):
                ratio = j / V_num
                top_points.append(interpolate_point_3d(
                    top_point_O,
                    top_point_I,
                    ratio,
                ))
            top_y_vector = Vector2D(
                x=-(top_point_O.y - top_point_I.y),
                y=top_point_O.x - top_point_I.x,
            )
            bottom_vertical_points = [bottom_point_O] + [
                get_intersect_point_on_curve_with_xy(
                    curve = const_line_obj(bottom_point_O, bottom_point_I),
                    point = point,
                    axis_vector= top_y_vector,
                ) for point in top_points[1:-1]
            ] + [bottom_point_I]
            return top_points, bottom_vertical_points

        prev_top_points, prev_bottom_vertical_points = get_L_top_bottom_vertical_points(prev_top_point_O, prev_top_point_I, prev_bottom_point_O, prev_bottom_point_I)
        next_top_points, next_bottom_vertical_points = get_L_top_bottom_vertical_points(next_top_point_O, next_top_point_I, next_bottom_point_O, next_bottom_point_I)

        for j in range(len(prev_top_points) - 1):
            def get_L_trimmed_points(top_point, bottom_mid_point, bottom_vertical_point, info):
                [top_point, bottom_mid_point, bottom_vertical_point] = [const_point_obj(pt) for pt in [top_point, bottom_mid_point, bottom_vertical_point]]
                moved_points_pos, moved_points_neg, move_vec_normal_pos, move_vec_normal_neg = offset_line_segment_on_plane_and_get_vectors(
                    p1 = top_point,
                    p2 = bottom_mid_point,
                    plane_p3= bottom_vertical_point,
                    offset= info.web.height / 2,
                )
                distance_to_pos = (const_line_obj(*moved_points_pos)).DistanceTo(const_point_obj(bottom_vertical_point), False)
                distance_to_neg = (const_line_obj(*moved_points_neg)).DistanceTo(const_point_obj(bottom_vertical_point), False)
                bottom_cut_target_direction = "pos" if distance_to_pos < distance_to_neg else "neg"
                top_cut_target_direction = "neg" if bottom_cut_target_direction == "pos" else "pos"
                bottom_cut_target_points = moved_points_pos if bottom_cut_target_direction == "pos" else moved_points_neg
                top_cut_target_points = moved_points_neg if top_cut_target_direction == "neg" else moved_points_pos
                O_bottom_point = get_intersect_point_on_srf_with_points(
                    srf = bottom_flange_top_srf,
                    points = bottom_cut_target_points
                )
                I_top_point = get_intersect_point_on_srf_with_points(
                    srf = top_flange_bottom_srf,
                    points = top_cut_target_points
                )
                if bottom_cut_target_direction == "pos":
                    I_bottom_point = const_point_obj(O_bottom_point) + move_vec_normal_neg * float(info.web.height)
                    O_top_point = const_point_obj(I_top_point) + move_vec_normal_pos * float(info.web.height)
                else:
                    I_bottom_point = const_point_obj(O_bottom_point) + move_vec_normal_pos * float(info.web.height)
                    O_top_point = const_point_obj(I_top_point) + move_vec_normal_neg * float(info.web.height)
                return [I_top_point, I_bottom_point], [O_top_point, O_bottom_point]

            def get_L_flange_points(prev_I_point, prev_O_point, next_I_point, next_O_point): #topとbottomでそれぞれ
                [prev_I_point, prev_O_point, next_I_point, next_O_point] = [const_3Dpoint(pt) for pt in [prev_I_point, prev_O_point, next_I_point, next_O_point]]
                
                edge_out_point = get_point_by_xyz_offset(
                    point1 = next_I_point,
                    point2 = prev_I_point,
                    offset_xyz = CG_info.center_L_info.bottom_flange.width,
                )
                inner_point = get_point_by_xyz_offset(
                    point1 = prev_I_point,
                    point2 = prev_O_point,
                    offset_xyz = CG_info.center_L_info.bottom_flange.thickness
                )
                gap_vector = rg.Vector3d(
                    prev_I_point.x - inner_point.x,
                    prev_I_point.y - inner_point.y,
                    prev_I_point.z - inner_point.z,
                )
                edge_in_point = Point3D(
                    edge_out_point.x - gap_vector.X,
                    edge_out_point.y - gap_vector.Y,
                    edge_out_point.z - gap_vector.Z,
                )
                return [prev_O_point, next_O_point, next_I_point, edge_out_point, edge_in_point, inner_point]
        
            def get_L_web_brep(prev_top_point, prev_bottom_mid_point, prev_bottom_vertical_point, next_top_point, next_bottom_mid_point, next_bottom_vertical_point, info):
                [prev_I_top_point, prev_I_bottom_point], [prev_O_top_point, prev_O_bottom_point] = get_L_trimmed_points(prev_top_point, prev_bottom_mid_point, prev_bottom_vertical_point, info)
                [next_I_top_point, next_I_bottom_point], [next_O_top_point, next_O_bottom_point] = get_L_trimmed_points(next_top_point, next_bottom_mid_point, next_bottom_vertical_point, info)
                top_L_flange_points = get_L_flange_points(prev_I_top_point, prev_O_top_point, next_I_top_point, next_O_top_point)
                bottom_L_flange_points = get_L_flange_points(prev_I_bottom_point, prev_O_bottom_point, next_I_bottom_point, next_O_bottom_point)
                crvs = []
                for j in range(len(top_L_flange_points)):
                    crvs.append(const_line_obj(top_L_flange_points[j], bottom_L_flange_points[j]))
                return const_brep_from_all_crvs(crvs)
            
            prev_top_point_O = prev_top_points[j]
            prev_top_point_I = prev_top_points[j+1]
            prev_bottom_point_O = prev_bottom_vertical_points[j]
            prev_bottom_point_I = prev_bottom_vertical_points[j+1]
            prev_bottom_point_mid = Point3D(
                (prev_bottom_point_O.x + prev_bottom_point_I.x) / 2,
                (prev_bottom_point_O.y + prev_bottom_point_I.y) / 2,
                (prev_bottom_point_O.z + prev_bottom_point_I.z) / 2,
            )
            next_top_point_O = next_top_points[j]
            next_top_point_I = next_top_points[j+1]
            next_bottom_point_O = next_bottom_vertical_points[j]
            next_bottom_point_I = next_bottom_vertical_points[j+1]
            next_bottom_point_mid = Point3D(
                (next_bottom_point_O.x + next_bottom_point_I.x) / 2,
                (next_bottom_point_O.y + next_bottom_point_I.y) / 2,
                (next_bottom_point_O.z + next_bottom_point_I.z) / 2,
            )

            O_Lweb_brep = get_L_web_brep(
                prev_top_point = prev_top_point_O,
                prev_bottom_mid_point = prev_bottom_point_mid,
                prev_bottom_vertical_point = prev_bottom_point_O,
                next_top_point = next_top_point_O,
                next_bottom_mid_point = next_bottom_point_mid,
                next_bottom_vertical_point = next_bottom_point_O,
                info = CG_info.center_L_info,
            )
            I_Lweb_brep = get_L_web_brep(
                prev_top_point = prev_top_point_I,
                prev_bottom_mid_point = prev_bottom_point_mid,
                prev_bottom_vertical_point = prev_bottom_point_I,
                next_top_point = next_top_point_I,
                next_bottom_mid_point = next_bottom_point_mid,
                next_bottom_vertical_point = next_bottom_point_I,
                info = CG_info.center_L_info,
            )
            CG_breps[f"O_Lweb_{i}_{j}"] = O_Lweb_brep
            CG_breps[f"I_Lweb_{i}_{j}"] = I_Lweb_brep

    # 左右の張出
    I_slab_bottom_polyline = slab_bottom_polyline_dict_for_bridge["I"]
    O_slab_bottom_polyline = slab_bottom_polyline_dict_for_bridge["O"]
    MG_point_info_I = MG_point_infos[-1] 
    MG_point_info_O = MG_point_infos[0]
    MG_polyline_dict_I = MG_polyline_dict_for_bridge[MG_point_info_I.MG_name]
    MG_polyline_dict_O = MG_polyline_dict_for_bridge[MG_point_info_O.MG_name]
    MG_point_I_side = get_MG_point_side_info(MG_point_info_I, "I")
    MG_point_O_side = get_MG_point_side_info(MG_point_info_O, "O")
    MG_polyline_I_side_dict = get_MG_polyline_side_dict(MG_polyline_dict_I, "I")
    MG_polyline_O_side_dict = get_MG_polyline_side_dict(MG_polyline_dict_O, "O")

    if CG_info.outer_existence:
        O_edge_top_brep, O_edge_bottom_brep, O_edge_web_brep = get_haridashi_H_breps(O_slab_bottom_polyline, MG_point_O_side, MG_polyline_O_side_dict, CG_info.outer_info, debug_crvs=debug_crvs)
        CG_breps["O_edge_top_flange"] = O_edge_top_brep
        CG_breps["O_edge_bottom_flange"] = O_edge_bottom_brep
        CG_breps["O_edge_web"] = O_edge_web_brep
    if CG_info.inner_existence:
        I_edge_top_brep, I_edge_bottom_brep, I_edge_web_brep = get_haridashi_H_breps(I_slab_bottom_polyline, MG_point_I_side, MG_polyline_I_side_dict, CG_info.inner_info, debug_crvs=debug_crvs)
        CG_breps["I_edge_top_flange"] = I_edge_top_brep
        CG_breps["I_edge_bottom_flange"] = I_edge_bottom_brep
        CG_breps["I_edge_web"] = I_edge_web_brep

    return CG_breps

def get_yokogeta_breps(
    CG_info: YokogetaInfo,
    MG_point_infos: list[MainGirderPointInfo_IO],
    MG_polyline_dict_for_bridge: dict[str, dict[str, rg.Polyline]],
    slab_bottom_polyline_dict_for_bridge: list[dict[str, rg.Polyline]],
    debug_crvs: Optional[list] = None,
) -> dict[str, rg.Brep]:
    CG_breps = {}
    for i in range(len(MG_point_infos) - 1):
        MG_point_info_I = MG_point_infos[i]
        MG_point_info_O = MG_point_infos[i+1]
        MG_polyline_dict_I = MG_polyline_dict_for_bridge[MG_point_info_I.MG_name]
        MG_polyline_dict_O = MG_polyline_dict_for_bridge[MG_point_info_O.MG_name]
        MG_point_I_side = get_MG_point_side_info(MG_point_info_I, "I")
        MG_point_O_side = get_MG_point_side_info(MG_point_info_O, "O")
        MG_polyline_I_side_dict = get_MG_polyline_side_dict(MG_polyline_dict_I, "I")
        MG_polyline_O_side_dict = get_MG_polyline_side_dict(MG_polyline_dict_O, "O")
        # H鋼
        top_brep, bottom_brep, web_brep = get_mid_H_breps(
            MG_point_side_O=MG_point_O_side,
            MG_polyline_side_dict_O=MG_polyline_O_side_dict,
            MG_point_side_I=MG_point_I_side,
            MG_polyline_side_dict_I=MG_polyline_I_side_dict,
            info=CG_info.center_info,
            offset_z_top= CG_info.center_top_offset_z,
            debug_crvs=debug_crvs,
        )
        CG_breps[f"H_top_flange_{i}"] = top_brep
        CG_breps[f"H_bottom_flange_{i}"] = bottom_brep
        CG_breps[f"H_web_{i}"] = web_brep
    
    # 左右の張出
    I_slab_bottom_polyline = slab_bottom_polyline_dict_for_bridge["I"]
    O_slab_bottom_polyline = slab_bottom_polyline_dict_for_bridge["O"]
    MG_point_info_I = MG_point_infos[-1] 
    MG_point_info_O = MG_point_infos[0]
    MG_polyline_dict_I = MG_polyline_dict_for_bridge[MG_point_info_I.MG_name]
    MG_polyline_dict_O = MG_polyline_dict_for_bridge[MG_point_info_O.MG_name]
    MG_point_I_side = get_MG_point_side_info(MG_point_info_I, "I")
    MG_point_O_side = get_MG_point_side_info(MG_point_info_O, "O")
    MG_polyline_I_side_dict = get_MG_polyline_side_dict(MG_polyline_dict_I, "I")
    MG_polyline_O_side_dict = get_MG_polyline_side_dict(MG_polyline_dict_O, "O")

    if CG_info.outer_existence:
        O_edge_top_brep, O_edge_bottom_brep, O_edge_web_brep = get_haridashi_H_breps(O_slab_bottom_polyline, MG_point_O_side, MG_polyline_O_side_dict, CG_info.outer_info, debug_crvs=debug_crvs)
        CG_breps["O_edge_top_flange"] = O_edge_top_brep
        CG_breps["O_edge_bottom_flange"] = O_edge_bottom_brep
        CG_breps["O_edge_web"] = O_edge_web_brep
    if CG_info.inner_existence:
        I_edge_top_brep, I_edge_bottom_brep, I_edge_web_brep = get_haridashi_H_breps(I_slab_bottom_polyline, MG_point_I_side, MG_polyline_I_side_dict, CG_info.inner_info, debug_crvs=debug_crvs)
        CG_breps["I_edge_top_flange"] = I_edge_top_brep
        CG_breps["I_edge_bottom_flange"] = I_edge_bottom_brep
        CG_breps["I_edge_web"] = I_edge_web_brep

    return CG_breps



def get_each_CG(
    CG_info: CrossGirderInfo,
    MG_point_info: list[MainGirderPointInfo_IO],
    MG_polyline_dict_for_bridge: dict[str, dict[str, rg.Polyline]],
    slab_bottom_polyline_dict_for_bridge: dict[str, rg.Polyline],
    debug_crvs: Optional[list] = None,
) -> list[rg.Brep]:
    bridge_name = CG_info.bridge_name
    CG_name = CG_info.CG_name
    if CG_info.CG_type == "横梁":
        print(bridge_name, CG_name, "横梁")
        CG_info = CG_info.yokobari_info
        brep_dict = get_yokobari_breps(CG_info, MG_point_info, MG_polyline_dict_for_bridge, slab_bottom_polyline_dict_for_bridge, debug_crvs=debug_crvs)
    elif CG_info.CG_type == "対傾構":
        print(bridge_name, CG_name, "対傾構")
        CG_info = CG_info.taikeikou_info
        brep_dict = get_taikeikou_breps(CG_info, MG_point_info, MG_polyline_dict_for_bridge, slab_bottom_polyline_dict_for_bridge, debug_crvs=debug_crvs)
    elif CG_info.CG_type == "横桁":
        print(bridge_name, CG_name, "横桁")
        CG_info = CG_info.yokogeta_info
        brep_dict = get_yokogeta_breps(CG_info, MG_point_info, MG_polyline_dict_for_bridge, slab_bottom_polyline_dict_for_bridge, debug_crvs=debug_crvs)
    else:
        raise ValueError(f"Invalid CG type: {CG_info.CG_type}")
    return brep_dict


def main(
    initial_or_final: str,
    debug: bool = False,
    target_bridge_name: Optional[str] = None,
    target_CG_name: Optional[str] = None,
):
    if initial_or_final == "initial":
        DIR = INITIAL_OUTPUT_DIR
    elif initial_or_final == "final":
        DIR = FINAL_OUTPUT_DIR

    CG_infos = load_from_pickle(
        file_path = DIR / f"{Filenames.INPUT}_{Filenames.CG}.pickle",
    )
    MG_point_dict_for_CG = load_from_pickle(
        file_path = DIR / f"{Filenames.WORLD}_{Filenames.MG}_{Filenames.POINTS}_for_{Filenames.CG}.pickle",
    )
    slab_bottom_points = load_from_pickle(
        file_path = DIR / f"{Filenames.WORLD}_{Filenames.SLAB}_{Filenames.BOTTOM}_{Filenames.POINTS}_for_{Filenames.CG}.pickle",
    )
    MG_point_IO_dict = load_from_pickle(
        file_path = DIR / f"{Filenames.WORLD}_{Filenames.MG}_{Filenames.POINTS}_IO.pickle",
    )

    world_items_dict_for_bake = {}
    world_items_dict_for_bake_2 = {}
    crvs = []

    for bridge_name, bridge_CG_infos in CG_infos.items():
        if target_bridge_name is not None and bridge_name != target_bridge_name:
            continue
        target_CG_infos = [
            CG_info for CG_info in bridge_CG_infos
            if target_CG_name is None or CG_info.CG_name == target_CG_name
        ]
        if not target_CG_infos:
            continue

        MG_point_dict_for_CG_for_bridge = MG_point_dict_for_CG[bridge_name]
        slab_bottom_points_for_bridge = slab_bottom_points[bridge_name]
        MG_point_dict_for_bridge = MG_point_IO_dict[bridge_name]
        MG_polyline_dict_for_bridge = {}
        for MG_name, MG_point_infos in MG_point_dict_for_bridge.items():
            MG_polyline_dict_for_MG = get_MG_polylines(MG_point_infos)
            MG_polyline_dict_for_bridge[MG_name] = MG_polyline_dict_for_MG
        slab_bottom_polyline_for_bridge_dict_list, CG_name_for_bridge_list = get_slab_bottom_polylines(slab_bottom_points_for_bridge)
        if bridge_name not in world_items_dict_for_bake:
            world_items_dict_for_bake[bridge_name] = {}
        for CG_info in target_CG_infos:
            CG_name = CG_info.CG_name
            MG_point_infos = MG_point_dict_for_CG_for_bridge[CG_name]
            if debug:
                for MG_name in dict.fromkeys(info.MG_name for info in MG_point_infos):
                    MG_polyline_dict = MG_polyline_dict_for_bridge[MG_name]
                    crvs.append(get_MG_point_or_polyline(point_name="bottom_out_O_point", MG_polyline_dict=MG_polyline_dict))
                    crvs.append(get_MG_point_or_polyline(point_name="bottom_out_I_point", MG_polyline_dict=MG_polyline_dict))
            slab_bottom_idx = next(
                (i for i, names in enumerate(CG_name_for_bridge_list) if CG_name in names),
                None
            )
            slab_bottom_polyline_dict_for_bridge = slab_bottom_polyline_for_bridge_dict_list[slab_bottom_idx]
            CG_brep_dict = get_each_CG(
                CG_info,
                MG_point_infos,
                MG_polyline_dict_for_bridge,
                slab_bottom_polyline_dict_for_bridge,
                debug_crvs=crvs if debug else None,
            )
            world_items_dict_for_bake[bridge_name][CG_name] = CG_brep_dict
    if not debug:
        return get_keys_and_values_for_bake(world_items_dict_for_bake)

    else:
        return crvs


if __name__ == "__main__":
    # crvs = main("initial", debug=True)
    (bake_keys, bake_objs)= main("initial")
    # breps = main("initial", debug=False)

