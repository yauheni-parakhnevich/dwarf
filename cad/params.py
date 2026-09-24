"""Every dimension of the printed gnome, in millimetres.

Z is up, +X is the direction the gnome faces, the origin is the centre of the floor.
Both build123d and Blender import this module, so it must stay plain Python.

Bought parts that have not been measured yet carry listing-typical defaults; the README
lists which ones to re-measure on arrival.
"""
import math

# --- printer and fits ------------------------------------------------------------------
BED = 256.0
WALL = 2.4                 # shell wall, two 0.6 mm perimeters
CLEAR = 0.3                # sliding fit, machined-scale parts
CLEAR_SHELL = 0.5          # shell-to-shell shingles: a voxel-remeshed skin is not a machined bore
INSERT_D = 4.0             # M3 heat-set insert bore
INSERT_DEPTH = 6.0
INSERT_DEPTH_SHORT = 4.0       # for 5 mm parts: a short M3 insert, still blind
M3_CLEAR = 3.4
M2_5_CLEAR = 2.8
SCREW_HEAD_H = 3.0

# --- heights ---------------------------------------------------------------------------
Z_FLOOR = 150.0            # the statue has no cavity below its coat hem; the boots and legs below are sand ballast
SAND_PLUG_D = 30.0         # a plugged hole in the floor plate to pour the sand through
Z_BELT = 240.0             # the split, under the statue's belt strap (234..282); any higher and the phone no longer fits under the deck
Z_BASE_TOP = 248.0         # the lower flange's tongue rises to here inside the torso
FLANGE_LOWER_H = 8.0       # the lower flange ring below the split; its tongue above it is RING_T
Z_TORSO_TOP = 420.0        # the coat's neck opening
Z_DECK = 400.0             # top face of the turntable deck
DECK_T = 6.0
RING_T = 8.0               # interface rings unioned into the shell
Z_HEAD = 478.0             # tilt axis and head centre
HEAD_R = 40.0              # the statue's head is 44 mm deep in front of the ear line; nothing nods now, this only sizes the shroud's top
Z_HAT = 500.0              # the statue's brim at the sides (0.713 H); the head and hat turn together, nothing nods
Z_TOP = 700.0              # the statue's height: its ear line then lands on the tilt axis

# --- shell profiles, (radius, z) from the bottom up --------------------------------------
# outer skins only; shell_r walks these.
BASE_PROFILE = [(112.0, 0.0), (125.0, 90.0), (112.0, 180.0), (95.0, Z_BELT), (95.0, Z_BASE_TOP)]
# broad shoulders up to 365 so the phone's top corners clear the wall; the beard collar hides them
TORSO_PROFILE = [(95.0 + CLEAR_SHELL + WALL, Z_BELT), (95.0 + CLEAR_SHELL + WALL, Z_BASE_TOP), (104.0, 280.0), (105.0, 320.0), (100.0, 360.0),
                 (96.0, 393.0), (84.0, 408.0), (76.0, Z_TORSO_TOP)]
HAT_BRIM_T = 8.0
BEARD_TOP_Z = 443.0
BEARD_BOTTOM_BACK_Z = 340.0    # the collar's back hangs over the exhaust fan (348..388) as the spec asks

SECTION_Z = {
    "base": (0.0, Z_BASE_TOP),
    "torso": (Z_BELT, Z_TORSO_TOP),
    "beard": (BEARD_BOTTOM_BACK_Z, BEARD_TOP_Z),      # the cape at the back hangs lowest
    "head_back": (Z_HEAD - HEAD_R, Z_HEAD + HEAD_R),
    "face": (Z_HEAD - HEAD_R, Z_HEAD + HEAD_R),
    "hat": (Z_HAT, Z_TOP),
}


def shell_r(profile, z):
    """Outer radius of a revolved profile at height z, linear between points.

    Where the profile steps (two points at one z) the larger radius wins, so a ring sized
    from it never lands inside a step.
    """
    pts = sorted(profile, key=lambda p: p[1])
    if z <= pts[0][1]:
        return pts[0][0]
    if z >= pts[-1][1]:
        return pts[-1][0]
    found = []
    for (r0, z0), (r1, z1) in zip(pts, pts[1:]):
        if z0 <= z <= z1:
            found.append(max(r0, r1) if z1 == z0 else r0 + (r1 - r0) * (z - z0) / (z1 - z0))
    return max(found)


