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
M4_PIN = 4.0
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
# outer skins only; shell_r walks these. The base's raised floor is a separate revolve row.
BASE_PROFILE = [(112.0, 0.0), (125.0, 90.0), (112.0, 180.0), (95.0, Z_BELT), (95.0, Z_BASE_TOP)]
BASE_FLOOR_R = 108.0
# broad shoulders up to 365 so the phone's top corners clear the wall; the beard collar hides them
TORSO_PROFILE = [(95.0 + CLEAR_SHELL + WALL, Z_BELT), (95.0 + CLEAR_SHELL + WALL, Z_BASE_TOP), (104.0, 280.0), (105.0, 320.0), (100.0, 360.0),
                 (96.0, 393.0), (84.0, 408.0), (76.0, Z_TORSO_TOP)]
TORSO_R_TOP = 76.0            # neck opening; the pan linkage sweeps inside it
HAT_BRIM_R = 70.0
HAT_BRIM_T = 8.0
HAT_CONE_R = 50.0
HAT_TIP_R = 4.0
HAT_BEND = 15.0            # how far the tip leans forward
BEARD_TOP_Z = 443.0
BEARD_BOTTOM_FRONT_Z = 350.0
BEARD_BOTTOM_BACK_Z = 340.0    # the collar's back hangs over the exhaust fan (348..388) as the spec asks
BEARD_T = 3.0
BEARD_R_OUT_TOP = TORSO_R_TOP + 8.0    # collar's outer radius at its top, 84
BEARD_R_IN_TOP = BEARD_R_OUT_TOP - BEARD_T

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
FLANGE_R_IN = 80.0
FLANGE_SCREW_R = 86.0
FLANGE_SCREW_ANGLES = [45.0, 135.0, 225.0, 315.0]
DIVIDER_PROUD = 0.3        # the divider stands this much above the base's rim so the belt screws load the PU bead, not the rim
GLAND_D = 12.5             # an M12 cable gland's thread, with clearance
GLAND_POS = [(-40.0, 30.0), (-40.0, -30.0)]
CHASSIS_T = 4.0
CHASSIS_R = 90.0
CHASSIS_SCREW_ANGLES = [40.0, 140.0, 220.0, 320.0]   # off the belt screws, the sled and the electronics deck
CHASSIS_SCREW_R = FLANGE_SCREW_R - 2.0
Z_CHASSIS = Z_BASE_TOP + RING_T   # 246, sits on the torso flange

# --- phone and window ---------------------------------------------------------------------
PHONE_L, PHONE_W, PHONE_T = 138.3, 67.1, 7.1
PHONE_CAM_FROM_END = 11.0      # rear camera centre from the phone's end
PHONE_CAM_FROM_SIDE = 11.0     # ... and from its side
LENS_CLIP_T = 12.0             # clip-on lens in front of the back glass
LENS_CLIP_W = 28.0             # the clip's width across the phone; measure the clip on arrival
ACRYLIC_T = 3.0
LENS_GAP = 2.0
WINDOW_W, WINDOW_H = 40.0, 48.0
WINDOW_Z_BIAS = 18.0           # window centre above the lens: the view needed is mostly above horizontal, and the belt joint is just below
HOOD_PITCH_DEG = 10.0
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
XL4015 = (54.0, 23.0)
XL4015_HOLES = (43.0, 15.0)
XL4015_HOLE_D = 3.2
MOSFET = (34.0, 27.0)
EDECK_T = 4.0                               # EDECK_L and EDECK_W are with the statue's numbers
EDECK_POS = (-30.0, 0.0)       # centre, x-y; it stands on the chassis
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
EDECK_HOLES = [(46.0, -30.0), (46.0, 30.0), (-8.0, 10.0)]   # in the free strip and the gap over the fuse
EDECK_POSTS = [(-46.0, -34.0), (-46.0, 34.0)]               # bare posts under the deck's back end
MOSFET_HOLES = (28.0, 21.0)       # measure the modules on arrival; the ESP32 has no standard holes and sits in a printed cradle
EDECK_STANDOFF = 8.0
FAN = 40.0
FAN_T = 10.0
FAN_PITCH = 32.0
VENT_IN_W, VENT_IN_H = 40.0, 20.0

