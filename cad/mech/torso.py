"""The dry zone: the belt joint, the floor plate, and everything that hangs off the chassis.

The shell is the statue now, so no part in here is shaped to a profile of revolution any more.
Every interface part - anything the assembler unions into a printed section - is built as an
oversize **blank**: BLANK millimetres past where the skin will be, in the radial direction, and
the assembler clips it to the statue's grown cavity. Only the loose parts (the divider, the
chassis, the sled, the deck, the floor plate) are drawn to their finished size, and those are
sized from the belt ellipse and the cavity reach table in the fit report.

There is no belly hatch any more. Everything dry-side is reached from the top with the turning
bell lifted off: the sled drops into its cutout through the chassis, the deck's screws are driven
down. The filler is outside, on the coat's back: mech/filler.py.
"""
import json
import math
from pathlib import Path
from build123d import Axis, Cone, Ellipse, Location, Polygon, Pos, extrude
import params as P
from mech import part
from mech.filler import passage_xy
from mech.common import (BARB_BORE_R, BARB_R, BARB_RING, barb_rings, box, cyl_z,
                         insert_holes, polar)

# --- numbers this module chooses, which params does not ----------------------------------
BLANK = 15.0                 # how far past the nominal skin every interface blank runs
R_FRONT = P.FRONT_SKIN_X_AT_WINDOW    # 89.4, the statue's front at the window
# the belt screws sit on the ring's mid-line: the ellipse halfway between the joint's outer
# section and its bore. At BELT_SCREW_ANGLES that is (51.3, 63.0) and its three mirrors.
BELT_MID_RX = (P.BELT_RX + P.BELT_IN_RX) / 2          # 67
BELT_MID_RY = (P.BELT_RY + P.BELT_IN_RY) / 2          # 98
# The chassis has its own three, and they are all at the back. It has to go in through the ring's
# top, which the parting's seam chamfer leaves only 82 out at the sides, 86 at the front and 74 at
# the back, so it is 72 x 80 now, not 70 x 100 - and at that size it overlaps the belt flange only
# front and back, over |azimuth| < 40 and > 140 degrees. The front of that is the sled's pocket.
# So the screws are at 185, 200 and 215, in the band between the flange's bore and the chassis's
# edge and outside the cage's foot ring, whose drivers they are; the front rests on the flange and
# nothing lifts it: the deck's load comes down the cage's legs.
CHASSIS_SCREWS = ((68.5, 185.0), (69.5, 200.0), (69.5, 215.0))   # none at 145 any more: the filler's hose
                                                                   # comes down at 147 and its port stands over 160
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

GLAND_BORE_R = 7.0           # wiring holes over the divider's glands: a 14 mm hole per bundle
SKIRT_H = 6.0                # the skirt under the divider round the filler's hose
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
CHASSIS_PORT_R = 61.0        # the chassis's back edge under the filler port, and ...
CHASSIS_PORT_HALF = 19.0     # ... either side of it: the port.s inside reaches in to r 65.8
ESP32_RAIL_T = 2.4           # the cradle's rails either side of the devkit
ESP32_RAIL_H = 4.0
TIE_SLOT_W = 3.0             # cable-tie slots


def _ell_z(rx, ry, z0, z1, x=0.0, y=0.0):
    """An elliptical prism along Z from z0 to z1."""
    return Pos(x, y, z0) * extrude(Ellipse(rx, ry), z1 - z0)


def _cone_z(r0, r1, z0, z1, x=0.0, y=0.0):
    """A cone along +Z, r0 at z0 and r1 at z1."""
    return Pos(x, y, (z0 + z1) / 2) * Cone(r0, r1, z1 - z0)


def _ell_ring(rx, ry, rx_in, ry_in, z0, z1):
    return _ell_z(rx, ry, z0, z1) - _ell_z(rx_in, ry_in, z0 - 1, z1 + 1)


def _mid_ring(angles):
    return [(BELT_MID_RX * math.cos(math.radians(a)), BELT_MID_RY * math.sin(math.radians(a)))
            for a in angles]


def belt_screws():
    """The four belt screws, on the ring's mid-line ellipse at BELT_SCREW_ANGLES."""
    return _mid_ring(P.BELT_SCREW_ANGLES)


def chassis_screws():
    """The chassis's own three, on the flange behind the boards."""
    return [polar(r, a) for r, a in CHASSIS_SCREWS]


def cage_feet():
    """Where the turntable cage's four legs land on the chassis, from params not by hand."""
    return [polar(P.CAGE_LEG_R, a) for a in P.DECK_SCREW_ANGLES]


def measured_legs():
    """The statue stage's measured leg cavities. LEG_LEFT_XY and LEG_RIGHT_XY were the fit report's
    estimate and are 41 mm from where the mesh puts the legs, so they are not a fallback: without
    the statue this raises (mech.common.features)."""
    from mech.common import features
    legs = features("legs")
    return {"left": tuple(legs["left"][:2]), "right": tuple(legs["right"][:2]), "r": float(legs["r"])}


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


