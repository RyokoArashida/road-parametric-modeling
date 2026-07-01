from dataclasses import fields

from my_project.config.file_names import Filenames
from my_project.config.locale_compat import normalize_lc_time

normalize_lc_time()

import pandas as pd

from my_project.config.paths import get_output_dir
from my_project.config.schemas.main_girder_schemas import (
    BottomFlangePointInfo,
    BoxGirderInfo,
    FlangePointInfo,
    IGirderInfo,
    MainGirderInfo,
    MainGirderPointInfo,
    TopFlangePointInfo,
)
from my_project.config.util_schemas import (
    Point3D,
)
from my_project.utils.bake import get_keys_and_values_for_bake
from my_project.utils.geometry.points import (
    get_distance_2D,
    get_point_by_xy_offset,
)
from my_project.utils.geometry_gh.attributes import get_distance_along_crv
from my_project.utils.geometry_gh.const import (
    const_closed_polycurve_obj,
    const_point_obj,
    const_polycurve_obj,
    const_srf_from_2crvs,
    join_breps_or_raise,
)
from my_project.utils.io import load_from_pickle, save_json_and_pickle


def get_LCR_points_offset(next_MG_point, prev_MG_point, next_distance, prev_distance, this_distance, name):
    C_offset = this_distance - prev_distance
    C_distance = next_distance - prev_distance
    if C_distance == 0:
        return None, prev_MG_point.CG # dが重なっているときは同じCGが返される
    if C_offset == 0:
        return None, prev_MG_point.CG
    if C_offset == C_distance:
        return None, next_MG_point.CG
    ratio = C_offset / C_distance
    U_distance = get_distance_2D(next_MG_point.U, prev_MG_point.U)
    D_distance = get_distance_2D(next_MG_point.D, prev_MG_point.D)
    U_offset = ratio * U_distance
    D_offset = ratio * D_distance
    return TopFlangePointInfo(
        CG = name,
        C=get_point_by_xy_offset(
            point1 = prev_MG_point.C,
            point2 = next_MG_point.C,
            offset = C_offset,
        ),
        U=get_point_by_xy_offset(
            point1 = prev_MG_point.U,
            point2 = next_MG_point.U,
            offset = U_offset,
        ),
        D=get_point_by_xy_offset(
            point1 = prev_MG_point.D,
            point2 = next_MG_point.D,
            offset = D_offset,
        ),
    ), name

def get_LCR_points_with_distance(this_distance, distances, top_flange_MG_points, name):
    prev_point, prev_distance = next(
        (point, d)
        for point, d in reversed(list(zip(top_flange_MG_points, distances)))
        if d <= this_distance
    )
    next_point, next_distance = next(
        (point, d)
        for point, d in zip(top_flange_MG_points, distances)
        if d >= this_distance
    )
    return get_LCR_points_offset(
        next_MG_point=next_point,
        prev_MG_point=prev_point,
        next_distance=next_distance,
        prev_distance=prev_distance,
        this_distance=this_distance,
        name=name,
    )

