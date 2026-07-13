# ruff: noqa: E402
from typing import Union

from my_project.config.locale_compat import normalize_lc_time

normalize_lc_time()

import pandas as pd
import Rhino.Geometry as rg

from my_project.config.file_names import Filenames
from my_project.config.paths import get_output_dir
from my_project.config.schemas.abut_schemas import (
    BackwallInfo,
    BarrierCommonInfo,
    BarrierInfo,
    CommonAbutInfo,
    InputAbutInfo,
    SeatInfo,
    SlabSeatInfo,
    WingCorners,
    WingInfo,
)
from my_project.config.util_schemas import (
    Point2D,
    Point3D,
    Square_Corners,
)
from my_project.utils.dataframe import flatten_any
from my_project.utils.geometry.points import (
    get_point_by_xy_offset,
    interpolate_point_3d,
)
from my_project.utils.geometry.vectors import get_frame_2D
from my_project.utils.geometry_gh.const import (
    const_3Dpoint,
    const_brep_from_two_closed_point_lists,
    const_closed_polycurve_obj,
    const_point_obj,
    const_srf_from_2crvs,
    join_breps_or_raise,
    remove_same_points,
)
from my_project.utils.geometry_gh.transform import place_obj
from my_project.utils.io import load_from_pickle, save_json_and_pickle


def get_named_footing_top_points(
    footing_top_points: list[Point3D],
    abut_points: dict,
) -> dict[str, Point3D]:
    if len(footing_top_points) != 4:
        raise ValueError(f"Need 4 footing top points, got {len(footing_top_points)}")

    wing_dict = abut_points["wing_dict"]
    U_base = wing_dict["U_wing_top_points"]["DB"]
    D_base = wing_dict["D_wing_top_points"]["UB"]
    U_wing = wing_dict["U_wing_top_points"]["DS"]
    D_wing = wing_dict["D_wing_top_points"]["US"]

    def center(point1: Point3D, point2: Point3D) -> Point3D:
        return Point3D(
            x=(point1.x + point2.x) / 2,
            y=(point1.y + point2.y) / 2,
            z=(point1.z + point2.z) / 2,
        )

    def xy_projection(point: Point3D, origin: Point3D, axis_end: Point3D) -> float:
        return (
            (point.x - origin.x) * (axis_end.x - origin.x)
            + (point.y - origin.y) * (axis_end.y - origin.y)
        )

    base_center = center(U_base, D_base)
    wing_center = center(U_wing, D_wing)
    sorted_by_base_to_wing = sorted(
        footing_top_points,
        key=lambda point: xy_projection(point, base_center, wing_center),
    )
    bridge_points = sorted_by_base_to_wing[:2]
    soil_points = sorted_by_base_to_wing[2:]

    def split_UD(points: list[Point3D]) -> tuple[Point3D, Point3D]:
        sorted_by_U_to_D = sorted(
            points,
            key=lambda point: xy_projection(point, U_base, D_base),
        )
        return sorted_by_U_to_D[0], sorted_by_U_to_D[1]

    U_bridge, D_bridge = split_UD(bridge_points)
    U_soil, D_soil = split_UD(soil_points)
    return {
        "U_bridge": U_bridge,
        "D_bridge": D_bridge,
        "U_soil": U_soil,
        "D_soil": D_soil,
    }


def get_box_from_SquareCorners(
    top_corners: Square_Corners,
    foundation_top_z: float,
    cap: bool = True,
) -> rg.Brep:
    bottom_corners = Square_Corners(
        DT=Point3D(x=top_corners.DT.x, y=top_corners.DT.y, z=foundation_top_z),
        DN=Point3D(x=top_corners.DN.x, y=top_corners.DN.y, z=foundation_top_z),
        UN=Point3D(x=top_corners.UN.x, y=top_corners.UN.y, z=foundation_top_z),
        UT=Point3D(x=top_corners.UT.x, y=top_corners.UT.y, z=foundation_top_z),
    )
    return const_brep_from_two_closed_point_lists(
        [top_corners.DT, top_corners.DN, top_corners.UN, top_corners.UT],
        [bottom_corners.DT, bottom_corners.DN, bottom_corners.UN, bottom_corners.UT],
        cap=cap,
    )


def get_beamseat(
    double: bool,
    seat_info: SeatInfo,
    foundation_top_z: float,
) -> dict[str, Union[rg.Brep, Square_Corners]]:
    y = seat_info.y
    slope = seat_info.y_slope.value / 100 # %なので
    def get_beamseat_from_data(
        D_x: float,
        U_x: float,
        D_z: float,
        U_z: float,
        cap: bool = True,
    ):
        z_offset = y * slope
        top_corners = Square_Corners(
            DT = Point3D(x=D_x, y = y, z = D_z - z_offset), # 外側に落ちる
            DN = Point3D(x=D_x, y = 0, z = D_z),
            UN = Point3D(x=U_x, y = 0, z = U_z),
            UT = Point3D(x=U_x, y = y, z = U_z - z_offset), # 外側に落ちる
        )
        brep = get_box_from_SquareCorners(
            top_corners = top_corners,
            foundation_top_z = foundation_top_z,
            cap = cap,
        )
        return brep, top_corners

    if not double:
        capped_brep, top_corners = get_beamseat_from_data(
            D_x = seat_info.D_x,
            U_x = -seat_info.U_x,
            D_z = seat_info.DD_z,
            U_z = seat_info.UU_z,
        )
        return {
            "beamseat": capped_brep,
            "beamseat_top_corners": top_corners,
        }
    
    else:
        D_brep, D_top_corners = get_beamseat_from_data(
            D_x = seat_info.D_x + seat_info.D_center_x,
            U_x = seat_info.D_center_x,
            D_z = seat_info.DD_z,
            U_z = seat_info.DU_z,
            cap = False, 
        )
        C_brep, C_top_corners = get_beamseat_from_data(
            D_x = seat_info.D_center_x,
            U_x = -seat_info.U_center_x,
            D_z = seat_info.DU_z,
            U_z = seat_info.UD_z,
            cap = False, 
        )
        U_brep, U_top_corners = get_beamseat_from_data(
            D_x = -seat_info.U_center_x,
            U_x = -seat_info.U_x - seat_info.U_center_x,
            D_z = seat_info.UD_z,
            U_z = seat_info.UU_z,
            cap = False, 
        )
        brep = join_breps_or_raise([D_brep, C_brep, U_brep], context="abut beamseat")
        capped_brep = brep.CapPlanarHoles(0.01)
        return {
            "beamseat": capped_brep,
            "D_beamseat_top_corners": D_top_corners,
            "C_beamseat_top_corners": C_top_corners,
            "U_beamseat_top_corners": U_top_corners,
        }
    
