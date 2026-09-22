"""The neck: what the head stands on and what turns it."""
import math
from build123d import Sphere, Pos, Rot, RegularPolygon, SkipClean, Location, extrude, Axis
import params as P
from mech import part
from mech.common import cyl_z, cyl_y, box, insert_holes, servo_body


def _polar(r, deg, z):
    return (r * math.cos(math.radians(deg)), r * math.sin(math.radians(deg)), z)


def _crank_pin():
    """The plate's pin, relative to the pan axis; the servo's pin is the same vector from its axis."""
    a = math.radians(P.CRANK_REST_DEG)
    return P.CRANK_L * math.cos(a), P.CRANK_L * math.sin(a)


def _column_slot(z0, z1):
    """The arc the plate's hanging column swings in: the annulus r0..r1 within +/-half of +X.

    The deck and the ring below it are both in the column's way, so both are cut with this.
    """
    r0, r1, half = P.DECK_SLOT
    band = cyl_z(r1, z0, z1) - cyl_z(r0, z0 - 1, z1 + 1)
    ahead = box(0, r1 + 5, -(r1 + 5), r1 + 5, z0 - 1, z1 + 1)          # every point with x >= 0
    return band & ahead & ahead.rotate(Axis.Z, half - 90) & ahead.rotate(Axis.Z, 90 - half)


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
    for a in (45, 135, 225, 315):                                          # bearing screws
        x, y, _ = _polar(P.BEARING_PITCH / 2 * math.sqrt(2), a, 0)
        d = d - cyl_z(P.BEARING_HOLE / 2, z0 - 1, z1 + 1, x, y)
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
    d = d - box(sx - off - P.CLEAR, sx + (L - off) + P.CLEAR, sy - W / 2 - P.CLEAR, sy + W / 2 + P.CLEAR,
                P.Z_PAN_SHAFT_FACE - 1, P.Z_PAN_SHAFT_FACE + H + P.CLEAR)
    # hard-stop posts either side of the plate's front tab. They stop a hair below the plate's
    # top face, because the yoke's ring stands on that face and its feet sweep over them.
    half_tab = math.degrees(math.atan2(P.STOP_TAB_W / 2, P.PLATE_R))
    for sign in (1, -1):
        x, y, _ = _polar(P.STOP_POST_R, sign * (P.PAN_STOP_DEG + half_tab + math.degrees(math.atan2(P.STOP_POST_D / 2, P.STOP_POST_R))), 0)
        d = d + cyl_z(P.STOP_POST_D / 2, z1 - 0.01, P.Z_PLATE_TOP - P.CLEAR, x, y)
    return d


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
    for a in (45, 135, 225, 315):                                          # bearing's top ring
        x, y, _ = _polar(P.BEARING_PITCH / 2 * math.sqrt(2), a, 0)
        p = p - cyl_z(P.BEARING_HOLE / 2, z0 - 1, z1 + 1, x, y)
    p = p + box(P.PLATE_R - 1, P.STOP_POST_R + P.STOP_POST_D / 2 + 1, -P.STOP_TAB_W / 2, P.STOP_TAB_W / 2, z0, z1)  # stop tab, front
    # column from the stop tab's underside through the deck's slot, and the foot bar to the pin
    r_in, r_out, w = P.PAN_COLUMN
    p = p + box(r_in, r_out, -w / 2, w / 2, P.Z_CRANK_BOTTOM, z0 + 0.01)
    p = p + box(P.PAN_FOOT_R_IN, r_out, -w / 2, w / 2, P.Z_CRANK_BOTTOM, P.Z_CRANK_TOP)
    px, py = _crank_pin()
    p = insert_holes(p, [(px, py, P.Z_CRANK_BOTTOM)], depth=P.INSERT_DEPTH_SHORT, direction="up")   # blind in a 5 mm bar
    p = insert_holes(p, [_polar(P.YOKE_SCREW_R, a, z1) for a in P.YOKE_SCREW_ANGLES], depth=P.PLATE_T - 1)
    return p


@part("shaft")
def shaft():
    """Hollow, passive: bonded into the plate, turns inside the bearing's opening."""
    z1 = P.Z_PLATE_TOP + 6.0                 # proud of the plate for a flared lip
    z0 = P.Z_DECK - P.DECK_T - 40.0          # well below the deck so the tube's bend stays gentle
    s = cyl_z(P.SHAFT_OD / 2, z0, z1) - cyl_z(P.SHAFT_ID / 2, z0 - 1, z1 + 1)
    flare = cyl_z(P.SHAFT_OD / 2 + 3, z1 - 3, z1) - cyl_z(P.SHAFT_ID / 2, z1 - 4, z1 + 1)
    return s + flare