def get_additional_top_flange_points_with_width(
    MG_info: MainGirderInfo,
    top_flange_MG_points: list[TopFlangePointInfo],
) -> tuple[list[TopFlangePointInfo], list[float], list[tuple[float, float, float, float]]]:
    CG_names = [top_flange_MG_point.CG for top_flange_MG_point in top_flange_MG_points]
    C_points = [top_flange_MG_point.C for top_flange_MG_point in top_flange_MG_points]
    C_polyline = const_polycurve_obj([top_flange_MG_point.C for top_flange_MG_point in top_flange_MG_points])
    distances = get_distance_along_crv(
        curve = C_polyline,
        points = C_points,
    )
    basic_below_flange_width = MG_info.bottom_flange_width

    width_infos = [] #(pre_distance, post_distance, pre_width, post_width)
    additional_top_flange_MG_points = top_flange_MG_points.copy()
    additional_distances = distances.copy()
    for i, width_change_info in enumerate(MG_info.width_change_infos):
        base_CG = width_change_info.CG
        if base_CG not in CG_names:
            raise ValueError(f"WidthChangeInfoのCG {base_CG} がTopFlangePointInfoのCGに見つかりませんでした。")
        base_index = CG_names.index(base_CG)
        base_distance = distances[base_index]
        width = width_change_info.y
        straight_x = width_change_info.straight_x
        slope_x = width_change_info.slope_x
        change_type = width_change_info.change_type

        if change_type == "start": # 二＞こういうかたち
            width_infos.extend([
                (base_distance, base_distance+straight_x, width, width),
                (base_distance+straight_x, base_distance+straight_x+slope_x, width, basic_below_flange_width),
            ])
            start_distance = None            
            start_point = None
            straight_start_distance = None
            straight_start_point = None
            straight_end_distance = base_distance + straight_x
            straight_end_point, _ = get_LCR_points_with_distance(
                this_distance=straight_end_distance,
                distances=distances,
                top_flange_MG_points=top_flange_MG_points,
                name = f"幅並行部終了_{i}",
            )
            end_distance = base_distance + straight_x + slope_x
            end_point, _ = get_LCR_points_with_distance(
                this_distance=end_distance,
                distances=distances,
                top_flange_MG_points=top_flange_MG_points,
                name = f"幅変化終了_{i}",
            )
        elif change_type == "end": # ＜二こういうかたち
            width_infos.extend([
                (base_distance-straight_x-slope_x, base_distance-straight_x, basic_below_flange_width, width),
                (base_distance-straight_x, base_distance, width, width),
            ])
            start_distance = base_distance - straight_x - slope_x
            start_point, _ = get_LCR_points_with_distance(
                this_distance=start_distance,
                distances=distances,
                top_flange_MG_points=top_flange_MG_points,
                name = f"幅変化開始_{i}",
            )
            straight_start_distance = base_distance - straight_x
            straight_start_point, _ = get_LCR_points_with_distance(
                this_distance=straight_start_distance,
                distances=distances,
                top_flange_MG_points=top_flange_MG_points,
                name = f"幅並行部開始_{i}",
            )
            straight_end_distance = None
            straight_end_point = None
            end_distance = None
            end_point = None
        else: # 中間での変化
            width_infos.extend([
                (base_distance-straight_x/2-slope_x, base_distance-straight_x/2, basic_below_flange_width, width),
                (base_distance-straight_x/2, base_distance+straight_x/2, width, width),
                (base_distance+straight_x/2, base_distance+straight_x/2+slope_x, width, basic_below_flange_width),
            ])
            start_distance = base_distance - straight_x/2 - slope_x
            start_point, _ = get_LCR_points_with_distance(
                this_distance=start_distance,
                distances=distances,
                top_flange_MG_points=top_flange_MG_points,
                name = f"幅変化開始_{i}",
            )
            straight_start_distance = base_distance - straight_x/2
            straight_start_point, _ = get_LCR_points_with_distance(
                this_distance=straight_start_distance,
                distances=distances,
                top_flange_MG_points=top_flange_MG_points,
                name = f"幅並行部開始_{i}",
            )
            straight_end_distance = base_distance + straight_x/2
            straight_end_point, _ = get_LCR_points_with_distance(
                this_distance=straight_end_distance,
                distances=distances,
                top_flange_MG_points=top_flange_MG_points,
                name = f"幅並行部終了_{i}",
            )
            end_distance = base_distance + straight_x/2 + slope_x
            end_point, _ = get_LCR_points_with_distance(
                this_distance=end_distance,
                distances=distances,
                top_flange_MG_points=top_flange_MG_points,
                name = f"幅変化終了_{i}",
            )
        pairs = [
            (start_point, start_distance),
            (straight_start_point, straight_start_distance),
            (straight_end_point, straight_end_distance),
            (end_point, end_distance),
        ]
        valid_pairs = [
            (p, d) for p, d in pairs
            if p is not None # ポイントがNoneのときはオフセットがちょうど0か距離と同じで、幅変化点が既存のトップフランジ点と重なっているため追加する必要がない
        ]
        additional_top_flange_MG_points.extend([p for p, _ in valid_pairs])
        additional_distances.extend([d for _, d in valid_pairs])
    additional_top_flange_MG_points, additional_distances = zip(*sorted(zip(additional_top_flange_MG_points, additional_distances), key=lambda x: x[1]))
    additional_top_flange_MG_points = list(additional_top_flange_MG_points)
    additional_distances = list(additional_distances)
    if len(width_infos) == 0:
        width_infos.append((0, distances[-1], basic_below_flange_width, basic_below_flange_width))
    if width_infos[0][0] > 0:
        width_infos.insert(0, (0, width_infos[0][0], basic_below_flange_width, width_infos[0][2]))
    if width_infos[-1][1] < distances[-1]:
        width_infos.append((width_infos[-1][1], distances[-1], width_infos[-1][3], basic_below_flange_width))
    width_infos = sorted(width_infos, key=lambda x: x[0])
    all_width_infos = []
    for i in range(len(width_infos)-1):
        this_info = width_infos[i]
        all_width_infos.append(this_info)
        next_info = width_infos[i+1]
        if this_info[1] < next_info[0]:
            all_width_infos.append((this_info[1], next_info[0], this_info[3], next_info[2]))
        elif this_info[1] > next_info[0]:
            raise ValueError(f"WidthChangeInfoの幅変化区間が重なっています。{this_info} {next_info}")
    all_width_infos.append(width_infos[-1])

    return additional_top_flange_MG_points, additional_distances, all_width_infos