def get_backwall(
    double: bool,
    backwall_info: BackwallInfo,
    foundation_top_z: float,
    seat_info: SeatInfo,
    BU_overhang_width: float,
    BD_overhang_width: float,
) -> dict[str, Union[rg.Brep, Square_Corners]]:
    y = backwall_info.y
    def get_backwall_from_data(
        D_x: float,
        U_x: float,
        DB_z: float,
        UB_z: float,
        DE_z: float,
        UE_z: float,
        cap: bool = True,
    ):
        top_corners = Square_Corners(
            DT=Point3D(x=D_x, y = 0, z = DB_z), 
            DN=Point3D(x=D_x, y = -y, z = DE_z), 
            UN=Point3D(x=U_x, y = -y, z = UE_z),
            UT=Point3D(x=U_x, y = 0, z = UB_z), 
        )
        brep = get_box_from_SquareCorners(
            top_corners = top_corners,
            foundation_top_z = foundation_top_z,
            cap = cap,
        )
        return brep, top_corners
    
    def get_adjusted_z(
        x_U: float,
        x_D: float,
        z_U: float,
        z_D: float,
        offset_U: float,
        offset_D: float,
    ) -> tuple[float, float]:
        input_U_point = Point3D(x=x_U, y=0, z=z_U)
        input_D_point = Point3D(x=x_D, y=0, z=z_D)
        U_poiunt = get_point_by_xy_offset(
            point1=input_U_point,
            point2=input_D_point,
            offset=offset_U,
        )
        D_point = get_point_by_xy_offset(
            point1=input_D_point,
            point2=input_U_point,
            offset=offset_D,
        )
        return U_poiunt.z, D_point.z

    if not double:
        UUB_z, DDB_z = get_adjusted_z(
            x_U =-(seat_info.U_x+BU_overhang_width),
            x_D = seat_info.D_x+BD_overhang_width,
            z_U = backwall_info.UUB_z,
            z_D = backwall_info.DDB_z,
            offset_U = BU_overhang_width,
            offset_D = BD_overhang_width,
        )
        UUE_z, DDE_z = get_adjusted_z(
            x_U =-(seat_info.U_x+BU_overhang_width),
            x_D = seat_info.D_x+BD_overhang_width,
            z_U = backwall_info.UUE_z,
            z_D = backwall_info.DDE_z,
            offset_U = BU_overhang_width,
            offset_D = BD_overhang_width,
        )
        capped_brep, top_corners = get_backwall_from_data(
            D_x = seat_info.D_x,
            U_x = -seat_info.U_x,
            DB_z = DDB_z,
            UB_z = UUB_z,
            DE_z = DDE_z,
            UE_z = UUE_z,
            cap=True,
        )
        return {
            "backwall": capped_brep,
            "backwall_top_corners": top_corners,
        }
    
    else:
        UUB_z, UDB_z = get_adjusted_z(
            x_U =-(seat_info.U_x+seat_info.U_center_x+BU_overhang_width),
            x_D =-(seat_info.U_center_x),
            z_U = backwall_info.UUB_z,
            z_D = backwall_info.UDB_z,
            offset_U = BU_overhang_width,
            offset_D = 0,
        )
        UUE_z, UDE_z = get_adjusted_z(
            x_U =-(seat_info.U_x+seat_info.U_center_x+BU_overhang_width),
            x_D =-(seat_info.U_center_x),
            z_U = backwall_info.UUE_z,
            z_D = backwall_info.UDE_z,
            offset_U = BU_overhang_width,
            offset_D = 0,
        )
        DUB_z, DDB_z = get_adjusted_z(
            x_U = seat_info.D_center_x,
            x_D = seat_info.D_x+seat_info.D_center_x+BD_overhang_width,
            z_U = backwall_info.DUB_z,
            z_D = backwall_info.DDB_z,
            offset_U = 0,
            offset_D = BD_overhang_width,
        )
        DUE_z, DDE_z = get_adjusted_z(
            x_U = seat_info.D_center_x,
            x_D = seat_info.D_x+seat_info.D_center_x+BD_overhang_width,
            z_U = backwall_info.DUE_z,
            z_D = backwall_info.DDE_z,
            offset_U = 0,
            offset_D = BD_overhang_width,
        )

        D_capped_brep, D_top_corners = get_backwall_from_data(
            D_x = seat_info.D_x + seat_info.D_center_x,
            U_x = seat_info.D_center_x,
            DB_z = DDB_z,
            UB_z = DUB_z,
            DE_z = DDE_z,
            UE_z = DUE_z,
            cap=False,
        )
        C_capped_brep, C_top_corners = get_backwall_from_data(
            D_x = seat_info.D_center_x,
            U_x = -seat_info.U_center_x,
            DB_z = DUB_z,
            UB_z = UDB_z,
            DE_z = DUE_z,
            UE_z = UDE_z,
            cap=False,
        )
        U_capped_brep, U_top_corners = get_backwall_from_data(
            D_x = -seat_info.U_center_x,
            U_x = -seat_info.U_x - seat_info.U_center_x,
            DB_z = UDB_z,
            UB_z = UUB_z,
            DE_z = UDE_z,
            UE_z = UUE_z,
            cap=False,
        )
        brep = join_breps_or_raise([D_capped_brep, C_capped_brep, U_capped_brep], context="abut backwall")
        capped_brep = brep.CapPlanarHoles(0.01)
        return {
            "backwall": capped_brep,
            "D_backwall_top_corners": D_top_corners,
            "C_backwall_top_corners": C_top_corners,
            "U_backwall_top_corners": U_top_corners,
        }