def ring_r_out(profile, z0, z1=None):
    """Outer radius for an interface ring spanning z0..z1: embedded 1.2 mm into the wall at the
    ring's narrowest height, so it never breaks through the skin where the wall tapers."""
    zs = (z0,) if z1 is None else (z0, z1)
    return min(shell_r(profile, z) for z in zs) - WALL + 1.2


# --- belt joint ---------------------------------------------------------------------------
DIVIDER_PROUD = 0.3        # the divider stands this much above the base's rim so the belt screws load the PU bead, not the rim
GLAND_D = 12.5             # an M12 cable gland's thread, with clearance
GLAND_POS = [(-40.0, 30.0), (-40.0, -30.0)]
CHASSIS_T = 4.0
Z_CHASSIS = Z_BASE_TOP + RING_T   # 256, sits on the torso flange

# --- phone and window ---------------------------------------------------------------------
PHONE_L, PHONE_W, PHONE_T = 138.3, 67.1, 7.1
PHONE_CAM_FROM_END = 11.0      # rear camera centre from the phone's end
PHONE_CAM_FROM_SIDE = 11.0     # ... and from its side
LENS_CLIP_T = 12.0             # clip-on lens in front of the back glass
LENS_CLIP_W = 28.0             # the clip's width across the phone; measure the clip on arrival
ACRYLIC_T = 3.0
LENS_GAP = 2.0
WINDOW_W, WINDOW_H = 40.0, 44.0            # 3.7 mm of coat left above the window under the ring's top
WINDOW_Z_BIAS = 18.0           # window centre above the lens: the view needed is mostly above horizontal, and the belt joint is just below
# the phone is centred; its camera sits CAM_Y off the centreline, which the aiming
# calibration absorbs like every other fixed offset
PHONE_Y_OFFSET = 0.0
CAM_Y = PHONE_Y_OFFSET + PHONE_W / 2 - PHONE_CAM_FROM_SIDE   # 22.55
SLED_WALL = 3.0
# the sled's tray hangs through a cutout in the chassis and stands just above the divider: that is
# the only way 138 mm of phone fits between the belt and the deck in this statue
SLED_FLOOR_Z = Z_BASE_TOP + DIVIDER_PROUD + 1.0        # 249.3
PHONE_BOTTOM_Z = SLED_FLOOR_Z + SLED_WALL              # 252.3
Z_LENS = PHONE_BOTTOM_Z + PHONE_CAM_FROM_END           # 263.3
LENS_FRONT_X = 89.4 - WALL - ACRYLIC_T - LENS_GAP      # 82: the statue's front skin at the window is 89.4
PHONE_BACK_X = LENS_FRONT_X - LENS_CLIP_T              # back glass
PHONE_FRONT_X = PHONE_BACK_X - PHONE_T                 # screen
SLED_FOOT_H = 5.0              # the feet are runners on the chassis; one screw from above locks the sled at home
SLED_GUIDE_H = 3.0             # ribs on the chassis either side of the feet

