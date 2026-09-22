import math
import pytest
from build123d import Axis
import params as P


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


def test_plate_sits_on_the_bearing(parts):
    plate = parts["plate"]
    bb = plate.bounding_box()
    assert math.isclose(bb.min.Z, P.Z_DECK + P.BEARING_T, abs_tol=1e-6)
    assert math.isclose(bb.max.Z, P.Z_PLATE_TOP, abs_tol=1e-6)
