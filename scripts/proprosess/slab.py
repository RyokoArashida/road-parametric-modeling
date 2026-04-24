from typing import Optional

import pandas as pd

from my_project.config.file_names import Filenames
from my_project.config.paths import (
    FINAL_INPUT_DIR,
    FINAL_OUTPUT_DIR,
    INITIAL_INPUT_DIR,
    INITIAL_OUTPUT_DIR,
)
from my_project.config.schemas.slab_schemas import (
    BottomSurfaceInfo,
    CommonHeightInfo,
    CommonWidthInfo,
    EmergencyLaneInfo,
    MainGirderTopPointInfo,
    SlabInfo,
    SlabPointInfo,
)
from my_project.config.schemas.superstructure_schemas import (
    CoordInfo,
    CrossGirderOffsetInfo,
)
from my_project.config.util_schemas import (
    Point3D,
)
from my_project.utils.io import load_from_pickle, read_file_to_df, save_json_and_pickle


def get_Point3D_from_row(df_row: pd.Series, point_key: str) -> Optional[Point3D]:
    if pd.isna(df_row[f"{point_key}_x"]) or pd.isna(df_row[f"{point_key}_y"]) or pd.isna(df_row[f"{point_key}_z"]):
        return None
    return Point3D(
        x = df_row[f"{point_key}_y"], # xとyは逆
        y = df_row[f"{point_key}_x"],
        z = df_row[f"{point_key}_z"],
    )

def get_indiv_slab_info(
    df_row: pd.Series,
    emergency_lane_df_for_bridge: pd.DataFrame,
    bottom_surface_df_for_bridge: pd.DataFrame,
    barrier_row: pd.Series,
    coord_infos: list[CoordInfo],
) -> SlabInfo:
    bridge_name = df_row["橋梁"]
    num = df_row["番号"]
    L2_key = df_row["L2"]
    R2_key = df_row["R2"]
    CL_key = df_row["CL"]
    start_cross_girder_key = df_row["開始横桁"]
    end_cross_girder_key = df_row["終了横桁"]
    barrier_type = df_row["壁高欄タイプ"]
    if pd.isna(start_cross_girder_key):
        start_cross_girder_key = coord_infos[0].name
    if pd.isna(end_cross_girder_key):
        end_cross_girder_key = coord_infos[-1].name
    start_idx = next(i for i, c in enumerate(coord_infos) if c.name == start_cross_girder_key)
    end_idx = next(i for i, c in enumerate(coord_infos) if c.name == end_cross_girder_key)    
    points = []
    for i in range(start_idx, end_idx+1):
        cross_girder_name = coord_infos[i].name
        if i != start_idx and i != end_idx and "GE" in cross_girder_name:
            continue # 開始・終了横桁以外のGEはスキップ（床版をカットする単位にならない。）
        frame_2D = coord_infos[i].UDframe2D
        slope = coord_infos[i].UDslope
        point_dict = coord_infos[i].Points
        if CL_key in point_dict and point_dict[CL_key] is not None:
            CL_point = point_dict[CL_key]
        else:
            raise ValueError(f"{bridge_name}の{coord_infos[i].name}にCLの点が見つかりません")
        if L2_key in point_dict and point_dict[L2_key] is not None:
            L2_point = point_dict[L2_key]
        else:
            raise ValueError(f"{bridge_name}の{coord_infos[i].name}にL2の点が見つかりません")
        if R2_key in point_dict and point_dict[R2_key] is not None:
            R2_point = point_dict[R2_key]
        else:
            raise ValueError(f"{bridge_name}の{coord_infos[i].name}にR2の点が見つかりません")
        girders = df_row["主桁"].split(",")
        girder_keys = [
            key for key in point_dict.keys()
            if key.endswith(tuple(girders))
        ]
        main_girder_points = []
        for girder_key in girder_keys:
            if girder_key in point_dict and point_dict[girder_key] is not None:
                main_girder_points.append(
                    MainGirderTopPointInfo(
                        name = girder_key,
                        center = point_dict[girder_key],
                        U_edge = None,
                        D_edge = None,
                    )
                )
        # Lに近い方からソート
        distances_to_L2 = [((p.center.x - L2_point.x)**2 + (p.center.y - L2_point.y)**2)**0.5 for p in main_girder_points]
        main_girder_points = [p for _, p in sorted(zip(distances_to_L2, main_girder_points), key=lambda x: x[0])]
        point_info = SlabPointInfo(
            name = cross_girder_name,
            CL = CL_point,
            L2 = L2_point,
            R2 = R2_point,
            UDframe2D = frame_2D,
            UDslope = slope,
            main_girder_points = main_girder_points,
        )
        points.append(point_info)

    height_info = CommonHeightInfo(
        pavement= df_row["舗装高さ"],
        edge = df_row["端高さ"],
        girder_above = df_row["桁上高さ"],
    )

    width_info = CommonWidthInfo(
        girder_flange = df_row["桁上フランジ幅"],
        edge_offset = barrier_row["水切り幅"],
    )

    emergency_lane_info = []
    for _, emergency_lane_row in emergency_lane_df_for_bridge.iterrows():
        emergency_lane_info.append(
            EmergencyLaneInfo(
                LR = emergency_lane_row["LR"],
                start_offset = CrossGirderOffsetInfo(
                    name=emergency_lane_row["非常駐車帯開始横桁"],
                    offset_y=emergency_lane_row["非常駐車帯開始横桁からの距離"],
                ),
                taper_length_N = emergency_lane_row["擦り付け手前"],
                length = emergency_lane_row["並行"],
                teper_length_T = emergency_lane_row["擦り付け奥"],
                width = emergency_lane_row["非常駐車帯拡幅"],
        )
    )

    bottom_surface_info = []
    for _, bottom_surface_row in bottom_surface_df_for_bridge.iterrows():
        start_cross_girder = bottom_surface_row["開始横桁"] if not pd.isna(bottom_surface_row["開始横桁"]) else points[0].name
        start_cross_girder_offset = bottom_surface_row["開始横桁から距離"] if not pd.isna(bottom_surface_row["開始横桁から距離"]) else 0.0
        end_cross_girder = bottom_surface_row["終了横桁"] if not pd.isna(bottom_surface_row["終了横桁"]) else points[-1].name
        end_cross_girder_offset = bottom_surface_row["終了横桁から距離"] if not pd.isna(bottom_surface_row["終了横桁から距離"]) else 0.0
        
        
        bottom_surface_info.append(
            BottomSurfaceInfo(
                start_offset = CrossGirderOffsetInfo(
                    name=start_cross_girder,
                    offset_y=start_cross_girder_offset,
                ),
                end_offset = CrossGirderOffsetInfo(
                    name=end_cross_girder,
                    offset_y=end_cross_girder_offset,
                ),
                slope_width = bottom_surface_row["断面擦付幅"],
                center_height = bottom_surface_row["中央高さ"],
        )
    )
    return SlabInfo(
        name = bridge_name,
        num = num,
        point_infos= points,
        height = height_info,
        width = width_info,
        emergency_lane = emergency_lane_info,
        bottom_surface = bottom_surface_info,
        barrier_type = barrier_type,
    )


    
