import math
import pytest
import params as P


def test_the_stack_adds_up_from_the_floor_to_the_hat():
    assert P.Z_TOP == 700.0
    order = [0.0, P.Z_FLOOR, P.Z_BELT, P.Z_BASE_TOP, P.PHONE_BOTTOM_Z, P.Z_CHASSIS, P.Z_DECK, P.Z_PLATE_TOP,
             P.Z_HEAD - P.HEAD_R, P.Z_HEAD, P.Z_HAT, P.Z_HAT + P.HAT_BRIM_T, P.Z_TOP]
    assert order == sorted(order), order
    for name, (lo, hi) in P.SECTION_Z.items():
        assert 0.0 <= lo < hi <= P.Z_TOP, name




def test_shell_radius_interpolates_the_profile():
    assert P.shell_r(P.BASE_PROFILE, 0) == 112.0
    assert P.shell_r(P.BASE_PROFILE, 90) == 125.0
    assert math.isclose(P.shell_r(P.BASE_PROFILE, 45), 118.5)


def test_shell_radius_takes_the_outer_side_of_a_step():
    stepped = [(10.0, 0.0), (20.0, 50.0), (30.0, 50.0), (40.0, 100.0)]
    assert P.shell_r(stepped, 50) == 30.0
    assert P.shell_r(stepped, 100) == 40.0




def test_phone_stands_on_the_divider_and_under_the_deck():
    bottom = P.PHONE_BOTTOM_Z
    top = bottom + P.PHONE_L
    assert bottom > P.Z_BASE_TOP + P.DIVIDER_PROUD + P.SLED_WALL      # the tray's floor is above the divider
    assert top + 2.0 < P.Z_DECK - P.DECK_T                             # under the deck with 2 mm
    # ... and the phone comes down through the cage's open front, not past a leg: its widest
    # corner is well inside the half-angle the foot ring leaves clear about +X
    corner = math.degrees(math.atan2(P.PHONE_W / 2, P.PHONE_FRONT_X))
    assert corner < P.CAGE_FOOT_OPEN - 10.0, corner




crank_pins = P.crank_pins


def _segment_distance_from_origin(p, q):
    px, py = p
    qx, qy = q
    dx, dy = qx - px, qy - py
    t = max(0.0, min(1.0, -(px * dx + py * dy) / (dx * dx + dy * dy)))
    return math.hypot(px + t * dx, py + t * dy)


def test_pan_linkage_lives_below_the_deck_and_above_the_electronics():
    from mech.nod import TUBE_UNDER
    assert P.Z_CRANK_TOP < P.Z_DECK - P.DECK_T - P.RING_T
    assert TUBE_UNDER[2] + P.TUBE_OD / 2 + 2.0 < P.Z_LINK_BOTTOM      # the tube passes under the link
    assert P.Z_LINK_BOTTOM - P.SCREW_HEAD_H > P.Z_CHASSIS + P.CHASSIS_T + P.EDECK_STANDOFF + P.EDECK_T + 20




def test_cranks_and_link_keep_clear_of_the_pan_axis():
    """Neither bar of the parallelogram crosses the pan axis: the nod servo's lead and the loom
    come down it past the link's plane. The tube itself goes under the link's plane (test_pose
    measures that gap); the keep-out here is a loom of 3 wires, slack and half a bar."""
    keep = 4.0 + 2.0 + 4.0                   # the loom, slack, half a bar
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
        assert math.hypot(hx, hy) - P.PAN_HANGER / math.sqrt(2) > P.BEARING_OD / 2 + 3.0   # off the bearing
        assert math.hypot(hx, hy) + P.PAN_HANGER / math.sqrt(2) < P.DECK_LOBE["r"]     # under the deck's lobe
    assert abs(P.PAN_SERVO_XY[1]) + W / 2 + 2.0 < P.shell_r(P.TORSO_PROFILE, P.Z_PAN_SHAFT_FACE) - P.WALL


