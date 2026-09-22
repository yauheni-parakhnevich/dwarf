import math
import pytest
from build123d import Axis
import params as P
from mech.common import box, cyl_z, servo_body


@pytest.fixture(scope="session")
def parts():
    import mech.turntable  # noqa: F401
    from mech import ALL
    return {name: fn() for name, fn in ALL}


def _bb(p):
    return p.bounding_box().size


def test_every_part_is_one_valid_solid(parts):
    for name, p in parts.items():
        assert p.is_valid, name
        assert len(p.solids()) == 1, name
        assert p.volume > 0, name


def test_every_part_fits_the_bed(parts):
    for name, p in parts.items():
        s = _bb(p)
        assert max(s.X, s.Y, s.Z) <= P.BED, (name, s)


def test_deck_ring_is_cut_around_the_pan_servo(parts):
    body = servo_body(P.DS3218, (P.PAN_SERVO_XY[0], P.PAN_SERVO_XY[1], P.Z_PAN_SHAFT_FACE), axis="-z")
    assert (body & parts["deck_ring"]).volume < 1e-6


def test_deck_bore_clears_the_shaft(parts):
    deck = parts["deck"]
    # a probe cylinder of the shaft's radius plus clearance passes through the deck untouched
    probe = cyl_z(P.SHAFT_OD / 2 + P.CLEAR, P.Z_DECK - P.DECK_T - 1, P.Z_DECK + 1)
    assert (deck & probe).volume < 1e-6


def test_shaft_bore_takes_tube_and_wires():
    assert P.SHAFT_ID >= 6.0 + 3 * 1.5 + 1.5


def test_plate_sits_on_the_bearing_and_hangs_its_column(parts):
    plate = parts["plate"]
    bb = plate.bounding_box()
    assert math.isclose(bb.max.Z, P.Z_PLATE_TOP, abs_tol=1e-6)          # nothing above the disc
    assert math.isclose(bb.min.Z, P.Z_CRANK_BOTTOM, abs_tol=1e-6)       # the foot bar's underside
    below = plate & box(-80, 80, -80, 80, P.Z_CRANK_BOTTOM - 1, P.Z_DECK + P.BEARING_T - 0.01)
    b = below.bounding_box()
    assert b.min.X >= P.PAN_FOOT_R_IN - 1e-6 and b.max.X <= P.PAN_COLUMN[1] + 1e-6   # only column and foot down here
    assert abs(b.min.Y) <= P.PAN_COLUMN[2] / 2 + 1e-6 and abs(b.max.Y) <= P.PAN_COLUMN[2] / 2 + 1e-6
    pin, _ = crank_pins(0)                                              # the foot's pin insert is blind
    probe = cyl_z(P.INSERT_D / 2, P.Z_CRANK_BOTTOM - 1, P.Z_CRANK_TOP, pin[0], pin[1])
    assert (probe & plate).volume > 1e-3


def crank_pins(deg):
    a = math.radians(P.CRANK_REST_DEG + deg)
    v = (P.CRANK_L * math.cos(a), P.CRANK_L * math.sin(a))
    return v, (P.PAN_SERVO_XY[0] + v[0], P.PAN_SERVO_XY[1] + v[1])


def test_link_eyes_are_a_centre_distance_apart(parts):
    link = parts["pan_link"]
    bb = link.bounding_box()
    assert math.isclose(bb.max.Z, P.Z_LINK_TOP, abs_tol=1e-6) and math.isclose(bb.min.Z, P.Z_LINK_BOTTOM, abs_tol=1e-6)
    a, b = crank_pins(0)
    for x, y in (a, b):
        probe = cyl_z(P.M3_CLEAR / 2 - 0.05, P.Z_LINK_BOTTOM - 1, P.Z_LINK_TOP + 1, x, y)
        assert (probe & link).volume < 1e-6, (x, y)                     # a bore at each pin
    assert math.isclose(bb.max.X - bb.min.X, abs(a[0] - b[0]) + 2 * P.LINK_EYE_R, abs_tol=0.01)


def test_the_cranks_pin_insert_is_blind(parts):
    _, pin = crank_pins(0)
    probe = cyl_z(P.INSERT_D / 2, P.Z_CRANK_BOTTOM - 1, P.Z_CRANK_TOP, pin[0], pin[1])
    assert (probe & parts["servo_crank"]).volume > 1e-3


def test_link_and_crank_live_below_the_deck_ring(parts):
    ring_bottom = P.Z_DECK - P.DECK_T - P.RING_T
    for name in ("pan_link", "servo_crank"):
        assert parts[name].bounding_box().max.Z < ring_bottom, name


def test_linkage_sweeps_without_touching_anything(parts):
    """Plate (with its column) about the pan axis, servo crank about the servo axis, link translated."""
    from build123d import Axis, Location
    servo_axis = Axis((P.PAN_SERVO_XY[0], P.PAN_SERVO_XY[1], 0), (0, 0, 1))
    rest_plate, _ = crank_pins(0)
    servo = servo_body(P.DS3218, (P.PAN_SERVO_XY[0], P.PAN_SERVO_XY[1], P.Z_PAN_SHAFT_FACE), axis="-z")
    fixed = parts["deck"] + parts["deck_ring"] + servo
    for deg in range(-int(P.PAN_STOP_DEG) + 1, int(P.PAN_STOP_DEG), 8):
        plate = (parts["plate"] + parts["yoke"]).rotate(Axis.Z, deg)
        crank = parts["servo_crank"].rotate(servo_axis, deg)
        pin, _ = crank_pins(deg)
        link = parts["pan_link"].moved(Location((pin[0] - rest_plate[0], pin[1] - rest_plate[1], 0)))
        for a, b, what in ((plate, crank, "plate/crank"), (plate, fixed, "plate/fixed"), (crank, fixed, "crank/fixed"),
                           (link, plate, "link/plate"), (link, crank, "link/crank"), (link, fixed, "link/fixed")):
            v = (a & b).volume
            assert v < 1e-3, (deg, what, v)


