"""The wet zone: what holds the bought vessel, pump and valve.

The canister lies centred on the floor in its cradle; the cradle's ends rise past it as two
towers, and the pump's plate screws down onto them. The valve stands beside the pump on the
same plate under a strap. Nothing in here is wider than the base's circle.
"""
import math
from build123d import Cone, Location, Plane, Pos, Rot
from bd_warehouse.thread import IsoThread
import params as P
from mech import part
from mech.common import cyl_z, cyl_x, box, insert_holes

# --- tank head -----------------------------------------------------------------------------
TANK_HEAD_R = P.CAN_THREAD_MAJOR / 2 + 3.0          # 22, three millimetres of wall on the thread
BORE_R = P.CAN_THREAD_MAJOR / 2 + 0.2               # the thread is cut into this bore
THREAD_X = 0.5                                      # where the thread starts inside the bore
# The head prints mouth down, so the roof over the Ø38.4 bore would be a flat bridge of the
# same diameter. Instead the bore closes as a 45 degree cone: every layer overhangs the one
# below by its own height and nothing is bridged.
CONE_X0 = P.CAN_THREAD_LEN                          # 12, where the thread's bore ends
CONE_R1 = 3.2                                       # the cone stops just short of its apex
CONE_X1 = CONE_X0 + (BORE_R - CONE_R1)              # 28
TANK_HEAD_L = CONE_X1 + 2.0                         # 30; a flat end face for the port fittings
# The filler stub rises +Z off the head's shoulder (FILLER_STUB_DIR) and its bore drops into
# the cone's cavity, which is the neck. It stands clear of the thread: a Ø14 bore centred any
# further back would cut into it.
STUB_R = P.FILLER_CAP_THREAD_MAJOR / 2              # 11, same OD as the neck at the back
STUB_X = P.CAN_THREAD_LEN + P.FILLER_D / 2          # 19; its bore starts half a
                                                    # millimetre past the thread's end
STUB_TOP = TANK_HEAD_R + 16.0                       # 38, sixteen millimetres of hose grip

# Ports through the nose as (y, z, radius). Everything that reaches the liquid has to pass the
# canister's own neck, so all three live inside a circle of CAN_NECK_ID / 2 with a millimetre
# of rim and a millimetre between them. The filler is no longer one of them - it comes down
# the stub into the cone - which is what let the float switch move onto the centreline.
PORTS = {
    "float": (0.0, 8.0, P.FLOAT_HOLE_D / 2),
    "dip": (0.0, -10.0, P.DIP_TUBE_D / 2),
    "vent": (11.0, 0.0, 1.5),
}

# It is modelled along +X from the thread's mouth and then turned to face the canister's neck,
# which points -X. Its stub still rises, because the turn is about Z.
TANK_HEAD_AT = Location((P.CANISTER_XY[0] - P.CANISTER[0] / 2, P.CANISTER_XY[1],
                         P.CANISTER_Z0 + P.CANISTER[2] / 2), (0, 0, 180))

# --- filler cap ----------------------------------------------------------------------------
CAP_R = P.FILLER_CAP_THREAD_MAJOR / 2 + 3           # 14
CAP_BORE_R = P.FILLER_CAP_THREAD_MAJOR / 2 + 0.2    # 11.2
CAP_END_T = 4.0                                     # the closed end, which the O-ring seats in
CAP_L = 14.0
CAP_THREAD_X = CAP_END_T + 0.5
CAP_THREAD_LEN = 9.0
GROOVE_R = (P.FILLER_D / 2 + 0.4, P.FILLER_CAP_THREAD_MAJOR / 2 - 1.4)

