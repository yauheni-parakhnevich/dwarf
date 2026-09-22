import itertools
import math
import pytest
from build123d import Axis, Location, Plane, Polygon, Pos, Sphere, Vertex, revolve
import params as P
from mech.common import box, cyl_x, cyl_z, cyl_y, servo_body


@pytest.fixture(scope="session")
def parts():
    import mech.turntable, mech.torso, mech.head, mech.base  # noqa: E401,F401
    from mech import ALL
    return {name: fn() for name, fn in ALL}


def _bb(p):
    return p.bounding_box().size


def test_every_part_is_one_valid_solid(parts):
    from mech import INTERFACES
    multi_ok = {n for names in INTERFACES.values() for n in names}
    for name, p in parts.items():
        assert p.is_valid, name
        assert len(p.solids()) == 1 or name in multi_ok, name
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
    top = P.Z_HEAD + P.YOKE_ARM_W / 2                          # the cross screw's insert stops short
    probe = cyl_z(P.INSERT_D / 2, top - P.INSERT_DEPTH_SHORT - 0.5, top, 0, P.EAR_OUT_Y + P.YOKE_GAP + P.YOKE_ARM_T / 2)
    assert (probe & coupler).volume < 1e-6                     # ... of the pocket, so it cannot foul the hex
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


def test_nozzle_holder_bore_is_on_the_mouth_axis(parts):
    probe = cyl_x(P.NOZZLE_D / 2 - 0.05, P.NOZZLE_HOLDER_X[0] - 1, P.NOZZLE_HOLDER_X[1] + 1, 0, P.Z_MOUTH)
    assert (probe & parts["nozzle_holder"]).volume < 1e-6


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
        # on the boss's own axis, past the insert's blind end: how far forward it reaches
        probe = cyl_x(0.2, P.NOZZLE_HOLDER_X[1] + P.INSERT_DEPTH, P.HEAD_R + 10, y, z)
        tip = (probe & bosses).bounding_box().max.X
        reach = math.sqrt((P.HEAD_R - P.WALL) ** 2 - y ** 2 - (z - P.Z_HEAD) ** 2)
        assert tip >= reach, (y, z, tip, reach)                        # it meets the inner wall
        blind = cyl_x(P.INSERT_D / 2, P.NOZZLE_HOLDER_X[1] + P.INSERT_DEPTH,
                      P.NOZZLE_HOLDER_X[1] + P.INSERT_DEPTH + 1.0, y, z)
        assert (blind & bosses).volume > 1e-3, (y, z)                  # the insert stops short of the skin


def test_the_holders_screws_can_be_driven_from_behind(parts):
    """A stubby driver on each screw head, 30 mm of it, meets nothing on its way in."""
    from mech.head import DRIVER_R, screw_points
    servo = servo_body(P.MG996R, (0, P.TILT_SERVO_SHAFT_Y, P.Z_HEAD), axis="y")
    x0 = P.NOZZLE_HOLDER_X[0]
    inside = Pos(0, 0, P.Z_HEAD) * Sphere(P.HEAD_R - P.WALL)
    for y, z in screw_points():
        driver = cyl_x(DRIVER_R, x0 - 30.0, x0, y, z)
        assert (driver - inside).volume < 1e-6, (y, z)                 # the driver stays in the cavity
        assert (driver & servo).volume < 1e-6, (y, z)
        for name in ("nozzle_holder", "nozzle_bosses", "tilt_cradle", "cradle_rails",
                     "head_lip", "face_stop", "coupler", "ear_boss", "yoke"):
            assert (driver & parts[name]).volume < 1e-6, (y, z, name)


def test_tank_head_thread_matches_the_canister(parts):
    th = parts["tank_head"]
    bb = th.bounding_box()
    # the cap's axis is X, so the wall around the thread is what its Y and Z spans show
    assert bb.max.Y - bb.min.Y >= P.CAN_THREAD_MAJOR + 2 * 3 - 1e-6    # wall around the thread
    assert bb.max.Z - bb.min.Z >= P.CAN_THREAD_MAJOR + 2 * 3 - 1e-6


