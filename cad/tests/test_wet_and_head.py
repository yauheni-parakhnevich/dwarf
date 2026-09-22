"""The head's nozzle and tube, and the wet zone: the tank, the pump's bridge and the valve."""
import itertools
import math
import pytest
from build123d import Axis, Plane, Polygon, Pos, Sphere, revolve
import params as P
from mech.common import box, cyl_x, cyl_z, servo_body


@pytest.fixture(scope="session")
def parts():
    import mech.turntable, mech.torso, mech.head, mech.base  # noqa: E401,F401
    from mech import ALL
    return {spec.name: spec.build() for spec in ALL}


@pytest.fixture(scope="session")
def placed(parts):
    """The same parts carried to where they sit in the machine."""
    from mech import ALL
    at = {spec.name: spec.placement for spec in ALL}
    return {name: at[name] * p for name, p in parts.items()}


def _base_inner():
    """The base's cavity with a millimetre to spare: shell_r - WALL - 1 at every height."""
    pts = [(P.shell_r(P.BASE_PROFILE, z) - P.WALL - 1.0, z) for _, z in P.BASE_PROFILE]
    z0, z1 = P.BASE_PROFILE[0][1], P.BASE_PROFILE[-1][1]
    return revolve(Plane.XZ * Polygon((0.0, z0), *pts, (0.0, z1)), axis=Axis.Z)


def _grown(body, by=1.0):
    bb = body.bounding_box()
    return box(bb.min.X - by, bb.max.X + by, bb.min.Y - by, bb.max.Y + by, bb.min.Z - by, bb.max.Z + by)


# --- the nozzle and its holder ----------------------------------------------------------------

def test_nozzle_holder_bore_is_on_the_mouth_axis(parts):
    from mech.head import BORE_X0
    probe = cyl_x(P.NOZZLE_D / 2 - 0.05, BORE_X0, P.HEAD_R, 0, P.Z_MOUTH)
    assert (probe & parts["nozzle_holder"]).volume < 1e-6


def test_the_nozzle_is_held_at_both_ends(parts):
    """A press fit in the nose and the mouth the assembler cuts, a nozzle's length apart.

    A press fit on its own would let the jet wander: the review measured plus or minus eight
    degrees on nine millimetres of grip. The mouth is the outboard bearing and the bore's rear
    the inboard one, and what matters is how far apart they are.
    """
    from mech.head import (BORE_X0, NOZZLE_BACK, NOZZLE_L, NOSE_X, SKIN_X, WALL_X,
                           press_fit_length)
    assert press_fit_length() >= 15.0, press_fit_length()
    tip = NOZZLE_BACK + NOZZLE_L
    assert 1.0 <= tip - SKIN_X <= 2.0, tip - SKIN_X          # through the wall and no further
    assert SKIN_X - WALL_X > 2.0                             # ... and the mouth is real bearing
    assert BORE_X0 <= NOZZLE_BACK                            # the bore takes it
    # the holder's nose runs out to its own clip sphere, a clearance short of the face's lip
    assert NOSE_X > P.NOZZLE_HOLDER_X[1] + 8.0
    holder = parts["nozzle_holder"]
    bore = cyl_x(P.NOZZLE_D / 2 - 0.05, BORE_X0 + 0.05, NOSE_X - 0.05, 0, P.Z_MOUTH)
    assert (bore & holder).volume < 1e-6                     # the bore is clear the whole way


def test_nozzle_holder_keeps_clear_of_the_head(parts):
    """A loose part inside the face: inside the wall, off the seating lip, off the cradle's rails."""
    holder = parts["nozzle_holder"]
    inner = Pos(0, 0, P.Z_HEAD) * Sphere(P.HEAD_R - P.WALL)
    assert (holder - inner).volume < 1e-6                              # never into the shell
    for name in ("head_lip", "cradle_rails", "tilt_cradle", "face_stop", "nozzle_bosses"):
        assert (holder & parts[name]).volume < 1e-6, name


