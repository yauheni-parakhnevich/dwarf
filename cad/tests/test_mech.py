import math
import pytest
from build123d import Axis, Location, Vertex
import params as P
from mech.common import box, cyl_z, cyl_y, servo_body


@pytest.fixture(scope="session")
def parts():
    import mech.turntable, mech.torso  # noqa: E401,F401
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
    assert math.isclose(bb.min.Z, P.Z_LINK_TOP, abs_tol=1e-6)           # the pin boss under the foot bar
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
    assert math.isclose(math.hypot(b[0] - a[0], b[1] - a[1]), P.PAN_OFFSET, abs_tol=1e-6)
    for x, y in (a, b):
        clear = cyl_z(P.PIN_BORE / 2 - 0.05, P.Z_LINK_BOTTOM - 1, P.Z_LINK_TOP + 1, x, y)
        assert (clear & link).volume < 1e-6, (x, y)                     # the bore is at least PIN_BORE
        wider = cyl_z(P.PIN_BORE / 2 + 0.05, P.Z_LINK_BOTTOM - 1, P.Z_LINK_TOP + 1, x, y)
        assert (wider & link).volume > 1e-3, (x, y)                     # ... and no wider
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


def _stop_pin_deg():
    return (P.PAN_STOP_DEG + math.degrees(math.asin((P.STOP_TAB_W / 2) / P.STOP_POST_R))
            + math.degrees(math.asin((P.STOP_POST_D / 2) / P.STOP_POST_R)))


def test_yoke_clears_the_pan_stop_posts_through_the_sweep(parts):
    pins = parts["stop_pin"] + parts["stop_pin"].rotate(Axis.Z, -2 * _stop_pin_deg())
    feet = parts["yoke"] & box(-80, 80, -80, 80, P.Z_PLATE_TOP - 1, P.Z_PLATE_TOP + P.YOKE_RING_T + 1)
    assert feet.bounding_box().min.Z >= P.STOP_PIN_TOP + 1.0             # a millimetre of daylight
    for deg in range(-64, 65, 5):
        assert (parts["yoke"].rotate(Axis.Z, deg) & pins).volume == 0, deg


def test_stop_pins_seat_in_the_deck(parts):
    pin = parts["stop_pin"]
    assert math.isclose(pin.bounding_box().max.Z, P.STOP_PIN_TOP, abs_tol=1e-6)
    for p in (pin, pin.rotate(Axis.Z, -2 * _stop_pin_deg())):
        assert (p & parts["deck"]).volume == 0                           # each sits in its own hole


def test_tilt_servo_fits_inside_the_head_and_on_the_bulkhead():
    body = servo_body(P.MG996R, (0, P.TILT_SERVO_SHAFT_Y, P.Z_HEAD), axis="y")
    for v in body.vertices():
        r = math.sqrt(v.X ** 2 + v.Y ** 2 + (v.Z - P.Z_HEAD) ** 2)
        assert r < P.HEAD_R - P.WALL, (v, r)
    assert math.isclose(body.bounding_box().min.Y + P.MG996R["tab_z"], P.BULKHEAD_Y, abs_tol=1e-6)


def test_the_cradle_takes_the_servo_without_touching_its_body(parts):
    body = servo_body(P.MG996R, (0, P.TILT_SERVO_SHAFT_Y, P.Z_HEAD), axis="y")
    assert (parts["tilt_cradle"] & body).volume < 1e-6        # the body hangs through the window
    along, across = P.MG996R["holes"]
    bb = body.bounding_box()
    zc = (bb.min.Z + bb.max.Z) / 2
    y_tip = P.BULKHEAD_Y - P.INSERT_DEPTH - 1.0
    for dz in (-along / 2, along / 2):                        # the bosses stay inside the head's wall
        r = math.sqrt((across / 2 + P.BULKHEAD_BOSS_D / 2) ** 2 + y_tip ** 2 + (zc + dz - P.Z_HEAD) ** 2)
        assert r < P.HEAD_R - P.WALL, (dz, r)
        assert P.CRADLE_Z[0] < zc + dz < P.CRADLE_Z[1], (dz, zc + dz)     # both bosses are on the plate


def test_coupler_passes_the_head_wall_and_seats_in_the_arm(parts):
    coupler, yoke = parts["coupler"], parts["yoke"]
    wall = cyl_y(P.HEAD_R, P.HEAD_R - P.WALL, P.HEAD_R, 0, P.Z_HEAD) - cyl_y(P.HEAD_BORE_D / 2, P.HEAD_R - P.WALL - 1, P.HEAD_R + 1, 0, P.Z_HEAD)
    assert (coupler & wall).volume < 1e-6                      # turns in the bore the assembler cuts
    assert (coupler & yoke).volume < 1e-3                      # hex sits in the hex pocket with clearance
    assert coupler.bounding_box().max.Y >= P.EAR_OUT_Y + P.YOKE_GAP + P.YOKE_ARM_T - 1e-6