def main(initial_or_final: str) -> None:
    if initial_or_final == "initial":
        input_dir = INITIAL_INPUT_DIR
        output_dir = INITIAL_OUTPUT_DIR
    elif initial_or_final == "final":
        input_dir = FINAL_INPUT_DIR
        output_dir = FINAL_OUTPUT_DIR

    common_df = read_file_to_df(
        file_path = input_dir / "床版諸元.xlsx",
        sheet_name = "床版共通"
    )

    emergency_lane_df = read_file_to_df(
        file_path = input_dir / "床版諸元.xlsx",
        sheet_name = "非常駐車帯"
    )

    bottom_surface_df = read_file_to_df(
        file_path = input_dir / "床版諸元.xlsx",
        sheet_name = "床版下面"
    )

    barrier_df = read_file_to_df(
        file_path = input_dir / "床版諸元.xlsx",
        sheet_name = "壁高欄共通"
    )

    coord_dict = load_from_pickle(
        file_path = output_dir / f"{Filenames.INPUT}_{Filenames.SUPERSTRUCTURE}_{Filenames.COMMON}.pickle",
    )

    all_slab_infos = list()
    for _, common_row in common_df.iterrows():
        name = common_row["橋梁"]
        coord_info = coord_dict[name]
        num = common_row["番号"]
        emergency_lane_df_for_bridge = emergency_lane_df[(emergency_lane_df["橋梁"] == name) & (emergency_lane_df["番号"] == num)]
        bottom_surface_df_for_bridge = bottom_surface_df[(bottom_surface_df["橋梁"] == name) & (bottom_surface_df["番号"] == num)]
        barrier_type = common_row["壁高欄タイプ"]
        barrier_row = barrier_df[barrier_df["橋梁"] == barrier_type].iloc[0]
        slab_info = get_indiv_slab_info(
            df_row = common_row,
            emergency_lane_df_for_bridge = emergency_lane_df_for_bridge,
            bottom_surface_df_for_bridge = bottom_surface_df_for_bridge,
            barrier_row = barrier_row,
            coord_infos = coord_info,
        )
        all_slab_infos.append(slab_info)
        
    save_json_and_pickle(
        data = all_slab_infos,
        folder_path = output_dir,
        name = f"{Filenames.INPUT}_{Filenames.SLAB}",
    )

if __name__ == "__main__":
    main("initial")