# --- electronics --------------------------------------------------------------------------
ESP32 = (55.0, 28.0)
XL4015_HOLES = (43.0, 15.0)
XL4015_HOLE_D = 3.2
EDECK_T = 4.0                               # EDECK_L and EDECK_W are with the statue's numbers
# board footprints on the deck, (x0, y0, x1, y1) relative to EDECK_POS: two columns, A at the back
# Two columns on the 100 x 92 deck: the wide boards down the back, the three MOSFET modules up
# the front, three millimetres between every pair. The ESP32 is the awkward one at 55 mm - it
# sets the back column's width and the front column starts three millimetres past it.
EDECK_LAYOUT = {
    "xl4015_a": (-50.0, -46.0, 4.0, -23.0),
    "xl4015_b": (-50.0, -20.0, 4.0, 3.0),
    "fuse": (-50.0, 6.0, -20.0, 15.0),
    "esp32": (-50.0, 18.0, 5.0, 46.0),
    "mosfet_b": (8.0, -46.0, 42.0, -19.0),
    "mosfet_c": (8.0, -16.0, 42.0, 11.0),
    "mosfet_a": (8.0, 18.0, 42.0, 45.0),
}
# deck screws, relative to EDECK_POS: three points (a plate on three cannot rock) in the gaps
# the layout leaves; the deck's back end rests on two plain posts instead, because a standoff
# under its back corners would stand off the chassis and into the wall
EDECK_HOLES = [(46.0, -34.0), (46.0, 24.0), (-8.0, 6.0)]    # in the free strip and the gap over the
                                                            # fuse, under the ESP32 cradle's near rail.
                                                            # The +Y one came in from 34: at 34 it stood
                                                            # at (46, 39) and the chassis's bore for the
                                                            # filler cap swallowed its standoff whole
EDECK_POSTS = [(-46.0, -34.0), (-46.0, 34.0)]               # bare posts under the deck's back end
MOSFET_HOLES = (28.0, 21.0)       # measure the modules on arrival; the ESP32 has no standard holes and sits in a printed cradle
EDECK_STANDOFF = 8.0
FAN = 40.0
FAN_T = 10.0
FAN_PITCH = 32.0
VENT_IN_W, VENT_IN_H = 40.0, 20.0          # the intake, cut in the belt ring's back at Z_VENT_IN

# --- turntable ----------------------------------------------------------------------------
BEARING_SQ = 60.0
BEARING_T = 6.0
BEARING_PITCH = 48.0
BEARING_HOLE = 3.4
SHAFT_OD, SHAFT_ID = 21.0, 13.0   # bore: tube + three wires + 2 mm, spec section 6
DECK_R = 80.0                  # the statue's front cavity at the deck is 85; a lobe towards -Y covers the servo hangers
DECK_LOBE = dict(angle=270.0, half=45.0, r=86.0)   # the hangers' corners reach 83.3; the cavity there is 95
DECK_BACK_R = 72.0             # over 140..220 degrees the coat's back is only 74..80 out
RING_R_IN = 50.0
RING_R_OUT = 58.0              # the ring is a narrow annulus standing on four legs down to the chassis (a cage): nothing above the belt is fixed shell
CAGE_LEG = 12.0                # the legs' square section
CAGE_LEG_R = 60.0              # the legs' centres; the deck's screws sit on the same points
DECK_SCREW_R = CAGE_LEG_R
DECK_SCREW_ANGLES = [82.0, 98.0, 235.0, 250.0]    # the cage's legs: clear of the electronics deck (|y| > 50), the pan servo (x -5..35, y -70..-50), the stop pins (+-70.7 at r 60) and the phone
PLATE_R = 50.0
PLATE_T = 5.0
Z_PLATE_TOP = Z_DECK + BEARING_T + PLATE_T           # 411
# --- pan drive: the servo hangs under the deck, shaft pointing down, and the parallelogram
#     lives below the deck where the torso is wide. The plate's front stop tab carries a column
#     down through an arc slot in the deck to the link. Nothing of the drive is above the deck.
PAN_SERVO_XY = (5.0, -60.1)    # servo axis; the body runs +X from the shaft end (x -5 .. 35, y -70.1 .. -50.1): 1 mm outside the column's sweep
PAN_OFFSET = (PAN_SERVO_XY[0] ** 2 + PAN_SERVO_XY[1] ** 2) ** 0.5   # the link's eye-to-eye length, 60.31
CRANK_L = 30.0                 # shorter than the servo offset, so neither bar can ever cross the pan axis
CRANK_REST_DEG = 0.0           # both cranks point +X (front) at rest
Z_PAN_SHAFT_FACE = 340.0       # the servo's output face, looking down; body top 380.5, under the deck; low enough that the link sweeps where the coat is 98 wide
CRANK_T = 5.0
LINK_T = 3.0
PIN_BORE = 3.2                 # link eyes on M3 shanks; ream after printing
PIN_BOSS_H = 0.5
PIN_BOSS_D = 8.0
Z_CRANK_TOP = Z_PAN_SHAFT_FACE               # 340; the crank's top is the shaft face, the horn sits in its pocket
Z_CRANK_BOTTOM = Z_CRANK_TOP - CRANK_T       # 335
Z_LINK_TOP = Z_CRANK_BOTTOM - PIN_BOSS_H     # 334.5; a boss on crank and foot takes the screw's clamp, not the link
Z_LINK_BOTTOM = Z_LINK_TOP - LINK_T          # 331.5
SHAFT_BOTTOM = Z_LINK_BOTTOM - 5.0           # the tube leaves the shaft below the link's plane
LINK_EYE_R = PIN_BORE / 2 + 3.0
PAN_COLUMN = (44.0, 52.0, 8.0)               # radial extent and width of the plate's hanging column
PAN_FOOT_R_IN = CRANK_L - 4.0                # the column's foot reaches inward to the pin at CRANK_L
DECK_SLOT = (PAN_COLUMN[0] - CLEAR, (PAN_COLUMN[1] ** 2 + (PAN_COLUMN[2] / 2) ** 2) ** 0.5 + CLEAR, 76.0)   # r0, r1 (the box's corners), half-angle
PAN_HANGER = 10.0                            # square columns under the deck the servo tabs screw to
PAN_SERVO_FIT = 0.5                          # the body slides up between the hangers; CLEAR is too tight over 40 mm
PAN_STOP_DEG = 65.0
STOP_POST_R = 60.0
STOP_POST_D = 6.0
STOP_PIN_SEAT_D = STOP_POST_D + 0.4    # the seat in the deck; glue the pin in, do not press it