def test_nozzle_bosses_reach_the_faces_inner_wall(parts):
    """Each boss runs out to the skin, 1.2 mm into the wall like every other interface part."""
    from mech.head import BOSS_R, screw_points
    bosses = parts["nozzle_bosses"]
    assert len(bosses.solids()) == 2                                   # joined only through the face
    assert (bosses - Pos(0, 0, P.Z_HEAD) * Sphere(P.HEAD_R - P.WALL)).volume > 1e-3          # into the wall
    assert (bosses - Pos(0, 0, P.Z_HEAD) * Sphere(P.HEAD_R - P.WALL + 1.2)).volume < 1e-6    # and no further
    for y, z in screw_points():
        probe = cyl_x(0.2, P.NOZZLE_HOLDER_X[1] + P.INSERT_DEPTH, P.HEAD_R + 10, y, z)
        tip = (probe & bosses).bounding_box().max.X
        reach = math.sqrt((P.HEAD_R - P.WALL) ** 2 - y ** 2 - (z - P.Z_HEAD) ** 2)
        assert tip >= reach, (y, z, tip, reach)                        # it meets the inner wall
        blind = cyl_x(P.INSERT_D / 2, P.NOZZLE_HOLDER_X[1] + P.INSERT_DEPTH,
                      P.NOZZLE_HOLDER_X[1] + P.INSERT_DEPTH + 1.0, y, z)
        assert (blind & bosses).volume > 1e-3, (y, z)                  # the insert stops short


def test_the_holders_screws_can_be_driven_from_behind(parts):
    """A stubby driver on each screw head, 30 mm of it, meets nothing on its way in."""
    from mech.head import DRIVER_R, screw_points
    servo = servo_body(P.MG996R, (0, P.TILT_SERVO_SHAFT_Y, P.Z_HEAD), axis="y")
    x0 = P.NOZZLE_HOLDER_X[0]
    inside = Pos(0, 0, P.Z_HEAD) * Sphere(P.HEAD_R - P.WALL)
    for y, z in screw_points():
        driver = cyl_x(DRIVER_R, x0 - 30.0, x0, y, z)
        assert (driver - inside).volume < 1e-6, (y, z)                 # stays in the cavity
        assert (driver & servo).volume < 1e-6, (y, z)
        for name in ("nozzle_holder", "nozzle_bosses", "tilt_cradle", "cradle_rails",
                     "head_lip", "face_stop", "coupler", "ear_boss", "yoke"):
            assert (driver & parts[name]).volume < 1e-6, (y, z, name)


def test_the_tube_reaches_the_shaft_in_one_bend(parts):
    """The barb faces -X on the centreline; one TUBE_BEND_R turn puts the tube down the pan axis.

    The bend radius is what fixes the barb's x: NOZZLE_HOLDER_X[0] is 15 and so is TUBE_BEND_R,
    which is why the arc lands on the axis rather than beside it. Its height is fixed from
    below by the cradle rails, which the tube has to pass under.
    """
    from mech.head import BARB_Z, tube_route
    route = tube_route()
    bb = route.bounding_box()
    assert math.isclose(bb.min.X, -P.TUBE_OD / 2, abs_tol=1e-6)        # it ends on the pan axis
    assert bb.max.X <= P.NOZZLE_HOLDER_X[0] + 1.0 + 1e-6
    assert math.isclose(bb.min.Z, P.Z_PLATE_TOP + 6.0, abs_tol=1e-6)   # down to the shaft's flare
    assert BARB_Z + P.TUBE_OD / 2 <= P.CRADLE_Z[0] - P.RAIL_H          # under the rails
    assert BARB_Z - P.TUBE_BEND_R >= P.Z_HEAD - P.HEAD_R               # on the axis before it leaves
    servo = servo_body(P.MG996R, (0, P.TILT_SERVO_SHAFT_Y, P.Z_HEAD), axis="y")
    assert (route & servo).volume < 1e-6
    for name in ("nozzle_holder", "nozzle_bosses", "tilt_cradle", "cradle_rails", "head_lip",
                 "face_stop", "coupler", "ear_boss", "yoke", "plate", "shaft", "deck"):
        assert (route & parts[name]).volume < 1e-6, name
    # inside the head's cavity until it drops through the bottom opening, and no further out
    cavity = Pos(0, 0, P.Z_HEAD) * Sphere(P.HEAD_R - P.WALL)
    opening = cyl_z(P.HEAD_OPENING_R, 300.0, P.Z_HEAD - (P.HEAD_R - P.WALL) + 1.0)
    assert (route - (cavity + opening)).volume < 1e-6


