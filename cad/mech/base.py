"""The wet zone: the bottle across the belly, and the pump and valve down the trouser legs.

The statue has no cavity below the coat's hem, so the floor is a plate at Z_FLOOR and everything
below it is sand ballast - except the two trouser legs, which are the only tall free volumes in
the whole statue and are where the pump and the valve now hang, on brackets bolted up under that
plate. The bottle lies on the plate on its wide face, neck to +Y, and the tank head screws onto
it; a hose comes down to its barb from the filler port on the coat's back (mech/filler.py).

Service: there is no hatch. The filler cap is outside, on the coat's back; the sled is reached
from the top. The bottle is 97 x 195 in plan and the belt ring's bore is 120 x 182, so it does not
pass that either - to change the bottle the belt joint comes apart and the divider lifts off.
"""
import math
from build123d import Cone, Location, Plane, Pos, Rectangle, loft
from bd_warehouse.thread import IsoThread
import params as P
from mech import part
from mech.common import BARB_BORE_R, BARB_R, BARB_RING, barb_rings, cyl_z, cyl_x, cyl_y, box, insert_holes
from mech.torso import FLOOR_T, bracket_bolts, cradle_bolts, leg_centres, measured_legs

# --- the bottle and its cradle -----------------------------------------------------------------
PLATE_TOP = P.Z_FLOOR + FLOOR_T                     # 154, what everything wet stands on
BOTTLE_W, BOTTLE_L, BOTTLE_H = P.BOTTLE
BOTTLE_Y1 = P.BOTTLE_XY[1] + BOTTLE_L / 2           # 105, the neck's outer face
BOTTLE_AXIS_Z = P.BOTTLE_Z0 + BOTTLE_H / 2          # 191.5, the neck's own axis
PAD_T = P.BOTTLE_Z0 - PLATE_TOP                     # 2, the cradle's pad under the bottle
RIB_T = 3.0                                         # the ribs that box the bottle in
RIB_H = 12.0

# --- tank head ------------------------------------------------------------------------------
# Drawn standing on its mouth at z = 0 with its axis up, because that is how it is printed: the
# bore opens downward onto the bed and its roof closes as a 45 degree cone, so nothing bridges.
TANK_HEAD_R = P.CAN_THREAD_MAJOR / 2 + 3.0          # 22, three millimetres of wall on the thread
BORE_R = P.CAN_THREAD_MAJOR / 2 + 0.2               # the thread is cut into this bore
THREAD_Z = 0.5
CONE_Z0 = P.CAN_THREAD_LEN                          # 12, where the thread's bore ends
CONE_R1 = 3.2
CONE_Z1 = CONE_Z0 + (BORE_R - CONE_R1)              # 28; 45 degrees is the radius it sheds
TANK_HEAD_L = CONE_Z1 + 2.0                         # 30; a flat end face for the port fittings
# The filler port leaves the shoulder sideways here and points +Z once the head is laid on the
# neck. A hose runs from it to the neck on the divider, and this end of it is a barb: the port
# used to be the M22 the cap is cut to, which no hose that fits the belly could ever go over.
STUB_R = BARB_R                                     # 3.25, the barb the filler hose pushes onto
STUB_Z = P.CAN_THREAD_LEN + P.FILLER_D / 2          # 19; half a millimetre past the thread's end
STUB_OUT = TANK_HEAD_R + 16.0                       # 38: HOSE_BARB_L of grip and room to bend after it
STUB_BORE_Y = -(TANK_HEAD_R - 12.0)                 # how far in the stub's bore reaches
# Ports up through the nose as (x, y, radius), all inside CAN_NECK_ID / 2 with a millimetre of
# rim, a millimetre between them, and clear of the stub's bore, which runs out along -Y.
PORTS = {
    "float": (0.0, 8.0, P.FLOAT_HOLE_D / 2),
    "dip": (-10.0, 0.0, P.DIP_TUBE_D / 2),
    "vent": (11.0, 0.0, 1.5),
}
# Laid on the bottle's neck, which points +Y: the print frame's +Z goes to +Y and its -Y - the
# filler stub - goes to +Z.
TANK_HEAD_AT = Location((P.BOTTLE_XY[0], BOTTLE_Y1 - TANK_HEAD_L, BOTTLE_AXIS_Z), (-90, 0, 0))

# --- filler cap ----------------------------------------------------------------------------
CAP_R = P.FILLER_CAP_THREAD_MAJOR / 2 + 3           # 14
CAP_GRIP = 0.0                                      # no flare any more: it turns in the port's
                                                    # pocket, 1 mm round it, by the bar on its top
