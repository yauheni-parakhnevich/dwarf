"""The dry zone: the belt joint and everything that hangs off the chassis."""
import math
import params as P
from mech import part
from mech.common import cyl_z, cyl_x, box, insert_holes

# The chassis has its own bolt circle, two millimetres inside the belt screws': an M3 clearance
# hole on FLANGE_SCREW_R would leave 0.3 mm of rim on a disc of CHASSIS_R, which is no rim at all.
CHASSIS_SCREW_R = P.FLANGE_SCREW_R - 2.0
# The electronics deck is wider than the chassis at the back (its corners reach r 96, the chassis
# stops at 88), so its corner holes come 14 mm in along the deck and 5 mm in across it; that puts
# all four standoffs on the plate.
EDECK_INSET = (14.0, 5.0)
SLED_FOOT_Y = 20.0            # the sled's two feet, either side of the phone's centreline


def _polar(r, deg):
    return r * math.cos(math.radians(deg)), r * math.sin(math.radians(deg))


def _edeck_holes():
    """Plan positions of the electronics deck's four corner screws, shared with the chassis."""
    ex, ey = P.EDECK_POS
    ix, iy = EDECK_INSET
    return [(ex + dx * (P.EDECK_L / 2 - ix), ey + dy * (P.EDECK_W / 2 - iy))
            for dx in (-1, 1) for dy in (-1, 1)]


def _sled_feet():
    """Plan positions of the phone sled's two feet, shared with the chassis."""
    return [(P.PHONE_FRONT_X - P.SLED_WALL - 4, P.PHONE_Y_OFFSET + dy)
            for dy in (-SLED_FOOT_Y, SLED_FOOT_Y)]


@part("belt_flange_lower", section="base")
def belt_flange_lower():
    """Ring inside the base's rim with the inserts the belt screws go into."""
    z1 = P.Z_BELT
    z0 = z1 - 2 * P.RING_T
    r_out = P.ring_r_out(P.BASE_PROFILE, z0, z1)
    ring = cyl_z(r_out, z0, z1) - cyl_z(P.FLANGE_R_IN, z0 - 1, z1 + 1)
    return insert_holes(ring, [(*_polar(P.FLANGE_SCREW_R, a), z1) for a in P.FLANGE_SCREW_ANGLES], depth=P.INSERT_DEPTH + 2)


@part("belt_flange_upper", section="torso")
def belt_flange_upper():
    """Ring inside the torso's skirt: belt screws pass down through it, chassis screws go into its top."""
    z0 = P.Z_BASE_TOP
    z1 = z0 + P.RING_T
    r_out = P.ring_r_out(P.TORSO_PROFILE, z0, z1)
    ring = cyl_z(r_out, z0, z1) - cyl_z(P.FLANGE_R_IN, z0 - 1, z1 + 1)
    for a in P.FLANGE_SCREW_ANGLES:
        x, y = _polar(P.FLANGE_SCREW_R, a)
        ring = ring - cyl_z(P.M3_CLEAR / 2, z0 - 1, z1 + 1, x, y)
        ring = ring - cyl_z(3.2, z1 - P.SCREW_HEAD_H, z1 + 1, x, y)      # head sits below the chassis
    return insert_holes(ring, [(*_polar(CHASSIS_SCREW_R, a), z1) for a in P.CHASSIS_SCREW_ANGLES])


@part("divider")
def divider():
    """The base's lid: slices at 100 % infill. Two glands, a bead groove, four belt-screw holes."""
    z0, z1 = P.Z_BELT, P.Z_BASE_TOP
    r = P.shell_r(P.BASE_PROFILE, z0) - P.WALL - P.CLEAR
    d = cyl_z(r, z0, z1)
    # groove for the PU bead, in the face the torso's flange lands on. It runs outboard of the
    # belt screws: a bead the screw holes cut through would not seal.
    d = d - (cyl_z(r - 1.3, z1 - 1.5, z1 + 1) - cyl_z(r - 3.3, z1 - 2, z1 + 2))
    for a in P.FLANGE_SCREW_ANGLES:
        d = d - cyl_z(P.M3_CLEAR / 2, z0 - 1, z1 + 1, *_polar(P.FLANGE_SCREW_R, a))
    for x, y in P.GLAND_POS:
        d = d - cyl_z(P.GLAND_D / 2, z0 - 1, z1 + 1, x, y)
    return d


@part("chassis")
def chassis():
    """Bolts to the torso flange's top; carries the sled at the front and the electronics behind."""
    z0 = P.Z_CHASSIS
    z1 = z0 + P.CHASSIS_T
    c = cyl_z(P.CHASSIS_R, z0, z1)
    c = c - cyl_z(40, z0 - 1, z1 + 1, -40, 0)                       # wiring and airflow through the middle
    for a in P.CHASSIS_SCREW_ANGLES:
        c = c - cyl_z(P.M3_CLEAR / 2, z0 - 1, z1 + 1, *_polar(CHASSIS_SCREW_R, a))
    for a in P.FLANGE_SCREW_ANGLES:                                  # reach the belt screws below
        c = c - cyl_z(3.5, z0 - 1, z1 + 1, *_polar(P.FLANGE_SCREW_R, a))
    # sled feet: a boss under the plate at each, so a 6 mm insert stays blind in a 4 mm plate
    for x, y in _sled_feet():
        c = c + cyl_z(4.5, z0 - 3, z1, x, y)
    c = insert_holes(c, [(x, y, z1) for x, y in _sled_feet()])
    for x, y in _edeck_holes():                                      # electronics deck standoffs
        c = c + cyl_z(4, z0, z1 + P.EDECK_STANDOFF, x, y)
        c = insert_holes(c, [(x, y, z1 + P.EDECK_STANDOFF)])
    return c


