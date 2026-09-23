import math
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
    assert P.PHONE_FRONT_X > P.RING_R_OUT                              # and outside the deck ring's annulus




crank_pins = P.crank_pins


def _segment_distance_from_origin(p, q):
    px, py = p
    qx, qy = q
    dx, dy = qx - px, qy - py
    t = max(0.0, min(1.0, -(px * dx + py * dy) / (dx * dx + dy * dy)))
    return math.hypot(px + t * dx, py + t * dy)


def test_pan_linkage_lives_below_the_deck_and_above_the_electronics():
    assert P.Z_CRANK_TOP < P.Z_DECK - P.DECK_T - P.RING_T
    assert P.SHAFT_BOTTOM < P.Z_LINK_BOTTOM                   # the tube leaves the shaft below the link
    assert P.Z_LINK_BOTTOM - P.SCREW_HEAD_H > P.Z_CHASSIS + P.CHASSIS_T + P.EDECK_STANDOFF + P.EDECK_T + 20




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
        assert math.hypot(hx, hy) + P.PAN_HANGER / math.sqrt(2) < P.DECK_LOBE["r"]     # under the deck's lobe
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


def tilt(point, deg):
    """Rotate (x, z) about the tilt axis; positive is nose up, the machine's convention."""
    dx, dz = point[0], point[1] - P.Z_HEAD
    a = math.radians(deg)
    return dx * math.cos(a) - dz * math.sin(a), P.Z_HEAD + dx * math.sin(a) + dz * math.cos(a)


def test_tilt_stops_bracket_the_firmware_range_with_margin():
    # the nozzle arm's convention is nose-up positive; the stops sit at least 3 degrees outside cfg
    import json
    from pathlib import Path
    cfg = json.loads(json.load(open(Path(__file__).resolve().parents[2] / "protocol/fixtures/commands.json"))["cfg"])
    assert P.TILT_STOP[0] <= cfg["tiltMin"] - 3 and P.TILT_STOP[1] >= cfg["tiltMax"] + 3




def test_hard_stops_sit_outside_the_fixture_limits():
    import json
    from pathlib import Path
    cfg = json.loads(json.load(open(Path(__file__).resolve().parents[2] / "protocol/fixtures/commands.json"))["cfg"])
    assert P.PAN_STOP_DEG > cfg["panMax"] and -P.PAN_STOP_DEG < cfg["panMin"]
    assert P.TILT_STOP[0] < cfg["tiltMin"] and P.TILT_STOP[1] > cfg["tiltMax"]


# The statue's cavity reach about the pan axis at 700 mm (fit report T8), used until the statue
# stage writes out/statue/features.json with the same table measured on the mesh.
def statue_reach():
    import json
    from pathlib import Path
    f = Path(__file__).resolve().parents[1] / "out" / "statue" / "features.json"
    if f.exists():
        data = json.load(open(f))
        if "reach" in data:
            return {float(k): v for k, v in data["reach"].items()}
    return {150: (51, 54, 93, 118, 102), 180: (90, 103, 95, 115, 115), 212: (83, 99, 83, 124, 124),
            230: (76, 99, 78, 133, 129), 250: (77, 96, 77, 133, 129), 265: (74, 98, 76, 129, 126),
            300: (72, 86, 72, 115, 109), 340: (71, 95, 74, 107, 98), 368: (71, 100, 74, 103, 86),
            392: (69, 92, 81, 114, 95), 400: (71, 85, 79, 114, 95), 411: (72, 72, 76, 106, 93),
            430: (69, 78, 76, 93, 85), 454: (57, 73, 84, 88, 75), 478: (44, 46, 86, 78, 69)}


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


def test_shroud_and_deck_fit_the_neck():
    _, front, back, left, right = reach_at(P.Z_DECK)
    assert P.DECK_R + 1.0 < min(front, left)             # the deck is a disc of DECK_R ...
    assert P.DECK_LOBE["r"] + 1.0 < right                # ... with a lobe over the servo hangers towards -Y
    assert P.DECK_BACK_R + 1.0 < back                    # ... and trimmed at the back
    hangers = max(math.hypot(x, y) + P.PAN_HANGER / math.sqrt(2) for x, y in P.pan_hangers())
    assert hangers < P.DECK_LOBE["r"]
    for z in (412.0, 430.0, 454.0):
        assert P.SHROUD_R_OUT + 3.0 < reach_at(z)[0], z


def test_belt_ring_fits_the_coats_section():
    _, front, back, left, right = reach_at(P.Z_BELT)
    assert P.BELT_RX + 1.0 < min(front, back)
    assert P.BELT_RY + 1.0 < min(left, right)
    assert P.CHASSIS_RX < P.BELT_IN_RX + 12 and P.CHASSIS_RY < P.BELT_IN_RY + 12   # it rests on the ring


def test_wet_zone_envelopes_fit_under_the_divider():
    ceiling = P.Z_BELT - P.FLANGE_LOWER_H
    assert P.Z_FLOOR + 4 + P.BOTTLE[2] + 2 < ceiling
    assert P.Z_FLOOR + 4 + P.PUMP[2] + 2 < ceiling
    _, front, back, left, right = reach_at(P.Z_FLOOR + 40)
    assert P.BOTTLE[1] / 2 + 2 < min(left, right)
    assert P.BOTTLE[0] + P.PUMP[1] + 4 < front + back                    # bottle in front, pump behind, along X


def test_nozzle_arm_stays_in_the_beard():
    px, _, pz = P.NOZZLE_PIVOT
    for deg in range(int(P.TILT_STOP[0]), int(P.TILT_STOP[1]) + 1):
        a = math.radians(deg)
        tip = (px + P.NOZZLE_ARM_L * math.cos(a), pz + P.NOZZLE_ARM_L * math.sin(a))
        assert tip[1] > P.Z_TURN + 10 and tip[1] < P.Z_HAT - 10, (deg, tip)