def test_the_holder_prints_on_its_back_face(parts):
    """Nothing behind x = NOZZLE_HOLDER_X[0]: it stands on that face and everything grows forward."""
    assert math.isclose(parts["nozzle_holder"].bounding_box().min.X, P.NOZZLE_HOLDER_X[0], abs_tol=1e-6)


# --- the tank head ------------------------------------------------------------------------------

def test_tank_head_thread_matches_the_canister(parts):
    th = parts["tank_head"]
    bb = th.bounding_box()
    # the cap's axis is X, so the wall around the thread is what its Y and Z spans show
    assert bb.max.Y - bb.min.Y >= P.CAN_THREAD_MAJOR + 2 * 3 - 1e-6    # wall around the thread
    assert bb.max.Z - bb.min.Z >= P.CAN_THREAD_MAJOR + 2 * 3 - 1e-6


def test_tank_head_thread_sits_wholly_inside_its_bore(parts):
    from mech.base import BORE_R, TANK_HEAD_R, can_thread
    thread = can_thread()
    assert thread.volume > 1e-3
    bb = thread.bounding_box()
    assert 0.0 < bb.min.X and bb.max.X < P.CAN_THREAD_LEN              # inside the bore's length
    reach = max(abs(bb.min.Y), bb.max.Y, abs(bb.min.Z), bb.max.Z)
    # bd_warehouse sinks the roots a fraction into the bore so the union takes; past that the
    # thread would be cutting its own way out through the cap's three millimetres of wall
    assert BORE_R < reach <= BORE_R + 0.25, reach
    assert reach < TANK_HEAD_R - 2.0
    # ... and nothing narrower than the thread's own crest is left standing in the bore
    free = cyl_x(P.CAN_THREAD_MAJOR / 2 - 1.25 * P.CAN_THREAD_PITCH * math.sqrt(3) / 2 - 0.05,
                 -1, P.CAN_THREAD_LEN)
    assert (free & parts["tank_head"]).volume < 1e-6


def test_tank_head_ports_pass_the_canisters_neck(parts):
    """Every port opens inside the neck bore with a millimetre of rim, and none runs into another."""
    from mech.base import PORTS, TANK_HEAD_L
    for name, (y, z, r) in PORTS.items():
        assert math.hypot(y, z) + r <= P.CAN_NECK_ID / 2 - 1.0, name
        probe = cyl_x(r - 0.05, P.CAN_THREAD_LEN, TANK_HEAD_L - 0.05, y, z)
        assert (probe & parts["tank_head"]).volume < 1e-6, name        # drilled through
    for a, b in itertools.combinations(PORTS, 2):
        ya, za, ra = PORTS[a]
        yb, zb, rb = PORTS[b]
        assert math.hypot(ya - yb, za - zb) >= ra + rb + 1.0, (a, b)


def test_tank_head_closes_its_bore_with_a_cone(parts):
    """Printed mouth down, the bore's roof would be a flat Ø38 bridge. It is a 45 degree cone.

    Checked on the slope rather than on the model's tags: the cavity's radius falls by one
    millimetre for every millimetre of x, so no layer overhangs the one under it by more than
    its own height.
    """
    from mech.base import BORE_R, CONE_R1, CONE_X0, CONE_X1, TANK_HEAD_L
    assert math.isclose(CONE_X1 - CONE_X0, BORE_R - CONE_R1, abs_tol=1e-9)       # 45 degrees
    head = parts["tank_head"]
    for dx in (0.0, 4.0, 8.0, 12.0, 15.9):
        x = CONE_X0 + dx
        r = BORE_R - dx
        assert (cyl_x(r - 0.2, x + 0.05, x + 0.1) & head).volume < 1e-6, x
    assert CONE_X1 + 1.0 <= TANK_HEAD_L                                # a flat face for the ports


