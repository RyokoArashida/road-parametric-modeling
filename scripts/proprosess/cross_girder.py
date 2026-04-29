import re
from dataclasses import fields

import pandas as pd

from my_project.config.file_names import Filenames
from my_project.config.paths import (
    FINAL_INPUT_DIR,
    FINAL_OUTPUT_DIR,
    INITIAL_INPUT_DIR,
    INITIAL_OUTPUT_DIR,
)
from my_project.config.schemas.cross_girder_schemas import (
    BoxGirderInfo_IO,
    CrossGirderInfo,
    EdgeWebInfo,
    FlangeInfo,
    HInfo,
    IGirderInfo_IO,
    LInfo,
    MainGirderPointInfo_IO,
    SlabBottomPoints_IO,
    TaikeikouInfo,
    WebInfo,
    YokobariInfo,
    YokogetaInfo,
)
from my_project.utils.io import load_from_pickle, read_file_to_df, save_json_and_pickle
from my_project.utils.proprocess import get_single


def get_all_mapping_dict(
    mapping_df: pd.DataFrame,
) -> dict[str, dict[list[str], tuple[str, int]]]:
    mapping_dict = {}
    for _, row in mapping_df.iterrows():
        bridge_name = row["橋梁"]
        CG_type = row["タイプ"]
        CG_type_num = int(row["番号"])
        CG_lists = row["横桁"].replace(" ", "").split(",")
        all_CG_list = []
        for CG_list in CG_lists:
            if "-" in CG_list:
                start, end = CG_list.split("-")
                prefix = re.match(r"\D+", start).group() # 数字以外の部分を抽出。先頭からマッチする
                start_num = int(re.search(r"\d+", start).group()) # 数字の部分を抽出
                end_num = int(re.search(r"\d+", end).group())
                all_CG_list.extend([f"{prefix}{i}" for i in range(start_num, end_num+1)])
            else:
                all_CG_list.append(CG_list)
        if bridge_name not in mapping_dict:
            mapping_dict[bridge_name] = {}
        for CG in all_CG_list:
            mapping_dict[bridge_name][CG] = (CG_type, CG_type_num)
    return mapping_dict

def convert_class_RL_or_UD_to_IO(info, UD, OutputClass):
    if UD == "U":
        trans = {
            "L": "O",
            "R": "I",
            "U": "O",
            "D": "I",
        }
    elif UD == "D":
        trans = {
            "L": "I",
            "R": "O",
            "U": "I",
            "D": "O",
        }
    else:
        raise ValueError(f"UD must be 'U' or 'D', got {UD}")
    kwargs = {}
    for f in fields(info):
        old_name = f.name
        new_name = old_name
        for old, new in trans.items():
            new_name = new_name.replace(old, new)
        kwargs[new_name] = getattr(info, old_name)
    return OutputClass(**kwargs)

