import itertools
import math
import pytest
from build123d import Axis, Location, Plane, Pos, Sphere, Vertex
import params as P
from mech.common import box, cyl_x, cyl_z, cyl_y, polar, posed, servo_body, skin_solid


def _bb(p):
    return p.bounding_box().size


def _driver(head, direction, r=3.0, length=40.0):
    """A driver of radius `r`, `length` long, on a screw head at `head` pointing `direction`."""
    mid = tuple(h + d * length / 2 for h, d in zip(head, direction))
    return Plane(origin=mid, z_dir=direction) * Pos(0, 0, -length / 2) * cyl_z(r, 0, length)


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


def test_the_fan_hole_clears_the_bearing_and_the_deck_rim(parts):
    """The 30 mm fan's hole clears the 6810's outer ring by 2 mm and more, and the deck is still
    there behind it: the rim the collar's shadow leaves at the back."""
    fx, fy = P.FAN_XY
    edge = math.hypot(fx, fy) - P.FAN_HOLE_D / 2 - P.BEARING_OD / 2
    assert edge >= 2.0, edge                                     # 3.5 as drawn
    deck = parts["deck"]
    behind = math.hypot(fx, fy) + P.FAN_HOLE_D / 2 + 1.0         # a millimetre past the hole's far edge
    x, y = polar(behind, math.degrees(math.atan2(fy, fx)))
    assert (cyl_z(0.4, P.Z_DECK - P.DECK_T + 1, P.Z_DECK - 1, x, y) & deck).volume > 1e-3
    for a in P.CAP_SCREW_ANGLES:                                 # the cap's inserts are still drilled
        bx, by = polar(P.CAP_SCREW_R, a)
        probe = cyl_z(P.INSERT_D / 2 - 0.05, P.Z_DECK - P.INSERT_DEPTH_SHORT + 0.1, P.Z_DECK + 1, bx, by)
        assert (probe & deck).volume < 1e-6, a


def test_the_deck_cage_stands_inside_the_bells_bore(parts):
    """It is the deck's only support now, and every millimetre of it is inside the turning bore.

    The bore is not the cavity: the bell turns +-65 degrees over everything above Z_TURN, so a
    fixed part is bound by the narrowest radius the cavity has anywhere over the bell's height -
    the back of the coat, which every azimuth comes round to. The statue measures that; it is
    68.8 mm at z 380, and this holds the cage a millimetre inside it.
    """
    from test_params import statue_reach
    cage = parts["deck_ring"]
    bb = cage.bounding_box()
    assert math.isclose(bb.min.Z, P.Z_CHASSIS + P.CHASSIS_T, abs_tol=1e-6)     # feet on the chassis
    assert math.isclose(bb.max.Z, P.Z_DECK - P.DECK_T, abs_tol=1e-6)           # head under the deck
    bore = min(v[0] for z, v in statue_reach().items() if P.Z_TURN <= z <= bb.max.Z)
    reach = max(math.hypot(v.X, v.Y) for v in cage.vertices())
    assert reach <= bore - 1.0, (reach, bore)                                  # inside the turning bore
    fx, fy = P.FAN_XY                                                          # the fan hangs clear
    assert (cage & box(fx - P.FAN / 2, fx + P.FAN / 2, fy - P.FAN / 2, fy + P.FAN / 2,
                       P.Z_DECK - P.DECK_T - P.FAN_T, P.Z_DECK - P.DECK_T)).volume < 1e-6
    for a in P.DECK_SCREW_ANGLES:
        x, y = polar(P.CAGE_LEG_R, a)
        foot = cyl_z(P.INSERT_D / 2 - 0.05, bb.min.Z - 1, bb.min.Z + P.INSERT_DEPTH - 0.2, x, y)
        assert (foot & cage).volume < 1e-6, a          # an insert up from every foot, for the chassis
        top = cyl_z(P.INSERT_D / 2 - 0.05, bb.max.Z - P.RING_T + 1.2, bb.max.Z + 1, x, y)
        assert (top & cage).volume < 1e-6, a           # ... and one down from every leg's top


BOARD_H = 25.0     # the tallest thing standing on the electronics deck, inductors and all


def board_stack(placed):
    """The electronics deck with a box on it for every board EDECK_LAYOUT names."""
    from mech.torso import _rect
    z0 = P.Z_CHASSIS + P.CHASSIS_T + P.EDECK_STANDOFF + P.EDECK_T
    stack = placed["electronics_deck"]
    for name in P.EDECK_LAYOUT:
        x0, y0, x1, y1 = _rect(P.EDECK_LAYOUT[name])
        stack = stack + box(x0, x1, y0, y1, z0, z0 + BOARD_H)
    return stack