@part("phone_sled")
def phone_sled():
    """Tray the phone drops into: screen to -X, camera end down. Fits only one way."""
    yc = P.PHONE_Y_OFFSET
    w = P.SLED_WALL
    x0 = P.PHONE_FRONT_X - w
    x1 = P.PHONE_BACK_X + w            # thin back lip; the lens clip sits proud of it
    x_lip = P.PHONE_BACK_X + P.CLEAR   # the lip's inner face, a clearance off the back glass
    y0 = yc - P.PHONE_W / 2 - w
    y1 = yc + P.PHONE_W / 2 + w
    z0 = P.Z_CHASSIS + P.CHASSIS_T                  # the floor lies flat on the chassis
    z1 = P.PHONE_BOTTOM_Z + P.PHONE_L - 20          # open at the top; the phone lifts out
    tray = box(x0, x1, y0, y1, z0, z1)
    pocket = box(P.PHONE_FRONT_X - P.CLEAR, x_lip, yc - P.PHONE_W / 2, yc + P.PHONE_W / 2, P.PHONE_BOTTOM_Z, z1 + 1)
    tray = tray - pocket
    # the lens clip stands 12 mm proud of the back glass: a channel up the whole back at the
    # camera, so the phone drops straight down into the tray with the clip already on
    tray = tray - box(P.PHONE_BACK_X - 0.01, x1 + 1, P.CAM_Y - 14, P.CAM_Y + 14, z0 - 1, z1 + 1)
    # the back lip stops a third of the way up, so the back glass is not rubbed ...
    lip_top = P.PHONE_BOTTOM_Z + 30
    tray = tray - box(P.PHONE_BACK_X - 0.01, x1 + 1, y0 - 1, y1 + 1, lip_top, z1 + 1)
    # ... except for two fingers that carry the back higher up. The finger at the mirror of the
    # camera's y is the orientation key: flipped end for end the phone's camera lands there, and
    # the finger runs six millimetres past it, so the lens clip meets the finger instead of the
    # channel however tall the clip is. Neither finger is inside the phone's own outline, so the
    # right way round the phone seats on both of them.
    key_top = P.PHONE_BOTTOM_Z + P.PHONE_L - P.PHONE_CAM_FROM_END + 6      # past the flipped camera
    for fy, top in ((yc, z1), (2 * yc - P.CAM_Y, key_top)):
        tray = tray + box(x_lip, x1, fy - 6, fy + 6, lip_top - 20, top)
    # screen-side window so the screen can be seen and the home button reached
    tray = tray - box(x0 - 1, P.PHONE_FRONT_X + 1, yc - 20, yc + 20, P.PHONE_BOTTOM_Z + 15, z1 + 1)
    # witness mark: a notch in the top edge of the +Y wall
    tray = tray - box(x0 - 1, x1 + 1, y1 - 2, y1 + 1, z1 - 4, z1 + 1)
    # feet, bolted down into the chassis in front of the tray
    for x, y in _sled_feet():
        tray = tray + box(x - 4.5, x0 + 1.0, y - 5, y + 5, z0, z0 + 12)
        tray = tray - cyl_z(P.M3_CLEAR / 2, z0 - 1, z0 + 13, x, y)
    return tray


@part("electronics_deck")
def electronics_deck():
    """Plate on standoffs behind the phone. Holes for two XL4015 and slots for the rest (cable-tied)."""
    ex, ey = P.EDECK_POS
    z0 = P.Z_CHASSIS + P.CHASSIS_T + P.EDECK_STANDOFF
    z1 = z0 + P.EDECK_T
    d = box(ex - P.EDECK_L / 2, ex + P.EDECK_L / 2, ey - P.EDECK_W / 2, ey + P.EDECK_W / 2, z0, z1)
    for x, y in _edeck_holes():
        d = d - cyl_z(P.M3_CLEAR / 2, z0 - 1, z1 + 1, x, y)
    hx, hy = P.XL4015_HOLES
    for cy in (ey - 25, ey + 25):                                       # two bucks side by side
        for dx, dy in ((-1, -1), (1, 1)):
            d = d - cyl_z(P.XL4015_HOLE_D / 2, z0 - 1, z1 + 1, ex - 20 + dx * hx / 2, cy + dy * hy / 2)
    for i in range(6):                                                  # tie slots for ESP32 and MOSFETs
        d = d - box(ex + 20 + (i % 2) * 20 - 1.5, ex + 20 + (i % 2) * 20 + 1.5, ey - 35 + (i // 2) * 30, ey - 25 + (i // 2) * 30, z0 - 1, z1 + 1)
    return d


@part("fan_frame", section="torso")
def fan_frame():
    """Ring of four insert bosses inside the torso's back wall around the exhaust; the fan screws to it."""
    z = P.Z_FAN
    x_wall = -(P.shell_r(P.TORSO_PROFILE, z) - P.WALL)
    half = P.FAN / 2 + 5
    frame = box(x_wall - 1.2, x_wall + 6, -half, half, z - half, z + half)
    frame = frame - cyl_x(P.FAN / 2 - 2, x_wall - 2, x_wall + 7, 0.0, z)   # the exhaust, round: the
    for dy in (-1, 1):                                                     # screw bosses are corners
        for dz in (-1, 1):
            frame = frame - cyl_x(P.INSERT_D / 2, x_wall + 6 - P.INSERT_DEPTH, x_wall + 7, dy * P.FAN_PITCH / 2, z + dz * P.FAN_PITCH / 2)
    return frame
