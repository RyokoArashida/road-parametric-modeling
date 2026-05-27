from typing import Optional

import pandas as pd

from my_project.config.file_names import Filenames
from my_project.config.paths import get_input_output_dirs
from my_project.config.schemas.shoe_schemas import (
    AnkerBoltInfo,
    CuboidInfo,
    DoubleCuboidInfo,
    FallProtectionInfo,
    OverhangingInfo,
    PlateInfo,
    PositionInfo,
    ShoeInfo,
    ShoeMainInfo,
    SteppedShapeInfo,
)
from my_project.config.schemas.superstructure_schemas import (
    CoordInfo,
)
from my_project.config.util_schemas import Point3D
from my_project.utils.io import load_from_pickle, read_file_to_df, save_json_and_pickle


def get_Point3D_from_row(df_row: pd.Series, point_key: str) -> Optional[Point3D]:
    if pd.isna(df_row[f"{point_key}_x"]) or pd.isna(df_row[f"{point_key}_y"]) or pd.isna(df_row[f"{point_key}_z"]):
        return None
    return Point3D(
        x = df_row[f"{point_key}_y"], # xとyは逆
        y = df_row[f"{point_key}_x"],
        z = df_row[f"{point_key}_z"],
    )

def get_indiv_shoe_info(
    df_row: pd.Series,
    coord_infos: list[CoordInfo],
) -> ShoeInfo:
    bridge_name = df_row["全体_全体_橋梁名"]
    MG_name = df_row["全体_全体_主桁名"]
    CG_name = df_row["全体_全体_横桁名"]
    shoe_name = f"{bridge_name}_{MG_name}_{CG_name}"
    substructure_name = df_row["全体_全体_下部工名"]
    coord_info_CG = next(filter(lambda c: c.name == CG_name, coord_infos))
    center_point = coord_info_CG.Points[MG_name]
    if center_point is None:
        raise ValueError(f"座標情報から支承中心点を取得できませんでした。bridge_name={bridge_name}, MG_name={MG_name}, CG_name={CG_name}, substructure_name={substructure_name}")
    angle = df_row["全体_全体_角度"]
    if pd.isna(df_row["台座_全体_x"]):
        base = None
    else:
        base_position = PositionInfo(
            center_x = False if pd.isna(df_row["台座_中心位置支承と一致_x"]) else True,
            center_y = False if pd.isna(df_row["台座_中心位置支承と一致_y"]) else True,
            near_edge_x = False if pd.isna(df_row["台座_端部位置支承側端部と一致_x"]) else True,
            near_edge_y = False if pd.isna(df_row["台座_端部位置支承側端部と一致_y"]) else True,
            far_edge_y = False if pd.isna(df_row["台座_端部位置逆側端部と一致_y"]) else True,
            Uedge_x_offset_from_center = float(df_row["台座_左端位置支承から_x"]) if not pd.isna(df_row["台座_左端位置支承から_x"]) else None,
            Nedge_y_offset_from_center = float(df_row["台座_下端位置支承から_y"]) if not pd.isna(df_row["台座_下端位置支承から_y"]) else None,
        )
        base = PlateInfo(
            x = float(df_row["台座_全体_x"]),
            y = float(df_row["台座_全体_y"]),
            height = float(df_row["台座_全体_厚さ"]),
            position = base_position,
        )
    other_position = PositionInfo(
        center_x = True,
        center_y = True,
        near_edge_x = False,
        near_edge_y = False,
        far_edge_y = False,
        Uedge_x_offset_from_center = None,
        Nedge_y_offset_from_center = None,
    )
    mortar = PlateInfo(
        x = float(df_row["モルタル_全体_x"]),
        y = float(df_row["モルタル_全体_y"]),
        height = float(df_row["モルタル_全体_厚さ"]),
        position = other_position,
    )
    base_plate = PlateInfo(
        x = float(df_row["ベースプレート_全体_x"]),
        y = float(df_row["ベースプレート_全体_y"]),
        height = float(df_row["ベースプレート_全体_厚さ"]),
        position = other_position,
    )
    bottom_plate = PlateInfo(
        x = float(df_row["下沓_全体_x"]),
        y = float(df_row["下沓_全体_y"]),
        height = float(df_row["下沓_全体_厚さ"]),
        position = other_position,
    )
    shoe = ShoeMainInfo(
        main_info=PlateInfo(
            x = float(df_row["支承_全体_x"]),
            y = float(df_row["支承_全体_y"]),
            height = float(df_row["支承_全体_厚さ"]),
            position = other_position,
        ),
        top_bottom_plates_height = float(df_row["支承_上下鋼板_厚さ"]),
        mid_plates_height = float(df_row["支承_補強鋼板_厚さ"]),
        mid_plates_num = int(df_row["支承_補強鋼板_枚数"]),
    )
    top_plate = PlateInfo(
        x = float(df_row["上沓_全体_x"]),
        y = float(df_row["上沓_全体_y"]),
        height = float(df_row["上沓_全体_厚さ"]),
        position = other_position,
    )
    anker_bolt = AnkerBoltInfo(
        count_x = int(df_row["アンカーボルト_本数_x"]),
        count_y = int(df_row["アンカーボルト_本数_y"]),
        diameter = float(df_row["アンカーボルト_全体_直径"]),
        length = float(df_row["アンカーボルト_全体_長さ"]),
        offset_x_list = [float(df_row[f"アンカーボルト_x離隔_{i}"]) for i in range(1, 5) if not pd.isna(df_row[f"アンカーボルト_x離隔_{i}"])],
        offset_y_list = [float(df_row[f"アンカーボルト_y離隔_{i}"]) for i in range(1, 5) if not pd.isna(df_row[f"アンカーボルト_y離隔_{i}"])],
    )
    sole_plate_gap_z = float(df_row["ソールプレート_全体_上面の路面からの下がり"]) if not pd.isna(df_row["ソールプレート_全体_上面の路面からの下がり"]) else None
    shoe_info = ShoeInfo(
        bridge_name = bridge_name,
        MG_name = MG_name,
        CG_name = CG_name,
        substructure_name = substructure_name,
        center_point = center_point,
        angle = angle,
        base = base,
        mortar = mortar,
        base_plate = base_plate,
        bottom_plate = bottom_plate,
        shoe = shoe,
        top_plate = top_plate,
        anker_bolt = anker_bolt,
        sole_plate_gap_z = sole_plate_gap_z,
        fall_protection_info=[], # 後で追加する
    )
    return shoe_info, shoe_name

