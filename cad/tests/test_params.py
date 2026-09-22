import math
import params as P


def test_total_height_is_550():
    assert P.Z_TOP == 550.0


def test_every_section_fits_the_bed():
    for name, (lo, hi) in P.SECTION_Z.items():
        assert hi - lo <= P.BED, name
    assert 2 * max(r for r, _ in P.BASE_PROFILE) <= P.BED
    assert 2 * max(r for r, _ in P.TORSO_PROFILE) <= P.BED
    assert 2 * P.HAT_BRIM_R <= P.BED


def test_shell_radius_interpolates_the_profile():
    assert P.shell_r(P.BASE_PROFILE, 0) == 112.0
    assert P.shell_r(P.BASE_PROFILE, 90) == 125.0
    assert math.isclose(P.shell_r(P.BASE_PROFILE, 45), 118.5)


def test_phone_lies_above_the_belt_and_below_the_deck_ring():
    bottom = P.Z_LENS - P.PHONE_CAM_FROM_END
    top = bottom + P.PHONE_L
    assert bottom > P.Z_BASE_TOP + P.CHASSIS_T
    assert top < P.Z_DECK - P.DECK_T - P.RING_T


def test_linkage_band_is_clear_of_the_head():
    # the highest point of the pan linkage must sit under the head's underside at that radius
    r = P.CRANK_L
    underside = P.Z_HEAD - math.sqrt(P.HEAD_R ** 2 - r ** 2)
    assert P.Z_LINK_TOP + P.SCREW_HEAD_H < underside


def test_hard_stops_sit_outside_the_fixture_limits():
    import json
    from pathlib import Path
    cfg = json.loads(json.load(open(Path(__file__).resolve().parents[2] / "protocol/fixtures/commands.json"))["cfg"])
    assert P.PAN_STOP_DEG > cfg["panMax"] and -P.PAN_STOP_DEG < cfg["panMin"]
    assert P.TILT_STOP[0] < cfg["tiltMin"] and P.TILT_STOP[1] > cfg["tiltMax"]
