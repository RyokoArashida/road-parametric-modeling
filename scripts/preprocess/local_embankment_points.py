import pandas as pd

from my_project.config.file_names import Filenames
from my_project.config.paths import (
    get_input_Rhino_dir,
    get_output_dir,
)
from my_project.config.schemas.embankment_schemas import (
    CrossSectionInfo,
    EdgePoints,
    LocalTopBottomPointInfo,
)
from my_project.config.util_schemas import Point3D
from my_project.utils.coordinates import get_STA_from_STA_info
from my_project.utils.io import read_file_to_df, save_json_and_pickle


def get_indiv_local_embankment_info(df: pd.DataFrame) -> tuple[str, list[CrossSectionInfo]]:
    name = df["共通名前"].iloc[0]
    df["STA"] = df.apply(lambda row: get_STA_from_STA_info(row["STA大"], row["STA小"]), axis=1)
    # STAでソートする
    df = df.sort_values(by="STA")
    # STAでグループ化する。
    STA_groups = df.groupby("STA")
    infos = []
    for group in STA_groups:
        STA, group_df = group
        UP_group = group_df[group_df["線側"] == "上り線"]
        DOWN_group = group_df[group_df["線側"] == "下り線"]
        UP_tier_num = max(UP_group["段番号"].unique())
        DOWN_tier_num = max(DOWN_group["段番号"].unique())
        UP_embankment_df = UP_group[UP_group["種別"] == "盛土"]
        DOWN_embankment_df = DOWN_group[DOWN_group["種別"] == "盛土"]
        UP_wall_df = UP_group[UP_group["種別"] == "擁壁"]
        DOWN_wall_df = DOWN_group[DOWN_group["種別"] == "擁壁"]
        U_points = []
        D_points = []
        def get_info_UD(
            embankment_df: pd.DataFrame,
            wall_df: pd.DataFrame,
            tier_num: int,
        ):
            points = []
            for tier in range(1, tier_num + 1):
                embankment_tier_df = embankment_df[embankment_df["段番号"] == tier]
                for _, row in embankment_tier_df.iterrows():
                    point = Point3D(
                        x=row["X"],
                        y=row["Y"],
                        z=row["Z"],
                    )
                    if row["点種"] == "法肩":
                        top_point = point
                    elif row["点種"] == "法尻":
                        bottom_point = point
                point_info = LocalTopBottomPointInfo(
                    top=top_point,
                    bottom=bottom_point,
                ) #どちらかが無ければエラーになる。
                points.append(point_info)
            if len(wall_df) > 0:
                wall_tier_num = max(wall_df["擁壁番号"].unique())
                wall_points = []
                wall_positions = []
                is_wall_only = []
                for tier in range(1, wall_tier_num + 1):
                    wall_tier_df = wall_df[wall_df["擁壁番号"] == tier]
                    wall_positions.append(wall_tier_df["段番号"].iloc[0])
                    is_wall_only.append(wall_tier_df["擁壁段区分"].iloc[0] == "擁壁だけの段")
                    for _, row in wall_tier_df.iterrows():
                        point = Point3D(
                            x=row["X"],
                            y=row["Y"],
                            z=row["Z"],
                        )
                        if row["点種"] == "法肩":
                            top_point = point
                        elif row["点種"] == "法尻":
                            bottom_point = point
                    point_info = LocalTopBottomPointInfo(
                        top=top_point,
                        bottom=bottom_point,
                    )
                    wall_points.append(point_info)
            else:
                wall_points = None
                wall_positions = None
                is_wall_only = None
            edge_points = EdgePoints(
                points=points,
                wall_points=wall_points,
                wall_positions=wall_positions,
                is_wall_only=is_wall_only,
            )
            return edge_points
        U_points = get_info_UD(UP_embankment_df, UP_wall_df, UP_tier_num)
        D_points = get_info_UD(DOWN_embankment_df, DOWN_wall_df, DOWN_tier_num)
        cross_section_info = CrossSectionInfo(
            STA=STA,
            U_points=U_points,
            D_points=D_points,
        )
        infos.append(cross_section_info)
    return name, infos

def main(initial_or_final: str) -> None:
    input_rhino_dir = get_input_Rhino_dir(initial_or_final)
    output_dir = get_output_dir(initial_or_final)
    # filenamesのEMBANKMENTが含まれるファイルを取得する
    embankment_files = [f for f in input_rhino_dir.glob("*.csv") if Filenames.EMBANKMENT in f.name]
    dfs = [
        read_file_to_df(file_path=f) for f in embankment_files
    ]
    local_embankment_points_dict = {}
    for df in dfs:
        name, indiv_info = get_indiv_local_embankment_info(df)
        local_embankment_points_dict[name] = indiv_info
    
    save_json_and_pickle(
        data = local_embankment_points_dict,
        folder_path = output_dir,
        name = f"{Filenames.INPUT}_{Filenames.LOCAL}_{Filenames.EMBANKMENT}_{Filenames.POINTS}"
    )


if __name__ == "__main__":
    main(initial_or_final="initial")