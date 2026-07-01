

from my_project.config.file_names import Filenames
from my_project.config.paths import get_output_dir
from my_project.config.schemas.barrier_schemas import (
    BarrierCommonInfo,
    BarrierInfo,
    CenterBarrierInfo,
    CenterBarrierNoseInfo,
    LR_point,
)
from my_project.config.util_schemas import (
    Point3D,
)
from my_project.utils.dataframe import flatten_any
from my_project.utils.geometry.points import (
    get_both_points_by_xy_offset,
    get_point_LR_x_z,
)
from my_project.utils.geometry.vectors import get_frame_2D
from my_project.utils.geometry_gh.attributes import get_distance_along_crv
from my_project.utils.geometry_gh.const import (
    const_closed_polycurve_obj,
    const_polycurve_obj,
    const_srf_from_2crvs,
)
from my_project.utils.geometry_gh.intersect import (
    get_intersect_point_on_curve_with_xy,
    get_intersect_point_on_srf_with_point,
)
from my_project.utils.io import load_from_pickle, save_json_and_pickle


def get_barrier_points(
    common_info: BarrierCommonInfo,
    slab_edge_points: LR_point,
) -> tuple[dict[str, list[Point3D]], Point3D, Point3D]:
    base_point_in_L, base_point_in_R = slab_edge_points.Lpoint, slab_edge_points.Rpoint
    base_bottom_L, base_bottom_R = get_both_points_by_xy_offset(
        L_point=base_point_in_L,
        R_point=base_point_in_R,
        offset_xy=common_info.x - common_info.edge_watertreatment_x
    )
    haunch_bottom_L, haunch_bottom_R = get_point_LR_x_z(
        L_point=base_bottom_L,
        R_point=base_bottom_R,
        offset_xy = 0,
        offset_z = common_info.base_height + common_info.pavement_height
    )
    face_bottom_L, face_bottom_R = get_point_LR_x_z(
        L_point=haunch_bottom_L,
        R_point=haunch_bottom_R,
        offset_xy = - common_info.haunch_x,
        offset_z = common_info.haunch_height
    )
    top_in_L, top_in_R = get_point_LR_x_z(
        L_point=face_bottom_L,
        R_point=face_bottom_R,
        offset_xy = - common_info.face_x,
        offset_z = common_info.face_height
    )
    top_x = common_info.x - (common_info.face_x + common_info.haunch_x)
    top_z = top_x * common_info.slope.value / 100
    top_out_L, top_out_R = get_point_LR_x_z(
        L_point=top_in_L,
        R_point=top_in_R,
        offset_xy = - top_x,
        offset_z = top_z,
    )
    bottom_in_L = Point3D(base_point_in_L.x, base_point_in_L.y, base_bottom_L.z - common_info.edge_watertreatment_height - common_info.edge_in_height)
    bottom_in_R = Point3D(base_point_in_R.x, base_point_in_R.y, base_bottom_R.z - common_info.edge_watertreatment_height - common_info.edge_in_height)
    bottom_out_L = Point3D(top_out_L.x, top_out_L.y, bottom_in_L.z)
    bottom_out_R = Point3D(top_out_R.x, top_out_R.y, bottom_in_R.z)

    return {
        "L": [
            top_out_L,
            top_in_L,
            face_bottom_L,
            haunch_bottom_L,
            base_bottom_L,
            base_point_in_L,
            bottom_in_L,
            bottom_out_L,
        ],
        "R": [
            top_out_R,
            top_in_R,
            face_bottom_R,
            haunch_bottom_R,
            base_bottom_R,
            base_point_in_R,
            bottom_in_R,
            bottom_out_R,
        ]
    }, base_bottom_L, base_bottom_R


def get_barrier_base_point_record(CG_name: str, U: Point3D, D: Point3D) -> dict:
    return {
        "CG_name": CG_name,
        "U": U,
        "D": D,
    }


def get_center_barrier_base_point_record(
    CG_name: str,
    Uin: Point3D,
    Din: Point3D,
    Uout: Point3D = None,
    Dout: Point3D = None,
) -> dict:
    return {
        "CG_name": CG_name,
        "Uin": Uin,
        "Uout": Uout,
        "Din": Din,
        "Dout": Dout,
    }


