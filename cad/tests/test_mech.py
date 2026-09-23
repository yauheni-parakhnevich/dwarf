import itertools
import math
from build123d import Axis, Location, Pos, Sphere, Vertex
import params as P
from mech.common import box, cyl_x, cyl_z, cyl_y, polar, servo_body, skin_solid
from mech.turntable import BOSS_OUT, _radial_span


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


def test_shaft_bore_takes_tube_and_wires(parts):
    """Measured on the part, not on the parameter: the bore is SHAFT_ID end to end."""
    shaft = parts["shaft"]
    bb = shaft.bounding_box()
    clear = cyl_z(P.SHAFT_ID / 2 - 0.05, bb.min.Z - 1, bb.max.Z + 1)
    assert (clear & shaft).volume < 1e-6                     # SHAFT_ID passes from end to end
    assert (cyl_z(P.SHAFT_ID / 2 + 0.05, bb.min.Z - 1, bb.max.Z + 1) & shaft).volume > 1e-3
    assert P.SHAFT_ID >= P.TUBE_OD + 3 * 1.5 + 2             # tube, three wires and slack, spec 6


def test_plate_sits_on_the_bearing_and_hangs_its_column(parts):
    plate = parts["plate"]
    bb = plate.bounding_box()
    assert math.isclose(bb.max.Z, P.Z_PLATE_TOP, abs_tol=1e-6)          # nothing above the disc
    assert math.isclose(bb.min.Z, P.Z_LINK_TOP, abs_tol=1e-6)           # the pin boss under the foot bar
    below = plate & box(-80, 80, -80, 80, P.Z_CRANK_BOTTOM - 1, P.Z_DECK + P.BEARING_T - 0.01)
    b = below.bounding_box()
    assert b.min.X >= P.PAN_FOOT_R_IN - 1e-6 and b.max.X <= P.PAN_COLUMN[1] + 1e-6   # only column and foot down here
    assert abs(b.min.Y) <= P.PAN_COLUMN[2] / 2 + 1e-6 and abs(b.max.Y) <= P.PAN_COLUMN[2] / 2 + 1e-6
    pin, _ = P.crank_pins(0)                                              # the foot's pin insert is blind
    probe = cyl_z(P.INSERT_D / 2, P.Z_CRANK_BOTTOM - 1, P.Z_CRANK_TOP, pin[0], pin[1])
    assert (probe & plate).volume > 1e-3


def test_link_eyes_are_a_centre_distance_apart(parts):
    link = parts["pan_link"]
    bb = link.bounding_box()
    assert math.isclose(bb.max.Z, P.Z_LINK_TOP, abs_tol=1e-6) and math.isclose(bb.min.Z, P.Z_LINK_BOTTOM, abs_tol=1e-6)
    a, b = P.crank_pins(0)
    assert math.isclose(math.hypot(b[0] - a[0], b[1] - a[1]), P.PAN_OFFSET, abs_tol=1e-6)
    for x, y in (a, b):
        clear = cyl_z(P.PIN_BORE / 2 - 0.05, P.Z_LINK_BOTTOM - 1, P.Z_LINK_TOP + 1, x, y)
        assert (clear & link).volume < 1e-6, (x, y)                     # the bore is at least PIN_BORE
        wider = cyl_z(P.PIN_BORE / 2 + 0.05, P.Z_LINK_BOTTOM - 1, P.Z_LINK_TOP + 1, x, y)
        assert (wider & link).volume > 1e-3, (x, y)                     # ... and no wider
    assert math.isclose(bb.max.X - bb.min.X, abs(a[0] - b[0]) + 2 * P.LINK_EYE_R, abs_tol=0.01)


def test_the_cranks_pin_insert_is_blind(parts):
    _, pin = P.crank_pins(0)
    probe = cyl_z(P.INSERT_D / 2, P.Z_CRANK_BOTTOM - 1, P.Z_CRANK_TOP, pin[0], pin[1])
    assert (probe & parts["servo_crank"]).volume > 1e-3


