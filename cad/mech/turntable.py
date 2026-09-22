"""The neck: what the head stands on and what turns it."""
import math
from build123d import Cylinder, Box, Pos, Rot, RegularPolygon, extrude, Plane, Axis
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
    # hard-stop posts either side of the plate's front tab
    half_tab = math.degrees(math.atan2(P.STOP_TAB_W / 2, P.PLATE_R))
    for sign in (1, -1):
        x, y, _ = _polar(P.STOP_POST_R, sign * (P.PAN_STOP_DEG + half_tab + math.degrees(math.atan2(P.STOP_POST_D / 2, P.STOP_POST_R))), 0)
        d = d + cyl_z(P.STOP_POST_D / 2, z1 - 0.01, P.Z_PLATE_TOP + 1, x, y)
    return d


@part("plate")
def plate():
    """The head's foundation: sits on the bearing, carries the shaft and the pan hard-stop tab.

    The crank pin post and the yoke arm feet are not built here: Task 3 appends the pan
    linkage, yoke and ears to this file, and adds them there. (The crank post would rise to
    Z_CRANK_TOP and the yoke feet sit at y in [EAR_OUT_Y + YOKE_GAP, ...], entirely outside
    PLATE_R, so neither belongs on this bearing-height disc yet.)
    """
    z0 = P.Z_DECK + P.BEARING_T
    z1 = P.Z_PLATE_TOP
    p = cyl_z(P.PLATE_R, z0, z1)
    p = p - cyl_z(P.SHAFT_OD / 2 + 0.1, z0 - 1, z1 + 1)                    # shaft bonds in here
    for a in (45, 135, 225, 315):                                          # bearing's top ring
        x, y, _ = _polar(P.BEARING_PITCH / 2 * math.sqrt(2), a, 0)
        p = p - cyl_z(P.BEARING_HOLE / 2, z0 - 1, z1 + 1, x, y)
    p = p + box(P.PLATE_R - 1, P.STOP_POST_R + P.STOP_POST_D / 2 + 1, -P.STOP_TAB_W / 2, P.STOP_TAB_W / 2, z0, z1)  # stop tab, front
    return p


@part("shaft")
def shaft():
    """Hollow, passive: bonded into the plate, turns inside the bearing's opening."""
    z1 = P.Z_PLATE_TOP + 6.0                 # proud of the plate for a flared lip
    z0 = P.Z_DECK - P.DECK_T - 40.0          # well below the deck so the tube's bend stays gentle
    s = cyl_z(P.SHAFT_OD / 2, z0, z1) - cyl_z(P.SHAFT_ID / 2, z0 - 1, z1 + 1)
    flare = cyl_z(P.SHAFT_OD / 2 + 3, z1 - 3, z1) - cyl_z(P.SHAFT_ID / 2, z1 - 4, z1 + 1)
    return s + flare
