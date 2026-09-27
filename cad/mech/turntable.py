"""The neck: what the head's pan runs on and what turns it.

The deck stands on the cage and carries the pan bearing's outer ring, the pan servo under it and
the fan; the plate rides the bearing's inner ring and carries, in one print, the hub in the
bearing, the two cheeks that hang from the hub down to C and hold the nod drive, the posts the
nod servo's tabs screw to, and the column down to the pan linkage. mech/nod.py has the stem, the
spider and the bought parts of the nod drive.
"""
import math
from build123d import Axis, Location, Polygon, Pos, extrude
import params as P
from mech import part
from mech.common import (ball, box, cyl_x, cyl_y, cyl_z, inner_table, insert_holes, polar,
                         servo_body)
from mech import nod as N


def _polar(r, deg, z):
    """polar() with the height this module's insert_holes calls want."""
    return (*polar(r, deg), z)


# The cavity's own section over the deck's band, measured from out/statue/cavity.stl at z 394,
# 396, 398 and 400 and minimised: the nearest boundary in each ten degrees of azimuth. Re-measured
# against the current mesh the same way, these thirty-six numbers are within 0.9 mm of it, so the
# table is not stale - it simply has nowhere better to live yet.
#
# out/statue/features.json cannot stand in for it. Its `reach` rows carry five numbers each - the
# minimum and the four cardinals - and statue.py's reach() throws the other sixty-eight directions
# away as it goes. Rebuilding this section from what survives misses badly: the minimum alone is
# 35.6 mm short at the sides, and interpolating the cardinals round the azimuth, whether straight
# or as a quadrant ellipse, is out by up to 22.1 and 17.3 mm and is *optimistic* almost everywhere
# - it reads 84 mm at 150 degrees where the coat's back corner is really at 69.3, which is exactly
# where the deck would then grow through the wall. So the literal stays. Move it to features.json
# when the statue stage publishes the whole profile rather than four points of it.
NECK_SECTION = {0: 82.2, 10: 83.2, 20: 88.0, 30: 93.3, 40: 89.7, 50: 89.5, 60: 98.2, 70: 103.4,
                80: 100.9, 90: 105.1, 100: 98.7, 110: 102.5, 120: 91.1, 130: 91.1, 140: 83.0,
                150: 69.3, 160: 69.2, 170: 74.5, 180: 75.6, 190: 74.5, 200: 69.2, 210: 69.3,
                220: 83.0, 230: 91.1, 240: 91.1, 250: 102.5, 260: 98.7, 270: 105.1, 280: 100.9,
                290: 103.4, 300: 98.2, 310: 89.5, 320: 89.7, 330: 93.3, 340: 88.0, 350: 83.2}
NECK_MARGIN = 1.0


def collar_shadow(z_top=P.Z_DECK - P.DECK_T):
    """The narrowest the collar is, in each direction, anywhere from its bottom up to z_top.

    The collar goes on after the deck, lowered over it from above, so a fixed part may stand no
    further out in any direction than the collar comes in anywhere below it - at the back that is
    the coat's own wall at 71, well inside the section at the deck's own height. Read from the
    statue's `collar_inner` table; (angles in degrees, radii).
    """
    t = inner_table("collar")
    if t is None:
        return None
    rows, step = t
    n = len(next(iter(rows.values())))
    out = []
    from mech.collar import tab_in_r
    tabs = {a: tab_in_r(a) for a in P.COLLAR_SCREW_ANGLES}      # and its spigot's tabs under it
    for i in range(n):
        seen = [row[i] for z, row in rows.items() if z <= z_top and row[i] > 0]
        seen += [r for a, r in tabs.items()
                 if abs((i * step - a + 180.0) % 360.0 - 180.0) <= P.SPIGOT_HALF_DEG + step]
        out.append(min(seen) if seen else 0.0)
    return [i * step for i in range(n)], out