def get_wings(
    double: bool,
    wing_info: WingInfo,
    foundation_top_z: float,
    backwall_dict: dict[str, Union[rg.Brep, Square_Corners]],
) -> dict[str, Union[rg.Brep, Square_Corners]]:
    if not double:
        DDB_top_point = backwall_dict["backwall_top_corners"].DN
        UUB_top_point = backwall_dict["backwall_top_corners"].UN
        DUB_top_point = get_point_by_xy_offset(
            point1=DDB_top_point,
            point2=UUB_top_point,
            offset=wing_info.D_x,
        )
        UDB_top_point = get_point_by_xy_offset(
            point1=UUB_top_point,
            point2=DDB_top_point,
            offset=wing_info.U_x,
        )
    else:
        DDB_top_point = backwall_dict["D_backwall_top_corners"].DN
        UUB_top_point = backwall_dict["U_backwall_top_corners"].UN
        backwall_DUE = backwall_dict["D_backwall_top_corners"].UN
        backwall_UDE = backwall_dict["U_backwall_top_corners"].DN
        DUB_top_point = get_point_by_xy_offset(
            point1=DDB_top_point,
            point2=backwall_DUE,
            offset=wing_info.D_x,
        )
        UDB_top_point = get_point_by_xy_offset(
            point1=UUB_top_point,
            point2=backwall_UDE,
            offset=wing_info.U_x,
        )

    def get_wing_from_data(
        out_B_top_point: Point3D,
        in_B_top_point: Point3D,
        out_edge_z: float,
        ab_y: float,
        bl_y: float,
        ab_height: float,
        bl_height: float,
    ) -> tuple[rg.Brep, list[Point3D]]:
        #上面
        z_gap = out_B_top_point.z - in_B_top_point.z
        out_E_top_point = Point3D(x=out_B_top_point.x, y=out_B_top_point.y - ab_y, z=out_edge_z)
        in_E_top_point = Point3D(x=in_B_top_point.x, y=in_B_top_point.y - ab_y, z=out_edge_z - z_gap) # 同じ差をキープ
        top_points = WingCorners( # ここではDが外、Uが内、Sが土工側、Bが橋側
            DB=out_B_top_point,
            DS=out_E_top_point,
            US=in_E_top_point,
            UB=in_B_top_point,
        )
        # 下面
        out_B_bottom_point = Point3D(x=out_B_top_point.x, y=out_B_top_point.y, z=foundation_top_z)
        in_B_bottom_point = Point3D(x=in_B_top_point.x, y=in_B_top_point.y, z=foundation_top_z)
        out_E_bottom_point = Point3D(x=out_E_top_point.x, y=out_B_top_point.y - bl_y , z=foundation_top_z)
        in_E_bottom_point = Point3D(x=in_E_top_point.x, y=in_B_top_point.y - bl_y , z=foundation_top_z)
        bottom_points = WingCorners(
            DB=out_B_bottom_point,
            DS=out_E_bottom_point,
            US=in_E_bottom_point,
            UB=in_B_bottom_point,
        )
        if ab_height == 0 and bl_height == 0:
            out_curve = const_closed_polycurve_obj([out_B_top_point, out_E_top_point, out_E_bottom_point, out_B_bottom_point])
            in_curve = const_closed_polycurve_obj([in_B_top_point, in_E_top_point, in_E_bottom_point, in_B_bottom_point])
            brep = const_srf_from_2crvs([out_curve, in_curve])
            capped_brep = brep.CapPlanarHoles(0.01)
            return capped_brep, top_points, top_points, bottom_points, bottom_points

        # 上面の下
        middle_wide_points = WingCorners(
            DB = Point3D(x=top_points.DB.x, y=top_points.DB.y, z=top_points.DB.z - ab_height),
            DS = Point3D(x=top_points.DS.x, y=top_points.DS.y, z=top_points.DS.z - ab_height),
            US = Point3D(x=top_points.US.x, y=top_points.US.y, z=top_points.US.z - ab_height),
            UB = Point3D(x=top_points.UB.x, y=top_points.UB.y, z=top_points.UB.z - ab_height),
        )
        #下面の上
        middle_narrow_points = WingCorners(
            DB = Point3D(x=bottom_points.DB.x, y=bottom_points.DB.y, z=middle_wide_points.DB.z - bl_height),
            DS = Point3D(x=bottom_points.DS.x, y=bottom_points.DS.y, z=middle_wide_points.DS.z - bl_height),
            US = Point3D(x=bottom_points.US.x, y=bottom_points.US.y, z=middle_wide_points.US.z - bl_height),
            UB = Point3D(x=bottom_points.UB.x, y=bottom_points.UB.y, z=middle_wide_points.UB.z - bl_height),
        )
        out_curve = const_closed_polycurve_obj([top_points.DB, top_points.DS, middle_wide_points.DS, middle_narrow_points.DS, bottom_points.DS, bottom_points.DB])
        in_curve = const_closed_polycurve_obj([top_points.UB, top_points.US, middle_wide_points.US, middle_narrow_points.US, bottom_points.US, bottom_points.UB])
        brep = const_srf_from_2crvs([out_curve, in_curve])
        capped_brep = brep.CapPlanarHoles(0.01)
        return capped_brep, top_points, middle_wide_points, middle_narrow_points, bottom_points
    
    D_wing_brep, D_top_points, D_middle_wide_points, D_middle_narrow_points, D_bottom_points = get_wing_from_data(
        out_B_top_point = DDB_top_point,
        in_B_top_point = DUB_top_point,
        out_edge_z = wing_info.D_z,
        ab_y = wing_info.Dab_y,
        bl_y = wing_info.Dbl_y,
        ab_height = wing_info.Dab_height,
        bl_height = wing_info.Dbl_height,
    )
    U_wing_brep, U_top_points, U_middle_wide_points, U_middle_narrow_points, U_bottom_points = get_wing_from_data(
        out_B_top_point = UUB_top_point,
        in_B_top_point = UDB_top_point,
        out_edge_z = wing_info.U_z,
        ab_y = wing_info.Uab_y,
        bl_y = wing_info.Ubl_y,
        ab_height = wing_info.Uab_height,
        bl_height = wing_info.Ubl_height,
    )
    def reverse_UD(corners: WingCorners) -> WingCorners:
        return WingCorners(
            UB=corners.DB,
            US=corners.DS,
            DS=corners.US,
            DB=corners.UB,
        )

    #U側はUとDが逆になっている
    U_top_points = reverse_UD(U_top_points)
    U_middle_wide_points = reverse_UD(U_middle_wide_points)
    U_middle_narrow_points = reverse_UD(U_middle_narrow_points)
    U_bottom_points = reverse_UD(U_bottom_points)
    return {
        "D_wing": D_wing_brep,
        "D_wing_top_points": D_top_points,
        "D_wing_middle_wide_points": D_middle_wide_points,
        "D_wing_middle_narrow_points": D_middle_narrow_points,
        "D_wing_bottom_points": D_bottom_points,
        "U_wing": U_wing_brep,
        "U_wing_top_points": U_top_points,
        "U_wing_middle_wide_points": U_middle_wide_points,
        "U_wing_middle_narrow_points": U_middle_narrow_points,
        "U_wing_bottom_points": U_bottom_points,
    }

