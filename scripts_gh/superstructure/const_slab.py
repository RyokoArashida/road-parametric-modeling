from typing import Optional, Union

import Rhino.Geometry as rg

from my_project.config.file_names import Filenames
from my_project.config.paths import (
    FINAL_OUTPUT_DIR,
    INITIAL_OUTPUT_DIR,
)
from my_project.config.schemas.input_slab_schemas import (
    EmergencyLaneInfo,
    SlabInfo,
    SlabPointInfo,
)
from my_project.config.util_schemas import (
    MonoSlope,
    Point3D,
)
from my_project.utils.geometry.points import get_point_by_xy_offset
from my_project.utils.geometry.vectors import get_frame_2D
from my_project.utils.geometry_gh.const import (
    const_point_obj,
    const_polycurve_obj,
)
from my_project.utils.io import load_from_pickle


def get_slab_points_length(
    point_infos: list[SlabPointInfo],
) -> list[SlabPointInfo]:
    CL_points = [p.CL for p in point_infos]
    CL_polyline = const_polycurve_obj(CL_points)
    point_distances = []
    for p in point_infos:
        p_obj = const_point_obj(p.CL)
        t = CL_polyline.ClosestPoint(p_obj)[1]
        if t == 0:
            distance = 0
        elif t == len(CL_points) - 1:
            distance = CL_polyline.GetLength()
        else:
            split_curves = CL_polyline.Split(t)
            start_curve = split_curves[0]
            distance = start_curve.GetLength()
        point_distances.append(distance)
    return point_distances, CL_polyline

def get_point_from_offset(
    base_line: Union[rg.Curve, rg.Line, rg.PolylineCurve],
    base_point_name: str,
    offset_distance: float,
    point_infos: list[SlabPointInfo],
    point_distances: list[float],
) -> rg.Point3d:
    base_point_idx = next(i for i, p in enumerate(point_infos) if p.name == base_point_name)
    base_point_distance = point_distances[base_point_idx]
    offset_point_distance = base_point_distance + offset_distance
    if offset_point_distance < 0 or offset_point_distance > point_distances[-1]:
        raise ValueError(f"base_point_distance={base_point_distance}, offset_point_distance={offset_point_distance}, total_length={point_distances[-1]}")
    offset_point = base_line.PointAtLength(offset_point_distance)
    return offset_point, offset_point_distance

def get_add_point_info(
    sorted_add_point_infos: list[SlabPointInfo],
    sorted_add_distances: list[float],
    add_point_idx: str,
) -> Optional[SlabPointInfo]:
    add_point_distance = sorted_add_distances[add_point_idx]
    pre_point_idx = add_point_idx - 1
    post_point_idx = add_point_idx + 1
    pre_point_distance, pre_point_info = sorted_add_distances[pre_point_idx], sorted_add_point_infos[pre_point_idx]
    post_point_distance, post_point_info = sorted_add_distances[post_point_idx], sorted_add_point_infos[post_point_idx]
    if pre_point_distance == add_point_distance:
        return None
    elif post_point_distance == add_point_distance:
        return None
    else:
        gap_distance_Pre2Post = post_point_distance - pre_point_distance
        gap_distance_Pre2Target = add_point_distance - pre_point_distance
        ratio = gap_distance_Pre2Target / gap_distance_Pre2Post
        Pre_L2 = pre_point_info.L2
        Post_L2 = post_point_info.L2
        Pre_R2 = pre_point_info.R2
        Post_R2 = post_point_info.R2
        L2 = Point3D(
            x = Pre_L2.x + (Post_L2.x - Pre_L2.x) * ratio,
            y = Pre_L2.y + (Post_L2.y - Pre_L2.y) * ratio,
            z = Pre_L2.z + (Post_L2.z - Pre_L2.z) * ratio,
        )
        R2 = Point3D(
            x = Pre_R2.x + (Post_R2.x - Pre_R2.x) * ratio,
            y = Pre_R2.y + (Post_R2.y - Pre_R2.y) * ratio,
            z = Pre_R2.z + (Post_R2.z - Pre_R2.z) * ratio,
        )
        frame2D = get_frame_2D(
            point_u = L2,
            point_d = R2,
            y_direction="UP"
        )
        slope = MonoSlope(
            value = (L2.z - R2.z) / ((L2.x - R2.x)**2 + (L2.y - R2.y)**2)**0.5
        )
        return SlabPointInfo(
            name = "temp",
            CL = None,
            L2 = L2,
            R2 = R2,
            UDframe2D = frame2D,
            UDslope = slope,
        )

