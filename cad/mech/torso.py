"""The dry zone: the belt joint, the belly hatch, and everything that hangs off the chassis.

The coat's front between the belt and the shoulders is a screwed-on panel. Everything dry-side
goes in and out through that opening: the chassis bolts to the torso flange through it, the
phone sled slides out of it along +X, and the electronics deck's screws are driven down through
it. What lives here are the two interface parts around the opening and the parts behind it.
"""
import math
from build123d import Axis, Plane, Polygon, revolve
import params as P
from mech import part
from mech.common import box, cyl_x, cyl_z, insert_holes, polar, skin_solid

# --- numbers this module chooses, which params does not ----------------------------------
CHASSIS_BORE_R = 18.0        # two lightening bores beside the deck, in the chassis's free lunes
CHASSIS_BORE_Y = 62.0        # ... on the centreline's flanks, clear of the deck and the sled
CHASSIS_VENT_R = 15.0        # a third bore between the deck's back edge and the sled's path
CHASSIS_VENT_X = 42.0
GLAND_BORE_R = 7.0           # wiring holes over the divider's glands: a 14 mm hole per bundle
BEAD_GROOVE = (1.3, 3.3)     # the bead groove's edges, in from the divider's rim
SLED_LOCK_X = 56.0           # the sled's two lock screws, behind everything else it carries
SLED_FOOT_Y = 20.0           # ... either side of the phone's centreline
SLED_FOOT_L = 10.0           # the feet's length in x, from the tray's back wall
SLED_OPEN_TOP = 20.0         # the tray's walls stop this far below the phone's top
SLED_KEY_OVERRUN = 6.0       # the key finger runs this far past the flipped camera
SLED_LIP_TOP = 30.0          # the back lip stops this far above the phone's bottom
BOSS_R = 5.5                 # the chassis's bosses round a blind M3 insert
STANDOFF_R = 4.0
ESP32_RAIL_T = 2.4           # the cradle's rails either side of the devkit
ESP32_RAIL_H = 4.0
TIE_SLOT_W = 3.0             # cable-tie slots


def _wedge(half_deg, z0, z1, r=220.0):
    """The solid wedge |atan2(y, x)| < half_deg between z0 and z1."""
    ahead = box(0, r, -r, r, z0, z1)
    return ahead & ahead.rotate(Axis.Z, half_deg - 90) & ahead.rotate(Axis.Z, 90 - half_deg)


def _edeck(points):
    """EDECK_HOLES or EDECK_POSTS in absolute x-y: the deck and the chassis both want them.

    Three screws and two posts, not four screws: see the note on EDECK_HOLES in params.
    """
    ex, ey = P.EDECK_POS
    return [(ex + x, ey + y) for x, y in points]


def _window_prism():
    """Everything behind the camera window's opening in the panel."""
    y = P.CAM_Y
    z = P.Z_LENS + P.WINDOW_Z_BIAS
    return box(0.0, 220.0, y - P.WINDOW_W / 2, y + P.WINDOW_W / 2, z - P.WINDOW_H / 2, z + P.WINDOW_H / 2)


def _sled_locks():
    """Plan positions of the sled's two lock screws, shared with the chassis."""
    return [(SLED_LOCK_X, P.PHONE_Y_OFFSET + dy) for dy in (-SLED_FOOT_Y, SLED_FOOT_Y)]