def test_the_cage_goes_on_before_the_boards_and_they_drop_in(placed):
    """The order the machine is actually built in, swept: nothing has to be sprung past anything.

    The cage is bolted to the chassis and the pair goes in; then the electronics deck comes
    straight down onto its three standoffs, boards and all, and then the phone's sled onto its
    two locks. Both drops are checked every 2 mm over the 60 mm above home against everything
    that is already in the statue, and the second of them is the service lift as well: the sled
    comes back out with the boards still bolted down, which is what the slots in the deck's
    front edge are for.

    This is what the two annuli made impossible. A ring of bore 50 under the deck and another
    at z 304 stood in the way of a 100 x 92 board deck and a sled that reaches r 81.6, and no
    ring wide enough for either fits inside the r 69 the turning bell leaves.
    """
    from mech.common import phone_body
    fixed = {n: placed[n] for n in ("deck_ring", "chassis", "divider", "filler_neck",
                                    "filler_cap", "belt_flange_upper", "belt_flange_lower")}
    boards = board_stack(placed)
    sled = placed["phone_sled"] + phone_body()
    for what, moving, extra in (("the boards", boards, {}),
                                ("the sled", sled, {"the boards": boards})):
        obstacles = dict(fixed, **extra)
        for dz in range(60, -1, -2):
            up = moving.moved(Pos(0, 0, float(dz)))
            for name, other in obstacles.items():
                v = (up & other).volume
                assert v < 1e-6, (what, f"+{dz} mm", name, v)


def test_the_cages_feet_are_driven_before_the_chassis_goes_in(parts, placed):
    """The cage bolts up into its own feet from under the chassis, so the two go on the bench.

    Nothing of the machine stands in those four screws' way - the boards are not on yet and the
    cage's legs are above them - but once the chassis is in the statue the divider is 7.7 mm
    under it, and no driver fits that. Hence the order: cage onto the chassis on the bench, the
    pair lowered in, and the chassis's own four screws driven from above afterwards.
    """
    from mech.torso import cage_feet
    z = P.Z_CHASSIS
    for x, y in cage_feet():
        driver = cyl_z(3.0, z - 30.0, z - 0.01, x, y)
        for name in ("chassis", "deck_ring"):
            assert (driver & placed[name]).volume < 1e-3, (x, y, name)
    x, y = cage_feet()[0]                               # ... and this is what says "on the bench"
    assert (cyl_z(3.0, z - 30.0, z - 0.01, x, y) & placed["divider"]).volume > 1e-3


def test_deck_ring_is_cut_around_the_pan_servo(parts):
    body = servo_body(P.DS3218, (P.PAN_SERVO_XY[0], P.PAN_SERVO_XY[1], P.Z_PAN_SHAFT_FACE), axis="-z")
    assert (body & parts["deck_ring"]).volume < 1e-6


def _bearing():
    return (cyl_z(P.BEARING_OD / 2, P.Z_BEARING, P.Z_BEARING + P.BEARING_B)
            - cyl_z(P.BEARING_ID / 2, P.Z_BEARING - 1, P.Z_BEARING + P.BEARING_B + 1))


def test_the_bearing_is_seated_and_held_both_ways(parts):
    """The 6810's outer ring in the deck, its inner ring on the plate's hub, each with 0.1-0.2 mm
    of radial fit, and each held both ways: the outer ring between the deck's lip and the cap, the
    inner ring between the plate's shoulder and the hub ring. Every clamping face touches only its
    own ring - a lip that reached the seal or the other ring would stop it turning."""
    deck, cap, plate, ring = parts["deck"], parts["bearing_cap"], parts["plate"], parts["hub_ring"]
    b = _bearing()
    z0, z1 = P.Z_BEARING, P.Z_BEARING + P.BEARING_B
    assert 0.1 <= P.BEARING_FIT <= 0.2
    for name, p in (("deck", deck), ("cap", cap), ("plate", plate), ("hub_ring", ring)):
        assert (p & b).volume < 1e-6, name                               # nothing is in the bearing
    # the seats are the bearing's own diameters plus the fit, and no more
    assert (cyl_z(P.BEARING_OD / 2 + P.BEARING_FIT - 0.02, z0 + 0.5, P.Z_DECK - 0.5) & deck).volume < 1e-6
    assert (cyl_z(P.BEARING_OD / 2 + P.BEARING_FIT + 0.05, z0 + 0.5, P.Z_DECK - 0.5) & deck).volume > 1e-3
    hub = plate & cyl_z(P.BEARING_ID / 2, z0 + 0.5, z1 - 0.5)
    r = max(math.hypot(v.X, v.Y) for v in hub.vertices())
    assert math.isclose(r, P.BEARING_ID / 2 - P.BEARING_FIT, abs_tol=0.01), r
    # each face that holds a ring touches it, and only in that ring's own band
    out_band = (cyl_z(P.BEARING_OD / 2 - 0.1, 0, 1) - cyl_z(P.BEARING_OUT_LAND_R, -1, 2))
    in_band = (cyl_z(P.BEARING_IN_LAND_R, 0, 1) - cyl_z(P.BEARING_ID / 2 + 0.1, -1, 2))
    for what, p, z, band in (("deck's lip", deck, z0 - 0.5, out_band), ("cap", cap, z1 + 0.5, out_band),
                             ("plate's shoulder", plate, z1 + 0.5, in_band), ("hub ring", ring, z0 - 0.5, in_band)):
        face = band.moved(Pos(0, 0, z - 0.5))
        assert (face & p).volume > 0.3 * face.volume, what               # it bears on its ring ...
        seal = (cyl_z(P.BEARING_OUT_LAND_R - 0.05, z - 0.4, z + 0.4)
                - cyl_z(P.BEARING_IN_LAND_R + 0.05, z - 1, z + 1))
        assert (seal & p).volume < 1e-6, what                            # ... and not on the seal


