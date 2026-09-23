"""The dry zone: the belt joint, the floor plate, and everything that hangs off the chassis.

The shell is the statue now, so no part in here is shaped to a profile of revolution any more.
Every interface part - anything the assembler unions into a printed section - is built as an
oversize **blank**: BLANK millimetres past where the skin will be, in the radial direction, and
the assembler clips it to the statue's grown cavity. Only the loose parts (the divider, the
chassis, the sled, the deck, the floor plate) are drawn to their finished size, and those are
sized from the belt ellipse and the cavity reach table in the fit report.

There is no belly hatch any more. Everything dry-side is reached from the top with the turning
bell lifted off: the sled drops into its cutout through the chassis, the deck's screws are driven
down, and the filler's cap is turned where it stands on the divider.
"""
import json
import math
from pathlib import Path
from build123d import Axis, Ellipse, Pos, extrude
import params as P
from mech import part
from mech.common import box, cyl_z, insert_holes, polar

# --- numbers this module chooses, which params does not ----------------------------------
BLANK = 15.0                 # how far past the nominal skin every interface blank runs
R_FRONT = P.FRONT_SKIN_X_AT_WINDOW    # 89.4, the statue's front at the window
# the belt screws sit on the ring's mid-line: the ellipse halfway between the joint's outer
# section and its bore. At BELT_SCREW_ANGLES that is (51.3, 63.0) and its three mirrors.
BELT_MID_RX = (P.BELT_RX + P.BELT_IN_RX) / 2          # 67
BELT_MID_RY = (P.BELT_RY + P.BELT_IN_RY) / 2          # 98
# The chassis has its own four on the same mid-line, between the belt's: the belt joint has to
# open without the chassis coming off first. Nearest pair is 48.3 mm apart. (params' own
# CHASSIS_SCREW_ANGLES is the belt's set and is not used here.)
# ... and clear of the phone and of the sled's guide ribs: at 10 degrees the screw landed at
# (66, 17), under the tray, with its driver going up into the phone; at 25 the driver caught the
# rib's outer edge. At 30 it is at (58.0, 49.0), a millimetre and a half in front of the tray's
# pocket and five clear of the rib.
CHASSIS_SCREW_ANGLES = [30.0, 150.0, 210.0, 330.0]
# The filler neck rises off the divider's front. At FILLER_NECK_XY's first value, y 0, its cap
# stood inside the sled's tray, which is at x 59.9 .. 73 from z 249.3 up; beside the tray it
# needs |y| >= 36.55 + 18 (the cap's grip) and it sits at y -58. That is 44 degrees round from
# the front. With the turning bell off, the cap is turned from straight above it.
NECK_FLANGE_R = 16.0
NECK_BASE_Z = P.Z_BASE_TOP + P.DIVIDER_PROUD          # the divider's top face
NECK_TOP_Z = NECK_BASE_Z + 15.0
# The floor plate's blank: the cavity at Z_FLOOR is 54 front, 93 back, 118/102 across (T8). A
# full BLANK past the widest of those would be 266 across and the bed is 256, so the +Y side
# gets 7 mm of blank instead of 15 and every other direction keeps at least 13.
FLOOR_RX, FLOOR_RY = 106.0, 125.0
FLOOR_T = 4.0
SAND_PLUG_XY = (-78.0, 0.0)  # behind the bottle, where the cavity at Z_FLOOR is 106 deep;
                             # its lip clears the cradle's rear flank rib by 3.5 mm and both
                             # leg ports by 11, and stands 9 inside the plate's own ellipse
LEG_PORT_X = -60.0           # tube and wiring down to the legs, clear of the bottle's -X face
LEG_PORT_R = 12.0
BRACKET_BOLT = 25.0          # half-pitch of the four inserts each leg bracket hangs from
CRADLE_BOLT = (40.0, 70.0)   # the bottle cradle's four inserts in the floor plate

CHASSIS_BORE_R = 18.0        # two lightening bores beside the deck, in the chassis's free lunes
CHASSIS_BORE_Y = 62.0        # ... on the centreline's flanks, clear of the deck and the sled
GLAND_BORE_R = 7.0           # wiring holes over the divider's glands: a 14 mm hole per bundle
BEAD_GROOVE = (1.3, 3.3)     # the bead groove's edges, in from the divider's rim
BOSS_R = 5.5                 # the chassis's bosses round a blind M3 insert
# the sled's lock screws sit just in front of its tray's back wall - any further back and the
# boss would be behind the wall, which is how the old constant broke when the phone moved
SLED_LOCK_X = P.PHONE_FRONT_X - P.SLED_WALL - BOSS_R - P.CLEAR - 1.0    # 53.1
SLED_FOOT_Y = 20.0           # the lock screws, either side of the phone's centreline
SLED_OPEN_TOP = 20.0         # the tray's walls stop this far below the phone's top
SLED_KEY_OVERRUN = 6.0       # the key finger runs this far past the flipped camera
SLED_LIP_TOP = 30.0          # the back lip stops this far above the phone's bottom
STANDOFF_R = 4.0
ESP32_RAIL_T = 2.4           # the cradle's rails either side of the devkit
ESP32_RAIL_H = 4.0
TIE_SLOT_W = 3.0             # cable-tie slots


