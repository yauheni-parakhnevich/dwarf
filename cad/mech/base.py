"""The wet zone: what holds the bought vessel, pump and valve."""
from build123d import Pos, Rot
from bd_warehouse.thread import IsoThread
import params as P
from mech import part
from mech.common import cyl_z, cyl_x, box

# --- tank head -----------------------------------------------------------------------------
# Modelled in its own frame, lying along +X with the thread's mouth at x = 0: it is a print
# coupon before it is an assembly, and the canister it screws onto is a bought part whose
# listed size does not yet fit the base (see the wet-zone note in the tests).
TANK_HEAD_R = P.CAN_THREAD_MAJOR / 2 + 3.0          # 22, three millimetres of wall on the thread
TANK_HEAD_L = P.CAN_THREAD_LEN + 4                  # 16, thread plus the end wall
BORE_R = P.CAN_THREAD_MAJOR / 2 + 0.2               # the thread is cut into this bore
THREAD_X = 0.5                                      # where the thread starts inside the bore

# Ports through the end wall as (y, z, radius). Everything that reaches the liquid has to pass
# the canister's own neck, so all four live inside a circle of CAN_NECK_ID / 2 with a
# millimetre of rim and a millimetre between them. The filler is the one that does not fit at
# its full FILLER_D: its throat necks down here and opens out again inside the stub.
PORTS = {
    "filler": (-7.0, 0.0, 7.0),
    "float": (8.0, 0.0, P.FLOAT_HOLE_D / 2),
    "dip": (0.0, -10.0, P.DIP_TUBE_D / 2),
    "vent": (0.0, 10.0, 1.5),
}

# --- filler cap ----------------------------------------------------------------------------
CAP_R = P.FILLER_CAP_THREAD_MAJOR / 2 + 3           # 15
CAP_BORE_R = P.FILLER_CAP_THREAD_MAJOR / 2 + 0.2    # 12.2
CAP_END_T = 4.0                                     # the closed end, which the O-ring seats in
CAP_L = 14.0
CAP_THREAD_X = CAP_END_T + 0.5
CAP_THREAD_LEN = 9.0


def can_thread():
    """The canister thread, where it sits in the tank head's bore."""
    thread = IsoThread(major_diameter=P.CAN_THREAD_MAJOR + 0.4, pitch=P.CAN_THREAD_PITCH,
                       length=P.CAN_THREAD_LEN - 1, external=False, end_finishes=("fade", "fade"))
    return Pos(THREAD_X, 0, 0) * Rot(0, 90, 0) * thread


def filler_neck():
    """The neck the filler cap screws onto, in the cap's own frame.

    Not printed here - it belongs to the back of the base's shell - but the cap is cut to it,
    so the mating half is worth having to test against. Its crests stand at FILLER_D + 4 and
    its bore is FILLER_D, which leaves 0.92 mm of wall at the thread's roots.

    Its thread is a millimetre shorter than the cap's at both ends, so its square ends never
    meet the faded ends of the cap's.
    """
    thread = IsoThread(major_diameter=P.FILLER_CAP_THREAD_MAJOR, pitch=P.FILLER_CAP_PITCH,
                       length=CAP_THREAD_LEN - 2.0, external=True, end_finishes=("square", "square"))
    neck = Pos(CAP_THREAD_X + 1.0, 0, 0) * Rot(0, 90, 0) * thread
    neck = neck + cyl_x(thread.min_radius, CAP_END_T, CAP_THREAD_X + CAP_THREAD_LEN + 10)
    return neck - cyl_x(P.FILLER_D / 2, CAP_END_T - 1, CAP_THREAD_X + CAP_THREAD_LEN + 11)


@part("tank_head")
def tank_head():
    """Screws onto the canister's neck. Carries the dip tube, the float switch, a vent and the filler.

    The thread is retention only - the canister's own gasket seals - so it is cut 0.4 mm over
    size into a bore that is the thread's own major diameter, and it fades at both ends.
    """
    cap = cyl_x(TANK_HEAD_R, 0, TANK_HEAD_L)
    cap = cap - cyl_x(BORE_R, -1, P.CAN_THREAD_LEN)                        # thread bore
    cap = cap + can_thread()
    for y, z, r in PORTS.values():                                         # ports through the end wall
        cap = cap - cyl_x(r, P.CAN_THREAD_LEN - 1, TANK_HEAD_L + 0.01, y, z)
    # filler stub out the back, its bore opening out of the throat at the end wall's face
    fy, fz, _ = PORTS["filler"]
    cap = cap + cyl_x(P.FILLER_D / 2 + 2, TANK_HEAD_L - 0.01, TANK_HEAD_L + 20, fy, fz)
    return cap - cyl_x(P.FILLER_D / 2, TANK_HEAD_L, TANK_HEAD_L + 21, fy, fz)


@part("tank_cradle")
def tank_cradle():
    """Two saddles the lying canister rests in, off the floor's drain slots."""
    L, W, H = P.CANISTER
    cx, cy = P.CANISTER_XY
    z0 = P.Z_FLOOR
    saddle = None
    for x in (cx - L / 3, cx + L / 3):
        s = box(x - 10, x + 10, cy - W / 2 - 4, cy + W / 2 + 4, z0, z0 + 14)
        s = s - box(x - 11, x + 11, cy - W / 2, cy + W / 2, z0 + 6, z0 + 15)
        saddle = s if saddle is None else saddle + s
    return saddle + box(cx - L / 3, cx + L / 3, cy - 8, cy + 8, z0, z0 + 4)


@part("filler_cap")
def filler_cap():
    """Retention thread only; an O-ring in the groove seals."""
    cap = cyl_x(CAP_R, 0, CAP_L) + cyl_x(CAP_R + 4, 0, 4)                  # body plus a grip flange
    cap = cap - cyl_x(CAP_BORE_R, CAP_END_T, CAP_L + 1)
    thread = IsoThread(major_diameter=P.FILLER_CAP_THREAD_MAJOR + 0.4, pitch=P.FILLER_CAP_PITCH,
                       length=CAP_THREAD_LEN, external=False, end_finishes=("fade", "fade"))
    cap = cap + Pos(CAP_THREAD_X, 0, 0) * Rot(0, 90, 0) * thread
    # O-ring groove in the seat face, straddling the neck's rim
    groove = cyl_x(11.5, CAP_END_T - 1.5, CAP_END_T + 0.01) - cyl_x(9.5, CAP_END_T - 1.6, CAP_END_T + 0.1)
    return cap - groove


@part("pump_mount")
def pump_mount():
    """Four grommet pockets under the pump's feet."""
    L, W, H = P.PUMP
    fx, fy = P.PUMP_FEET
    cx, cy = P.PUMP_XY
    z0 = P.Z_FLOOR
    m = box(cx - fx / 2 - 8, cx + fx / 2 + 8, cy - fy / 2 - 8, cy + fy / 2 + 8, z0, z0 + 4)
    for dx in (-1, 1):
        for dy in (-1, 1):
            x = cx + dx * fx / 2
            y = cy + dy * fy / 2
            m = m + cyl_z(7, z0 + 3.99, z0 + 10, x, y) - cyl_z(4.5, z0 + 4, z0 + 11, x, y)
    m = m - box(cx - fx / 2 + 12, cx + fx / 2 - 12, cy - fy / 2 + 12, cy + fy / 2 - 12, z0 - 1, z0 + 5)   # lighten
    return m