def get_additional_top_flange_points_with_height(
    MG_info: MainGirderInfo,
    top_flange_MG_points: list[TopFlangePointInfo],
    distances: list[float],
) -> tuple[list[TopFlangePointInfo], list[float], list[tuple[float, float, float, float]]]:
    CG_names = [top_flange_MG_point.CG for top_flange_MG_point in top_flange_MG_points]
    basic_height = MG_info.basic_height

    height_infos = [] #(pre_distance, post_distance, pre_height, post_height)
    additional_top_flange_MG_points = top_flange_MG_points.copy()
    additional_distances = distances.copy()
    for i, height_change_info in enumerate(MG_info.height_change_infos):
        start_CG = height_change_info.start_CG
        start_offset = height_change_info.start_offset
        straight_start_CG = height_change_info.straight_start_CG
        straight_start_offset = height_change_info.straight_start_offset
        straight_end_CG = height_change_info.straight_end_CG
        straight_end_offset = height_change_info.straight_end_offset
        end_CG = height_change_info.end_CG
        end_offset = height_change_info.end_offset
        if pd.isna(straight_start_CG):
            raise ValueError("HeightChangeInfoのstraight_start_CGは必須項目です。")
        if pd.isna(straight_end_CG):
            raise ValueError("HeightChangeInfoのstraight_end_CGは必須項目です。")
        if straight_start_CG not in CG_names:
            raise ValueError(f"HeightChangeInfoのstraight_start_CG {straight_start_CG} がTopFlangePointInfoのCGに見つかりませんでした。{straight_start_CG} {CG_names}")
        if straight_end_CG not in CG_names:
            raise ValueError(f"HeightChangeInfoのstraight_end_CG {straight_end_CG} がTopFlangePointInfoのCGに見つかりませんでした。{straight_end_CG} {CG_names}")
        notna_CGs = [cg for cg in [start_CG, straight_start_CG, straight_end_CG, end_CG] if pd.notna(cg)]
        if not all(cg in CG_names for cg in notna_CGs):
            raise ValueError("HeightChangeInfoのCGのいずれかがTopFlangePointInfoのCGに見つかりませんでした。")
        height = height_change_info.height
        straight_start_base_CG_index = CG_names.index(straight_start_CG)
        straight_start_base_CG_distance = distances[straight_start_base_CG_index]
        straight_start_distance = straight_start_base_CG_distance + straight_start_offset
        straight_start_point, _ = get_LCR_points_with_distance(
            this_distance=straight_start_distance,
            distances=distances,
            top_flange_MG_points=top_flange_MG_points,
            name = f"高さ並行部開始_{i}",
        )
        straight_end_base_CG_index = CG_names.index(straight_end_CG)
        straight_end_base_CG_distance = distances[straight_end_base_CG_index]
        straight_end_distance = straight_end_base_CG_distance + straight_end_offset
        straight_end_point, _ = get_LCR_points_with_distance(
            this_distance=straight_end_distance,
            distances=distances,
            top_flange_MG_points=top_flange_MG_points,
            name = f"高さ並行部終了_{i}",
        )
        start_distance, start_point = None, None
        end_distance, end_point = None, None
        if pd.notna(start_CG):
            start_base_CG_index = CG_names.index(start_CG)
            start_base_CG_distance = distances[start_base_CG_index]
            start_distance = start_base_CG_distance + start_offset
            height_infos.append(
                (start_distance, straight_start_distance, basic_height, height),
            )
            start_point, _ = get_LCR_points_with_distance(
                this_distance=start_distance,
                distances=distances,
                top_flange_MG_points=top_flange_MG_points,
                name = f"高さ変化開始_{i}",
            )
        height_infos.append(
            (straight_start_distance, straight_end_distance, height, height),
        )
        if pd.notna(end_CG):
            end_base_CG_index = CG_names.index(end_CG)
            end_base_CG_distance = distances[end_base_CG_index]
            end_distance = end_base_CG_distance + end_offset
            height_infos.append(
                (straight_end_distance, end_distance, height, basic_height),
            )
            end_point, _ = get_LCR_points_with_distance(
                this_distance=end_distance,
                distances=distances,
                top_flange_MG_points=top_flange_MG_points,
                name = f"高さ変化終了_{i}",
            )

        pairs = [
            (start_point, start_distance),
            (straight_start_point, straight_start_distance),
            (straight_end_point, straight_end_distance),
            (end_point, end_distance),
        ]
        valid_pairs = [
            (p, d) for p, d in pairs
            if p is not None # ポイントがNoneのときはオフセットがちょうど0か距離と同じで、幅変化点が既存のトップフランジ点と重なっているため追加する必要がない
        ]
        additional_top_flange_MG_points.extend([p for p, _ in valid_pairs])
        additional_distances.extend([d for _, d in valid_pairs])
    additional_top_flange_MG_points, additional_distances = zip(*sorted(zip(additional_top_flange_MG_points, additional_distances), key=lambda x: x[1]))
    additional_top_flange_MG_points = list(additional_top_flange_MG_points)
    additional_distances = list(additional_distances)

    if len(height_infos) == 0:
        height_infos.append((0, distances[-1], basic_height, basic_height))
    if height_infos[0][0] > 0:
        height_infos.insert(0, (0, height_infos[0][0], basic_height, height_infos[0][2]))
    if height_infos[-1][1] < distances[-1]:
        height_infos.append((height_infos[-1][1], distances[-1], height_infos[-1][3], basic_height))
    height_infos = sorted(height_infos, key=lambda x: x[0])
    all_height_infos = []
    for i in range(len(height_infos)-1):
        this_info = height_infos[i]
        all_height_infos.append(this_info)
        next_info = height_infos[i+1]
        if this_info[1] < next_info[0]:
            all_height_infos.append((this_info[1], next_info[0], this_info[3], next_info[2]))
        elif this_info[1] > next_info[0]:
            raise ValueError("HeightChangeInfoの高さ変化区間が重なっています。")
    all_height_infos.append(height_infos[-1])
    return additional_top_flange_MG_points, additional_distances, all_height_infos