def test_the_filler_stub_rises_and_a_hose_can_reach_the_neck(parts, placed):
    """The stub pointed -X into ten millimetres of room. It rises instead, under the neck."""
    from mech.base import HOSE_R, STUB_R, STUB_TOP, STUB_X, hose_route, hose_turn
    assert P.FILLER_STUB_DIR == "+z"
    head = placed["tank_head"]
    top = P.CANISTER_Z0 + P.CANISTER[2] / 2 + STUB_TOP
    assert math.isclose(head.bounding_box().max.Z, top, abs_tol=1e-6)
    assert math.isclose(2 * STUB_R, P.FILLER_CAP_THREAD_MAJOR, abs_tol=1e-9)     # Ø22 over Ø14
    bore = cyl_z(P.FILLER_D / 2 - 0.05, top - 16.0, top + 1.0,
                 P.CANISTER_XY[0] - P.CANISTER[0] / 2 - STUB_X, P.CANISTER_XY[1])
    assert (bore & head).volume < 1e-6                                 # open all the way down
    assert hose_turn() < 5.0, hose_turn()                              # the run is all but straight
    route = hose_route()
    assert (route - _base_inner()).volume < 1e-6                       # inside the wall
    from mech.common import canister_body, pump_body, valve_body
    for name, body in (("canister", canister_body()), ("pump", pump_body()), ("valve", valve_body()),
                       ("tank_head", head), ("tank_cradle", placed["tank_cradle"]),
                       ("pump_plate", placed["pump_plate"]), ("valve_strap", placed["valve_strap"])):
        assert (route & body).volume < 1e-6, name


def test_filler_cap_screws_onto_a_filler_neck(parts):
    """The cap takes a neck whose crests stand at FILLER_CAP_THREAD_MAJOR over a FILLER_D bore."""
    from mech.base import CAP_THREAD_LEN, CAP_THREAD_X, filler_neck
    cap = parts["filler_cap"]
    neck = filler_neck()
    assert neck.volume > 1e-3
    bb = neck.bounding_box()
    assert math.isclose(bb.max.Y - bb.min.Y, P.FILLER_CAP_THREAD_MAJOR, abs_tol=0.01)   # crests at the major
    assert (cyl_x(P.FILLER_D / 2 - 0.05, bb.min.X - 1, bb.max.X + 1) & neck).volume < 1e-6   # FILLER_D bore
    assert (neck & cap).volume < 1e-3                                  # it screws on, it does not jam
    grip = cyl_x(P.FILLER_CAP_THREAD_MAJOR / 2 - 0.05, CAP_THREAD_X, CAP_THREAD_X + CAP_THREAD_LEN)
    assert (grip & cap).volume > 1e-3                                  # ... and the cap's crests bite


# --- the bridge over the canister ------------------------------------------------------------------

def test_wet_zone_parts_stand_on_the_floor_under_the_belt(placed):
    bb = placed["tank_cradle"].bounding_box()
    assert math.isclose(bb.min.Z, P.Z_FLOOR, abs_tol=1e-6)
    for name in ("tank_cradle", "pump_plate", "valve_strap"):
        assert placed[name].bounding_box().max.Z < P.Z_BELT - 2 * P.RING_T, name


def test_canister_and_pump_fit_inside_the_base(placed):
    """The whole wet zone: nothing overlaps, nothing reaches the wall, nothing reaches the belt."""
    from mech.common import canister_body, pump_body, valve_body
    inner = _base_inner()
    bodies = {"canister": canister_body(), "pump": pump_body(), "valve": valve_body(),
              "pump_plate": placed["pump_plate"], "tank_cradle": placed["tank_cradle"],
              "tank_head": placed["tank_head"], "valve_strap": placed["valve_strap"]}
    for name, body in bodies.items():
        assert (body - inner).volume < 1e-6, name                      # inside the wall with a millimetre
        assert body.bounding_box().max.Z < P.Z_BELT - 2 * P.RING_T, name
    for a, b in itertools.combinations(bodies, 2):
        assert (bodies[a] & bodies[b]).volume < 1e-6, (a, b)