def test_ear_tab_meets_the_pegs_only_at_the_stops(parts):
    """The stops must engage nose-up at TILT_STOP[1] and nose-down at TILT_STOP[0].

    build123d's rotate about +Y LOWERS the nose for a positive angle, so the machine's
    nose-up-positive tilt is -deg here. The marker proves it rather than trusting the sign.
    """
    ear, yoke = parts["ear_boss"], parts["yoke"]
    tilt_axis = Axis((0, 0, P.Z_HEAD), (0, 1, 0))
    nose = Vertex(P.HEAD_R, 0.0, P.Z_HEAD).rotate(tilt_axis, -P.TILT_STOP[1])
    assert nose.Z > P.Z_HEAD, nose                                       # +TILT_STOP[1] is nose up
    for deg in (P.TILT_STOP[0] + 3, 0, P.TILT_STOP[1] - 3):
        assert (ear.rotate(tilt_axis, -deg) & yoke).volume < 1e-6, deg
    for deg in (P.TILT_STOP[0] - 3, P.TILT_STOP[1] + 3):
        assert (ear.rotate(tilt_axis, -deg) & yoke).volume > 1e-3, deg


def test_tilt_cradle_slides_in_through_the_face(parts):
    unit = parts["tilt_cradle"] + servo_body(P.MG996R, (0, P.TILT_SERVO_SHAFT_Y, P.Z_HEAD), axis="y")
    inner = (P.HEAD_R - P.WALL) ** 2
    for dx in range(0, 41, 5):
        for v in unit.moved(Location((dx, 0, 0))).vertices():
            r2 = v.X ** 2 + v.Y ** 2 + (v.Z - P.Z_HEAD) ** 2
            assert r2 < inner or v.X > P.FACE_SPLIT_X, (dx, (v.X, v.Y, v.Z), math.sqrt(r2))
    for other in ("cradle_rails", "head_lip", "face_stop"):
        assert (unit & parts[other]).volume == 0, other
    assert (unit.moved(Location((-1, 0, 0))) & parts["cradle_rails"]).volume > 0    # the back wall stops it


def test_coupler_goes_in_from_outside(parts):
    coupler, yoke = parts["coupler"], parts["yoke"]
    body = servo_body(P.MG996R, (0, P.TILT_SERVO_SHAFT_Y, P.Z_HEAD), axis="y")
    for dy in (0, 10, 20, 30):
        moved = coupler.moved(Location((0, dy, 0)))
        assert (moved & body).volume == 0, dy
        assert (moved & yoke).volume == 0, dy
    assert coupler.moved(Location((0, 30, 0))).bounding_box().min.Y > P.HEAD_R


def test_horn_screw_driver_path(parts):
    coupler = parts["coupler"]
    y_in = P.TILT_SERVO_SHAFT_Y + P.HORN_T
    _, y_arm1 = P.EAR_OUT_Y + P.YOKE_GAP, P.EAR_OUT_Y + P.YOKE_GAP + P.YOKE_ARM_T
    for a in P.HORN_SCREWS_USED:
        hx = P.HORN_SCREW_R * math.cos(math.radians(a))
        hz = P.HORN_SCREW_R * math.sin(math.radians(a))
        bore = cyl_y(P.HORN_ACCESS_D / 2 - 0.05, y_in + 2.0, y_arm1, hx, P.Z_HEAD + hz)
        assert (bore & coupler).volume < 1e-6, a


def test_phone_slot_fits_the_phone_with_clearance(parts):
    from mech.common import phone_body
    sled = parts["phone_sled"]
    phone = phone_body()
    assert (sled & phone).volume < 1e-6                        # the phone drops in
    # the slot is not sloppy: growing the phone by 2*CLEAR in thickness makes it collide
    fat = box(P.PHONE_FRONT_X - P.CLEAR - 0.05, P.PHONE_BACK_X + P.CLEAR + 0.05,
              P.PHONE_Y_OFFSET - P.PHONE_W / 2, P.PHONE_Y_OFFSET + P.PHONE_W / 2,
              P.PHONE_BOTTOM_Z, P.PHONE_BOTTOM_Z + P.PHONE_L)
    assert (sled & fat).volume > 0


