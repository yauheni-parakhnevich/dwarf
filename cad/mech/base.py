"""The wet zone: what holds the bought vessel, pump and valve.

The canister lies centred on the floor in its cradle and the pump is bridged straight above
it on four legs that stand beside its ends, with the valve beside the pump on the same plate.
Nothing in here is wider than the base's circle any more.
"""
import math
from build123d import Location, Pos, Rot
from bd_warehouse.thread import IsoThread
import params as P
from mech import part
from mech.common import cyl_z, cyl_x, box, insert_holes

# --- tank head -----------------------------------------------------------------------------
TANK_HEAD_R = P.CAN_THREAD_MAJOR / 2 + 3.0          # 22, three millimetres of wall on the thread
TANK_HEAD_L = P.CAN_THREAD_LEN + 4                  # 16, thread plus the end wall
BORE_R = P.CAN_THREAD_MAJOR / 2 + 0.2               # the thread is cut into this bore
THREAD_X = 0.5                                      # where the thread starts inside the bore
STUB_L = 16.0                                       # the filler stub, long enough for a barb

# It is modelled along +X from the thread's mouth and then turned to face the canister's neck,
# which points -X, so the filler stub points -X too, out towards the back of the base.
TANK_HEAD_AT = Location((P.CANISTER_XY[0] - P.CANISTER[0] / 2, P.CANISTER_XY[1],
                         P.CANISTER_Z0 + P.CANISTER[2] / 2), (0, 0, 180))

# Ports through the end wall as (y, z, radius). Everything that reaches the liquid has to pass
# the canister's own neck, so all four live inside a circle of CAN_NECK_ID / 2 with a
# millimetre of rim and a millimetre between them. The dip tube is lowest, the vent highest.
PORTS = {
    "filler": (-7.0, 0.0, P.FILLER_D / 2),
    "float": (8.0, 0.0, P.FLOAT_HOLE_D / 2),
    "dip": (0.0, -10.0, P.DIP_TUBE_D / 2),
    "vent": (0.0, 10.0, 1.5),
}

# --- filler cap ----------------------------------------------------------------------------
CAP_R = P.FILLER_CAP_THREAD_MAJOR / 2 + 3           # 14
CAP_BORE_R = P.FILLER_CAP_THREAD_MAJOR / 2 + 0.2    # 11.2
CAP_END_T = 4.0                                     # the closed end, which the O-ring seats in
CAP_L = 14.0
CAP_THREAD_X = CAP_END_T + 0.5
CAP_THREAD_LEN = 9.0
# the groove straddles the neck's rim, which is the ring between its bore and its thread roots
GROOVE_R = (P.FILLER_D / 2 + 0.4, P.FILLER_CAP_THREAD_MAJOR / 2 - 1.4)

# --- pump mount ----------------------------------------------------------------------------
PLATE_Z0 = P.PUMP_Z0 - 6.0                          # 141, four millimetres over the canister
PLATE_Z1 = P.PUMP_Z0 - 2.0                          # 145; the feet stand on grommets above it
PLATE_MARGIN = 8.0
BOSS_R = 7.0
BOSS_Z0 = PLATE_Z0 - 2.5                            # 138.5, so a boss still clears the canister
GROMMET_R = 4.5
GROMMET_DEPTH = 5.0
STRAP_X = P.VALVE[0] / 2 + BOSS_R + 1.0             # 30.5; the strap's bosses miss the valve
STRAP_TOP = PLATE_Z1 + 2.0                          # the strap bridges the valve at its feet


def can_thread():
    """The canister thread, where it sits in the tank head's bore. The part's own frame."""
    thread = IsoThread(major_diameter=P.CAN_THREAD_MAJOR + 0.4, pitch=P.CAN_THREAD_PITCH,
                       length=P.CAN_THREAD_LEN - 1, external=False, end_finishes=("fade", "fade"))
    return Pos(THREAD_X, 0, 0) * Rot(0, 90, 0) * thread


def filler_neck():
    """The neck the filler cap screws onto, in the cap's own frame.

    Not printed here - it belongs to the back of the base's shell - but the cap is cut to it,
    so the mating half is worth having to test against. Its crests stand at
    FILLER_CAP_THREAD_MAJOR over a FILLER_D bore, which leaves 2.9 mm of wall at its roots.

    Its thread is a millimetre shorter than the cap's at both ends, so its square ends never
    meet the faded ends of the cap's.
    """
    thread = IsoThread(major_diameter=P.FILLER_CAP_THREAD_MAJOR, pitch=P.FILLER_CAP_PITCH,
                       length=CAP_THREAD_LEN - 2.0, external=True, end_finishes=("square", "square"))
    neck = Pos(CAP_THREAD_X + 1.0, 0, 0) * Rot(0, 90, 0) * thread
    neck = neck + cyl_x(thread.min_radius, CAP_END_T, CAP_THREAD_X + CAP_THREAD_LEN + 10)
    return neck - cyl_x(P.FILLER_D / 2, CAP_END_T - 1, CAP_THREAD_X + CAP_THREAD_LEN + 11)


