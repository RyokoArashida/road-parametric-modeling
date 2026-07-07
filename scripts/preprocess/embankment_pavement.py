
import pandas as pd

from my_project.config.file_names import Filenames
from my_project.config.paths import get_input_output_dirs
from my_project.config.schemas.embankment_pavement_schemas import (
    EdgeStructureInfo,
    EmbankmentPaveInfo,
    PointsInfo,
)
from my_project.config.util_schemas import MonoSlope
from my_project.utils.io import load_from_pickle, read_file_to_df, save_json_and_pickle


def get_indiv_info_from_row(row: pd.Series, edge_points_dict: dict) -> EmbankmentPaveInfo:
    name = row["全体_名称"]
    num = int(row["全体_番号"])
    edge_key = f"{name}_{num - 1}"
    edge_points = edge_points_dict[edge_key]
    if row["境界構造物_起点側種類"] is not None:
        if row["境界構造物_起点側種類"] == "橋台":
            row["境界構造物_起点側種類"] = "abutment"
        else:
            raise ValueError(f"Unknown structure type: {row['境界構造物_起点側種類']}")
    if row["境界構造物_終点側種類"] is not None:
        if row["境界構造物_終点側種類"] == "橋台":
            row["境界構造物_終点側種類"] = "abutment"
        else:
            raise ValueError(f"Unknown structure type: {row['境界構造物_終点側種類']}")
    return EmbankmentPaveInfo(
        name=name,
        num=num,
        points=PointsInfo(
            STAs=edge_points["STAs"],
            Upoint=edge_points["U_points"],
            Dpoint=edge_points["D_points"],
        ),
        thickness=row["形状_厚"],
        slope=MonoSlope(row["形状_勾配"]),
        start_edge_structure=EdgeStructureInfo(
            structure_type=row["境界構造物_起点側種類"],
            structure_name=row["境界構造物_起点側名称"],
        ),
        end_edge_structure=EdgeStructureInfo(
            structure_type=row["境界構造物_終点側種類"],
            structure_name=row["境界構造物_終点側名称"],
        )
    )



def main(initial_or_final: str) -> None:
    input_dir, output_dir = get_input_output_dirs(initial_or_final)

    embankment_pave_excel_path = input_dir / "土工部舗装横断線形.xlsx"

    embankment_pave_master_df = read_file_to_df(
        file_path = embankment_pave_excel_path,
        sheet_name = "土工部舗装対象一覧",
        header = [0,1]
    )

    edge_points_dict = load_from_pickle(
        file_path=output_dir / f"{Filenames.ROAD}_{Filenames.EDGE}_{Filenames.POINTS}.pickle",
    )

    embankment_pave_info = []
    for _, row in embankment_pave_master_df.iterrows():
        info = get_indiv_info_from_row(row, edge_points_dict)
        embankment_pave_info.append(info)
        

    save_json_and_pickle(
        data = embankment_pave_info,
        folder_path = output_dir,
        name = f"{Filenames.INPUT}_{Filenames.EMBANKMENT}_{Filenames.PAVEMENT}"
    )


if __name__ == "__main__":
    main("initial")