def _neck_prism(z0, z1, margin=None):
    """What the deck may occupy in plan: inside the collar's shadow less DECK_SHADOW_MARGIN, or,
    before the statue stage has published it, the hand-measured NECK_SECTION less NECK_MARGIN."""
    sh = collar_shadow()
    if sh is None:
        pts = [polar(NECK_SECTION[a] - NECK_MARGIN, a) for a in sorted(NECK_SECTION)]
    else:
        m = P.DECK_SHADOW_MARGIN if margin is None else margin
        a, r = sh
        n = len(r)
        # each corner takes the least of its own and its neighbours' radii, so the straight edge
        # between two samples never crosses a wall that steps in between them
        low = [min(x for x in (r[(i - 1) % n], r[i], r[(i + 1) % n]) if x > 0) for i in range(n)]
        pts = [polar(x - m, ai) for ai, x in zip(a, low)]
    return Pos(0, 0, z0) * extrude(Polygon(*pts), z1 - z0)


def socket_ball():
    """The collar's socket, less DECK_SOCKET_MARGIN: everything fixed under the dome stays in it."""
    return ball(P.NECK_SPHERE_R - P.TURN_GAP - P.WALL - P.DECK_SOCKET_MARGIN)


def _sector(a0, a1, z0, z1, far):
    """The wedge between two azimuths, out to `far`, over z0..z1. a1 - a0 must be under 180."""
    ahead = box(0, far, -far, far, z0, z1)                 # every point with x >= 0
    return ahead.rotate(Axis.Z, a1 - 90.0) & ahead.rotate(Axis.Z, a0 + 90.0)


def _column_slot(z0, z1):
    """The arc the plate's hanging column swings in: the annulus r0..r1 within +/-half of +X.

    The deck and the ring below it are both in the column's way, so both are cut with this.
    """
    r0, r1, half = P.DECK_SLOT
    band = cyl_z(r1, z0, z1) - cyl_z(r0, z0 - 1, z1 + 1)
    ahead = box(0, r1 + 5, -(r1 + 5), r1 + 5, z0 - 1, z1 + 1)          # every point with x >= 0
    return band & ahead.rotate(Axis.Z, half - 90) & ahead.rotate(Axis.Z, 90 - half)