def get_each_barrier(
    barrier_info: BarrierInfo,
):
    common_info = barrier_info.common_info
    slab_edge_points = barrier_info.slab_edge_points
    barrier_base_points = []
    barrier_dict = {}
    for i in range(len(slab_edge_points)):
        slab_edge_points_i = slab_edge_points[i]
        name_i = slab_edge_points_i.name
        barrier_points_dict_i, base_bottom_L, base_bottom_R = get_barrier_points(
            common_info = common_info,
            slab_edge_points = slab_edge_points_i,
        )
        barrier_base_points.append(
            get_barrier_base_point_record(
                CG_name=name_i,
                U=base_bottom_L,
                D=base_bottom_R,
            )
        )
        if i < len(slab_edge_points) - 1:
            slab_edge_points_i1 = slab_edge_points[i+1]
            name_i1 = slab_edge_points_i1.name
            barrier_points_dict_i1, _, _ = get_barrier_points(
                common_info = common_info,
                slab_edge_points = slab_edge_points_i1,
            )
            L_curve_i = const_closed_polycurve_obj(barrier_points_dict_i["L"])
            R_curve_i = const_closed_polycurve_obj(barrier_points_dict_i["R"])
            L_curve_i1 = const_closed_polycurve_obj(barrier_points_dict_i1["L"])
            R_curve_i1 = const_closed_polycurve_obj(barrier_points_dict_i1["R"])
            L_brep = const_srf_from_2crvs([L_curve_i, L_curve_i1]).CapPlanarHoles(0.01)
            R_brep = const_srf_from_2crvs([R_curve_i, R_curve_i1]).CapPlanarHoles(0.01)
            barrier_dict[f"{name_i}_to_{name_i1}"] = {
                "L": L_brep,
                "R": R_brep,
            }
    return barrier_dict, barrier_base_points

