import pandas as pd

from my_project.config.file_names import Filenames
from my_project.config.paths import (
    FINAL_INPUT_DIR,
    FINAL_OUTPUT_DIR,
    INITIAL_INPUT_DIR,
    INITIAL_OUTPUT_DIR,
)
from my_project.config.schemas.cross_girder_schemas import MainGirderPointInfo_IO
from my_project.config.schemas.I_Box_joint_schemas import (
    BoxPointsInfo,
    IBoxJointFlangeInfo,
    IBoxJointInfo,
    PlatePointsInfo,
)
from my_project.utils.io import load_from_pickle, read_file_to_df, save_json_and_pickle


def get_indiv_joint_info(
    df_row: pd.Series,
    MG_point_IO_dict: dict[str, MainGirderPointInfo_IO],
) -> IBoxJointInfo:

    I_bridge_name = df_row["全体_鈑桁側_橋梁名"]
    I_CG_name = df_row["全体_鈑桁側_横桁名"]
    Box_bridge_name = df_row["全体_箱桁側_橋梁名"]
    Box_CG_name = df_row["全体_箱桁側_横桁名"]
    inner_MG_name = df_row["全体_主桁_内側"]
    outer_MG_name = df_row["全体_主桁_外側"]
    all_Plate_I_MG_points = MG_point_IO_dict[I_bridge_name][inner_MG_name]
    all_Plate_O_MG_points = MG_point_IO_dict[I_bridge_name][outer_MG_name]
    all_Box_I_MG_points = MG_point_IO_dict[Box_bridge_name][inner_MG_name]
    all_Box_O_MG_points = MG_point_IO_dict[Box_bridge_name][outer_MG_name]

    Plate_I_MG_points = next(MG_point_info for MG_point_info in all_Plate_I_MG_points if MG_point_info.CG_name == I_CG_name)
    Plate_O_MG_points = next(MG_point_info for MG_point_info in all_Plate_O_MG_points if MG_point_info.CG_name == I_CG_name)
    Box_I_MG_points = next(MG_point_info for MG_point_info in all_Box_I_MG_points if MG_point_info.CG_name == Box_CG_name)
    Box_O_MG_points = next(MG_point_info for MG_point_info in all_Box_O_MG_points if MG_point_info.CG_name == Box_CG_name)

    Plate_O_MG_points_O = PlatePointsInfo(
        top_flange_thickness = Plate_O_MG_points.top_flange_thickness,
        bottom_flange_thickness = Plate_O_MG_points.bottom_flange_thickness,
        top_out = Plate_O_MG_points.I_points.top_out_O_point,
        top_in = Plate_O_MG_points.I_points.top_in_O_point,
        web_top = Plate_O_MG_points.I_points.web_top_O_point,
        web_bottom = Plate_O_MG_points.I_points.web_bottom_O_point,
        bottom_in = Plate_O_MG_points.I_points.bottom_in_O_point,
        bottom_out = Plate_O_MG_points.I_points.bottom_out_O_point,
    )
    Plate_O_MG_points_I = PlatePointsInfo(
        top_flange_thickness = Plate_O_MG_points.top_flange_thickness,
        bottom_flange_thickness = Plate_O_MG_points.bottom_flange_thickness,
        top_out = Plate_O_MG_points.I_points.top_out_I_point,
        top_in = Plate_O_MG_points.I_points.top_in_I_point,
        web_top = Plate_O_MG_points.I_points.web_top_I_point,
        web_bottom = Plate_O_MG_points.I_points.web_bottom_I_point,
        bottom_in = Plate_O_MG_points.I_points.bottom_in_I_point,
        bottom_out = Plate_O_MG_points.I_points.bottom_out_I_point,
    )
    Plate_I_MG_points_O = PlatePointsInfo(
        top_flange_thickness = Plate_I_MG_points.top_flange_thickness,
        bottom_flange_thickness = Plate_I_MG_points.bottom_flange_thickness,
        top_out = Plate_I_MG_points.I_points.top_out_I_point, # I側は左右対称で考えるとOとI逆転
        top_in = Plate_I_MG_points.I_points.top_in_I_point,
        web_top = Plate_I_MG_points.I_points.web_top_I_point,
        web_bottom = Plate_I_MG_points.I_points.web_bottom_I_point,
        bottom_in = Plate_I_MG_points.I_points.bottom_in_I_point,
        bottom_out = Plate_I_MG_points.I_points.bottom_out_I_point,
    )
    Plate_I_MG_points_I = PlatePointsInfo(
        top_flange_thickness = Plate_I_MG_points.top_flange_thickness,
        bottom_flange_thickness = Plate_I_MG_points.bottom_flange_thickness,
        top_out = Plate_I_MG_points.I_points.top_out_O_point, # I側は左右対称で考えるとOとI逆転
        top_in = Plate_I_MG_points.I_points.top_in_O_point,
        web_top = Plate_I_MG_points.I_points.web_top_O_point,
        web_bottom = Plate_I_MG_points.I_points.web_bottom_O_point,
        bottom_in = Plate_I_MG_points.I_points.bottom_in_O_point,
        bottom_out = Plate_I_MG_points.I_points.bottom_out_O_point,
    )
    Box_O_MG_points_O = BoxPointsInfo(
        top_flange_thickness = Box_O_MG_points.top_flange_thickness,
        bottom_flange_thickness = Box_O_MG_points.bottom_flange_thickness,
        top_out = Box_O_MG_points.Box_points.top_out_O_point,
        top_in = Box_O_MG_points.Box_points.top_in_O_point,
        web_top_out = Box_O_MG_points.Box_points.Oweb_top_O_point,
        web_bottom_out= Box_O_MG_points.Box_points.Oweb_bottom_O_point,
        web_top_in = Box_O_MG_points.Box_points.Oweb_top_I_point,
        web_bottom_in = Box_O_MG_points.Box_points.Oweb_bottom_I_point,
        bottom_in = Box_O_MG_points.Box_points.bottom_in_O_point,
        bottom_out = Box_O_MG_points.Box_points.bottom_out_O_point,
    )
    Box_O_MG_points_I = BoxPointsInfo(
        top_flange_thickness = Box_O_MG_points.top_flange_thickness,
        bottom_flange_thickness = Box_O_MG_points.bottom_flange_thickness,
        top_out = Box_O_MG_points.Box_points.top_out_I_point,
        top_in = Box_O_MG_points.Box_points.top_in_I_point,
        web_top_out = Box_O_MG_points.Box_points.Iweb_top_I_point,
        web_bottom_out= Box_O_MG_points.Box_points.Iweb_bottom_I_point,
        web_top_in = Box_O_MG_points.Box_points.Iweb_top_O_point,
        web_bottom_in= Box_O_MG_points.Box_points.Iweb_bottom_O_point,
        bottom_in = Box_O_MG_points.Box_points.bottom_in_I_point,
        bottom_out = Box_O_MG_points.Box_points.bottom_out_I_point,
    )
    Box_I_MG_points_O = BoxPointsInfo(
        top_flange_thickness = Box_I_MG_points.top_flange_thickness,
        bottom_flange_thickness = Box_I_MG_points.bottom_flange_thickness,
        top_out = Box_I_MG_points.Box_points.top_out_I_point, # I側は左右対称で考えるとOとI逆転
        top_in = Box_I_MG_points.Box_points.top_in_I_point,
        web_top_out = Box_I_MG_points.Box_points.Iweb_top_I_point,
        web_bottom_out= Box_I_MG_points.Box_points.Iweb_bottom_I_point,
        web_top_in = Box_I_MG_points.Box_points.Iweb_top_O_point,
        web_bottom_in= Box_I_MG_points.Box_points.Iweb_bottom_O_point,
        bottom_in = Box_I_MG_points.Box_points.bottom_in_I_point,
        bottom_out = Box_I_MG_points.Box_points.bottom_out_I_point,
    )
    Box_I_MG_points_I = BoxPointsInfo(
        top_flange_thickness = Box_I_MG_points.top_flange_thickness,
        bottom_flange_thickness = Box_I_MG_points.bottom_flange_thickness,
        top_out = Box_I_MG_points.Box_points.top_out_O_point, # I側は左右対称で考えるとOとI逆転
        top_in = Box_I_MG_points.Box_points.top_in_O_point,
        web_top_out = Box_I_MG_points.Box_points.Oweb_top_O_point,
        web_bottom_out= Box_I_MG_points.Box_points.Oweb_bottom_O_point,
        web_top_in = Box_I_MG_points.Box_points.Oweb_top_I_point,
        web_bottom_in= Box_I_MG_points.Box_points.Oweb_bottom_I_point,
        bottom_in = Box_I_MG_points.Box_points.bottom_in_O_point,
        bottom_out = Box_I_MG_points.Box_points.bottom_out_O_point,
    )



    top_flange_info = IBoxJointFlangeInfo(
        Box_out_y = df_row["上フランジ_箱桁部_y"],
        Plate_out_y = df_row["上フランジ_鈑桁部_y"],
        Box_in_y = df_row["上フランジ_箱桁部内側_y"],
        Plate_in_y = df_row["上フランジ_鈑桁部内側_y"],
        thickness = df_row["上フランジ_共通_厚"],
    )
    bottom_flange_info = IBoxJointFlangeInfo(
        Box_out_y = df_row["下フランジ_箱桁部_y"],
        Plate_out_y = df_row["下フランジ_鈑桁部_y"],
        Box_in_y = df_row["下フランジ_箱桁部内側_y"],
        Plate_in_y = df_row["下フランジ_鈑桁部内側_y"],
        thickness = df_row["下フランジ_共通_厚"],
    )
    web_thickness = df_row["横桁_共通_厚"]
    web_gap_y = df_row["横桁_横桁部_y"]
    return IBoxJointInfo(
        Plate_bridge_name=I_bridge_name,
        Box_bridge_name=Box_bridge_name,
        Plate_I_MG_points_I=Plate_I_MG_points_I,
        Plate_I_MG_points_O=Plate_I_MG_points_O,
        Plate_O_MG_points_I=Plate_O_MG_points_I,
        Plate_O_MG_points_O=Plate_O_MG_points_O,
        Box_I_MG_points_I=Box_I_MG_points_I,
        Box_I_MG_points_O=Box_I_MG_points_O,
        Box_O_MG_points_I=Box_O_MG_points_I,
        Box_O_MG_points_O=Box_O_MG_points_O,
        top_flange_info=top_flange_info,
        bottom_flange_info=bottom_flange_info,
        web_thickness=web_thickness,
        web_gap_y=web_gap_y,
    )

    
def main(initial_or_final: str) -> None:
    if initial_or_final == "initial":
        input_dir = INITIAL_INPUT_DIR
        output_dir = INITIAL_OUTPUT_DIR
    elif initial_or_final == "final":
        input_dir = FINAL_INPUT_DIR
        output_dir = FINAL_OUTPUT_DIR

    joint_df = read_file_to_df(
        file_path = input_dir / "鈑桁箱桁接続部諸元.xlsx",
        header=[0,1,2]
    )
    MG_point_IO_dict = load_from_pickle(output_dir / f"{Filenames.WORLD}_{Filenames.MG}_{Filenames.POINTS}_IO.pickle")


    all_infos = []

    for _, row in joint_df.iterrows():
        info = get_indiv_joint_info(
            df_row = row,
            MG_point_IO_dict = MG_point_IO_dict,
        )
        all_infos.append(info)
    
    save_json_and_pickle(
        data = all_infos,
        folder_path = output_dir,
        name = f"{Filenames.INPUT}_{Filenames.I_BOX_JOINT}",
    )

if __name__ == "__main__":
    main("initial")


