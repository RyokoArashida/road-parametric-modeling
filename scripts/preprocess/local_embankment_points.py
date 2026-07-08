import pandas as pd

from my_project.config.file_names import Filenames
from my_project.config.paths import (
    get_input_Rhino_dir,
    get_output_dir,
)
from my_project.config.schemas.embankment_schemas import (
    CorrespondingPointsInfo,
    CrossSectionInfo,
    EdgeCrossSectionInfo,
    EdgePoints,
    EdgeStructureInfo,
    LocalTopBottomPointInfo,
)
from my_project.config.util_schemas import Point3D
from my_project.utils.coordinates import get_STA_from_STA_info
from my_project.utils.io import load_from_pickle, read_file_to_df, save_json_and_pickle


def clean_optional_name(value):
    if pd.isna(value):
        return None
    return str(value)


def get_info_UD(
    embankment_df: pd.DataFrame,
    wall_df: pd.DataFrame,
    tier_num: int,
):
    tier_num = int(tier_num)
    points = []
    for tier in range(1, tier_num + 1):
        top_point = None
        bottom_point = None
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
        if top_point is None or bottom_point is None:
            raise ValueError(f"Missing embankment top or bottom point: tier={tier}")
        points.append(LocalTopBottomPointInfo(top=top_point, bottom=bottom_point))

    if len(wall_df) > 0:
        wall_tier_num = int(max(wall_df["擁壁番号"].unique()))
        wall_points = []
        wall_positions = []
        is_wall_only = []
        wall_names = []
        for tier in range(1, wall_tier_num + 1):
            top_point = None
            bottom_point = None
            wall_tier_df = wall_df[wall_df["擁壁番号"] == tier]
            wall_positions.append(wall_tier_df["段番号"].iloc[0])
            is_wall_only.append(wall_tier_df["擁壁段区分"].iloc[0] == "擁壁だけの段")
            wall_names.append(clean_optional_name(wall_tier_df["擁壁名前"].iloc[0]))
            for _, row in wall_tier_df.iterrows():
                point = Point3D(
                    x=row["X"],
                    y=row["Y"],
                    z=row["Z"],
                )
                if row["点種"] == "外側上端":
                    top_point = point
                elif row["点種"] == "外側下端（地表面高）":
                    bottom_point = point
            if top_point is None or bottom_point is None:
                raise ValueError(f"Missing wall top or bottom point: tier={tier}")
            wall_points.append(LocalTopBottomPointInfo(top=top_point, bottom=bottom_point))
    else:
        wall_points = None
        wall_positions = None
        is_wall_only = None
        wall_names = None

    return EdgePoints(
        points=points,
        wall_points=wall_points,
        wall_positions=wall_positions,
        is_wall_only=is_wall_only,
        wall_names=wall_names,
    )


def get_indiv_local_embankment_info(df: pd.DataFrame) -> tuple[str, list[CrossSectionInfo]]:
    name = df["共通名前"].iloc[0]
    df["STA"] = df.apply(lambda row: get_STA_from_STA_info(row["STA大"], row["STA小"]), axis=1)
    df = df.sort_values(by="STA")
    STA_groups = df.groupby("STA")
    infos = []
    for STA, group_df in STA_groups:
        UP_group = group_df[group_df["線側"] == "上り線"]
        DOWN_group = group_df[group_df["線側"] == "下り線"]
        UP_tier_num = max(UP_group["段番号"].unique())
        DOWN_tier_num = max(DOWN_group["段番号"].unique())
        UP_embankment_df = UP_group[UP_group["種別"] == "盛土"]
        DOWN_embankment_df = DOWN_group[DOWN_group["種別"] == "盛土"]
        UP_wall_df = UP_group[UP_group["種別"] == "擁壁"]
        DOWN_wall_df = DOWN_group[DOWN_group["種別"] == "擁壁"]
        infos.append(
            CrossSectionInfo(
                STA=STA,
                U_points=get_info_UD(UP_embankment_df, UP_wall_df, UP_tier_num),
                D_points=get_info_UD(DOWN_embankment_df, DOWN_wall_df, DOWN_tier_num),
            )
        )
    return name, infos


