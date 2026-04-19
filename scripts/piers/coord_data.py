from typing import Any, Optional

import pandas as pd
from Rhino.Geometry import Brep

from my_project.config.file_names import Filenames
from my_project.config.input_pier_schemas import (
    ColumnInfo,
    CommonPierInfo,
    InputPierInfo,
    MaxPierTopX,
    PierTopInfo,
    PierTopSurfInfo,
)
from my_project.config.paths import (
    FINAL_OUTPUT_DIR,
    INITIAL_OUTPUT_DIR,
)
from my_project.config.util_schemas import (
    Frame2D,
    LocalOffset,
    Point2D,
    Point3D,
    Vector2D,
)
from my_project.utils.geometry import (
    extrude_curve_in_frame,
    offset_point_in_frame,
)
from my_project.utils.io import load_from_pickle
from my_project.utils.lines import const_line_obj
from my_project.utils.points import const_point_obj
from my_project.utils.proprocess import midpoint, normalize


def get_frame_2D(point_u: Point2D, point_d: Point2D) -> Frame2D:
    # U -> D のベクトルをx軸とする
    raw_x = Vector2D(
        x=point_d.x - point_u.x,
        y=point_d.y - point_u.y
    )
    x_axis = normalize(raw_x)
    y_axis = Vector2D(
        x=-x_axis.y,
        y=x_axis.x,
    ) # x軸に対して反時計回りに90度回転させるとy軸になる
    return Frame2D(
        x_axis=x_axis,
        y_axis=y_axis,
    )

def get_pier_top_surf_corners(
    zero_point2D: Point2D,
    width_y: float,
    frame_2D: Frame2D,
    pier_top_x: float,
) -> list[Point2D]: #PierTopSurfModel.corner_points
    """橋座面の4点を求める"""
    y_plus = width_y / 2
    y_minus = -width_y / 2
    offsets = [
        LocalOffset(x=pier_top_x, y=y_plus, z=0), # p1
        LocalOffset(x=pier_top_x, y=y_minus, z=0), # p2
        LocalOffset(x=0, y=y_minus, z=0), # p3
        LocalOffset(x=0, y=y_plus, z=0), # p4
    ]
    corner_points = []
    for offset in offsets:
        corner_point = offset_point_in_frame(
            point=zero_point2D,
            local_offset=offset,
            frame_2D=frame_2D,
        )
        corner_points.append(corner_point)
    return corner_points

def get_column_corners(
    frame_2D: Frame2D,
    column_info: ColumnInfo,
    pier_center_point: Point2D,
) -> list[Point2D]:
    x_ou = column_info.outer_x / 2
    x_in = column_info.inner_x / 2
    y_ou = column_info.outer_y / 2
    y_in = column_info.inner_y / 2
    offset_xs = [x_ou, x_in, x_in, x_ou, -x_ou, -x_in, -x_in, -x_ou]
    offset_ys = [y_in, y_ou, -y_ou, -y_in, -y_in, -y_ou, y_ou, y_in]
    corners = []
    for offset_x, offset_y in zip(offset_xs, offset_ys):
        local_offset = LocalOffset(x=offset_x, y=offset_y, z=0)
        corner_point = offset_point_in_frame(
            point=pier_center_point,
            local_offset=local_offset,
            frame_2D=frame_2D,
        )
        corners.append(corner_point)
    return corners

def get_horizontal_offset(
    x: float,
    pier_top_x_type: Optional[str],
    max_piertop_x: MaxPierTopX,
    edge: bool # 端部か中間か    
    ) -> Optional[float]:
    if pd.isna(pier_top_x_type):
        return None
    elif pier_top_x_type == "直線":
        max_x = max_piertop_x.max_slope_x
    elif pier_top_x_type == "曲線":
        max_x = max_piertop_x.max_curve_x
    if edge:
        max_x = max_x
    else:
        max_x = max_x * 2
    if x > max_x:
        return x - max_x
    else:
        return None