def get_indiv_fall_protection_info(
    df_row: pd.Series,
) -> FallProtectionInfo:
    bridge_name = df_row["全体_全体_橋梁名"]
    MG_name = df_row["全体_全体_主桁名"]
    CG_name = df_row["全体_全体_横桁名"]
    shoe_name = f"{bridge_name}_{MG_name}_{CG_name}"
    position_info = PositionInfo(
        center_x = False if pd.isna(df_row["中心位置_支承と一致_x"]) else True,
        center_y = False if pd.isna(df_row["中心位置_支承と一致_y"]) else True,
        near_edge_x = False if pd.isna(df_row["端部位置_支承側端部と一致_x"]) else True,
        near_edge_y = False if pd.isna(df_row["端部位置_支承側端部と一致_y"]) else True,
        far_edge_y = False if pd.isna(df_row["端部位置_逆側端部と一致_y"]) else True,
        Uedge_x_offset_from_center = float(df_row["左端位置_支承から_x"]) if not pd.isna(df_row["左端位置_支承から_x"]) else None,
        Nedge_y_offset_from_center = float(df_row["下端位置_支承から_y"]) if not pd.isna(df_row["下端位置_支承から_y"]) else None,
    )
    fall_protection_type = df_row["全体_全体_タイプ"]
    print(shoe_name, fall_protection_type)
    if fall_protection_type == "直方体":
        cuboid = CuboidInfo(
            x = float(df_row["本体_1_x"]),
            y = float(df_row["本体_1_y"]),
            Uheight = float(df_row["本体_中心左端_高さ"]),
            Dheight = float(df_row["本体_中心右端_高さ"]),
        )
        double_cuboid = None
        stepped_shape = None
        overhanging = None
    elif fall_protection_type == "二直方体":
        cuboid = None
        double_cuboid = DoubleCuboidInfo(
            x1 = float(df_row["本体_1_x"]),
            y1 = float(df_row["本体_1_y"]),
            x2 = float(df_row["本体_2_x"]),
            y2 = float(df_row["本体_2_y"]),
            Uheight = float(df_row["本体_中心左端_高さ"]),
            Cheight = float(df_row["本体_中心切替_高さ"]),
            Dheight = float(df_row["本体_中心右端_高さ"]),
        )
        stepped_shape = None
        overhanging = None
    elif fall_protection_type == "段違い":
        cuboid = None
        double_cuboid = None
        stepped_shape = SteppedShapeInfo(
            x = float(df_row["本体_1_x"]),
            y = float(df_row["本体_1_y"]),
            Uheight = float(df_row["本体_中心左端_高さ"]),
            Dheight = float(df_row["本体_中心右端_高さ"]),
            step_y = float(df_row["本体_天端_y"]),
            step_height = float(df_row["本体_天端_高さ"]),
        )
        overhanging = None
    elif fall_protection_type == "張り出し":
        cuboid = None
        double_cuboid = None
        stepped_shape = None
        overhanging = OverhangingInfo(
            x = float(df_row["本体_1_x"]),
            y = float(df_row["本体_1_y"]),
            Uheight = float(df_row["本体_中心左端_高さ"]),
            Dheight = float(df_row["本体_中心右端_高さ"]),
            step_y = float(df_row["本体_天端_y"]),
            step_height = float(df_row["本体_天端_高さ"]),
            slope_y = float(df_row["本体_隅切り_y"]),
            slope_height = float(df_row["本体_隅切り_高さ"]),
        )
    else:
        raise ValueError(f"不正なタイプ: {fall_protection_type}")
    fall_protection_info = FallProtectionInfo(
        position_info=position_info,
        fall_protection_type = fall_protection_type,
        cuboid = cuboid,
        double_cuboid = double_cuboid,
        stepped_shape = stepped_shape,
        overhanging = overhanging,
    )
    return fall_protection_info, shoe_name

    
