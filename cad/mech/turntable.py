"""The neck: what the head stands on and what turns it."""
import math
from build123d import (Sphere, Pos, Rot, Plane, Polygon, RegularPolygon, SkipClean, Location,
                       extrude, revolve, Axis)
import params as P
from mech import part
from mech.common import cyl_z, cyl_y, box, insert_holes, polar, servo_body


def _polar(r, deg, z):
    """polar() with the height this module's insert_holes calls want."""
    return (*polar(r, deg), z)


def _bearing_holes(part, z0, z1):
    """The lazy susan's four screws, on the diagonal of its bolt square."""
    for a in (45, 135, 225, 315):
        x, y, _ = _polar(P.BEARING_PITCH / 2 * math.sqrt(2), a, 0)
        part = part - cyl_z(P.BEARING_HOLE / 2, z0, z1, x, y)
    return part


def _in_wall():
    """Interface parts are clipped to this: 1.2 mm into the head's wall, never through it."""
    return Pos(0, 0, P.Z_HEAD) * Sphere(P.HEAD_R - P.WALL + 1.2)


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
    d = cyl_z(P.DECK_R, z0, z1)
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


def _arm_y(sy):
    y_in = sy * (P.EAR_OUT_Y + P.YOKE_GAP)
    y_out = y_in + sy * P.YOKE_ARM_T
    return min(y_in, y_out), max(y_in, y_out)


@part("yoke")
def yoke():
    """Ring on the plate's rim with two arms. +Y holds the coupler's hex; -Y takes the M4 pin and the tilt stop pegs."""
    z0 = P.Z_PLATE_TOP
    z1 = z0 + P.YOKE_RING_T
    y = cyl_z(P.PLATE_R, z0, z1) - cyl_z(P.YOKE_RING_R_IN, z0 - 1, z1 + 1)
    for a in P.YOKE_SCREW_ANGLES:
        px, py, _ = _polar(P.YOKE_SCREW_R, a, 0)
        y = y - cyl_z(P.M3_CLEAR / 2, z0 - 1, z1 + 1, px, py)
    for sy in (1, -1):
        y0, y1 = _arm_y(sy)
        foot = box(-P.YOKE_ARM_W / 2, P.YOKE_ARM_W / 2, min(sy * P.YOKE_RING_R_IN, y0), max(sy * P.YOKE_RING_R_IN, y1), z0, z1)
        arm = box(-P.YOKE_ARM_W / 2, P.YOKE_ARM_W / 2, y0, y1, z1 - 0.01, P.Z_HEAD) + cyl_y(P.YOKE_ARM_W / 2, y0, y1, 0, P.Z_HEAD)
        y = y + foot + arm
    # +Y: hex pocket for the coupler, locked by a cross screw
    y0, y1 = _arm_y(1)
    hexagon = Pos(0, (y0 + y1) / 2, P.Z_HEAD) * Rot(90, 0, 0) * extrude(RegularPolygon(P.COUPLER_HEX_AF / math.sqrt(3) + P.CLEAR / 2, 6), P.YOKE_ARM_T + 2, both=True)
    y = y - hexagon
    # the cross screw threads into an insert in the arm's top and its tip enters the coupler's
    # hole. A short insert: a six would break into the hex pocket, whose top is 1.35 mm below it.
    cy, top = (y0 + y1) / 2, P.Z_HEAD + P.YOKE_ARM_W / 2
    y = insert_holes(y, [(0, cy, top)], depth=P.INSERT_DEPTH_SHORT)
    y = y - cyl_z(P.M3_CLEAR / 2, P.Z_HEAD - 1, top - P.INSERT_DEPTH_SHORT + 0.01, 0, cy)
    # -Y: the M4 bolt's clearance hole, which is the tilt bearing, and two stop pegs
    y0, y1 = _arm_y(-1)
    y = y - cyl_y(P.M4_PIN / 2 + 0.1, y0 - 1, y1 + 1, 0, P.Z_HEAD)
    peg_r = 2.5
    # the peg's centre must clear the tab's flank by its own radius, so at TILT_STOP_TAB_R it sits
    # asin((half the tab + the peg) / r) round from the tab's centre line: tangent at the stop
    offset = math.degrees(math.asin((P.STOP_TAB_W / 2 + peg_r) / P.TILT_STOP_TAB_R))
    for deg in P.TILT_STOP:
        # the tab hangs straight down (270 deg) at tilt 0. Positive tilt is nose up, which carries
        # a point at angle phi to phi + deg, so the peg sits beyond the tab's rotated centre in the
        # direction it travels.
        a = 270.0 + deg + math.copysign(offset, deg)
        px = P.TILT_STOP_TAB_R * math.cos(math.radians(a))
        pz = P.Z_HEAD + P.TILT_STOP_TAB_R * math.sin(math.radians(a))
        y = y + cyl_y(peg_r, y1 - 0.01, -(P.HEAD_R + 1.0), px, pz)   # inward from the arm's inner face
    return y