def test_the_stem_channel_takes_the_tube(parts):
    """The tube runs down the stem's channel from its head to where it leaves the neck's back,
    with half a millimetre all round, and the channel does not break out of the stem's sides."""
    from mech.nod import tube_stem_points
    from mech.common import polyline
    stem = parts["stem"]
    pts = tube_stem_points()
    inside = polyline(pts[1:4], P.TUBE_OD / 2)
    assert (inside & stem).volume < 1e-6                                  # the tube passes
    assert P.STEM_CHANNEL_D >= P.TUBE_OD + 1.0
    walls = box(-30, 30, -P.STEM_T / 2, P.STEM_T / 2, 395.0, P.STEM_HEAD[2] - 1.0)
    ring = polyline(pts[1:3], P.STEM_CHANNEL_D / 2 + 1.2) - polyline(pts[1:3], P.STEM_CHANNEL_D / 2 + 0.01)
    assert (ring & stem).volume > 0.97 * (ring & walls).volume           # 1.2 mm of wall all the way


def test_plate_sits_on_the_bearing_and_hangs_its_column(parts):
    plate = parts["plate"]
    bb = plate.bounding_box()
    assert math.isclose(bb.max.Z, P.Z_PLATE_TOP, abs_tol=1e-6)          # nothing above the disc
    below = plate & box(20, 80, -80, 80, P.Z_CRANK_BOTTOM - 1, P.Z_HUB_BOTTOM - 0.01)
    b = below.bounding_box()
    assert b.min.X >= P.PAN_FOOT_R_IN - 1e-6 and b.max.X <= P.PAN_COLUMN[1] + 1e-6   # only column and foot out here
    assert abs(b.min.Y) <= P.PAN_COLUMN[2] / 2 + 1e-6 and abs(b.max.Y) <= P.PAN_COLUMN[2] / 2 + 1e-6
    pin, _ = P.crank_pins(0)                                              # the foot's pin insert is blind
    probe = cyl_z(P.INSERT_D / 2, P.Z_CRANK_BOTTOM - 1, P.Z_CRANK_TOP, pin[0], pin[1])
    assert (probe & plate).volume > 1e-3


def test_the_yoke_drops_through_the_bearing(parts):
    """Everything of the plate under the bearing's bore, but the column, is inside it: the plate
    and its yoke go down through the inner ring, and the hub ring slides up over them."""
    plate = parts["plate"]
    under = plate & cyl_z(60, P.Z_CRANK_BOTTOM - 10, P.Z_BEARING)
    under = under - box(P.PAN_FOOT_R_IN - 1, 80, -10, 10, P.Z_CRANK_BOTTOM - 10, P.Z_BEARING)
    r = max(math.hypot(v.X, v.Y) for v in under.vertices())
    assert r <= P.HUB_R + 1e-6, r                                         # 24.85: the hub itself
    lower = plate & cyl_z(60, P.Z_CRANK_BOTTOM - 10, P.Z_HUB_BOTTOM - 0.01)
    lower = lower - box(P.PAN_FOOT_R_IN - 1, 80, -10, 10, P.Z_CRANK_BOTTOM - 10, P.Z_BEARING)
    r = max(math.hypot(v.X, v.Y) for v in lower.vertices())
    assert r < P.HUB_R + 0.15 - 1.0, r                                    # the ring's bore passes it by a millimetre


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
    """The plate with its yoke and the nod servo on it about the pan axis, the servo crank about
    the servo's axis, the link translated: nothing touches through the whole pan, the stops
    included, but the link's eyes under their two pin bosses, which is what the bosses are for."""
    from mech.nod import nod_servo
    servo_axis = Axis((P.PAN_SERVO_XY[0], P.PAN_SERVO_XY[1], 0), (0, 0, 1))
    rest_plate, _ = P.crank_pins(0)
    servo = servo_body(P.DS3218, (P.PAN_SERVO_XY[0], P.PAN_SERVO_XY[1], P.Z_PAN_SHAFT_FACE), axis="-z")
    fixed = parts["deck"] + parts["deck_ring"] + parts["bearing_cap"] + servo
    turning = parts["plate"] + parts["hub_ring"] + nod_servo()
    interior = range(-int(P.PAN_STOP_DEG) + 1, int(P.PAN_STOP_DEG), 8)
    for deg in [-P.PAN_STOP_DEG, *interior, P.PAN_STOP_DEG]:      # the stops themselves as well
        plate = turning.rotate(Axis.Z, deg)
        crank = parts["servo_crank"].rotate(servo_axis, deg)
        pin, _ = P.crank_pins(deg)
        link = parts["pan_link"].moved(Location((pin[0] - rest_plate[0], pin[1] - rest_plate[1], 0)))
        for a, b, what in ((plate, crank, "plate/crank"), (plate, fixed, "plate/fixed"), (crank, fixed, "crank/fixed"),
                           (link, plate, "link/plate"), (link, crank, "link/crank"), (link, fixed, "link/fixed")):
            v = (a & b).volume
            assert v < 1e-3, (deg, what, v)
        # and the link's plane stays 2 mm under the yoke: the study's cheek met it by 0.5 at -65
        body = plate - box(P.PAN_FOOT_R_IN - 6, 80, -10, 10, P.Z_LINK_BOTTOM - 5, P.Z_CRANK_TOP + 0.01).rotate(Axis.Z, deg)
        assert link.distance_to(body) >= 2.0, (deg, link.distance_to(body))