def get_indiv_abut_edge_info(
    df: pd.DataFrame,
    world_abut_points: dict[str, dict],
) -> tuple[str, EdgePoints, EdgePoints, list[CorrespondingPointsInfo], list[CorrespondingPointsInfo]]:
    name = df["共通名前"].iloc[0]
    embankment_df = df[df["種別"] == "盛土"]
    wall_df = df[df["種別"] == "擁壁"]
    U_embankment_df = embankment_df[embankment_df["線側"] == "上り線"]
    D_embankment_df = embankment_df[embankment_df["線側"] == "下り線"]
    U_wall_df = wall_df[wall_df["線側"] == "上り線"]
    D_wall_df = wall_df[wall_df["線側"] == "下り線"]
    UP_tier_num = max(U_embankment_df["段番号"].unique())
    DOWN_tier_num = max(D_embankment_df["段番号"].unique())
    U_points = get_info_UD(U_embankment_df, U_wall_df, UP_tier_num)
    D_points = get_info_UD(D_embankment_df, D_wall_df, DOWN_tier_num)

    U_ref_df = df[(df["線側"] == "上り線") & (df["種別"] == "アバット")]
    D_ref_df = df[(df["線側"] == "下り線") & (df["種別"] == "アバット")]
    U_wing_soil_top = world_abut_points["wing_dict"]["U_wing_top_points"]["UN"]
    D_wing_soil_top = world_abut_points["wing_dict"]["D_wing_top_points"]["DN"]
    U_footing_bridge = world_abut_points["footing_dict"]["footing_top_points"]["U_bridge"]
    D_footing_bridge = world_abut_points["footing_dict"]["footing_top_points"]["D_bridge"]
    U_footing_soil = world_abut_points["footing_dict"]["footing_top_points"]["U_soil"]
    D_footing_soil = world_abut_points["footing_dict"]["footing_top_points"]["D_soil"]

    def get_ref_points(ref_df: pd.DataFrame, UD: str) -> list[CorrespondingPointsInfo]:
        ref_points = []
        for _, row in ref_df.iterrows():
            local_point = Point3D(
                x=row["X"],
                y=row["Y"],
                z=row["Z"],
            )
            point_name = row["点種"]
            if point_name == "ウイング先の上点":
                world_point = U_wing_soil_top if UD == "U" else D_wing_soil_top
            elif point_name == "フーチングの橋梁側上点":
                world_point = U_footing_bridge if UD == "U" else D_footing_bridge
            elif point_name == "フーチングの盛り土側上点":
                world_point = U_footing_soil if UD == "U" else D_footing_soil
            else:
                raise ValueError(f"Unknown point type: {point_name}")
            ref_points.append(CorrespondingPointsInfo(local=local_point, world=world_point))
        return ref_points

    U_ref_points = get_ref_points(U_ref_df, "U")
    D_ref_points = get_ref_points(D_ref_df, "D")
    return name, U_points, D_points, U_ref_points, D_ref_points


def main(initial_or_final: str) -> None:
    input_rhino_dir = get_input_Rhino_dir(initial_or_final)
    output_dir = get_output_dir(initial_or_final)
    embankment_files = [
        f for f in input_rhino_dir.glob("*.csv")
        if Filenames.EMBANKMENT in f.name
    ]
    abut_embankment_files = [
        f for f in embankment_files
        if "abut" in f.name.lower()
    ]
    embankment_files = [
        f for f in embankment_files
        if "abut" not in f.name.lower()
    ]

    local_embankment_points_dict = {}
    for file_path in embankment_files:
        name, indiv_info = get_indiv_local_embankment_info(read_file_to_df(file_path=file_path))
        local_embankment_points_dict[name] = indiv_info

    world_abut_points_dict = load_from_pickle(output_dir / f"{Filenames.WORLD}_{Filenames.ABUT}_{Filenames.POINTS}.pickle")
    embankment_pave_info = load_from_pickle(output_dir / f"{Filenames.INPUT}_{Filenames.EMBANKMENT}_{Filenames.PAVEMENT}.pickle")
    abut_edge_info_dict = {}
    for file_path in abut_embankment_files:
        df = read_file_to_df(file_path=file_path)
        name = df["共通名前"].iloc[0]
        abut_edge_info_dict[name] = get_indiv_abut_edge_info(df, world_abut_points_dict[name])

    local_abut_embankment_points_dict = {}
    for pavement_info in embankment_pave_info:
        start_edge_structure = pavement_info.start_edge_structure
        end_edge_structure = pavement_info.end_edge_structure
        if start_edge_structure is None or end_edge_structure is None:
            continue
        if start_edge_structure.structure_type != "abutment" or end_edge_structure.structure_type != "abutment":
            continue

        start_name = start_edge_structure.structure_name
        end_name = end_edge_structure.structure_name
        _, start_U_points, start_D_points, start_U_refs, start_D_refs = abut_edge_info_dict[start_name]
        _, end_U_points, end_D_points, end_U_refs, end_D_refs = abut_edge_info_dict[end_name]
        local_abut_embankment_points_dict[f"{pavement_info.name}_{pavement_info.num}"] = EdgeStructureInfo(
            start_section=EdgeCrossSectionInfo(
                U_points=start_U_points,
                D_points=start_D_points,
                U_ref_points=start_U_refs,
                D_ref_points=start_D_refs,
            ),
            end_section=EdgeCrossSectionInfo(
                U_points=end_U_points,
                D_points=end_D_points,
                U_ref_points=end_U_refs,
                D_ref_points=end_D_refs,
            ),
        )

    save_json_and_pickle(
        data=local_embankment_points_dict,
        folder_path=output_dir,
        name=f"{Filenames.INPUT}_{Filenames.LOCAL}_{Filenames.EMBANKMENT}_{Filenames.POINTS}",
    )
    save_json_and_pickle(
        data=local_abut_embankment_points_dict,
        folder_path=output_dir,
        name=f"{Filenames.INPUT}_{Filenames.LOCAL}_{Filenames.ABUT}_{Filenames.EMBANKMENT}_{Filenames.POINTS}",
    )


if __name__ == "__main__":
    main(initial_or_final="initial")