def get_yokobari_info_from_row(
    yokobari_row: pd.Series
) -> YokobariInfo:
    web_offset = yokobari_row["中間_ウェブ_オフセットy"]
    center_info = HInfo(
        top_flange = FlangeInfo(
            thickness=yokobari_row["中間_上フランジ_厚"],
            width = yokobari_row["中間_上フランジ_y"],
            width_plus = yokobari_row["中間_上フランジ_上y"],
            width_minus = yokobari_row["中間_上フランジ_下y"],
        ),
        bottom_flange = FlangeInfo(
            thickness=yokobari_row["中間_下フランジ_厚"],
            width = yokobari_row["中間_下フランジ_y"],
            width_plus = yokobari_row["中間_下フランジ_上y"],
            width_minus = yokobari_row["中間_下フランジ_下y"],
        ),
        web = WebInfo(
            thickness=yokobari_row["中間_ウェブ_厚"],
        )
    )
    outer_extension = False
    inner_extension = False
    outer_existence = False
    inner_existence = False
    outer_info = None 
    inner_info = None # 張出
    outer_edge_info = None #延長のときは端っこにwebもできる
    inner_edge_info = None #延長のときは端っこにwebもできる

    if yokobari_row["路肩側張り出し_ウェブ_根本高さ"] == "延長":
        outer_extension = True
        outer_edge_info = EdgeWebInfo(
            thickness=yokobari_row["路肩側張り出し_端部ウェブ_厚"],
            offset=yokobari_row["路肩側張り出し_端部ウェブ_路肩端からオフセットx"],
        )
    elif isinstance(yokobari_row["路肩側張り出し_ウェブ_根本高さ"], (int, float)):
        outer_existence = True
        outer_info = HInfo(
            top_flange = FlangeInfo(
                thickness=yokobari_row["路肩側張り出し_上フランジ_厚"],
                width = yokobari_row["路肩側張り出し_上フランジ_y"],
                width_plus = yokobari_row["路肩側張り出し_上フランジ_上y"],
                width_minus = yokobari_row["路肩側張り出し_上フランジ_下y"],
            ),
            bottom_flange = FlangeInfo(
                thickness=yokobari_row["路肩側張り出し_下フランジ_厚"],
                width = yokobari_row["路肩側張り出し_下フランジ_y"],
                width_plus = yokobari_row["路肩側張り出し_下フランジ_上y"],
                width_minus = yokobari_row["路肩側張り出し_下フランジ_下y"],
            ),
            web = WebInfo(
                thickness=yokobari_row["路肩側張り出し_ウェブ_厚"],
                height=yokobari_row["路肩側張り出し_ウェブ_根本高さ"],
                edge_height=yokobari_row["路肩側張り出し_ウェブ_先端高さ"],
            )
        )
    if yokobari_row["中央側張り出し_ウェブ_根本高さ"] == "延長":
        inner_extension = True
        inner_edge_info = EdgeWebInfo(
            thickness=yokobari_row["中央側張り出し_端部ウェブ_厚"],
            offset=yokobari_row["中央側張り出し_端部ウェブ_中央端からオフセットx"],
        )
    elif isinstance(yokobari_row["中央側張り出し_ウェブ_根本高さ"], (int, float)):
        inner_existence = True
        inner_info = HInfo(
            top_flange = FlangeInfo(
                thickness=yokobari_row["中央側張り出し_上フランジ_厚"],
                width = yokobari_row["中央側張り出し_上フランジ_y"],
                width_plus = yokobari_row["中央側張り出し_上フランジ_上y"],
                width_minus = yokobari_row["中央側張り出し_上フランジ_下y"],
            ),
            bottom_flange = FlangeInfo(
                thickness=yokobari_row["中央側張り出し_下フランジ_厚"],
                width = yokobari_row["中央側張り出し_下フランジ_y"],
                width_plus = yokobari_row["中央側張り出し_下フランジ_上y"],
                width_minus = yokobari_row["中央側張り出し_下フランジ_下y"],
            ),
            web = WebInfo(
                thickness=yokobari_row["中央側張り出し_ウェブ_厚"],
                height=yokobari_row["中央側張り出し_ウェブ_根本高さ"],
                edge_height=yokobari_row["中央側張り出し_ウェブ_先端高さ"],
            )
        )
    return YokobariInfo(
        web_offset = web_offset,
        center_info = center_info,
        outer_extension = outer_extension,
        inner_extension = inner_extension,
        outer_existence = outer_existence,
        inner_existence = inner_existence,
        outer_info = outer_info, # 張出
        inner_info = inner_info, # 張出
        outer_edge_info = outer_edge_info, #延長のときは端っこにwebもできる
        inner_edge_info = inner_edge_info, #延長のときは端っこにwebもできる
    )