@part("deck_ring")
def deck_ring():
    """A cage: four legs from the chassis up to the deck, tied at their feet and nowhere else.

    Nothing above the coat's shoulder is fixed any more but the two side panels, and the bell
    sweeps the ground between them, so the deck cannot hang from the shell. It stands instead
    on four legs that run straight down to the chassis and bolt through it from below, inside
    the bell's bore the whole way. The deck's own four screws go into the legs' tops.

    It used to carry two annuli - one under the deck and a tie at z 304 - and between them they
    made the machine unassemblable: the electronics deck is 100 x 92 and the phone's sled reaches
    r 81.6, and neither can be got past a ring whose bore is 50. Nor can the ring be opened to
    let them through, because the bell turns +-65 degrees over everything above Z_TURN and the
    coat's back sweeps in to r 69: any ring wide enough for the boards is wider than that. So
    both are gone, and what ties the legs is a foot ring at the one height where there is room
    for it - between the chassis's face and the boards' underside, below everything that has to
    come down past the legs - open CAGE_FOOT_OPEN either side of +X where the sled drops in.

    What binds the legs' radius is not the cavity but the bell's own inner wall as it comes
    round: the coat's back is 69 mm out where its flanks are 105, and 130 degrees of pan bring
    that back over every azimuth the legs stand at. test_shell turns the built bell against the
    built cage every 5 degrees and measures it - 2.98 mm at the nearest, at +30 degrees - and
    test_mech keeps the same rule cheaply, against the statue's own reach table.

    The legs do not need a mid-span tie. Each is a 10 mm square PETG column 134 mm long, built
    in at the chassis and at the deck: its radius of gyration is 2.89 mm, so L/k is 46 - stocky,
    not slender - and the Euler load of the fixed-fixed case, 4 pi^2 EI / L^2, is 3.7 kN at
    E = 2 GPa. The four of them carry the bell, the plate and the deck, some 16 N between them.

    Print it foot ring down: the ring lies flat on the bed and the four legs rise 134 mm off it,
    no overhang anywhere and nothing to bridge. Use a brim.
    """
    z1 = P.Z_DECK - P.DECK_T
    foot = P.Z_CHASSIS + P.CHASSIS_T
    half = P.CAGE_LEG / 2
    cage = None
    for a in P.DECK_SCREW_ANGLES:
        leg = box(P.CAGE_LEG_R - half, P.CAGE_LEG_R + half, -half, half, foot, z1).rotate(Axis.Z, a)
        cage = leg if cage is None else cage + leg
    top = foot + P.CAGE_FOOT_T                          # the foot ring, in the legs' own band but
    ring = (cyl_z(P.CAGE_LEG_R + half - 2.5, foot, top)  # 2.5 short of their outside: the chassis's screws'
                                                        # drivers, and the filler's hose down the back
            - cyl_z(P.CAGE_LEG_R - half, foot - 1, top + 1))
    reach = P.CAGE_LEG_R + half + 5.0
    ring = ring - _sector(-P.CAGE_FOOT_OPEN, P.CAGE_FOOT_OPEN, foot - 1, top + 1, reach)
    cage = cage + ring
    # the pan servo and its hangers share the -Y quarter with the legs, but only from the servo's
    # own shaft face upward: below that the legs and the foot ring have the floor to themselves
    for hx, hy in P.pan_hangers():
        cage = cage - box(hx - P.PAN_HANGER / 2 - P.CLEAR, hx + P.PAN_HANGER / 2 + P.CLEAR,
                          hy - P.PAN_HANGER / 2 - P.CLEAR, hy + P.PAN_HANGER / 2 + P.CLEAR,
                          P.Z_PAN_SHAFT_FACE, z1 + 1)
    fx, fy, fh = P.FAN_XY[0], P.FAN_XY[1], P.FAN / 2    # the fan hangs past the -Y legs
    cage = cage - box(fx - fh - P.CLEAR, fx + fh + P.CLEAR, fy - fh - P.CLEAR, fy + fh + P.CLEAR,
                      z1 - P.FAN_T - P.CLEAR, z1 + 1)
    feet = [_polar(P.CAGE_LEG_R, a, foot) for a in P.DECK_SCREW_ANGLES]
    cage = insert_holes(cage, feet, direction="up")     # an M3 up through the chassis into each foot
    return insert_holes(cage, [_polar(P.DECK_SCREW_R, a, z1) for a in P.DECK_SCREW_ANGLES],
                        depth=P.RING_T - 1)


POCKET_R = P.BEARING_OD / 2 + P.BEARING_FIT          # 32.65, the outer ring's seat