#ノーズ先端の円形部分は作らない
def get_center_barrier_and_nose_LR2points(
    center_barrier_info: CenterBarrierInfo,
    slab_edge_points: list[LR_point],
):
    # まずノーズ開始点、ノーズ終了点のRL座標を求める
    LR2_points = center_barrier_info.LR2_points
    C_points = []
    for point in LR2_points:
        C_point = Point3D(
            x = (point.Lpoint.x + point.Rpoint.x) / 2,
            y = (point.Lpoint.y + point.Rpoint.y) / 2,
            z = (point.Lpoint.z + point.Rpoint.z) / 2,
        )
        C_points.append(C_point)
    C_polyline = const_polycurve_obj(C_points)
    C_distances = get_distance_along_crv(C_polyline, C_points)
    nose_start_CG_name = center_barrier_info.nose_common_info.start_cross_girder_key
    nose_start_CG_offset = center_barrier_info.nose_common_info.start_offset
    nose_start_distance = next(d for n, d in zip(LR2_points, C_distances) if n.name == nose_start_CG_name) + nose_start_CG_offset
    if nose_start_CG_offset == 0:
        nose_start_point, nose_start_point_idx = next((p, i) for i, p in enumerate(LR2_points) if p.name == nose_start_CG_name)
        barrier_LR2_points = LR2_points[:nose_start_point_idx+1]
        nose_LR2_points = LR2_points[nose_start_point_idx:]
    else:
        for i, d in enumerate(C_distances):
            if d > nose_start_distance:
                post_point = LR2_points[i]
                post_distance = d
                if i == 0:
                    raise ValueError("先頭点が条件を満たしているため pre_point が定義できない")
                pre_point = LR2_points[i - 1]
                pre_distance = C_distances[i - 1]
                break
        else:
            raise ValueError("nose_start_distance を超える点が存在しない")
        ratio = (nose_start_distance - pre_distance) / (post_distance - pre_distance)
        nose_start_point = LR_point(
            name = "nose_start_point",
            Lpoint = Point3D(
                x = pre_point.Lpoint.x + ratio * (post_point.Lpoint.x - pre_point.Lpoint.x),
                y = pre_point.Lpoint.y + ratio * (post_point.Lpoint.y - pre_point.Lpoint.y),
                z = pre_point.Lpoint.z + ratio * (post_point.Lpoint.z - pre_point.Lpoint.z),
            ),
            Rpoint = Point3D(
                x = pre_point.Rpoint.x + ratio * (post_point.Rpoint.x - pre_point.Rpoint.x),
                y = pre_point.Rpoint.y + ratio * (post_point.Rpoint.y - pre_point.Rpoint.y),
                z = pre_point.Rpoint.z + ratio * (post_point.Rpoint.z - pre_point.Rpoint.z),
            )
        )
        barrier_LR2_points = LR2_points[:i] + [nose_start_point]
        nose_LR2_points = [nose_start_point] + LR2_points[i:]

    # ノーズの直線部分の終わりの点を求める
    nose_straight_end_distance = nose_start_distance + center_barrier_info.nose_common_info.length
    if nose_straight_end_distance <= C_distances[-1]:
        for i, d in enumerate(C_distances):
            if d > nose_straight_end_distance:
                nose_straight_post_point = LR2_points[i]
                nose_straight_post_distance = d
                if i == 0:
                    raise ValueError("先頭点が条件を満たしているため nose_straight_pre_point が定義できない")
                nose_straight_pre_point = LR2_points[i - 1]
                nose_straight_pre_distance = C_distances[i - 1]
                break
        ratio = (nose_straight_end_distance - nose_straight_pre_distance) / (nose_straight_post_distance - nose_straight_pre_distance)
        nose_straight_end_point = LR_point(
            name = "nose_straight_end_point",
            Lpoint = Point3D(
                x = nose_straight_pre_point.Lpoint.x + ratio * (nose_straight_post_point.Lpoint.x - nose_straight_pre_point.Lpoint.x),
                y = nose_straight_pre_point.Lpoint.y + ratio * (nose_straight_post_point.Lpoint.y - nose_straight_pre_point.Lpoint.y),
                z = nose_straight_pre_point.Lpoint.z + ratio * (nose_straight_post_point.Lpoint.z - nose_straight_pre_point.Lpoint.z),
            ),
            Rpoint = Point3D(
                x = nose_straight_pre_point.Rpoint.x + ratio * (nose_straight_post_point.Rpoint.x - nose_straight_pre_point.Rpoint.x),
                y = nose_straight_pre_point.Rpoint.y + ratio * (nose_straight_post_point.Rpoint.y - nose_straight_pre_point.Rpoint.y),
                z = nose_straight_pre_point.Rpoint.z + ratio * (nose_straight_post_point.Rpoint.z - nose_straight_pre_point.Rpoint.z),
            )
        )
        nose_straight_LR2_points = nose_LR2_points[:i] + [nose_straight_end_point]
    else:
        last_1_point = LR2_points[-1]
        last_2_point = LR2_points[-2]
        ratio = (nose_straight_end_distance - C_distances[-2]) / (C_distances[-1] - C_distances[-2])
        nose_straight_end_point = LR_point(
            name = "nose_straight_end_point",
            Lpoint = Point3D(
                x = last_2_point.Lpoint.x + ratio * (last_1_point.Lpoint.x - last_2_point.Lpoint.x),
                y = last_2_point.Lpoint.y + ratio * (last_1_point.Lpoint.y - last_2_point.Lpoint.y),
                z = last_2_point.Lpoint.z + ratio * (last_1_point.Lpoint.z - last_2_point.Lpoint.z),
            ),
            Rpoint = Point3D(
                x = last_2_point.Rpoint.x + ratio * (last_1_point.Rpoint.x - last_2_point.Rpoint.x),
                y = last_2_point.Rpoint.y + ratio * (last_1_point.Rpoint.y - last_2_point.Rpoint.y),
                z = last_2_point.Rpoint.z + ratio * (last_1_point.Rpoint.z - last_2_point.Rpoint.z),
            )
        )
        nose_straight_LR2_points = nose_LR2_points + [nose_straight_end_point]

    #本当のLR2を調べる。
    def get_LR2_points_on_slab(point: LR_point) -> LR_point:
        name = point.name
        if name == "nose_start_point" or name == "nose_straight_end_point":
            if name == "nose_start_point":
                pre_name = barrier_LR2_points[-2].name
            else:
                pre_name = nose_straight_LR2_points[-2].name
            pre_edge_point, pre_edge_point_idx = next((p, i) for i, p in enumerate(slab_edge_points) if p.name == pre_name)
            post_edge_point = slab_edge_points[pre_edge_point_idx + 1]
            slab_top_srf = const_srf_from_2crvs([
                const_polycurve_obj([pre_edge_point.Lpoint, pre_edge_point.Rpoint]),
                const_polycurve_obj([post_edge_point.Lpoint, post_edge_point.Rpoint]),
            ])
            L_point = get_intersect_point_on_srf_with_point(
                srf = slab_top_srf,
                point = point.Lpoint,
            )
            R_point = get_intersect_point_on_srf_with_point(
                srf = slab_top_srf,
                point = point.Rpoint,
            )
        else:
            slab_LR_point = next(p for p in slab_edge_points if p.name == name)
            slab_LR_line = const_polycurve_obj([slab_LR_point.Lpoint, slab_LR_point.Rpoint])
            slab_LR_frame2D = get_frame_2D(point_u=point.Lpoint, point_d=point.Rpoint,y_direction="UP")
            L_point = get_intersect_point_on_curve_with_xy(
                curve = slab_LR_line,
                point = point.Lpoint,
                axis_vector=slab_LR_frame2D.y_axis
            )
            R_point = get_intersect_point_on_curve_with_xy(
                curve = slab_LR_line,
                point = point.Rpoint,
                axis_vector=slab_LR_frame2D.y_axis
            )
        return LR_point(
            name = name,
            Lpoint = L_point,
            Rpoint = R_point,
        )
    barrier_LR2_points_on_slab = [get_LR2_points_on_slab(p) for p in barrier_LR2_points]
    nose_straight_LR2_points_on_slab = [get_LR2_points_on_slab(p) for p in nose_straight_LR2_points]
    return barrier_LR2_points_on_slab, nose_straight_LR2_points_on_slab