def get_block_points(
    MG_info: MainGirderInfo,
    top_flange_MG_points: list[TopFlangePointInfo],
    distances: list[float],
):
    CG_names = [top_flange_MG_point.CG for top_flange_MG_point in top_flange_MG_points]
    thickness_infos = [] #(pre_distance, post_distance, (top_thickness, bottom_thickness, web_thickness)) 擦り付けがないから。
    block_end_CG_names = []
    additional_top_flange_MG_points = top_flange_MG_points.copy()
    additional_distances = distances.copy()
    pre_distance = 0
    for i, block_info in enumerate(MG_info.block_infos):
        if i == len(MG_info.block_infos) - 1:
            continue # 最後の一つは位置が確定している
        base_CG = block_info.CG
        base_offset = block_info.CG_offset
        if pd.isna(base_CG):
            raise ValueError("BlockInfoのstart_CGは必須項目です。")
        if base_CG not in CG_names:
            raise ValueError(f"BlockInfoのstart_CG {base_CG} がMG_outer_pointsのCGに見つかりませんでした。{base_CG} {CG_names}")
        base_idx = CG_names.index(base_CG)
        base_distance = distances[base_idx]
        thickness_infos.append(
            (pre_distance, base_distance+base_offset, (block_info.top_flange_thickness, block_info.bottom_flange_thickness, block_info.web_thickness))
        )
        this_distance = base_distance + base_offset
        # this_distanceの前後のdistanceのMG_outer_pointを見つける
        if this_distance < distances[0] or this_distance > distances[-1]:
            raise ValueError(f"BlockInfoの位置がMGの範囲外です。{this_distance} {distances[0]} {distances[-1]}")
        block_end_point, CG_name = get_LCR_points_with_distance(
            this_distance=this_distance,
            distances=distances,
            top_flange_MG_points=top_flange_MG_points,
            name = f"ブロック終点_{i}",
        )
        block_end_CG_names.append(CG_name) 
        if block_end_point is None:
            continue
        block_end_point = TopFlangePointInfo(
            CG = CG_name,
            C = block_end_point.C,
            U = block_end_point.U,
            D = block_end_point.D,
        )
        additional_top_flange_MG_points.append(block_end_point)
        additional_distances.append(base_distance + base_offset)
        pre_distance = base_distance + base_offset
    
    last_block_info = MG_info.block_infos[-1]
    thickness_infos.append((pre_distance, distances[-1], (last_block_info.top_flange_thickness, last_block_info.bottom_flange_thickness, last_block_info.web_thickness)))
    block_end_CG_names.append(top_flange_MG_points[-1].CG) # 最後のブロックの終点はMGの終点と同じ位置なので、CGも同じになるはず。

    additional_top_flange_MG_points, additional_distances = zip(*sorted(zip(additional_top_flange_MG_points, additional_distances), key=lambda x: x[1]))
    additional_top_flange_MG_points = list(additional_top_flange_MG_points)
    additional_distances = list(additional_distances)
    return additional_top_flange_MG_points, additional_distances, thickness_infos, block_end_CG_names

def get_MG_outer_points(
    top_flange_MG_points: list[TopFlangePointInfo],
    distances: list[float],
    width_infos: list[tuple[float, float, float, float]],
    height_infos: list[tuple[float, float, float, float]],
) -> list[FlangePointInfo]:
    MG_outer_points = []
    for i, top_flange_MG_point in enumerate(top_flange_MG_points):
        CG = top_flange_MG_point.CG
        distance = distances[i]
        if i == len(top_flange_MG_points) - 1:
            width = width_infos[-1][3]
            height = height_infos[-1][3]
        else:
            width_info = next(wi for wi in width_infos if wi[0] <= distance < wi[1])
            pre_distance, post_distance, pre_width, post_width = width_info
            width = pre_width + (post_width - pre_width) * (distance - pre_distance) / (post_distance - pre_distance)
            height_info = next(hi for hi in height_infos if hi[0] <= distance < hi[1])
            pre_distance, post_distance, pre_height, post_height = height_info
            height = pre_height + (post_height - pre_height) * (distance - pre_distance) / (post_distance - pre_distance)
        
        # LCRが同一線上に並ぶように。
        top_flange_MG_point_in_line = TopFlangePointInfo(
            CG = CG,
            U=top_flange_MG_point.U,
            D=top_flange_MG_point.D,
            C=Point3D(
                x = (top_flange_MG_point.U.x + top_flange_MG_point.D.x)/2,
                y = (top_flange_MG_point.U.y + top_flange_MG_point.D.y)/2,
                z = (top_flange_MG_point.U.z + top_flange_MG_point.D.z)/2,
            )
        )
        bottom_C = Point3D(
            x = top_flange_MG_point_in_line.C.x,
            y = top_flange_MG_point_in_line.C.y,
            z = top_flange_MG_point_in_line.C.z - height,
        )
        rough_bottom_U = Point3D(
            x = top_flange_MG_point.U.x,
            y = top_flange_MG_point.U.y,
            z = top_flange_MG_point.U.z - height,
        )
        rough_bottom_D = Point3D(
            x = top_flange_MG_point.D.x,
            y = top_flange_MG_point.D.y,
            z = top_flange_MG_point.D.z - height,
        )
        bottom_U = get_point_by_xy_offset(
            point1 = bottom_C,
            point2 = rough_bottom_U,
            offset = width/2,
        )
        bottom_D = get_point_by_xy_offset(
            point1 = bottom_C,
            point2 = rough_bottom_D,
            offset = width/2,
        )
        
        MG_outer_points.append(FlangePointInfo(
            CG = CG,
            top = top_flange_MG_point_in_line,
            bottom = BottomFlangePointInfo(
                CG = CG,
                C = bottom_C,
                U = bottom_U,
                D = bottom_D,
            )
        ))
    return MG_outer_points 