def _offset(p, q, d):
    """The segment p->q shifted d to its left: for this profile, into the shroud's cavity."""
    dr, dz = q[0] - p[0], q[1] - p[1]
    n = math.hypot(dr, dz)
    nr, nz = -dz / n, dr / n
    return (p[0] + d * nr, p[1] + d * nz), (q[0] + d * nr, q[1] + d * nz)


def _meet(a, b, c, d):
    """Where the line through a, b crosses the line through c, d."""
    (ar, az), (br, bz), (cr, cz), (dr_, dz_) = a, b, c, d
    u, v = (br - ar, bz - az), (dr_ - cr, dz_ - cz)
    det = u[0] * v[1] - u[1] * v[0]
    t = ((cr - ar) * v[1] - (cz - az) * v[0]) / det
    return (ar + t * u[0], az + t * u[1])


def _shroud_faces():
    """The shroud's outer path and the inner face of its wall, both bottom to top, as (r, z).

    The path the brief names - base ring, cone out, cylinder, cone in - is the OUTER surface,
    and the wall lies WALL inside it. The skirt is shallow enough that its inner surface runs
    into the base ring rather than onto its top face, which is why the base is thicker than
    three millimetres at its rim; the screws' counterbores are sunk to leave exactly three.
    """
    a1 = (P.PLATE_R, P.SHROUD_BASE_Z)
    a2 = (P.PLATE_R, P.SHROUD_BASE_Z + 3.0)
    a3 = (P.SHROUD_R_OUT, P.SHROUD_SKIRT_Z)
    a4 = (P.SHROUD_R_OUT, P.SHROUD_SHOULDER_Z)
    a5 = (P.SHROUD_TOP_R, P.SHROUD_TOP_Z)
    l1 = _offset(a2, a3, P.WALL)                       # skirt cone, inner face
    l2 = _offset(a3, a4, P.WALL)                       # cylinder, inner face
    l3 = _offset(a4, a5, P.WALL)                       # top cone, inner face
    b5 = l3[1]
    b4 = _meet(*l3, *l2)
    b3 = _meet(*l2, *l1)
    t = (P.YOKE_RING_R_IN - l1[0][0]) / (l1[1][0] - l1[0][0])
    b2 = (P.YOKE_RING_R_IN, l1[0][1] + t * (l1[1][1] - l1[0][1]))
    return [(P.YOKE_RING_R_IN, P.SHROUD_BASE_Z), a1, a2, a3, a4, a5], [b2, b3, b4, b5]


def _shroud_profile():
    """The wall as a closed (r, z) loop: up the outside, round the rolled rim, down the inside."""
    outer, inner = _shroud_faces()
    a5, b5 = outer[-1], inner[-1]
    mid = ((a5[0] + b5[0]) / 2, (a5[1] + b5[1]) / 2)
    rad = math.hypot(a5[0] - mid[0], a5[1] - mid[1])
    start = math.atan2(a5[1] - mid[1], a5[0] - mid[0])
    roll = [(mid[0] + rad * math.cos(start + i * math.pi / 6),
             mid[1] + rad * math.sin(start + i * math.pi / 6)) for i in range(1, 6)]
    return [*outer, *roll, *reversed(inner)]


def jet_axis(deg):
    """Where the jet leaves the mouth and which way it points, in (r, z), at a tilt of `deg`.

    Positive is nose up, the machine's convention. The mouth is on the head's sphere, so its
    x comes from HEAD_R and the mouth's drop below the tilt axis.
    """
    x0 = math.sqrt(P.HEAD_R ** 2 - (P.Z_HEAD - P.Z_MOUTH) ** 2)
    dz = P.Z_MOUTH - P.Z_HEAD
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return (x0 * c - dz * s, P.Z_HEAD + x0 * s + dz * c), (c, s)


