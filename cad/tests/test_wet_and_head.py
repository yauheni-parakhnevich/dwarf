"""The wet zone: the bottle across the belly, the tank head, the filler, and the leg brackets.

`parts` and `placed` come from conftest: every registered part in its print frame, and the same
parts carried to where they sit in the machine.
"""
import itertools
import math
from build123d import Pos
import params as P
from mech.common import box, cyl_x, cyl_y, cyl_z


def _iso_crest_r(major, pitch):
    """Radius of an internal ISO thread's crest: the free bore it actually leaves.

    Its minor diameter is the major less 2 x (5/8)H, so the radius loses (5/8)H - half of what
    the diameter does, which is an easy factor of two to drop.
    """
    return major / 2 - 0.625 * pitch * math.sqrt(3) / 2


# --- the tank head ------------------------------------------------------------------------------

def test_tank_head_thread_matches_the_bottle(parts):
    """The neck goes in past the thread's crests, and there is wall left outside its roots."""
    from mech.base import BORE_R, TANK_HEAD_R
    assert P.CAN_THREAD_MAJOR == P.BOTTLE_THREAD_MAJOR                  # cut to the bottle it buys
    crest = _iso_crest_r(P.CAN_THREAD_MAJOR + 0.4, P.CAN_THREAD_PITCH)
    assert crest > P.CAN_NECK_ID / 2, crest                             # the neck's own bore passes
    assert TANK_HEAD_R - BORE_R >= 2.5, TANK_HEAD_R - BORE_R            # ... and wall outside the roots
    head = parts["tank_head"]
    assert (cyl_z(crest - 0.05, -1, P.CAN_THREAD_LEN) & head).volume < 1e-6           # bore is clear
    assert (cyl_z(crest + 0.2, 1.0, P.CAN_THREAD_LEN - 1.0) & head).volume > 1e-3     # crests are there


def test_tank_head_ports_pass_the_bottles_neck(parts):
    """Every port opens inside the neck with a millimetre of rim, clear of each other and the stub."""
    from mech.base import PORTS, STUB_BORE_Y, STUB_OUT, STUB_R, STUB_Z, TANK_HEAD_L
    head = parts["tank_head"]
    for name, (x, y, r) in PORTS.items():
        assert math.hypot(x, y) + r <= P.CAN_NECK_ID / 2 - 1.0, name
        probe = cyl_z(r - 0.05, P.CAN_THREAD_LEN, TANK_HEAD_L - 0.05, x, y)
        assert (probe & head).volume < 1e-6, name                       # drilled right through
    for a, b in itertools.combinations(PORTS, 2):
        xa, ya, ra = PORTS[a]
        xb, yb, rb = PORTS[b]
        assert math.hypot(xa - xb, ya - yb) >= ra + rb + 1.0, (a, b)
    # the filler's bore crosses the same nose on its way out along -Y; no port may open into it
    bore = cyl_y(P.FILLER_D / 2, -(STUB_OUT + 1), STUB_BORE_Y, 0.0, STUB_Z)
    for name, (x, y, r) in PORTS.items():
        port = cyl_z(r, P.CAN_THREAD_LEN - 1, TANK_HEAD_L + 1, x, y)
        assert (bore & port).volume < 1e-6, name
    assert math.isclose(2 * STUB_R, P.FILLER_CAP_THREAD_MAJOR, abs_tol=1e-9)


def test_tank_head_closes_its_bore_with_a_cone(parts):
    """Printed mouth down, the bore's roof would be a flat bridge. It is a 45 degree cone."""
    from mech.base import BORE_R, CONE_R1, CONE_Z0, CONE_Z1, TANK_HEAD_L
    assert math.isclose(CONE_Z1 - CONE_Z0, BORE_R - CONE_R1, abs_tol=1e-9)       # 45 degrees
    head = parts["tank_head"]
    assert math.isclose(head.bounding_box().min.Z, 0.0, abs_tol=1e-6)            # mouth on the bed
    for dz in (0.0, 4.0, 8.0, 12.0, 15.9):
        z = CONE_Z0 + dz
        assert (cyl_z(BORE_R - dz - 0.2, z + 0.05, z + 0.1) & head).volume < 1e-6, z
    assert CONE_Z1 + 1.0 <= TANK_HEAD_L                                # a flat face for the ports