def _sled_envelope(grow=0.0):
    """Everything the sled and the phone in it sweep as the sled slides +X out of the hatch.

    Three boxes rather than the parts themselves: the tray up to its top, the phone above that,
    and the feet and lock lugs behind both. Anything fixed that this touches would stop the sled.
    """
    yc, w, out = P.PHONE_Y_OFFSET, P.SLED_WALL, 220.0
    y0 = yc - P.PHONE_W / 2 - w - grow
    y1 = yc + P.PHONE_W / 2 + P.CLEAR + w + grow
    z_floor = P.Z_CHASSIS + P.CHASSIS_T - grow
    tray = box(P.PHONE_FRONT_X - w - grow, out, y0, y1, z_floor, P.PHONE_BOTTOM_Z + P.PHONE_L - SLED_OPEN_TOP + grow)
    phone = box(P.PHONE_FRONT_X - grow, out, yc - P.PHONE_W / 2 - grow, yc + P.PHONE_W / 2 + P.CLEAR + grow,
                P.PHONE_BOTTOM_Z - grow, P.PHONE_BOTTOM_Z + P.PHONE_L + grow)
    feet = box(SLED_LOCK_X - BOSS_R - grow, out, -SLED_FOOT_Y - 5 - grow, SLED_FOOT_Y + 5 + grow,
               z_floor, z_floor + P.SLED_FOOT_H + 4 + grow)
    return tray + phone + feet


@part("belt_flange_lower", section="base")
def belt_flange_lower():
    """Ring inside the base's rim with the inserts the belt screws go into.

    Sixteen millimetres tall, and the base flares over that height, so a straight ring sized at
    its narrowest would stand off the wall everywhere but its top. It is revolved from a profile
    instead: the outer edge follows ring_r_out height by height and meets the wall all the way
    down, the inner edge stands at FLANGE_R_IN. The insert bore is a millimetre deeper than the
    insert so an M3 x 20 - the nearest stock length to the stack - cannot bottom in it.
    """
    z1 = P.Z_BELT
    z0 = z1 - 2 * P.RING_T
    heights = (z0, z0 + 4, z0 + 8, z0 + 12, z1)
    outer = [(P.ring_r_out(P.BASE_PROFILE, z, z), z) for z in heights]
    section = Plane.XZ * Polygon((P.FLANGE_R_IN, z0), *outer, (P.FLANGE_R_IN, z1))
    ring = revolve(section, axis=Axis.Z)
    return insert_holes(ring, [(*polar(P.FLANGE_SCREW_R, a), z1) for a in P.FLANGE_SCREW_ANGLES],
                        depth=P.INSERT_DEPTH + 3)


@part("belt_flange_upper", section="torso")
def belt_flange_upper():
    """Ring inside the torso's skirt: belt screws pass down through it, chassis screws go into its top.

    The counterbore is half a millimetre deeper than a cheese head, so the chassis lands on the
    ring and not on four screw heads.
    """
    z0 = P.Z_BASE_TOP
    z1 = z0 + P.RING_T
    r_out = P.ring_r_out(P.TORSO_PROFILE, z0, z1)
    ring = cyl_z(r_out, z0, z1) - cyl_z(P.FLANGE_R_IN, z0 - 1, z1 + 1)
    for a in P.FLANGE_SCREW_ANGLES:
        x, y = polar(P.FLANGE_SCREW_R, a)
        ring = ring - cyl_z(P.M3_CLEAR / 2, z0 - 1, z1 + 1, x, y)
        ring = ring - cyl_z(3.2, z1 - (P.SCREW_HEAD_H + 0.5), z1 + 1, x, y)
    return insert_holes(ring, [(*polar(P.CHASSIS_SCREW_R, a), z1) for a in P.CHASSIS_SCREW_ANGLES])


@part("divider")
def divider():
    """The base's lid: slices at 100 % infill. Two glands, a bead groove, four belt-screw holes.

    Its top stands DIVIDER_PROUD above the base's rim. Both stacks used to land on 238.000 and
    the bead sealed only if they did; now the torso's flange always meets the divider first and
    the belt screws squeeze the bead rather than the rim.
    """
    z0, z1 = P.Z_BELT, P.Z_BASE_TOP + P.DIVIDER_PROUD
    r = P.shell_r(P.BASE_PROFILE, z0) - P.WALL - P.CLEAR
    d = cyl_z(r, z0, z1)
    # groove for the PU bead, in the face the torso's flange lands on. It runs outboard of the
    # belt screws: a bead the screw holes cut through would not seal.
    g_out, g_in = BEAD_GROOVE
    d = d - (cyl_z(r - g_out, z1 - 1.5, z1 + 1) - cyl_z(r - g_in, z1 - 2, z1 + 2))
    for a in P.FLANGE_SCREW_ANGLES:
        d = d - cyl_z(P.M3_CLEAR / 2, z0 - 1, z1 + 1, *polar(P.FLANGE_SCREW_R, a))
    for x, y in P.GLAND_POS:
        d = d - cyl_z(P.GLAND_D / 2, z0 - 1, z1 + 1, x, y)
    return d


