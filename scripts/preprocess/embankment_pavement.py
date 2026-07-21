import re
from typing import Optional

import pandas as pd

from my_project.config.file_names import Filenames
from my_project.config.paths import get_input_output_dirs
from my_project.config.schemas.embankment_pavement_schemas import (
    EdgeSideInfo,
    EdgeStructureInfo,
    EmbankmentPaveInfo,
    PavementCrossSlopeInfo,
    WallInterferenceInfo,
    WallTargetInfo,
)
from my_project.config.util_schemas import MonoSlope
from my_project.utils.coordinates import get_STA_from_STA_info
from my_project.utils.io import read_file_to_df, save_json_and_pickle


def clean_optional(value):
    if pd.isna(value):
        return None
    return value


def clean_optional_str(value):
    value = clean_optional(value)
    if value is None:
        return None
    return str(value)


def clean_optional_int(value):
    value = clean_optional(value)
    if value is None:
        return None
    return int(value)


def get_optional_row_value(row: pd.Series, key: str):
    if key not in row.index:
        return None
    return clean_optional(row[key])


def structure_type_to_code(value):
    value = clean_optional_str(value)
    if value is None:
        return None
    if value == "橋台":
        return "abutment"
    raise ValueError(f"Unknown structure type: {value}")


def target_type_to_code(value):
    value = clean_optional_str(value)
    if value is None:
        return None
    mapping = {
        "端部": "edge",
        "並行部": "parallel",
    }
    if value in mapping:
        return mapping[value]
    raise ValueError(f"Unknown wall target type: {value}")


def target_edge_name_to_code(value):
    value = clean_optional_str(value)
    if value is None:
        return None
    mapping = {
        "起点側": "start",
        "終点側": "end",
    }
    if value in mapping:
        return mapping[value]
    raise ValueError(f"Unknown wall target edge name: {value}")


def target_parallel_name_to_code(value):
    value = clean_optional_str(value)
    if value is None:
        return None
    mapping = {
        "上り": "U",
        "下り": "D",
        "上り線": "U",
        "下り線": "D",
    }
    if value in mapping:
        return mapping[value]
    raise ValueError(f"Unknown wall target parallel name: {value}")


def split_target_side_name(target_type: Optional[str], value) -> tuple[Optional[str], Optional[str]]:
    if target_type is None:
        return None, None
    if target_type == "edge":
        return target_edge_name_to_code(value), None
    if target_type == "parallel":
        return None, target_parallel_name_to_code(value)
    raise ValueError(f"Unknown wall target type: {target_type}")


def target_position_to_code(value):
    value = clean_optional_str(value)
    if value is None:
        return None
    mapping = {
        "法尻": "toe",
        "法肩": "shoulder",
    }
    if value in mapping:
        return mapping[value]
    raise ValueError(f"Unknown wall target position: {value}")


def get_embankment_excel_path(input_dir):
    candidates = [
        input_dir / "土工部土工線形.xlsx",
        input_dir / "土工部横断線形.xlsx",
    ]
    for path in candidates:
        if path.exists():
            return path
    raise FileNotFoundError(f"Embankment alignment Excel was not found: {candidates}")


def get_edge_structure(row: pd.Series, prefix: str) -> Optional[EdgeStructureInfo]:
    structure_type = structure_type_to_code(row[f"{prefix}_全体_種類"])
    structure_name = clean_optional_str(row[f"{prefix}_全体_名称"])
    if structure_type is None and structure_name is None:
        return None
    if structure_type is None or structure_name is None:
        raise ValueError(f"Incomplete edge structure info: {prefix}, {row.to_dict()}")
    return EdgeStructureInfo(
        structure_type=structure_type,
        structure_name=structure_name,
    )


def get_edge_slope_dict(row: pd.Series, prefix: str, side: str) -> dict[int, float]:
    slope_dict = {}
    col_prefix = f"{prefix}_勾配_{side}"
    for col in row.index:
        if not str(col).startswith(col_prefix):
            continue
        value = clean_optional(row[col])
        if value is None:
            continue
        suffix = str(col).removeprefix(col_prefix)
        match = re.fullmatch(r"\d+", suffix)
        if match is None:
            continue
        tier = int(suffix)
        slope_dict[tier] = float(value)
    return slope_dict


