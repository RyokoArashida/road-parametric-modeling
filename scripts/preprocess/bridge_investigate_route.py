

import pandas as pd

from my_project.config.file_names import Filenames
from my_project.config.paths import (
    FINAL_INPUT_DIR,
    FINAL_OUTPUT_DIR,
    INITIAL_INPUT_DIR,
    INITIAL_OUTPUT_DIR,
)
from my_project.config.schemas.bridge_investigate_route_schemas import (
    CrossingInfo,
    MainInfo,
    RoutePoint,
    Sizeinfo,
)
from my_project.config.schemas.superstructure_schemas import (
    CoordInfo,
)
from my_project.utils.geometry.points import get_polyline_info_from_coord_info
from my_project.utils.io import load_from_pickle, read_file_to_df, save_json_and_pickle


def add_target_point_name(
    target_point_name_dict: dict[str, set[str]],
    bridge_name: str,
    point_name: str,
) -> None:
    if pd.isna(bridge_name) or pd.isna(point_name):
        return
    if bridge_name not in target_point_name_dict:
        target_point_name_dict[bridge_name] = set()
    target_point_name_dict[bridge_name].add(point_name)


def add_target_point_alias(
    output_name_by_point_name_dict: dict[str, dict[str, str]],
    bridge_name: str,
    point_name: str,
    output_name: str,
) -> None:
    if pd.isna(bridge_name) or pd.isna(point_name) or pd.isna(output_name):
        return
    if bridge_name not in output_name_by_point_name_dict:
        output_name_by_point_name_dict[bridge_name] = {}
    output_name_by_point_name_dict[bridge_name][point_name] = output_name

def build_target_point_polyline_dict(
    coord_dict: dict[str, list[CoordInfo]],
    orthogonal_basis_df: pd.DataFrame,
    main_df: pd.DataFrame,
) -> dict:
    target_point_name_dict = {}
    output_name_by_point_name_dict = {}
    target_specs = [
        (main_df, "全体_橋梁名", "基準主桁_名称"),
    ]
    for target_df, bridge_col, point_col in target_specs:
        for _, row in target_df.iterrows():
            add_target_point_name(
                target_point_name_dict = target_point_name_dict,
                bridge_name = row[bridge_col],
                point_name = row[point_col],
            )

    for _, row in orthogonal_basis_df.iterrows():
        add_target_point_name(
            target_point_name_dict=target_point_name_dict,
            bridge_name=row["橋梁名"],
            point_name=row["中心"],
        )
        add_target_point_alias(
            output_name_by_point_name_dict=output_name_by_point_name_dict,
            bridge_name=row["橋梁名"],
            point_name=row["中心"],
            output_name="CL",
        )

    return {
        bridge_name: get_polyline_info_from_coord_info(
            coord_infos = coord_dict[bridge_name],
            target_point_name_list = target_point_name_list,
            output_name_by_point_name = output_name_by_point_name_dict.get(bridge_name),
        )
        for bridge_name, target_point_name_list in target_point_name_dict.items()
    }

def get_base_CL_name_dict(
    orthogonal_basis_df: pd.DataFrame,
) -> dict[str, str]:
    base_CL_name_dict = {}
    for _, row in orthogonal_basis_df.iterrows():
        base_CL_name_dict[row["橋梁名"]] = row["中心"]
    return base_CL_name_dict

def get_size_info_dict(
    size_df: pd.DataFrame,
) -> dict[str, Sizeinfo]:
    size_info_dict = {}
    for _, row in size_df.iterrows():
        size_info_dict[row["ID"]] = Sizeinfo(
            width=row["幅"],
            height=row["高さ"],
            thickness=row["厚さ"],
        )
    return size_info_dict

def get_crossing_info_dict(
    crossing_df: pd.DataFrame,
    size_info_dict: dict[str, Sizeinfo],
) -> dict[str, CrossingInfo]:
    crossing_info_dict = {}
    for _, row in crossing_df.iterrows():
        size_info = size_info_dict[row["寸法_タイプ"]]
        crossing_info_dict[row["全体_橋梁名"]] = CrossingInfo(
            side="plus", # 仮
            size_info=size_info,
            length=0, # 仮
            height_offset=row["床版上面から検査路下面_落ち"],
        )
    return crossing_info_dict