def get_taikeikou_info_from_row(
    taikeikou_row: pd.Series
) -> TaikeikouInfo:
    V_num = int(taikeikou_row["全体_全体_V数"])
    center_top_offset_z = taikeikou_row["中間_上H鋼_主桁上から中間z"]
    center_top_H_info = HInfo(
        top_flange = FlangeInfo(
            thickness=taikeikou_row["中間_上H鋼_フランジ厚"],
            width = taikeikou_row["中間_上H鋼_幅"],
            width_plus = taikeikou_row["中間_上H鋼_幅"] / 2,
            width_minus = taikeikou_row["中間_上H鋼_幅"] / 2,
        ),
        bottom_flange = FlangeInfo(
            thickness=taikeikou_row["中間_下H鋼_フランジ厚"],
            width = taikeikou_row["中間_下H鋼_幅"],
            width_plus = taikeikou_row["中間_下H鋼_幅"] / 2,
            width_minus = taikeikou_row["中間_下H鋼_幅"] / 2,
        ),
        web = WebInfo(
            thickness=taikeikou_row["中間_上H鋼_ウェブ厚"],
            height=taikeikou_row["中間_上H鋼_高さ"],
        )
    )
    center_bottom_offset_z = taikeikou_row["中間_下H鋼_主桁下から中間z"]
    center_bottom_H_info = HInfo(
        top_flange = FlangeInfo(
            thickness=taikeikou_row["中間_下H鋼_フランジ厚"],
            width = taikeikou_row["中間_下H鋼_幅"],
            width_plus = taikeikou_row["中間_下H鋼_幅"] / 2,
            width_minus = taikeikou_row["中間_下H鋼_幅"] / 2,
        ),
        bottom_flange = FlangeInfo(
            thickness=taikeikou_row["中間_下H鋼_フランジ厚"],
            width = taikeikou_row["中間_下H鋼_幅"],
            width_plus = taikeikou_row["中間_下H鋼_幅"] / 2,
            width_minus = taikeikou_row["中間_下H鋼_幅"] / 2,
        ),
        web = WebInfo(
            thickness=taikeikou_row["中間_下H鋼_ウェブ厚"],
            height=taikeikou_row["中間_下H鋼_高さ"],
        )
    )
    center_L_info = LInfo(
        bottom_flange = FlangeInfo(
            thickness=taikeikou_row["中間_斜L鋼_厚"],
            width = taikeikou_row["中間_斜L鋼_幅"],
            width_plus = taikeikou_row["中間_斜L鋼_幅"] / 2,
            width_minus = taikeikou_row["中間_斜L鋼_幅"] / 2,
        ),
        web = WebInfo(
            thickness=taikeikou_row["中間_斜L鋼_厚"],
            height=taikeikou_row["中間_斜L鋼_高さ"],
        )
    )
    outer_existence = False
    inner_existence = False
    outer_info = None # 張出
    inner_info = None # 張出
    if taikeikou_row["張り出し_ウェブ_路肩側先端高さ"] != "なし":
        outer_existence = True
        outer_info = HInfo(
            top_flange = FlangeInfo(
                thickness=taikeikou_row["張り出し_上フランジ_路肩側厚"],
                width = taikeikou_row["張り出し_上フランジ_y"],
                width_plus = taikeikou_row["張り出し_上フランジ_上y"],
                width_minus = taikeikou_row["張り出し_上フランジ_下y"],
            ),
            bottom_flange = FlangeInfo(
                thickness=taikeikou_row["張り出し_下フランジ_路肩側厚"],
                width = taikeikou_row["張り出し_下フランジ_y"],
                width_plus = taikeikou_row["張り出し_下フランジ_上y"],
                width_minus = taikeikou_row["張り出し_下フランジ_下y"],
            ),
            web = WebInfo(
                thickness=taikeikou_row["張り出し_ウェブ_路肩側厚"],
                height=taikeikou_row["張り出し_ウェブ_根本高さ"],
                edge_height=taikeikou_row["張り出し_ウェブ_路肩側先端高さ"],
            )
        )
    if taikeikou_row["張り出し_ウェブ_中央側先端高さ"] != "なし":
        inner_existence = True
        inner_info = HInfo(
            top_flange = FlangeInfo(
                thickness=taikeikou_row["張り出し_上フランジ_中央側厚"],
                width = taikeikou_row["張り出し_上フランジ_y"],
                width_plus = taikeikou_row["張り出し_上フランジ_上y"],
                width_minus = taikeikou_row["張り出し_上フランジ_下y"],
            ),
            bottom_flange = FlangeInfo(
                thickness=taikeikou_row["張り出し_下フランジ_中央側厚"],
                width = taikeikou_row["張り出し_下フランジ_y"],
                width_plus = taikeikou_row["張り出し_下フランジ_上y"],
                width_minus = taikeikou_row["張り出し_下フランジ_下y"],
            ),
            web = WebInfo(
                thickness=taikeikou_row["張り出し_ウェブ_中央側厚"],
                height=taikeikou_row["張り出し_ウェブ_根本高さ"],
                edge_height=taikeikou_row["張り出し_ウェブ_中央側先端高さ"],
            )
        )
    return TaikeikouInfo(
        V_num = V_num,
        center_top_H_offset_z = center_top_offset_z,
        center_top_H_info = center_top_H_info,
        center_bottom_H_offset_z = center_bottom_offset_z,
        center_bottom_H_info = center_bottom_H_info,
        center_L_info = center_L_info,
        outer_existence = outer_existence,
        inner_existence = inner_existence,
        outer_info = outer_info, # 張出
        inner_info = inner_info, # 張出
    )