def test_pan_servo_hangs_from_the_deck_and_touches_nothing_else(parts):
    body = servo_body(P.DS3218, (P.PAN_SERVO_XY[0], P.PAN_SERVO_XY[1], P.Z_PAN_SHAFT_FACE), axis="-z")
    for other in (_bearing(), parts["deck"], parts["deck_ring"], parts["plate"], parts["hub_ring"],
                  parts["stem"]):
        assert (body & other).volume < 1e-6
    # the hangers meet the tabs: a hanger's bottom face is at the tabs' upper face
    hangers = parts["deck"] & box(-120, 120, -120, 120, P.Z_PAN_SHAFT_FACE - 5, P.Z_DECK - P.DECK_T - 0.01)
    assert math.isclose(hangers.bounding_box().min.Z, P.Z_PAN_SHAFT_FACE + (P.DS3218["body"][2] - P.DS3218["tab_z"]) + P.DS3218["tab_t"], abs_tol=1e-6)


def test_stop_pins_seat_in_the_deck(parts):
    """Each pin drops into its own seat, and the seat is a glue fit rather than a press one."""
    pin = parts["stop_pin"]
    assert math.isclose(pin.bounding_box().max.Z, P.STOP_PIN_TOP, abs_tol=1e-6)
    for p in (pin, pin.rotate(Axis.Z, -2 * P.stop_pin_deg())):
        assert (p & parts["deck"]).volume == 0                           # each sits in its own hole
    # a printed pin comes out over size; the seat takes one 0.3 mm fat without being driven in
    assert P.STOP_PIN_SEAT_D - P.STOP_POST_D >= 0.4, P.STOP_PIN_SEAT_D
    x, y = polar(P.STOP_POST_R, P.stop_pin_deg())
    fat = cyl_z((P.STOP_POST_D + 0.3) / 2, P.Z_DECK - P.STOP_PIN_DEPTH, P.Z_DECK, x, y)
    assert (fat & parts["deck"]).volume < 1e-6


def test_the_spider_fits_the_head_and_takes_its_screws(parts):
    """Four radial inserts at z 440, bored round, their faces at r 57 where the shroud's were;
    the stem's head fits up into the spider; its two screws and the tube's bore go through.

    The bosses stand inside the head's cavity, read from the statue's reach table at that height,
    so this skips without a statue rather than passing against a number typed in here.
    """
    from test_params import reach_at
    from mech.nod import SPIDER_SCREW_X
    sp, st = parts["spider"], parts["stem"]
    assert P.SPIDER_BOSS_R + 3.0 <= reach_at(P.HEAD_SCREWS_Z)[0]
    r0, r1 = P.SPIDER_BOSS_R - P.INSERT_DEPTH, P.SPIDER_BOSS_R
    for a in P.HEAD_SCREW_ANGLES:
        bore = cyl_x(P.INSERT_D / 2 - 0.05, r0 + 0.2, r1 + 1, 0.0, P.HEAD_SCREWS_Z).rotate(Axis.Z, a)
        assert (bore & sp).volume < 1e-6, (a, "the insert's bore is not clear")
        wall = (cyl_x(P.INSERT_D / 2 + 1.5, r0 + 0.2, r1 - 0.2, 0.0, P.HEAD_SCREWS_Z)
                - cyl_x(P.INSERT_D / 2 + 0.05, r0, r1, 0.0, P.HEAD_SCREWS_Z)).rotate(Axis.Z, a)
        assert (wall & sp).volume > 0.9 * wall.volume, (a, "the boss is not round the insert")
        on_axis = cyl_x(0.3, 0.0, 100.0, 0.0, P.HEAD_SCREWS_Z + P.INSERT_D / 2 + 1.0).rotate(Axis.Z, a)
        face = max(math.hypot(v.X, v.Y) for v in (sp & on_axis).vertices())
        assert math.isclose(face, P.SPIDER_BOSS_R, abs_tol=0.05), face
    assert (sp & st).volume < 1e-6                                         # the stem's head fits in it
    for x in (-SPIDER_SCREW_X, SPIDER_SCREW_X):
        shank = cyl_z(P.M3_CLEAR / 2 - 0.05, P.STEM_HEAD[2], P.SPIDER_Z[1] + 1, x, 0.0)
        assert (shank & sp).volume < 1e-6, x
        insert = cyl_z(P.INSERT_D / 2 - 0.05, P.STEM_HEAD[2] - P.INSERT_DEPTH + 0.1, P.STEM_HEAD[2], x, 0.0)
        assert (insert & st).volume < 1e-6, x
    assert (cyl_z(P.TUBE_OD / 2 + 0.3, P.SPIDER_Z[0] - 1, P.SPIDER_Z[1] + 1) & sp).volume < 1e-6


def test_the_deck_stays_in_the_socket(parts):
    """The deck, hangers and all, is DECK_SOCKET_MARGIN inside the collar's socket, and inside the
    narrowest the collar is anywhere under it less DECK_SHADOW_MARGIN, which is what lets the
    collar be lowered over it. The narrowest is at the back, 71 mm out."""
    from mech.turntable import collar_shadow
    deck = parts["deck"]
    inner = P.NECK_SPHERE_R - P.TURN_GAP - P.WALL
    far = max(math.dist((v.X, v.Y, v.Z), (0, 0, P.Z_NOD)) for v in deck.vertices())
    assert far <= inner - P.DECK_SOCKET_MARGIN + 1e-3, far
    sh = collar_shadow()
    if sh is None:
        pytest.skip("the statue stage has not published collar_inner")
    angles, radii = sh
    step = angles[1] - angles[0]
    worst = 1e9
    for v in deck.vertices():
        a = (math.degrees(math.atan2(v.Y, v.X)) % 360.0) / step
        i, f = int(a) % len(radii), a - int(a)
        r = radii[i] + (radii[(i + 1) % len(radii)] - radii[i]) * f      # the shadow, between samples
        worst = min(worst, r - math.hypot(v.X, v.Y))
    assert worst >= P.DECK_SHADOW_MARGIN - 0.1, worst