def get_slabseat(
    double: bool,
    slabseat_info: SlabSeatInfo,
    Uwing_in_top_point: Point3D,
    Dwing_in_top_point: Point3D,
    Ubackwall_top_point_DN: Union[Point3D, None],
    Dbackwall_top_point_UN: Union[Point3D, None],
) -> dict[str, rg.Brep]:
    def get_slabseat_from_data(
        backwall_start_top_point: Point3D, 
        backwall_end_top_point: Point3D, 
    ) -> rg.Brep:
        def get_slabseat_curve(backwall_point):
            top_B = Point3D(x=backwall_point.x, y=backwall_point.y, z=backwall_point.z - slabseat_info.B_ab_height)
            bottom_B = Point3D(x=top_B.x, y=top_B.y, z=top_B.z - slabseat_info.height)
            top_E = Point3D(x=top_B.x, y=top_B.y - slabseat_info.y, z=backwall_point.z - slabseat_info.E_ab_height)
            bottom_E = Point3D(x=top_E.x, y=top_E.y, z=top_E.z - slabseat_info.straight_height)
            crv = const_closed_polycurve_obj([top_B, top_E, bottom_E, bottom_B])
            return crv
        start_crv = get_slabseat_curve(backwall_start_top_point)
        end_crv = get_slabseat_curve(backwall_end_top_point)
        brep = const_srf_from_2crvs([start_crv, end_crv])
        capped_brep = brep.CapPlanarHoles(0.01)
        return capped_brep
    if not double:
        slabseat_brep = get_slabseat_from_data(Uwing_in_top_point, Dwing_in_top_point)
        return {
            "slabseat": slabseat_brep,
        }
    else:
        U_start = Uwing_in_top_point
        U_end = get_point_by_xy_offset(
            point1=Uwing_in_top_point,
            point2=Ubackwall_top_point_DN,
            offset=slabseat_info.U_x,
        )
        D_start = Dwing_in_top_point
        D_end = get_point_by_xy_offset(
            point1=Dwing_in_top_point,
            point2=Dbackwall_top_point_UN,
            offset=slabseat_info.D_x,
        )
        U_slabseat_brep = get_slabseat_from_data(U_start, U_end)
        D_slabseat_brep = get_slabseat_from_data(D_start, D_end)
        return {
            "U_slabseat": U_slabseat_brep,
            "D_slabseat": D_slabseat_brep,
        }
        