def _ell_z(rx, ry, z0, z1, x=0.0, y=0.0):
    """An elliptical prism along Z from z0 to z1."""
    return Pos(x, y, z0) * extrude(Ellipse(rx, ry), z1 - z0)


def _ell_ring(rx, ry, rx_in, ry_in, z0, z1):
    return _ell_z(rx, ry, z0, z1) - _ell_z(rx_in, ry_in, z0 - 1, z1 + 1)


def _mid_ring(angles):
    return [(BELT_MID_RX * math.cos(math.radians(a)), BELT_MID_RY * math.sin(math.radians(a)))
            for a in angles]


def belt_screws():
    """The four belt screws, on the ring's mid-line ellipse at BELT_SCREW_ANGLES."""
    return _mid_ring(P.BELT_SCREW_ANGLES)


def chassis_screws():
    """The chassis's own four, on the same ellipse between the belt's."""
    return _mid_ring(CHASSIS_SCREW_ANGLES)


def cage_feet():
    """Where the turntable cage's four legs land on the chassis, from params not by hand."""
    return [polar(P.CAGE_LEG_R, a) for a in P.DECK_SCREW_ANGLES]


def measured_legs():
    """The statue stage's measured leg cavities if it has written them, else the parameters'.

    LEG_LEFT_XY and LEG_RIGHT_XY are the fit report's estimate from a reach table; the statue
    measures the real cavity and puts it in out/statue/features.json under "legs".
    """
    path = Path(__file__).resolve().parents[1] / "out" / "statue" / "features.json"
    try:
        legs = json.loads(path.read_text())["legs"]
        return {"left": tuple(legs["left"][:2]), "right": tuple(legs["right"][:2]),
                "r": float(legs["r"])}
    except (OSError, KeyError, ValueError):
        return {"left": tuple(P.LEG_LEFT_XY), "right": tuple(P.LEG_RIGHT_XY), "r": P.LEG_R}


def leg_centres():
    legs = measured_legs()
    return [legs["left"], legs["right"]]


def bracket_bolts(centre):
    """The four inserts in the floor plate a leg bracket hangs from."""
    cx, cy = centre
    return [(cx + dx * BRACKET_BOLT, cy + dy * BRACKET_BOLT) for dx in (-1, 1) for dy in (-1, 1)]


def cradle_bolts():
    bx, by = CRADLE_BOLT
    return [(dx * bx, dy * by) for dx in (-1, 1) for dy in (-1, 1)]



def _edeck(points):
    ex, ey = P.EDECK_POS
    return [(ex + x, ey + y) for x, y in points]


def _rect(r):
    """An EDECK_LAYOUT rectangle in absolute x-y."""
    ex, ey = P.EDECK_POS
    return r[0] + ex, r[1] + ey, r[2] + ex, r[3] + ey


def _rect_centre(name):
    x0, y0, x1, y1 = _rect(P.EDECK_LAYOUT[name])
    return (x0 + x1) / 2, (y0 + y1) / 2



def _sled_locks():
    return [(SLED_LOCK_X, P.PHONE_Y_OFFSET + dy) for dy in (-SLED_FOOT_Y, SLED_FOOT_Y)]


def sled_pocket(grow=0.0):
    """The hole the sled's tray hangs through in the chassis: phone, walls and a shell clearance."""
    yc, w = P.PHONE_Y_OFFSET, P.SLED_WALL + P.CLEAR_SHELL + grow
    return (P.PHONE_FRONT_X - w, P.PHONE_BACK_X + w,
            yc - P.PHONE_W / 2 - w, yc + P.PHONE_W / 2 + P.CLEAR + w)



# --- the belt joint ---------------------------------------------------------------------------