def sled_lug(x, y):
    """One of the sled's two lock lugs, in plan: (x0, x1, y0, y1).

    It reaches back from the tray to cover its screw's head and a millimetre more, which puts its
    heel at x 48.9 - a millimetre inside the electronics deck's front edge. The deck is slotted
    for it. It was 2.3 mm longer, to the boss's edge; the sled's way in with the lens clipped on is
    a dog-leg 6 mm behind its place past the boards' front edge, and that is the room it needed.
    """
    return (x - LUG_HEAD_R - 1.0, P.PHONE_FRONT_X - P.SLED_WALL + 1.0, y - 5.0, y + 5.0)


LUG_HEAD_R = 3.2                 # the lock screw's head, which the lug covers


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
    flange = insert_holes(ring + tongue, [(x, y, P.Z_BELT) for x, y in belt_screws()],
                          depth=P.INSERT_DEPTH + 3)
    return flange - cyl_z(P.FILLER_PASSAGE_D / 2, z0 - 1, P.Z_BASE_TOP + 1, *passage_xy())   # the filler's hose


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
    # ... and the lens clipped onto the phone's back hangs down into it: 12 mm proud of the back
    # glass and 28 wide, its barrel reaches under the ring's top at the front
    hw = P.LENS_CLIP_W / 2 + P.CLEAR_SHELL
    ring = ring - box(px1 - 0.01, P.LENS_FRONT_X + 1.0, P.CAM_Y - hw, P.CAM_Y + hw, z0 - 1, z1 + 1)
    ring = ring - cyl_z(P.FILLER_PASSAGE_D / 2, z0 - 1, z1 + 1, *passage_xy())     # the filler's hose
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
    # the filler's hose passes here, near the rim at the back, 0.5 mm round it: little air between
    # the wet side and the boards, and a drip down the hose is led into the gap by a funnel on top
    # and down the hose by a skirt underneath, inside the lower flange's bore. Print it top down.
    px, py = passage_xy()
    r = P.FILLER_DIVIDER_D / 2
    skirt = cyl_z(r + 0.9, z0 - SKIRT_H, z0 + 0.01, px, py)
    d = d + skirt
    d = d - cyl_z(r, z0 - SKIRT_H - 1, z1 + 1, px, py)
    return d - _cone_z(r, r + 2.5, z1 - 2.5, z1 + 0.01, px, py)


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
    for x, y in chassis_screws():                                    # down into the torso ring
        c = c - cyl_z(P.M3_CLEAR / 2, z0 - 1, z1 + 1, x, y)
    for x, y in cage_feet():                                         # up into the cage's feet
        c = c - cyl_z(P.M3_CLEAR / 2, z0 - 1, z1 + 1, x, y)
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
    # the filler port stands over the chassis's back edge and the chassis goes down past it: it is
    # cut back to r CHASSIS_PORT_R over the port's width, which takes the hose's bore with it
    a = P.FILLER_PORT_AZ
    notch = extrude(Polygon((0.0, 0.0), *[polar(200.0, a + d) for d in (-CHASSIS_PORT_HALF, 0.0, CHASSIS_PORT_HALF)]),
                    z1 - z0 + 2).moved(Location((0, 0, z0 - 1)))
    return c - (notch - cyl_z(CHASSIS_PORT_R, z0 - 2, z1 + 2))


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
        tray = tray + box(*sled_lug(x, y), z_lug, z_lug + lug_t)
        tray = tray - cyl_z(P.M3_CLEAR / 2, z_lug - 1, z_lug + lug_t + 1, x, y)
        tray = tray - cyl_z(3.2, z_lug + 1, z_lug + lug_t + 1, x, y)     # head, flush
    return tray


@part("electronics_deck")
def electronics_deck():
    """Plate on standoffs behind the phone, laid out from EDECK_LAYOUT.

    Its front edge is slotted where the phone sled's two lock lugs come up past it, so the sled
    can be lifted straight out for phone service with the boards still bolted down. The slots
    are in the free strip between the MOSFET modules and the edge, and nothing is laid out in
    them; the +Y standoff sits just past the upper one.
    """
    ex, ey = P.EDECK_POS
    z0 = P.Z_CHASSIS + P.CHASSIS_T + P.EDECK_STANDOFF
    z1 = z0 + P.EDECK_T
    zc0, zc1 = z0 - 1, z1 + 1
    d = box(ex - P.EDECK_L / 2, ex + P.EDECK_L / 2, ey - P.EDECK_W / 2, ey + P.EDECK_W / 2, z0, z1)
    for lx, ly in _sled_locks():                                     # the sled's lugs pass here
        x0, x1, y0, y1 = sled_lug(lx, ly)
        d = d - box(x0 - P.CLEAR, ex + P.EDECK_L / 2 + 1, y0 - 1.0, y1 + 1.0, zc0, zc1)
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
