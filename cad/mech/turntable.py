"""The neck: what the head stands on and what turns it."""
import math
from build123d import Location, Axis
import params as P
from mech import part
from mech.common import cyl_x, cyl_y, cyl_z, box, insert_holes, polar, servo_body


def _polar(r, deg, z):
    """polar() with the height this module's insert_holes calls want."""
    return (*polar(r, deg), z)


def _bearing_holes(part, z0, z1):
    """The lazy susan's four screws, on the diagonal of its bolt square."""
    for a in (45, 135, 225, 315):
        x, y, _ = _polar(P.BEARING_PITCH / 2 * math.sqrt(2), a, 0)
        part = part - cyl_z(P.BEARING_HOLE / 2, z0, z1, x, y)
    return part


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


@part("deck_ring", section="torso")
def deck_ring():
    """Narrow annulus the deck bolts to, joined to the shoulders' wall by four webs. Unioned into the torso.

    Narrow on purpose: the phone's top passes outside it (PHONE_FRONT_X > RING_R_OUT). Cut
    away around the pan servo hanging beneath it, and along the arc the plate's column swings
    in: the column reaches r 52.15, past the ring's own bore at RING_R_IN.
    """
    z1 = P.Z_DECK - P.DECK_T
    z0 = z1 - P.RING_T
    ring = cyl_z(P.RING_R_OUT, z0, z1) - cyl_z(P.RING_R_IN, z0 - 1, z1 + 1)
    r_wall = P.ring_r_out(P.TORSO_PROFILE, z0, z1)
    for a in P.DECK_SCREW_ANGLES:
        ring = ring + box(P.RING_R_OUT - 2, r_wall, -P.RING_WEB_W / 2, P.RING_WEB_W / 2, z0, z1).rotate(Axis.Z, a)
    (x0, y0), (x1, y1) = P.PAN_RING_CUT
    ring = ring - box(x0, x1, y0, y1, z0 - 1, z1 + 1)
    ring = ring - _column_slot(z0 - 1, z1 + 1)          # RING_R_IN is 50; the column reaches r 52.15
    return insert_holes(ring, [_polar(P.DECK_SCREW_R, a, z1) for a in P.DECK_SCREW_ANGLES], depth=P.RING_T - 1)


@part("deck")
def deck():
    """Carries the bearing's fixed ring, the pan servo hanging beneath it, and the pan hard stops.

    The servo is wholly below the deck now, so there is no notch: only the arc slot the
    plate's column swings in and four columns the servo's tabs screw up into.
    """
    z1, z0 = P.Z_DECK, P.Z_DECK - P.DECK_T
    far = P.DECK_LOBE["r"] + 10.0
    d = cyl_z(P.DECK_R, z0, z1)
    lobe = P.DECK_LOBE                                     # a wider lobe where the hangers' corners are
    d = d + (cyl_z(lobe["r"], z0, z1)
             & _sector(lobe["angle"] - lobe["half"], lobe["angle"] + lobe["half"], z0 - 1, z1 + 1, far))
    back = _sector(140.0, 220.0, z0 - 1, z1 + 1, far) - cyl_z(P.DECK_BACK_R, z0 - 2, z1 + 2)
    d = d - back                                           # ... and cut back where the coat closes in
    d = d - cyl_z(P.SHAFT_OD / 2 + P.CLEAR + 1.0, z0 - 1, z1 + 1)          # shaft passes with room
    d = _bearing_holes(d, z0 - 1, z1 + 1)
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
    # seats for the two hard-stop pins, drilled from the top face. STOP_PIN_DEPTH is the deck's
    # own thickness, so they go right through: the pin is glued and its end shows underneath.
    # The pins are separate parts, so nothing stands proud and the deck prints flat, hangers up.
    for sign in (1, -1):
        x, y, _ = _polar(P.STOP_POST_R, sign * P.stop_pin_deg(), 0)
        d = d - cyl_z((P.STOP_POST_D + 0.1) / 2, z1 - P.STOP_PIN_DEPTH, z1 + 0.01, x, y)
    return d


@part("stop_pin")
def stop_pin():
    """Glued into the deck; the plate's tab runs into it at the pan stop. Print two."""
    x, y, _ = _polar(P.STOP_POST_R, P.stop_pin_deg(), 0)
    return cyl_z(P.STOP_POST_D / 2, P.Z_DECK - P.STOP_PIN_DEPTH, P.STOP_PIN_TOP, x, y)