def get_edge_side(row: pd.Series, prefix: str) -> EdgeSideInfo:
    U_slopes = get_edge_slope_dict(row, prefix, "上り線")
    D_slopes = get_edge_slope_dict(row, prefix, "下り線")
    return EdgeSideInfo(
        structure=get_edge_structure(row, prefix),
        U_slope=U_slopes.get(1),
        D_slope=D_slopes.get(1),
        U_slopes=U_slopes,
        D_slopes=D_slopes,
    )


def get_target_info(row: pd.Series, prefix: str) -> Optional[WallTargetInfo]:
    target_name = clean_optional_str(row[f"{prefix}_対象名称"])
    target_num = clean_optional_int(row[f"{prefix}_対象番号"])
    target_type = target_type_to_code(row[f"{prefix}_対象区分"])
    target_edge_name, target_parallel_name = split_target_side_name(target_type, row[f"{prefix}_対象名称.1"])
    target_tier = clean_optional_int(row[f"{prefix}_対象盛土段"])
    target_position = target_position_to_code(row[f"{prefix}_対象盛土位置"])
    if all(v is None for v in [target_name, target_num, target_type, target_edge_name, target_parallel_name, target_tier, target_position]):
        return None
    if target_name is None or target_num is None or target_type is None:
        raise ValueError(f"Incomplete wall target info: {prefix}, {row.to_dict()}")
    return WallTargetInfo(
        target_type=target_type,
        target_edge_name=target_edge_name,
        target_parallel_name=target_parallel_name,
        target_tier=target_tier,
        target_position=target_position,
    )


def get_target_key(row: pd.Series, prefix: str) -> Optional[tuple[str, int]]:
    target_name = clean_optional_str(row[f"{prefix}_対象名称"])
    target_num = clean_optional_int(row[f"{prefix}_対象番号"])
    target_type = clean_optional_str(row[f"{prefix}_対象区分"])
    target_edge_name = clean_optional_str(row[f"{prefix}_対象名称.1"])
    target_tier = clean_optional_int(row[f"{prefix}_対象盛土段"])
    target_position = clean_optional_str(row[f"{prefix}_対象盛土位置"])
    if all(v is None for v in [target_name, target_num, target_type, target_edge_name, target_tier, target_position]):
        return None
    if target_name is None or target_num is None:
        raise ValueError(f"Incomplete wall target key: {prefix}, {row.to_dict()}")
    return get_key(target_name, target_num)


def get_key(name: str, num: int) -> tuple[str, int]:
    return name, int(num)


def get_edge_info_dict(edge_df: pd.DataFrame) -> dict[tuple[str, int], tuple[EdgeSideInfo, EdgeSideInfo]]:
    edge_info_dict = {}
    for _, row in edge_df.iterrows():
        name = clean_optional_str(row["全体_全体_名称"])
        num = clean_optional_int(row["全体_全体_番号"])
        if name is None and num is None:
            continue
        if name is None or num is None:
            raise ValueError(f"Incomplete edge info target: {row.to_dict()}")
        edge_info_dict[get_key(name, num)] = (
            get_edge_side(row, "起点側"),
            get_edge_side(row, "終点側"),
        )
    return edge_info_dict


def get_wall_interference_dict(wall_df: pd.DataFrame) -> dict[tuple[str, int], list[WallInterferenceInfo]]:
    interference_dict: dict[tuple[str, int], list[WallInterferenceInfo]] = {}
    wall_df = wall_df[wall_df["全体_大名称"] != "大名称"]
    for _, row in wall_df.iterrows():
        wall_info = WallInterferenceInfo(
            wall_main_name=row["全体_大名称"],
            wall_name=row["全体_小名称"],
            berm=get_target_info(row, "小段"),
            top=get_target_info(row, "上点"),
            bottom=get_target_info(row, "下点"),
        )
        target_infos = [info for info in [wall_info.berm, wall_info.top, wall_info.bottom] if info is not None]
        if not target_infos:
            continue
        keys = {
            key for key in [
                get_target_key(row, "小段"),
                get_target_key(row, "上点"),
                get_target_key(row, "下点"),
            ]
            if key is not None
        }
        if len(keys) != 1:
            raise ValueError(f"Wall interference points refer to multiple embankments: {row.to_dict()}")
        key = next(iter(keys))
        interference_dict.setdefault(key, []).append(wall_info)
    return interference_dict