def test_link_and_crank_live_below_the_deck_ring(parts):
    ring_bottom = P.Z_DECK - P.DECK_T - P.RING_T
    for name in ("pan_link", "servo_crank"):
        assert parts[name].bounding_box().max.Z < ring_bottom, name


def test_linkage_sweeps_without_touching_anything(parts):
    """Plate (with its column) about the pan axis, servo crank about the servo axis, link translated."""
    servo_axis = Axis((P.PAN_SERVO_XY[0], P.PAN_SERVO_XY[1], 0), (0, 0, 1))
    rest_plate, _ = P.crank_pins(0)
    servo = servo_body(P.DS3218, (P.PAN_SERVO_XY[0], P.PAN_SERVO_XY[1], P.Z_PAN_SHAFT_FACE), axis="-z")
    fixed = parts["deck"] + parts["deck_ring"] + parts["shaft"] + servo
    interior = range(-int(P.PAN_STOP_DEG) + 1, int(P.PAN_STOP_DEG), 8)
    for deg in [-P.PAN_STOP_DEG, *interior, P.PAN_STOP_DEG]:      # the stops themselves as well
        plate = (parts["plate"] + parts["yoke"]).rotate(Axis.Z, deg)
        crank = parts["servo_crank"].rotate(servo_axis, deg)
        pin, _ = P.crank_pins(deg)
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


def test_stop_pins_seat_in_the_deck(parts):
    pin = parts["stop_pin"]
    assert math.isclose(pin.bounding_box().max.Z, P.STOP_PIN_TOP, abs_tol=1e-6)
    for p in (pin, pin.rotate(Axis.Z, -2 * P.stop_pin_deg())):
        assert (p & parts["deck"]).volume == 0                           # each sits in its own hole


def test_the_shroud_fits_the_statues_cavity_and_takes_its_screws(parts):
    """The shroud is a body of revolution inside the beard: the chin is the tightest place."""
    import json
    from pathlib import Path
    cavity = {"chin": 57.0, "z400": 71.0}                      # from the fit report, at 700 mm
    feat = Path(__file__).resolve().parents[1] / "out/statue/features.json"
    if feat.exists():
        cavity.update(json.loads(feat.read_text()).get("cavity_r", {}))
    for where, r in cavity.items():
        assert P.SHROUD_R_OUT + 3.0 <= r, (where, r)
    shroud = parts["neck_shroud"]
    bb = shroud.bounding_box()
    assert math.isclose(bb.min.Z, P.SHROUD_BASE_Z, abs_tol=1e-6)
    assert math.isclose(bb.max.Z, P.SHROUD_TOP_Z, abs_tol=1e-6)
    for a in P.YOKE_SCREW_ANGLES:                              # down into the plate's inserts
        x, y = polar(P.YOKE_SCREW_R, a)
        shank = cyl_z(P.M3_CLEAR / 2 - 0.05, P.SHROUD_BASE_Z - 1, P.SHROUD_BASE_Z + 3, x, y)
        assert (shank & shroud).volume < 1e-6, a
    for a in P.SHROUD_SCREW_ANGLES:                            # ... and the head shell's, radially
        probe = _radial_span(P.SHROUD_R_OUT + BOSS_OUT - P.INSERT_DEPTH + 0.2,
                             P.SHROUD_R_OUT + BOSS_OUT + 1, a, P.SHROUD_SCREWS_Z, P.INSERT_D / 2 - 0.05)
        assert (probe & shroud).volume < 1e-6, a


def test_the_deck_is_lobed_to_the_coat(parts):
    deck = parts["deck"]
    for deg, r in ((0.0, P.DECK_R), (P.DECK_LOBE["angle"], P.DECK_LOBE["r"]), (180.0, P.DECK_BACK_R)):
        x, y = polar(r - 1.0, deg)
        assert (cyl_z(0.5, P.Z_DECK - 1, P.Z_DECK + 1, x, y) & deck).volume > 1e-3, (deg, "inside")
        x, y = polar(r + 1.0, deg)
        assert (cyl_z(0.5, P.Z_DECK - 1, P.Z_DECK + 1, x, y) & deck).volume < 1e-6, (deg, "outside")


