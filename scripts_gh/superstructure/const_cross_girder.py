
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
    YokobariInfo,
)
from my_project.config.util_schemas import (
    Point3D,
)
from my_project.utils.bake import get_keys_and_values_for_bake
from my_project.utils.geometry.points import get_point_by_xy_offset
from my_project.utils.geometry_gh.const import (
    const_line_obj,
    const_point_along_curve,
    const_polycurve_obj,
    const_srf_from_crvs,
)
from my_project.utils.geometry_gh.intersect import (
    get_intersect_point_on_crvs,
    trim_curve_between_two_points,
)
from my_project.utils.geometry_gh.transform import move_obj
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
    slab_bottom_points_for_CG: list[SlabBottomPoints_IO],
):
    return get_polyline_from_points(slab_bottom_points_for_CG)

def get_MG_point_or_polyline(
    point_name: str,
    MG_point_info: Optional[MainGirderPointInfo_IO] = None,
    MG_polyline_dict: Optional[dict[str, rg.Polyline]] = None,
) -> Point3D:
    shared_point_name = [
        "top_out_I_point",
        "top_out_O_point",
        "top_in_O_point",
        "bottom_in_O_point",
        "bottom_out_O_point",
        "bottom_out_I_point",
        "bottom_in_I_point",
        "top_in_I_point",
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
    target_crv: rg.Polyline,
    shared_offset: Optional[float] = None,
    prev_offset: Optional[float] = None,
    next_offset: Optional[float] = None,
) -> list[rg.Polyline]:
    prev_point_O = const_point_along_curve(
        curve=base_point_O_crv,
        base_point=base_point_O,
        offset= -shared_offset if shared_offset is not None else -prev_offset,
    )
    prev_point_I = const_point_along_curve(
        curve=base_point_I_crv,
        base_point=base_point_I,
        offset= -shared_offset if shared_offset is not None else -prev_offset,
    )
    next_point_O = const_point_along_curve(
        curve=base_point_O_crv,
        base_point=base_point_O,
        offset= shared_offset if shared_offset is not None else next_offset,
    )
    next_point_I = const_point_along_curve(
        curve=base_point_I_crv,
        base_point=base_point_I,
        offset= shared_offset if shared_offset is not None else next_offset,
    )
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
    return split_crv
   

def get_box_brep(thickness, TB, base_I_crv, base_O_crv):
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
    above_srf = const_srf_from_crvs([above_I_crv, above_O_crv])
    below_srf = const_srf_from_crvs([below_I_crv, below_O_crv])
    I_srf = const_srf_from_crvs([above_I_crv, below_I_crv])
    O_srf = const_srf_from_crvs([above_O_crv, below_O_crv])
    flange_brep = rg.Brep.JoinBreps([above_srf, below_srf, I_srf, O_srf], 0.01)[0]
    return flange_brep.CapPlanarHoles(0.01)