# --- turntable ----------------------------------------------------------------------------
BEARING_SQ = 60.0
BEARING_T = 6.0
BEARING_OPEN = 32.0
BEARING_PITCH = 48.0
BEARING_HOLE = 3.4
SHAFT_OD, SHAFT_ID = 21.0, 13.0   # bore: tube + three wires + 2 mm, spec section 6
DECK_R = 80.0                  # the statue's front cavity at the deck is 85; a lobe towards -Y covers the servo hangers
DECK_LOBE = dict(angle=270.0, half=45.0, r=86.0)   # the hangers' corners reach 83.3; the cavity there is 95
DECK_BACK_R = 72.0             # over 140..220 degrees the coat's back is only 74..80 out
RING_R_IN = 50.0
RING_R_OUT = 58.0              # the ring is a narrow annulus; four webs reach the wall; the phone's top passes outside it
RING_WEB_W = 8.0
DECK_SCREW_R = 54.0
DECK_SCREW_ANGLES = [90.0, 150.0, 210.0, 240.0]   # off the column's arc slot (front +-76), the hangers (250..300) and the phone
PLATE_R = 50.0
PLATE_T = 5.0
Z_PLATE_TOP = Z_DECK + BEARING_T + PLATE_T           # 411
# --- pan drive: the servo hangs under the deck, shaft pointing down, and the parallelogram
#     lives below the deck where the torso is wide. The plate's front stop tab carries a column
#     down through an arc slot in the deck to the link. Nothing of the drive is above the deck.
PAN_SERVO_XY = (5.0, -60.1)    # servo axis; the body runs +X from the shaft end (x -5 .. 35, y -70.1 .. -50.1): 1 mm outside the column's sweep
PAN_OFFSET = (PAN_SERVO_XY[0] ** 2 + PAN_SERVO_XY[1] ** 2) ** 0.5   # the link's eye-to-eye length, 60.21
CRANK_L = 30.0                 # shorter than the servo offset, so neither bar can ever cross the pan axis
CRANK_REST_DEG = 0.0           # both cranks point +X (front) at rest
Z_PAN_SHAFT_FACE = 340.0       # the servo's output face, looking down; body top 380.5, under the deck; low enough that the link sweeps where the coat is 98 wide
CRANK_T = 5.0
LINK_T = 3.0
PIN_BORE = 3.2                 # link eyes on M3 shanks; ream after printing
PIN_BOSS_H = 0.5
PIN_BOSS_D = 8.0
Z_CRANK_TOP = Z_PAN_SHAFT_FACE               # 353; the crank's top is the shaft face, the horn sits in its pocket
Z_CRANK_BOTTOM = Z_CRANK_TOP - CRANK_T       # 348
Z_LINK_TOP = Z_CRANK_BOTTOM - PIN_BOSS_H     # 347.5; a boss on crank and foot takes the screw's clamp, not the link
Z_LINK_BOTTOM = Z_LINK_TOP - LINK_T          # 344.5
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
MG996R = dict(body=(40.7, 19.7, 42.9), tab_span=53.0, tab_t=2.5, tab_z=28.0, shaft_off=10.0,
              holes=(48.5, 10.0))
HORN_D = 21.0
HORN_T = 2.5
HORN_SCREW_R = 7.0
# pan servo footprint in plan, with its tabs, plus 2 mm: the deck ring is cut away here
_L, _W, _H = DS3218["body"]
_tab = (DS3218["tab_span"] - _L) / 2
def pan_hangers():
    """Plan positions of the four columns under the deck the pan servo's tabs screw to."""
    along, across = DS3218["holes"]
    cx = PAN_SERVO_XY[0] - DS3218["shaft_off"] + _L / 2
    return [(cx + dx, PAN_SERVO_XY[1] + dy) for dx in (-along / 2, along / 2) for dy in (-across / 2, across / 2)]


PAN_RING_CUT = ((min(x for x, _ in pan_hangers()) - PAN_HANGER / 2 - 2.0, min(y for _, y in pan_hangers()) - PAN_HANGER / 2 - 2.0),
                (max(x for x, _ in pan_hangers()) + PAN_HANGER / 2 + 2.0, max(y for _, y in pan_hangers()) + PAN_HANGER / 2 + 2.0))