def get_center_barrier_points(
    barrier_common_info: BarrierCommonInfo,
    LR2_point: LR_point,
) -> tuple[dict[str, list[Point3D]], Point3D, Point3D, Point3D, Point3D]:
    base_bottom_L, base_bottom_R = LR2_point.Lpoint, LR2_point.Rpoint
    bottom_out_L, bottom_out_R = get_both_points_by_xy_offset(
        L_point=base_bottom_L,
        R_point=base_bottom_R,
        offset_xy=barrier_common_info.x
    )
    haunch_bottom_L, haunch_bottom_R = get_point_LR_x_z(
        L_point=base_bottom_L,
        R_point=base_bottom_R,
        offset_xy = 0,
        offset_z = barrier_common_info.base_height + barrier_common_info.pavement_height
    )
    face_bottom_L, face_bottom_R = get_point_LR_x_z(
        L_point=haunch_bottom_L,
        R_point=haunch_bottom_R,
        offset_xy =  barrier_common_info.haunch_x, # 近づいていく
        offset_z = barrier_common_info.haunch_height
    )
    top_in_L, top_in_R = get_point_LR_x_z(
        L_point=face_bottom_L,
        R_point=face_bottom_R,
        offset_xy = barrier_common_info.face_x, # 近づいていく
        offset_z = barrier_common_info.face_height
    )
    top_x = barrier_common_info.x - (barrier_common_info.face_x + barrier_common_info.haunch_x)
    top_z = top_x * barrier_common_info.slope.value / 100
    top_out_L, top_out_R = get_point_LR_x_z(
        L_point=top_in_L,
        R_point=top_in_R,
        offset_xy = top_x, # 近づいていく
        offset_z = top_z, # 高くなる
    )
    return {
        "L": [
            top_out_L,
            top_in_L,
            face_bottom_L,
            haunch_bottom_L,
            base_bottom_L,
            bottom_out_L,
        ],
        "R": [
            top_out_R,
            top_in_R,
            face_bottom_R,
            haunch_bottom_R,
            base_bottom_R,
            bottom_out_R,
        ]
    }, base_bottom_L, base_bottom_R, bottom_out_L, bottom_out_R