def get_yokobari_breps(
    CG_info: YokobariInfo,
    MG_point_infos: list[MainGirderPointInfo_IO],
    MG_polyline_dict_for_bridge: dict[str, dict[str, rg.Polyline]],
    slab_bottom_polyline_dict_for_bridge: list[dict[str, rg.Polyline]],
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
        # まずフランジ
        top_base_point_O = MG_point_O_side.top_out
        top_base_point_I = MG_point_I_side.top_out
        bottom_base_point_O = MG_point_O_side.bottom_out
        bottom_base_point_I = MG_point_I_side.bottom_out
        top_base_crv_O = MG_polyline_O_side_dict["top_out"]
        top_base_crv_I = MG_polyline_I_side_dict["top_out"]
        bottom_base_crv_O = MG_polyline_O_side_dict["bottom_out"]
        bottom_base_crv_I = MG_polyline_I_side_dict["bottom_out"]
        def get_top_flange_crv(target_crv):
            return get_split_crvs_with_base_points_offset(
                base_point_O = top_base_point_O,
                base_point_I = top_base_point_I,
                base_point_O_crv = top_base_crv_O,
                base_point_I_crv = top_base_crv_I,
                target_crv = target_crv,
                prev_offset= CG_info.center_info.top_flange.width_minus,
                next_offset= CG_info.center_info.top_flange.width_plus,
            )
        top_flange_top_O_crv = get_top_flange_crv(top_base_crv_O)
        top_flange_top_I_crv = get_top_flange_crv(top_base_crv_I)
        top_flange_thickness = float(CG_info.center_info.top_flange.thickness)
        top_flange_brep = get_box_brep(
            thickness = top_flange_thickness,
            TB = "top",
            base_I_crv= top_flange_top_I_crv,
            base_O_crv= top_flange_top_O_crv,
        )
        def get_full_web_crv(target_crv):
            return get_split_crvs_with_base_points_offset(
                base_point_O = bottom_base_point_O,
                base_point_I = bottom_base_point_I,
                base_point_O_crv = bottom_base_crv_O,
                base_point_I_crv = bottom_base_crv_I,
                target_crv = target_crv,
                prev_offset= CG_info.center_info.bottom_flange.width_minus,
                next_offset= CG_info.center_info.bottom_flange.width_plus,
            )
        bottom_flange_bottom_O_crv = get_full_web_crv(bottom_base_crv_O)
        bottom_flange_bottom_I_crv = get_full_web_crv(bottom_base_crv_I)
        bottom_flange_thickness = float(CG_info.center_info.bottom_flange.thickness)
        bottom_flange_brep = get_box_brep(
            thickness = bottom_flange_thickness,
            TB = "bottom",
            base_I_crv= bottom_flange_bottom_I_crv,
            base_O_crv= bottom_flange_bottom_O_crv,
        )
        CG_breps[f"top_flange_{i}"] = top_flange_brep
        CG_breps[f"bottom_flange_{i}"] = bottom_flange_brep

        # 中間ウェブ
        mid_top_out_crv_O = move_obj(top_base_crv_O, rg.Vector3d(0, 0, -top_flange_thickness))
        mid_bottom_out_crv_O = move_obj(bottom_base_crv_O, rg.Vector3d(0, 0, bottom_flange_thickness))
        mid_top_out_crv_I = move_obj(top_base_crv_I, rg.Vector3d(0, 0, -top_flange_thickness))
        mid_bottom_out_crv_I = move_obj(bottom_base_crv_I, rg.Vector3d(0, 0, bottom_flange_thickness))
        web_offset = CG_info.web_offset
        def get_full_web_crvs(target_crv):
            prev_crv =  get_split_crvs_with_base_points_offset(
                base_point_O = bottom_base_point_O,
                base_point_I = bottom_base_point_I,
                base_point_O_crv = bottom_base_crv_O,
                base_point_I_crv = bottom_base_crv_I,
                target_crv = target_crv,
                prev_offset= web_offset + CG_info.center_info.web.thickness / 2,
                next_offset= -(web_offset - CG_info.center_info.web.thickness / 2), # prev側に行くのでマイナス
            )
            next_crv =  get_split_crvs_with_base_points_offset(
                base_point_O = bottom_base_point_O,
                base_point_I = bottom_base_point_I,
                base_point_O_crv = bottom_base_crv_O,
                base_point_I_crv = bottom_base_crv_I,
                target_crv = target_crv,
                prev_offset= -(web_offset - CG_info.center_info.web.thickness / 2), # next側に行くのでマイナス
                next_offset= web_offset + CG_info.center_info.web.thickness / 2,
            )
            return prev_crv, next_crv
        target_crv_names = ["top_out", "web_top", "web_bottom", "bottom_out"]
        I_target_crvs = [MG_polyline_I_side_dict[name] for name in target_crv_names]
        O_target_crvs = [MG_polyline_O_side_dict[name] for name in target_crv_names[::-1]] # O側は逆順で処理する
        target_crvs = [
            *I_target_crvs,
            mid_bottom_out_crv_I,
            mid_bottom_out_crv_O,
            *O_target_crvs,
            mid_top_out_crv_O,
            mid_top_out_crv_I,
        ]
        prev_crvs = []
        next_crvs = []
        for target_crv in target_crvs:
            prev_crv, next_crv = get_full_web_crvs(target_crv)
            prev_crvs.append(prev_crv)
            next_crvs.append(next_crv)
        def get_full_web_brep(crvs):
            crvs = crvs + [crvs[0]]
            breps = []
            for i in range(len(crvs)-1):
                crv1 = crvs[i]
                crv2 = crvs[i+1]
                srf = const_srf_from_crvs([crv1, crv2])
                breps.append(srf)
            brep = rg.Brep.JoinBreps(breps, 0.01)[0]
            brep = brep.CapPlanarHoles(0.01)
            return brep
        CG_breps[f"web_prev_{i}"] = get_full_web_brep(prev_crvs)
        CG_breps[f"web_next_{i}"] = get_full_web_brep(next_crvs)
    
    # debug
    CG_breps = list(CG_breps.values())
    return CG_breps

        


def get_each_CG(
    CG_info: CrossGirderInfo,
    MG_point_info: list[MainGirderPointInfo_IO],
    MG_polyline_dict_for_bridge: dict[str, dict[str, rg.Polyline]],
    slab_bottom_polyline_dict_for_bridge: list[dict[str, rg.Polyline]],
) -> list[rg.Brep]:
    CG_breps = []
    if CG_info.CG_type == "横梁":
        print(CG_info.bridge_name, CG_info.CG_name)
        CG_info = CG_info.yokobari_info
        CG_breps = get_yokobari_breps(CG_info, MG_point_info, MG_polyline_dict_for_bridge, slab_bottom_polyline_dict_for_bridge)
        print(f"CG_breps: {len(CG_breps)}")
    # elif CG_info.CG_type == "対傾構":
    #     CG_info = CG_info.taikeikou_info
    #     CG_breps = get_taikeikou_breps(CG_info, MG_point_info, prev_MG_point_info, next_MG_point_info)
    # elif CG_info.CG_type == "横桁":
    #     CG_info = CG_info.yokogeta_info
    #     CG_breps = get_yokogeta_breps(CG_info, MG_point_info, prev_MG_point_info, next_MG_point_info)
    # else:
    #     raise ValueError(f"Invalid CG type: {CG_info.CG_type}")
    return CG_breps



def main(initial_or_final: str, debug: bool = False):
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
        DIR / f"{Filenames.WORLD}_{Filenames.MG}_{Filenames.POINTS}_IO.pickle",
    )


    world_items_dict_for_bake = {}
    world_items_dict_for_bake_2 = {}

    for bridge_name, CG_infos in CG_infos.items():
        MG_point_dict_for_CG_for_bridge = MG_point_dict_for_CG[bridge_name]
        slab_bottom_points_for_bridge = slab_bottom_points[bridge_name]
        MG_point_dict_for_bridge = MG_point_IO_dict[bridge_name]
        MG_polyline_dict_for_bridge = {}
        for MG_name, MG_point_infos in MG_point_dict_for_bridge.items():
            MG_polyline_dict_for_MG = get_MG_polylines(MG_point_infos)
            MG_polyline_dict_for_bridge[MG_name] = MG_polyline_dict_for_MG
        slab_bottom_polyline_dict_for_bridge = []
        for slab_bottom_point_infos in slab_bottom_points_for_bridge:
            slab_bottom_polyline_dict = get_slab_bottom_polylines(slab_bottom_point_infos)
            slab_bottom_polyline_dict_for_bridge.append(slab_bottom_polyline_dict)
            
        if bridge_name not in world_items_dict_for_bake:
            world_items_dict_for_bake[bridge_name] = {}
        for CG_info in CG_infos:
            CG_name = CG_info.CG_name
            MG_point_infos = MG_point_dict_for_CG_for_bridge[CG_name]
            CG_breps = get_each_CG(CG_info, MG_point_infos, MG_polyline_dict_for_bridge, slab_bottom_polyline_dict_for_bridge)
            for i, CG_brep in enumerate(CG_breps):
                world_items_dict_for_bake[bridge_name][f"{CG_name}_{i}"] = CG_brep
    if not debug:
        return get_keys_and_values_for_bake(world_items_dict_for_bake)

    else:
        breps = []
        for bridge_name, items_dict in world_items_dict_for_bake.items():
            breps.extend(items_dict.values())
        return breps


if __name__ == "__main__":
    # points = main("initial", debug=True)
    # (bake_keys, bake_objs)= main("initial")
    breps = main("initial", debug=True)

