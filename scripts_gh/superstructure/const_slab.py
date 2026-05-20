from typing import Optional, Union

import Rhino.Geometry as rg

from my_project.config.file_names import Filenames
from my_project.config.paths import (
    FINAL_OUTPUT_DIR,
    INITIAL_OUTPUT_DIR,
)
from my_project.config.schemas.main_girder_schemas import (
    MainGirderInfo,
    TopFlangePointInfo,
)
from my_project.config.schemas.slab_schemas import (
    AdditionalPointInfo,
    BottomSurfaceInfo,
    DepressedPointInfo,
    EmergencyLaneInfo,
    MainGirderTopPointInfo,
    SlabBottomPoints,
    SlabCGPointInfo,
    SlabCorners,
    SlabInfo,
)
from my_project.config.util_schemas import MonoSlope, Point2D, Point3D
from my_project.utils.dataframe import flatten_any
from my_project.utils.geometry.points import (
    get_point_by_xy_offset,
)
from my_project.utils.geometry.vectors import get_frame_2D
from my_project.utils.geometry_gh.attributes import get_distance_along_crv
from my_project.utils.geometry_gh.const import (
    const_planer_srf_from_points,
    const_point_obj,
    const_polycurve_obj,
    const_srf_from_2crvs,
)
from my_project.utils.geometry_gh.intersect import (
    get_intersect_point_on_curve_with_xy,
    get_intersect_points_on_brep_with_point,
)
from my_project.utils.io import load_from_pickle, save_json_and_pickle


def get_slab_points_length(
    point_infos: list[SlabCGPointInfo],
) -> list[SlabCGPointInfo]:
    CL_points = [p.CL for p in point_infos]
    CL_polyline = const_polycurve_obj(CL_points)
    point_distances = get_distance_along_crv(
        curve = CL_polyline,
        points = [p.CL for p in point_infos],
    )
    return point_distances, CL_polyline

def get_point_from_offset(
    base_line: Union[rg.Curve, rg.Line, rg.PolylineCurve],
    base_point_name: str,
    offset_distance: float,
    point_infos: list[SlabCGPointInfo],
    point_distances: list[float],
) -> rg.Point3d:
    base_point_idx = next(i for i, p in enumerate(point_infos) if p.CG_name == base_point_name)
    base_point_distance = point_distances[base_point_idx]
    if offset_distance == 0:
        return point_infos[base_point_idx].CL, base_point_distance
    offset_point_distance = base_point_distance + offset_distance
    if offset_point_distance < 0 or offset_point_distance > point_distances[-1]:
        raise ValueError(f"base_point_distance={base_point_distance}, offset_point_distance={offset_point_distance}, total_length={point_distances[-1]}")
    offset_point = base_line.PointAtLength(offset_point_distance)
    return offset_point, offset_point_distance

def get_point_between_points(
    point1: Union[Point3D,Point2D],
    point2: Union[Point3D,Point2D],
    distance1: float,
    distance2: float,
    target_distance: float,
) -> Union[Point3D, Point2D]:
    if distance1 == distance2:
        raise ValueError(f"distance1 and distance2 are the same: {distance1}")
    ratio = (target_distance - distance1) / (distance2 - distance1)
    x = point1.x + (point2.x - point1.x) * ratio
    y = point1.y + (point2.y - point1.y) * ratio
    if isinstance(point1, Point3D) and isinstance(point2, Point3D):
        z = point1.z + (point2.z - point1.z) * ratio
        return Point3D(x=x, y=y, z=z)
    else:
        return Point2D(x=x, y=y)

def get_add_point_info(
    original_point_infos: list[SlabCGPointInfo],
    original_distances: list[float],
    sorted_add_point_infos: list[SlabCGPointInfo],
    sorted_add_distances: list[float],
    add_point_idx: str,
) -> tuple[Optional[SlabCGPointInfo], Optional[str], Optional[str], Optional[float], Optional[float]]:
    if add_point_idx == 0 or add_point_idx == len(sorted_add_point_infos) - 1:
        return None, None, None, None, None
    add_point_distance = sorted_add_distances[add_point_idx]
    pre_original_point_idx = next(i for i, d in enumerate(original_distances) if d > add_point_distance) - 1
    post_original_point_idx = pre_original_point_idx + 1
    pre_point_distance, pre_point_info = original_distances[pre_original_point_idx], original_point_infos[pre_original_point_idx]
    post_point_distance, post_point_info = original_distances[post_original_point_idx], original_point_infos[post_original_point_idx]
    pre_point_name, post_point_name = pre_point_info.CG_name, post_point_info.CG_name
    if pre_point_distance == add_point_distance:
        return None, None, None, None, None
    elif post_point_distance == add_point_distance:
        return None, None, None, None, None
    else:
        Pre_L2 = pre_point_info.L2
        Post_L2 = post_point_info.L2
        Pre_R2 = pre_point_info.R2
        Post_R2 = post_point_info.R2
        L2 = get_point_between_points(
            point1 = Pre_L2,
            point2 = Post_L2,
            distance1 = pre_point_distance,
            distance2 = post_point_distance,
            target_distance = add_point_distance,
        )
        R2 = get_point_between_points(
            point1 = Pre_R2,
            point2 = Post_R2,
            distance1 = pre_point_distance,
            distance2 = post_point_distance,
            target_distance = add_point_distance,
        )
        Pre_MG_points = pre_point_info.MG_points
        Post_MG_points = post_point_info.MG_points
        if len(Pre_MG_points) != len(Post_MG_points):
            raise ValueError(f"Pre_girder_points and Post_girder_points have different lengths: {len(Pre_MG_points)}, {len(Post_MG_points)}")
        MG_points = []
        for pre_p, post_p in zip(Pre_MG_points, Post_MG_points):
            if pre_p.MG_name != post_p.MG_name:
                raise ValueError(f"pre_p and post_p have different names: {pre_p.MG_name}, {post_p.MG_name}")
            name = pre_p.MG_name
            MG_point = get_point_between_points(
                point1 = pre_p.center,
                point2 = post_p.center,
                distance1 = pre_point_distance,
                distance2 = post_point_distance,
                target_distance = add_point_distance,
            )
            MG_points.append(MainGirderTopPointInfo(
                MG_name = name,
                center = MG_point,
                U_edge = None,
                D_edge = None,
            ))

        frame2D = get_frame_2D(
            point_u = L2,
            point_d = R2,
            y_direction="UP"
        )
        slope = MonoSlope(
            value = (L2.z - R2.z) / ((L2.x - R2.x)**2 + (L2.y - R2.y)**2)**0.5
        )
        return SlabCGPointInfo(
            CG_name = "temp",
            CL = None,
            L2 = L2,
            R2 = R2,
            MG_points = MG_points,
            UDframe2D = frame2D,
            UDslope = slope,
        ), pre_point_name, post_point_name, pre_point_distance, post_point_distance