def get_nose_points(
    nose_common_info: CenterBarrierNoseInfo,
    LR2_point: LR_point,
) -> list[Point3D]:
    top_point_L, top_point_R = get_point_LR_x_z(
        L_point=LR2_point.Lpoint,
        R_point=LR2_point.Rpoint,
        offset_xy = nose_common_info.edge_cut_width,
        offset_z = nose_common_info.height,
    )
    return [LR2_point.Lpoint, top_point_L, top_point_R, LR2_point.Rpoint], LR2_point.Lpoint, LR2_point.Rpoint

def get_center_barriers_and_noses(
    center_barrier_info: CenterBarrierInfo,
    slab_edge_points: list[LR_point],
):
    barrier_common_info = center_barrier_info.barrier_common_info
    nose_common_info = center_barrier_info.nose_common_info
    barrier_LR2_points_on_slab, nose_straight_LR2_points_on_slab = get_center_barrier_and_nose_LR2points(
        center_barrier_info = center_barrier_info,
        slab_edge_points = slab_edge_points,
    )
    center_barrier_base_points = []
    center_barrier_base_point_names = set()
    center_barrier_dict = {}
    center_barrier_dict["中央壁高欄"] = {}
    center_barrier_dict["ノーズ"] = {}
    for i in range(len(barrier_LR2_points_on_slab)):
        barrier_LR2_points_i = barrier_LR2_points_on_slab[i]
        name_i = barrier_LR2_points_i.name
        barrier_points_dict_i, base_bottom_Li, base_bottom_Ri, bottom_out_Li, bottom_out_Ri = get_center_barrier_points(
            barrier_common_info = barrier_common_info,
            LR2_point = barrier_LR2_points_i,
        )
        center_barrier_base_points.append(
            get_center_barrier_base_point_record(
                CG_name=name_i,
                Uin=base_bottom_Li,
                Uout=bottom_out_Li,
                Din=base_bottom_Ri,
                Dout=bottom_out_Ri,
            )
        )
        center_barrier_base_point_names.add(name_i)
        if i < len(barrier_LR2_points_on_slab) - 1:
            barrier_LR2_points_i1 = barrier_LR2_points_on_slab[i+1]
            name_i1 = barrier_LR2_points_i1.name
            barrier_points_dict_i1, _, _, _, _ = get_center_barrier_points(
                barrier_common_info = barrier_common_info,
                LR2_point = barrier_LR2_points_i1,
            )
            L_curve_i = const_closed_polycurve_obj(barrier_points_dict_i["L"])
            R_curve_i = const_closed_polycurve_obj(barrier_points_dict_i["R"])
            L_curve_i1 = const_closed_polycurve_obj(barrier_points_dict_i1["L"])
            R_curve_i1 = const_closed_polycurve_obj(barrier_points_dict_i1["R"])
            L_brep = const_srf_from_2crvs([L_curve_i, L_curve_i1]).CapPlanarHoles(0.01)
            R_brep = const_srf_from_2crvs([R_curve_i, R_curve_i1]).CapPlanarHoles(0.01)
            center_barrier_dict["中央壁高欄"][f"{name_i}_to_{name_i1}"] = {
                "L": L_brep,
                "R": R_brep,
            }
    for i in range(len(nose_straight_LR2_points_on_slab)):
        nose_straight_LR2_points_on_slab_i = nose_straight_LR2_points_on_slab[i]
        name_i = nose_straight_LR2_points_on_slab_i.name
        nose_points_i, base_Li, base_Ri = get_nose_points(
            nose_common_info = nose_common_info,
            LR2_point = nose_straight_LR2_points_on_slab_i,
        )
        if i > 0:
            if name_i in center_barrier_base_point_names:
                raise ValueError("同じ名前のLR2ポイント")
            center_barrier_base_points.append(
                get_center_barrier_base_point_record(
                    CG_name=name_i,
                    Uin=base_Li,
                    Din=base_Ri,
                )
            )
            center_barrier_base_point_names.add(name_i)
        if i < len(nose_straight_LR2_points_on_slab) - 1:
            nose_straight_LR2_points_on_slab_i1 = nose_straight_LR2_points_on_slab[i+1]
            name_i1 = nose_straight_LR2_points_on_slab_i1.name
            nose_points_i1, _, _ = get_nose_points(
                nose_common_info = nose_common_info,
                LR2_point = nose_straight_LR2_points_on_slab_i1,
            )
            curve_i = const_closed_polycurve_obj(nose_points_i)
            curve_i1 = const_closed_polycurve_obj(nose_points_i1)
            brep = const_srf_from_2crvs([curve_i, curve_i1]).CapPlanarHoles(0.01)
            center_barrier_dict["ノーズ"][f"{name_i}_to_{name_i1}"] = brep
    return center_barrier_dict, center_barrier_base_points