@part("plate")
def plate():
    """The head's foundation: sits on the bearing, carries the shaft and the pan hard-stop tab.

    Nothing of the drive is above it any more. Under the stop tab a column hangs down
    through the deck's arc slot to a foot bar below the deck, and the foot carries the
    plate's half of the parallelogram. The disc's top face has only the yoke's inserts.
    """
    z0 = P.Z_DECK + P.BEARING_T
    z1 = P.Z_PLATE_TOP
    p = cyl_z(P.PLATE_R, z0, z1)
    p = p - cyl_z(P.SHAFT_OD / 2 + 0.1, z0 - 1, z1 + 1)                    # shaft bonds in here
    p = _bearing_holes(p, z0 - 1, z1 + 1)                                  # bearing's top ring
    p = p + box(P.PLATE_R - 1, P.STOP_POST_R + P.STOP_POST_D / 2 + 1, -P.STOP_TAB_W / 2, P.STOP_TAB_W / 2, z0, z1)  # stop tab, front
    # column from the stop tab's underside through the deck's slot, and the foot bar to the pin
    r_in, r_out, w = P.PAN_COLUMN
    p = p + box(r_in, r_out, -w / 2, w / 2, P.Z_CRANK_BOTTOM, z0 + 0.01)
    p = p + box(P.PAN_FOOT_R_IN, r_out, -w / 2, w / 2, P.Z_CRANK_BOTTOM, P.Z_CRANK_TOP)
    px, py = P.crank_pins(0)[0]
    # the pin's boss: the screw clamps this half-millimetre, so the link is free to turn on it
    p = p + cyl_z(P.PIN_BOSS_D / 2, P.Z_CRANK_BOTTOM - P.PIN_BOSS_H, P.Z_CRANK_BOTTOM, px, py)
    p = insert_holes(p, [(px, py, P.Z_CRANK_BOTTOM - P.PIN_BOSS_H)],
                     depth=P.INSERT_DEPTH_SHORT + P.PIN_BOSS_H, direction="up")     # blind in a 5 mm bar
    # the yoke and the shroud stack 3 + 3 above a 4 mm insert, so an M3 x 10 would bottom out;
    # a millimetre more hole gives it daylight
    p = insert_holes(p, [_polar(P.YOKE_SCREW_R, a, z1) for a in P.YOKE_SCREW_ANGLES],
                     depth=P.INSERT_DEPTH_SHORT + 1)
    return p


@part("shaft")
def shaft():
    """Hollow, passive: bonded into the plate, turns inside the bearing's opening."""
    z1 = P.Z_PLATE_TOP + 6.0                 # proud of the plate for a flared lip
    z0 = P.SHAFT_BOTTOM                      # below the link's plane, so the tube leaves clear of the sweep
    s = cyl_z(P.SHAFT_OD / 2, z0, z1) - cyl_z(P.SHAFT_ID / 2, z0 - 1, z1 + 1)
    flare = cyl_z(P.SHAFT_OD / 2 + 3, z1 - 3, z1) - cyl_z(P.SHAFT_ID / 2, z1 - 4, z1 + 1)
    return s + flare


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


def jet_axis(deg):
    """Where the jet leaves the mouth and which way it points, in (r, z), at a tilt of `deg`.

    Positive is nose up, the machine's convention. The mouth is on the head's sphere, so its
    x comes from HEAD_R and the mouth's drop below the tilt axis.
    """
    x0 = math.sqrt(P.HEAD_R ** 2 - (P.Z_HEAD - P.Z_MOUTH) ** 2)
    dz = P.Z_MOUTH - P.Z_HEAD
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return (x0 * c - dz * s, P.Z_HEAD + x0 * s + dz * c), (c, s)


TAIL = 10.0             # how far the arm reaches back from the pivot, to the tube's barb
BARB_D = 4.4            # the 6 x 4 tube pushes over this
ARM_W = 12.0            # across the beard's parting, which is NOZZLE_SLOT_W wide
ARM_T = 14.0            # the arm's depth, perpendicular to its length
BRACKET_SCREW_ANGLES = (-24.0, 24.0)   # clear of the servo's body and of the arm's wedge
BOSS_D = P.INSERT_D + 4.0
BOSS_OUT = 5.0          # how far a radial insert boss stands off the shroud's wall


def _tail_reach(deg):
    """Where the arm's barb sits at a tilt of `deg`, in (r, z)."""
    a = math.radians(deg)
    return (P.NOZZLE_PIVOT[0] - TAIL * math.cos(a), P.NOZZLE_PIVOT[2] - TAIL * math.sin(a))


