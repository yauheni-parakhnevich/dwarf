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


def crank_pins(deg):
    """Plate pin and servo pin at a pan angle: both cranks are CRANK_L at CRANK_REST_DEG + deg."""
    a = math.radians(P.CRANK_REST_DEG + deg)
    v = (P.CRANK_L * math.cos(a), P.CRANK_L * math.sin(a))
    return v, (P.PAN_SERVO_XY[0] + v[0], P.PAN_SERVO_XY[1] + v[1])


def _segment_distance_from_origin(p, q):
    px, py = p
    qx, qy = q
    dx, dy = qx - px, qy - py
    t = max(0.0, min(1.0, -(px * dx + py * dy) / (dx * dx + dy * dy)))
    return math.hypot(px + t * dx, py + t * dy)


def test_pan_linkage_lives_below_the_deck_and_above_the_electronics():
    assert P.Z_CRANK_TOP < P.Z_DECK - P.DECK_T - P.RING_T
    assert P.Z_LINK_BOTTOM - P.SCREW_HEAD_H > P.Z_CHASSIS + P.CHASSIS_T + P.EDECK_STANDOFF + P.EDECK_T + 20


def test_pan_linkage_sweeps_inside_the_torso():
    for z in (P.Z_LINK_BOTTOM, P.Z_CRANK_TOP):
        wall = P.shell_r(P.TORSO_PROFILE, z) - P.WALL
        for deg in range(-int(P.PAN_STOP_DEG), int(P.PAN_STOP_DEG) + 1):
            plate_pin, servo_pin = crank_pins(deg)
            worst = max(math.hypot(*plate_pin), math.hypot(*servo_pin)) + P.LINK_EYE_R
            assert worst + 3.0 < wall, (z, deg, worst, wall)


def test_cranks_and_link_keep_clear_of_the_tube_below_the_shaft():
    """The tube and wires drop out of the shaft's bottom on the pan axis; nothing may sweep across them."""
    keep = P.SHAFT_ID / 2 + 4.0 + 4.0       # tube radius, slack, half a bar
    for deg in range(-int(P.PAN_STOP_DEG), int(P.PAN_STOP_DEG) + 1):
        plate_pin, servo_pin = crank_pins(deg)
        assert _segment_distance_from_origin(P.PAN_SERVO_XY, servo_pin) > keep, ("servo crank", deg)
        assert _segment_distance_from_origin(plate_pin, servo_pin) > keep, ("link", deg)


def test_pan_servo_hangs_clear_of_deck_and_shaft():
    L, W, H = P.DS3218["body"]
    assert P.Z_PAN_SHAFT_FACE + H < P.Z_DECK - P.DECK_T         # under the deck
    (x0, y0), (x1, y1) = P.PAN_RING_CUT
    for hx, hy in P.pan_hangers():                             # hangers inside the ring's cut, off the shaft
        assert x0 < hx - P.PAN_HANGER / 2 and hx + P.PAN_HANGER / 2 < x1
        assert y0 < hy - P.PAN_HANGER / 2 and hy + P.PAN_HANGER / 2 < y1
        assert math.hypot(hx, hy) - P.PAN_HANGER / math.sqrt(2) > P.SHAFT_OD / 2 + 3.0
        assert math.hypot(hx, hy) + P.PAN_HANGER / math.sqrt(2) < P.DECK_R
    assert abs(P.PAN_SERVO_XY[1]) + W / 2 + 2.0 < P.shell_r(P.TORSO_PROFILE, P.Z_PAN_SHAFT_FACE) - P.WALL


def test_plate_column_slot_misses_the_bearing_the_screws_and_the_hangers():
    r0, r1, half = P.DECK_SLOT
    assert r0 > P.BEARING_SQ / 2 * math.sqrt(2) + 1.0       # outside the fixed plate's corners
    for ang in P.DECK_SCREW_ANGLES:
        a = (ang + 180) % 360 - 180
        assert abs(a) > half + 6 or not (r0 - 3 < P.DECK_SCREW_R < r1 + 3), ang
    assert P.STOP_POST_R - P.STOP_POST_D / 2 > r1 + 2.0
    assert P.STOP_POST_R + P.STOP_POST_D / 2 < P.DECK_R
    for hx, hy in P.pan_hangers():
        r, a = math.hypot(hx, hy), math.degrees(math.atan2(hy, hx))
        inner_corner = r - P.PAN_HANGER / math.sqrt(2)
        assert abs(a) > half + 8 or inner_corner > r1 + 2.0, (hx, hy, inner_corner)


def test_pan_foot_and_column_stay_off_the_stop_posts():
    # the plate's column at the front sweeps ±PAN_STOP_DEG; the stop posts must sit outside its arc
    half_col = math.degrees(math.atan2(P.PAN_COLUMN[2] / 2, P.PAN_COLUMN[0]))
    for sign in (1, -1):
        post = sign * (P.PAN_STOP_DEG + math.degrees(math.atan2(P.STOP_TAB_W / 2, P.PLATE_R)) + math.degrees(math.atan2(P.STOP_POST_D / 2, P.STOP_POST_R)))
        assert abs(post) > P.PAN_STOP_DEG + half_col


def test_deck_screws_keep_clear_of_the_servo_hangers():
    hangers = P.pan_hangers()
    for ang in P.DECK_SCREW_ANGLES:
        x = P.DECK_SCREW_R * math.cos(math.radians(ang)); y = P.DECK_SCREW_R * math.sin(math.radians(ang))
        for hx, hy in hangers:
            assert math.hypot(x - hx, y - hy) > P.PAN_HANGER / 2 + P.M3_CLEAR / 2 + 2.0, (ang, hx, hy)


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