def stop_pin_deg():
    """Where a stop pin's centre sits so the plate's tab meets it at exactly PAN_STOP_DEG."""
    return PAN_STOP_DEG + math.degrees(math.asin((STOP_TAB_W / 2) / STOP_POST_R)) + math.degrees(math.asin((STOP_POST_D / 2) / STOP_POST_R))


def crank_pins(deg):
    """Plate pin and servo pin at a pan angle: both cranks are CRANK_L at CRANK_REST_DEG + deg."""
    a = math.radians(CRANK_REST_DEG + deg)
    v = (CRANK_L * math.cos(a), CRANK_L * math.sin(a))
    return v, (PAN_SERVO_XY[0] + v[0], PAN_SERVO_XY[1] + v[1])
STOP_PIN_TOP = Z_PLATE_TOP - 1.5          # separate pins glued into the deck: 3.5 mm of the tab's 5, 1.5 under the yoke
STOP_PIN_DEPTH = 6.0
STOP_TAB_W = 6.0
TILT_STOP = (-35.0, 45.0)

# --- servos: (length, width, height), tab span, tab thickness, tab height from the bottom,
#     shaft offset from the near end along the length, hole pitch (along length, across)
DS3218 = dict(body=(40.0, 20.0, 40.5), tab_span=54.5, tab_t=2.5, tab_z=28.0, shaft_off=10.0,
              holes=(49.5, 10.0))
HORN_D = 21.0
HORN_T = 2.5
HORN_SCREW_R = 7.0
# pan servo footprint in plan, with its tabs, plus 2 mm: the deck ring is cut away here
_L = DS3218["body"][0]
def pan_hangers():
    """Plan positions of the four columns under the deck the pan servo's tabs screw to."""
    along, across = DS3218["holes"]
    cx = PAN_SERVO_XY[0] - DS3218["shaft_off"] + _L / 2
    return [(cx + dx, PAN_SERVO_XY[1] + dy) for dx in (-along / 2, along / 2) for dy in (-across / 2, across / 2)]


PAN_RING_CUT = ((min(x for x, _ in pan_hangers()) - PAN_HANGER / 2 - 2.0, min(y for _, y in pan_hangers()) - PAN_HANGER / 2 - 2.0),
                (max(x for x, _ in pan_hangers()) + PAN_HANGER / 2 + 2.0, max(y for _, y in pan_hangers()) + PAN_HANGER / 2 + 2.0))