@part("chassis")
def chassis():
    """Bolts to the torso flange's top; carries the sled at the front and the electronics behind.

    Nothing hangs below the plate - it prints flat on its underside - and nothing stands on it
    inside the sled's slide path except the two lock bosses, which sit behind the sled's feet,
    and the guide ribs outboard of its flanks.
    """
    z0 = P.Z_CHASSIS
    z1 = z0 + P.CHASSIS_T
    c = cyl_z(P.CHASSIS_R, z0, z1)
    for x, y in P.GLAND_POS:                                         # wiring up from the glands
        c = c - cyl_z(GLAND_BORE_R, z0 - 1, z1 + 1, x, y)
    for y in (-CHASSIS_BORE_Y, CHASSIS_BORE_Y):                      # lightening, in the free lunes
        c = c - cyl_z(CHASSIS_BORE_R, z0 - 1, z1 + 1, 0.0, y)
    c = c - cyl_z(CHASSIS_VENT_R, z0 - 1, z1 + 1, CHASSIS_VENT_X, 0.0)
    for a in P.CHASSIS_SCREW_ANGLES:                                 # down into the torso flange
        c = c - cyl_z(P.M3_CLEAR / 2, z0 - 1, z1 + 1, *polar(P.CHASSIS_SCREW_R, a))
    for a in P.FLANGE_SCREW_ANGLES:                                  # reach the belt screws below
        c = c - cyl_z(3.5, z0 - 1, z1 + 1, *polar(P.FLANGE_SCREW_R, a))
    # the sled's two lock bosses, on the top face: SLED_FOOT_H tall, so the sled's lugs land on
    # them, and the insert is blind in boss and plate together
    for x, y in _sled_locks():
        c = c + cyl_z(BOSS_R, z0, z1 + P.SLED_FOOT_H, x, y)
    c = insert_holes(c, [(x, y, z1 + P.SLED_FOOT_H) for x, y in _sled_locks()])
    # guide ribs outboard of the sled's flanks, from behind its home position out to the rim
    y_in = P.PHONE_Y_OFFSET + P.PHONE_W / 2 + P.CLEAR + P.SLED_WALL + P.CLEAR
    for sy, y_rib in ((1, y_in), (-1, -(y_in - P.CLEAR))):
        rib = box(SLED_LOCK_X, P.CHASSIS_R, min(y_rib, y_rib + sy * 3.0), max(y_rib, y_rib + sy * 3.0),
                  z1, z1 + P.SLED_GUIDE_H)
        c = c + (rib & cyl_z(P.CHASSIS_R, z1, z1 + P.SLED_GUIDE_H))
    for x, y in _edeck(P.EDECK_HOLES):                               # electronics deck standoffs
        c = c + cyl_z(STANDOFF_R, z0, z1 + P.EDECK_STANDOFF, x, y)
        c = insert_holes(c, [(x, y, z1 + P.EDECK_STANDOFF)])
    for x, y in _edeck(P.EDECK_POSTS):                               # ... and two posts under its back
        c = c + cyl_z(STANDOFF_R, z0, z1 + P.EDECK_STANDOFF, x, y)
    return c