def test_plate_column_slot_misses_the_bearing_the_screws_and_the_hangers():
    r0, r1, half = P.DECK_SLOT
    assert r0 > P.CAP_R + 1.0                               # outside the bearing's cap
    for ang in P.DECK_SCREW_ANGLES:
        a = (ang + 180) % 360 - 180
        assert abs(a) > half + 6 or not (r0 - 3 < P.DECK_SCREW_R < r1 + 3), ang
    assert P.STOP_POST_R - P.STOP_POST_D / 2 > r1 + 2.0
    assert P.STOP_POST_R + P.STOP_POST_D / 2 < P.DECK_R
    for hx, hy in P.pan_hangers():
        r, a = math.hypot(hx, hy), math.degrees(math.atan2(hy, hx))
        inner_corner = r - P.PAN_HANGER / math.sqrt(2)
        assert abs(a) > half + 8 or inner_corner > r1 + 2.0, (hx, hy, inner_corner)


def test_pan_column_and_stop_pins_never_meet():
    # the plate's column sweeps an annulus in front of the deck; the stop pins stand outside it
    column_outer = math.hypot(P.PAN_COLUMN[1], P.PAN_COLUMN[2] / 2)
    pin_inner = P.STOP_POST_R - P.STOP_POST_D / 2
    assert pin_inner - column_outer > 2.0
    # and the pins do sit where the tab meets them at the stop, not before
    assert P.stop_pin_deg() > P.PAN_STOP_DEG


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


def _fixture():
    import json
    from pathlib import Path
    return json.loads(json.load(open(Path(__file__).resolve().parents[2] / "protocol/fixtures/commands.json"))["cfg"])


def test_the_nod_stops_bracket_the_nod_range_by_a_degree():
    """The owner's range is -15..+5, nose up positive; the printed stops are a degree outside it,
    so a command at the end of the range never finds plastic and a runaway one never finds the
    servo's own end stop."""
    assert P.NOD_STOP == (P.NOD_RANGE[0] - 3.0, P.NOD_RANGE[1] + 3.0)
    assert P.NOD_REACH == P.NOD_STOP                                     # the parting covers them
    assert P.STEM_LEAN == -(P.NOD_RANGE[0] + P.NOD_RANGE[1]) / 2        # the swing is centred


@pytest.mark.xfail(strict=True, reason="firmware follow-up on another branch: tiltMin/tiltMax in "
                                       "firmware/lib/dwarf/types.h and the protocol fixture are still "
                                       "-30/+40 from the nozzle arm; the head nods -15..+5")
def test_the_firmware_tilt_limits_sit_inside_the_nod_stops():
    cfg = _fixture()
    assert P.NOD_STOP[0] < cfg["tiltMin"] and cfg["tiltMax"] < P.NOD_STOP[1]


def test_hard_stops_sit_outside_the_fixture_limits():
    cfg = _fixture()
    assert P.PAN_STOP_DEG > cfg["panMax"] and -P.PAN_STOP_DEG < cfg["panMin"]


def statue_features():
    """out/statue/features.json, or a skip.

    Every layout test below is measured against the statue's own mesh. There used to be a table
    of the fit report's numbers here to fall back on, and in a clone without cad/in/ five tests
    quietly passed against it while the mesh said something else. test_fit.py skips without the
    statue and so does this.
    """
    import json
    from pathlib import Path
    f = Path(__file__).resolve().parents[1] / "out" / "statue" / "features.json"
    if not f.exists():
        pytest.skip("the statue stage has not written features.json")
    return json.load(open(f))


def statue_reach():
    """The cavity's reach about the pan axis every 5 mm, as the statue stage measured it."""
    return {float(k): v for k, v in statue_features()["reach"].items()}


def statue_legs():
    """The two trouser legs' centres and free radius, as the statue stage measured them."""
    legs = statue_features()["legs"]
    return {"left": tuple(legs["left"][:2]), "right": tuple(legs["right"][:2]), "r": float(legs["r"])}


def reach_at(z):
    """(min, front, back, left, right) cavity reach at height z, interpolated between the table's rows."""
    table = statue_reach()
    zs = sorted(table)
    if z <= zs[0]:
        return tuple(table[zs[0]])
    if z >= zs[-1]:
        return tuple(table[zs[-1]])
    below = max(k for k in zs if k <= z)
    above = min(k for k in zs if k >= z)
    if above == below:
        return tuple(table[below])
    f = (z - below) / (above - below)
    return tuple(a + (b - a) * f for a, b in zip(table[below], table[above]))