@part("belt_flange_lower", section="base")
def belt_flange_lower():
    """The base's half of the belt joint: a ring under the split and a tongue above it.

    The ring carries the four inserts every belt screw lands in. The tongue rises past the split
    to Z_BASE_TOP outside the divider, so the torso's skirt lands over it rather than on a butt
    joint; the assembler clips the ring to the cavity and the tongue to the cavity less
    CLEAR_SHELL, which is what makes it a tongue and not an interference fit.
    """
    z0 = P.Z_BELT - P.FLANGE_LOWER_H
    ring = _ell_ring(P.BELT_RX + BLANK, P.BELT_RY + BLANK, P.BELT_IN_RX, P.BELT_IN_RY, z0, P.Z_BELT)
    tongue = _ell_ring(P.BELT_RX + BLANK, P.BELT_RY + BLANK, P.BELT_RX, P.BELT_RY,
                       P.Z_BELT, P.Z_BASE_TOP)
    return insert_holes(ring + tongue, [(x, y, P.Z_BELT) for x, y in belt_screws()],
                        depth=P.INSERT_DEPTH + 3)


@part("belt_flange_upper", section="torso")
def belt_flange_upper():
    """The torso's half: a ring the belt screws pass down through, inside the skirt.

    The belt screws pass down through it into the base's inserts, heads recessed in its top so
    the chassis lands on the ring and not on four screw heads. The chassis's own four go into
    inserts beside them, so the belt can be opened with the chassis still bolted down.
    """
    z0 = P.Z_BASE_TOP
    z1 = z0 + P.RING_T
    ring = _ell_ring(P.BELT_RX + BLANK, P.BELT_RY + BLANK, P.BELT_IN_RX, P.BELT_IN_RY, z0, z1)
    px0, px1, py0, py1 = sled_pocket()                           # the sled's tray hangs past it
    ring = ring - box(px0, px1, py0, py1, z0 - 1, z1 + 1)
    # only as tall as the neck's own flange: any deeper and it takes the belt screw at 40
    # degrees, which is 8.86 mm away, out of the ring with it
    ring = ring - cyl_z(NECK_FLANGE_R + 1.0, z0 - 1, NECK_BASE_Z + 3.5, *P.FILLER_NECK_XY)
    for x, y in belt_screws():
        ring = ring - cyl_z(P.M3_CLEAR / 2, z0 - 1, z1 + 1, x, y)
        ring = ring - cyl_z(3.2, z1 - (P.SCREW_HEAD_H + 0.5), z1 + 1, x, y)
    return insert_holes(ring, [(x, y, z1) for x, y in chassis_screws()])


@part("divider")
def divider():
    """The base's lid: an ellipse a clearance inside the belt's section, at 100 % infill.

    Its top stands DIVIDER_PROUD above the base's rim so the belt screws always squeeze the PU
    bead rather than bottoming the two rims on each other. Two glands, and the four screws pass
    through it on their way from the chassis to the base.
    """
    z0, z1 = P.Z_BELT, P.Z_BASE_TOP + P.DIVIDER_PROUD
    rx, ry = P.BELT_RX - P.CLEAR, P.BELT_RY - P.CLEAR
    d = _ell_z(rx, ry, z0, z1)
    g_out, g_in = BEAD_GROOVE                                    # the PU bead, outboard of the screws
    d = d - (_ell_z(rx - g_out, ry - g_out, z1 - 1.5, z1 + 1)
             - _ell_z(rx - g_in, ry - g_in, z1 - 2, z1 + 2))
    for x, y in belt_screws():
        d = d - cyl_z(P.M3_CLEAR / 2, z0 - 1, z1 + 1, x, y)
    for x, y in P.GLAND_POS:
        d = d - cyl_z(P.GLAND_D / 2, z0 - 1, z1 + 1, x, y)
    nx, ny = P.FILLER_NECK_XY                                    # the filler neck's spigot
    return d - cyl_z(P.FILLER_D / 2 + 2 + P.CLEAR, z0 - 1, z1 + 1, nx, ny)


# --- the floor over the sand ---------------------------------------------------------------------

@part("floor_plate", section="base")
def floor_plate():
    """The wet zone's floor: an elliptical blank at Z_FLOOR the assembler clips into the cavity.

    Everything wet stands on it or hangs under it. Below it the trouser legs and the boots are
    sand, poured in through the plug hole and stopped at SAND_Z_TOP, well under the pump and the
    valve; each leg gets a port for that part's tube and wiring, behind the bottle where the
    plate is free.
    """
    z0, z1 = P.Z_FLOOR, P.Z_FLOOR + FLOOR_T
    p = _ell_z(FLOOR_RX, FLOOR_RY, z0, z1)
    p = p - cyl_z(P.SAND_PLUG_D / 2, z0 - 1, z1 + 1, *SAND_PLUG_XY)
    for _, cy in leg_centres():
        p = p - cyl_z(LEG_PORT_R, z0 - 1, z1 + 1, LEG_PORT_X, cy)
    p = insert_holes(p, [(x, y, z1) for x, y in cradle_bolts()])          # the bottle's cradle
    for centre in leg_centres():                                          # ... and the two brackets
        p = insert_holes(p, [(x, y, z0) for x, y in bracket_bolts(centre)], direction="up")
    return p