# --- the yoke ring under the shroud, and the nozzle's bore ----------------------------------
YOKE_RING_R_IN = 44.0          # the yoke stands on a ring on the plate's rim
YOKE_RING_T = 3.0
YOKE_SCREW_R = 46.7
YOKE_SCREW_ANGLES = [45.0, 135.0, 225.0, 315.0]
NOZZLE_D = 8.0
MOUTH_D = NOZZLE_D + 0.4       # the mouth is the nozzle's outboard bearing
# --- neck shroud: a cylinder on the plate that turns with the head and carries it; see the statue block
SHROUD_BASE_Z = Z_PLATE_TOP + YOKE_RING_T           # 414: sits on the yoke's ring, held by the same four screws
JET_D = NOZZLE_D + 4.0                               # the jet's keep-out: nozzle bore plus spread over 30 mm
JET_NOTCH_HALF_DEG = 9.0                             # the shroud's front is notched for the jet over the whole tilt range
TUBE_OD = 6.0
TUBE_BEND_R = 15.0             # 6 x 4 PU tube's static minimum; the holder's barb faces -X so one such bend reaches the axis

# --- base, wet zone -----------------------------------------------------------------------
# The bought 1 L bottle lies across the whole belly on the floor plate; the pump and the valve
# stand in the trouser legs, hanging from brackets under the floor plate. Below them the boots
# hold sand. Leg centres are measured on the statue's cavity mesh by the statue stage and
# written to out/statue/features.json ("legs"); the numbers here are the fit report's estimate.
BOTTLE = (97.0, 195.0, 71.0)                # a rectangular 1 L HDPE lab bottle lying on its wide face: x, y (along the belly), z. The belly takes 195 across at its corners; buy one at most this long (or with rounded ends) and measure it
# Its shoulder is what makes 195 fit: the coat draws in as it rises to the belt, and at the
# bottle's top the belly takes a half-length of only 84.5 against a square corner's 97.5. The
# taper below pulls that corner back inside. CHECK IT ON THE BOTTLE BOUGHT - a squarer one must
# be 170 long at most, whatever its label says.
BOTTLE_SHOULDER_H = 25.0                    # the top of the bottle tapers in over this height
BOTTLE_SHOULDER_IN = (8.0, 16.0)            # ... by this much on each side (x) and each end (y)
BOTTLE_XY = (2.0, 0.0)                      # 2 mm forward of centre: rear and front shoulder corners each clear the coat by about 2.5 mm; the hose passes its end
BOTTLE_Z0 = Z_FLOOR + 4.0 + 2.0             # on the floor plate's cradle
BOTTLE_THREAD_MAJOR = 38.0                  # its neck, towards +Y; CAN_THREAD_MAJOR follows it
CAN_THREAD_MAJOR = 38.0
CAN_THREAD_PITCH = 3.0
CAN_THREAD_LEN = 12.0
CAN_NECK_ID = 30.0
PUMP = (45.0, 40.0, 95.0)                   # a micro 12 V diaphragm pump (about 1 L/min, 7 bar) standing in the left leg; x, y, z. Re-measure
PUMP_FEET = (30.0, 30.0)                    # its mounting holes; re-measure
LEG_LEFT_XY = (0.0, 80.0)                   # leg cavity centres at Z_FLOOR - 50, from the fit report; the statue stage measures them
LEG_RIGHT_XY = (0.0, -80.0)
LEG_R = 38.0                                # the legs' free radius there
PUMP_Z0 = Z_FLOOR - PUMP[2] - 5.0           # hangs under the floor plate on a bracket, 5 mm below the plate
VALVE = (45.0, 25.0, 55.0)
VALVE_Z0 = Z_FLOOR - VALVE[2] - 5.0
VALVE_STRAP = (12.0, 3.0)                   # a bar across the valve's body, two M3s into the bracket's inserts
PUMP_TIE_SLOTS = True                       # cable-tie slots hold the pump to its bracket
FLOAT_HOLE_D = 12.0
DIP_TUBE_D = 8.0
FILLER_D = 14.0                             # the neck's 30 mm bore must also pass the float switch and the dip tube
FILLER_VIA_TOP = True                       # a hose from the tank head's port to a filler neck in the divider's front, reached from the top with the bell off
HOSE_OD = 8.0                               # the filler hose, tank head to neck. Two gaps size it and
                                            # neither gives: it rises beside the stub at y 86.5, where
                                            # the belt ring's bore is only 90.9 out, and it crosses the
                                            # 13 mm between the bottle's top (227) and the divider (240)