def get_barrier(
    barrier_info: BarrierInfo,
    barrier_common_info: BarrierCommonInfo,
    UB_backwall_top_out_point: Point3D,
    DB_backwall_top_out_point: Point3D,
    UE_backwall_top_out_point: Point3D,
    DE_backwall_top_out_point: Point3D,
    UE_wing_top_out_point: Point3D,
    DE_wing_top_out_point: Point3D,
    UB_backwall_top_in_point: Point3D,
    DB_backwall_top_in_point: Point3D,
    UE_backwall_top_in_point: Point3D,
    DE_backwall_top_in_point: Point3D,
    UE_wing_top_in_point: Point3D,
    DE_wing_top_in_point: Point3D,
) -> dict[str, Union[rg.Brep, Point3D]]:
    slope = barrier_common_info.slope.value / 100

    def get_barrier_crv(
        bw_top_point_in: Point3D,
        bw_top_point_out: Point3D,
        overhang_width: float,
        UB: str,
    ) -> tuple[rg.PolylineCurve, Point3D]:
        y = bw_top_point_out.y
        if UB == "U":
            x_dir = -1
        else:
            x_dir = 1

        def get_barrier_points_sheared(
            base_bottom: Point3D,
        ) -> tuple[Point3D, Point3D, Point3D, Point3D]:
            y = base_bottom.y
            haunch_bottom = Point3D(x=base_bottom.x, y=y, z=base_bottom.z + (barrier_common_info.base_height + barrier_common_info.pavement_height))
            face_bottom = Point3D(x=haunch_bottom.x + x_dir * barrier_common_info.haunch_x, y=y, z=haunch_bottom.z + barrier_common_info.haunch_height)
            top_in = Point3D(x=face_bottom.x + x_dir * barrier_common_info.face_x, y=y, z=face_bottom.z + barrier_common_info.face_height)
            top_gap_x = barrier_common_info.x - (barrier_common_info.face_x + barrier_common_info.haunch_x)
            top_gap_z = slope * top_gap_x
            top_out = Point3D(x=top_in.x + x_dir * top_gap_x, y=y, z=top_in.z + top_gap_z)
            return top_out, top_in, face_bottom, haunch_bottom

        if overhang_width == 0:
            bottom_out = bw_top_point_out
            bottom_in = get_point_by_xy_offset(
                point1=bw_top_point_out,
                point2=bw_top_point_in,
                offset=barrier_common_info.x # 壁高欄の幅だけ内側にオフセット
            )
            top_out, top_in, face_bottom, haunch_bottom = get_barrier_points_sheared(
                base_bottom = bottom_in,
            )
            crv = const_closed_polycurve_obj([top_out, top_in, face_bottom, haunch_bottom, bottom_in, bottom_out])
            base_bottom = bottom_in

        else:
            base_point_in = bw_top_point_out # 壁高欄にとってのinはウィング等のout
            base_point_out = get_point_by_xy_offset(
                point1=bw_top_point_out,
                point2=bw_top_point_in,
                offset=-overhang_width, # 壁高欄の外側に出すのでマイナス
            )
            base_bottom = get_point_by_xy_offset(
                point1=base_point_in,
                point2=base_point_out,
                offset=overhang_width - barrier_common_info.x
            )
            if UB == "U":
                x_dir = -1
            else:
                x_dir = 1
            bottom_in = Point3D(x=base_point_in.x, y=y, z=base_point_in.z - barrier_common_info.edge_in_height)
            bottom_out = Point3D(x=base_point_out.x, y=y, z=base_point_out.z - barrier_common_info.edge_out_height)
            watertreatment_bottom = Point3D(x=base_point_out.x + x_dir * (- barrier_common_info.edge_watertreatment_x), y=y, z=bottom_out.z)
            watertreatment_top = Point3D(x=watertreatment_bottom.x, y=y, z=watertreatment_bottom.z + barrier_common_info.edge_watertreatment_height)
            top_out, top_in, face_bottom, haunch_bottom = get_barrier_points_sheared(
                base_bottom = base_bottom,
            )
            crv = const_closed_polycurve_obj([top_out, top_in, face_bottom, haunch_bottom, base_bottom, base_point_in, bottom_in, watertreatment_top, watertreatment_bottom, bottom_out]) 

        return crv, base_bottom # 壁高欄の基準点は今後使う

    UB_backwall_crv, UB_backwall_base_bottom = get_barrier_crv(
        bw_top_point_in = UB_backwall_top_in_point,
        bw_top_point_out = UB_backwall_top_out_point,
        overhang_width = barrier_info.BU_overhang_width,
        UB = "U",
    )
    DB_backwall_crv, DB_backwall_base_bottom = get_barrier_crv(
        bw_top_point_in = DB_backwall_top_in_point,
        bw_top_point_out = DB_backwall_top_out_point,
        overhang_width = barrier_info.BD_overhang_width,
        UB = "D",
    )
    UE_backwall_crv, UE_backwall_base_bottom = get_barrier_crv(
        bw_top_point_in = UE_backwall_top_in_point,
        bw_top_point_out = UE_backwall_top_out_point,
        overhang_width = barrier_info.BU_overhang_width, # ここは同じ
        UB = "U",
    )
    DE_backwall_crv, DE_backwall_base_bottom = get_barrier_crv(
        bw_top_point_in = DE_backwall_top_in_point,
        bw_top_point_out = DE_backwall_top_out_point,
        overhang_width = barrier_info.BD_overhang_width,
        UB = "D",
    )
    UE_wing_crv, UE_wing_base_bottom = get_barrier_crv(
        bw_top_point_in = UE_wing_top_in_point,
        bw_top_point_out = UE_wing_top_out_point,
        overhang_width = barrier_info.EU_overhang_width,
        UB = "U",
    )
    DE_wing_crv, DE_wing_base_bottom = get_barrier_crv(
        bw_top_point_in = DE_wing_top_in_point,
        bw_top_point_out = DE_wing_top_out_point,
        overhang_width = barrier_info.ED_overhang_width,
        UB = "D",
    )
    U_backwall_barrier = const_srf_from_2crvs([UB_backwall_crv, UE_backwall_crv])
    D_backwall_barrier = const_srf_from_2crvs([DB_backwall_crv, DE_backwall_crv])
    U_wing_barrier = const_srf_from_2crvs([UE_backwall_crv, UE_wing_crv])
    D_wing_barrier = const_srf_from_2crvs([DE_backwall_crv, DE_wing_crv]) 
    U_barrier = join_breps_or_raise([U_backwall_barrier, U_wing_barrier], context="abut U barrier").CapPlanarHoles(0.01)
    D_barrier = join_breps_or_raise([D_backwall_barrier, D_wing_barrier], context="abut D barrier").CapPlanarHoles(0.01)
    return {
        "U_barrier": U_barrier,
        "D_barrier": D_barrier,
        "UB_backwall_base_bottom": UB_backwall_base_bottom,
        "DB_backwall_base_bottom": DB_backwall_base_bottom,
        "UE_backwall_base_bottom": UE_backwall_base_bottom,
        "DE_backwall_base_bottom": DE_backwall_base_bottom,
        "UE_wing_base_bottom": UE_wing_base_bottom,
        "DE_wing_base_bottom": DE_wing_base_bottom,
    }