@part("sand_plug")
def sand_plug():
    """Closes the floor plate's pour hole: a disc with a lip that drops into it and a finger slot."""
    z0, z1 = P.Z_FLOOR, P.Z_FLOOR + FLOOR_T
    r = P.SAND_PLUG_D / 2
    x, y = SAND_PLUG_XY
    plug = cyl_z(r - P.CLEAR, z0, z1, x, y) + cyl_z(r + 4.0, z1, z1 + 1.5, x, y)
    return plug - box(x - 2.0, x + 2.0, y - (r + 5), y + (r + 5), z1 + 0.5, z1 + 2)


# --- the chassis and what stands on it -----------------------------------------------------------

@part("chassis")
def chassis():
    """The dry zone's floor: an ellipse inside the coat, bolted down by the same four belt screws.

    The sled's tray hangs through a pocket in it - the tray's floor is at SLED_FLOOR_Z, below
    this plate - so the pocket is the phone plus the tray's walls plus a shell clearance all
    round. The sled's two lock lugs still land on bosses on this plate's top.
    """
    z0 = P.Z_CHASSIS
    z1 = z0 + P.CHASSIS_T
    c = _ell_z(P.CHASSIS_RX, P.CHASSIS_RY, z0, z1)
    px0, px1, py0, py1 = sled_pocket()
    c = c - box(px0, px1, py0, py1, z0 - 1, z1 + 1)                  # the tray hangs through here
    for x, y in P.GLAND_POS:                                         # wiring up from the glands
        c = c - cyl_z(GLAND_BORE_R, z0 - 1, z1 + 1, x, y)
    for y in (-CHASSIS_BORE_Y, CHASSIS_BORE_Y):                      # lightening, in the free lunes
        c = c - cyl_z(CHASSIS_BORE_R, z0 - 1, z1 + 1, 0.0, y)
    for x, y in chassis_screws():                                    # down into the torso ring
        c = c - cyl_z(P.M3_CLEAR / 2, z0 - 1, z1 + 1, x, y)
    for x, y in cage_feet():                                         # up into the cage's feet
        c = c - cyl_z(P.M3_CLEAR / 2, z0 - 1, z1 + 1, x, y)
    for x, y in belt_screws():                                       # reach the belt screws below
        c = c - cyl_z(3.5, z0 - 1, z1 + 1, x, y)
    for x, y in _sled_locks():                                       # the sled's lock bosses
        c = c + cyl_z(BOSS_R, z0, z1 + P.SLED_FOOT_H, x, y)
    c = insert_holes(c, [(x, y, z1 + P.SLED_FOOT_H) for x, y in _sled_locks()])
    y_in = py1 + P.CLEAR                                             # guide ribs outboard of the flanks
    for y_rib in (y_in, py0 - P.CLEAR - P.SLED_GUIDE_H):
        rib = box(SLED_LOCK_X, P.CHASSIS_RX, y_rib, y_rib + P.SLED_GUIDE_H, z1, z1 + P.SLED_GUIDE_H)
        c = c + (rib & _ell_z(P.CHASSIS_RX, P.CHASSIS_RY, z1, z1 + P.SLED_GUIDE_H))
    for x, y in _edeck(P.EDECK_HOLES):                               # electronics deck standoffs
        c = c + cyl_z(STANDOFF_R, z0, z1 + P.EDECK_STANDOFF, x, y)
        c = insert_holes(c, [(x, y, z1 + P.EDECK_STANDOFF)])
    for x, y in _edeck(P.EDECK_POSTS):                               # ... and two posts under its back
        c = c + cyl_z(STANDOFF_R, z0, z1 + P.EDECK_STANDOFF, x, y)
    nx, ny = P.FILLER_NECK_XY                                        # the filler cap passes through,
    return c - cyl_z(P.FILLER_CAP_THREAD_MAJOR / 2 + 3 + 4 + 1.0,    # last, so a rib cannot grow back
                     z0 - 1, z1 + P.EDECK_STANDOFF + 1, nx, ny)