def get_individual_MG_breps(
    MG_outer_points: list[FlangePointInfo],
    distances: list[float],
    thickness_infos: list[tuple[float, float, tuple[float, float, float]]],
    block_end_CG_names: list[str],
    MG_info: MainGirderInfo,
):
    MG_type = MG_info.MG_type
    bridge_name = MG_info.bridge_name
    MG_name = MG_info.MG_name
    web_offset = MG_info.web_offset
    MG_points_list = {}

    def get_top_bottom_MG_points(top_flange_points, bottom_flange_points, thickness_info):
        top_flange_thickness, bottom_flange_thickness, _ = thickness_info
        top_out_L_point = top_flange_points.U
        top_out_R_point = top_flange_points.D
        top_out_C_point = top_flange_points.C
        bottom_in_L_point = bottom_flange_points.U # 下逃げ
        bottom_in_R_point = bottom_flange_points.D
        bottom_in_C_point = bottom_flange_points.C
        top_in_L_point = Point3D(
            x = top_out_L_point.x,
            y = top_out_L_point.y,
            z = top_out_L_point.z - top_flange_thickness,
        )
        top_in_R_point = Point3D(
            x = top_out_R_point.x,
            y = top_out_R_point.y,
            z = top_out_R_point.z - top_flange_thickness,
        )
        bottom_out_L_point = Point3D(
            x = bottom_in_L_point.x,
            y = bottom_in_L_point.y,
            z = bottom_in_L_point.z - bottom_flange_thickness,
        )
        bottom_out_R_point = Point3D(
            x = bottom_in_R_point.x,
            y = bottom_in_R_point.y,
            z = bottom_in_R_point.z - bottom_flange_thickness,
        )
        top_in_C_point = Point3D(
            x = top_out_C_point.x,
            y = top_out_C_point.y,
            z = top_out_C_point.z - top_flange_thickness,
        )
        bottom_out_C_point = Point3D(
            x = bottom_in_C_point.x,
            y = bottom_in_C_point.y,
            z = bottom_in_C_point.z - bottom_flange_thickness,
        )
        return top_out_L_point, top_out_R_point, bottom_out_L_point, bottom_out_R_point, top_in_L_point, top_in_R_point, bottom_in_L_point, bottom_in_R_point, top_in_C_point, bottom_in_C_point, top_out_C_point, bottom_out_C_point
    
    def get_I_web_points(top_in_L_point, top_in_R_point, bottom_in_L_point, bottom_in_R_point, top_in_C_point, bottom_in_C_point, web_thickness):
        web_top_L_point = get_point_by_xy_offset(
            point1 = top_in_C_point,
            point2 = top_in_L_point,
            offset = web_thickness/2,
        )
        web_top_R_point = get_point_by_xy_offset(
            point1 = top_in_C_point,
            point2 = top_in_R_point,
            offset = web_thickness/2,
        )
        web_bottom_L_point = get_point_by_xy_offset(
            point1 = bottom_in_C_point,
            point2 = bottom_in_L_point,
            offset = web_thickness/2,
        )
        web_bottom_R_point = get_point_by_xy_offset(
            point1 = bottom_in_C_point,
            point2 = bottom_in_R_point,
            offset = web_thickness/2,
        )
        return web_top_L_point, web_top_R_point, web_bottom_L_point, web_bottom_R_point
    
    def get_box_web_points(top_in_L_point, top_in_R_point, bottom_in_L_point, bottom_in_R_point, top_in_C_point, bottom_in_C_point, web_thickness, web_offset):
        Lweb_top_L_point = get_point_by_xy_offset(
            point1 = top_in_C_point,
            point2 = top_in_L_point,
            offset = web_offset + web_thickness/2,
        )
        Lweb_top_R_point = get_point_by_xy_offset(
            point1 = top_in_C_point,
            point2 = top_in_L_point,
            offset = web_offset - web_thickness/2,
        )
        Lweb_bottom_L_point = get_point_by_xy_offset(
            point1 = bottom_in_C_point,
            point2 = bottom_in_L_point,
            offset = web_offset + web_thickness/2,
        )
        Lweb_bottom_R_point = get_point_by_xy_offset(
            point1 = bottom_in_C_point,
            point2 = bottom_in_L_point,
            offset = web_offset - web_thickness/2,
        )
        Rweb_top_L_point = get_point_by_xy_offset(
            point1 = top_in_C_point,
            point2 = top_in_R_point,
            offset = web_offset - web_thickness/2,
        )
        Rweb_top_R_point = get_point_by_xy_offset(
            point1 = top_in_C_point,
            point2 = top_in_R_point,
            offset = web_offset + web_thickness/2,
        )
        Rweb_bottom_L_point = get_point_by_xy_offset(
            point1 = bottom_in_C_point,
            point2 = bottom_in_R_point,
            offset = web_offset - web_thickness/2,
        )
        Rweb_bottom_R_point = get_point_by_xy_offset(
            point1 = bottom_in_C_point,
            point2 = bottom_in_R_point,
            offset = web_offset + web_thickness/2,
        )
        return Lweb_top_L_point, Lweb_top_R_point, Lweb_bottom_L_point, Lweb_bottom_R_point, Rweb_top_L_point, Rweb_top_R_point, Rweb_bottom_L_point, Rweb_bottom_R_point
    
    def get_MG_points(top_flange_points, bottom_flange_points, thickness_info, MG_type, web_offset):
        top_out_L_point, top_out_R_point, bottom_out_L_point, bottom_out_R_point, top_in_L_point, top_in_R_point, bottom_in_L_point, bottom_in_R_point, top_in_C_point, bottom_in_C_point, top_out_C_point, bottom_out_C_point = get_top_bottom_MG_points(top_flange_points, bottom_flange_points, thickness_info)
        if MG_type == "鈑桁":
            web_top_L_point, web_top_R_point, web_bottom_L_point, web_bottom_R_point = get_I_web_points(top_in_L_point, top_in_R_point, bottom_in_L_point, bottom_in_R_point, top_in_C_point, bottom_in_C_point, thickness_info[2])
            return [top_out_R_point, top_out_L_point, top_in_L_point, web_top_L_point, web_bottom_L_point, bottom_in_L_point, bottom_out_L_point, bottom_out_R_point, bottom_in_R_point, web_bottom_R_point, web_top_R_point, top_in_R_point]
        elif MG_type == "箱桁":
            Lweb_top_L_point, Lweb_top_R_point, Lweb_bottom_L_point, Lweb_bottom_R_point, Rweb_top_L_point, Rweb_top_R_point, Rweb_bottom_L_point, Rweb_bottom_R_point = get_box_web_points(top_in_L_point, top_in_R_point, bottom_in_L_point, bottom_in_R_point, top_in_C_point, bottom_in_C_point, thickness_info[2], web_offset)
            return (
                [top_out_C_point, top_out_L_point, top_in_L_point, Lweb_top_L_point, Lweb_bottom_L_point, bottom_in_L_point, bottom_out_L_point, bottom_out_C_point, bottom_in_C_point, Lweb_bottom_R_point, Lweb_top_R_point, top_in_C_point],
                [top_out_C_point, top_out_R_point, top_in_R_point, Rweb_top_R_point, Rweb_bottom_R_point, bottom_in_R_point, bottom_out_R_point, bottom_out_C_point, bottom_in_C_point, Rweb_bottom_L_point, Rweb_top_L_point, top_in_C_point]
            )
        
    def get_MG_point_info(MG_points, L_MG_points, R_MG_points, MG_type, thickness_info, CG_name):
        top_flange_thickness, bottom_flange_thickness, web_thickness = thickness_info
        if MG_type == "鈑桁":
            [top_out_R_point, top_out_L_point, top_in_L_point, web_top_L_point, web_bottom_L_point, bottom_in_L_point, bottom_out_L_point, bottom_out_R_point, bottom_in_R_point, web_bottom_R_point, web_top_R_point, top_in_R_point] = MG_points
        elif MG_type == "箱桁":
            [top_out_C_point, top_out_L_point, top_in_L_point, Lweb_top_L_point, Lweb_bottom_L_point, bottom_in_L_point, bottom_out_L_point, bottom_out_C_point, bottom_in_C_point, Lweb_bottom_R_point, Lweb_top_R_point, top_in_C_point] = L_MG_points
            [top_out_C_point, top_out_R_point, top_in_R_point, Rweb_top_R_point, Rweb_bottom_R_point, bottom_in_R_point, bottom_out_R_point, bottom_out_C_point, bottom_in_C_point, Rweb_bottom_L_point, Rweb_top_L_point, top_in_C_point] = R_MG_points
        return MainGirderPointInfo(
            CG_name=CG_name,
            top_flange_thickness=top_flange_thickness,
            bottom_flange_thickness=bottom_flange_thickness,
            web_thickness=web_thickness,
            I_points = IGirderInfo(
                top_out_R_point = top_out_R_point,
                top_out_L_point = top_out_L_point,
                top_in_L_point = top_in_L_point,
                web_top_L_point = web_top_L_point,
                web_bottom_L_point = web_bottom_L_point,
                bottom_in_L_point = bottom_in_L_point,
                bottom_out_L_point = bottom_out_L_point,
                bottom_out_R_point = bottom_out_R_point,
                bottom_in_R_point = bottom_in_R_point,
                web_bottom_R_point = web_bottom_R_point,
                web_top_R_point = web_top_R_point,
                top_in_R_point = top_in_R_point,
            ) if MG_type == "鈑桁" else None,
            Box_points = BoxGirderInfo(
                top_out_R_point = top_out_R_point,
                top_out_L_point = top_out_L_point,
                top_in_L_point = top_in_L_point,
                Lweb_top_L_point = Lweb_top_L_point,
                Lweb_bottom_L_point = Lweb_bottom_L_point,
                bottom_in_L_point = bottom_in_L_point,
                bottom_out_L_point = bottom_out_L_point,
                bottom_out_R_point = bottom_out_R_point,
                bottom_in_R_point = bottom_in_R_point,
                Rweb_bottom_R_point = Rweb_bottom_R_point,
                Rweb_top_R_point = Rweb_top_R_point,
                top_in_R_point = top_in_R_point,
                Rweb_top_L_point = Rweb_top_L_point,
                Lweb_top_R_point = Lweb_top_R_point,
                Lweb_bottom_R_point = Lweb_bottom_R_point,
                Rweb_bottom_L_point = Rweb_bottom_L_point,
            ) if MG_type == "箱桁" else None,
        )

        
    CG_names = [MG_outer_point.CG for MG_outer_point in MG_outer_points]
    block_end_CG_ids = [CG_names.index(cg) for cg in block_end_CG_names]
    MG_points_list = []
    MG_dict = {}
    for i in range(len(block_end_CG_ids)):
        block_num = i
        if i == 0:
            start_idx = 0
        else:
            start_idx = block_end_CG_ids[i-1]
        end_idx = block_end_CG_ids[i]
        start_distance = distances[start_idx]
        thickness_info_list = [ti for ti in thickness_infos if ti[0] == start_distance]
        if len(thickness_info_list) != 1:
            raise ValueError(f"Blockの開始位置 {start_distance} に対応する厚さ情報が見つからないか、複数見つかっています。{thickness_info_list}")
        thickness_info = thickness_info_list[0][2]
        breps = []
        for idx in range(start_idx, end_idx):
            this_MG_outer_point = MG_outer_points[idx]
            next_MG_outer_point = MG_outer_points[idx+1]
            this_MG_points = None
            this_L_MG_points = None
            this_R_MG_points = None
            next_MG_points = None
            next_L_MG_points = None
            next_R_MG_points = None
            if MG_type == "鈑桁":
                this_MG_points = get_MG_points(this_MG_outer_point.top, this_MG_outer_point.bottom, thickness_info, MG_type, web_offset)
                next_MG_points = get_MG_points(next_MG_outer_point.top, next_MG_outer_point.bottom, thickness_info, MG_type, web_offset)
                this_MG_crv = const_closed_polycurve_obj(this_MG_points)
                next_MG_crv = const_closed_polycurve_obj(next_MG_points)
                brep = const_srf_from_2crvs([this_MG_crv, next_MG_crv])
                breps.append(brep)
            elif MG_type == "箱桁":
                this_L_MG_points, this_R_MG_points = get_MG_points(this_MG_outer_point.top, this_MG_outer_point.bottom, thickness_info, MG_type, web_offset)
                next_L_MG_points, next_R_MG_points = get_MG_points(next_MG_outer_point.top, next_MG_outer_point.bottom, thickness_info, MG_type, web_offset)
                this_L_MG_crv = const_polycurve_obj(this_L_MG_points)
                next_L_MG_crv = const_polycurve_obj(next_L_MG_points)
                left_brep = const_srf_from_2crvs([this_L_MG_crv, next_L_MG_crv])
                this_R_MG_crv = const_polycurve_obj(this_R_MG_points)
                next_R_MG_crv = const_polycurve_obj(next_R_MG_points)
                right_brep = const_srf_from_2crvs([this_R_MG_crv, next_R_MG_crv])
                brep = join_breps_or_raise([left_brep, right_brep], context=f"{bridge_name} {MG_name} box girder block")
                breps.append(brep)
            
            # MG_points_dictを作成
            this_CG_name = this_MG_outer_point.CG
            MG_points_list.append(get_MG_point_info(this_MG_points, this_L_MG_points, this_R_MG_points, MG_type, thickness_info, this_CG_name))
            if idx == end_idx - 1: # ブロックの終点に対応するMGポイント情報も保存
                MG_points_list.append(get_MG_point_info(next_MG_points, next_L_MG_points, next_R_MG_points, MG_type, thickness_info, next_MG_outer_point.CG))
                
        brep = join_breps_or_raise(breps, context=f"{bridge_name} {MG_name} girder")
        brep = brep.CapPlanarHoles(0.01)
        MG_dict[block_num] = brep
    
    return MG_points_list, MG_dict