def get_top_points(
    point_infos: list[SlabPointInfo],
    point_distances: list[float],
    CL_polyline: rg.PolylineCurve,
    emergency_lane_infos: list[EmergencyLaneInfo],
    edge_offset: float,
) -> list[SlabPointInfo]:
    add_point_infos = point_infos.copy()
    add_distances = point_distances.copy()
    top_surf_distance_list = [] #(start_dis, end_dis, start_L_width, end_L_width, start_R_width, end_R_width)のリスト。非常駐車帯の始点・終点の距離と幅を記録する。)
    L_top_points = []
    R_top_points = []
    for i, emergency_lane_info in enumerate(emergency_lane_infos):
        base_point_name = emergency_lane_info.start_offset.name
        EMstart_offset = emergency_lane_info.start_offset.offset_y
        EMstart_point, EMstart_distance = get_point_from_offset(
            base_line = CL_polyline,
            base_point_name = base_point_name,
            offset_distance = EMstart_offset,
            point_infos = point_infos,
            point_distances = point_distances,
        )
        EMstraight_start_offset = EMstart_offset + emergency_lane_info.taper_length_N
        EMstraight_start_point, EMstraight_start_distance = get_point_from_offset(
            base_line = CL_polyline,
            base_point_name = base_point_name,
            offset_distance = EMstraight_start_offset,
            point_infos = point_infos,
            point_distances = point_distances,
        )
        EMstraight_end_offset = EMstraight_start_offset + emergency_lane_info.length
        EMstraight_end_point, EMstraight_end_distance = get_point_from_offset(
            base_line = CL_polyline,
            base_point_name = base_point_name,
            offset_distance = EMstraight_end_offset,
            point_infos = point_infos,
            point_distances = point_distances,
        )
        EMend_offset = EMstraight_end_offset + emergency_lane_info.teper_length_T
        EMend_point, EMend_distance = get_point_from_offset(
            base_line = CL_polyline,
            base_point_name = base_point_name,
            offset_distance = EMend_offset,
            point_infos = point_infos,
            point_distances = point_distances,
        )
        EM_add_names = [f"非常駐車帯{i}_始点", f"非常駐車帯{i}_並行部始点", f"非常駐車帯{i}_並行部終点", f"非常駐車帯{i}_終点"]
        EM_add_points = [EMstart_point, EMstraight_start_point, EMstraight_end_point, EMend_point]
        EM_add_distances = [EMstart_distance, EMstraight_start_distance, EMstraight_end_distance, EMend_distance]
        for name, point, distance in zip(EM_add_names, EM_add_points, EM_add_distances):
            add_point_infos.append(
                SlabPointInfo(
                    name = name,
                    CL = point,
                    L2 = None,
                    R2 = None,
                    UDframe2D = None,
                    UDslope = None,
                )
            )
            add_distances.append(distance)
        
        pos = emergency_lane_info.LR
        width = emergency_lane_info.width
        if len(top_surf_distance_list) > 0:
            last_distance = top_surf_distance_list[-1][1]
        else:
            last_distance = 0
        if pos == "L":
            L_width = width
            R_width = 0
        else:
            L_width = 0
            R_width = width
        top_surf_distance_list.extend([
            (last_distance, EMstart_distance, 0, 0, 0, 0),
            (EMstart_distance, EMstraight_start_distance, 0, L_width, 0, R_width),
            (EMstraight_start_distance, EMstraight_end_distance, L_width, L_width, R_width, R_width),
            (EMstraight_end_distance, EMend_distance, L_width, 0, R_width, 0),
        ])

    sorted_add_point_infos, sorted_add_distances = zip(*sorted(zip(add_point_infos, add_distances), key=lambda x: x[1]))
    # まずは追加した点のL2, R2, frame, slopeを補完する。ただし被っているときは補完せず、元の点の情報を使う。
    new_point_infos = []
    new_distances = []
    for i, point_info in enumerate(sorted_add_point_infos):
        distance = sorted_add_distances[i]
        if point_info.name.startswith("非常駐車帯"):
            temp_point_info = get_add_point_info(
                sorted_add_point_infos = sorted_add_point_infos,
                sorted_add_distances = sorted_add_distances,
                add_point_idx = i,
            )
            if temp_point_info is None:
                continue
            point_info = SlabPointInfo(
                name = point_info.name,
                CL = point_info.CL,
                L2 = temp_point_info.L2,
                R2 = temp_point_info.R2,
                UDframe2D = temp_point_info.UDframe2D,
                UDslope = temp_point_info.UDslope,
            )
            new_point_infos.append(point_info)
            new_distances.append(distance)
        else:
            new_point_infos.append(point_info)
            new_distances.append(distance)
    
    # 次に各点の上端部点を求める
    if len(top_surf_distance_list) == 0:
        top_surf_distance_list.append((0, point_distances[-1], 0, 0, 0, 0)) # 非常駐車帯がないときは全区間の距離情報を追加
    else:
        for point_info, distance in zip(new_point_infos, new_distances):
            print(point_info.name, distance)
        if top_surf_distance_list[0][0] != 0:
            top_surf_distance_list.append((0, top_surf_distance_list[0][0], 0, 0, 0, 0)) # 始点の距離情報を追加
        if top_surf_distance_list[-1][1] != point_distances[-1]:
            top_surf_distance_list.append((top_surf_distance_list[-1][1], point_distances[-1], 0, 0, 0, 0)) # 終点の距離情報を追加
    print("top_surf_distance_list", top_surf_distance_list)
    for i, (point_info, distance) in enumerate(zip(new_point_infos, new_distances)):
        if i == len(sorted_add_point_infos) - 1: # ＜で計算しているので最後の点はループの外で計算する
            L_offset = top_surf_distance_list[-1][3]
            R_offset = top_surf_distance_list[-1][5]
        for start_distance, end_distance, start_L_width, end_L_width, start_R_width, end_R_width in top_surf_distance_list:
            if distance >= start_distance and distance < end_distance:
                if start_L_width == end_L_width:
                    L_offset = start_L_width
                else:
                    L_offset = start_L_width + (end_L_width - start_L_width) * (distance - start_distance) / (end_distance - start_distance)
                if start_R_width == end_R_width:
                    R_offset = start_R_width
                else:
                    R_offset = start_R_width + (end_R_width - start_R_width) * (distance - start_distance) / (end_distance - start_distance)
                break
        top_L_point = get_point_by_xy_offset(
            point1=point_info.L2,
            point2=point_info.R2,
            offset=-(L_offset + edge_offset), # 左方向にオフセットするのでマイナス
        )
        top_R_point = get_point_by_xy_offset(
            point1=point_info.R2,
            point2=point_info.L2,
            offset=-(R_offset + edge_offset), # 右方向にオフセットするのでマイナス
        )
        L_top_points.append(top_L_point)
        R_top_points.append(top_R_point)
    
    return L_top_points, R_top_points, new_point_infos, new_distances