def test_the_nozzle_arm_swings_its_whole_range_untouched(parts):
    from mech.turntable import _tilt_servo
    axis = Axis((P.NOZZLE_PIVOT[0], 0, P.NOZZLE_PIVOT[2]), (0, 1, 0))
    fixed = parts["tilt_bracket"] + parts["neck_shroud"] + parts["plate"] + parts["deck"] \
        + parts["shaft"] + _tilt_servo()
    for deg in range(int(P.TILT_STOP[0]), int(P.TILT_STOP[1]) + 1):
        # build123d's +deg about +Y lowers the nose, so the machine's tilt is -deg here
        assert (parts["nozzle_arm"].rotate(axis, -deg) & fixed).volume < 1e-6, deg


def test_the_jet_leaves_the_nozzle_untouched(parts):
    """A JET_D column from the tip, along the arm, at every degree of the arm's travel."""
    from mech.turntable import _tilt_servo, nozzle_tip
    fixed = parts["tilt_bracket"] + parts["neck_shroud"] + parts["plate"] + parts["deck"] \
        + parts["deck_ring"] + parts["shaft"] + _tilt_servo()
    axis = Axis((P.NOZZLE_PIVOT[0], 0, P.NOZZLE_PIVOT[2]), (0, 1, 0))
    jet = cyl_x(P.JET_D / 2, P.NOZZLE_PIVOT[0] + P.NOZZLE_ARM_L, P.NOZZLE_PIVOT[0] + 140.0,
                0, P.NOZZLE_PIVOT[2])
    for deg in range(int(P.TILT_STOP[0]), int(P.TILT_STOP[1]) + 1):
        shot = jet.rotate(axis, -deg)                           # the arm turns with its own jet
        assert (shot & (fixed + parts["nozzle_arm"].rotate(axis, -deg))).volume < 1e-6, deg
        (tx, tz), _ = nozzle_tip(deg)
        assert math.hypot(tx, 0.0) > P.SHROUD_R_OUT, deg        # the tip is always outside the shroud


def test_the_tube_reaches_the_barb_at_both_stops(parts):
    """The barb swings; a 6 x 4 tube leaves the shaft's mouth and reaches it at either end."""
    from mech.turntable import _tail_reach
    mouth = (0.0, P.Z_PLATE_TOP + 6.0)                          # the shaft's flared top
    reach = []
    for deg in P.TILT_STOP:
        bx, bz = _tail_reach(deg)
        run = math.hypot(bx - mouth[0], bz - mouth[1])
        reach.append(run)
        assert run > P.TUBE_BEND_R, (deg, run)                  # one bend of TUBE_BEND_R fits in it
    assert abs(reach[0] - reach[1]) < 2 * P.TUBE_BEND_R          # ... and the swing is inside one bend


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


def _clip(y, z, h=30.0):
    """The clip-on lens: LENS_CLIP_T proud of the back glass, LENS_CLIP_W across, h tall."""
    return box(P.PHONE_BACK_X, P.LENS_FRONT_X, y - P.LENS_CLIP_W / 2, y + P.LENS_CLIP_W / 2,
               z - h / 2, z + h / 2)


def test_phone_sled_only_fits_camera_down(parts):
    """Camera down the clip runs up the sled's channel; flipped it lands on the key finger."""
    from mech.common import phone_body
    from mech.torso import phone_sled
    sled = parts["phone_sled"]
    assert (sled & (phone_body() + _clip(P.CAM_Y, P.Z_LENS))).volume < 1e-6        # the right way round
    # flipped end for end the camera goes to the top and mirrors to -CAM_Y
    z_flipped = P.PHONE_BOTTOM_Z + P.PHONE_L - P.PHONE_CAM_FROM_END
    flipped = phone_body() + _clip(-P.CAM_Y, z_flipped)
    assert (sled & flipped).volume > 1e-3                                          # ... and it will not seat
    # and it is the key finger that stops it: delete the finger and the flipped phone drops in
    from mech.torso import SLED_KEY_OVERRUN, SLED_LIP_TOP
    key = box(P.PHONE_BACK_X + P.CLEAR - 0.01, P.PHONE_BACK_X + P.SLED_WALL + 1,
              -P.CAM_Y - 6.01, -P.CAM_Y + 6.01, P.PHONE_BOTTOM_Z + SLED_LIP_TOP - 20.01,
              P.PHONE_BOTTOM_Z + P.PHONE_L - P.PHONE_CAM_FROM_END + SLED_KEY_OVERRUN + 0.01)
    assert ((sled - key) & flipped).volume < 1e-6