def test_the_spider_keeps_off_the_dome(parts):
    """Beyond SPIDER_CORE_R the spider is NECK_SPHERE_R from C, like the unit it carries; inside
    it, it stays in the dome's bore at every nod. Both measured on the part's vertices."""
    from mech.common import pose_point
    sp = parts["spider"]
    worst_far, worst_bore = 1e9, 0.0
    for v in sp.vertices():
        p = (v.X, v.Y, v.Z)
        r = math.hypot(v.X, v.Y)
        d = math.dist(p, (0, 0, P.Z_NOD))
        if r > P.SPIDER_CORE_R + 1e-6:
            worst_far = min(worst_far, d)
        else:
            for nod in (P.NOD_STOP[0], P.NOD_STOP[1]):
                q = pose_point(p, 0.0, nod)
                worst_bore = max(worst_bore, math.hypot(q[0], q[1]))
    assert worst_far >= P.NECK_SPHERE_R, worst_far
    assert worst_bore <= P.NECK_BORE_R - 3.0, worst_bore


def test_the_stem_swings_clear_of_the_yoke(parts):
    """At every degree of the nod range the stem is NOD_CLEAR clear of the plate and its yoke, and
    at the hard stops it still touches nothing but the stop."""
    from mech.nod import neck_x_range, stop_lug
    plate, stem = parts["plate"], parts["stem"]
    for deg in range(int(P.NOD_STOP[0]), int(P.NOD_STOP[1]) + 1):
        assert (posed(stem, 0, deg) & plate).volume < 1e-6, deg
        assert (posed(stem, 0, deg) & parts["hub_ring"]).volume < 1e-6, deg
    # the slot the plate leaves the neck is its sweep over the stops, NOD_CLEAR wider each side
    for z in (P.Z_HUB_BOTTOM + 1.0, P.Z_BEARING + 3.0, P.Z_PLATE_TOP - 0.5):
        lo, hi = neck_x_range(z, P.NOD_RANGE[0], P.NOD_RANGE[1])
        for x in (lo - P.NOD_CLEAR + 0.05, hi + P.NOD_CLEAR - 0.05):
            assert (cyl_z(0.02, z - 0.2, z + 0.2, x, 0.0) & plate).volume < 1e-9, (z, x)


def test_the_clear_hole_through_the_bearing(parts):
    """The stem sliced at z 394, 400 and 406 at every nod pose: the circle that holds all of it -
    the hole the neck needs - with 1.5 mm to spare inside the bearing's 50 mm bore and the deck's
    lip. As drawn it is 33.0, 35.0 and 37.0 across."""
    from build123d import Box
    stem = parts["stem"]
    holes = {}
    for z in (394.0, 400.0, 406.0):
        r = 0.0
        for deg in range(int(P.NOD_RANGE[0]), int(P.NOD_RANGE[1]) + 1):
            cut = posed(stem, 0, deg) & (Pos(0, 0, z) * Box(200, 200, 0.2))
            r = max(r, max(math.hypot(v.X, v.Y) for v in cut.vertices()))
        holes[z] = 2 * r
        assert 2 * r + 2 * 1.5 <= P.BEARING_ID, (z, 2 * r)
        assert 2 * r + 2 * 1.5 <= 2 * P.BEARING_OUT_LAND_R, (z, 2 * r)
    assert holes[406.0] <= 38.0, holes                                     # the study said about 37


def test_the_nod_stops_meet_the_lug_exactly(parts):
    """The spec's rule: a runaway command finds a printed stop, not the servo's own limit. The
    stop lug on the stem's hub runs in an arc slot in the -Y cheek whose ends are an asin of the
    lug's radius past NOD_STOP: clear a degree inside either stop, in contact a degree past it,
    and never anything in between."""
    from mech.nod import stop_lug
    lug, plate = stop_lug(), parts["plate"]
    for deg in (P.NOD_STOP[0] + 1, 0.0, P.NOD_STOP[1] - 1):
        assert (posed(lug, 0, deg) & plate).volume < 1e-6, deg
    for deg in (P.NOD_STOP[0] - 1, P.NOD_STOP[1] + 1):
        assert (posed(lug, 0, deg) & plate).volume > 1e-3, deg
    for deg in P.NOD_STOP:                                                 # and just touching, at the stop
        assert (posed(lug, 0, deg) & plate).volume < 1e-3, deg
        past = deg + math.copysign(0.25, deg)
        assert (posed(lug, 0, past) & plate).volume > 1e-6, past
    for deg in range(int(P.NOD_STOP[0]) + 1, int(P.NOD_STOP[1])):
        assert (posed(parts["stem"], 0, deg) & plate).volume < 1e-6, deg