# --- the bridge over the canister -------------------------------------------------------------
PLATE_Z0 = P.PUMP_Z0 - 6.0                          # 141, four millimetres over the canister
PLATE_Z1 = P.PUMP_Z0 - 2.0                          # 145; the feet stand on grommets above it
PLATE_MARGIN = 8.0
GROMMET_R = 4.5
TIE_SLOT = (4.0, 1.5)                               # cable-tie slots beside each grommet
BOSS_R = 7.0
STRAP_X = P.VALVE[0] / 2 + BOSS_R + 1.0             # 30.5; the strap's bolts miss the valve
STRAP_TOP = PLATE_Z1 + 2.0                          # the bosses stand proud so the strap clears
# PUMP_LEG_XY (90, 45) puts a tower's corner at r 107.35 and the raised floor stops at
# BASE_FLOOR_R 108, which is 0.65 mm of ledge to stand on. Clamped here to leave two.
TOWER_XY = (min(P.PUMP_LEG_XY[0],
                math.sqrt((P.BASE_FLOOR_R - 2.0) ** 2 - (P.PUMP_LEG_XY[1] + P.PUMP_LEG / 2) ** 2)
                - P.PUMP_LEG / 2),
            P.PUMP_LEG_XY[1])
TOWER_Y = TOWER_XY[1] + P.PUMP_LEG / 2              # 50, the tower wall's half width
TOWER_WINDOW = (P.CANISTER_Z0 + P.CANISTER[2] / 2 + 10.5, 35.0)   # (centre z, radius)
HOSE_R = STUB_R + 2.0                               # 13; the filler hose slides over the stub
TOWER_SLOT_Y = HOSE_R + 1.0                         # the hose climbs through the tower's tie


def _cone_x(r0, r1, x0, x1):
    """A cone along +X, r0 at x0 and r1 at x1."""
    return Pos((x0 + x1) / 2, 0, 0) * Rot(0, 90, 0) * Cone(r0, r1, x1 - x0)


def can_thread():
    """The canister thread, where it sits in the tank head's bore. The part's own frame."""
    thread = IsoThread(major_diameter=P.CAN_THREAD_MAJOR + 0.4, pitch=P.CAN_THREAD_PITCH,
                       length=P.CAN_THREAD_LEN - 1, external=False, end_finishes=("fade", "fade"))
    return Pos(THREAD_X, 0, 0) * Rot(0, 90, 0) * thread


def filler_neck():
    """The neck the filler cap screws onto, in the cap's own frame.

    Not printed here - it belongs to the back of the base's shell - but the cap is cut to it,
    so the mating half is worth having to test against. Its crests stand at
    FILLER_CAP_THREAD_MAJOR over a FILLER_D bore.
    """
    thread = IsoThread(major_diameter=P.FILLER_CAP_THREAD_MAJOR, pitch=P.FILLER_CAP_PITCH,
                       length=CAP_THREAD_LEN - 2.0, external=True, end_finishes=("square", "square"))
    neck = Pos(CAP_THREAD_X + 1.0, 0, 0) * Rot(0, 90, 0) * thread
    neck = neck + cyl_x(thread.min_radius, CAP_END_T, CAP_THREAD_X + CAP_THREAD_LEN + 10)
    return neck - cyl_x(P.FILLER_D / 2, CAP_END_T - 1, CAP_THREAD_X + CAP_THREAD_LEN + 11)


def _tank_head():
    """The tank head in its own frame, mouth at x = 0, stub rising +Z off its shoulder."""
    cap = cyl_x(TANK_HEAD_R, 0, TANK_HEAD_L)
    cap = cap + cyl_z(STUB_R, TANK_HEAD_R - 6.0, STUB_TOP, STUB_X, 0.0)    # the filler stub
    cap = cap - cyl_x(BORE_R, -1, CONE_X0)                                 # thread bore
    cap = cap - _cone_x(BORE_R, CONE_R1, CONE_X0, CONE_X1)                 # its 45 degree roof
    cap = cap + can_thread()
    cap = cap - cyl_z(P.FILLER_D / 2, TANK_HEAD_R - 12.0, STUB_TOP + 1, STUB_X, 0.0)
    for y, z, r in PORTS.values():                                         # out through the nose
        cap = cap - cyl_x(r, P.CAN_THREAD_LEN - 1, TANK_HEAD_L + 1, y, z)
    return cap