@part("servo_crank")
def servo_crank():
    """Hangs on the pan servo's horn, pocketed from above; carries the far pin of the parallelogram below."""
    z0, z1 = P.Z_CRANK_BOTTOM, P.Z_CRANK_TOP
    sx, sy = P.PAN_SERVO_XY
    dx, dy = _crank_pin()
    px, py = sx + dx, sy + dy
    arm = box(min(sx, px) - 4, max(sx, px) + 4, min(sy, py) - 4, max(sy, py) + 4, z0, z1)
    arm = arm + cyl_z(P.HORN_D / 2 + 3, z0, z1, sx, sy) + cyl_z(4, z0, z1, px, py)
    arm = arm - cyl_z(P.HORN_D / 2 + P.CLEAR / 2, z1 - P.HORN_T, z1 + 1, sx, sy)      # horn pocket from above
    for a in (0, 90, 180, 270):
        hx, hy, _ = _polar(P.HORN_SCREW_R, a, 0)
        arm = arm - cyl_z(P.M2_5_CLEAR / 2, z0 - 1, z1 + 1, sx + hx, sy + hy)
    arm = arm - cyl_z(2.5, z0 - 1, z1 + 1, sx, sy)                                     # horn's centre screw
    return insert_holes(arm, [(px, py, z0)], depth=P.INSERT_DEPTH_SHORT, direction="up")   # blind in a 5 mm crank


@part("pan_link")
def pan_link():
    """Joins the plate's pin to the servo crank's pin, below both. Eye-to-eye is the servo offset."""
    z0, z1 = P.Z_LINK_BOTTOM, P.Z_LINK_TOP
    (ax, ay), (bx, by) = _crank_pin(), (P.PAN_SERVO_XY[0] + _crank_pin()[0], P.PAN_SERVO_XY[1] + _crank_pin()[1])
    length = math.hypot(bx - ax, by - ay)
    ang = math.degrees(math.atan2(by - ay, bx - ax))
    bar = box(0, length, -3.0, 3.0, z0, z1).rotate(Axis.Z, ang).moved(Location((ax, ay, 0)))
    link = bar + cyl_z(P.LINK_EYE_R, z0, z1, ax, ay) + cyl_z(P.LINK_EYE_R, z0, z1, bx, by)
    return link - cyl_z(P.M3_CLEAR / 2, z0 - 1, z1 + 1, ax, ay) - cyl_z(P.M3_CLEAR / 2, z0 - 1, z1 + 1, bx, by)


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
    y = y - cyl_z(P.M3_CLEAR / 2, P.Z_HEAD - 1, P.Z_HEAD + P.YOKE_ARM_W / 2 + 1, 0, (y0 + y1) / 2)
    # -Y: pin bore and two stop pegs reaching inward to the ear's tab
    y0, y1 = _arm_y(-1)
    y = y - cyl_y(P.M4_PIN / 2 + 0.05, y0 - 1, y1 + 1, 0, P.Z_HEAD)
    peg_r = 2.5
    half = math.degrees(math.atan2(P.STOP_TAB_W / 2, P.TILT_STOP_TAB_R))
    peg_half = math.degrees(math.atan2(peg_r, P.TILT_STOP_TAB_R))
    for deg in P.TILT_STOP:
        # the tab hangs straight down (270°) at tilt 0; turning the head by +deg about +Y carries
        # it to 270 - deg. The peg's flank, not its centre, is what the tab lands on, so it sits
        # its own half-angle plus the tab's beyond the tab's rotated centre.
        a = 270.0 - deg - math.copysign(half + peg_half, deg)
        px = P.TILT_STOP_TAB_R * math.cos(math.radians(a))
        pz = P.Z_HEAD + P.TILT_STOP_TAB_R * math.sin(math.radians(a))
        y = y + cyl_y(peg_r, y1 - 0.01, -(P.HEAD_R + 1.0), px, pz)   # inward from the arm's inner face
    return y


@part("ear_boss", section="head_back")
def ear_boss():
    """-Y ear: fixed to the head, bored for the M4 pin, with the tilt stop tab. Unioned into the head."""
    y_out, y_in = -P.EAR_OUT_Y, -(P.HEAD_R - 10.0)
    boss = cyl_y(P.EAR_R, y_out, y_in, 0, P.Z_HEAD) - cyl_y(P.M4_PIN / 2 + 0.1, y_out - 1, y_in + 1, 0, P.Z_HEAD)
    tab = box(-P.STOP_TAB_W / 2, P.STOP_TAB_W / 2, y_out + 1, y_out + 5, P.Z_HEAD - P.TILT_STOP_TAB_R - 2, P.Z_HEAD)
    return boss + tab