def get_each_slab(
    slab_info: SlabInfo,
) -> rg.Brep:
    cross_girder_points = [p.CL for p in slab_info.point_infos]
    distances, CL_polyline = get_slab_points_length(slab_info.point_infos)
    L_top_points, R_top_points, new_point_infos, new_distances = get_top_points(
        point_infos = slab_info.point_infos,
        point_distances = distances,
        CL_polyline = CL_polyline,
        emergency_lane_infos = slab_info.emergency_lane,
        edge_offset = slab_info.width.edge_offset,
    )

    # debug
    return L_top_points, R_top_points





def main(initial_or_final: str):
    if initial_or_final == "initial":
        DIR = INITIAL_OUTPUT_DIR
    elif initial_or_final == "final":
        DIR = FINAL_OUTPUT_DIR

    slab_infos = load_from_pickle(
        file_path=DIR /  f"{Filenames.INPUT}_{Filenames.SLAB}.pickle",
    )
    barrier_base_bottom_dict = {}
    world_items_dict_for_bake = {}
    world_items_dict_for_bake_2 = {}

    # debug
    points = []
    for slab_info in slab_infos:
        L_top_points, R_top_points = get_each_slab(slab_info)
        for p in L_top_points:
            points.append(const_point_obj(p))
        for p in R_top_points:
            points.append(const_point_obj(p))
    return points
        
    #     abut_dict, barrier_dict, barrier_base_point_dict = get_each_abut(
    #         input_indiv_info = indiv_info,
    #         input_common_info = common_info,
    #     )

    #     barrier_base_bottom_dict[abut_name] = barrier_base_point_dict # ここはpickel用
    #     world_items_dict_for_bake[abut_name] = abut_dict # ここはbake用
    #     world_items_dict_for_bake_2[abut_name] = barrier_dict # ここはbake用
    
    # # 壁高欄起点情報を全部pickelに保存
    # save_json_and_pickle(
    #     data = barrier_base_bottom_dict,
    #     folder_path = DIR,
    #     name = f"{Filenames.WORLD}_{Filenames.ABUT}_{Filenames.BARRIER}_{Filenames.BASE_POINT}",
    # )
    # def get_keys_and_values_for_bake(world_items_dict):
    #     flatten_dict_for_bake = flatten_any(world_items_dict)
    #     items = list(flatten_dict_for_bake.items())
    #     # valueがNoneのものはbakeできないので除外
    #     items = [(k,v) for k,v in items if v is not None]
    #     keys = [k for k, _ in items]
    #     values = [v for _, v in items]
    #     return keys, values
#     return get_keys_and_values_for_bake(world_items_dict_for_bake), get_keys_and_values_for_bake(world_items_dict_for_bake_2)

if __name__ == "__main__":
#     (bake_keys, bake_objs), (bake_keys2, bake_objs2) = main("initial")
    # debug
    points = main("initial")