def _tank_head():
    """The tank head in its own frame, mouth at x = 0 and the stub running out along +X."""
    cap = cyl_x(TANK_HEAD_R, 0, TANK_HEAD_L)
    cap = cap - cyl_x(BORE_R, -1, P.CAN_THREAD_LEN)                        # thread bore
    cap = cap + can_thread()
    for y, z, r in PORTS.values():                                         # ports through the end wall
        cap = cap - cyl_x(r, P.CAN_THREAD_LEN - 1, TANK_HEAD_L + 0.01, y, z)
    fy, fz, _ = PORTS["filler"]                                            # filler stub, bored right through
    cap = cap + cyl_x(P.FILLER_CAP_THREAD_MAJOR / 2, TANK_HEAD_L - 0.01, TANK_HEAD_L + STUB_L, fy, fz)
    return cap - cyl_x(P.FILLER_D / 2, P.CAN_THREAD_LEN - 1, TANK_HEAD_L + STUB_L + 1, fy, fz)


@part("tank_head")
def tank_head():
    """Screws onto the canister's neck. Carries the dip tube, the float switch, a vent and the filler.

    The thread is retention only - the canister's own gasket seals - so it is cut 0.4 mm over
    size into a bore that is the thread's own major diameter, and it fades at both ends. The
    stub takes the tube that runs to the filler cap at the back of the base.
    """
    return TANK_HEAD_AT * _tank_head()


@part("tank_cradle")
def tank_cradle():
    """Two saddles the lying canister rests in, off the floor's drain slots.

    They stand a third of the canister's length either side of the middle and well inboard of
    the pump mount's legs, which come down past the canister's ends.
    """
    L, W, H = P.CANISTER
    cx, cy = P.CANISTER_XY
    z0 = P.Z_FLOOR
    rise = P.CANISTER_Z0 - z0                                              # the canister's bed height
    saddle = None
    for x in (cx - L / 3, cx + L / 3):
        s = box(x - 10, x + 10, cy - W / 2 - 4, cy + W / 2 + 4, z0, z0 + rise + 8)
        s = s - box(x - 11, x + 11, cy - W / 2, cy + W / 2, z0 + rise, z0 + rise + 9)
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
    r0, r1 = GROOVE_R                                                      # O-ring groove in the seat face
    groove = cyl_x(r1, CAP_END_T - 1.5, CAP_END_T + 0.01) - cyl_x(r0, CAP_END_T - 1.6, CAP_END_T + 0.1)
    return cap - groove


def _feet_xy():
    fx, fy = P.PUMP_FEET
    return [(sx * fx / 2, sy * fy / 2) for sx in (-1, 1) for sy in (-1, 1)]


def _legs_xy():
    lx, ly = P.PUMP_LEG_XY
    return [(sx * lx, sy * ly) for sx in (-1, 1) for sy in (-1, 1)]


def _strap_xy():
    vx, vy = P.VALVE_XY
    return [(vx - STRAP_X, vy), (vx + STRAP_X, vy)]


@part("pump_mount")
def pump_mount():
    """The bridge over the canister: the pump on grommets, the valve beside it, four legs down.

    The plate is only as wide as the pump's feet want, with a pad reaching back to the valve
    and four arms out to the legs; a full rectangle over the legs would be 124 mm from the
    axis and the wall is at 114 up here. The valve is strapped down to two inserts either side
    of it, which stand two millimetres proud of the plate so the strap clears its feet. The
    grommet pockets are sunk into the plate rather than raised, because the pump's underside
    is only two millimetres above it.
    """
    fx, fy = P.PUMP_FEET
    half = P.PUMP_LEG / 2
    vx, vy = P.VALVE_XY
    m = box(-fx / 2 - PLATE_MARGIN, fx / 2 + PLATE_MARGIN,
            -fy / 2 - PLATE_MARGIN, fy / 2 + PLATE_MARGIN, PLATE_Z0, PLATE_Z1)
    m = m + box(vx - STRAP_X - BOSS_R, vx + STRAP_X + BOSS_R, fy / 2 - 0.01,
                vy + P.VALVE[1] / 2 + 6.0, PLATE_Z0, PLATE_Z1)             # the valve's pad
    for lx, ly in _legs_xy():                                              # arms out to the legs
        ax = sorted((math.copysign(fx / 2 - PLATE_MARGIN, lx), lx + math.copysign(half, lx)))
        ay = sorted((math.copysign(fy / 2 - PLATE_MARGIN, ly), ly + math.copysign(half, ly)))
        m = m + box(ax[0], ax[1], ay[0], ay[1], PLATE_Z0, PLATE_Z1)
        m = m + box(lx - half, lx + half, ly - half, ly + half, P.Z_FLOOR, PLATE_Z0 + 0.01)
    m = m - box(-45, 45, -18, 18, PLATE_Z0 - 1, PLATE_Z1 + 1)              # lighten
    for x, y in _feet_xy():
        m = m + cyl_z(BOSS_R, BOSS_Z0, PLATE_Z0 + 0.01, x, y)
        m = m - cyl_z(GROMMET_R, PLATE_Z1 - GROMMET_DEPTH, PLATE_Z1 + 1, x, y)
    for x, y in _strap_xy():
        m = m + cyl_z(BOSS_R, BOSS_Z0, STRAP_TOP, x, y)
    return insert_holes(m, [(x, y, STRAP_TOP) for x, y in _strap_xy()])
