"""The neck: what the head stands on and what turns it."""
import math
from build123d import Sphere, Pos, Rot, RegularPolygon, SkipClean, extrude, Axis
import params as P
from mech import part
from mech.common import cyl_z, cyl_y, box, insert_holes, servo_body


def _polar(r, deg, z):
    return (r * math.cos(math.radians(deg)), r * math.sin(math.radians(deg)), z)


def _notch(z0, z1):
    (x0, y0), (x1, y1) = P.PAN_NOTCH
    return box(x0, x1, y0, y1, z0, z1)


def _servo_tab_holes():
    L, W, H = P.DS3218["body"]
    along, across = P.DS3218["holes"]
    sx, sy = P.PAN_SERVO_XY
    cy = sy + P.DS3218["shaft_off"] - L / 2      # body centre along Y
    return [(sx + dx, cy + dy) for dx in (-across / 2, across / 2) for dy in (-along / 2, along / 2)]


@part("deck_ring", section="torso")
def deck_ring():
    """Narrow annulus the deck bolts to, joined to the shoulders' wall by four webs. Unioned into the torso.

    Narrow on purpose: the phone's top passes outside it (PHONE_FRONT_X > RING_R_OUT). Cut
    away around the pan servo, whose body hangs through it with its tab screws and nuts.
    """
    z1 = P.Z_DECK - P.DECK_T
    z0 = z1 - P.RING_T
    ring = cyl_z(P.RING_R_OUT, z0, z1) - cyl_z(P.RING_R_IN, z0 - 1, z1 + 1)
    r_wall = P.ring_r_out(P.TORSO_PROFILE, z0, z1)
    for a in P.DECK_SCREW_ANGLES:
        ring = ring + box(P.RING_R_OUT - 2, r_wall, -P.RING_WEB_W / 2, P.RING_WEB_W / 2, z0, z1).rotate(Axis.Z, a)
    (x0, y0), (x1, y1) = P.PAN_RING_CUT
    ring = ring - box(x0, x1, y0, y1, z0 - 1, z1 + 1)
    return insert_holes(ring, [_polar(P.DECK_SCREW_R, a, z1) for a in P.DECK_SCREW_ANGLES], depth=P.RING_T - 1)