def test_nothing_stands_in_the_phones_volume(parts):
    """Every dry-zone part keeps out of the phone: the sled's pocket surrounds it, nothing touches it."""
    from mech.common import phone_body
    phone = phone_body()
    for name in ("belt_flange_lower", "belt_flange_upper", "divider", "chassis", "phone_sled",
                 "electronics_deck", "fan_frame", "hatch_lip", "hatch_bosses"):
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
    assert math.isclose(bb.max.Z, P.Z_BASE_TOP + P.DIVIDER_PROUD, abs_tol=1e-6)   # proud of the rim
    assert bb.max.X <= P.shell_r(P.BASE_PROFILE, P.Z_BELT) - P.WALL - P.CLEAR + 1e-6


def test_the_boards_fit_the_deck_as_laid_out():
    """Every rectangle is on the deck, none overlaps another, and none covers a screw or driver."""
    from mech.torso import _edeck, _rect
    ex, ey = P.EDECK_POS
    for name in P.EDECK_LAYOUT:
        x0, y0, x1, y1 = _rect(P.EDECK_LAYOUT[name])
        assert ex - P.EDECK_L / 2 <= x0 < x1 <= ex + P.EDECK_L / 2, name
        assert ey - P.EDECK_W / 2 <= y0 < y1 <= ey + P.EDECK_W / 2, name
    for a, b in itertools.combinations(P.EDECK_LAYOUT, 2):
        ax0, ay0, ax1, ay1 = _rect(P.EDECK_LAYOUT[a])
        bx0, by0, bx1, by1 = _rect(P.EDECK_LAYOUT[b])
        assert ax1 <= bx0 or bx1 <= ax0 or ay1 <= by0 or by1 <= ay0, (a, b)
    for x, y in _edeck(P.EDECK_HOLES):                       # head and driver, r 3
        for name in P.EDECK_LAYOUT:
            x0, y0, x1, y1 = _rect(P.EDECK_LAYOUT[name])
            assert not (x0 - 3 < x < x1 + 3 and y0 - 3 < y < y1 + 3), (name, x, y)
    area = sum((r[2] - r[0]) * (r[3] - r[1]) for r in P.EDECK_LAYOUT.values())
    assert area <= P.EDECK_L * P.EDECK_W


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


def test_assembly_step_exists_after_build(tmp_path):
    from build123d import export_step
    from mech.common import assembly
    import mech.turntable, mech.torso, mech.head, mech.base  # noqa: E401,F401
    from mech import ALL
    comp = assembly({spec.name: spec.build() for spec in ALL})
    expect = sum(len(p.solids()) for p in built.values()) + len(built["stop_pin"].solids())
    assert len(comp.solids()) == expect            # every part's solids, and the pin fitted twice
    labels = [c.label for c in comp.children]
    assert all(labels) and len(labels) == len(ALL) + 1           # the stop pin is fitted twice
    assert labels.count("stop_pin") == 1 and "stop_pin_mirrored" in labels
    # the two parts that declare a placement are drawn at the origin and land where it says
    from mech.base import CAP_L, STUB_OUT, TANK_HEAD_L
    at = {c.label: c.bounding_box() for c in comp.children}
    raw = {spec.name: spec.build().bounding_box() for spec in ALL if spec.placement != Location()}
    neck_x = P.CANISTER_XY[0] - P.CANISTER[0] / 2
    assert math.isclose(raw["tank_head"].min.Z, 0.0, abs_tol=1e-6)            # drawn upright, bore along Z
    assert math.isclose(at["tank_head"].max.X, neck_x, abs_tol=1e-6)          # fitted on the neck
    assert math.isclose(at["tank_head"].min.X, neck_x - TANK_HEAD_L, abs_tol=1e-6)
    assert math.isclose(at["tank_head"].max.Z, P.CANISTER_Z0 + P.CANISTER[2] / 2 + STUB_OUT, abs_tol=1e-6)
    skin = P.shell_r(P.BASE_PROFILE, P.Z_FILLER)
    assert math.isclose(raw["filler_cap"].min.Z, 0.0, abs_tol=1e-6)           # ... and so is the cap
    assert math.isclose(at["filler_cap"].max.X, -skin, abs_tol=1e-6)          # mouth on the skin
    assert math.isclose(at["filler_cap"].min.X, -skin - CAP_L, abs_tol=1e-6)  # ... closed end outboard
    assert math.isclose((at["filler_cap"].min.Z + at["filler_cap"].max.Z) / 2, P.Z_FILLER, abs_tol=1e-6)
    step = tmp_path / "mechanism_assembly.step"                  # the build writes exactly this
    assert export_step(comp, str(step))
    assert step.stat().st_size > 0
    from build123d import import_step
    back = import_step(str(step))                                # the labels survive the round trip
    assert {c.label for c in back.children} == set(labels)