CAP_BORE_R = P.FILLER_CAP_THREAD_MAJOR / 2 + 0.2    # 11.2
CAP_END_T = 4.0
CAP_L = 14.0
CAP_SEAT_Z = CAP_L - CAP_END_T                      # 10; the neck's rim lands here
CAP_THREAD_Z = 0.5
CAP_THREAD_LEN = 9.0
GROOVE_R = (P.FILLER_D / 2 + 0.4, P.FILLER_CAP_THREAD_MAJOR / 2 - 1.4)
GRIP = (26.0, 5.0, 6.0)                             # a bar across the cap's top, for a gloved hand
# it screws onto the port's neck, sunk in the pocket, along the port's axis
from mech.filler import cap_location  # noqa: E402
FILLER_CAP_AT = cap_location()

# --- the brackets in the legs ------------------------------------------------------------------
BRACKET_T = 4.0                                     # the plate that bolts up under the floor
BRACKET_WALL = 3.0
STRAP_BOSS_R = 6.0


def _cone_z(r0, r1, z0, z1):
    """A cone along +Z, r0 at z0 and r1 at z1."""
    return Pos(0, 0, (z0 + z1) / 2) * Cone(r0, r1, z1 - z0)


def _frustum(cx, cy, w0, h0, w1, h1, z0, z1):
    """A rectangular frustum: the w0 x h0 section at z0 drawn in to w1 x h1 at z1."""
    return loft([Pos(cx, cy, z0) * Rectangle(w0, h0), Pos(cx, cy, z1) * Rectangle(w1, h1)])


def bottle_envelope():
    """The whole bought bottle as it lies: on its wide face, neck to +Y, shoulder and all.

    Modelled with its shoulder rather than as a plain box, because that is what fits. The coat
    draws in as it rises to the belt - at the bottle's top the belly takes a half-length of 84.5
    against a square corner's 97.5 - and the taper is what pulls the corner back inside.
    """
    cx, cy = P.BOTTLE_XY
    z0 = P.BOTTLE_Z0
    z1 = z0 + BOTTLE_H
    zs = z1 - P.BOTTLE_SHOULDER_H
    dx, dy = P.BOTTLE_SHOULDER_IN
    barrel = box(cx - BOTTLE_W / 2, cx + BOTTLE_W / 2, cy - BOTTLE_L / 2, cy + BOTTLE_L / 2, z0, zs)
    return barrel + _frustum(cx, cy, BOTTLE_W, BOTTLE_L, BOTTLE_W - 2 * dx, BOTTLE_L - 2 * dy, zs, z1)


def bottle_body():
    """The same, less the neck the tank head screws onto - which is inside its 195, not beyond it."""
    cx, cy = P.BOTTLE_XY
    neck = box(cx - BOTTLE_W, cx + BOTTLE_W, BOTTLE_Y1 - TANK_HEAD_L, cy + BOTTLE_L,
               P.BOTTLE_Z0 - 1, P.BOTTLE_Z0 + BOTTLE_H + 1)
    return bottle_envelope() - neck


def can_thread():
    """The bottle's thread, where it sits in the tank head's bore. The part's own frame."""
    thread = IsoThread(major_diameter=P.CAN_THREAD_MAJOR + 0.4, pitch=P.CAN_THREAD_PITCH,
                       length=P.CAN_THREAD_LEN - 1, external=False, end_finishes=("fade", "fade"))
    return Pos(0, 0, THREAD_Z) * thread


def hose_points():
    """The filler hose's centreline, from the port's barb on the coat's back to the tank head's.

    Straight down from the port's barb, through the chassis, both belt flanges and the divider at
    FILLER_PASSAGE; under the lower flange, in towards the axis until it is inside the belt ring's
    bore and past the bottle's shoulder; up to the run over the bottle, inside that bore; across to
    the stub; and down onto it. The run's height is the old one, a hose radius and a millimetre over
    the stub's top, and inside the bore the hose may rise to the divider, so it is not the 13 mm
    between the bottle and the divider any more that sizes it, but the bore beside the stub.
    """
    from mech.filler import hose_start, passage_xy
    r = P.HOSE_OD / 2
    sx, sy = P.BOTTLE_XY[0], BOTTLE_Y1 - TANK_HEAD_L + STUB_Z
    top = BOTTLE_AXIS_Z + STUB_OUT                       # the stub's end face
    run = max(top, P.BOTTLE_Z0 + P.BOTTLE[2]) + r + 1.0  # over the stub and the bottle
    px, py = passage_xy()
    under = P.Z_BELT - P.FLANGE_LOWER_H - r - 2.0         # under the lower flange
    ix, iy = HOSE_TURN_IN                                 # inside the belt's bore, past the shoulder
    return [hose_start(), (px, py, under), (ix, iy, under), (ix, iy, run), (sx, sy, run),
            (sx, sy, top)]