def get_piertop_ud_points(
    pier_top_x: float,
    zero_point2D: Point2D,
    frame_2D: Frame2D,
    column_info: ColumnInfo,
    piertop_info: PierTopInfo,
    max_piertop_x: MaxPierTopX
) -> tuple[Optional[list[Point2D]], Optional[list[Point2D]]]:
    # まずは本当の端部の点を求める
    ou_y = column_info.outer_y / 2
    u_offsets = [(0, ou_y), (0, -ou_y)]
    d_offsets = [(pier_top_x, ou_y), (pier_top_x, -ou_y)]
    u_p4, u_p3 = [offset_point_in_frame(
        point=zero_point2D,
        local_offset=LocalOffset(x=offset_x, y=offset_y, z=0),
        frame_2D=frame_2D,
    ) for offset_x, offset_y in u_offsets]
    d_p1, d_p2 = [offset_point_in_frame(
        point=zero_point2D,
        local_offset=LocalOffset(x=offset_x, y=offset_y, z=0),
        frame_2D=frame_2D,
    ) for offset_x, offset_y in d_offsets]

    u_horizontal_x = get_horizontal_offset(piertop_info.u_side_x.x, piertop_info.u_side_x.pier_top_x_type, max_piertop_x, edge=True)
    d_horizontal_x = get_horizontal_offset(piertop_info.d_side_x.x, piertop_info.d_side_x.pier_top_x_type, max_piertop_x, edge=True)

    if u_horizontal_x is None:
        u_p1, u_p2 = None, None
    else:
        u_p1 = offset_point_in_frame(
            point=u_p4,
            local_offset=LocalOffset(x=u_horizontal_x, y=0, z=0),
            frame_2D=frame_2D,
        )
        u_p2 = offset_point_in_frame(
            point=u_p3,
            local_offset=LocalOffset(x=u_horizontal_x, y=0, z=0),
            frame_2D=frame_2D,
        )
    if d_horizontal_x is None:
        d_p3, d_p4 = None, None
    else:
        d_p4 = offset_point_in_frame(
            point=d_p1,
            local_offset=LocalOffset(x=-d_horizontal_x, y=0, z=0),
            frame_2D=frame_2D,
        )
        d_p3 = offset_point_in_frame(
            point=d_p2,
            local_offset=LocalOffset(x=-d_horizontal_x, y=0, z=0),
            frame_2D=frame_2D,
        )
    return ([u_p1, u_p2, u_p3, u_p4], [d_p1, d_p2, d_p3, d_p4])

def get_piertop_between_points(
    column_corners: list[list[Point2D]],
    piertop_info: PierTopInfo,
    frame_2D: Frame2D,
    max_piertop_x: MaxPierTopX,
) -> list[list[Point2D]]:
    between_points = []
    for i, between_column_x in enumerate(piertop_info.between_columns_x):
        horizontal_x = get_horizontal_offset(between_column_x.x, between_column_x.pier_top_x_type, max_piertop_x, edge=False)
        if horizontal_x is None:
            p1, p2, p3, p4 = None, None, None, None
        else:
            offset_x = (between_column_x.x - horizontal_x) / 2
            column_corner_1 = column_corners[i+1][6]
            column_corner_2 = column_corners[i+1][5]
            column_corner_3 = column_corners[i][2]
            column_corner_4 = column_corners[i][1]
            p1 = offset_point_in_frame(
                point=column_corner_1,
                local_offset=LocalOffset(x=-offset_x, y=0, z=0),
                frame_2D=frame_2D,
            )
            p2 = offset_point_in_frame(
                point=column_corner_2,
                local_offset=LocalOffset(x=-offset_x, y=0, z=0),
                frame_2D=frame_2D,
            )
            p3 = offset_point_in_frame(
                point=column_corner_3,
                local_offset=LocalOffset(x=offset_x, y=0, z=0),
                frame_2D=frame_2D,
            )
            p4 = offset_point_in_frame(
                point=column_corner_4,
                local_offset=LocalOffset(x=offset_x, y=0, z=0),
                frame_2D=frame_2D,
            )
        between_points.append([p1, p2, p3, p4])
    return between_points
    