def test_the_threaded_parts_print_standing_up(parts):
    """Both arrive at the slicer on their mouth with the axis vertical, not lying on their side."""
    from mech.base import CAP_SEAT_Z, TANK_HEAD_L
    heads = (("tank_head", _iso_crest_r(P.CAN_THREAD_MAJOR + 0.4, P.CAN_THREAD_PITCH), P.CAN_THREAD_LEN),
             ("filler_cap", _iso_crest_r(P.FILLER_CAP_THREAD_MAJOR + 0.4, P.FILLER_CAP_PITCH), CAP_SEAT_Z))
    for name, r, z1 in heads:
        p = parts[name]
        bb = p.bounding_box()
        assert math.isclose(bb.min.Z, 0.0, abs_tol=1e-6), name         # standing on its mouth
        assert (cyl_z(r - 0.05, -1.0, z1 - 0.1) & p).volume < 1e-6, name
        assert (cyl_x(r - 0.05, -bb.max.X - 1, bb.max.X + 1, 0.0, z1 / 2) & p).volume > 1e-3, name
    assert math.isclose(parts["tank_head"].bounding_box().max.Z, TANK_HEAD_L, abs_tol=1e-6)


def test_the_tank_head_sits_on_the_bottles_neck(placed):
    """Laid on the neck at +Y, inside the bottle's own plan, with the filler stub pointing up."""
    from mech.base import BOTTLE_AXIS_Z, BOTTLE_Y1, STUB_OUT, TANK_HEAD_L, TANK_HEAD_R, bottle_body
    head = placed["tank_head"]
    bb = head.bounding_box()
    assert math.isclose(bb.max.Y, BOTTLE_Y1, abs_tol=1e-6)             # its mouth is the neck's face
    assert math.isclose(bb.min.Y, BOTTLE_Y1 - TANK_HEAD_L, abs_tol=1e-6)
    assert max(abs(bb.min.X), bb.max.X) <= P.BOTTLE[0] / 2             # never wider than the bottle
    assert math.isclose(bb.max.Z, BOTTLE_AXIS_Z + STUB_OUT, abs_tol=1e-6)        # the stub points up
    assert bb.max.Z < P.Z_BELT - 2.0                                   # ... and stops under the divider
    assert math.isclose((bb.min.Z + bb.max.Z + TANK_HEAD_R - STUB_OUT) / 2, BOTTLE_AXIS_Z, abs_tol=6.0)
    assert (head & bottle_body()).volume < 1e-6                        # it screws on, it does not bite


# --- the filler, under the belly hatch ------------------------------------------------------------

def test_filler_cap_screws_onto_the_divider_neck(parts, placed):
    """The cap takes the neck on the divider: crests at FILLER_CAP_THREAD_MAJOR over a FILLER_D bore."""
    from mech.base import CAP_THREAD_LEN, CAP_THREAD_Z
    cap = parts["filler_cap"]
    neck = placed["filler_neck"]
    assert P.FILLER_VIA_HATCH
    bb = neck.bounding_box()
    assert math.isclose(bb.max.Y - bb.min.Y, 2 * 16.0, abs_tol=0.01)             # its bonding flange
    grip = cyl_z(P.FILLER_CAP_THREAD_MAJOR / 2 - 0.05, CAP_THREAD_Z, CAP_THREAD_Z + CAP_THREAD_LEN)
    assert (grip & cap).volume > 1e-3                                  # the cap's crests bite
    nx, ny = P.FILLER_NECK_XY
    bore = cyl_z(P.FILLER_D / 2 - 0.05, P.Z_BELT - 3, bb.max.Z + 1, nx, ny)
    assert (bore & neck).volume < 1e-6                                 # open all the way down


def test_the_filler_is_reached_beside_the_sled(parts, placed):
    """The cap stands above the divider, out of the sled's slide path, inside the belly opening.

    At FILLER_NECK_XY's first value - y 0 - the cap stood inside the sled's tray. Beside it the
    cap needs the tray's half width plus its own grip, which is what put it where it is; that is
    round from the front by more than the hatch's own wedge, so it is reached by hand rather
    than seen down the middle of the opening.
    """
    from mech.torso import sled_pocket
    cap = placed["filler_cap"]
    bb = cap.bounding_box()
    assert bb.min.Z >= P.Z_BASE_TOP + P.DIVIDER_PROUD                  # it clears the divider's face
    assert bb.max.Z < P.HATCH_Z[1]                                     # ... and is inside the opening
    _, _, py0, py1 = sled_pocket()
    assert bb.max.Y < py0 - 2.0 or bb.min.Y > py1 + 2.0, (bb.min.Y, bb.max.Y)
    assert (cap & placed["phone_sled"]).volume < 1e-6
    assert (cap & placed["chassis"]).volume < 1e-6                     # the chassis is notched for it
    nx, ny = P.FILLER_NECK_XY
    assert math.degrees(math.atan2(abs(ny), nx)) > P.HATCH_HALF_ANGLE   # ... which this records