def test_the_nod_servo_is_seated_and_drives_the_hub(parts):
    """The MG996R's tabs lie on the yoke's two posts, their four screw holes over inserts; its case
    touches nothing; its spline goes through the +Y cheek into the horn let into the stem's hub."""
    from mech.nod import horn, nod_servo, nod_servo_holes, nod_servo_tab_y
    plate, stem, servo = parts["plate"], parts["stem"], nod_servo()
    assert (servo & plate).volume < 1e-3                                   # it lies on the posts
    assert (servo & stem).volume < 1e-6
    yt = nod_servo_tab_y()
    for x, z in nod_servo_holes():
        insert = cyl_y(P.INSERT_D / 2 - 0.05, yt - P.INSERT_DEPTH + 0.1, yt - 0.01, x, z)
        assert (insert & plate).volume < 1e-6, (x, z)
        post = cyl_y(P.INSERT_D / 2 + 1.0, yt - 3, yt - 0.01, x, z) - cyl_y(P.INSERT_D / 2 + 0.05, yt - 4, yt, x, z)
        assert (post & plate).volume > 0.9 * post.volume, (x, z)
    assert (horn() & stem).volume < 1e-6 and (horn() & plate).volume < 1e-6
    for deg in P.NOD_STOP:
        assert (posed(stem, 0, deg) & servo).volume < 1e-6, deg
    body = servo.bounding_box()                                            # inside the cage's +Y legs
    assert math.hypot(body.max.X, body.max.Y) <= P.CAGE_LEG_R - P.CAGE_LEG / 2 - 6.0


def test_the_pin_is_held_in_the_hub_and_turns_in_the_bushing(parts):
    from mech.nod import bushing, pin
    stem, plate = parts["stem"], parts["plate"]
    assert (pin() & stem).volume > 0.0                                     # pressed in
    held = pin() & stem
    assert held.bounding_box().max.Y - held.bounding_box().min.Y >= 7.5     # 7.6 mm of it in the hub
    assert (bushing() & plate).volume > 0.0                                # the bushing, pressed
    assert (pin() & (plate - cyl_y(P.BUSH_OD / 2, -20, 0, 0.0, P.Z_NOD))).volume < 1e-6   # nothing else


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
                 "electronics_deck", "filler_neck"):
        assert (phone & parts[name]).volume < 1e-6, name


def test_belt_screws_line_up(parts):
    """One screw a corner, through the torso's ring and the divider into the base ring's insert.

    They are on the belt ring's mid-line ellipse now, not a bolt circle: between the joint's
    section and its bore, which is the only band that is material in all three layers.
    """
    from mech.torso import BELT_MID_RX, BELT_MID_RY, belt_screws
    lower, upper, divider = parts["belt_flange_lower"], parts["belt_flange_upper"], parts["divider"]
    for x, y in belt_screws():
        assert (x / P.BELT_IN_RX) ** 2 + (y / P.BELT_IN_RY) ** 2 > 1.0, (x, y)   # outside the bore
        assert (x / P.BELT_RX) ** 2 + (y / P.BELT_RY) ** 2 < 1.0, (x, y)         # ... inside the section
        probe = cyl_z(P.M3_CLEAR / 2 - 0.05, P.Z_BELT - 4, P.Z_BASE_TOP + P.RING_T + 1, x, y)
        assert (probe & upper).volume < 1e-6, (x, y)
        assert (probe & divider).volume < 1e-6, (x, y)
        insert = cyl_z(P.INSERT_D / 2 - 0.05, P.Z_BELT - P.INSERT_DEPTH + 0.1, P.Z_BELT - 0.1, x, y)
        assert (insert & lower).volume < 1e-6, (x, y)
    assert math.isclose(BELT_MID_RX, (P.BELT_RX + P.BELT_IN_RX) / 2, abs_tol=1e-9)
    assert math.isclose(BELT_MID_RY, (P.BELT_RY + P.BELT_IN_RY) / 2, abs_tol=1e-9)


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


def test_the_electronics_decks_standoffs_are_whole(parts):
    """Three standoffs and two posts on the chassis, and nothing eats any of them. The +Y standoff
    is back at y 34 square with the -Y one: it was at 27 while the filler cap's bore stood there,
    and at (46, 39) that bore took all but 1.6 mm3 of 326.7."""
    from mech.torso import STANDOFF_R, _edeck
    chassis = parts["chassis"]
    z0 = P.Z_CHASSIS + P.CHASSIS_T
    assert P.EDECK_HOLES[1][1] == -P.EDECK_HOLES[0][1]
    for kind, points in (("standoff", _edeck(P.EDECK_HOLES)), ("post", _edeck(P.EDECK_POSTS))):
        solid = []
        for x, y in points:
            column = cyl_z(STANDOFF_R, z0, z0 + P.EDECK_STANDOFF, x, y)
            solid.append((column & chassis).volume)
        assert min(solid) >= 0.95 * max(solid), (kind, solid)      # ... and none has been eaten


def test_the_lower_flanges_tongue_stands_outside_the_divider(parts):
    """The base's half rises past the split as a tongue for the torso's skirt to shingle over.

    Its bore above the split is the belt's own section, so the divider - a clearance inside that
    same ellipse - drops into it rather than onto it, and the assembler clips the tongue to the
    cavity less CLEAR_SHELL. Below the split the ring's bore is BELT_IN, which is what gives the
    screws their annulus.
    """
    flange, divider = parts["belt_flange_lower"], parts["divider"]
    assert math.isclose(flange.bounding_box().min.Z, P.Z_BELT - P.FLANGE_LOWER_H, abs_tol=1e-6)
    assert math.isclose(flange.bounding_box().max.Z, P.Z_BASE_TOP, abs_tol=1e-6)
    for z in (P.Z_BELT + 1.0, P.Z_BASE_TOP - 1.0):                          # the tongue's bore
        probe = cyl_z(0.4, z - 0.2, z + 0.2, P.BELT_RX - 1.0, 0.0)
        assert (probe & flange).volume < 1e-6, z
    probe = cyl_z(0.4, P.Z_BELT - 1.0, P.Z_BELT - 0.6, P.BELT_IN_RX - 1.0, 0.0)
    assert (probe & flange).volume < 1e-6                                   # the ring's bore, below
    assert (flange & divider).volume < 1e-6                                 # they never touch