@part("tank_head")
def tank_head():
    """Screws onto the canister's neck. Carries the dip tube, the float switch, a vent and the filler.

    The thread is retention only - the canister's own gasket seals - so it is cut 0.4 mm over
    size into a bore that is the thread's own major diameter, and it fades at both ends. The
    stub takes the hose that climbs to the filler cap at the back of the base.
    """
    return TANK_HEAD_AT * _tank_head()


def tower_inserts():
    """Where the pump plate screws down into the cradle's towers."""
    return [(sx * TOWER_XY[0], sy * TOWER_XY[1]) for sx in (-1, 1) for sy in (-1, 1)]


@part("tank_cradle")
def tank_cradle():
    """Saddles for the lying canister, and the two towers the pump's plate stands on.

    Everything on it is vertical or lies on the floor, so it prints upright with no support.
    Each tower is a portal: a window through it clears the tank head and its filler stub at
    the -X end, and leaves two columns carrying an insert apiece.
    """
    L, W, H = P.CANISTER
    cx, cy = P.CANISTER_XY
    z0 = P.Z_FLOOR
    rise = P.CANISTER_Z0 - z0                                              # the canister's bed height
    cradle = None
    for x in (cx - L / 3, cx + L / 3):
        s = box(x - 10, x + 10, cy - W / 2 - 4, cy + W / 2 + 4, z0, z0 + rise + 8)
        s = s - box(x - 11, x + 11, cy - W / 2, cy + W / 2, z0 + rise, z0 + rise + 9)
        cradle = s if cradle is None else cradle + s
    cradle = cradle + box(cx - L / 3, cx + L / 3, cy - 8, cy + 8, z0, z0 + 4)
    half = P.PUMP_LEG / 2
    wz, wr = TOWER_WINDOW
    for sx in (-1, 1):
        tx = sx * TOWER_XY[0]
        cradle = cradle + box(min(tx - half, sx * (L / 3 + 10)), max(tx + half, sx * (L / 3 + 10)),
                              cy - TOWER_Y, cy + TOWER_Y, z0, z0 + 4)      # rail out to the tower
        tower = box(tx - half, tx + half, cy - TOWER_Y, cy + TOWER_Y, z0, PLATE_Z0)
        tower = tower - cyl_x(wr, tx - half - 1, tx + half + 1, cy, wz)    # the window
        tower = tower - box(tx - half - 1, tx + half + 1, cy - TOWER_SLOT_Y, cy + TOWER_SLOT_Y,
                            wz, PLATE_Z0 + 1)                              # the filler hose's slot
        cradle = cradle + tower
    return insert_holes(cradle, [(x, y, PLATE_Z0) for x, y in tower_inserts()])


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


def _strap_xy():
    vx, vy = P.VALVE_XY
    return [(vx - STRAP_X, vy), (vx + STRAP_X, vy)]