HOSE_BEND_R = 5.0                           # the tightest corner the route turns, at both fittings, and
                                            # all the 13 mm leaves. A plain PVC hose of HOSE_OD wants
                                            # three times that: silicone of this bore will take it, a
                                            # corrugated hose certainly, a stiff PVC one not
HOSE_BARB_D = 6.5                           # the barb at both ends of that hose: its 5 mm bore and a
                                            # millimetre and a half of stretch. Bored HOSE_BARB_D - 2,
                                            # so filling is slow - a litre through 5 mm on the 0.1 m of
                                            # head between the cap and an empty bottle runs at about
                                            # 1 L/min and falls to 0.6 as the bottle fills: call it a
                                            # minute and a half with a funnel, and the air it displaces
                                            # leaves by the tank head's vent into the belly, not back
                                            # up the hose
HOSE_BARB_L = 10.0                          # how much of each barb the hose grips
HOSE_BARB_LIP = 0.5                         # how far each barb's two ridges stand off its shank; the
                                            # divider's hole has to pass them, the neck going in from above
FILLER_NECK_XY = (42.0, 54.0)               # on the divider, on the bottle's neck side and beside the sled's
                                            # path; the ring is notched for it. x is what lets the hose rise
                                            # to it inside the belt ring's bore - at 48 the neck sat 0.2 mm
                                            # inside that ellipse and no hose could reach it from below.
                                            # y keeps the cap out of the sled's tray. See mech/torso.py
FILLER_CAP_THREAD_MAJOR = 22.0              # 2.8 mm of wall at the neck's thread roots
FILLER_CAP_PITCH = 2.0
SAND_Z_TOP = Z_FLOOR - PUMP[2] - 12.0       # sand fills the boots up to here, under the pump and the valve
DRAIN_ARCH_W, DRAIN_ARCH_H = 30.0, 12.0
STAKE_HOLE_D = 8.0
STAKE_HOLE_R = 95.0