HOSE_TURN_IN = (-47.0, 43.0)       # where the hose turns up to the run: inside the belt ring's bore
                                   # (0.84 of it) and 4.5 mm outside the bottle's shoulder at z 226


def hose_route(r=None):
    """The hose itself: hose_points() swept as cylinders, HOSE_OD across unless told otherwise."""
    r = P.HOSE_OD / 2 if r is None else r
    pts = hose_points()
    route = None
    for a, b in zip(pts, pts[1:]):
        d = math.dist(a, b)
        if d < 1e-6:
            continue
        seg = Plane(origin=tuple((ai + bi) / 2 for ai, bi in zip(a, b)),
                    z_dir=tuple(bi - ai for ai, bi in zip(a, b))) * Pos(0, 0, -d / 2) * cyl_z(r, 0, d)
        route = seg if route is None else route + seg
    return route


@part("tank_cradle")
def tank_cradle():
    """The bottle's bed on the floor plate: a pad, two ribs down its flanks and two end stops.

    Nothing wraps over it, so the bottle lifts straight out once the divider is off - which is
    the only way it comes out, there being no hatch to take it through.
    """
    cx, cy = P.BOTTLE_XY
    hx, hy = BOTTLE_W / 2, BOTTLE_L / 2
    pad = box(cx - hx, cx + hx, cy - hy, cy + hy, PLATE_TOP, P.BOTTLE_Z0)
    for sx in (-1, 1):                                                   # ribs down the flanks
        x = cx + sx * hx
        pad = pad + box(min(x, x + sx * RIB_T), max(x, x + sx * RIB_T), cy - hy + 15.0, cy + hy - 15.0,
                        PLATE_TOP, P.BOTTLE_Z0 + RIB_H)
    for sy in (-1, 1):                                                   # and a stop at each end
        y = cy + sy * hy
        pad = pad + box(cx - 30.0, cx + 30.0, min(y, y + sy * RIB_T), max(y, y + sy * RIB_T),
                        PLATE_TOP, P.BOTTLE_Z0 + RIB_H)
    for x, y in cradle_bolts():
        pad = pad - cyl_z(P.M3_CLEAR / 2, PLATE_TOP - 1, P.BOTTLE_Z0 + 1, x, y)
        pad = pad - cyl_z(3.2, P.BOTTLE_Z0 - 1.6, P.BOTTLE_Z0 + 1, x, y)   # head, under the bottle
    return pad


@part("tank_head", placement=TANK_HEAD_AT)
def tank_head():
    """Screws onto the bottle's neck. Carries the dip tube, the float switch, a vent and the filler.

    Drawn standing on its mouth at z = 0; TANK_HEAD_AT lays it on the neck, which points +Y, and
    the filler stub then points straight up at the divider. The thread is retention only - the
    bottle's own gasket seals - so it is cut 0.4 mm over size into a bore that is the thread's
    own major diameter, and it fades at both ends.
    """
    cap = cyl_z(TANK_HEAD_R, 0, TANK_HEAD_L)
    cap = cap + cyl_y(STUB_R, -STUB_OUT, -(TANK_HEAD_R - 6.0), 0.0, STUB_Z)      # the filler barb
    for d in barb_rings():                                                       # its two ridges
        cap = cap + cyl_y(STUB_R + P.HOSE_BARB_LIP, -STUB_OUT + d,
                          -STUB_OUT + d + BARB_RING, 0.0, STUB_Z)
    cap = cap - cyl_z(BORE_R, -1, CONE_Z0)                                       # thread bore
    cap = cap - _cone_z(BORE_R, CONE_R1, CONE_Z0, CONE_Z1)                       # its 45 degree roof
    cap = cap + can_thread()
    cap = cap - cyl_y(BARB_BORE_R, -(STUB_OUT + 1), STUB_BORE_Y, 0.0, STUB_Z)
    for x, y, r in PORTS.values():                                               # up through the nose
        cap = cap - cyl_z(r, P.CAN_THREAD_LEN - 1, TANK_HEAD_L + 1, x, y)
    return cap