def get_yokogeta_info_from_row(
    yokogeta_row: pd.Series
) -> YokogetaInfo:
    center_info = HInfo(
        top_flange = FlangeInfo(
            thickness=yokogeta_row["中間_上フランジ_厚"],
            width = yokogeta_row["中間_上フランジ_y"],
            width_plus = yokogeta_row["中間_上フランジ_y"] / 2,
            width_minus = yokogeta_row["中間_上フランジ_y"] / 2,
        ),
        bottom_flange = FlangeInfo(
            thickness=yokogeta_row["中間_下フランジ_厚"],
            width = yokogeta_row["中間_下フランジ_y"],
            width_plus = yokogeta_row["中間_下フランジ_y"] / 2,
            width_minus = yokogeta_row["中間_下フランジ_y"] / 2,
        ),
        web = WebInfo(
            thickness= yokogeta_row["中間_ウェブ_厚"],
            height = yokogeta_row["中間_全体_z"]
        )
    )
    outer_existence = False
    inner_existence = False
    outer_info = None # 張出
    inner_info = None # 張出
    if yokogeta_row["張り出し_ウェブ_路肩側先端高さ"] != "なし":
        outer_existence = True
        outer_info = HInfo(
            top_flange = FlangeInfo(
                thickness=yokogeta_row["張り出し_上フランジ_路肩側厚"],
                width = yokogeta_row["張り出し_上フランジ_y"],
                width_plus = yokogeta_row["張り出し_上フランジ_y"] / 2,
                width_minus = yokogeta_row["張り出し_上フランジ_y"] / 2,
            ),
            bottom_flange = FlangeInfo(
                thickness=yokogeta_row["張り出し_下フランジ_路肩側厚"],
                width = yokogeta_row["張り出し_下フランジ_y"],
                width_plus = yokogeta_row["張り出し_下フランジ_y"] / 2,
                width_minus = yokogeta_row["張り出し_下フランジ_y"] / 2,
            ),
            web = WebInfo(
                thickness=yokogeta_row["張り出し_ウェブ_路肩側厚"],
                height=yokogeta_row["張り出し_ウェブ_根本高さ"],
                edge_height=yokogeta_row["張り出し_ウェブ_路肩側先端高さ"],
            )
        )
    if yokogeta_row["張り出し_ウェブ_中央側先端高さ"] != "なし":
        inner_existence = True
        inner_info = HInfo(
            top_flange = FlangeInfo(
                thickness=yokogeta_row["張り出し_上フランジ_中央側厚"],
                width = yokogeta_row["張り出し_上フランジ_y"],
                width_plus = yokogeta_row["張り出し_上フランジ_y"] / 2,
                width_minus = yokogeta_row["張り出し_上フランジ_y"] / 2,
            ),
            bottom_flange = FlangeInfo(
                thickness=yokogeta_row["張り出し_下フランジ_中央側厚"],
                width = yokogeta_row["張り出し_下フランジ_y"],
                width_plus = yokogeta_row["張り出し_下フランジ_y"] / 2,
                width_minus = yokogeta_row["張り出し_下フランジ_y"] / 2,
            ),
            web = WebInfo(
                thickness=yokogeta_row["張り出し_ウェブ_中央側厚"],
                height=yokogeta_row["張り出し_ウェブ_根本高さ"],
                edge_height=yokogeta_row["張り出し_ウェブ_中央側先端高さ"],
            )
        )
    return YokogetaInfo(
        center_info = center_info,
        outer_existence = outer_existence,
        inner_existence = inner_existence,
        outer_info = outer_info, # 張出
        inner_info = inner_info, # 張出
    )


