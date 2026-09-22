import math
import params as P


def test_total_height_is_558():
    assert P.Z_TOP == 558.0


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


def test_shell_radius_takes_the_outer_side_of_a_step():
    stepped = [(10.0, 0.0), (20.0, 50.0), (30.0, 50.0), (40.0, 100.0)]
    assert P.shell_r(stepped, 50) == 30.0
    assert P.shell_r(stepped, 100) == 40.0


def test_interface_ring_never_breaks_the_skin():
    z0 = P.Z_DECK - P.DECK_T - P.RING_T
    z1 = P.Z_DECK - P.DECK_T
    r = P.ring_r_out(P.TORSO_PROFILE, z0, z1)
    for z in (z0, (z0 + z1) / 2, z1):
        assert r < P.shell_r(P.TORSO_PROFILE, z), z                    # never through the skin
        assert r > P.shell_r(P.TORSO_PROFILE, z) - P.WALL - 1.2, z     # embedded, or a gap the union bridges


def test_phone_lies_above_the_chassis_and_below_the_deck():
    bottom = P.Z_LENS - P.PHONE_CAM_FROM_END
    top = bottom + P.PHONE_L
    assert bottom > P.Z_CHASSIS + P.CHASSIS_T + P.SLED_WALL
    assert top < P.Z_DECK - P.DECK_T                 # under the deck itself
    assert P.PHONE_FRONT_X > P.RING_R_OUT            # and outside the deck ring's annulus


def test_phone_corners_clear_the_torso_wall():
    top = P.Z_LENS - P.PHONE_CAM_FROM_END + P.PHONE_L
    for z in (P.Z_LENS, 300.0, top):
        inner = P.shell_r(P.TORSO_PROFILE, z) - P.WALL
        corner = math.hypot(P.PHONE_BACK_X, P.PHONE_Y_OFFSET + P.PHONE_W / 2)
        assert corner < inner - 1.0, (z, corner, inner)


def test_linkage_band_is_clear_of_the_head():
    # the highest point of the pan linkage must sit under the head's underside at that radius
    r = P.CRANK_L
    underside = P.Z_HEAD - math.sqrt(P.HEAD_R ** 2 - r ** 2)
    assert P.Z_LINK_TOP + P.SCREW_HEAD_H < underside


def crank_pins(deg):
    """Plate pin and servo pin at a pan angle: both cranks are CRANK_L at CRANK_REST_DEG + deg."""
    a = math.radians(P.CRANK_REST_DEG + deg)
    v = (P.CRANK_L * math.cos(a), P.CRANK_L * math.sin(a))
    return v, (-P.PAN_OFFSET + v[0], v[1])


def _linkage_max_radius(deg):
    """Farthest point of the pan linkage from the pan axis at a pan angle."""
    plate_pin, servo_pin = crank_pins(deg)
    return max(math.hypot(*plate_pin), math.hypot(*servo_pin)) + P.LINK_EYE_R


def test_link_at_rest_clears_the_shaft_mouth():
    # the link is a bar 6 wide between the pins; at rest it must not lie across the shaft's flare
    plate_pin, servo_pin = crank_pins(0)
    assert min(abs(plate_pin[1]), abs(servo_pin[1])) - 3.0 > P.SHAFT_OD / 2 + 3.0 + 1.0


def test_pan_linkage_sweeps_inside_the_neck_and_the_collar():
    band = [P.Z_SERVO_HORN_TOP, P.Z_CRANK_TOP, P.Z_LINK_TOP, P.Z_LINK_TOP + P.SCREW_HEAD_H]
    worst = max(_linkage_max_radius(d) for d in range(-int(P.PAN_STOP_DEG), int(P.PAN_STOP_DEG) + 1))
    for z in band:
        wall = P.shell_r(P.TORSO_PROFILE, z) - P.WALL if z <= P.Z_TORSO_TOP else P.BEARD_R_IN_TOP
        assert worst + 3.0 < wall, (z, worst, wall)


def test_pan_servo_misses_the_deck_ring_cut():
    (x0, y0), (x1, y1) = P.PAN_RING_CUT
    L, W, _ = P.DS3218["body"]
    sx, sy = P.PAN_SERVO_XY
    assert x0 < sx - W / 2 and x1 > sx + W / 2
    tab = (P.DS3218["tab_span"] - L) / 2
    assert y0 < sy - (L - P.DS3218["shaft_off"]) - tab and y1 > sy + P.DS3218["shaft_off"] + tab


def test_deck_screws_keep_clear_of_the_servo_tab_screws():
    L, W, _ = P.DS3218["body"]
    along, across = P.DS3218["holes"]
    sx, sy = P.PAN_SERVO_XY
    cy = sy + P.DS3218["shaft_off"] - L / 2
    tabs = [(sx + dx, cy + dy) for dx in (-across / 2, across / 2) for dy in (-along / 2, along / 2)]
    for ang in P.DECK_SCREW_ANGLES:
        x = P.DECK_SCREW_R * math.cos(math.radians(ang)); y = P.DECK_SCREW_R * math.sin(math.radians(ang))
        for tx, ty in tabs:
            assert math.hypot(x - tx, y - ty) > P.M3_CLEAR + 4.0, (ang, tx, ty)


def test_window_and_intake_stay_above_the_belt_joint():
    window_bottom = P.Z_LENS + P.WINDOW_Z_BIAS - P.WINDOW_H / 2
    assert window_bottom > P.Z_BASE_TOP + P.RING_T          # above the torso flange
    assert P.Z_VENT_IN - P.VENT_IN_H / 2 > P.Z_BASE_TOP + P.RING_T


def test_hat_brim_clears_the_collar_at_full_tilt():
    # the brim's rear underside corner swings on a circle about the tilt axis
    dx, dz = -P.HAT_BRIM_R, P.Z_HAT - P.Z_HEAD
    for deg in P.TILT_STOP:
        a = math.radians(deg)
        x = dx * math.cos(a) - dz * math.sin(a)
        z = P.Z_HEAD + dx * math.sin(a) + dz * math.cos(a)
        if z < P.BEARD_TOP_Z + 1.0:
            assert abs(x) < P.BEARD_R_IN_TOP - 3.0, (deg, x, z)     # inboard of the collar, with its texture


def test_hard_stops_sit_outside_the_fixture_limits():
    import json
    from pathlib import Path
    cfg = json.loads(json.load(open(Path(__file__).resolve().parents[2] / "protocol/fixtures/commands.json"))["cfg"])
    assert P.PAN_STOP_DEG > cfg["panMax"] and -P.PAN_STOP_DEG < cfg["panMin"]
    assert P.TILT_STOP[0] < cfg["tiltMin"] and P.TILT_STOP[1] > cfg["tiltMax"]