def get_each_MG(
    MG_info: MainGirderInfo,
    top_flange_MG_points: list[TopFlangePointInfo],
):
    additional_top_flange_MG_points_with_width, additional_distances_with_width, width_infos = get_additional_top_flange_points_with_width(
        MG_info = MG_info,
        top_flange_MG_points = top_flange_MG_points,
    )
    additional_top_flange_MG_points_with_height, additional_distances_with_height, height_infos = get_additional_top_flange_points_with_height(
        MG_info = MG_info,
        top_flange_MG_points = additional_top_flange_MG_points_with_width,
        distances = additional_distances_with_width,
    )
    additional_top_flange_MG_points_with_block, additional_distances_with_block, thickness_infos, block_end_CG_names = get_block_points(
        MG_info = MG_info,
        top_flange_MG_points = additional_top_flange_MG_points_with_height,
        distances = additional_distances_with_height,
    )
    MG_outer_points = get_MG_outer_points(
        top_flange_MG_points = additional_top_flange_MG_points_with_block,
        distances = additional_distances_with_block,
        width_infos = width_infos,
        height_infos = height_infos,
    )

    MG_points_list, MG_dict = get_individual_MG_breps(
        MG_outer_points = MG_outer_points,
        distances = additional_distances_with_block,
        thickness_infos = thickness_infos,
        block_end_CG_names = block_end_CG_names,
        MG_info = MG_info,
    )
    return MG_points_list, MG_dict