@part("deck")
def deck():
    """Carries the pan bearing's outer ring, the pan servo hanging beneath it, the fan, and the
    pan hard stops.

    The bearing drops into a pocket from above onto a millimetre's lip and stands 2 mm proud of
    the deck's top; the printed cap clamps it there. The deck's outline is whatever the socket
    leaves: the statue's section less its margin, the collar's narrowest opening under it (the
    collar is lowered over it), and the socket's inner sphere, which bevels the rim.
    """
    z1, z0 = P.Z_DECK, P.Z_DECK - P.DECK_T
    far = P.DECK_LOBE["r"] + 10.0
    d = cyl_z(P.DECK_R, z0, z1)
    lobe = P.DECK_LOBE                                     # a wider lobe where the hangers are
    d = d + (cyl_z(lobe["r"], z0, z1)
             & _sector(lobe["angle"] - lobe["half"], lobe["angle"] + lobe["half"], z0 - 1, z1 + 1, far))
    back = _sector(140.0, 220.0, z0 - 1, z1 + 1, far) - cyl_z(P.DECK_BACK_R, z0 - 2, z1 + 2)
    d = d - back                                           # ... and cut back where the coat closes in
    d = d & _neck_prism(z0 - 1, z1 + 1)                    # ... then trimmed to what the collar passes
    d = d - cyl_z(POCKET_R, P.Z_BEARING, z1 + 1)                           # the bearing's seat
    d = d - cyl_z(P.BEARING_OUT_LAND_R, z0 - 1, z1 + 1)                    # ... and its lip
    d = insert_holes(d, [_polar(P.CAP_SCREW_R, a, z1) for a in P.CAP_SCREW_ANGLES],
                     depth=P.INSERT_DEPTH_SHORT)                           # the cap's screws, blind
    for a in P.DECK_SCREW_ANGLES:                                          # down into the ring
        x, y, _ = _polar(P.DECK_SCREW_R, a, 0)
        d = d - cyl_z(P.M3_CLEAR / 2, z0 - 1, z1 + 1, x, y)
    d = d - _column_slot(z0 - 1, z1 + 1)                                   # the plate's hanging column
    # hangers for the pan servo, down from the underside to the tabs' upper face
    z_tab = P.Z_PAN_SHAFT_FACE + (P.DS3218["body"][2] - P.DS3218["tab_z"]) + P.DS3218["tab_t"]
    for hx, hy in P.pan_hangers():
        d = d + box(hx - P.PAN_HANGER / 2, hx + P.PAN_HANGER / 2, hy - P.PAN_HANGER / 2, hy + P.PAN_HANGER / 2, z_tab, z0 + 0.01)
        d = insert_holes(d, [(hx, hy, z_tab)], direction="up")
    # the tab holes sit only 4.75 mm outside the body's end faces, so a 10 mm hanger overhangs
    # them by 0.25; trim every hanger back to a clearance around the servo
    L, W, H = P.DS3218["body"]
    off, (sx, sy) = P.DS3218["shaft_off"], P.PAN_SERVO_XY
    d = d - box(sx - off - P.PAN_SERVO_FIT, sx + (L - off) + P.PAN_SERVO_FIT,
                sy - W / 2 - P.PAN_SERVO_FIT, sy + W / 2 + P.PAN_SERVO_FIT,
                P.Z_PAN_SHAFT_FACE - 1, P.Z_PAN_SHAFT_FACE + H + P.PAN_SERVO_FIT)
    # the fan hangs under the deck and blows up through it. Its screws take short inserts drilled
    # blind into the deck itself: it is six thick and the insert four
    fx, fy = P.FAN_XY
    d = d - cyl_z(P.FAN_HOLE_D / 2, z0 - 1, z1 + 1, fx, fy)
    d = insert_holes(d, [(fx + dx, fy + dy, z0) for dx in (-P.FAN_PITCH / 2, P.FAN_PITCH / 2)
                         for dy in (-P.FAN_PITCH / 2, P.FAN_PITCH / 2)],
                     depth=P.INSERT_DEPTH_SHORT, direction="up")
    # seats for the two hard-stop pins, drilled from the top face. STOP_PIN_DEPTH is the deck's
    # own thickness, so they go right through: the pin is glued and its end shows underneath.
    for sign in (1, -1):
        x, y, _ = _polar(P.STOP_POST_R, sign * P.stop_pin_deg(), 0)
        d = d - cyl_z(P.STOP_PIN_SEAT_D / 2, z1 - P.STOP_PIN_DEPTH, z1 + 0.01, x, y)
    return d & socket_ball()


CAP_STEP_R = P.BEARING_OD / 2 + 0.8                  # the cap's inner band presses the outer ring out to here