@part("phone_sled")
def phone_sled():
    """Tray the phone drops into: screen to -X, camera end down. Fits only one way, and slides
    out of the belly hatch along +X with the phone still in it.

    The pocket is the phone plus CLEAR across its width, taken off the -Y face: that face is the
    datum the camera's offset is measured from, so the clearance goes on the far side of it.
    """
    yc = P.PHONE_Y_OFFSET
    w = P.SLED_WALL
    y_p0 = yc - P.PHONE_W / 2                       # datum flank
    y_p1 = yc + P.PHONE_W / 2 + P.CLEAR             # ... and the clearance, all on the far side
    x0 = P.PHONE_FRONT_X - w
    x1 = P.PHONE_BACK_X + w            # thin back lip; the lens clip sits proud of it
    x_lip = P.PHONE_BACK_X + P.CLEAR   # the lip's inner face, a clearance off the back glass
    y0, y1 = y_p0 - w, y_p1 + w
    z0 = P.Z_CHASSIS + P.CHASSIS_T                  # the floor lies flat on the chassis
    z1 = P.PHONE_BOTTOM_Z + P.PHONE_L - SLED_OPEN_TOP
    tray = box(x0, x1, y0, y1, z0, z1)
    tray = tray - box(P.PHONE_FRONT_X - P.CLEAR, x_lip, y_p0, y_p1, P.PHONE_BOTTOM_Z, z1 + 1)
    # the lens clip stands LENS_CLIP_T proud of the back glass: a channel up the whole back at
    # the camera, so the phone drops in with the clip already on
    tray = tray - box(P.PHONE_BACK_X - 0.01, x1 + 1, P.CAM_Y - P.LENS_CLIP_W / 2, y1 + 1, z0 - 1, z1 + 1)
    # the back lip stops a third of the way up, so the back glass is not rubbed ...
    lip_top = P.PHONE_BOTTOM_Z + SLED_LIP_TOP
    tray = tray - box(P.PHONE_BACK_X - 0.01, x1 + 1, y0 - 1, y1 + 1, lip_top, z1 + 1)
    # ... except for two fingers that carry the back higher up. The finger at the mirror of the
    # camera's y is the orientation key: flipped end for end the phone's camera lands there, and
    # the finger runs past it, so the lens clip meets the finger instead of the channel however
    # tall the clip is. Neither finger is inside the phone's own outline.
    key_top = P.PHONE_BOTTOM_Z + P.PHONE_L - P.PHONE_CAM_FROM_END + SLED_KEY_OVERRUN
    for fy, top in ((yc, z1), (2 * yc - P.CAM_Y, key_top)):
        tray = tray + box(x_lip, x1, fy - 6, fy + 6, lip_top - 20, top)
    # screen-side window so the screen can be seen and the home button reached
    tray = tray - box(x0 - 1, P.PHONE_FRONT_X + 1, yc - 20, yc + 20, P.PHONE_BOTTOM_Z + 15, z1 + 1)
    # witness mark: a notch in the top edge of the +Y wall
    tray = tray - box(x0 - 1, x1 + 1, y1 - 2, y1 + 1, z1 - 4, z1 + 1)
    # Two feet behind the tray carry the lock lugs. The feet run on the chassis, the lugs stand
    # SLED_FOOT_H above it on the chassis's bosses, and nothing of the sled is ever behind them,
    # so the bosses are out of the slide path the moment the sled starts to move.
    for x, y in _sled_locks():
        tray = tray + box(x + BOSS_R + P.CLEAR, x0 + 1.0, y - 5, y + 5, z0, z0 + P.SLED_FOOT_H)
        tray = tray + box(x - BOSS_R - 1, x0 + 1.0, y - 5, y + 5, z0 + P.SLED_FOOT_H, z0 + P.SLED_FOOT_H + 4)
        tray = tray - cyl_z(P.M3_CLEAR / 2, z0 + P.SLED_FOOT_H - 1, z0 + P.SLED_FOOT_H + 5, x, y)
        tray = tray - cyl_z(3.2, z0 + P.SLED_FOOT_H + 1, z0 + P.SLED_FOOT_H + 5, x, y)   # head, flush
    return tray