def jet_notch_z():
    """How low the shroud's front opening reaches.

    The jet no longer crosses the shroud - it leaves an arm outside it - so what the opening
    has to pass is the arm's tail, which swings inside the wall, and the tube behind it. The
    lowest the barb gets is at the nose-up stop; the opening starts its radius and 2 mm below.
    """
    low = min(_tail_reach(d)[1] for d in P.TILT_STOP)
    return low - BARB_D / 2 - 2.0


def _arm_swing():
    """The wedge the arm sweeps through the shroud's and the bracket's front walls.

    The arm's corners reach lowest at the nose-up stop and highest at the nose-down one; the
    wedge is JET_NOTCH_HALF_DEG either side of +X, which at the wall is wider than the arm.
    """
    lo = hi = P.NOZZLE_PIVOT[2]
    for deg in P.TILT_STOP:
        a = math.radians(deg)
        for dx, dz in ((-TAIL, ARM_T / 2), (-TAIL, -ARM_T / 2)):
            z = P.NOZZLE_PIVOT[2] + dx * math.sin(a) + dz * math.cos(a)
            lo, hi = min(lo, z), max(hi, z)
    half = P.JET_NOTCH_HALF_DEG
    return _sector(-half, half, lo - 2.0, hi + 2.0, P.SHROUD_R_OUT + 20.0)


def _jet_notch():
    """The opening through the shroud's front: the arm's tail swings in it, the tube leaves by it."""
    half = P.JET_NOTCH_HALF_DEG
    return _sector(-half, half, jet_notch_z(), P.SHROUD_TOP_Z + 5.0, P.SHROUD_R_OUT + 10.0)


def _radial_span(r0, r1, deg, z, half):
    """A square bar lying along the radius at azimuth `deg`, from r0 to r1, 2*half across."""
    bar = box(r0, r1, -half, half, z - half, z + half).rotate(Axis.Z, deg)
    return bar & cyl_z(r1, z - half, z + half)


def _radial_boss(part, r, deg, z):
    """A boss on the shroud's outside with an insert bored radially inward from its face."""
    part = part + _radial_span(r - 3.0, r + BOSS_OUT, deg, z, BOSS_D / 2)
    return part - _radial_span(r + BOSS_OUT - P.INSERT_DEPTH, r + BOSS_OUT + 1, deg, z, P.INSERT_D / 2)


@part("neck_shroud")
def neck_shroud():
    """Turns with the plate and carries the statue's beard, head and hat.

    A plain cup now that nothing nods: a ring on the plate's rim held by the same four screws,
    a barrel up to a closed top, an opening at the front the nozzle arm's tail swings in, and
    four radial inserts the head shell screws into from outside, hidden in the beard's locks.
    """
    r, w = P.SHROUD_R_OUT, P.WALL
    z0, z1 = P.SHROUD_BASE_Z, P.SHROUD_TOP_Z
    base_top = z0 + 3.0
    s = cyl_z(r, z0, z1) - cyl_z(r - w, base_top, z1 - w)          # barrel, closed at the top
    s = s - cyl_z(P.YOKE_RING_R_IN, z0 - 1, base_top + 0.01)       # the ring's bore
    s = s - cyl_z(5.0, z1 - w - 1, z1 + 1)                         # the tube and the servo's lead
    s = s - _jet_notch()
    head_d = P.M3_CLEAR + 2.6                                      # an M3 socket head is 5.5 across
    for a in P.YOKE_SCREW_ANGLES:
        x, y = polar(P.YOKE_SCREW_R, a)
        s = s - cyl_z(P.M3_CLEAR / 2, z0 - 1, z0 + 6, x, y)
        s = s - cyl_z(head_d / 2, base_top, z0 + 8, x, y)          # head sunk, 3 mm of ring left
    for a in P.SHROUD_SCREW_ANGLES:                                # the head shell's four screws
        s = _radial_boss(s, r, a, P.SHROUD_SCREWS_Z)
    for a in BRACKET_SCREW_ANGLES:                                 # ... and the tilt bracket's two
        s = _radial_boss(s, r, a, P.NOZZLE_PIVOT[2])
    return s


SERVO_SHAFT_Y = -8.0    # the micro servo's output face; its body runs on to -Y, beside the arm
CHEEK_Y = (-17.5, -15.5)   # the servo's tabs land here: tab_z up the body from its far end
FAR_CHEEK_Y = (6.5, 9.5)   # the far end of the pivot runs in this one


def _tilt_servo():
    """The MG92B where it sits: shaft along +Y at the pivot's height, body out to -Y."""
    return servo_body(P.MG92B, (P.NOZZLE_PIVOT[0], SERVO_SHAFT_Y, P.NOZZLE_PIVOT[2]), axis="y")