def get_cross_slope_info_dict(slope_info_df: pd.DataFrame) -> dict[str, list[PavementCrossSlopeInfo]]:
    slope_info_dict: dict[str, list[PavementCrossSlopeInfo]] = {}
    for _, row in slope_info_df.iterrows():
        name = clean_optional_str(row["名称"])
        if name is None:
            continue
        if pd.isna(row["測点大"]) or pd.isna(row["測点小"]):
            continue
        slope_info_dict.setdefault(name, []).append(
            PavementCrossSlopeInfo(
                STA=get_STA_from_STA_info(row["測点大"], row["測点小"]),
                slope=MonoSlope(row["横断勾配"]),
            )
        )
    return {
        name: sorted(infos, key=lambda info: info.STA)
        for name, infos in slope_info_dict.items()
    }


def get_indiv_info_from_row(
    row: pd.Series,
    edge_info_dict: dict[tuple[str, int], tuple[EdgeSideInfo, EdgeSideInfo]],
    wall_interference_dict: dict[tuple[str, int], list[WallInterferenceInfo]],
    cross_slope_info_dict: dict[str, list[PavementCrossSlopeInfo]],
) -> EmbankmentPaveInfo:
    name = row["全体_名称"]
    num = int(row["全体_番号"])
    key = get_key(name, num)
    start_edge, end_edge = edge_info_dict.get(key, (None, None))
    return EmbankmentPaveInfo(
        name=name,
        num=num,
        points=None,
        width=get_optional_row_value(row, "形状_幅"),
        thickness=row["形状_厚"],
        slope=MonoSlope(row["形状_勾配"]),
        cross_slope_infos=cross_slope_info_dict.get(name, []),
        start_edge=start_edge,
        end_edge=end_edge,
        wall_interferences=wall_interference_dict.get(key, []),
    )


def main(initial_or_final: str) -> None:
    input_dir, output_dir = get_input_output_dirs(initial_or_final)
    embankment_excel_path = get_embankment_excel_path(input_dir)

    embankment_target_df = read_file_to_df(
        file_path=embankment_excel_path,
        sheet_name="土工部対象一覧",
        header=[0, 1],
    )
    edge_info_df = read_file_to_df(
        file_path=embankment_excel_path,
        sheet_name="端部情報一覧",
        header=[0, 1, 2],
    )
    wall_interference_df = read_file_to_df(
        file_path=embankment_excel_path,
        sheet_name="擁壁干渉一覧",
        header=[0, 1],
    )
    slope_info_df = read_file_to_df(
        file_path=embankment_excel_path,
        sheet_name="舗装横断勾配",
    )
    edge_info_dict = get_edge_info_dict(edge_info_df)
    wall_interference_dict = get_wall_interference_dict(wall_interference_df)
    cross_slope_info_dict = get_cross_slope_info_dict(slope_info_df)

    embankment_pave_info = [
        get_indiv_info_from_row(
            row=row,
            edge_info_dict=edge_info_dict,
            wall_interference_dict=wall_interference_dict,
            cross_slope_info_dict=cross_slope_info_dict,
        )
        for _, row in embankment_target_df.iterrows()
        if clean_optional_str(row["全体_名称"]) is not None
        and clean_optional_int(row["全体_番号"]) is not None
    ]

    save_json_and_pickle(
        data=embankment_pave_info,
        folder_path=output_dir,
        name=f"{Filenames.INPUT}_{Filenames.EMBANKMENT}_{Filenames.PAVEMENT}",
    )


if __name__ == "__main__":
    main("initial")