@part("filler_cap", placement=FILLER_CAP_AT)
def filler_cap():
    """Closes the filler port on the coat's back. Retention thread, an O-ring seal, and a bar
    across its top a gloved hand can turn it by. Printed open end down."""
    cap = cyl_z(CAP_R, 0, CAP_L) + box(-GRIP[0] / 2, GRIP[0] / 2, -GRIP[1] / 2, GRIP[1] / 2,
                                       CAP_L - 0.01, CAP_L + GRIP[2])
    cap = cap - cyl_z(CAP_BORE_R, -1, CAP_SEAT_Z)
    thread = IsoThread(major_diameter=P.FILLER_CAP_THREAD_MAJOR + 0.4, pitch=P.FILLER_CAP_PITCH,
                       length=CAP_THREAD_LEN, external=False, end_finishes=("fade", "fade"))
    cap = cap + Pos(0, 0, CAP_THREAD_Z) * thread
    r0, r1 = GROOVE_R                                                    # O-ring groove in the seat
    groove = cyl_z(r1, CAP_SEAT_Z - 0.01, CAP_SEAT_Z + 1.5) - cyl_z(r0, CAP_SEAT_Z - 0.1, CAP_SEAT_Z + 1.6)
    return cap - groove


def _bracket(centre, body, feet, z0_part, floor=True):
    """A plate bolted up under the floor plate with a cage round what hangs from it.

    The part's own z0 comes from params, so the cage's floor lands on it rather than on an
    assumed drop; the valve's is left open, because its strap is the floor.
    """
    cx, cy = centre
    bx, by, bz = body
    z1 = P.Z_FLOOR
    z0 = z1 - BRACKET_T
    x0, x1 = cx - bx / 2 - BRACKET_WALL, cx + bx / 2 + BRACKET_WALL
    y0, y1 = cy - by / 2 - BRACKET_WALL, cy + by / 2 + BRACKET_WALL
    plate = box(x0, x1, y0, y1, z0, z1)
    for x, y in bracket_bolts(centre):                                   # up into the floor plate
        plate = plate - cyl_z(P.M3_CLEAR / 2, z0 - 1, z1 + 1, x, y)
        plate = plate - cyl_z(3.2, z0 - 0.01, z0 + P.SCREW_HEAD_H, x, y)
    for dx in (-1, 1):                                                   # the part's own feet
        for dy in (-1, 1):
            plate = plate - cyl_z(P.M3_CLEAR / 2, z0 - 1, z1 + 1,
                                  cx + dx * feet[0] / 2, cy + dy * feet[1] / 2)
    for sx in (-1, 1):                                                   # a wall down each flank
        x = cx + sx * (bx / 2 + BRACKET_WALL / 2)
        plate = plate + box(x - BRACKET_WALL / 2, x + BRACKET_WALL / 2, y0, y1,
                            z0_part - BRACKET_WALL, z0 + 0.01)
    if floor:
        plate = plate + box(x0, x1, y0, y1, z0_part - BRACKET_WALL, z0_part)
    else:                                                                # inserts for the strap
        for sx in (-1, 1):
            plate = insert_holes(plate, [(cx + sx * (bx / 2 + BRACKET_WALL / 2), cy,
                                          z0_part - BRACKET_WALL)], direction="up")
    if P.PUMP_TIE_SLOTS:                                                 # ties round the body
        for dz in (0.3, 0.7):
            z = z0_part + bz * dz
            for sx in (-1, 1):
                x = cx + sx * (bx / 2 + BRACKET_WALL / 2)
                plate = plate - box(x - BRACKET_WALL, x + BRACKET_WALL, y0 - 1, y0 + 2.0, z, z + 3.0)
    return plate


@part("pump_bracket")
def pump_bracket():
    """The micro pump, hanging in the left trouser leg under the floor plate.

    It is the only place in the statue tall enough for it: the legs are the one free volume
    below the hem, and the sand stops at SAND_Z_TOP, well under the cage's floor.
    """
    return _bracket(measured_legs()["left"], P.PUMP, P.PUMP_FEET, P.PUMP_Z0)


@part("valve_bracket")
def valve_bracket():
    """The solenoid valve, in the right leg, on the same pattern; its strap closes the cage."""
    return _bracket(measured_legs()["right"], P.VALVE, (P.VALVE[0] - 16.0, P.VALVE[1] - 10.0),
                    P.VALVE_Z0, floor=False)


@part("valve_strap")
def valve_strap():
    """The floor of the valve's cage: a bar under it, pulled up into the two flank walls."""
    w, t = P.VALVE_STRAP
    cx, cy = measured_legs()["right"]
    z1 = P.VALVE_Z0 - BRACKET_WALL
    z0 = z1 - t
    reach = P.VALVE[0] / 2 + BRACKET_WALL
    bar = box(cx - reach, cx + reach, cy - w / 2, cy + w / 2, z0, z1)
    for sx in (-1, 1):
        bar = bar - cyl_z(P.M3_CLEAR / 2, z0 - 1, z1 + 1, cx + sx * (P.VALVE[0] / 2 + BRACKET_WALL / 2), cy)
    return bar