def test_the_filler_hose_reaches_the_neck(placed):
    """From the tank head's stub, over the bottle and across to the divider's neck."""
    from mech.base import bottle_body, hose_route
    route = hose_route()
    bb = route.bounding_box()
    assert bb.max.Z <= P.Z_BELT + 3.0                                  # it stops in the divider's hole
    for name in ("tank_cradle", "pump_bracket", "valve_bracket", "phone_sled", "divider"):
        assert (route & placed[name]).volume < 1e-6, name
    assert (route & bottle_body()).volume < 1e-6


# --- the bottle, its cradle and the floor plate ------------------------------------------------------

def test_the_bottle_sits_in_its_cradle_on_the_floor_plate(parts, placed):
    """The cradle bolts to the floor plate's inserts and boxes the bottle in without trapping it."""
    from mech.base import PLATE_TOP, bottle_body
    from mech.torso import FLOOR_T, cradle_bolts
    cradle, plate = placed["tank_cradle"], placed["floor_plate"]
    assert math.isclose(cradle.bounding_box().min.Z, PLATE_TOP, abs_tol=1e-6)    # it stands on the plate
    assert math.isclose(plate.bounding_box().max.Z, P.Z_FLOOR + FLOOR_T, abs_tol=1e-6)
    bottle = bottle_body()
    assert (cradle & bottle).volume < 1e-6                             # the bottle drops into it
    assert math.isclose(bottle.bounding_box().min.Z, PLATE_TOP + (P.BOTTLE_Z0 - PLATE_TOP), abs_tol=1e-6)
    for x, y in cradle_bolts():                                        # the screws line up
        through = cyl_z(P.M3_CLEAR / 2 - 0.05, PLATE_TOP - 0.01, P.BOTTLE_Z0 + 1, x, y)
        assert (through & cradle).volume < 1e-6, (x, y)
        blind = cyl_z(P.INSERT_D / 2 - 0.05, P.Z_FLOOR + FLOOR_T - P.INSERT_DEPTH + 0.1,
                      P.Z_FLOOR + FLOOR_T - 0.1, x, y)
        assert (blind & plate).volume < 1e-6, (x, y)
    # lifting it straight up meets nothing: the cradle has no lip over the bottle
    assert (bottle.moved(Pos(0, 0, 40)) & cradle).volume < 1e-6


def test_the_bottle_comes_out_through_the_belt_not_the_hatch():
    """The service note, as an assertion: it does not pass the opening in any orientation."""
    hatch_w = 2 * P.shell_r(P.BASE_PROFILE, sum(P.HATCH_Z) / 2) * math.sin(math.radians(P.HATCH_HALF_ANGLE)) \
        if hasattr(P, "BASE_PROFILE") else 110.0
    opening = sorted((hatch_w, P.HATCH_Z[1] - P.HATCH_Z[0]))
    plan = sorted(P.BOTTLE[:2])
    assert plan[0] > opening[0] or plan[1] > opening[1], (plan, opening)


def test_the_floor_plate_carries_the_sand_and_the_ports(parts):
    """The pour hole, a port down to each leg, and the inserts everything wet hangs from."""
    from mech.torso import FLOOR_T, LEG_PORT_R, LEG_PORT_X, SAND_PLUG_XY, bracket_bolts, leg_centres
    plate, plug = parts["floor_plate"], parts["sand_plug"]
    z0, z1 = P.Z_FLOOR, P.Z_FLOOR + FLOOR_T
    pour = cyl_z(P.SAND_PLUG_D / 2 - 0.05, z0 - 1, z1 + 1, *SAND_PLUG_XY)
    assert (pour & plate).volume < 1e-6                                # the sand goes in here
    assert (plug & plate).volume < 1e-6                                # ... and the plug closes it
    assert P.SAND_Z_TOP < min(P.PUMP_Z0, P.VALVE_Z0) - 3.0             # sand stops under both parts
    for centre in leg_centres():
        port = cyl_z(LEG_PORT_R - 0.05, z0 - 1, z1 + 1, LEG_PORT_X, centre[1])
        assert (port & plate).volume < 1e-6, centre
        for x, y in bracket_bolts(centre):
            blind = cyl_z(P.INSERT_D / 2 - 0.05, z0 + 0.1, z0 + P.INSERT_DEPTH - 0.1, x, y)
            assert (blind & plate).volume < 1e-6, (x, y)