def test_assembly_step_exists_after_build(tmp_path):
    from build123d import export_step
    from mech.common import assembly
    import mech; mech.load_all()
    from mech import ALL
    built = {spec.name: spec.build() for spec in ALL}
    comp = assembly(built)
    expect = sum(len(p.solids()) for p in built.values()) + len(built["stop_pin"].solids())
    assert len(comp.solids()) == expect            # every part's solids, and the pin fitted twice
    labels = [c.label for c in comp.children]
    assert all(labels) and len(labels) == len(ALL) + 1           # the stop pin is fitted twice
    assert labels.count("stop_pin") == 1 and "stop_pin_mirrored" in labels
    # every part that declares a placement is drawn upright at the origin and lands elsewhere:
    # the STEP a printer is given is the print frame, and only assembly() moves it
    at = {c.label: c.bounding_box() for c in comp.children}
    placed_specs = [spec for spec in ALL if spec.placement != Location()]
    assert placed_specs, "no part declares a placement any more; this test has nothing to hold"
    for spec in placed_specs:
        raw = spec.build().bounding_box()
        assert math.isclose(raw.min.Z, 0.0, abs_tol=1e-6), spec.name          # drawn standing up
        moved = at[spec.name]
        assert abs(moved.min.Z - raw.min.Z) + abs(moved.min.X - raw.min.X) > 1e-6, spec.name
    step = tmp_path / "mechanism_assembly.step"                  # the build writes exactly this
    assert export_step(comp, str(step))
    assert step.stat().st_size > 0
    from build123d import import_step
    back = import_step(str(step))                                # the labels survive the round trip
    assert {c.label for c in back.children} == set(labels)


def test_no_two_parts_in_a_group_overlap(placed):
    """Three groups - what is fixed, what pans with the plate, what pans and nods with the stem -
    each checked against itself, bought parts included. The linkage is left out: it sweeps, and
    its own test covers it. Poses are the pose sweep's business (test_pose.py).

    Interface parts of one shell section are let off each other: they are unioned into the same
    section, so an overlap between two of them would close up rather than clash.

    The design's own contacts are asserted for what they are: the divider stands DIVIDER_PROUD
    above the base's rim so the belt screws always squeeze the bead; the filler's cap screws onto
    its neck; the pin is pressed into the stem's hub and its bushing into the -Y cheek; the stop
    lug's sleeve is clamped to the hub's face; the nod servo's tabs lie on their posts.
    """
    from mech import INTERFACES, LINKAGE, NODS, PANS
    from mech.nod import nod_bought
    section = {n: s for s, names in INTERFACES.items() for n in names}
    fx, fy, fh = P.FAN_XY[0], P.FAN_XY[1], P.FAN / 2         # the bought fan, under the deck
    placed = dict(placed, fan=box(fx - fh, fx + fh, fy - fh, fy + fh,
                                  P.Z_DECK - P.DECK_T - P.FAN_T, P.Z_DECK - P.DECK_T),
                  bearing=_bearing())
    bought = nod_bought()
    for name, (shape, _) in bought.items():
        placed[name] = shape
    pans = set(PANS) | {n for n, (_, how) in bought.items() if how == "pans"}
    nods = (set(NODS) | {n for n, (_, how) in bought.items() if how == "nods"}) - set(section)
    contacts = [{"pin", "stem"}, {"bushing", "plate"}, {"stop_lug", "stem"}, {"nod_servo", "plate"},
                {"pin", "bushing"}]
    groups = [[n for n in placed if n not in pans | nods | set(LINKAGE) | {"stop_pin"}],
              sorted(pans), sorted(nods)]
    for group in groups:
        for a, b in itertools.combinations(group, 2):
            if a in section and b in section and section[a] == section[b]:
                continue
            if {a, b} == {"filler_neck", "filler_cap"}:
                continue                     # the cap screws onto the neck; its own test measures that
            if "filler_port" in (a, b) and "filler_cap" in (a, b):
                continue                     # the port's blank runs out past the skin, round the cap
            crush = (placed[a] & placed[b])
            if {a, b} == {"divider", "belt_flange_upper"}:
                bb = crush.bounding_box()
                assert math.isclose(bb.min.Z, P.Z_BASE_TOP, abs_tol=1e-5)
                assert math.isclose(bb.max.Z, P.Z_BASE_TOP + P.DIVIDER_PROUD, abs_tol=1e-5)
                continue
            if {a, b} in contacts:
                continue
            assert crush.volume < 1e-3, (a, b, crush.volume)
    for a, b in ({"pin", "stem"}, {"bushing", "plate"}):                     # the two presses, and no more
        v = (placed[a] & placed[b]).volume
        assert 0.0 < v < 20.0, (a, b, v)