def test_the_cradles_towers_carry_the_pump_plate(placed):
    """The legs are part of the cradle now, so the plate is flat and the cradle prints upright."""
    from mech.base import PLATE_Z0, TOWER_XY, tower_inserts
    from mech.common import canister_body
    cradle, plate = placed["tank_cradle"], placed["pump_plate"]
    assert math.isclose(cradle.bounding_box().max.Z, PLATE_Z0, abs_tol=1e-6)     # up to the plate
    # the cradle holds the canister, so it touches it; the towers stand beside its ends and the
    # plate bridges clear over its top
    assert TOWER_XY[0] - P.PUMP_LEG / 2 >= P.CANISTER[0] / 2 + 2.0
    assert (plate & _grown(canister_body())).volume < 1e-6
    # a tower corner stands at least two millimetres inside the raised floor's rim
    corner = math.hypot(TOWER_XY[0] + P.PUMP_LEG / 2, TOWER_XY[1] + P.PUMP_LEG / 2)
    assert corner <= P.BASE_FLOOR_R - 2.0, corner
    for x, y in tower_inserts():                                       # the screws line up
        through = cyl_z(P.M3_CLEAR / 2 - 0.05, PLATE_Z0 - 0.01, PLATE_Z0 + 10.0, x, y)
        assert (through & plate).volume < 1e-6, (x, y)                 # clear through the plate
        blind = cyl_z(P.INSERT_D / 2 - 0.05, PLATE_Z0 - P.INSERT_DEPTH + 0.1, PLATE_Z0 - 0.1, x, y)
        assert (blind & cradle).volume < 1e-6, (x, y)                  # into an insert in the tower


def test_the_pump_is_held_down_and_the_valve_strapped(placed):
    """Grommets alone only damp the pump; a tie through the slots beside each is what holds it."""
    from mech.base import GROMMET_R, PLATE_Z0, PLATE_Z1, STRAP_X, TIE_SLOT, _feet_xy, _strap_xy
    plate, strap = placed["pump_plate"], placed["valve_strap"]
    assert P.PUMP_TIE_SLOTS
    for x, y in _feet_xy():
        pocket = cyl_z(GROMMET_R - 0.05, PLATE_Z0 - 1, PLATE_Z1 + 1, x, y)
        assert (pocket & plate).volume < 1e-6, (x, y)                  # the grommet snaps through
        w, t = TIE_SLOT
        for dy in (-(GROMMET_R + 3.0), GROMMET_R + 3.0):               # a tie slot either side
            slot = box(x - w / 2 + 0.05, x + w / 2 - 0.05, y + dy - t / 2 + 0.05,
                       y + dy + t / 2 - 0.05, PLATE_Z0 - 1, PLATE_Z1 + 1)
            assert (slot & plate).volume < 1e-6, (x, y, dy)
    # the strap is a bar over the valve, bolted either side of it into the plate's inserts
    w, t = P.VALVE_STRAP
    bb = strap.bounding_box()
    assert math.isclose(bb.max.Y - bb.min.Y, w, abs_tol=1e-6)
    assert math.isclose(bb.max.Z - bb.min.Z, t, abs_tol=1e-6)
    assert math.isclose(bb.min.Z, P.PUMP_Z0 + P.VALVE[2], abs_tol=1e-6)          # it lies on the valve
    assert STRAP_X > P.VALVE[0] / 2                                              # ... bolted outside it
    for x, y in _strap_xy():
        bolt = cyl_z(P.M3_CLEAR / 2 - 0.05, bb.min.Z - 1, bb.max.Z + 1, x, y)
        assert (bolt & strap).volume < 1e-6, (x, y)
        seat = cyl_z(P.INSERT_D / 2 - 0.05, PLATE_Z1 + 2.0 - P.INSERT_DEPTH + 0.1, PLATE_Z1 + 1.9, x, y)
        assert (seat & plate).volume < 1e-6, (x, y)


def test_the_bridge_prints_without_support(parts):
    """The plate lies on its underside and the cradle stands up; neither grows outward as it rises."""
    from mech.base import PLATE_Z0
    plate, cradle = parts["pump_plate"], parts["tank_cradle"]
    assert math.isclose(plate.bounding_box().min.Z, PLATE_Z0, abs_tol=1e-6)      # no boss below it
    foot = (cradle & box(-200, 200, -200, 200, P.Z_FLOOR, P.Z_FLOOR + 1.0)).bounding_box()
    for z in (40.0, 60.0, 90.0, 120.0, 140.0):
        band = cradle & box(-200, 200, -200, 200, z, z + 1.0)
        bb = band.bounding_box()
        assert bb.min.X >= foot.min.X - 1e-6 and bb.max.X <= foot.max.X + 1e-6, z
        assert bb.min.Y >= foot.min.Y - 1e-6 and bb.max.Y <= foot.max.Y + 1e-6, z