def get_each_abut(
    input_indiv_info: InputAbutInfo,
    input_common_info: CommonAbutInfo,
):
    # 橋脚のローカル2D座標系を求める
    point_u = input_indiv_info.points_for_vector.point_u
    point_d = input_indiv_info.points_for_vector.point_d
    direction = input_indiv_info.direction
    frame_2D = get_frame_2D(
        point_u=Point2D(x=point_u.x, y=point_u.y),
        point_d=Point2D(x=point_d.x, y=point_d.y),
        y_direction=direction, # 始点側の場合UPが入っている。橋側をｙの正方向とする。
    )

    # ゼロ点の座標を得る。ただし今回は高さは全て絶対評価なので0とする。
    ref_point = input_indiv_info.ref_point
    zero_point = Point3D(ref_point.x, ref_point.y, 0)

    # 上下線一体の橋台かどうか
    double = True if input_indiv_info.seat.UD_z != 0 else False

    # 基礎の上面の高さ
    if not pd.isna(input_indiv_info.footing):
        foundation_top_z = input_indiv_info.footing.top_z
    elif not pd.isna(input_indiv_info.caisson):
        foundation_top_z = input_indiv_info.caisson.top_z
    else:
        raise ValueError("基礎がありません。footingかcaissonのどちらかの情報が必要です。")

    # 1. 橋座を得る
    beamseat_dict = get_beamseat(
        double = double,
        seat_info = input_indiv_info.seat,
        foundation_top_z = foundation_top_z,
    )

    # 2. パラペットを得る
    backwall_dict = get_backwall(
        double = double,
        backwall_info = input_indiv_info.backwall,
        foundation_top_z = foundation_top_z,
        seat_info = input_indiv_info.seat,
        BD_overhang_width=input_indiv_info.barrier.BD_overhang_width,
        BU_overhang_width=input_indiv_info.barrier.BU_overhang_width,
    )

    # 3. ウィングを得る
    wing_dict = get_wings(
        double = double,
        wing_info = input_indiv_info.wing,
        foundation_top_z = foundation_top_z,
        backwall_dict = backwall_dict,
    )
    
    # 4. 踏みかけ版掛けを得る
    slabseat_dict = get_slabseat(
        double = double,
        slabseat_info = input_indiv_info.slab_seat,
        Uwing_in_top_point = wing_dict["U_wing_top_points"].DB,
        Dwing_in_top_point = wing_dict["D_wing_top_points"].UB,
        Ubackwall_top_point_DN = backwall_dict["U_backwall_top_corners"].DN if double else None,
        Dbackwall_top_point_UN = backwall_dict["D_backwall_top_corners"].UN if double else None,
    )

    # 5. 壁高欄を得る
    barrier_dict = get_barrier(
        barrier_info = input_indiv_info.barrier,
        barrier_common_info = input_common_info.barrier_common_info,
        UB_backwall_top_out_point = backwall_dict["U_backwall_top_corners"].UT if double else backwall_dict["backwall_top_corners"].UT,
        DB_backwall_top_out_point = backwall_dict["D_backwall_top_corners"].DT if double else backwall_dict["backwall_top_corners"].DT,
        UE_backwall_top_out_point = backwall_dict["U_backwall_top_corners"].UN if double else backwall_dict["backwall_top_corners"].UN,
        DE_backwall_top_out_point = backwall_dict["D_backwall_top_corners"].DN if double else backwall_dict["backwall_top_corners"].DN,
        UE_wing_top_out_point = wing_dict["U_wing_top_points"].US,
        DE_wing_top_out_point = wing_dict["D_wing_top_points"].DS,
        UB_backwall_top_in_point = backwall_dict["U_backwall_top_corners"].DT if double else backwall_dict["backwall_top_corners"].DT,
        DB_backwall_top_in_point = backwall_dict["D_backwall_top_corners"].UT if double else backwall_dict["backwall_top_corners"].UT,
        UE_backwall_top_in_point = backwall_dict["U_backwall_top_corners"].DN if double else backwall_dict["backwall_top_corners"].DN,
        DE_backwall_top_in_point = backwall_dict["D_backwall_top_corners"].UN if double else backwall_dict["backwall_top_corners"].UN,
        UE_wing_top_in_point = wing_dict["U_wing_top_points"].DS,
        DE_wing_top_in_point = wing_dict["D_wing_top_points"].US,
    )

    beamseat = beamseat_dict["beamseat"]
    backwall = backwall_dict["backwall"]
    D_wing = wing_dict["D_wing"]
    U_wing = wing_dict["U_wing"]
    slabseat = slabseat_dict["slabseat"] if not double else None
    D_slabseat = slabseat_dict["D_slabseat"] if double else None
    U_slabseat = slabseat_dict["U_slabseat"] if double else None
    D_barrier = barrier_dict["D_barrier"]
    U_barrier = barrier_dict["U_barrier"]
    UB_backwall_base_bottom = barrier_dict["UB_backwall_base_bottom"]
    DB_backwall_base_bottom = barrier_dict["DB_backwall_base_bottom"]
    UE_backwall_base_bottom = barrier_dict["UE_backwall_base_bottom"]
    DE_backwall_base_bottom = barrier_dict["DE_backwall_base_bottom"]
    UE_wing_base_bottom = barrier_dict["UE_wing_base_bottom"]
    DE_wing_base_bottom = barrier_dict["DE_wing_base_bottom"]
    U_wing_inside_bridge_point = wing_dict["U_wing_top_points"].DB
    U_wing_inside_soil_point = wing_dict["U_wing_top_points"].DS
    D_wing_inside_soil_point = wing_dict["D_wing_top_points"].US
    D_wing_inside_bridge_point = wing_dict["D_wing_top_points"].UB
    def get_center_soil_points(bridge_point, soil_point):
        return [
            bridge_point,
            soil_point,
            Point3D(x=soil_point.x, y=soil_point.y, z=foundation_top_z),
            Point3D(x=bridge_point.x, y=bridge_point.y, z=foundation_top_z),
        ]

    def get_center_soil_end_point(bridge_point):
        x_length = D_wing_inside_bridge_point.x - U_wing_inside_bridge_point.x
        if abs(x_length) < 0.01:
            return U_wing_inside_soil_point
        ratio = (bridge_point.x - U_wing_inside_bridge_point.x) / x_length
        return interpolate_point_3d(
            U_wing_inside_soil_point,
            D_wing_inside_soil_point,
            ratio,
        )

    def same_center_section(section1, section2):
        return (
            const_point_obj(section1[0]).DistanceTo(const_point_obj(section2[0])) < 0.01
            and const_point_obj(section1[1]).DistanceTo(const_point_obj(section2[1])) < 0.01
        )

    def get_center_soil_brep(center_sections):
        unique_sections = []
        for section in center_sections:
            if not unique_sections or not same_center_section(unique_sections[-1], section):
                unique_sections.append(section)
        center_breps = [
            const_brep_from_two_closed_point_lists(section1, section2)
            for i, (section1, section2) in enumerate(zip(unique_sections, unique_sections[1:]))
        ]
        if len(center_breps) == 1:
            return center_breps[0]
        unioned = rg.Brep.CreateBooleanUnion(center_breps, 0.01)
        if not unioned or len(unioned) != 1:
            raise ValueError(f"Failed to union center soil breps. count={len(center_breps)}")
        capped_brep = unioned[0].CapPlanarHoles(0.01)
        return capped_brep if capped_brep is not None else unioned[0]

    if double:
        center_soil_brep = get_center_soil_brep([
            get_center_soil_points(
                U_wing_inside_bridge_point,
                U_wing_inside_soil_point,
            ),
            get_center_soil_points(
                backwall_dict["U_backwall_top_corners"].DN,
                get_center_soil_end_point(backwall_dict["U_backwall_top_corners"].DN),
            ),
            get_center_soil_points(
                backwall_dict["C_backwall_top_corners"].UN,
                get_center_soil_end_point(backwall_dict["C_backwall_top_corners"].UN),
            ),
            get_center_soil_points(
                backwall_dict["C_backwall_top_corners"].DN,
                get_center_soil_end_point(backwall_dict["C_backwall_top_corners"].DN),
            ),
            get_center_soil_points(
                backwall_dict["D_backwall_top_corners"].UN,
                get_center_soil_end_point(backwall_dict["D_backwall_top_corners"].UN),
            ),
            get_center_soil_points(
                D_wing_inside_bridge_point,
                D_wing_inside_soil_point,
            ),
        ])
    else:
        center_soil_brep = const_brep_from_two_closed_point_lists(
            get_center_soil_points(
                U_wing_inside_bridge_point,
                U_wing_inside_soil_point,
            ),
            get_center_soil_points(
                D_wing_inside_bridge_point,
                D_wing_inside_soil_point,
            ),
        )

    def get_wing_under_soil_points(middle_wide, middle_narrow, bottom):
        middle_wide_bottom = Point3D(
            x=middle_wide.x,
            y=middle_wide.y,
            z=foundation_top_z,
        )
        return [
            middle_wide,
            middle_narrow,
            bottom,
            middle_wide_bottom,
        ]

    def get_wing_under_soil_brep(U_inside_points, D_inside_points):
        if len(remove_same_points(U_inside_points)) < 3 or len(remove_same_points(D_inside_points)) < 3:
            return None
        return const_brep_from_two_closed_point_lists(
            U_inside_points,
            D_inside_points,
        )

    U_wing_under_soil_brep = get_wing_under_soil_brep(
        U_inside_points=get_wing_under_soil_points(
            wing_dict["U_wing_middle_wide_points"].DS,
            wing_dict["U_wing_middle_narrow_points"].DS,
            wing_dict["U_wing_bottom_points"].DS,
        ),
        D_inside_points=get_wing_under_soil_points(
            wing_dict["U_wing_middle_wide_points"].US,
            wing_dict["U_wing_middle_narrow_points"].US,
            wing_dict["U_wing_bottom_points"].US,
        ),
    )
    D_wing_under_soil_brep = get_wing_under_soil_brep(
        U_inside_points=get_wing_under_soil_points(
            wing_dict["D_wing_middle_wide_points"].US,
            wing_dict["D_wing_middle_narrow_points"].US,
            wing_dict["D_wing_bottom_points"].US,
        ),
        D_inside_points=get_wing_under_soil_points(
            wing_dict["D_wing_middle_wide_points"].DS,
            wing_dict["D_wing_middle_narrow_points"].DS,
            wing_dict["D_wing_bottom_points"].DS,
        ),
    )
    soil_dict = {
        "center": center_soil_brep,
        "U_wing_under": U_wing_under_soil_brep,
        "D_wing_under": D_wing_under_soil_brep,
    }

    def place_obj_setting(obj):
        if obj is None:
            return None
        return place_obj(
            obj=obj,
            local_origin=Point3D(0,0,0),
            world_origin=zero_point,
            frame_2D=frame_2D,
        )
    def place_point_setting(point):
        if point is None:
            return None
        return const_3Dpoint(place_obj_setting(point))

    def place_point_data(obj):
        if obj is None:
            return None
        if isinstance(obj, (Point2D, Point3D, rg.Point3d)):
            return place_point_setting(obj)
        if isinstance(obj, dict):
            return {
                key: place_point_data(value)
                for key, value in obj.items()
            }
        if isinstance(obj, (list, tuple)):
            return [
                place_point_data(value)
                for value in obj
            ]
        if hasattr(obj, "__dict__"):
            return {
                key: place_point_data(value)
                for key, value in obj.__dict__.items()
                if not key.startswith("_")
            }
        return obj

    def collect_point_data(source_dict):
        point_key_tokens = ("point", "points", "corner", "corners", "bottom")
        return {
            key: place_point_data(value)
            for key, value in source_dict.items()
            if any(token in key for token in point_key_tokens)
        }

    abut_points = {
        "beamseat_dict": collect_point_data(beamseat_dict),
        "backwall_dict": collect_point_data(backwall_dict),
        "wing_dict": collect_point_data(wing_dict),
        "slabseat_dict": collect_point_data(slabseat_dict),
        "barrier_dict": collect_point_data(barrier_dict),
    }

    # 上面のデータは必要(ワールド座標）
    if not double:
        top_surf_corners = [
            Square_Corners(
                DT = const_3Dpoint(place_point_setting(beamseat_dict["beamseat_top_corners"].DT)),
                DN = const_3Dpoint(place_point_setting(beamseat_dict["beamseat_top_corners"].DN)),
                UT = const_3Dpoint(place_point_setting(beamseat_dict["beamseat_top_corners"].UT)),
                UN = const_3Dpoint(place_point_setting(beamseat_dict["beamseat_top_corners"].UN))
            )
        ]
    else:
        top_surf_corners = [
            Square_Corners(
                DT = const_3Dpoint(place_point_setting(beamseat_dict["U_beamseat_top_corners"].DT)),
                DN = const_3Dpoint(place_point_setting(beamseat_dict["U_beamseat_top_corners"].DN)),
                UT = const_3Dpoint(place_point_setting(beamseat_dict["U_beamseat_top_corners"].UT)),
                UN = const_3Dpoint(place_point_setting(beamseat_dict["U_beamseat_top_corners"].UN))
            ),
            Square_Corners(
                DT = const_3Dpoint(place_point_setting(beamseat_dict["D_beamseat_top_corners"].DT)),
                DN = const_3Dpoint(place_point_setting(beamseat_dict["D_beamseat_top_corners"].DN)),
                UT = const_3Dpoint(place_point_setting(beamseat_dict["D_beamseat_top_corners"].UT)),
                UN = const_3Dpoint(place_point_setting(beamseat_dict["D_beamseat_top_corners"].UN))
            ),
        ]


    return ({
        "橋座": place_obj_setting(beamseat),
        "パラペット": place_obj_setting(backwall),
        "ウィング_下": place_obj_setting(D_wing),
        "ウィング_上": place_obj_setting(U_wing),
        "踏掛版受け": place_obj_setting(slabseat),
        "踏掛版受け_下": place_obj_setting(D_slabseat),
        "踏掛版受け_上": place_obj_setting(U_slabseat),
    },
    {
        "壁高欄_下": place_obj_setting(D_barrier),
        "壁高欄_上": place_obj_setting(U_barrier),
    },
    {
        "UB_backwall": place_point_setting(UB_backwall_base_bottom),
        "DB_backwall": place_point_setting(DB_backwall_base_bottom),
        "UE_backwall": place_point_setting(UE_backwall_base_bottom),
        "DE_backwall": place_point_setting(DE_backwall_base_bottom),
        "UE_wing": place_point_setting(UE_wing_base_bottom),
        "DE_wing": place_point_setting(DE_wing_base_bottom),
    },
    abut_points,
    foundation_top_z,
    {
        key: place_obj_setting(brep)
        for key, brep in soil_dict.items()
        if brep is not None
    },
    {
        "frame_2D": frame_2D,
        "top_corners": top_surf_corners,
    })