@part("bearing_cap")
def bearing_cap():
    """Clamps the bearing's outer ring down onto the deck's lip: three countersunk M3 x 8 into
    short inserts in the deck.

    Its underside steps: the inner band lies on the ring, which stands 2 mm proud of the deck,
    and the outer band stands 0.2 mm off the deck, so the screws load the ring and not the deck.
    It goes on over the plate's hub before the bearing does and waits under the plate; its
    screws are driven through three holes in the plate at pan 0. Prints top face down.
    """
    zr = P.Z_BEARING + P.BEARING_B                    # 402, the ring's top face
    top = zr + P.CAP_T
    c = cyl_z(CAP_STEP_R, zr, top) + (cyl_z(P.CAP_R, P.Z_DECK + 0.2, top) - cyl_z(CAP_STEP_R, zr - 5, zr))
    c = c - cyl_z(P.BEARING_OUT_LAND_R, zr - 5, top + 1)
    fx, fy = P.FAN_XY
    c = c - cyl_z(P.FAN_HOLE_D / 2, zr - 5, top + 1, fx, fy)       # the fan blows through here too
    for a in P.CAP_SCREW_ANGLES:
        x, y = polar(P.CAP_SCREW_R, a)
        c = c - cyl_z(P.M3_CLEAR / 2, zr - 5, top + 1, x, y)
        c = c - (Pos(x, y, top) * _countersink())
    return c


def _countersink():
    """A 90 degree countersink for an M3 flat head, 6 across at the face, pointing down from z 0."""
    from build123d import Cone
    h = (6.0 - P.M3_CLEAR) / 2
    return Pos(0, 0, -h / 2) * Cone(P.M3_CLEAR / 2, 3.0, h) + cyl_z(3.0, 0, 1.0)


HUB_RING_SCREW_Z = P.Z_HUB_BOTTOM + 2.75             # 390.75


@part("hub_ring")
def hub_ring():
    """Clamps the bearing's inner ring up against the plate's shoulder, from below.

    It slides up the hub over the yoke - its bore is the hub's, and the yoke under the hub is
    narrower - and two radial countersunk M3 x 10 go through it into inserts in the hub where
    the hub is solid, beside the cheeks. That is done on the bench, before the plate goes into
    the deck: under the deck no driver reaches them. It passes the deck's lip after. Prints flat.
    """
    z0, z1 = P.Z_HUB_BOTTOM, P.Z_BEARING
    band = z1 - 1.5
    r = cyl_z(P.HUB_RING_R, z0, band) + cyl_z(P.BEARING_IN_LAND_R, band - 0.01, z1)
    r = r - cyl_z(P.HUB_R + 0.15, z0 - 1, z1 + 1)
    for a in P.HUB_RING_SCREW_ANGLES:
        hole = cyl_x(P.M3_CLEAR / 2, P.HUB_R - 1, P.HUB_RING_R + 1, 0.0, HUB_RING_SCREW_Z)
        sink = Pos(P.HUB_RING_R, 0, HUB_RING_SCREW_Z) * (_countersink().rotate(Axis.Y, 90))
        r = r - (hole + sink).rotate(Axis.Z, a)
    return r


@part("stop_pin")
def stop_pin():
    """Glued into the deck; the plate's tab runs into it at the pan stop. Print two."""
    x, y, _ = _polar(P.STOP_POST_R, P.stop_pin_deg(), 0)
    return cyl_z(P.STOP_POST_D / 2, P.Z_DECK - P.STOP_PIN_DEPTH, P.STOP_PIN_TOP, x, y)


CHEEK_R = 16.0                                       # the -Y cheek round C: pin, bushing, stop slot
CHEEK_W = 9.0                                        # both cheeks' half-width where they leave the hub
SERVO_POST_Z = (332.0, P.Z_NOD - P.MG996R["shaft_off"] - 0.3,        # under the case ...
                P.Z_NOD - P.MG996R["shaft_off"] + P.MG996R["body"][0] + 0.3, P.Z_HUB_BOTTOM)   # ... over it