def jet_notch_z():
    """How low the shroud's front notch has to reach.

    At the nose-down stop the jet leaves at that angle and crosses the shroud's inner face low
    on the skirt; the notch starts half the jet's width and a two millimetre margin below it.
    """
    (px, pz), (dx, dz) = jet_axis(P.TILT_STOP[0])
    inner = _shroud_faces()[1]
    hits = []
    for (qr, qz), (rr, rz) in zip(inner, inner[1:]):
        det = dx * (qz - rz) - dz * (qr - rr)
        if abs(det) < 1e-12:
            continue
        t = ((qr - px) * (qz - rz) - (qz - pz) * (qr - rr)) / det
        u = (dx * (qz - pz) - dz * (qr - px)) / det
        if t > 0 and -1e-9 <= u <= 1 + 1e-9:
            hits.append(pz + t * dz)
    return min(hits) - P.JET_D / 2 - 2.0


def _jet_notch():
    """The wedge through the shroud's front that the jet passes down, open at the top."""
    half, far = P.JET_NOTCH_HALF_DEG, P.SHROUD_R_OUT + 5.0
    ahead = box(0, far, -far, far, jet_notch_z(), P.SHROUD_TOP_Z + 5.0)
    return ahead.rotate(Axis.Z, half - 90) & ahead.rotate(Axis.Z, 90 - half)


def _arm_slots():
    """The channels the yoke's arms travel down as the shroud is lowered onto the ring.

    A straight prism of the arm's section: the arms cross the skirt as well as the top cone,
    so the slot runs the shroud's whole height, open at the top.
    """
    w = P.YOKE_ARM_W / 2 + P.CLEAR
    cut = None
    for sy in (1, -1):
        y0, y1 = _arm_y(sy)
        band = box(-w, w, y0 - P.CLEAR, y1 + P.CLEAR, P.SHROUD_BASE_Z - 1, P.SHROUD_TOP_Z + 5)
        cut = band if cut is None else cut + band
    return cut


@part("neck_shroud")
def neck_shroud():
    """Turns with the head, hiding the yoke inside the collar and closing the gap around the head.

    A body of revolution on the yoke's ring, held by the same four screws: base ring, a skirt
    out to SHROUD_R_OUT clear of the arms, a cylinder up past the collar's rim, then a cone in
    to a rolled rim SHROUD_TOP_R from the pan axis, a few millimetres off the head.
    """
    s = revolve(Plane.XZ * Polygon(*_shroud_profile()), axis=Axis.Z)
    s = s - _arm_slots() - _jet_notch()
    head_d = P.M3_CLEAR + 2.6                                  # an M3 socket head is 5.5 across
    for a in P.YOKE_SCREW_ANGLES:
        x, y = polar(P.YOKE_SCREW_R, a)
        s = s - cyl_z(P.M3_CLEAR / 2, P.SHROUD_BASE_Z - 1, P.SHROUD_BASE_Z + 6, x, y)
        s = s - cyl_z(head_d / 2, P.SHROUD_BASE_Z + 3.0, P.SHROUD_BASE_Z + 8, x, y)   # head, 3 mm of base left
    return s


@part("ear_boss", section="head_back")
def ear_boss():
    """-Y ear: fixed to the head, with an M4 insert the tilt bolt threads into, and the stop tab.

    The bolt comes from outside through the arm's clearance hole, which is the bearing, and
    threads into the insert here; its head stays outside the arm where a driver can reach it.
    """
    y_out, y_in = -P.EAR_OUT_Y, -(P.HEAD_R - 10.0)
    boss = cyl_y(P.EAR_R, y_out, y_in, 0, P.Z_HEAD)
    tab = box(-P.STOP_TAB_W / 2, P.STOP_TAB_W / 2, y_out + 1, y_out + 5, P.Z_HEAD - P.TILT_STOP_TAB_R - 2, P.Z_HEAD)
    # drilled last: the tab reaches across the bore's mouth, so it has to be there to be cut
    return (boss + tab) - cyl_y(P.INSERT_M4_D / 2, y_out - 1, y_out + P.INSERT_M4_DEPTH, 0, P.Z_HEAD)