def main(initial_or_final: str):
    DIR = get_output_dir(initial_or_final)

    indiv_infos = load_from_pickle(DIR / f"{Filenames.INPUT}_{Filenames.ABUT}_{Filenames.INDIV}.pickle")
    common_info_dict = load_from_pickle(DIR / f"{Filenames.INPUT}_{Filenames.ABUT}_{Filenames.COMMON}.pickle")
    abut_footing_top_points_dict = load_from_pickle(
        DIR / f"{Filenames.WORLD}_{Filenames.ABUT}_{Filenames.FOOTING}_{Filenames.TOP}_{Filenames.POINTS}.pickle"
    )
    barrier_base_bottom_dict = {}
    abut_points_dict = {}
    local_top_surf_corners_dict = {}
    world_items_dict_for_bake = {}
    world_items_dict_for_bake_2 = {}
    world_items_dict_for_bake_3 = {}

    for abut_name, indiv_info in indiv_infos.items():
        bridge_type = indiv_info.bridge_type
        common_info = common_info_dict[bridge_type]
        abut_dict, barrier_dict, barrier_base_point_dict, abut_points, foundation_top_z, soil_dict, top_surf_corners_dict = get_each_abut(
            input_indiv_info = indiv_info,
            input_common_info = common_info,
        )

        barrier_base_bottom_dict[abut_name] = {
            "pavement_height": common_info.barrier_common_info.pavement_height,
            "foundation_top_z": foundation_top_z,
            "points": barrier_base_point_dict,
        } # ここはpickel用
        if abut_name in abut_footing_top_points_dict:
            abut_points["footing_dict"] = {
                "footing_top_points": get_named_footing_top_points(
                    footing_top_points=abut_footing_top_points_dict[abut_name],
                    abut_points=abut_points,
                )
            }
        abut_points_dict[abut_name] = abut_points
        frame_2D = top_surf_corners_dict["frame_2D"]
        top_surf_corners = top_surf_corners_dict["top_corners"]
        if len(top_surf_corners) == 1:
            local_top_surf_corners_dict[abut_name] = {
                "frame_2D": frame_2D,
                "top_corners": top_surf_corners[0],
            }
        else:
            local_top_surf_corners_dict[f"{abut_name}A"] = {
                "frame_2D": frame_2D,
                "top_corners": top_surf_corners[0],
            }
            local_top_surf_corners_dict[f"{abut_name}B"] = {
                "frame_2D": frame_2D,
                "top_corners": top_surf_corners[1],
            }
        
        world_items_dict_for_bake[abut_name] = abut_dict # ここはbake用
        world_items_dict_for_bake_2[abut_name] = barrier_dict # ここはbake用
        world_items_dict_for_bake_3[f"{abut_name}_soil"] = soil_dict
    
    # 壁高欄起点情報を全部pickelに保存
    save_json_and_pickle(
        data = barrier_base_bottom_dict,
        folder_path = DIR,
        name = f"{Filenames.WORLD}_{Filenames.ABUT}_{Filenames.BARRIER}_{Filenames.BASE_POINT}",
    )
    save_json_and_pickle(
        data = local_top_surf_corners_dict,
        folder_path = DIR,
        name = f"{Filenames.WORLD}_{Filenames.ABUT}_{Filenames.TOP}_{Filenames.POINTS}",
    )
    save_json_and_pickle(
        data = abut_points_dict,
        folder_path = DIR,
        name = f"{Filenames.WORLD}_{Filenames.ABUT}_{Filenames.POINTS}",
    )
    def get_keys_and_values_for_bake(world_items_dict):
        flatten_dict_for_bake = flatten_any(world_items_dict)
        items = list(flatten_dict_for_bake.items())
        # valueがNoneのものはbakeできないので除外
        items = [(k,v) for k,v in items if v is not None]
        keys = [k for k, _ in items]
        values = [v for _, v in items]
        return keys, values
    return (
        get_keys_and_values_for_bake(world_items_dict_for_bake),
        get_keys_and_values_for_bake(world_items_dict_for_bake_2),
        get_keys_and_values_for_bake(world_items_dict_for_bake_3),
    )

if __name__ == "__main__":
    (bake_keys, bake_objs), (bake_keys2, bake_objs2), (bake_keys3, bake_objs3) = main("initial")