# --- head, ears, tilt ---------------------------------------------------------------------
EAR_R = 12.0                   # both ears are the coupler's diameter
EAR_OUT_Y = HEAD_R + 6.0       # outer face of the ear boss / coupler
YOKE_GAP = 1.0
YOKE_ARM_T = 8.0
YOKE_ARM_W = 36.0              # 3.5 mm of wall either side of the 25 mm hex's corners
YOKE_RING_R_IN = 44.0          # the yoke stands on a ring on the plate's rim
YOKE_RING_T = 3.0
YOKE_SCREW_R = 46.7
YOKE_SCREW_ANGLES = [45.0, 135.0, 225.0, 315.0]
COUPLER_D = 24.0               # no boss: the coupler passes the wall bore from outside
HEAD_BORE_D = COUPLER_D + 2 * CLEAR
HORN_ACCESS_D = 4.6            # counterbores down the coupler for the horn screws' driver
HORN_SCREWS_USED = (0.0, 180.0)   # two of the horn's four holes
INSERT_M4_D = 5.6
INSERT_M4_DEPTH = 8.0
COUPLER_HEX_AF = 25.0          # wider than the shaft: the coupler enters from outside through this hex
TILT_SERVO_SHAFT_Y = 21.0      # servo shaft face inside the head, +Y side; the body's far corner must pass the face opening
TILT_SERVO_UP = True           # the body's long side runs up from the shaft, so its tabs sit where the sphere is wide
BULKHEAD_Y = TILT_SERVO_SHAFT_Y - MG996R["body"][2] + MG996R["tab_z"]   # 6.1; the cradle plate's +Y face, the tabs sit on it
BULKHEAD_T = 2.5
BULKHEAD_BOSS_D = 8.5          # bosses round the four insert holes, INSERT_DEPTH + 1 tall, on the -Y side
# the cradle is assembled with the servo on the bench and slides in through the face opening
# along -X, into two rails on the back of the head; a lip on the lower rail and a stop block on
# the face cap box it in. No screw is driven inside the head.
CRADLE_X = (-12.0, 14.0)
CRADLE_Z = (458.0, 517.0)      # spans the servo's tab bosses with the body running up; the top corners stay inside the sphere
RAIL_T = 3.0                   # the rails' lips either side of the plate
RAIL_H = 6.0                   # how far a rail reaches above/below the plate's edge
RAIL_LIP_L = 2.5               # the lower rail's front lip, which the plate drops in behind
FACE_STOP_Z = (506.0, 516.0)   # the face cap's stop block bears on the plate's top front edge
HEAD_OPENING_R = 15.0          # tube and wires enter through the bottom
FACE_SPLIT_X = 20.0            # the face is the cap in front of this plane
FACE_LIP_T = 2.0
FACE_LIP_L = 5.0
Z_MOUTH = Z_HEAD - 8.0         # 470: high enough that the jet at full nose-down clears the turntable
NOZZLE_D = 8.0
MOUTH_D = NOZZLE_D + 0.4       # the mouth is the nozzle's outboard bearing
NOZZLE_BOSS_Y = 13.4           # an r 3 driver on the screw passes the cradle rails with 1 mm to spare
NOZZLE_HOLDER_X = (15.0, 28.0)
TILT_STOP_TAB_R = 15.0
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
BOTTLE_XY = (0.0, 0.0)                      # centred: its corners are the tightest thing in the belly
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
PUMP_XY = LEG_LEFT_XY
PUMP_Z0 = Z_FLOOR - PUMP[2] - 5.0           # hangs under the floor plate on a bracket, 5 mm below the plate
VALVE = (45.0, 25.0, 55.0)
VALVE_XY = LEG_RIGHT_XY
VALVE_Z0 = Z_FLOOR - VALVE[2] - 5.0
VALVE_STRAP = (12.0, 3.0)                   # a bar across the valve's body, two M3s into the bracket's inserts
PUMP_TIE_SLOTS = True                       # cable-tie slots hold the pump to its bracket
FLOAT_HOLE_D = 12.0
DIP_TUBE_D = 8.0
FILLER_D = 14.0                             # the neck's 30 mm bore must also pass the float switch and the dip tube
FILLER_VIA_TOP = True                       # a hose from the tank head's port to a filler neck in the divider's front, reached from the top with the bell off
FILLER_NECK_XY = (60.0, -58.0)              # on the divider, beside the sled's path: at y 0 the cap would
                                            # stand inside the sled's tray. See the note in mech/torso.py
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
PANEL_Y = 95.0
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
FAN_PANEL = "left"
FAN_XZ = (-20.0, 370.0)                     # the fan's centre on the panel (x, z); its axis along Y
Z_VENT_IN = 272.0
# the belt joint follows the coat's section: an ellipse, not a circle
BELT_RX, BELT_RY = 74.0, 105.0             # outer, at Z_BELT; the assembler clips every interface part to the cavity anyway
BELT_IN_RX, BELT_IN_RY = 60.0, 91.0
BELT_SCREW_ANGLES = [40.0, 140.0, 220.0, 320.0]
CHASSIS_RX, CHASSIS_RY = 70.0, 100.0
# the dry zone, re-stacked
FRONT_SKIN_X_AT_WINDOW = 89.4               # the statue's front at the window (LENS_FRONT_X is derived from it above)
EDECK_L, EDECK_W = 100.0, 92.0             # its corner sits at 0.68 of the chassis ellipse
EDECK_POS = (0.0, 0.0)
# the turning unit: the shroud carries the beard, head and hat; the pan drive is unchanged
SHROUD_R_OUT = 52.0                         # no arms to clear any more; the chin's cavity is 57
SHROUD_TOP_Z = 454.0                        # closed top with a hole for the tube and wires
SHROUD_SCREWS_Z = 440.0                     # four radial M3 from outside, hidden in the beard's locks
SHROUD_SCREW_ANGLES = [60.0, 120.0, 240.0, 300.0]
# the nozzle tilts on a micro servo inside the beard, through the beard's parting under the mouth
MG92B = dict(body=(22.8, 12.4, 28.5), tab_span=32.5, tab_t=2.0, tab_z=19.0, shaft_off=6.0, holes=(27.8, 0.0))
MICRO_HORN_D = 14.0
Z_MOUTH = 424.0                             # the statue's mouth (0.603 H)
NOZZLE_PIVOT = (62.0, 0.0, 424.0)           # tilt axis of the nozzle arm, along Y, just inside the beard
NOZZLE_ARM_L = 20.0                         # pivot to the nozzle's tip at the mouth's skin, x 82
NOZZLE_SLOT_W = 14.0                        # the parting in the beard the nozzle arm (12 wide) swings through