@part("plate")
def plate():
    """The head's pan: rides the bearing's inner ring and carries the whole nod drive but the
    stem, in one print.

    The disc sits over the bearing's cap; under it a shoulder bears on the inner ring's face and
    the hub goes down through the ring to Z_HUB_BOTTOM. The neck of the stem swings in a slot
    through all of it, |y| <= 6.4, as long as its sweep over the hard stops plus NOD_CLEAR. From
    the hub two cheeks hang down to C: the -Y cheek carries the pin's bushing and the arc slot
    the stop lug runs in; the +Y cheek is thin and only joins the nod servo's two posts round the
    servo's spline. Everything below the hub is inside r 23.3, so the plate and yoke drop through
    the bearing's 50 mm bore. The column still hangs from the stop tab to the pan linkage.

    Prints disc down, hub and cheeks up; the posts' undersides are the overhang.
    """
    z0, z1 = P.Z_PLATE_BOTTOM, P.Z_PLATE_TOP
    p = cyl_z(P.PLATE_R, z0, z1)
    p = p + box(P.PLATE_R - 1, P.STOP_POST_R + P.STOP_POST_D / 2 + 1, -P.STOP_TAB_W / 2, P.STOP_TAB_W / 2, z0, z1)
    p = p + cyl_z(P.BEARING_IN_LAND_R, P.Z_BEARING + P.BEARING_B, z0 + 0.01)       # the shoulder
    p = p + cyl_z(P.HUB_R, P.Z_HUB_BOTTOM, P.Z_BEARING + P.BEARING_B + 0.01)       # the hub
    # the cheeks
    y0, y1 = P.CHEEK_Y
    neg = box(-CHEEK_W, CHEEK_W, -y1, -y0, P.Z_NOD, P.Z_HUB_BOTTOM + 0.01)
    neg = neg + cyl_y(CHEEK_R, -y1, -y0, 0.0, P.Z_NOD)
    neg = neg + N.xz_prism([(-CHEEK_W, P.Z_NOD + 30), (CHEEK_W, P.Z_NOD + 30),
                            (CHEEK_R, P.Z_NOD), (-CHEEK_R, P.Z_NOD)], -y1, -y0)
    sy0, _ = P.SERVO_CHEEK_Y
    sy1 = P.SERVO_CHEEK_Y[1]
    ytab = N.nod_servo_tab_y()
    pos = box(-CHEEK_W, CHEEK_W, sy0, sy1, SERVO_POST_Z[0], P.Z_HUB_BOTTOM + 0.01)
    for za, zb in ((SERVO_POST_Z[0], SERVO_POST_Z[1]), (SERVO_POST_Z[2], SERVO_POST_Z[3] + 0.01)):
        pos = pos + box(-CHEEK_W, CHEEK_W, sy0, ytab, za, zb)
    p = p + neg + pos
    # the column from the stop tab's underside through the deck's slot, and the foot bar to the pin
    r_in, r_out, w = P.PAN_COLUMN
    p = p + box(r_in, r_out, -w / 2, w / 2, P.Z_CRANK_BOTTOM, z0 + 0.01)
    p = p + box(P.PAN_FOOT_R_IN, r_out, -w / 2, w / 2, P.Z_CRANK_BOTTOM, P.Z_CRANK_TOP)
    px, py = P.crank_pins(0)[0]
    # the pin's boss: the screw clamps this half-millimetre, so the link is free to turn on it
    p = p + cyl_z(P.PIN_BOSS_D / 2, P.Z_CRANK_BOTTOM - P.PIN_BOSS_H, P.Z_CRANK_BOTTOM, px, py)
    p = insert_holes(p, [(px, py, P.Z_CRANK_BOTTOM - P.PIN_BOSS_H)],
                     depth=P.INSERT_DEPTH_SHORT + P.PIN_BOSS_H, direction="up")     # blind in a 5 mm bar
    # the stem's slot, the cap's three access holes, the hub ring's two inserts
    p = p - N.neck_slot(P.Z_HUB_BOTTOM - 1.0, z1 + 1.0)
    for a in P.CAP_SCREW_ANGLES:
        x, y = polar(P.CAP_SCREW_R, a)
        p = p - cyl_z(3.5, z0 - 1, z1 + 1, x, y)
    for a in P.HUB_RING_SCREW_ANGLES:
        bore = cyl_x(P.INSERT_D / 2, P.HUB_R - P.INSERT_DEPTH, P.HUB_R + 1.0, 0.0, HUB_RING_SCREW_Z)
        p = p - bore.rotate(Axis.Z, a)
    # the nod drive's seats: the bushing, the stop slot, the servo's spline, the tab inserts
    p = p - cyl_y(P.BUSH_OD / 2 - 0.05, -y1 - 1, -y0 + 0.01, 0.0, P.Z_NOD)
    a0, a1 = N.stop_slot_angles()
    slot = (cyl_y(P.STOP_LUG_R + P.STOP_LUG_D / 2 + 0.2, -y1 - 1, -y0 + 1, 0.0, P.Z_NOD)
            - cyl_y(P.STOP_LUG_R - P.STOP_LUG_D / 2 - 0.2, -y1 - 2, -y0 + 2, 0.0, P.Z_NOD))
    p = p - (slot & N.xz_wedge(a0, a1, CHEEK_R + 5, -y1 - 1, -y0 + 1))
    p = p - cyl_y(P.SPLINE_BOSS[0] / 2 + 1.0, sy0 - 1, sy1 + 1, 0.0, P.Z_NOD)
    for x, z in N.nod_servo_holes():
        p = p - cyl_y(P.INSERT_D / 2, ytab - P.INSERT_DEPTH, ytab + 0.01, x, z)
    return p