def test_phone_sled_only_fits_camera_down(parts):
    """Flip the phone end for end: the lens clip now sits where the sled has no cutout."""
    sled = parts["phone_sled"]
    clip = box(P.PHONE_BACK_X, P.LENS_FRONT_X, P.CAM_Y - 12, P.CAM_Y + 12, P.Z_LENS - 12, P.Z_LENS + 12)     # correct way
    assert (sled & clip).volume < 1e-6
    # flipped end for end, the camera moves to the top and mirrors to y = -CAM_Y. The sled's back
    # holds the phone there, so the clip standing proud of the back glass has nowhere to go and
    # the phone cannot seat.
    flipped_phone = box(P.PHONE_FRONT_X, P.PHONE_BACK_X + 1,
                        P.PHONE_Y_OFFSET - P.PHONE_W / 2, P.PHONE_Y_OFFSET + P.PHONE_W / 2,
                        P.PHONE_BOTTOM_Z, P.PHONE_BOTTOM_Z + P.PHONE_L)
    assert (sled & flipped_phone).volume > 0


def test_nothing_stands_in_the_phones_volume(parts):
    """Every dry-zone part keeps out of the phone: the sled's pocket surrounds it, nothing touches it."""
    from mech.common import phone_body
    phone = phone_body()
    for name in ("belt_flange_lower", "belt_flange_upper", "divider", "chassis",
                 "phone_sled", "electronics_deck", "fan_frame"):
        assert (phone & parts[name]).volume < 1e-6, name


def test_belt_screws_line_up(parts):
    lower, upper, divider = parts["belt_flange_lower"], parts["belt_flange_upper"], parts["divider"]
    for a in P.FLANGE_SCREW_ANGLES:
        x = P.FLANGE_SCREW_R * math.cos(math.radians(a)); y = P.FLANGE_SCREW_R * math.sin(math.radians(a))
        probe = cyl_z(P.M3_CLEAR / 2 - 0.05, P.Z_BELT - 4, P.Z_BASE_TOP + P.RING_T + 1, x, y)
        assert (probe & upper).volume < 1e-6, a
        assert (probe & divider).volume < 1e-6, a
        insert = cyl_z(P.INSERT_D / 2 - 0.05, P.Z_BELT - P.INSERT_DEPTH + 0.1, P.Z_BELT - 0.1, x, y)
        assert (insert & lower).volume < 1e-6, a


def test_divider_fills_the_base_cup(parts):
    bb = parts["divider"].bounding_box()
    assert math.isclose(bb.min.Z, P.Z_BELT, abs_tol=1e-6)
    assert math.isclose(bb.max.Z, P.Z_BASE_TOP, abs_tol=1e-6)
    assert bb.max.X <= P.shell_r(P.BASE_PROFILE, P.Z_BELT) - P.WALL - P.CLEAR + 1e-6


def test_electronics_fit_on_the_deck():
    boards = [P.ESP32, P.XL4015, P.XL4015, P.MOSFET, P.MOSFET, P.MOSFET]
    assert sum(w * h for w, h in boards) * 1.3 <= P.EDECK_L * P.EDECK_W


def test_lower_belt_flange_follows_the_bases_flare(parts):
    """Revolved, not a straight ring: at every height it reaches the wall, and through none of it.

    Measured on a slice rather than by intersecting a thin probe ring: a ring half a millimetre
    off the revolve's conical face makes OCCT return nonsense (an empty common and a cut bigger
    than the ring itself), which would pass for the wrong reason.
    """
    flange = parts["belt_flange_lower"]
    z0 = P.Z_BELT - 2 * P.RING_T
    for z in (z0, z0 + 4, z0 + 8, z0 + 12, P.Z_BELT):
        band = flange & box(-120, 120, -120, 120, max(z0, z - 0.5), min(P.Z_BELT, z + 0.5))
        r_max = max(math.hypot(v.X, v.Y) for v in band.vertices())
        assert r_max > P.ring_r_out(P.BASE_PROFILE, z, z) - 0.5, (z, r_max)   # out at the wall here
        assert r_max < P.shell_r(P.BASE_PROFILE, z) + 0.1, (z, r_max)         # never through the skin


def test_fan_frame_follows_the_barrel(parts):
    """Clipped to the wall: it reaches the wall at every height and stands proud of the skin nowhere."""
    frame = parts["fan_frame"]
    for z in (P.Z_FAN - P.FAN / 2 - 5, P.Z_FAN, P.Z_FAN + P.FAN / 2 + 5):
        band = frame & box(-120, 120, -120, 120, z - 0.5, z + 0.5)
        r_max = max(math.hypot(p.X, p.Y) for p in band.vertices())
        assert r_max < P.shell_r(P.TORSO_PROFILE, z), (z, r_max)                       # inside the skin
        assert r_max > P.shell_r(P.TORSO_PROFILE, z) - P.WALL - 0.5, (z, r_max)        # out at the wall