@part("electronics_deck")
def electronics_deck():
    """Plate on standoffs behind the phone, laid out from EDECK_LAYOUT.

    Screws come down through it into the standoffs' inserts, so every head has to be reachable
    from above: the four sit in the gaps between the boards' rectangles.
    """
    ex, ey = P.EDECK_POS
    z0 = P.Z_CHASSIS + P.CHASSIS_T + P.EDECK_STANDOFF
    z1 = z0 + P.EDECK_T
    zc0, zc1 = z0 - 1, z1 + 1
    d = box(ex - P.EDECK_L / 2, ex + P.EDECK_L / 2, ey - P.EDECK_W / 2, ey + P.EDECK_W / 2, z0, z1)
    for x, y in _edeck(P.EDECK_HOLES):
        d = d - cyl_z(P.M3_CLEAR / 2, zc0, zc1, x, y)
    for name in ("xl4015_a", "xl4015_b"):
        cx, cy = _rect_centre(name)
        for dx in (-1, 1):
            for dy in (-1, 1):
                d = d - cyl_z(P.XL4015_HOLE_D / 2, zc0, zc1,
                              cx + dx * P.XL4015_HOLES[0] / 2, cy + dy * P.XL4015_HOLES[1] / 2)
    for name in ("mosfet_a", "mosfet_b", "mosfet_c"):
        cx, cy = _rect_centre(name)
        for dx in (-1, 1):
            for dy in (-1, 1):
                d = d - cyl_z(P.M3_CLEAR / 2, zc0, zc1,
                              cx + dx * P.MOSFET_HOLES[0] / 2, cy + dy * P.MOSFET_HOLES[1] / 2)
    # the ESP32 has no usable hole pattern, so it drops into a cradle: two rails a devkit's width
    # apart, and two tie slots that pass under both rails so a tie can come up outside the board
    x0, y_lo, x1, y_hi = _rect(P.EDECK_LAYOUT["esp32"])
    rail_gap = P.ESP32[1] + 0.6
    y_out = min(y_hi + 1.0, ey + P.EDECK_W / 2)                      # the +Y rail lands on the edge
    y_rail1 = y_out - ESP32_RAIL_T
    y_rail0 = y_rail1 - rail_gap
    for lo in (y_rail0 - ESP32_RAIL_T, y_rail1):
        d = d + box(x0, x1, lo, lo + ESP32_RAIL_T, z1 - 0.01, z1 + ESP32_RAIL_H)
    for x in (x0 + 4.0, x1 - 7.0):
        d = d - box(x, x + TIE_SLOT_W, y_rail0 - ESP32_RAIL_T - 0.5, y_out + 0.5, zc0, z1 + ESP32_RAIL_H + 1)
    fx0, fy0, fx1, fy1 = _rect(P.EDECK_LAYOUT["fuse"])               # two ties over the fuse holder
    for lo, hi in ((fy0 + 0.5, fy0 + 4.0), (fy1 - 4.0, fy1 - 0.5)):
        d = d - box(fx1 + 1.0, fx1 + 1.0 + TIE_SLOT_W, lo, hi, zc0, zc1)
    return d


def _rect(r):
    """An EDECK_LAYOUT rectangle in absolute x-y."""
    ex, ey = P.EDECK_POS
    return r[0] + ex, r[1] + ey, r[2] + ex, r[3] + ey


def _rect_centre(name):
    x0, y0, x1, y1 = _rect(P.EDECK_LAYOUT[name])
    return (x0 + x1) / 2, (y0 + y1) / 2