def get_top_points(
    point_infos: list[SlabCGPointInfo],
    point_distances: list[float],
    CL_polyline: rg.PolylineCurve,
    emergency_lane_infos: list[EmergencyLaneInfo],
    edge_offset: float,
    pavement_thickness: float,
) -> tuple[dict[str, Point3D], dict[str, Point3D], list[SlabCGPointInfo], list[float]]:
    add_point_infos = point_infos.copy()
    add_distances = point_distances.copy()
    top_surf_distance_list = [] #(start_dis, end_dis, start_L_width, end_L_width, start_R_width, end_R_width)のリスト。非常駐車帯の始点・終点の距離と幅を記録する。)
    L_top_point_dict = {}
    R_top_point_dict = {}
    last_distance = 0
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
                SlabCGPointInfo(
                    CG_name = name,
                    CL = point,
                    L2 = None,
                    R2 = None,
                    MG_points = None,
                    UDframe2D = None,
                    UDslope = None,
                )
            )
            add_distances.append(distance)
        
        pos = emergency_lane_info.LR
        width = emergency_lane_info.width
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
        last_distance = EMend_distance

    sorted_add_point_infos, sorted_add_distances = zip(*sorted(zip(add_point_infos, add_distances), key=lambda x: x[1]))
    # まずは追加した点のL2, R2, frame, slopeを補完する。ただし被っているときは補完せず、元の点の情報を使う。
    new_point_infos = []
    new_distances = []
    for i, point_info in enumerate(sorted_add_point_infos):
        distance = sorted_add_distances[i]
        if point_info.CG_name.startswith("非常駐車帯"):
            temp_point_info, _, _, _, _ = get_add_point_info(
                original_point_infos = point_infos,
                original_distances = point_distances,
                sorted_add_point_infos = sorted_add_point_infos,
                sorted_add_distances = sorted_add_distances,
                add_point_idx = i,
            )
            if temp_point_info is None:
                continue
            point_info = SlabCGPointInfo(
                CG_name = point_info.CG_name,
                CL = point_info.CL,
                L2 = temp_point_info.L2,
                R2 = temp_point_info.R2,
                MG_points = temp_point_info.MG_points,
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
        if top_surf_distance_list[0][0] != 0:
            top_surf_distance_list.append((0, top_surf_distance_list[0][0], 0, 0, 0, 0)) # 始点の距離情報を追加
        if top_surf_distance_list[-1][1] != point_distances[-1]:
            top_surf_distance_list.append((top_surf_distance_list[-1][1], point_distances[-1], 0, 0, 0, 0)) # 終点の距離情報を追加
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
        top_L_point = Point3D(x=top_L_point.x, y=top_L_point.y, z=top_L_point.z - pavement_thickness) # 上端部点は舗装厚分だけ下げる
        top_R_point = Point3D(x=top_R_point.x, y=top_R_point.y, z=top_R_point.z - pavement_thickness) # 上端部点は舗装厚分だけ下げる
        L_top_point_dict[point_info.CG_name] = top_L_point
        R_top_point_dict[point_info.CG_name] = top_R_point
    
    return L_top_point_dict, R_top_point_dict, new_point_infos, new_distances



def get_bottom_points(
    point_infos: list[SlabCGPointInfo],
    point_distances: list[float],
    bottom_surface_infos: list[BottomSurfaceInfo],
    CL_polyline: rg.PolylineCurve,
    base_edge_height: float,
    base_girder_above_height: float,
    girder_flange_width: float,
    L_top_point_dist: dict[str, Point3D],
    R_top_point_dist: dict[str, Point3D],
):
    add_point_infos = point_infos.copy()
    add_distances = point_distances.copy()
    bottom_surf_distance_list = [] #(start_dis, end_dis, start_slope_width, end_slope_width, start_center_height, end_center_height)のリスト。下面変化の始点・終点の距離と斜面の幅、中央高さを記録する。)
    last_distance = None
    last_center_height = None
    last_slope_width = None
    for i, bottom_surface_info in enumerate(bottom_surface_infos):
        Bstart_name = bottom_surface_info.start_offset.name
        Bstart_offset = bottom_surface_info.start_offset.offset_y
        Bend_name = bottom_surface_info.end_offset.name
        Bend_offset = bottom_surface_info.end_offset.offset_y
        Bstart_point, Bstart_distance = get_point_from_offset(
            base_line = CL_polyline,
            base_point_name = Bstart_name,
            offset_distance = Bstart_offset,
            point_infos = point_infos,
            point_distances = point_distances,
        )
        Bend_point, Bend_distance = get_point_from_offset(
            base_line = CL_polyline,
            base_point_name = Bend_name,
            offset_distance = Bend_offset,
            point_infos = point_infos,
            point_distances = point_distances,
        )
        B_add_names = [f"下面変化点{i}_始点", f"下面変化点{i}_終点"]
        B_add_points = [Bstart_point, Bend_point]
        B_add_distances = [Bstart_distance, Bend_distance]
        for name, point, distance in zip(B_add_names, B_add_points, B_add_distances):
            add_point_infos.append(
                SlabCGPointInfo(
                    CG_name = name,
                    CL = point,
                    L2 = None,
                    R2 = None,
                    MG_points = None,
                    UDframe2D = None,
                    UDslope = None,
                )
            )
            add_distances.append(distance)

        slope_width = bottom_surface_info.slope_width
        center_height = bottom_surface_info.center_height
        if last_distance is None:
            bottom_surf_distance_list.append(
                (Bstart_distance, Bend_distance, slope_width, slope_width, center_height, center_height)
            )
        else:
            bottom_surf_distance_list.extend([
                (last_distance, Bstart_distance, last_slope_width, slope_width, last_center_height, center_height),
                (Bstart_distance, Bend_distance, slope_width, slope_width, center_height, center_height),
            ])
        last_distance = Bend_distance
        last_slope_width = slope_width
        last_center_height = center_height
    
    sorted_add_point_infos, sorted_add_distances = zip(*sorted(zip(add_point_infos, add_distances), key=lambda x: x[1]))
    # まずは追加した点のL2, R2, frame, slope, L_top_point, R_top_pointを補完する。ただし被っているときは補完せず、元の点の情報を使う。
    new_point_infos = []
    new_distances = []
    new_L_top_point_dict = {}
    new_R_top_point_dict = {}
    for i, point_info in enumerate(sorted_add_point_infos):
        distance = sorted_add_distances[i]
        if point_info.CG_name.startswith("下面変化点"):
            temp_point_info, pre_point_name, post_point_name, pre_point_distance, post_point_distance = get_add_point_info(
                original_point_infos = point_infos,
                original_distances = point_distances,
                sorted_add_point_infos = sorted_add_point_infos,
                sorted_add_distances = sorted_add_distances,
                add_point_idx = i,
            )
            if temp_point_info is None:
                continue
            point_info = SlabCGPointInfo(
                CG_name = point_info.CG_name,
                CL = point_info.CL,
                L2 = temp_point_info.L2,
                R2 = temp_point_info.R2,
                MG_points = temp_point_info.MG_points,
                UDframe2D = temp_point_info.UDframe2D,
                UDslope = temp_point_info.UDslope,
            )
            new_point_infos.append(point_info)
            new_distances.append(distance)
            
            pre_top_L_point = L_top_point_dist[pre_point_name]
            pre_top_R_point = R_top_point_dist[pre_point_name]
            post_top_L_point = L_top_point_dist[post_point_name]
            post_top_R_point = R_top_point_dist[post_point_name]
            top_L_point = get_point_between_points(
                point1 = pre_top_L_point,
                point2 = post_top_L_point,
                distance1 = pre_point_distance,
                distance2 = post_point_distance,
                target_distance = distance,
            )
            top_R_point = get_point_between_points(
                point1 = pre_top_R_point,
                point2 = post_top_R_point,
                distance1 = pre_point_distance,
                distance2 = post_point_distance,
                target_distance = distance,
            )
            new_L_top_point_dict[point_info.CG_name] = top_L_point
            new_R_top_point_dict[point_info.CG_name] = top_R_point
        else:
            new_point_infos.append(point_info)
            new_distances.append(distance)
            new_L_top_point_dict[point_info.CG_name] = L_top_point_dist[point_info.CG_name]
            new_R_top_point_dict[point_info.CG_name] = R_top_point_dist[point_info.CG_name]
    
    # 次に各点のコーナーを全部求める
    corner_points = []
    # debug
    if len(bottom_surf_distance_list) == 0:
        bottom_surf_distance_list.append((0, point_distances[-1], 0, 0, base_girder_above_height, base_girder_above_height)) # 下面変化がないときは全区間の距離情報を追加
    for i, (point_info, distance) in enumerate(zip(new_point_infos, new_distances)):
        if i == len(sorted_add_point_infos) - 1: # ＜で計算しているので最後の点はループの外で計算する
            slope_width = bottom_surf_distance_list[-1][3]
            center_height = bottom_surf_distance_list[-1][5]
        for start_distance, end_distance, start_slope_width, end_slope_width, start_center_height, end_center_height in bottom_surf_distance_list:
            if distance >= start_distance and distance < end_distance:
                if start_slope_width == end_slope_width:
                    slope_width = start_slope_width
                else:
                    slope_width = start_slope_width + (end_slope_width - start_slope_width) * (distance - start_distance) / (end_distance - start_distance)
                if start_center_height == end_center_height:
                    center_height = start_center_height
                else:
                    center_height = start_center_height + (end_center_height - start_center_height) * (distance - start_distance) / (end_distance - start_distance)
                break
        y_axis_vector = point_info.UDframe2D.y_axis
        MG_points = point_info.MG_points # L側から順番になっている。
        L_top_point = new_L_top_point_dict[point_info.CG_name]
        R_top_point = new_R_top_point_dict[point_info.CG_name]

        L_bottom_edge_point = Point3D(L_top_point.x, L_top_point.y, L_top_point.z - base_edge_height)
        R_bottom_edge_point = Point3D(R_top_point.x, R_top_point.y, R_top_point.z - base_edge_height)

        MG_top_points = []
        for MG_point in MG_points:
            GC_ab_point = get_intersect_point_on_curve_with_xy( 
                curve = const_polycurve_obj([L_top_point, R_top_point]),
                point = MG_point.center,
                axis_vector=y_axis_vector
            )        
            GU_ab_point = get_point_by_xy_offset(
                point1=GC_ab_point,
                point2=L_top_point,
                offset=girder_flange_width/2
            )
            GD_ab_point = get_point_by_xy_offset(
                point1=GC_ab_point,
                point2=R_top_point,
                offset=girder_flange_width/2
            )
            GC_top_point = Point3D(GC_ab_point.x, GC_ab_point.y, GC_ab_point.z - base_girder_above_height)
            GU_top_point = Point3D(GU_ab_point.x, GU_ab_point.y, GU_ab_point.z - base_girder_above_height)
            GD_top_point = Point3D(GD_ab_point.x, GD_ab_point.y, GD_ab_point.z - base_girder_above_height)

                    
            MG_top_points.append(MainGirderTopPointInfo(
                MG_name = MG_point.MG_name,
                center = GC_top_point,
                U_edge = GU_top_point,
                D_edge = GD_top_point,
            ))

        depressed_points = []
        if slope_width == 0:
            if center_height != base_girder_above_height:
                raise ValueError(f"slope_width is 0 but center_height is different from base_girder_above_height: {center_height} vs {base_girder_above_height}")
            is_center_depressed = False
        else:
            if center_height == base_girder_above_height:
                raise ValueError(f"slope_width is not 0 but center_height is the same as base_girder_above_height: {center_height} vs {base_girder_above_height}")
            is_center_depressed = True
            for i in range(len(MG_top_points)-1):
                GU_ab_point = MG_top_points[i].D_edge
                GD_ab_point = MG_top_points[i+1].U_edge
                dep_start_ab_pave_point = get_point_by_xy_offset(
                    point1=GU_ab_point,
                    point2=GD_ab_point,
                    offset=slope_width
                )
                dep_end_ab_pave_point = get_point_by_xy_offset(
                    point1=GD_ab_point,
                    point2=GU_ab_point,
                    offset=slope_width
                )
                height_gap = base_girder_above_height - center_height
                dep_start_point = Point3D(dep_start_ab_pave_point.x, dep_start_ab_pave_point.y, dep_start_ab_pave_point.z + height_gap)
                dep_end_point = Point3D(dep_end_ab_pave_point.x, dep_end_ab_pave_point.y, dep_end_ab_pave_point.z + height_gap)
                depressed_points.append(DepressedPointInfo(
                    pre_girder_name = MG_top_points[i].MG_name,
                    post_girder_name = MG_top_points[i+1].MG_name,
                    start_point=dep_start_point,
                    end_point=dep_end_point,
                ))
        corner_points.append(SlabCorners(
            CG_name = point_info.CG_name,
            is_center_depressed = is_center_depressed,
            Utop=L_top_point,
            Dtop=R_top_point,
            Ubottom=L_bottom_edge_point,
            Dbottom=R_bottom_edge_point,
            MG_top_points=MG_top_points,
            depressed_points=depressed_points,
        ))
    return corner_points

"""
ここであり得るパターン
①全て同じ
②桁の数は同じで、へこみの有無が変わる
③桁の数が変わる。
ただし、
・桁の数が変わるときは、へこみの有無は同じであるべき（違うとどんな形になるかわからない）
・両端は同じであるべき（違うと不連続な形状になるので別の床版として処理することにしているはず）
・桁の数が変わるとは、必ず増減どちらかだけになる。例えば[1,2,4]->[1,2,3,4]->[1,3,4]みたいな感じに重複する断面がないとおかしい。例えば[1,2,4]->[1,3,4]みたいな感じでいきなり2が消えて3が増えるのはおかしい。
・へこみがあって桁の数が変わると、桁上部分が相手の広いへこみにアクセスすることになりｚ方向の傾きがおかしい。おそらく桁の数が変わるときはへこませることが出来ない。よってへこみがない。
"""
def const_indiv_slab(
    corner_points: list[SlabCorners],
    origin_names: list[str],
) -> rg.Brep:
    slab_dict = {}
    rough_slabs = []

    for i in range(len(corner_points)-1):
        corner1 = corner_points[i]
        corner2 = corner_points[i+1]
        corner1_MG_names = [p.MG_name for p in corner1.MG_top_points]
        corner2_MG_names = [p.MG_name for p in corner2.MG_top_points]
        corner1_is_depressed = corner1.is_center_depressed
        corner2_is_depressed = corner2.is_center_depressed
        if corner1_MG_names != corner2_MG_names and (corner1_is_depressed or corner2_is_depressed): 
            raise ValueError(f"桁の数が違うのに、どちらかがへこんでいます。: {corner1.CG_name} has {len(corner1_MG_names)} MGs and is_center_depressed={corner1.is_center_depressed}, {corner2.CG_name} has {len(corner2_MG_names)} MGs and is_center_depressed={corner2.is_center_depressed}")
        if corner1_MG_names[0] != corner2_MG_names[0] or corner1_MG_names[-1] != corner2_MG_names[-1]:
            raise ValueError(f": 両端の桁の名前が違います。: {corner1_MG_names} vs {corner2_MG_names}, {corner1.CG_name} and {corner2.CG_name}")
        
        # 両端桁の端部→下端→上端だけはどのタイプでも同じ
        first_MG_point1 = corner1.MG_top_points[0]
        last_MG_point1 = corner1.MG_top_points[-1]
        first_MG_point2 = corner2.MG_top_points[0]
        last_MG_point2 = corner2.MG_top_points[-1]
        top_edge_crv1 = const_polycurve_obj([first_MG_point1.U_edge, corner1.Ubottom, corner1.Utop, corner1.Dtop, corner1.Dbottom, last_MG_point1.D_edge])
        top_edge_crv2 = const_polycurve_obj([first_MG_point2.U_edge, corner2.Ubottom, corner2.Utop, corner2.Dtop, corner2.Dbottom, last_MG_point2.D_edge])
        common_srf = const_srf_from_2crvs([top_edge_crv1, top_edge_crv2])
        slab_srfs = [common_srf]

        # 真ん中がへこんでいない場合、主桁の点は同じL,Rトップ上にある中心点からオフセットでとって、同じ距離ｚにずらしただけなので、端部だけつなげればよい。対象外の点も必ず端部の直線上にあるはず。
        # また、桁の数が違うときは必ずここに落ちる
        if (not corner1_is_depressed) and (not corner2_is_depressed):
            crv1 = const_polycurve_obj([first_MG_point1.U_edge, last_MG_point1.D_edge])
            crv2 = const_polycurve_obj([first_MG_point2.U_edge, last_MG_point2.D_edge])
            bottom_srf = const_srf_from_2crvs([crv1, crv2])
            slab_srfs.append(bottom_srf)

        # 両方へこんでいる場合は桁の数も同じ＝点の数が同じ
        elif corner1_is_depressed and corner2_is_depressed:
            def get_all_points(corner):
                points = []
                for i in range(len(corner.MG_top_points)):
                    points.append(corner.MG_top_points[i].U_edge)
                    points.append(corner.MG_top_points[i].center)
                    points.append(corner.MG_top_points[i].D_edge)
                    if i < len(corner.MG_top_points) - 1:
                        points.append(corner.depressed_points[i].start_point)
                        points.append(corner.depressed_points[i].end_point)
                return points
            corner1_points = get_all_points(corner1)
            corner2_points = get_all_points(corner2)
            corner1_curve = const_polycurve_obj(corner1_points)
            corner2_curve = const_polycurve_obj(corner2_points)
            bottom_srf = const_srf_from_2crvs([corner1_curve, corner2_curve])
            slab_srfs.append(bottom_srf)

        else:
            Dep_corner = corner1 if corner1_is_depressed else corner2
            NonDep_corner = corner2 if corner1_is_depressed else corner1
            for i in range(len(Dep_corner.MG_top_points)):
                dep_MG_point = Dep_corner.MG_top_points[i]
                nondep_MG_point = NonDep_corner.MG_top_points[i]
                # まず桁の上面
                dep_crv = const_polycurve_obj([dep_MG_point.U_edge, dep_MG_point.center, dep_MG_point.D_edge])
                nondep_crv = const_polycurve_obj([nondep_MG_point.U_edge, nondep_MG_point.center, nondep_MG_point.D_edge])
                girder_srf = const_srf_from_2crvs([dep_crv, nondep_crv])
                slab_srfs.append(girder_srf)
                # 次にへこんでいるところ
                if i < len(Dep_corner.MG_top_points) - 1:
                    UG_name = dep_MG_point.MG_name
                    DG_name = Dep_corner.MG_top_points[i+1].MG_name
                    dep_point = next(p for p in Dep_corner.depressed_points if p.pre_girder_name == UG_name and p.post_girder_name == DG_name)
                    if dep_point is None:
                        raise ValueError(f"へこみ点が見つかりませんでした。pre_girder_name={UG_name}, post_girder_name={DG_name}")
                    dep_UG = dep_MG_point.D_edge
                    dep_UD = dep_point.start_point
                    dep_DD = dep_point.end_point
                    dep_DG = Dep_corner.MG_top_points[i+1].U_edge
                    nondep_UG = nondep_MG_point.D_edge
                    nondep_DG = NonDep_corner.MG_top_points[i+1].U_edge
                    Usrf = const_planer_srf_from_points([dep_UG, dep_UD, nondep_UG])
                    Csrf = const_srf_from_2crvs([
                        const_polycurve_obj([dep_UD, dep_DD]),
                        const_polycurve_obj([nondep_UG, nondep_DG])
                    ])
                    Dsrf = const_planer_srf_from_points([dep_DD, dep_DG, nondep_DG])
                    slab_srfs.extend([Usrf, Csrf, Dsrf])
        slab_brep = rg.Brep.JoinBreps(slab_srfs, 0.01)
        if len(slab_brep) != 1:
            raise ValueError(f"床版のサーフェスが正しく結合できませんでした。名前は{corner1.CG_name} vs {corner2.CG_name}で、結合したサーフェスの数は{len(slab_brep)}です。")
        else:
            rough_slabs.append((corner1.CG_name, corner2.CG_name, slab_brep))

    for i in range(len(origin_names)-1):
        name1 = origin_names[i]
        name2 = origin_names[i+1]
        corner1_idx = next(idx for idx, rough_slab_tuple in enumerate(rough_slabs) if rough_slab_tuple[0] == name1)
        corner2_idx = next(idx for idx, rough_slab_tuple in enumerate(rough_slabs) if rough_slab_tuple[1] == name2)
        slabs = []
        for i in range(corner1_idx, corner2_idx + 1):
            slabs.extend(rough_slabs[i][2])

        slab_brep = rg.Brep.JoinBreps(slabs, 0.01)
        if slab_brep is None:
            raise ValueError(f"床版のサーフェスが正しく結合できませんでした。名前は{name1} vs {name2}で、結合したサーフェスの数はNoneです。")
        if len(slab_brep) != 1:
            raise ValueError(f"床版のサーフェスが正しく結合できませんでした。名前は{name1} vs {name2}で、結合したサーフェスの数は{len(slab_brep)}です。")
        slab_dict[f"{name1}_to_{name2}"] = slab_brep[0].CapPlanarHoles(0.01)

    return slab_dict


def get_each_slab(
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
    origin_CG_names = [p.CG_name for p in slab_info.point_infos]
    slab_dict = const_indiv_slab(
        corner_points = corner_points,
        origin_names = origin_CG_names
    )

    # 主桁の上面の点のデータは必要なので返す
    MG_point_dict = {}
    for name in origin_CG_names:
        corner_point_info = next(cps for cps in corner_points if cps.CG_name == name)
        MG_point_dict[name] = corner_point_info.MG_top_points
    
    # 下の端のデータは必要なので返す（横桁の張り出し）
    final_CG_names = [p.CG_name for p in new_point_infos]
    bottom_edge_point_dict = {}
    for name in final_CG_names:
        corner_point_info = next(cps for cps in corner_points if cps.CG_name == name)
        bottom_edge_point_dict[name] = SlabBottomPoints(
            CG_name=name,
            U = corner_point_info.Ubottom,
            D = corner_point_info.Dbottom,
        )
    return slab_dict, MG_point_dict, bottom_edge_point_dict, L_top_point_dict, R_top_point_dict


def get_all_MG_points(
    all_slab_dict: dict[str, dict[str, rg.Brep]],
    all_MG_top_point_dict: dict[str, dict[str, list[MainGirderTopPointInfo]]],
    all_MG_infos: list[MainGirderInfo],
    additional_point_infos: list[AdditionalPointInfo],
):
    MG_top_flange_point_dict = {}
    for unique_slab_name, MG_top_point_dict in all_MG_top_point_dict.items():
        bridge_name = unique_slab_name.split("_")[0]
        if bridge_name not in MG_top_flange_point_dict:
            MG_top_flange_point_dict[bridge_name] = {}
        for CG_name, MG_top_points in MG_top_point_dict.items():
            for MG_top_point in MG_top_points:
                MG_name = MG_top_point.MG_name
                if MG_name not in MG_top_flange_point_dict[bridge_name]:
                    MG_top_flange_point_dict[bridge_name][MG_name] = []
                main_girder_info = next(mg for mg in all_MG_infos if mg.bridge_name == bridge_name and mg.MG_name == MG_name)
                if CG_name in main_girder_info.original_CG_names:
                    if CG_name in MG_top_flange_point_dict[bridge_name][MG_name]:
                        raise ValueError(f"同じ主桁の上端部点が既に存在しています。bridge_name={bridge_name}, MG_name={MG_name}, CG_name={CG_name}")
                    MG_top_flange_point_dict[bridge_name][MG_name].append(TopFlangePointInfo(
                        CG=CG_name,
                        U=MG_top_point.U_edge,
                        D=MG_top_point.D_edge,
                        C=MG_top_point.center,
                    ))
    for additional_point_info in additional_point_infos:
        bridge_name = additional_point_info.bridge_name
        MG_name = additional_point_info.MG_name
        CG_name = additional_point_info.CG_name
        base_CG_name = additional_point_info.base_CG_name
        base_idx = next(idx for idx, top_flange_point in enumerate(MG_top_flange_point_dict[bridge_name][MG_name]) if top_flange_point.CG == base_CG_name) #なかったらエラーになる
        base_CG_offset = additional_point_info.base_CG_offset
        if base_CG_offset > 0:
            this_position = "next"
        elif base_CG_offset < 0:
            this_position = "prev"
        else:
            raise ValueError(f"base_CG_offset is 0, which is not allowed. additional_point_info={additional_point_info}")
        base_CG_U = MG_top_flange_point_dict[bridge_name][MG_name][base_idx].U
        base_CG_D = MG_top_flange_point_dict[bridge_name][MG_name][base_idx].D
        base_CG_C = MG_top_flange_point_dict[bridge_name][MG_name][base_idx].C
        if base_idx == 0: #最初だったら後のやつとの比較
            next_CG_U = MG_top_flange_point_dict[bridge_name][MG_name][1].U
            next_CG_D = MG_top_flange_point_dict[bridge_name][MG_name][1].D
            next_CG_C = MG_top_flange_point_dict[bridge_name][MG_name][1].C
            rough_U_point = get_point_by_xy_offset(
                point1=base_CG_U,
                point2=next_CG_U,
                offset=base_CG_offset, #オフセットは次横桁方向が正
            )
            rough_D_point = get_point_by_xy_offset(
                point1=base_CG_D,
                point2=next_CG_D,
                offset=base_CG_offset, #オフセットは次横桁方向が正
            )
            rough_C_point = get_point_by_xy_offset(
                point1=base_CG_C,
                point2=next_CG_C,
                offset=base_CG_offset, #オフセットは次横桁方向が正
            )
        else: #それ以外は前との比較
            prev_CG_U = MG_top_flange_point_dict[bridge_name][MG_name][base_idx-1].U
            prev_CG_D = MG_top_flange_point_dict[bridge_name][MG_name][base_idx-1].D
            prev_CG_C = MG_top_flange_point_dict[bridge_name][MG_name][base_idx-1].C
            rough_U_point = get_point_by_xy_offset(
                point1=base_CG_U,
                point2=prev_CG_U,
                offset=-base_CG_offset, #オフセットは前横桁方向が負
            )
            rough_D_point = get_point_by_xy_offset(
                point1=base_CG_D,
                point2=prev_CG_D,
                offset=-base_CG_offset, #オフセットは前横桁方向が負
            )
            rough_C_point = get_point_by_xy_offset(
                point1=base_CG_C,
                point2=prev_CG_C,
                offset=-base_CG_offset, #オフセットは前横桁方向が負
            )
        slab_pre_CG_name = additional_point_info.slab_pre_CG_name
        slab_post_CG_name = additional_point_info.slab_post_CG_name
        slab_name = f"{slab_pre_CG_name}_to_{slab_post_CG_name}"
        for slab_unique_bridge_name, slab_dict in all_slab_dict.items():
            slab_bridge_name = slab_unique_bridge_name.split("_")[0]
            if slab_bridge_name == bridge_name and slab_name in slab_dict:
                slab_brep = slab_dict[slab_name]
                break
        if slab_brep is None:
            raise ValueError(f"追加点の床版が見つかりませんでした。slab_name={slab_name}, bridge_name={bridge_name}")
        def get_slab_bottom_point(rough_point):
            intersect_pts = get_intersect_points_on_brep_with_point(
                brep = slab_brep,
                intersection_points = rough_point,
            )
            bottom_point = intersect_pts[0] if intersect_pts[0].Z < intersect_pts[1].Z else intersect_pts[1]
            return Point3D(x=bottom_point.X, y=bottom_point.Y, z=bottom_point.Z)

        U_point = get_slab_bottom_point(rough_U_point)
        D_point = get_slab_bottom_point(rough_D_point)
        C_point = get_slab_bottom_point(rough_C_point)
        this_info = TopFlangePointInfo(
            CG=CG_name,
            U=U_point,
            D=D_point,
            C=C_point,
        )
        if this_position == "next":
            MG_top_flange_point_dict[bridge_name][MG_name].insert(base_idx + 1, this_info)
        elif this_position == "prev":
            MG_top_flange_point_dict[bridge_name][MG_name].insert(base_idx, this_info)
        else:
            raise ValueError(f"Invalid this_position value: {this_position}")
    for bridge_name, MG_dict in MG_top_flange_point_dict.items():
        for MG_name, top_flange_points in MG_dict.items():
            main_girder_info = next(mg for mg in all_MG_infos if mg.bridge_name == bridge_name and mg.MG_name == MG_name)
            original_CG_names = main_girder_info.original_CG_names
            top_flange_point_CG_names = [p.CG for p in top_flange_points]
            # originalにあるものが全て入っていることを確認する
            for original_CG_name in original_CG_names:
                if original_CG_name not in top_flange_point_CG_names:
                    raise ValueError(f"主桁の上端部点のCG名が不足しています。bridge_name={bridge_name}, MG_name={MG_name}, missing_CG_name={original_CG_name}")
            print(f"主桁の上端部点のCG名が確認できました。bridge_name={bridge_name}, MG_name={MG_name}")
            # 追加点のCG名がoriginalにないものは全て追加点であることを確認する
            for top_flange_point_CG_name in top_flange_point_CG_names:
                if top_flange_point_CG_name not in original_CG_names:
                    if top_flange_point_CG_name not in [add.CG_name for add in additional_point_infos]:
                        raise ValueError(f"主桁の上端部点のCG名がoriginalにも追加点にもないものがあります。bridge_name={bridge_name}, MG_name={MG_name}, CG_name={top_flange_point_CG_name}")
                    else:
                        print(f"主桁の上端部点のCG名が追加点で確認できました。bridge_name={bridge_name}, MG_name={MG_name}, CG_name={top_flange_point_CG_name}")
    return MG_top_flange_point_dict

def get_all_bottom_edge_points(
    bottom_edge_point_dict: dict[str, dict[str, SlabBottomPoints]],
):
    all_bottom_edge_points = {}
    for unique_slab_name, edge_point_dict in bottom_edge_point_dict.items():
        bridge_name = unique_slab_name.split("_")[0]
        if bridge_name not in all_bottom_edge_points:
            all_bottom_edge_points[bridge_name] = []
        edge_points = []
        for CG_name, edge_point_info in edge_point_dict.items():
            edge_points.append(edge_point_info)
        all_bottom_edge_points[bridge_name].append(edge_points)
    return all_bottom_edge_points

def main(initial_or_final: str):
    if initial_or_final == "initial":
        DIR = INITIAL_OUTPUT_DIR
    elif initial_or_final == "final":
        DIR = FINAL_OUTPUT_DIR

    slab_infos = load_from_pickle(
        file_path=DIR /  f"{Filenames.INPUT}_{Filenames.SLAB}.pickle",
    )
    MG_infos = load_from_pickle(
        file_path=DIR /  f"{Filenames.INPUT}_{Filenames.MG}.pickle",
    )
    add_point_infos = load_from_pickle(
        file_path=DIR /  f"{Filenames.INPUT}_{Filenames.SLAB}_{Filenames.ADDITIONAL}_{Filenames.POINTS}.pickle",
    )

    MG_points_dict = {}
    bottom_edge_point_dict = {}
    all_L_top_point_dict = {}
    all_R_top_point_dict = {}
    world_items_dict_for_bake = {}
    world_items_dict_for_bake_2 = {}

    for slab_info in slab_infos:
        unique_slab_name = f"{slab_info.name}_{slab_info.num}"
        slab_dict, this_MG_point_dict, this_bottom_edge_point_dict, L_top_point_dict, R_top_point_dict = get_each_slab(
            slab_info = slab_info,
        )
        MG_points_dict[unique_slab_name] = this_MG_point_dict # ここはpickel用
        bottom_edge_point_dict[unique_slab_name] = this_bottom_edge_point_dict # ここはpickel用
        all_L_top_point_dict[unique_slab_name] = L_top_point_dict # ここはpickel用
        all_R_top_point_dict[unique_slab_name] = R_top_point_dict # ここはpickel用
        world_items_dict_for_bake[unique_slab_name] = slab_dict # ここはbake用
    
    all_MG_top_flange_point_dict = get_all_MG_points(
        all_slab_dict = world_items_dict_for_bake,
        all_MG_top_point_dict = MG_points_dict,
        all_MG_infos = MG_infos,
        additional_point_infos=add_point_infos,
    )

    all_bottom_edge_points = get_all_bottom_edge_points(
        bottom_edge_point_dict = bottom_edge_point_dict,
    )

    # debug
    points = []
    for bridge_name, edge_point_lists in all_bottom_edge_points.items():
        for edge_point_list in edge_point_lists:
            for edge_points in edge_point_list:
                points.append(const_point_obj(edge_points.U))
                points.append(const_point_obj(edge_points.D))

    all_MG_top_flange_point_dict_name = f"{Filenames.WORLD}_{Filenames.MG}_{Filenames.TOP}_{Filenames.POINTS}"
    all_bottom_edge_points_dict_name = f"{Filenames.WORLD}_{Filenames.SLAB}_{Filenames.BOTTOM}_{Filenames.POINTS}"
    all_L_top_point_dict_name = f"{Filenames.WORLD}_{Filenames.SLAB}_{Filenames.UP}_{Filenames.TOP}_{Filenames.POINTS}"
    all_R_top_point_dict_name = f"{Filenames.WORLD}_{Filenames.SLAB}_{Filenames.DOWN}_{Filenames.TOP}_{Filenames.POINTS}"

    for dict, name in zip(
        [all_MG_top_flange_point_dict, all_bottom_edge_points, all_L_top_point_dict, all_R_top_point_dict],
        [all_MG_top_flange_point_dict_name, all_bottom_edge_points_dict_name, all_L_top_point_dict_name, all_R_top_point_dict_name]
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
    # return get_keys_and_values_for_bake(world_items_dict_for_bake)
    # debug
    return get_keys_and_values_for_bake(world_items_dict_for_bake), points

if __name__ == "__main__":
    # (bake_keys, bake_objs) = main("initial")
    (bake_keys, bake_objs), points = main("initial")