def get_each_2Dpoints(
    input_pier_info: InputPierInfo,
    input_common_info: CommonPierInfo,
    zero_point2D: Point2D,
    num_columns: int,
    frame_2D: Frame2D,
): ##pointのクラスを集めたもの
    #橋座面の点を求める
    pier_top_x = input_pier_info.column.inner_x * num_columns + input_pier_info.piertop.u_side_x.x + input_pier_info.piertop.d_side_x.x
    for between_column_x in input_pier_info.piertop.between_columns_x:
        pier_top_x += between_column_x.x
    piertop_surf_corner_points = get_pier_top_surf_corners(
        zero_point2D=zero_point2D,
        width_y=input_pier_info.piertop_surf.width_y,
        frame_2D=frame_2D,
        pier_top_x=pier_top_x,
    )

    # 柱の中心を求める
    column_centers = []
    offset_x = input_pier_info.piertop.u_side_x.x + input_pier_info.column.inner_x / 2
    for i in range(num_columns):
        local_offset = LocalOffset(
            x = offset_x,
            y = 0,
            z = 0,
        )
        column_center = offset_point_in_frame(
            point=zero_point2D,
            local_offset=local_offset,
            frame_2D=frame_2D,
        )
        column_centers.append(column_center)
        if i < num_columns - 1:
            offset_x += input_pier_info.column.inner_x + input_pier_info.piertop.between_columns_x[i].x
    
    # 各柱について、柱の外側の点を求める
    column_corners = []
    for column_center in column_centers:
        corners = get_column_corners(
            frame_2D=frame_2D,
            column_info=input_pier_info.column,
            pier_center_point=column_center,
        )
        column_corners.append(corners)
    
    # 梁の点を求める
    u_side_corners, d_side_corners = get_piertop_ud_points(
        pier_top_x=pier_top_x,
        zero_point2D=zero_point2D,
        frame_2D=frame_2D,
        column_info=input_pier_info.column,
        piertop_info=input_pier_info.piertop,
        max_piertop_x=input_common_info.max_piertop_x,
    )
    between_corners = get_piertop_between_points(
        column_corners=column_corners,
        piertop_info=input_pier_info.piertop,
        frame_2D=frame_2D,
        max_piertop_x=input_common_info.max_piertop_x,
    )
    
    # デバッグ用
    debug_points = []
    for p in piertop_surf_corner_points:
        debug_points.append(const_point_obj(p))
    for p in column_centers:
        debug_points.append(const_point_obj(p))
    for corners in column_corners:
        for p in corners:
            debug_points.append(const_point_obj(p))
    for corners in [u_side_corners, d_side_corners]:
        if corners is not None:
            for p in corners:
                if p is not None:
                    debug_points.append(const_point_obj(p))
    for corners in between_corners:
        for p in corners:
            if p is not None:
                debug_points.append(const_point_obj(p))
    # return debug_points

    return {
        "pier_top_x": pier_top_x,
        "piertop_surf_corner_points": piertop_surf_corner_points,
        "column_centers": column_centers,
        "column_corners": column_corners,
        "u_side_corners": u_side_corners,
        "d_side_corners": d_side_corners,
        "between_corners": between_corners,
    }, debug_points

def const_piertop_srfs(
    piertop_surf_corner_points: list[Point2D],
    zero_point: Point3D,
    piertop_surf_info: PierTopSurfInfo,
    pier_top_x: float,
    frame_2D: Frame2D,
) -> tuple[Brep, Brep]:
    """橋座面と梁下面のサーフェスを作る"""
    TD2D, ND2D, NU2D, TU2D = piertop_surf_corner_points
    CU2D = midpoint(NU2D, TU2D)
    UCx = TU2D.x
    DCx = TD2D.x
    REFx = zero_point.x
    x_slope = piertop_surf_info.u2d_slope.value
    UCz = zero_point.z + (REFx - UCx) * x_slope / 100 # %で与えられているので100で割る。Uのほうが高い場合正なので、引いた値が正になるように。
    DCz = zero_point.z + (REFx - DCx) * x_slope / 100
    y_slope = piertop_surf_info.crown_slope.value
    Uz = UCz - piertop_surf_info.width_y / 2 * y_slope / 100 # 山形

    def get_piertop_surf_origin(NT:str) -> Brep:
        if NT == "T":
            Uedge_point = TU2D
        elif NT == "N":
            Uedge_point = NU2D
        line = const_line_obj(
            Point3D(x=Uedge_point.x, y=Uedge_point.y, z=Uz),
            Point3D(x=CU2D.x, y=CU2D.y, z=UCz),
        )
        local_offset = LocalOffset(x= pier_top_x, y=0, z=DCz - UCz)
        origin_surf = extrude_curve_in_frame(
            obj=line,
            local_offset=local_offset,
            frame_2D=frame_2D,
        )
        return origin_surf
    
    T_origin_surf = get_piertop_surf_origin("T")
    N_origin_surf = get_piertop_surf_origin("N")

    return T_origin_surf, N_origin_surf