def test_belt_screw_length(parts):
    """An M3 x 20 driven from the counterbore's floor: full engagement, and it does not bottom."""
    lower, upper = parts["belt_flange_lower"], parts["belt_flange_upper"]
    floor = P.Z_BASE_TOP + P.RING_T - (P.SCREW_HEAD_H + 0.5)
    from mech.torso import belt_screws
    x, y = belt_screws()[0]
    head = cyl_z(3.2 - 0.05, floor, P.Z_BASE_TOP + P.RING_T, x, y)
    assert (head & upper).volume < 1e-6                          # the head sinks below the ring's top
    probe = cyl_z(P.INSERT_D / 2 - 0.05, P.Z_BELT - 2 * P.RING_T, P.Z_BELT, x, y)
    bore_floor = (probe & lower).bounding_box().max.Z            # where the insert bore stops
    tip = floor - 20.0
    assert min(P.INSERT_DEPTH, P.Z_BELT - tip) >= P.INSERT_DEPTH - 1e-6   # six millimetres of insert
    assert tip - bore_floor >= 1.0, (tip, bore_floor)                     # ... and daylight below it


def bench_screws():
    """Every screw the deck sub-assembly takes on the bench, in the order they go in, as
    (what, head, the way its driver comes in, driver radius, the parts in place at that moment).

    The hub ring's two radial screws go in with only the plate, the bearing and the cap there -
    under the deck no driver reaches them. The cap's three go down through the plate's three
    holes at pan 0. Then the stem drops in, the pin and the lug from the -Y side before the pan
    servo is on (at pan 0 the pan servo stands in their line), the pin's set screw from behind,
    the nod servo's four from +Y before the deck sits on the cage (whose +Y legs are in their line).
    """
    from mech.nod import LUG_HEAD, LUG_SLEEVE_Y, SET_SCREW_Y, nod_servo_holes, nod_servo_tab_y
    from mech.turntable import HUB_RING_SCREW_Z
    out = []
    first = ("plate", "hub_ring", "bearing_cap", "bearing")
    for a in P.HUB_RING_SCREW_ANGLES:
        ux, uy = math.cos(math.radians(a)), math.sin(math.radians(a))
        out.append((f"hub ring screw at {a:.0f}", (P.HUB_RING_R * ux, P.HUB_RING_R * uy, HUB_RING_SCREW_Z),
                    (ux, uy, 0.0), 3.0, first))
    decked = first + ("deck",)
    for a in P.CAP_SCREW_ANGLES:
        x, y = polar(P.CAP_SCREW_R, a)
        out.append((f"cap screw at {a:.0f}", (x, y, P.Z_BEARING + P.BEARING_B + P.CAP_T), (0, 0, 1), 3.0, decked))
    stemmed = decked + ("stem", "pin", "bushing")
    z_lug = P.Z_NOD - P.STOP_LUG_R
    out.append(("stop lug screw", (0.0, LUG_SLEEVE_Y[0] - LUG_HEAD[1], z_lug), (0, -1, 0), 2.5, stemmed))
    out.append(("pin's set screw", (-P.STEM_HUB_R, SET_SCREW_Y, P.Z_NOD), (-1, 0, 0), 1.5, stemmed))
    yt = nod_servo_tab_y() + P.MG996R["tab_t"]
    for x, z in nod_servo_holes():
        out.append((f"nod servo tab screw at ({x:+.0f}, {z:.0f})", (x, yt, z), (0, 1, 0), 3.0,
                    stemmed + ("nod_servo",)))
    return out


def test_chassis_and_deck_screws_have_driver_paths(parts):
    """A stubby driver on every dry-zone screw head, 30 mm of it, reaches nothing else; and 40 mm
    of driver on every screw of the deck sub-assembly, against what is on the bench when it goes
    in (bench_screws()). The spider's two screws are driven from above before the unit goes on;
    the head's four and the collar's four are the shell tests' (they go through the shell)."""
    from mech.common import phone_body
    from mech.nod import SPIDER_CB_Z, SPIDER_SCREW_X, nod_bought
    from mech.torso import _edeck
    obstacles = dict(parts)
    obstacles["phone"] = phone_body()
    z_chassis = P.Z_CHASSIS + P.CHASSIS_T
    from mech.torso import chassis_screws
    heads = [(xy, z_chassis) for xy in chassis_screws()]
    z_deck = z_chassis + P.EDECK_STANDOFF + P.EDECK_T
    heads += [((x, y), z_deck) for x, y in _edeck(P.EDECK_HOLES)]
    for (x, y), z in heads:
        driver = cyl_z(3.0, z, z + 30.0, x, y)
        for name, other in obstacles.items():
            assert (driver & other).volume < 1e-3, (x, y, name)
    bench = dict(parts, bearing=_bearing(), **{n: s for n, (s, _) in nod_bought().items()})
    for what, head, direction, r, present in bench_screws():
        driver = _driver(head, direction, r=r)
        for name in present:
            v = (driver & bench[name]).volume
            assert v < 1e-3, (what, name, v)
    for x in (-SPIDER_SCREW_X, SPIDER_SCREW_X):                  # from above, before the unit
        driver = cyl_z(3.0, SPIDER_CB_Z + 0.01, SPIDER_CB_Z + 40.0, x, 0.0)
        for name, other in obstacles.items():
            if name == "nozzle_holder":
                continue                                         # it comes with the head, after
            assert (driver & other).volume < 1e-3, ("spider screw", x, name)