def nozzle_tip(deg):
    """Where the nozzle's tip is, and which way it points, at a tilt of `deg`. Nose up is positive."""
    px, _, pz = P.NOZZLE_PIVOT
    a = math.radians(deg)
    return (px + P.NOZZLE_ARM_L * math.cos(a), pz + P.NOZZLE_ARM_L * math.sin(a)), (math.cos(a), math.sin(a))


@part("tilt_bracket")
def tilt_bracket():
    """Hangs off the shroud's front and carries the micro servo and the nozzle arm's pivot.

    Two M3 into radial inserts in the shroud, a saddle that follows its wall, a cheek the
    servo's tabs bolt to and a second cheek that takes the far end of the pivot. It is fitted
    before the beard shell goes on, which is the only time a driver can reach those screws.
    """
    r, px, pz = P.SHROUD_R_OUT, P.NOZZLE_PIVOT[0], P.NOZZLE_PIVOT[2]
    y0, y1 = CHEEK_Y[0], FAR_CHEEK_Y[1]
    back = (cyl_z(r + 3.0, P.SHROUD_BASE_Z + 3.0, 446.0) - cyl_z(r + P.CLEAR, P.SHROUD_BASE_Z + 2.0, 447.0)) \
        & _sector(-30.0, 30.0, 0, 600, r + 10.0)
    b = back + box(50.0, 70.0, *CHEEK_Y, 412.0, 446.0)             # the servo's cheek
    b = b + box(50.0, 70.0, *FAR_CHEEK_Y, 416.0, 432.0)            # ... and the far bearing's
    bb = _tilt_servo().bounding_box()
    b = b - box(bb.min.X - P.CLEAR, bb.max.X + P.CLEAR, y0 - 1, y1 + 1,
                bb.min.Z - P.CLEAR, bb.max.Z + P.CLEAR)            # the body drops through the cheek
    along = P.MG92B["holes"][0]
    zc = (bb.min.Z + bb.max.Z) / 2
    for dz in (-along / 2, along / 2):                             # the tabs' two M2 screws
        b = b - cyl_y(2.4 / 2, y0 - 1, y1 + 1, px, zc + dz)
    b = b - cyl_y(3.2 / 2, FAR_CHEEK_Y[0] - 1, FAR_CHEEK_Y[1] + 1, px, pz)   # the pivot pin
    b = b - _arm_swing()                                           # the arm's tail swings through it
    for a in BRACKET_SCREW_ANGLES:                                 # a pocket over the shroud's boss,
        b = b - _radial_span(r - 1, r + BOSS_OUT + P.CLEAR, a, pz, BOSS_D / 2 + P.CLEAR)
        b = b - _radial_span(r - 1, r + 20, a, pz, P.M3_CLEAR / 2)          # ... and the screw through it
    b = b - cyl_z(P.SHROUD_R_OUT + P.CLEAR, P.SHROUD_BASE_Z - 2, P.SHROUD_TOP_Z + 2)   # off the wall
    return b - _tilt_servo()


@part("nozzle_arm")
def nozzle_arm():
    """The lever on the micro servo's horn that swings the nozzle through the beard's parting.

    The tube pushes onto a barb behind the pivot, the water runs up the arm, and the brass
    nozzle presses into the bore at the tip. Drawn at rest; it swings TILT_STOP about the pivot.
    """
    px, pz = P.NOZZLE_PIVOT[0], P.NOZZLE_PIVOT[2]
    tip = px + P.NOZZLE_ARM_L
    a = box(px - TAIL, tip, -ARM_W / 2, ARM_W / 2, pz - ARM_T / 2, pz + ARM_T / 2)
    a = a + cyl_y(ARM_T / 2, -ARM_W / 2, ARM_W / 2, px, pz)                      # the hub, round
    a = a + cyl_x(BARB_D / 2, px - TAIL - 6.0, px - TAIL + 1, 0, pz)             # the tube's barb
    a = a - cyl_x(P.NOZZLE_D / 2, tip - 14.0, tip + 1, 0, pz)                    # the nozzle's press bore
    a = a - cyl_x(3.2 / 2, px - TAIL - 7.0, tip - 13.0, 0, pz)                   # the feed
    a = a - cyl_y(P.MICRO_HORN_D / 2 + P.CLEAR / 2, -ARM_W / 2 - 1, -ARM_W / 2 + 2.0, px, pz)   # horn pocket
    for dz in (-5.0, 5.0):                                                       # the horn's two M2
        a = a - cyl_y(2.4 / 2, -ARM_W / 2 - 1, ARM_W / 2 + 1, px, pz + dz)
    return a