@part("pump_plate")
def pump_plate():
    """The bridge's deck: the pump on grommets, the valve beside it, screwed onto the towers.

    Flat on its underside and every feature above it, so it prints on that face without a
    support anywhere. The grommet pockets are through holes - a rubber grommet snaps into a
    panel, which is what this is - with a cable-tie slot either side of each, because a
    grommet alone only damps the pump, it does not hold it down.

    Only as wide as the pump's feet want, with a pad reaching back to the valve and four arms
    out to the towers; a full rectangle over them would be 124 mm from the axis and the wall
    up here is at 114.
    """
    fx, fy = P.PUMP_FEET
    vx, vy = P.VALVE_XY
    m = box(-fx / 2 - PLATE_MARGIN, fx / 2 + PLATE_MARGIN,
            -fy / 2 - PLATE_MARGIN, fy / 2 + PLATE_MARGIN, PLATE_Z0, PLATE_Z1)
    m = m + box(vx - STRAP_X - BOSS_R, vx + STRAP_X + BOSS_R, fy / 2 - 0.01,
                vy + P.VALVE[1] / 2 + 6.0, PLATE_Z0, PLATE_Z1)             # the valve's pad
    for tx, ty in tower_inserts():                                         # arms out to the towers
        ax = sorted((math.copysign(fx / 2 - PLATE_MARGIN, tx), tx + math.copysign(P.PUMP_LEG / 2, tx)))
        ay = sorted((math.copysign(fy / 2 - PLATE_MARGIN, ty), ty + math.copysign(P.PUMP_LEG / 2, ty)))
        m = m + box(ax[0], ax[1], ay[0], ay[1], PLATE_Z0, PLATE_Z1)
    m = m - box(-45, 45, -18, 18, PLATE_Z0 - 1, PLATE_Z1 + 1)              # lighten
    for x, y in _feet_xy():
        m = m - cyl_z(GROMMET_R, PLATE_Z0 - 1, PLATE_Z1 + 1, x, y)         # the grommet snaps in
        if P.PUMP_TIE_SLOTS:
            w, t = TIE_SLOT
            for dy in (-(GROMMET_R + 3.0), GROMMET_R + 3.0):
                m = m - box(x - w / 2, x + w / 2, y + dy - t / 2, y + dy + t / 2,
                            PLATE_Z0 - 1, PLATE_Z1 + 1)
    for x, y in tower_inserts():                                           # down into the towers
        m = m - cyl_z(P.M3_CLEAR / 2, PLATE_Z0 - 1, PLATE_Z1 + 1, x, y)
    for x, y in _strap_xy():
        m = m + cyl_z(BOSS_R, PLATE_Z0, STRAP_TOP, x, y)
    return insert_holes(m, [(x, y, STRAP_TOP) for x, y in _strap_xy()])


def hose_route(r=None):
    """The hose from the filler stub's mouth to the filler neck's inboard end, as cylinders.

    The stub rises under the neck, so the run is very nearly straight up: a 40 mm bend radius
    is never called on. The route is built from the polyline all the same, so that moving
    either end shows up as a clash rather than as a hose that cannot be bent.
    """
    r = HOSE_R if r is None else r
    x0 = P.CANISTER_XY[0] - P.CANISTER[0] / 2 - STUB_X
    z0 = P.CANISTER_Z0 + P.CANISTER[2] / 2 + STUB_TOP
    x1 = -(P.shell_r(P.BASE_PROFILE, P.Z_FILLER) - P.WALL - 15.0)
    pts = [(x0, z0), (x0, P.Z_FILLER), (x1, P.Z_FILLER)]
    route = None
    for (ax, az), (bx, bz) in zip(pts, pts[1:]):
        d = math.hypot(bx - ax, bz - az)
        if d < 1e-6:
            continue
        seg = Plane(origin=((ax + bx) / 2, P.CANISTER_XY[1], (az + bz) / 2),
                    z_dir=(bx - ax, 0.0, bz - az)) * Pos(0, 0, -d / 2) * cyl_z(r, 0, d)
        route = seg if route is None else route + seg
    return route


def hose_turn():
    """How far the hose has to bend on that route, in degrees."""
    x0 = P.CANISTER_XY[0] - P.CANISTER[0] / 2 - STUB_X
    x1 = -(P.shell_r(P.BASE_PROFILE, P.Z_FILLER) - P.WALL - 15.0)
    z0 = P.CANISTER_Z0 + P.CANISTER[2] / 2 + STUB_TOP
    return math.degrees(math.atan2(abs(x1 - x0), P.Z_FILLER - z0))


@part("valve_strap")
def valve_strap():
    """A bar across the top of the valve, pulled down onto it by two long screws.

    The screws pass either side of the valve's body into the plate's inserts, so the bar is a
    plain flat part that prints on its face.
    """
    w, t = P.VALVE_STRAP
    vx, vy = P.VALVE_XY
    z0 = P.PUMP_Z0 + P.VALVE[2]
    bar = box(vx - STRAP_X - BOSS_R, vx + STRAP_X + BOSS_R, vy - w / 2, vy + w / 2, z0, z0 + t)
    for x, y in _strap_xy():
        bar = bar - cyl_z(P.M3_CLEAR / 2, z0 - 1, z0 + t + 1, x, y)
    return bar