@part("coupler")
def coupler():
    """+Y ear: the tilt servo's horn on the inside, a hex in the yoke arm on the outside."""
    y_horn = P.TILT_SERVO_SHAFT_Y
    y_arm0, y_arm1 = _arm_y(1)
    c = cyl_y(P.COUPLER_D / 2, y_horn, P.EAR_OUT_Y, 0, P.Z_HEAD)
    c = c + cyl_y(P.HORN_D / 2 + 3, y_horn, y_horn + P.HORN_T + 3, 0, P.Z_HEAD)   # boss around the horn pocket
    hexagon = Pos(0, (P.EAR_OUT_Y + y_arm1) / 2, P.Z_HEAD) * Rot(90, 0, 0) * extrude(RegularPolygon(P.COUPLER_HEX_AF / math.sqrt(3), 6), (y_arm1 - P.EAR_OUT_Y) / 2, both=True)
    c = c + hexagon
    c = c - cyl_y(P.HORN_D / 2 + P.CLEAR / 2, y_horn - 1, y_horn + P.HORN_T, 0, P.Z_HEAD)          # horn pocket
    for a in (0, 90, 180, 270):
        hx, hz, _ = _polar(P.HORN_SCREW_R, a, 0)
        c = c - cyl_y(P.M2_5_CLEAR / 2, y_horn - 1, y_horn + P.HORN_T + 8, hx, P.Z_HEAD + hz)
    c = c - cyl_z(P.M3_CLEAR / 2, P.Z_HEAD - 1, P.Z_HEAD + P.YOKE_ARM_W / 2 + 1, 0, (y_arm0 + y_arm1) / 2)  # cross screw
    return c


@part("tilt_bulkhead", section="head_back")
def tilt_bulkhead():
    """Chord plate inside the head the tilt servo's tabs screw to. Unioned into the back of the head.

    The MG996R's flange is 28 mm up its 42.9 mm body, so 28 mm of body hangs through a window
    in the plate and only the tabs land on its +Y face. The inserts therefore sit in bosses on
    the plate's -Y side, where the servo is not: they open at the +Y face, six millimetres deep,
    and stop a millimetre short of the boss's end.
    """
    y1 = P.BULKHEAD_Y
    y0 = y1 - P.BULKHEAD_T
    L, W, H = P.MG996R["body"]
    along, across = P.MG996R["holes"]
    z_top = P.Z_HEAD + P.MG996R["shaft_off"]
    zc = z_top - L / 2
    plate = box(-P.HEAD_R + 2, P.FACE_SPLIT_X - 1, y0, y1, zc - along / 2 - 8, zc + along / 2 + 8)
    with SkipClean():                      # tidying a sphere's boolean result corrupts it
        plate = plate & (Pos(0, 0, P.Z_HEAD) * Sphere(P.HEAD_R - P.WALL + 1.0))
    y_boss = y1 - P.INSERT_DEPTH - 1.0                                   # the insert's blind end
    holes = [(dx, zc + dz) for dx in (-across / 2, across / 2) for dz in (-along / 2, along / 2)]
    for hx, hz in holes:
        plate = plate + cyl_y(P.BULKHEAD_BOSS_D / 2, y_boss, y0 + 0.01, hx, hz)
    # the body drops through this window; it also trims the bosses, which reach 0.9 mm past its ends
    plate = plate - box(-W / 2 - P.CLEAR, W / 2 + P.CLEAR, y_boss - 1, y1 + 1,
                        P.Z_HEAD - (L - P.MG996R["shaft_off"]) - P.CLEAR, z_top + P.CLEAR)
    for hx, hz in holes:
        plate = plate - cyl_y(P.INSERT_D / 2, y1 - P.INSERT_DEPTH, y1 + 1, hx, hz)
    return plate


@part("head_lip", section="head_back")
def head_lip():
    """Ring inside the back of the head at the face split: the face cap seats on it."""
    r_out = P.HEAD_R - P.WALL - P.CLEAR
    band = box(P.FACE_SPLIT_X - P.FACE_LIP_L, P.FACE_SPLIT_X + P.FACE_LIP_L, -P.HEAD_R, P.HEAD_R, P.Z_HEAD - P.HEAD_R, P.Z_HEAD + P.HEAD_R)
    with SkipClean():                      # tidying a sphere's boolean result corrupts it
        shell = (Pos(0, 0, P.Z_HEAD) * Sphere(r_out)) - (Pos(0, 0, P.Z_HEAD) * Sphere(r_out - P.FACE_LIP_T))
        return shell & band