def main(initial_or_final: str) -> None:
    input_dir, output_dir = get_input_output_dirs(initial_or_final)

    shoe_df = read_file_to_df(
        file_path = input_dir / "支承諸元.xlsx",
        sheet_name = "支承",
        header=[0,1,2]
    )

    fall_protection_df = read_file_to_df(
        file_path = input_dir / "支承諸元.xlsx",
        sheet_name = "変位防止",
        header=[0,1,2]
    )

    coord_dict = load_from_pickle(
        file_path = output_dir / f"{Filenames.INPUT}_{Filenames.SUPERSTRUCTURE}_{Filenames.COMMON}.pickle",
    )

    all_shoe_infos_dict_wo_fall_protection = {}
    all_fall_protection_infos_dict = {}
    all_shoe_infos = list()

    for _, shoe_row in shoe_df.iterrows():
        bridge_name = shoe_row["全体_全体_橋梁名"]
        coord_info = coord_dict[bridge_name]
        shoe_info_wo_fall_protection, shoe_name = get_indiv_shoe_info(
            df_row = shoe_row,
            coord_infos = coord_info,
        )
        all_shoe_infos_dict_wo_fall_protection[shoe_name] = shoe_info_wo_fall_protection
    
    for _, fall_protection_row in fall_protection_df.iterrows():
        bridge_name = fall_protection_row["全体_全体_橋梁名"]
        coord_info = coord_dict[bridge_name]
        fall_protection_info, shoe_name = get_indiv_fall_protection_info(
            df_row = fall_protection_row,
        )
        if shoe_name not in all_fall_protection_infos_dict:
            all_fall_protection_infos_dict[shoe_name] = [fall_protection_info]
        else:
            all_fall_protection_infos_dict[shoe_name].append(fall_protection_info)
    
    for shoe_name, shoe_info_wo_fall_protection in all_shoe_infos_dict_wo_fall_protection.items():
        fall_protection_info = all_fall_protection_infos_dict.get(shoe_name, [])
        shoe_info = ShoeInfo(
            bridge_name = shoe_info_wo_fall_protection.bridge_name,
            MG_name = shoe_info_wo_fall_protection.MG_name,
            CG_name = shoe_info_wo_fall_protection.CG_name,
            substructure_name = shoe_info_wo_fall_protection.substructure_name,
            center_point = shoe_info_wo_fall_protection.center_point,
            angle = shoe_info_wo_fall_protection.angle,
            base = shoe_info_wo_fall_protection.base,
            mortar = shoe_info_wo_fall_protection.mortar,
            base_plate = shoe_info_wo_fall_protection.base_plate,
            bottom_plate = shoe_info_wo_fall_protection.bottom_plate,
            shoe = shoe_info_wo_fall_protection.shoe,
            top_plate = shoe_info_wo_fall_protection.top_plate,
            anker_bolt = shoe_info_wo_fall_protection.anker_bolt,
            sole_plate_gap_z = shoe_info_wo_fall_protection.sole_plate_gap_z,
            fall_protection_info = fall_protection_info,
        )
        all_shoe_infos.append(shoe_info)

    save_json_and_pickle(
        data = all_shoe_infos,
        folder_path = output_dir,
        name = f"{Filenames.INPUT}_{Filenames.SHOE}",
    )

if __name__ == "__main__":
    main("initial")