# --- the legs -------------------------------------------------------------------------------------

def test_the_brackets_hang_in_the_legs(placed):
    """Both stay inside the leg's free radius, above the sand, and clear of the floor plate's ports."""
    from mech.base import BRACKET_WALL
    from mech.torso import measured_legs
    legs = measured_legs()
    for name, centre, body, z0 in (("pump_bracket", legs["left"], P.PUMP, P.PUMP_Z0),
                                   ("valve_bracket", legs["right"], P.VALVE, P.VALVE_Z0)):
        p = placed[name]
        bb = p.bounding_box()
        cx, cy = centre
        corner = max(math.hypot(x - cx, y - cy) for x in (bb.min.X, bb.max.X) for y in (bb.min.Y, bb.max.Y))
        assert corner <= legs["r"] - 2.0, (name, corner)               # inside the leg with 2 mm
        assert bb.min.Z >= P.SAND_Z_TOP + 2.0, (name, bb.min.Z)        # above the sand
        assert math.isclose(bb.max.Z, P.Z_FLOOR, abs_tol=1e-6), name   # bolted up under the plate
        assert bb.min.Z >= z0 - BRACKET_WALL - 1e-6, name


def test_the_valves_strap_closes_its_cage(placed):
    """The valve's cage has no floor; the strap is it, pulled up into the two flank walls."""
    from mech.base import BRACKET_WALL
    from mech.torso import measured_legs
    strap = placed["valve_strap"]
    bb = strap.bounding_box()
    w, t = P.VALVE_STRAP
    assert math.isclose(bb.max.Y - bb.min.Y, w, abs_tol=1e-6)
    assert math.isclose(bb.max.Z - bb.min.Z, t, abs_tol=1e-6)
    from mech.base import BRACKET_WALL as BW
    assert math.isclose(bb.max.Z, P.VALVE_Z0 - BW, abs_tol=1e-6)       # it closes the cage's bottom
    cx, cy = measured_legs()["right"]
    for sx in (-1, 1):
        x = cx + sx * (P.VALVE[0] / 2 + BRACKET_WALL / 2)
        bolt = cyl_z(P.M3_CLEAR / 2 - 0.05, bb.min.Z - 1, bb.max.Z + 1, x, cy)
        assert (bolt & strap).volume < 1e-6, x
        seat = cyl_z(P.INSERT_D / 2 - 0.05, P.VALVE_Z0 - BRACKET_WALL + 0.1,
                     P.VALVE_Z0 - BRACKET_WALL + P.INSERT_DEPTH - 0.1, x, cy)  # into the flank wall
        assert (seat & placed["valve_bracket"]).volume < 1e-6, x


def test_no_two_wet_zone_parts_overlap(placed):
    """Everything wet, plus the bought bottle, the pump and the valve, against each other."""
    from mech.base import bottle_body
    from mech.torso import measured_legs
    legs = measured_legs()
    L, W, H = P.PUMP
    px, py = legs["left"]
    pump = box(px - L / 2, px + L / 2, py - W / 2, py + W / 2, P.PUMP_Z0, P.PUMP_Z0 + H)
    L, W, H = P.VALVE
    vx, vy = legs["right"]
    valve = box(vx - L / 2, vx + L / 2, vy - W / 2, vy + W / 2, P.VALVE_Z0, P.VALVE_Z0 + H)
    bodies = {"bottle": bottle_body(), "pump": pump, "valve": valve}
    for name in ("tank_cradle", "tank_head", "floor_plate", "pump_bracket", "valve_bracket",
                 "valve_strap", "divider", "filler_neck", "filler_cap"):
        bodies[name] = placed[name]
    for a, b in itertools.combinations(bodies, 2):
        if {a, b} <= {"pump", "pump_bracket"} or {a, b} <= {"valve", "valve_bracket"}:
            continue                                                   # each sits in its own cage
        if {a, b} in ({"valve", "valve_strap"}, {"filler_neck", "divider"},
                      {"filler_neck", "filler_cap"},
                      {"bottle", "tank_head"}, {"bottle", "tank_cradle"}):
            continue                             # bonded, or the head screwed onto the neck the
                                                 # bottle's own envelope includes
        assert (bodies[a] & bodies[b]).volume < 1e-6, (a, b)