@part("phone_sled")
def phone_sled():
    """Tray the phone drops into: screen to -X, camera end down, lowered in from above.

    Its floor is at SLED_FLOOR_Z, just above the divider and below the chassis, so the tray hangs
    through the chassis's pocket and the phone sits as low as the divider allows. With no hatch
    it goes in from the top, down through that same pocket, and its lugs lock on the chassis. The pocket is
    the phone plus CLEAR across its width, taken off the +Y face: the -Y face is the datum the
    camera's offset is measured from.
    """
    yc = P.PHONE_Y_OFFSET
    w = P.SLED_WALL
    y_p0 = yc - P.PHONE_W / 2                       # datum flank
    y_p1 = yc + P.PHONE_W / 2 + P.CLEAR             # ... and the clearance, all on the far side
    x0 = P.PHONE_FRONT_X - w
    x1 = P.PHONE_BACK_X + w            # thin back lip; the lens clip sits proud of it
    x_lip = P.PHONE_BACK_X + P.CLEAR   # the lip's inner face, a clearance off the back glass
    y0, y1 = y_p0 - w, y_p1 + w
    z0 = P.SLED_FLOOR_Z
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
    # camera's y is the orientation key: flipped end for end the phone's camera lands there.
    key_top = P.PHONE_BOTTOM_Z + P.PHONE_L - P.PHONE_CAM_FROM_END + SLED_KEY_OVERRUN
    for fy, top in ((yc, z1), (2 * yc - P.CAM_Y, key_top)):
        tray = tray + box(x_lip, x1, fy - 6, fy + 6, lip_top - 20, top)
    # screen-side window so the screen can be seen and the home button reached
    tray = tray - box(x0 - 1, P.PHONE_FRONT_X + 1, yc - 20, yc + 20, P.PHONE_BOTTOM_Z + 15, z1 + 1)
    # witness mark: a notch in the top edge of the +Y wall
    tray = tray - box(x0 - 1, x1 + 1, y1 - 2, y1 + 1, z1 - 4, z1 + 1)
    # two lugs behind the tray that land on the chassis's bosses and lock it at home
    z_lug = P.Z_CHASSIS + P.CHASSIS_T + P.SLED_FOOT_H
    lug_t = P.EDECK_STANDOFF - P.SLED_FOOT_H - 0.5          # half a millimetre under the deck
    for x, y in _sled_locks():
        tray = tray + box(x - BOSS_R - 1, x0 + 1.0, y - 5, y + 5, z_lug, z_lug + lug_t)
        tray = tray - cyl_z(P.M3_CLEAR / 2, z_lug - 1, z_lug + lug_t + 1, x, y)
        tray = tray - cyl_z(3.2, z_lug + 1, z_lug + lug_t + 1, x, y)     # head, flush
    return tray


@part("electronics_deck")
def electronics_deck():
    """Plate on standoffs behind the phone, laid out from EDECK_LAYOUT."""
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
    y_out = min(y_hi + 1.0, ey + P.EDECK_W / 2)
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


# --- the fan's blank in the left side panel -------------------------------------------------------


@part("filler_neck")
def filler_neck():
    """The filler's neck, bonded into the divider's front: the cap screws onto this.

    The tank head's port feeds it by a hose, so the bottle is topped up without taking the
    divider off - reached from the top, with the bell lifted. Its spigot passes through the
    divider and its flange sits on the divider's top face; the thread is the same M22 the cap
    is cut to.
    """
    from bd_warehouse.thread import IsoThread
    nx, ny = P.FILLER_NECK_XY
    bore = P.FILLER_D / 2
    thread = IsoThread(major_diameter=P.FILLER_CAP_THREAD_MAJOR, pitch=P.FILLER_CAP_PITCH,
                       length=NECK_TOP_Z - NECK_BASE_Z - 4.0, external=True,
                       end_finishes=("square", "square"))
    core = thread.min_radius
    neck = cyl_z(bore + 2.0, P.Z_BELT, NECK_BASE_Z, nx, ny)                # spigot, through the divider
                                                                           # only: a millimetre lower and
                                                                           # it is in the base ring's bore
    neck = neck + cyl_z(NECK_FLANGE_R, NECK_BASE_Z, NECK_BASE_Z + 3.0, nx, ny)
    neck = neck + cyl_z(core, NECK_BASE_Z, NECK_TOP_Z, nx, ny)
    neck = neck + Pos(nx, ny, NECK_BASE_Z + 3.0) * thread
    return neck - cyl_z(bore, P.Z_BELT - 1.0, NECK_TOP_Z + 1.0, nx, ny)