def test_tank_head_thread_sits_wholly_inside_its_bore(parts):
    from mech.base import BORE_R, TANK_HEAD_AT, TANK_HEAD_R, can_thread
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
    assert (TANK_HEAD_AT * free & parts["tank_head"]).volume < 1e-6


def test_tank_head_ports_pass_the_canisters_neck(parts):
    """Every port opens inside the neck bore with a millimetre of rim, and none runs into another."""
    from mech.base import PORTS, TANK_HEAD_AT, TANK_HEAD_L
    for name, (y, z, r) in PORTS.items():
        assert math.hypot(y, z) + r <= P.CAN_NECK_ID / 2 - 1.0, name
        probe = cyl_x(r - 0.05, P.CAN_THREAD_LEN, TANK_HEAD_L - 0.05, y, z)
        assert (TANK_HEAD_AT * probe & parts["tank_head"]).volume < 1e-6, name   # drilled through
    for a, b in itertools.combinations(PORTS, 2):
        ya, za, ra = PORTS[a]
        yb, zb, rb = PORTS[b]
        assert math.hypot(ya - yb, za - zb) >= ra + rb + 1.0, (a, b)


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
    # ... and it grips: the cap's crests stand inside the neck's major diameter
    grip = cyl_x(P.FILLER_CAP_THREAD_MAJOR / 2 - 0.05, CAP_THREAD_X, CAP_THREAD_X + CAP_THREAD_LEN)
    assert (grip & cap).volume > 1e-3


def test_wet_zone_parts_stand_on_the_floor_under_the_belt(parts):
    for name in ("tank_cradle", "pump_mount"):
        bb = parts[name].bounding_box()
        assert math.isclose(bb.min.Z, P.Z_FLOOR, abs_tol=1e-6), name
        assert bb.max.Z < P.Z_BELT - 2 * P.RING_T, name


def _base_inner():
    """The base's cavity with a millimetre to spare: shell_r - WALL - 1 at every height."""
    pts = [(P.shell_r(P.BASE_PROFILE, z) - P.WALL - 1.0, z) for _, z in P.BASE_PROFILE]
    z0, z1 = P.BASE_PROFILE[0][1], P.BASE_PROFILE[-1][1]
    return revolve(Plane.XZ * Polygon((0.0, z0), *pts, (0.0, z1)), axis=Axis.Z)


def test_canister_and_pump_fit_inside_the_base(parts):
    """The whole wet zone: nothing overlaps, nothing reaches the wall, nothing reaches the belt."""
    from mech.common import canister_body, pump_body, valve_body
    inner = _base_inner()
    bodies = {"canister": canister_body(), "pump": pump_body(), "valve": valve_body(),
              "pump_mount": parts["pump_mount"], "tank_cradle": parts["tank_cradle"],
              "tank_head": parts["tank_head"]}
    for name, body in bodies.items():
        assert (body - inner).volume < 1e-6, name                      # inside the wall with a millimetre
        assert body.bounding_box().max.Z < P.Z_BELT - 2 * P.RING_T, name
    for a, b in itertools.combinations(bodies, 2):
        assert (bodies[a] & bodies[b]).volume < 1e-6, (a, b)


def test_the_pump_mount_bridges_the_canister(parts):
    """It stands off the canister by a millimetre and reaches the floor on its four legs."""
    from mech.common import canister_body
    mount = parts["pump_mount"]
    grown = canister_body()
    bb = grown.bounding_box()
    grown = box(bb.min.X - 1, bb.max.X + 1, bb.min.Y - 1, bb.max.Y + 1, bb.min.Z - 1, bb.max.Z + 1)
    assert (mount & grown).volume < 1e-6
    assert (mount & parts["tank_cradle"]).volume < 1e-6
    feet = mount & box(-200, 200, -200, 200, P.Z_FLOOR - 1, P.Z_FLOOR + 1)
    assert len(feet.solids()) == 4                                     # four legs, nothing else, on the floor