def test_pan_servo_hangs_from_the_deck_and_touches_nothing_else(parts):
    body = servo_body(P.DS3218, (P.PAN_SERVO_XY[0], P.PAN_SERVO_XY[1], P.Z_PAN_SHAFT_FACE), axis="-z")
    bearing = box(-P.BEARING_SQ / 2, P.BEARING_SQ / 2, -P.BEARING_SQ / 2, P.BEARING_SQ / 2, P.Z_DECK, P.Z_DECK + P.BEARING_T)
    for other in (bearing, parts["deck"], parts["deck_ring"], parts["plate"], parts["yoke"], parts["shaft"]):
        assert (body & other).volume < 1e-6
    # the hangers meet the tabs: a hanger's bottom face is at the tabs' upper face
    hangers = parts["deck"] & box(-80, 80, -80, 80, P.Z_DECK - P.DECK_T - 30, P.Z_DECK - P.DECK_T - 0.01)
    assert math.isclose(hangers.bounding_box().min.Z, P.Z_PAN_SHAFT_FACE + (P.DS3218["body"][2] - P.DS3218["tab_z"]) + P.DS3218["tab_t"], abs_tol=1e-6)


def test_yoke_clears_the_pan_stop_posts_through_the_sweep(parts):
    from build123d import Axis
    posts = parts["deck"] & box(-80, 80, -80, 80, P.Z_DECK + 0.1, P.Z_PLATE_TOP + 2)
    for deg in (-P.PAN_STOP_DEG + 1, 0, P.PAN_STOP_DEG - 1):
        assert (parts["yoke"].rotate(Axis.Z, deg) & posts).volume < 1e-6, deg


def test_tilt_servo_fits_inside_the_head_and_on_the_bulkhead():
    from mech.common import servo_body
    body = servo_body(P.MG996R, (0, P.TILT_SERVO_SHAFT_Y, P.Z_HEAD), axis="y")
    for v in body.vertices():
        r = math.sqrt(v.X ** 2 + v.Y ** 2 + (v.Z - P.Z_HEAD) ** 2)
        assert r < P.HEAD_R - P.WALL, (v, r)
    assert math.isclose(body.bounding_box().min.Y + P.MG996R["tab_z"], P.BULKHEAD_Y, abs_tol=1e-6)


def test_the_bulkhead_takes_the_servo_without_touching_its_body(parts):
    body = servo_body(P.MG996R, (0, P.TILT_SERVO_SHAFT_Y, P.Z_HEAD), axis="y")
    assert (parts["tilt_bulkhead"] & body).volume < 1e-6      # the body hangs through the window
    along, across = P.MG996R["holes"]
    zc = P.Z_HEAD + P.MG996R["shaft_off"] - P.MG996R["body"][0] / 2
    y_tip = P.BULKHEAD_Y - P.INSERT_DEPTH - 1.0
    for dz in (-along / 2, along / 2):                        # the bosses stay inside the head's wall
        r = math.sqrt((across / 2 + P.BULKHEAD_BOSS_D / 2) ** 2 + y_tip ** 2 + (zc + dz - P.Z_HEAD) ** 2)
        assert r < P.HEAD_R - P.WALL, (dz, r)


def test_coupler_passes_the_head_wall_and_seats_in_the_arm(parts):
    from mech.common import cyl_y
    coupler, yoke = parts["coupler"], parts["yoke"]
    wall = cyl_y(P.HEAD_R, P.HEAD_R - P.WALL, P.HEAD_R, 0, P.Z_HEAD) - cyl_y(P.COUPLER_D / 2 + P.CLEAR, P.HEAD_R - P.WALL - 1, P.HEAD_R + 1, 0, P.Z_HEAD)
    assert (coupler & wall).volume < 1e-6                      # turns in the bore the assembler cuts
    assert (coupler & yoke).volume < 1e-3                      # hex sits in the hex pocket with clearance
    assert coupler.bounding_box().max.Y >= P.EAR_OUT_Y + P.YOKE_GAP + P.YOKE_ARM_T - 1e-6


def test_ear_tab_meets_the_pegs_only_at_the_stops(parts):
    from build123d import Axis
    ear, yoke = parts["ear_boss"], parts["yoke"]
    tilt_axis = Axis((0, 0, P.Z_HEAD), (0, 1, 0))
    for deg in (P.TILT_STOP[0] + 3, 0, P.TILT_STOP[1] - 3):
        assert (ear.rotate(tilt_axis, deg) & yoke).volume < 1e-6, deg
    for deg in (P.TILT_STOP[0] - 3, P.TILT_STOP[1] + 3):
        assert (ear.rotate(tilt_axis, deg) & yoke).volume > 1e-3, deg