@part("coupler")
def coupler():
    """+Y ear: a plain shaft on the servo's horn inside, a hex in the yoke's arm outside.

    No boss and no horn pocket, so nothing on it is wider than the wall bore. Its inner face
    lands on the horn's outer face; the two horn screws drop down counterbores that a driver
    reaches from the hex end, and a recess clears the horn's own centre screw.
    """
    y_in = P.TILT_SERVO_SHAFT_Y + P.HORN_T                     # the horn's outer face
    y_arm0, y_arm1 = _arm_y(1)
    c = cyl_y(P.COUPLER_D / 2, y_in, P.EAR_OUT_Y, 0, P.Z_HEAD)
    c = c + Pos(0, (P.EAR_OUT_Y + y_arm1) / 2, P.Z_HEAD) * Rot(90, 0, 0) * extrude(
        RegularPolygon(P.COUPLER_HEX_AF / math.sqrt(3), 6), (y_arm1 - P.EAR_OUT_Y) / 2, both=True)
    c = c - cyl_y(5.0 / 2, y_in - 0.01, y_in + 1.5, 0, P.Z_HEAD)          # the horn's centre screw head
    for a in P.HORN_SCREWS_USED:
        hx, hz, _ = _polar(P.HORN_SCREW_R, a, 0)
        c = c - cyl_y(P.HORN_ACCESS_D / 2, y_in + 2.0, y_arm1 + 1, hx, P.Z_HEAD + hz)   # driver bore
        c = c - cyl_y(P.M2_5_CLEAR / 2, y_in - 1, y_in + 2.01, hx, P.Z_HEAD + hz)       # the screw itself
    c = c - cyl_z(P.M3_CLEAR / 2, P.Z_HEAD - 1, P.Z_HEAD + P.YOKE_ARM_W / 2 + 1, 0, (y_arm0 + y_arm1) / 2)  # cross screw
    return c


def _tilt_servo():
    """The tilt servo where it sits in the head. Everything the cradle needs is read off it."""
    return servo_body(P.MG996R, (0, P.TILT_SERVO_SHAFT_Y, P.Z_HEAD), axis="y")


def _tab_holes():
    """The tilt servo's four tab holes as (x, z), straddling the body's centre along its length."""
    along, across = P.MG996R["holes"]
    bb = _tilt_servo().bounding_box()
    zc = (bb.min.Z + bb.max.Z) / 2
    return [(dx, zc + dz) for dx in (-across / 2, across / 2) for dz in (-along / 2, along / 2)]


def _cradle_channel():
    """The slot the cradle plate slides in: its y faces with CLEAR either side."""
    return P.BULKHEAD_Y - P.BULKHEAD_T - P.CLEAR, P.BULKHEAD_Y + P.CLEAR


def _boss_sweep():
    """The band the cradle's -Y insert bosses travel through, all the way in and out.

    They stand proud of the plate's back face and reach into the z the rails grip, so the
    rails' -Y lips are relieved along their path; the +Y lips and the floor are untouched.
    """
    _, across = P.MG996R["holes"]
    r = P.BULKHEAD_BOSS_D / 2
    sweep = None
    for hz in sorted({z for _, z in _tab_holes()}):
        band = box(-across / 2 - r - P.CLEAR, P.HEAD_R + 40.0,
                   P.BULKHEAD_Y - P.INSERT_DEPTH - 1.0 - P.CLEAR, P.BULKHEAD_Y - P.BULKHEAD_T + 0.05,
                   hz - r - P.CLEAR, hz + r + P.CLEAR)
        sweep = band if sweep is None else sweep + band
    return sweep


@part("tilt_cradle")
def tilt_cradle():
    """The tilt servo's plate, assembled with it on the bench and slid into the head's rails.

    The MG996R's flange is 28 mm along its 42.9 mm body, so most of the body passes through a
    window and only the tabs land on the +Y face. The inserts are in bosses on the -Y side, where the
    servo is not: they open at the +Y face, six millimetres deep, and stop a millimetre short.
    A plain rectangle - it is a loose part, not part of the shell.
    """
    y1 = P.BULKHEAD_Y
    y0 = y1 - P.BULKHEAD_T
    bb = _tilt_servo().bounding_box()
    plate = box(P.CRADLE_X[0], P.CRADLE_X[1], y0, y1, P.CRADLE_Z[0], P.CRADLE_Z[1])
    y_boss = y1 - P.INSERT_DEPTH - 1.0                                   # the insert's blind end
    for hx, hz in _tab_holes():
        plate = plate + cyl_y(P.BULKHEAD_BOSS_D / 2, y_boss, y0 + 0.01, hx, hz)
    # the body passes through this window; it also trims the bosses, which reach past its ends
    plate = plate - box(bb.min.X - P.CLEAR, bb.max.X + P.CLEAR, y_boss - 1, y1 + 1,
                        bb.min.Z - P.CLEAR, bb.max.Z + P.CLEAR)
    for hx, hz in _tab_holes():
        plate = plate - cyl_y(P.INSERT_D / 2, y1 - P.INSERT_DEPTH, y1 + 1, hx, hz)
    return plate