# --- the statue -----------------------------------------------------------------------------
# The shell is an image-to-3D reconstruction of the user's reference statue (cad/in/, not
# committed), converted to this frame, mirrored about its body axis, scaled to Z_TOP. Everything
# below is measured on it at 700 mm; the statue stage rewrites out/statue/features.json and the
# tests read that, not these, where they differ.
STATUE_GLB = "in/gnome_ai.glb"
STATUE_AXIS_Y = 8.0 * 700.0 / 589.0        # the body's axis sits +8 mm (at 589) from the boots' centre; mirrored away
STATUE_FEATURES = {                         # fraction of height, from the fit analysis
    "boot_top": 0.115, "hem": 0.207, "hands_bottom": 0.302, "belt": 0.367, "hands_top": 0.421,
    "beard_bottom": 0.441, "chin": 0.589, "mouth": 0.603, "nose": 0.645, "eye": 0.679,
    "ear": 0.684, "brim_side": 0.713, "brim_front": 0.735,
}
Z_TURN = 309.0                              # the turning bell starts at the beard's bottom (0.441 H)
TURN_GAP = 2.0                              # air between the bell's rim and the fixed coat below it
# The bell is everything above Z_TURN except the sleeves: the coat's side panels with the mittens,
# |y| >= PANEL_Y, stay fixed up to PANEL_TOP so the arms do not twist with the head. The bell
# sweeps +-PAN_STOP_DEG inside them; where its lower front (the beard's ends) would touch a
# panel, the statue stage lathes the bell there and reports it.
PANEL_Y = 105.0                             # at 95 the beard's front had to be lathed 12 mm and 14 mm slots opened beside the chest; at 105 it loses 2.3 mm
PANEL_TOP = 400.0
PANEL_BOTTOM = 196.0                        # the mittens' lower edge; below Z_BELT the panel belongs to the base halves
SECTIONS_STATUE = {                         # printable pieces, each within the 256 mm bed
    "base_left": (0.0, Z_BELT), "base_right": (0.0, Z_BELT),        # split at y = 0, sand ballast inside
    "hand_left": (PANEL_BOTTOM, Z_BELT), "hand_right": (PANEL_BOTTOM, Z_BELT),   # mitten caps glued to the base halves
    "torso": (Z_BELT, Z_TURN - TURN_GAP),                             # the coat's belt ring, fixed
    "panel_left": (Z_BELT, PANEL_TOP), "panel_right": (Z_BELT, PANEL_TOP),      # sleeves and shoulders' sides, fixed, glued to the ring
    "beard": (Z_TURN, 412.0), "head": (412.0, Z_HAT), "hat": (Z_HAT, Z_TOP),    # the turning bell, glued
}
# With the bell off, everything inside is reached from the top: there is no belly hatch. The
# window is cut in the ring; the exhaust fan sits on the left panel's inner face, the intake
# in the ring's back.
# The fan hangs under the deck and blows upward through a hole in it; the intake is in the belt
# ring's back and the air leaves through the bell's turning gap and the beard's parting, a chimney.
# The sleeves are too thin to hold a fan and everything else above the belt turns.
FAN_XY = (-49.0, -20.0)                     # the fan's axis, under the deck: its hole stops short of the bearing's square, inside the deck's trimmed back (r 71 of 72)
FAN_HOLE_D = FAN - 4.0
Z_VENT_IN = 272.0
# the belt joint follows the coat's section: an ellipse, not a circle
BELT_RX, BELT_RY = 74.0, 105.0             # outer, at Z_BELT; the assembler clips every interface part to the cavity anyway
BELT_IN_RX, BELT_IN_RY = 60.0, 91.0
BELT_SCREW_ANGLES = [55.0, 140.0, 220.0, 305.0]   # the front pair sits away from the filler neck at (48, 54)
CHASSIS_RX, CHASSIS_RY = 70.0, 100.0
# the dry zone, re-stacked
FRONT_SKIN_X_AT_WINDOW = 89.4               # the statue's front at the window (LENS_FRONT_X is derived from it above)
EDECK_L, EDECK_W = 100.0, 92.0             # its corner sits at 0.68 of the chassis ellipse
EDECK_POS = (0.0, 5.0)                      # 5 mm off the axis: it clears the deck cage's
                                            # 235 and 250 degree legs without a notch in either
# the turning unit: the shroud carries the beard, head and hat; the pan drive is unchanged
SHROUD_R_OUT = 52.0                         # no arms to clear any more; the chin's cavity is 57
SHROUD_TOP_Z = 454.0                        # closed top with a hole for the tube and wires
SHROUD_SCREWS_Z = 440.0                     # four radial M3 from outside, hidden in the beard's locks
SHROUD_SCREW_ANGLES = [60.0, 120.0, 240.0, 300.0]
SHROUD_ACCESS_D = 7.0                       # the roof is bored this wide over each of the four screws
                                            # that hold the shroud down: they are driven from inside
                                            # the cup and the driver leaves through the roof
# the nozzle tilts on a micro servo inside the beard, through the beard's parting under the mouth
MG92B = dict(body=(22.8, 12.4, 28.5), tab_span=32.5, tab_t=2.0, tab_z=19.0, shaft_off=6.0, holes=(27.8, 0.0))
MICRO_HORN_D = 14.0
Z_MOUTH = 424.0                             # the statue's mouth (0.603 H)
NOZZLE_PIVOT = (62.0, 0.0, 424.0)           # tilt axis of the nozzle arm, along Y, just inside the beard
NOZZLE_ARM_L = 20.0                         # pivot to the nozzle's tip at the mouth's skin, x 82
NOZZLE_SLOT_W = 14.0                        # the parting in the beard the nozzle arm (12 wide) swings through