def test_no_two_parts_in_a_group_overlap(placed):
    """Three groups - what is fixed, what turns with the plate, what nods with the head - each
    checked against itself. The linkage is left out: it sweeps, and its own test covers it.

    Interface parts of one shell section are let off each other: they are unioned into the same
    revolve, so an overlap between two of them would close up rather than clash. None of them
    overlaps today - the exemption is there for the shell, not to excuse a mistake.

    One interference is the design's: the divider stands DIVIDER_PROUD above the base's rim so
    the belt screws always squeeze the bead. It is asserted for what it is, and for no more.
    """
    from mech import INTERFACES
    section = {n: s for s, names in INTERFACES.items() for n in names}
    pan = {"plate", "shaft", "neck_shroud", "tilt_bracket", "servo_crank", "pan_link"}
    head = {"nozzle_arm"}
    linkage = {"servo_crank", "pan_link", "stop_pin", "nozzle_arm"}
    groups = [[n for n in placed if n not in pan | head | linkage], sorted(pan), sorted(head)]
    for group in groups:
        for a, b in itertools.combinations(group, 2):
            if a in section and b in section and section[a] == section[b]:
                continue
            crush = (placed[a] & placed[b])
            if {a, b} == {"divider", "belt_flange_upper"}:
                bb = crush.bounding_box()
                assert math.isclose(bb.min.Z, P.Z_BASE_TOP, abs_tol=1e-6)
                assert math.isclose(bb.max.Z, P.Z_BASE_TOP + P.DIVIDER_PROUD, abs_tol=1e-6)
                continue
            assert crush.volume < 1e-3, (a, b, crush.volume)


def test_the_sled_slides_out_through_the_hatch(parts):
    """With the panel off, the sled and the phone in it come straight out along +X."""
    from mech.common import phone_body
    from mech.torso import _wedge
    unit = parts["phone_sled"] + phone_body()
    outside = skin_solid(P.TORSO_PROFILE, P.WALL) - _wedge(P.HATCH_HALF_ANGLE, *P.HATCH_Z)
    fixed = [parts[n] for n in ("chassis", "electronics_deck", "belt_flange_upper", "deck_ring",
                                "deck", "fan_frame", "hatch_bosses", "hatch_lip")] + [outside]
    clear_of = P.shell_r(P.TORSO_PROFILE, P.Z_LENS) + 5.0
    d = 0.0
    while True:
        moved = unit.moved(Location((d, 0, 0)))
        for other in fixed:
            assert (moved & other).volume < 1e-3, d
        if P.PHONE_FRONT_X - P.SLED_WALL + d > clear_of:
            break
        d += 5.0