@part("servo_crank")
def servo_crank():
    """Hangs on the pan servo's horn, pocketed from above; carries the far pin of the parallelogram below."""
    z0, z1 = P.Z_CRANK_BOTTOM, P.Z_CRANK_TOP
    sx, sy = P.PAN_SERVO_XY
    dx, dy = P.crank_pins(0)[0]
    px, py = sx + dx, sy + dy
    arm = box(min(sx, px) - 4, max(sx, px) + 4, min(sy, py) - 4, max(sy, py) + 4, z0, z1)
    arm = arm + cyl_z(P.HORN_D / 2 + 3, z0, z1, sx, sy) + cyl_z(4, z0, z1, px, py)
    arm = arm - cyl_z(P.HORN_D / 2 + P.CLEAR / 2, z1 - P.HORN_T, z1 + 1, sx, sy)      # horn pocket from above
    for a in (0, 90, 180, 270):
        hx, hy, _ = _polar(P.HORN_SCREW_R, a, 0)
        arm = arm - cyl_z(P.M2_5_CLEAR / 2, z0 - 1, z1 + 1, sx + hx, sy + hy)
    arm = arm - cyl_z(2.5, z0 - 1, z1 + 1, sx, sy)                                     # horn's centre screw
    arm = arm + cyl_z(P.PIN_BOSS_D / 2, z0 - P.PIN_BOSS_H, z0, px, py)                 # the link turns on this
    return insert_holes(arm, [(px, py, z0 - P.PIN_BOSS_H)],
                        depth=P.INSERT_DEPTH_SHORT + P.PIN_BOSS_H, direction="up")     # blind in a 5 mm crank


@part("pan_link")
def pan_link():
    """Joins the plate's pin to the servo crank's pin, below both. Eye-to-eye is the servo offset."""
    z0, z1 = P.Z_LINK_BOTTOM, P.Z_LINK_TOP
    (ax, ay), (bx, by) = P.crank_pins(0)
    length = math.hypot(bx - ax, by - ay)
    ang = math.degrees(math.atan2(by - ay, bx - ax))
    bar = box(0, length, -3.0, 3.0, z0, z1).rotate(Axis.Z, ang).moved(Location((ax, ay, 0)))
    link = bar + cyl_z(P.LINK_EYE_R, z0, z1, ax, ay) + cyl_z(P.LINK_EYE_R, z0, z1, bx, by)
    return link - cyl_z(P.PIN_BORE / 2, z0 - 1, z1 + 1, ax, ay) - cyl_z(P.PIN_BORE / 2, z0 - 1, z1 + 1, bx, by)