def main(initial_or_final: str, debug: bool = False):
    DIR = get_output_dir(initial_or_final)

    MG_infos = load_from_pickle(
        file_path = DIR / f"{Filenames.INPUT}_{Filenames.MG}.pickle",
    )
    top_flange_MG_points_infos = load_from_pickle(
        file_path = DIR / f"{Filenames.WORLD}_{Filenames.MG}_{Filenames.TOP}_{Filenames.POINTS}.pickle",
    )

    all_MG_points_dict = {}
    world_items_dict_for_bake = {}
    world_items_dict_for_bake_2 = {}

    if not debug:
        for MG_info in MG_infos:
            bridge_name = MG_info.bridge_name
            if bridge_name not in all_MG_points_dict:
                all_MG_points_dict[bridge_name] = {}
            if bridge_name not in world_items_dict_for_bake:
                world_items_dict_for_bake[bridge_name] = {}
            MG_name = MG_info.MG_name
            top_flange_MG_points = top_flange_MG_points_infos[bridge_name][MG_name]

            MG_points_list, MG_dict = get_each_MG(
                MG_info = MG_info,
                top_flange_MG_points = top_flange_MG_points,
            )
            all_MG_points_dict[bridge_name][MG_name] = MG_points_list
            world_items_dict_for_bake[bridge_name][MG_name] = MG_dict

        save_json_and_pickle(
            data = all_MG_points_dict,
            folder_path = DIR,
            name = f"{Filenames.WORLD}_{Filenames.MG}_{Filenames.POINTS}",
        )
        return get_keys_and_values_for_bake(world_items_dict_for_bake)

    else:
        points = []
        for MG_info in MG_infos:
            bridge_name = MG_info.bridge_name
            if bridge_name not in all_MG_points_dict:
                all_MG_points_dict[bridge_name] = {}
            if bridge_name not in world_items_dict_for_bake:
                world_items_dict_for_bake[bridge_name] = {}
            if bridge_name not in world_items_dict_for_bake_2:
                world_items_dict_for_bake_2[bridge_name] = {}
            MG_name = MG_info.MG_name
            print(f"Processing {bridge_name} {MG_name}...")
            top_flange_MG_points = top_flange_MG_points_infos[bridge_name][MG_name]

            MG_points_list, MG_dict = get_each_MG(
                MG_info = MG_info,
                top_flange_MG_points = top_flange_MG_points,
            )
            all_MG_points_dict[bridge_name][MG_name] = MG_points_list
            world_items_dict_for_bake[bridge_name][MG_name] = MG_dict

            for point_info in MG_points_list:
                I_points = point_info.I_points
                Box_points = point_info.Box_points
                if I_points is not None:
                    this_points = [getattr(I_points, f.name) for f in fields(I_points)]
                elif Box_points is not None:
                    this_points = [getattr(Box_points, f.name) for f in fields(Box_points)]
                points.extend(this_points)
            points = [const_point_obj(point) for point in points if point is not None]
                
        save_json_and_pickle(
            data = all_MG_points_dict,
            folder_path = DIR,
            name = f"{Filenames.WORLD}_{Filenames.MG}_{Filenames.POINTS}",
        )
        return get_keys_and_values_for_bake(world_items_dict_for_bake), points
    
if __name__ == "__main__":
    # points = main("initial", debug=True)
    (bake_keys, bake_objs), points = main("initial", debug=True)


