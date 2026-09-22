import math
import pytest
from build123d import Axis
import params as P
from mech.common import box


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
    from mech.common import servo_body
    body = servo_body(P.DS3218, (P.PAN_SERVO_XY[0], P.PAN_SERVO_XY[1], P.PAN_SERVO_BODY_Z0 + P.DS3218["body"][2]), axis="z")
    assert (body & parts["deck_ring"]).volume < 1e-6


def test_deck_bore_clears_the_shaft(parts):
    deck = parts["deck"]
    # a probe cylinder of the shaft's radius plus clearance passes through the deck untouched
    from mech.common import cyl_z
    probe = cyl_z(P.SHAFT_OD / 2 + P.CLEAR, P.Z_DECK - P.DECK_T - 1, P.Z_DECK + 1)
    assert (deck & probe).volume < 1e-6


def test_shaft_bore_takes_tube_and_wires():
    assert P.SHAFT_ID >= 6.0 + 3 * 1.5 + 1.5


def test_plate_sits_on_the_bearing_and_carries_the_crank_post(parts):
    plate = parts["plate"]
    bb = plate.bounding_box()
    assert math.isclose(bb.min.Z, P.Z_DECK + P.BEARING_T, abs_tol=1e-6)
    assert math.isclose(bb.max.Z, P.Z_CRANK_TOP, abs_tol=1e-6)          # the pin post
    disc = plate & box(-60, 60, -60, 60, P.Z_DECK + P.BEARING_T - 1, P.Z_PLATE_TOP + 0.5)
    assert math.isclose(disc.bounding_box().max.Z, P.Z_PLATE_TOP, abs_tol=1e-6)


def crank_pins(deg):
    a = math.radians(P.CRANK_REST_DEG + deg)
    v = (P.CRANK_L * math.cos(a), P.CRANK_L * math.sin(a))
    return v, (-P.PAN_OFFSET + v[0], v[1])


def test_link_eyes_are_a_centre_distance_apart(parts):
    s = _bb(parts["pan_link"])
    assert math.isclose(s.X, P.PAN_OFFSET + 2 * P.LINK_EYE_R, abs_tol=0.01)
    assert math.isclose(s.Y, 2 * P.LINK_EYE_R, abs_tol=0.01)


def test_link_and_cranks_stay_below_the_head(parts):
    for name in ("pan_link", "servo_crank"):
        top = parts[name].bounding_box().max.Z
        assert top <= P.Z_LINK_TOP + 1e-6, name


def test_linkage_sweeps_without_touching_anything_fixed(parts):
    """Rotate the plate about the pan axis and the servo crank about the servo axis; translate the link."""
    from build123d import Axis, Location
    servo_axis = Axis((-P.PAN_OFFSET, 0, 0), (0, 0, 1))
    rest_plate, _ = crank_pins(0)
    fixed = parts["deck"] + parts["deck_ring"]
    for deg in range(-int(P.PAN_STOP_DEG) + 1, int(P.PAN_STOP_DEG), 8):
        plate = (parts["plate"] + parts["yoke"]).rotate(Axis.Z, deg)
        crank = parts["servo_crank"].rotate(servo_axis, deg)
        pin, _ = crank_pins(deg)
        link = parts["pan_link"].moved(Location((pin[0] - rest_plate[0], pin[1] - rest_plate[1], 0)))
        for a, b, what in ((plate, crank, "plate/crank"), (plate, fixed, "plate/deck"), (crank, fixed, "crank/deck"),
                           (link, plate, "link/plate"), (link, crank, "link/crank"), (link, fixed, "link/deck")):
            v = (a & b).volume
            assert v < 1e-3, (deg, what, v)


def test_pan_servo_does_not_hit_the_bearing_deck_or_ring(parts):
    from mech.common import servo_body, box
    body = servo_body(P.DS3218, (P.PAN_SERVO_XY[0], P.PAN_SERVO_XY[1], P.PAN_SERVO_BODY_Z0 + P.DS3218["body"][2]), axis="z")
    bearing = box(-P.BEARING_SQ / 2, P.BEARING_SQ / 2, -P.BEARING_SQ / 2, P.BEARING_SQ / 2, P.Z_DECK, P.Z_DECK + P.BEARING_T)
    for other in (bearing, parts["deck"], parts["deck_ring"], parts["plate"], parts["yoke"]):
        assert (body & other).volume < 1e-6


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