def const_piertop(
    piertop_surf_info: PierTopSurfInfo,
    piertop_info: PierTopInfo,
    column_info: ColumnInfo,
    zero_point: Point3D,
    frame_2D: Frame2D,
    points2D_dict: dict[str, Any],
) -> Brep:
    T_surf, N_surf = const_piertop_srfs(
        piertop_surf_corner_points=points2D_dict["piertop_surf_corner_points"],
        zero_point=zero_point,
        piertop_surf_info=piertop_surf_info,
        pier_top_x=points2D_dict["pier_top_x"],
        frame_2D=frame_2D,
    )


    # debug
    surfs_dict = {
        "T_surf": T_surf,
        "N_surf": N_surf,
    }

    return surfs_dict
    





        

def get_each_pier(
    input_pier_info: InputPierInfo,
    input_common_info: CommonPierInfo,
) -> dict[str, Brep]:
    # 橋脚のローカル2D座標系を求める
    point_u = input_pier_info.points_for_vector.point_u
    point_d = input_pier_info.points_for_vector.point_d
    frame_2D = get_frame_2D(
        point_u=Point2D(x=point_u.x, y=point_u.y),
        point_d=Point2D(x=point_d.x, y=point_d.y),
    )

    # ゼロ点を橋座面の基準点に合わせる
    zero_point = offset_point_in_frame(
        point=input_pier_info.piertop_surf.reference_point,
        local_offset=input_pier_info.piertop_surf.reference_offset,
        frame_2D=frame_2D,
    )
    zero_point2D = Point2D(x=zero_point.x, y=zero_point.y)

    # 柱の数
    num_columns = len(input_pier_info.piertop.between_columns_x) + 1

    points_2D_dict, point_list = get_each_2Dpoints(
        input_pier_info=input_pier_info,
        input_common_info=input_common_info,
        zero_point2D=zero_point2D,
        num_columns=num_columns,
        frame_2D=frame_2D,
    )

    piertop_surf_dict = const_piertop(
        piertop_surf_info=input_pier_info.piertop_surf,
        zero_point=zero_point,
        frame_2D=frame_2D,
        points2D_dict=points_2D_dict,
        piertop_info=input_pier_info.piertop,
        column_info=input_pier_info.column,

    )

    # debug
    surfs = []
    surfs.append(piertop_surf_dict["T_surf"])
    surfs.append(piertop_surf_dict["N_surf"])
    return piertop_surf_dict, surfs
    

def main(initial_or_final: str):
    if initial_or_final == "initial":
        DIR = INITIAL_OUTPUT_DIR
    elif initial_or_final == "final":
        DIR = FINAL_OUTPUT_DIR

    indiv_infos = load_from_pickle(DIR / f"{Filenames.INPUT}_{Filenames.PIER}_{Filenames.INDIV}.pickle")
    common_infos = load_from_pickle(DIR / f"{Filenames.INPUT}_{Filenames.PIER}_{Filenames.COMMON}.pickle")

    all_data = []
    for pier_name, indiv_info in indiv_infos.items():
        bridge_type = indiv_info.type
        common_info = common_infos[bridge_type]
        each_dict, each_data = get_each_pier(
            input_pier_info=indiv_info,
            input_common_info=common_info,
        )


        # debug
        all_data.extend(each_data)
    return all_data


if __name__ == "__main__":
    all_data = main("initial")