def test_belt_screw_length(parts):
    """An M3 x 20 driven from the counterbore's floor: full engagement, and it does not bottom."""
    lower, upper = parts["belt_flange_lower"], parts["belt_flange_upper"]
    floor = P.Z_BASE_TOP + P.RING_T - (P.SCREW_HEAD_H + 0.5)
    x, y = polar(P.FLANGE_SCREW_R, P.FLANGE_SCREW_ANGLES[0])
    head = cyl_z(3.2 - 0.05, floor, P.Z_BASE_TOP + P.RING_T, x, y)
    assert (head & upper).volume < 1e-6                          # the head sinks below the ring's top
    probe = cyl_z(P.INSERT_D / 2 - 0.05, P.Z_BELT - 2 * P.RING_T, P.Z_BELT, x, y)
    bore_floor = (probe & lower).bounding_box().max.Z            # where the insert bore stops
    tip = floor - 20.0
    assert min(P.INSERT_DEPTH, P.Z_BELT - tip) >= P.INSERT_DEPTH - 1e-6   # six millimetres of insert
    assert tip - bore_floor >= 1.0, (tip, bore_floor)                     # ... and daylight below it


def test_chassis_and_deck_screws_have_driver_paths(parts):
    """A stubby driver on every dry-zone screw head, 30 mm of it, reaches nothing else."""
    from mech.common import phone_body
    from mech.torso import _edeck
    obstacles = dict(parts)
    obstacles["phone"] = phone_body()
    z_chassis = P.Z_CHASSIS + P.CHASSIS_T
    heads = [(polar(P.CHASSIS_SCREW_R, a), z_chassis) for a in P.CHASSIS_SCREW_ANGLES]
    z_deck = z_chassis + P.EDECK_STANDOFF + P.EDECK_T
    heads += [((x, y), z_deck) for x, y in _edeck(P.EDECK_HOLES)]
    for (x, y), z in heads:
        driver = cyl_z(3.0, z, z + 30.0, x, y)
        for name, other in obstacles.items():
            assert (driver & other).volume < 1e-3, (x, y, name)


def test_hatch_bosses_take_a_blind_insert_and_stay_in_the_wall(parts):
    """One bracket per screw, each with a blind insert facing the panel and material behind it."""
    bosses = parts["hatch_bosses"]
    assert len(bosses.solids()) == len(P.HATCH_SCREWS)
    for z, a in P.HATCH_SCREWS:
        r_in = P.shell_r(P.TORSO_PROFILE, z) - P.WALL
        bore = cyl_x(P.INSERT_D / 2 - 0.05, r_in - P.INSERT_DEPTH + 0.1, r_in - 0.1, 0, z).rotate(Axis.Z, a)
        assert (bore & bosses).volume < 1e-6, (z, a)                      # the insert's hole is clear
        behind = cyl_x(P.INSERT_D / 2 - 0.05, r_in - P.INSERT_DEPTH - 0.9,
                       r_in - P.INSERT_DEPTH - 0.1, 0, z).rotate(Axis.Z, a)
        assert (behind & bosses).volume > 1e-3, (z, a)                    # ... and it is blind
    assert (bosses - skin_solid(P.TORSO_PROFILE, P.WALL - 1.2)).volume < 1e-6   # never proud


def test_hatch_lip_frames_the_opening_and_leaves_its_top_clear(parts):
    """A ledge round the bottom and both sides; the top edge is a shingle, not a lip."""
    lip = parts["hatch_lip"]
    bb = lip.bounding_box()
    assert math.isclose(bb.min.Z, P.HATCH_Z[0], abs_tol=1e-6)
    assert math.isclose(bb.max.Z, P.HATCH_Z[1], abs_tol=1e-6)
    top = lip & box(-120, 120, -120, 120, P.HATCH_Z[1] - P.HATCH_LIP_W, P.HATCH_Z[1])
    assert top.volume > 1e-3                                              # the sides run to the top
    middle = top & box(-120, 120, -30, 30, P.HATCH_Z[1] - P.HATCH_LIP_W, P.HATCH_Z[1])
    assert middle.volume < 1e-6                                           # nothing crosses the middle
    assert (lip - skin_solid(P.TORSO_PROFILE, P.WALL - 1.2)).volume < 1e-6