def get_main_route_info(
    row: pd.Series,
    size_info_dict: dict[str, Sizeinfo],
    crossing_info_dict: dict[str, CrossingInfo],
    base_CL_name_dict: dict[str, str],
) -> MainInfo:
    bridge_name = row["全体_橋梁名"]
    route_name = row["全体_検査路名"]
    size_info = size_info_dict[row["寸法_タイプ"]]
    base_MG = row["基準主桁_名称"]

    start_point = RoutePoint(
        x_offset=row["始点_x控え"],
        y_base_CG=row["始点_y横桁名"],
        y_offset=row["始点_y控え"],
        z_offset=row["始点_床版上面から検査路下面落ち"],
    )
    end_point = RoutePoint(
        x_offset=row["終点_x控え"],
        y_base_CG=row["終点_y横桁名"],
        y_offset=row["終点_y控え"],
        z_offset=row["終点_床版上面から検査路下面落ち"],
    )

    start_crossing = None
    end_crossing = None
    if not pd.isna(row["横行検査路_始点長さ"]):
        crossing_info = crossing_info_dict[bridge_name] # 無かったらエラー
        start_crossing = CrossingInfo(
            side = row["横行検査路_向き"],
            size_info=crossing_info.size_info,
            length=row["横行検査路_始点長さ"],
            height_offset=crossing_info.height_offset,
        )
    if not pd.isna(row["横行検査路_終点長さ"]):
        crossing_info = crossing_info_dict[bridge_name] # 無かったらエラー
        end_crossing = CrossingInfo(
            side = row["横行検査路_向き"],
            size_info=crossing_info.size_info,
            length=row["横行検査路_終点長さ"],
            height_offset=crossing_info.height_offset,
        )
    
    base_CL = base_CL_name_dict[bridge_name] # 無かったらエラー

    return MainInfo(
        bridge_name=bridge_name,
        route_name=route_name,
        size_info=size_info,
        base_MG=base_MG,
        base_CL=base_CL,
        start_point=start_point,
        end_point=end_point,
        start_crossing=start_crossing,
        end_crossing=end_crossing,
    )

def main(initial_or_final: str) -> None:
    if initial_or_final == "initial":
        input_dir = INITIAL_INPUT_DIR
        output_dir = INITIAL_OUTPUT_DIR
    elif initial_or_final == "final":
        input_dir = FINAL_INPUT_DIR
        output_dir = FINAL_OUTPUT_DIR

    route_excel_path = input_dir / "橋梁検査路諸元.xlsx"

    orthogonal_basis_df = read_file_to_df(
        file_path = route_excel_path,
        sheet_name = "直交面の基準",
    )

    size_df = read_file_to_df(
        file_path = route_excel_path,
        sheet_name = "寸法一覧",
    )

    main_df = read_file_to_df(
        file_path = route_excel_path,
        sheet_name = "主検査路",
        header=[0,1]
    )

    crossing_df = read_file_to_df(
        file_path = route_excel_path,
        sheet_name = "横行検査路",
        header=[0,1]
    )

    coord_dict = load_from_pickle(
        file_path = output_dir / f"{Filenames.INPUT}_{Filenames.SUPERSTRUCTURE}_{Filenames.COMMON}.pickle",
    )

    # まずcoord情報を整理
    target_point_name_dict = build_target_point_polyline_dict(
        coord_dict = coord_dict,
        orthogonal_basis_df = orthogonal_basis_df,
        main_df = main_df,
    )

    size_info_dict = get_size_info_dict(size_df)
    crossing_info_dict = get_crossing_info_dict(crossing_df, size_info_dict)
    base_CL_name_dict = get_base_CL_name_dict(orthogonal_basis_df)

    main_route_info_dict = {}
    for _, row in main_df.iterrows():
        main_info = get_main_route_info(
            row = row,
            size_info_dict = size_info_dict,
            crossing_info_dict = crossing_info_dict,
            base_CL_name_dict = base_CL_name_dict,
        )
        main_route_info_dict[(main_info.bridge_name, main_info.route_name)] = main_info

    save_json_and_pickle(
        data = main_route_info_dict,
        folder_path = output_dir,
        name = f"{Filenames.INPUT}_{Filenames.INVESTIGATE_ROUTE}_{Filenames.MAIN}",
    )

    save_json_and_pickle(
        data = target_point_name_dict,
        folder_path = output_dir,
        name = f"{Filenames.INPUT}_{Filenames.INVESTIGATE_ROUTE}_{Filenames.POINTS}",
    )

if __name__ == "__main__":
    main("initial")