@part("hatch_lip", section="torso")
def hatch_lip():
    """The ledge the belly panel rests on, round the bottom and both sides of the opening.

    It fills the wall's inner 1.2 mm along the perimeter, so the panel - rebated by that much at
    its edge - finishes flush with the skin. There is none along the top edge: the panel shingles
    under the torso's cut edge there, and a lip would stand in the phone's way as the sled comes
    out (the phone's top is at 392.3 and the opening's top edge at 398).
    """
    z0, z1 = P.HATCH_Z
    band = skin_solid(P.TORSO_PROFILE, P.WALL - 1.2) - skin_solid(P.TORSO_PROFILE, P.WALL)
    inset = math.degrees(P.HATCH_LIP_W / P.shell_r(P.TORSO_PROFILE, (z0 + z1) / 2))
    return band & (_wedge(P.HATCH_HALF_ANGLE, z0, z1)
                   - _wedge(P.HATCH_HALF_ANGLE - inset, z0 + P.HATCH_LIP_W, z1 + 1))


@part("hatch_bosses", section="torso")
def hatch_bosses():
    """Four brackets inside the opening's edges that the belly panel screws into.

    Each reaches in from the side of the opening - where the shell is - to the screw's line, and
    stands proud of the wall far enough for a full blind insert facing the panel. Two cuts keep
    them honest: the sled's slide envelope, which at thirty degrees passes 9.5 mm inboard of the
    lower pair, and the window's opening, which the lower +Y bracket would otherwise show a
    millimetre and a half of through the glass.
    """
    bosses = None
    trim = _sled_envelope(P.CLEAR) + _window_prism()
    for z, a in P.HATCH_SCREWS:
        r_in = P.shell_r(P.TORSO_PROFILE, z) - P.WALL          # the panel's inner face
        r_face = r_in - P.INSERT_DEPTH - 1.0
        s = 1.0 if a > 0 else -1.0
        t_out = 16.0                                            # out past the opening's edge
        b = box(r_face, r_in + 1.2, min(-5.0 * s, t_out * s), max(-5.0 * s, t_out * s), z - 5, z + 5)
        b = b - cyl_x(P.INSERT_D / 2, r_in - P.INSERT_DEPTH, r_in + 2.2, 0.0, z)
        b = b.rotate(Axis.Z, a)
        bosses = b if bosses is None else bosses + b
    return (bosses & skin_solid(P.TORSO_PROFILE, P.WALL - 1.2)) - trim


@part("fan_frame", section="torso")
def fan_frame():
    """Four insert bosses inside the torso's back wall around the exhaust; the fan screws to them.

    The frame is a flat slab clipped to the wall, so it follows the barrel rather than standing
    proud where the shoulders draw in: over its fifty millimetres the torso narrows by six, and
    an unclipped slab left its top corner 1.8 mm outside the skin. What the clip takes away is
    the material the upper two screws would have gone into, so the inserts do not sit in the slab
    at all. They sit in four bosses on the inner face, four millimetres proud of it, which is
    also what the fan lands on.
    """
    z = P.Z_FAN
    x_wall = -(P.shell_r(P.TORSO_PROFILE, z) - P.WALL)
    half = P.FAN / 2 + 5
    x_boss = x_wall + 10                                                   # the face the fan bolts to
    frame = box(x_wall - 1.2, x_wall + 6, -half, half, z - half, z + half)
    frame = frame - cyl_x(P.FAN / 2 - 2, x_wall - 2, x_wall + 7, 0.0, z)   # the exhaust, round: the
    for dy in (-1, 1):                                                     # screw bosses are corners
        for dz in (-1, 1):
            frame = frame + cyl_x(4.0, x_wall + 4, x_boss, dy * P.FAN_PITCH / 2, z + dz * P.FAN_PITCH / 2)
    frame = frame & skin_solid(P.TORSO_PROFILE, P.WALL - 1.2)              # never proud of the back
    for dy in (-1, 1):
        for dz in (-1, 1):
            frame = frame - cyl_x(P.INSERT_D / 2, x_boss - P.INSERT_DEPTH, x_boss + 1, dy * P.FAN_PITCH / 2, z + dz * P.FAN_PITCH / 2)
    return frame