def test_every_statue_section_fits_the_bed():
    for name, (lo, hi) in P.SECTIONS_STATUE.items():
        assert hi - lo <= P.BED, name
    assert P.Z_TOP - P.Z_HAT <= P.BED                    # the hat is the tallest piece


def test_phone_stays_inside_the_statues_belly():
    top = P.PHONE_BOTTOM_Z + P.PHONE_L
    for z in (P.PHONE_BOTTOM_Z, P.Z_LENS, 300.0, top):
        _, front, _, left, right = reach_at(z)
        assert P.LENS_FRONT_X + P.LENS_GAP + P.ACRYLIC_T <= front + 1.0, (z, front)   # the pane sits inside the wall
        assert P.PHONE_Y_OFFSET + P.PHONE_W / 2 + P.SLED_WALL + 2 < min(left, right), z


def test_pan_linkage_sweeps_inside_the_statue():
    # the servo pin is the outermost thing; at its worst azimuth (towards -Y) the right-hand reach binds
    for z in (P.Z_LINK_BOTTOM, P.Z_CRANK_TOP):
        _, _, _, _, right = reach_at(z)
        worst = 0.0
        for deg in range(-int(P.PAN_STOP_DEG), int(P.PAN_STOP_DEG) + 1):
            plate_pin, servo_pin = P.crank_pins(deg)
            worst = max(worst, math.hypot(*servo_pin))
        assert worst + P.LINK_EYE_R + 3.0 < right, (z, worst, right)


def test_the_deck_and_the_spider_fit_the_neck():
    """The deck's lobe covers the servo's hangers and stays inside the socket's inner sphere, and
    the spider's bosses stand inside the head at the height of its screws."""
    h = P.PAN_HANGER / 2
    hangers = max(math.hypot(x + dx, y + dy) for x, y in P.pan_hangers() for dx in (-h, h) for dy in (-h, h))
    assert hangers < P.DECK_LOBE["r"]
    inner = P.NECK_SPHERE_R - P.TURN_GAP - P.WALL - P.DECK_SOCKET_MARGIN
    assert hangers <= math.sqrt(inner ** 2 - (P.Z_DECK - P.DECK_T - P.Z_NOD) ** 2) + 0.05, hangers
    assert P.SPIDER_BOSS_R + 3.0 < reach_at(P.HEAD_SCREWS_Z)[0]


def test_belt_ring_fits_the_coats_section():
    _, front, back, left, right = reach_at(P.Z_BELT)
    assert P.BELT_RX + 1.0 < min(front, back)
    assert P.BELT_RY + 1.0 < min(left, right)
    assert P.BELT_IN_RX < P.CHASSIS_RX < P.BELT_RX          # it rests on the ring, front and back,
    assert P.CHASSIS_RY < P.BELT_RY                          # inside the ring's outside all round


def test_wet_zone_envelopes_fit():
    """The bottle in the belly, and the pump and the valve in the legs the statue measured."""
    ceiling = P.Z_BELT - P.FLANGE_LOWER_H
    assert P.BOTTLE_Z0 + P.BOTTLE[2] + 2 < ceiling                      # the bottle under the lower flange
    _, front, back, left, right = reach_at(P.BOTTLE_Z0 + P.BOTTLE[2] / 2)
    assert P.BOTTLE[1] / 2 + 2 < min(left, right)
    assert P.BOTTLE[0] / 2 + 2 < min(front, back)
    legs = statue_legs()                             # the mesh's radius, not LEG_R's 38 mm guess
    for part in (P.PUMP, P.VALVE):                                      # each stands in one leg
        assert math.hypot(part[0], part[1]) / 2 + 2 < legs["r"], part
    # ... and the two legs are far enough apart that the two cages cannot touch, walls and all
    wall = 3.0                                                          # mech.base's BRACKET_WALL
    gap = abs(legs["left"][1] - legs["right"][1]) - (P.PUMP[1] + P.VALVE[1]) / 2 - 2 * wall
    assert gap > 2.0, (gap, legs)
    assert P.PUMP_Z0 > P.SAND_Z_TOP and P.VALVE_Z0 > P.SAND_Z_TOP