def main(initial_or_final: str):
    DIR = get_output_dir(initial_or_final)

    barrier_infos = load_from_pickle(
        file_path = DIR / f"{Filenames.INPUT}_{Filenames.SLAB}_{Filenames.BARRIER}.pickle",
    )
    center_barrier_infos = load_from_pickle(
        file_path = DIR / f"{Filenames.INPUT}_{Filenames.SLAB}_{Filenames.BARRIER}_{Filenames.CENTER}.pickle",
    )

    barrier_base_bottom_dict = {}
    center_barrier_base_bottom_dict = {}
    world_items_dict_for_bake = {}
    world_items_dict_for_bake_2 = {}

    for barrier_info in barrier_infos:
        unique_slab_name = f"{barrier_info.bridge_name}_{barrier_info.num}"
        barrier_dict, barrier_base_points_dict = get_each_barrier(
            barrier_info = barrier_info,
        )
        barrier_base_bottom_dict[unique_slab_name] = {
            "pavement_height": barrier_info.common_info.pavement_height,
            "points": barrier_base_points_dict,
        }
        world_items_dict_for_bake[unique_slab_name] = barrier_dict # ここはbake用
    for center_barrier_info in center_barrier_infos:
        unique_slab_name = f"{center_barrier_info.bridge_name}_{center_barrier_info.num}"
        barrier_info = next(b for b in barrier_infos if b.bridge_name == center_barrier_info.bridge_name and b.num == center_barrier_info.num)
        center_barrier_dict, center_barrier_base_points_dict = get_center_barriers_and_noses(
            center_barrier_info = center_barrier_info,
            slab_edge_points = barrier_info.slab_edge_points,
        )
        center_barrier_base_bottom_dict[unique_slab_name] = {
            "pavement_height": center_barrier_info.barrier_common_info.pavement_height,
            "points": center_barrier_base_points_dict,
        }
        world_items_dict_for_bake_2[unique_slab_name] = center_barrier_dict # ここはbake用
    
    save_json_and_pickle(
        data = barrier_base_bottom_dict,
        folder_path = DIR,
        name = f"{Filenames.WORLD}_{Filenames.SLAB}_{Filenames.BARRIER}_{Filenames.BASE_POINT}",
    )
    save_json_and_pickle(
        data = center_barrier_base_bottom_dict,
        folder_path = DIR,
        name = f"{Filenames.WORLD}_{Filenames.SLAB}_{Filenames.CENTER}_{Filenames.BARRIER}_{Filenames.BASE_POINT}",
    )

    def get_keys_and_values_for_bake(world_items_dict):
        flatten_dict_for_bake = flatten_any(world_items_dict)
        items = list(flatten_dict_for_bake.items())
        # valueがNoneのものはbakeできないので除外
        items = [(k,v) for k,v in items if v is not None]
        keys = [k for k, _ in items]
        values = [v for _, v in items]
        return keys, values
    return get_keys_and_values_for_bake(world_items_dict_for_bake), get_keys_and_values_for_bake(world_items_dict_for_bake_2)

if __name__ == "__main__":
    (bake_keys, bake_objs), (bake_keys2, bake_objs2) = main("initial")