@part("deck")
def deck():
    """Carries the bearing's fixed ring, the pan servo and the pan hard stops."""
    z1, z0 = P.Z_DECK, P.Z_DECK - P.DECK_T
    d = cyl_z(P.DECK_R, z0, z1)
    d = d - cyl_z(P.SHAFT_OD / 2 + P.CLEAR + 1.0, z0 - 1, z1 + 1)          # shaft passes with room
    for a in (45, 135, 225, 315):                                          # bearing screws
        x, y, _ = _polar(P.BEARING_PITCH / 2 * math.sqrt(2), a, 0)
        d = d - cyl_z(P.BEARING_HOLE / 2, z0 - 1, z1 + 1, x, y)
    for a in P.DECK_SCREW_ANGLES:                                          # down into the ring
        x, y, _ = _polar(P.DECK_SCREW_R, a, 0)
        d = d - cyl_z(P.M3_CLEAR / 2, z0 - 1, z1 + 1, x, y)
    d = d - _notch(z0 - 1, z1 + 1)                                         # pan servo body
    for x, y in _servo_tab_holes():                                        # tab screws, nut below
        d = d - cyl_z(P.M3_CLEAR / 2, z0 - 1, z1 + 1, x, y)
        d = d - Pos(x, y, z0 + P.NUT_M3_T / 2 - 0.01) * extrude(RegularPolygon(P.NUT_M3_AF / math.sqrt(3), 6), P.NUT_M3_T)
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

    It also carries the pan linkage's near pin post, which rises from the disc to
    Z_CRANK_TOP with an insert in its top, and the four inserts the yoke's ring screws
    down into. The yoke's arm feet themselves are part of the yoke, not of this disc.
    """
    z0 = P.Z_DECK + P.BEARING_T
    z1 = P.Z_PLATE_TOP
    p = cyl_z(P.PLATE_R, z0, z1)
    p = p - cyl_z(P.SHAFT_OD / 2 + 0.1, z0 - 1, z1 + 1)                    # shaft bonds in here
    for a in (45, 135, 225, 315):                                          # bearing's top ring
        x, y, _ = _polar(P.BEARING_PITCH / 2 * math.sqrt(2), a, 0)
        p = p - cyl_z(P.BEARING_HOLE / 2, z0 - 1, z1 + 1, x, y)
    p = p + box(P.PLATE_R - 1, P.STOP_POST_R + P.STOP_POST_D / 2 + 1, -P.STOP_TAB_W / 2, P.STOP_TAB_W / 2, z0, z1)  # stop tab, front
    # crank pin post, in the band above the plate; the yoke's ring screws
    px, py = P.CRANK_L * math.cos(math.radians(P.CRANK_REST_DEG)), P.CRANK_L * math.sin(math.radians(P.CRANK_REST_DEG))
    p = p + cyl_z(P.PIN_POST_D / 2, z1 - 0.01, P.Z_CRANK_TOP, px, py)
    p = insert_holes(p, [(px, py, P.Z_CRANK_TOP)])
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


def _crank_pin():
    a = math.radians(P.CRANK_REST_DEG)
    return P.CRANK_L * math.cos(a), P.CRANK_L * math.sin(a)


@part("servo_crank")
def servo_crank():
    """Bolts to the pan servo's round horn; carries the far pin of the parallelogram."""
    z0, z1 = P.Z_SERVO_HORN_TOP, P.Z_CRANK_TOP
    sx, sy = P.PAN_SERVO_XY
    dx, dy = _crank_pin()
    px, py = sx + dx, sy + dy
    arm = box(min(sx, px) - 4, max(sx, px) + 4, min(sy, py) - 4, max(sy, py) + 4, z0, z1)
    arm = arm + cyl_z(P.HORN_D / 2 + 3, z0, z1, sx, sy) + cyl_z(4, z0, z1, px, py)
    arm = arm - cyl_z(P.HORN_D / 2 + P.CLEAR / 2, z0 - 1, z0 + P.HORN_T, sx, sy)      # horn pocket from below
    for a in (0, 90, 180, 270):
        hx, hy, _ = _polar(P.HORN_SCREW_R, a, 0)
        arm = arm - cyl_z(P.M2_5_CLEAR / 2, z0 - 1, z1 + 1, sx + hx, sy + hy)
    arm = arm - cyl_z(2.5, z0 - 1, z1 + 1, sx, sy)                                     # horn's centre screw
    return insert_holes(arm, [(px, py, z1)])


@part("pan_link")
def pan_link():
    """Joins the plate's pin to the servo crank's pin. Eye-to-eye length is the centre distance."""
    z0, z1 = P.Z_CRANK_TOP, P.Z_LINK_TOP
    ax, ay = _crank_pin()
    bx, by = ax - P.PAN_OFFSET, ay
    bar = box(bx, ax, ay - 3.0, ay + 3.0, z0, z1)
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
    """Chord plate inside the head the tilt servo's tabs screw to. Unioned into the back of the head."""
    y1 = P.BULKHEAD_Y
    y0 = y1 - P.BULKHEAD_T
    L, W, H = P.MG996R["body"]
    along, across = P.MG996R["holes"]
    z_top = P.Z_HEAD + P.MG996R["shaft_off"]
    zc = z_top - L / 2
    plate = box(-P.HEAD_R + 2, P.FACE_SPLIT_X - 1, y0, y1, zc - along / 2 - 8, zc + along / 2 + 8)
    with SkipClean():                      # tidying a sphere's boolean result corrupts it
        plate = plate & (Pos(0, 0, P.Z_HEAD) * Sphere(P.HEAD_R - P.WALL + 1.0))
    for dx in (-across / 2, across / 2):
        for dz in (-along / 2, along / 2):
            plate = plate - cyl_y(P.INSERT_D / 2, y1 - P.INSERT_DEPTH, y1 + 1, dx, zc + dz)
    return plate


@part("head_lip", section="head_back")
def head_lip():
    """Ring inside the back of the head at the face split: the face cap seats on it."""
    r_out = P.HEAD_R - P.WALL - P.CLEAR
    band = box(P.FACE_SPLIT_X - P.FACE_LIP_L, P.FACE_SPLIT_X + P.FACE_LIP_L, -P.HEAD_R, P.HEAD_R, P.Z_HEAD - P.HEAD_R, P.Z_HEAD + P.HEAD_R)
    with SkipClean():                      # tidying a sphere's boolean result corrupts it
        shell = (Pos(0, 0, P.Z_HEAD) * Sphere(r_out)) - (Pos(0, 0, P.Z_HEAD) * Sphere(r_out - P.FACE_LIP_T))
        return shell & band