def main(initial_or_final: str) -> None:
    if initial_or_final == "initial":
        input_dir = INITIAL_INPUT_DIR
        output_dir = INITIAL_OUTPUT_DIR
    elif initial_or_final == "final":
        input_dir = FINAL_INPUT_DIR
        output_dir = FINAL_OUTPUT_DIR

    mapping_df = read_file_to_df(
        file_path = input_dir / "横桁諸元.xlsx",
        sheet_name = "対応表"
    )

    UD_df = read_file_to_df(
        file_path = input_dir / "横桁諸元.xlsx",
        sheet_name = "上下対応表",
    )

    yokobari_df = read_file_to_df(
        file_path = input_dir / "横桁諸元.xlsx",
        sheet_name = "横梁",
        header=[0,1,2]
    )

    taikeikou_df = read_file_to_df(
        file_path = input_dir / "横桁諸元.xlsx",
        sheet_name = "対傾構",
        header=[0,1,2]
    )

    yokogeta_df = read_file_to_df(
        file_path = input_dir / "横桁諸元.xlsx",
        sheet_name = "横桁",
        header=[0,1,2]
    )

    MG_point_dict = load_from_pickle(
        output_dir / f"{Filenames.WORLD}_{Filenames.MG}_{Filenames.POINTS}.pickle",
    )

    slab_bottom_points = load_from_pickle(
        output_dir / f"{Filenames.WORLD}_{Filenames.SLAB}_{Filenames.BOTTOM}_{Filenames.POINTS}.pickle",
    )


    all_mapping_dict = get_all_mapping_dict(mapping_df)
    all_CG_infos = {}

    for bridge_name, CG_dict in all_mapping_dict.items():
        all_CG_infos[bridge_name] = []
        MG_point_dict_for_bridge = MG_point_dict[bridge_name]
        original_CG_names = []
        MG_point_dict_for_bridge_changed = {}
        for MG_name, MG_point_dict_for_MG in MG_point_dict_for_bridge.items():
            original_CG_names.extend(list(MG_point_dict_for_MG.keys()))
            for CG_name, MG_infos in MG_point_dict_for_MG.items():
                if CG_name not in MG_point_dict_for_bridge_changed:
                    MG_point_dict_for_bridge_changed[CG_name] = {}
                MG_point_dict_for_bridge_changed[CG_name][MG_name] = MG_infos
        original_CG_names = list(set(original_CG_names))
        original_CG_names = [CG_name for CG_name in original_CG_names if "GE" not in CG_name] # GEは横桁のCGなので除外
        slab_bottom_points_for_bridge = slab_bottom_points[bridge_name]
        slab_CG_names = list(slab_bottom_points_for_bridge.keys())
        # originalにあってslabにないもの
        gap = set(original_CG_names) - set(slab_CG_names)
        if gap:
            print(f"Warning: {bridge_name}のCGのうち、以下のCGはスラブの情報に存在しません。: {gap}")
        UD = UD_df[UD_df["橋梁"] == bridge_name]["UD"].values[0]
        MG_order = UD_df[UD_df["橋梁"] == bridge_name]["主桁路肩から中央"].values[0]
        MG_order = MG_order.replace(" ", "").split(",")
        for CG_name in original_CG_names:
            CG_map = CG_dict.get(CG_name)
            if CG_map is None:
                print(f"Warning: {bridge_name}の{CG_name}は対応表に存在しません。")
                continue
            CG_type, CG_type_num = CG_map
            yokobari_info = None
            taikeikou_info = None
            yokogeta_info = None
            if CG_type == "横梁":
                yokobari_row = yokobari_df[yokobari_df["全体_全体_番号"] == CG_type_num]
                yokobari_row = get_single(yokobari_row)
                yokobari_info = get_yokobari_info_from_row(yokobari_row)
            elif CG_type == "対傾構":
                taikeikou_row = taikeikou_df[taikeikou_df["全体_全体_番号"] == CG_type_num]
                taikeikou_row = get_single(taikeikou_row)
                taikeikou_info = get_taikeikou_info_from_row(taikeikou_row)
            elif CG_type == "横桁":
                yokogeta_row = yokogeta_df[yokogeta_df["全体_全体_番号"] == CG_type_num]
                yokogeta_row = get_single(yokogeta_row)
                yokogeta_info = get_yokogeta_info_from_row(yokogeta_row)

            MG_point_dict_for_CG = MG_point_dict_for_bridge_changed.get(CG_name, {})
            MG_names = list(MG_point_dict_for_CG.keys())
            MG_data = [(MG_name, MG_point_dict_for_CG[MG_name]) for MG_name in MG_names]
            # MG_dataの名前の中でMG_orderにないものがあったらvalue error
            if any(MG_name not in MG_order for MG_name, _ in MG_data):
                raise ValueError(f"Error: {bridge_name}の{CG_name}のMGのうち、MG_orderに存在しないものがあります。MG_order: {MG_order}, MG_data: {MG_data}")
            sorted_MG_data = sorted(MG_data, key=lambda x: MG_order.index(x[0]))
            sorted_MG_infos = [MG_info for _, MG_info in sorted_MG_data]
            print(f"{bridge_name}の{CG_name}のMGの順番: {[MG_name for MG_name, _ in sorted_MG_data]}")
            MG_infos_IO = []
            for MG_info in sorted_MG_infos:
                top_flange_thickness = MG_info.top_flange_thickness
                bottom_flange_thickness = MG_info.bottom_flange_thickness
                web_thickness = MG_info.web_thickness
                I_points = MG_info.I_points
                Box_points = MG_info.Box_points
                I_points_IO = None
                Box_points_IO = None
                if pd.notna(I_points):
                    I_points_IO = convert_class_RL_or_UD_to_IO(I_points, UD, IGirderInfo_IO)
                elif pd.notna(Box_points):
                    Box_points_IO = convert_class_RL_or_UD_to_IO(Box_points, UD, BoxGirderInfo_IO)
                MG_info_IO = MainGirderPointInfo_IO(
                    top_flange_thickness = top_flange_thickness,
                    bottom_flange_thickness = bottom_flange_thickness,
                    web_thickness = web_thickness,
                    I_points = I_points_IO,
                    Box_points = Box_points_IO,
                )
                MG_infos_IO.append(MG_info_IO)

            slab_bottom_points_for_CG = slab_bottom_points_for_bridge.get(CG_name)
            if slab_bottom_points_for_CG is None:
                print(f"Warning: {bridge_name}の{CG_name}はスラブの情報に存在しません。")
                continue
            slab_bottom_points_for_CG_IO = convert_class_RL_or_UD_to_IO(slab_bottom_points_for_CG, UD, SlabBottomPoints_IO)
            CG_info = CrossGirderInfo(
                bridge_name = bridge_name,
                CG_name = CG_name,
                MGs = MG_infos_IO,
                slab_bottom_points = slab_bottom_points_for_CG_IO,
                CG_type=CG_type,
                yokobari_info=yokobari_info,
                taikeikou_info=taikeikou_info,
                yokogeta_info=yokogeta_info,
            )
            all_CG_infos[bridge_name].append(CG_info)

    
    save_json_and_pickle(
        data = all_CG_infos,
        folder_path = output_dir,
        name = f"{Filenames.INPUT}_{Filenames.CG}"
    )


if __name__ == "__main__":
    main("initial")