@part("cradle_rails", section="head_back")
def cradle_rails():
    """Two channels along X on the back of the head that the tilt cradle slides into.

    The plate goes in bottom edge first behind the lower rail's front lip, then swings up into
    the upper rail, which is two millimetres deeper than it needs so it can. A back wall stops
    it at home and ties the two rails into one piece. Everything is clipped into the wall.
    """
    c0, c1 = _cradle_channel()
    lo, hi = c0 - P.RAIL_T, c1 + P.RAIL_T
    x_back, x_front = -(P.HEAD_R + 20.0), P.CRADLE_X[1]      # the sphere clips the back
    zb, zt = P.CRADLE_Z
    r = box(x_back, x_front, lo, c0, zb - P.RAIL_H, zb + 3.0)            # lower -Y lip
    r = r + box(x_back, x_front, c1, hi, zb - P.RAIL_H, zb + 3.0)        # lower +Y lip
    r = r + box(x_back, x_front, lo, hi, zb - P.RAIL_H, zb)              # floor, under the bottom edge
    r = r + box(x_front, x_front + P.RAIL_LIP_L, lo, hi, zb - P.RAIL_H, zb + 3.0)   # front lip
    r = r + box(x_back, x_front, lo, c0, zt - 3.0, zt + P.RAIL_H)        # upper -Y lip
    r = r + box(x_back, x_front, c1, hi, zt - 3.0, zt + P.RAIL_H)        # upper +Y lip
    r = r + box(x_back, x_front, lo, hi, zt + 2.0, zt + P.RAIL_H)        # ceiling, 2 mm of swing room
    r = r + box(x_back, P.CRADLE_X[0], lo, hi, zb - P.RAIL_H, zt + P.RAIL_H)        # back wall
    r = r - _boss_sweep()
    return r & _in_wall()


def _lip_band(grow=0.0):
    """The spherical band the face cap seats on, straddling the split.

    Behind the split it is body, reaching 1.2 mm into the wall like every other interface part,
    so it welds to the head's back half instead of floating inside it. In front of the split the
    cap slides over it, so there it stops CLEAR short of the cap's inner face. `grow` inflates
    the whole ring into a clearance cutter.
    """
    r_in = P.HEAD_R - P.WALL - P.CLEAR - P.FACE_LIP_T - grow
    core = Pos(0, 0, P.Z_HEAD) * Sphere(r_in)

    def band(r, x0, x1):
        window = box(x0, x1, -P.HEAD_R, P.HEAD_R, P.Z_HEAD - P.HEAD_R, P.Z_HEAD + P.HEAD_R)
        return ((Pos(0, 0, P.Z_HEAD) * Sphere(r)) - core) & window

    with SkipClean():                      # build123d corrupts a sphere's boolean when it tidies it
        back = band(P.HEAD_R - P.WALL + 1.2 + grow, P.FACE_SPLIT_X - P.FACE_LIP_L - grow, P.FACE_SPLIT_X)
        front = band(P.HEAD_R - P.WALL - P.CLEAR + grow, P.FACE_SPLIT_X, P.FACE_SPLIT_X + P.FACE_LIP_L + grow)
        return back + front


@part("face_stop", section="face")
def face_stop():
    """Block on the face cap that bears on the cradle's front edge and boxes it in."""
    b = box(P.CRADLE_X[1] + P.CLEAR, P.HEAD_R, P.BULKHEAD_Y - P.BULKHEAD_T - 2.0, P.BULKHEAD_Y + 2.0,
            P.FACE_STOP_Z[0], P.FACE_STOP_Z[1])
    return (b & _in_wall()) - _lip_band(P.CLEAR)         # the lip is on the back half; keep clear of it


@part("head_lip", section="head_back")
def head_lip():
    """Ring inside the back of the head at the face split: the face cap seats on it."""
    return _lip_band()
