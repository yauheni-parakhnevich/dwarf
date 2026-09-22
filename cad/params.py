"""Every dimension of the printed gnome, in millimetres.

Z is up, +X is the direction the gnome faces, the origin is the centre of the floor.
Both build123d and Blender import this module, so it must stay plain Python.

Bought parts that have not been measured yet carry listing-typical defaults; the README
lists which ones to re-measure on arrival.
"""
# --- printer and fits ------------------------------------------------------------------
BED = 256.0
WALL = 2.4                 # shell wall, two 0.6 mm perimeters
CLEAR = 0.3                # sliding fit
INSERT_D = 4.0             # M3 heat-set insert bore
INSERT_DEPTH = 6.0
INSERT_DEPTH_SHORT = 4.0       # for 5 mm parts: a short M3 insert, still blind
M3_CLEAR = 3.4
M4_PIN = 4.0
M2_5_CLEAR = 2.8
NUT_M3_AF = 5.5            # across flats
NUT_M3_T = 2.4
SCREW_HEAD_H = 3.0

# --- heights ---------------------------------------------------------------------------
Z_FLOOR = 26.0             # underside of the raised floor; the skirt below has drain arches
Z_BELT = 210.0             # the split
Z_BASE_TOP = 218.0         # the base's rim, hidden inside the torso's skirt
Z_TORSO_TOP = 400.0
Z_DECK = 380.0             # top face of the turntable deck
DECK_T = 6.0
RING_T = 8.0               # interface rings unioned into the shell
Z_HEAD = 458.0             # tilt axis and head centre
HEAD_R = 45.0
Z_HAT = 481.0              # underside of the brim
Z_TOP = 558.0
Z_LENS = 245.0

# --- shell profiles, (radius, z) from the bottom up --------------------------------------
# outer skins only; shell_r walks these. The base's raised floor is a separate revolve row.
BASE_PROFILE = [(112.0, 0.0), (125.0, 90.0), (108.0, 170.0), (95.0, Z_BELT), (95.0, Z_BASE_TOP)]
BASE_FLOOR_R = 108.0
# broad shoulders up to 365 so the phone's top corners clear the wall; the beard collar hides them
TORSO_PROFILE = [(97.7, Z_BELT), (97.7, Z_BASE_TOP), (104.0, 260.0), (105.0, 300.0), (100.0, 340.0),
                 (96.0, 373.0), (84.0, 388.0), (76.0, Z_TORSO_TOP)]
TORSO_R_TOP = 76.0            # neck opening; the pan linkage sweeps inside it
HAT_BRIM_R = 70.0
HAT_BRIM_T = 8.0
HAT_CONE_R = 50.0
HAT_TIP_R = 4.0
HAT_BEND = 15.0            # how far the tip leans forward
BEARD_TOP_Z = 423.0
BEARD_BOTTOM_FRONT_Z = 330.0
BEARD_BOTTOM_BACK_Z = 383.0
BEARD_T = 3.0
BEARD_R_OUT_TOP = TORSO_R_TOP + 8.0    # collar's outer radius at its top, 84
BEARD_R_IN_TOP = BEARD_R_OUT_TOP - BEARD_T

SECTION_Z = {
    "base": (0.0, Z_BASE_TOP),
    "torso": (Z_BELT, Z_TORSO_TOP),
    "beard": (BEARD_BOTTOM_FRONT_Z, BEARD_TOP_Z),
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
FLANGE_SCREWS = 4
FLANGE_SCREW_ANGLES = [45.0, 135.0, 225.0, 315.0]
CHASSIS_SCREW_ANGLES = [0.0, 90.0, 180.0, 270.0]
DIVIDER_T = 8.0            # fills the base's top cup, flush with Z_BASE_TOP
GLAND_D = 12.0
GLAND_POS = [(-40.0, 30.0), (-40.0, -30.0)]
CHASSIS_T = 4.0
CHASSIS_R = 88.0
Z_CHASSIS = Z_BASE_TOP + RING_T   # 226, sits on the torso flange

# --- phone and window ---------------------------------------------------------------------
PHONE_L, PHONE_W, PHONE_T = 138.3, 67.1, 7.1
PHONE_CAM_FROM_END = 11.0      # rear camera centre from the phone's end
PHONE_CAM_FROM_SIDE = 11.0     # ... and from its side
LENS_CLIP_T = 12.0             # clip-on lens in front of the back glass
LENS_CLIP_W = 28.0             # the clip's width across the phone; measure the clip on arrival
ACRYLIC_T = 3.0
LENS_GAP = 2.0
WINDOW_W, WINDOW_H = 40.0, 48.0
WINDOW_Z_BIAS = 6.0            # window centre above the lens: the view needed is mostly above horizontal, and the belt joint is just below
HOOD_DEPTH = 15.0
HOOD_PITCH_DEG = 10.0
# the phone is centred; its camera sits CAM_Y off the centreline, which the aiming
# calibration absorbs like every other fixed offset
PHONE_Y_OFFSET = 0.0
CAM_Y = PHONE_Y_OFFSET + PHONE_W / 2 - PHONE_CAM_FROM_SIDE   # 22.55
PHONE_BOTTOM_Z = Z_LENS - PHONE_CAM_FROM_END           # 234
LENS_FRONT_X = shell_r(TORSO_PROFILE, Z_LENS) - WALL - ACRYLIC_T - LENS_GAP
PHONE_BACK_X = LENS_FRONT_X - LENS_CLIP_T              # back glass
PHONE_FRONT_X = PHONE_BACK_X - PHONE_T                 # screen
SLED_WALL = 3.0

# --- electronics --------------------------------------------------------------------------
ESP32 = (55.0, 28.0)
XL4015 = (54.0, 23.0)
XL4015_HOLES = (43.0, 15.0)
XL4015_HOLE_D = 3.2
MOSFET = (34.0, 27.0)
EDECK_L, EDECK_W, EDECK_T = 110.0, 90.0, 4.0
EDECK_POS = (-30.0, 0.0)       # centre, x-y; it stands on the chassis
EDECK_STANDOFF = 8.0
FAN = 40.0
FAN_T = 10.0
FAN_PITCH = 32.0
Z_FAN = 348.0                  # the whole 50 mm frame stays inside the shoulder; the exhaust sits on the back below the collar
VENT_IN_W, VENT_IN_H, Z_VENT_IN = 40.0, 20.0, 245.0   # above the torso flange (226)

# --- turntable ----------------------------------------------------------------------------
BEARING_SQ = 60.0
BEARING_T = 6.0
BEARING_OPEN = 32.0
BEARING_PITCH = 48.0
BEARING_HOLE = 3.4
SHAFT_OD, SHAFT_ID = 20.0, 12.0
DECK_R = 84.0                  # the wall's inner radius here is about 87
RING_R_IN = 50.0
RING_R_OUT = 66.0              # the ring is a narrow annulus; four webs reach the wall
RING_WEB_W = 8.0
DECK_SCREW_R = 58.0
DECK_SCREW_ANGLES = [30.0, 150.0, 210.0, 330.0]   # off the pan servo's hangers and the phone
PLATE_R = 50.0
PLATE_T = 5.0
Z_PLATE_TOP = Z_DECK + BEARING_T + PLATE_T           # 391
# --- pan drive: the servo hangs under the deck, shaft pointing down, and the parallelogram
#     lives below the deck where the torso is wide. The plate's front stop tab carries a column
#     down through an arc slot in the deck to the link. Nothing of the drive is above the deck.
PAN_SERVO_XY = (5.0, -60.0)    # servo axis; the body runs +X from the shaft end (x -5 .. 35, y -70 .. -50)
PAN_OFFSET = (PAN_SERVO_XY[0] ** 2 + PAN_SERVO_XY[1] ** 2) ** 0.5   # link length, 48.33
CRANK_L = 30.0                 # shorter than the servo offset, so neither bar can ever cross the pan axis
CRANK_REST_DEG = 0.0           # both cranks point +X (front) at rest
Z_PAN_SHAFT_FACE = 333.0       # the servo's output face, looking down; body top 373.5, under the deck
Z_PAN_HORN_BOTTOM = Z_PAN_SHAFT_FACE - 2.5
CRANK_T = 5.0
LINK_T = 3.0
Z_CRANK_TOP = Z_PAN_HORN_BOTTOM              # 330.5; the crank pockets the horn from below
Z_CRANK_BOTTOM = Z_CRANK_TOP - CRANK_T       # 325.5
Z_LINK_TOP = Z_CRANK_BOTTOM                  # 325.5
Z_LINK_BOTTOM = Z_LINK_TOP - LINK_T          # 322.5
LINK_EYE_R = M3_CLEAR / 2 + 3.0
PAN_COLUMN = (44.0, 52.0, 8.0)               # radial extent and width of the plate's hanging column
PAN_FOOT_R_IN = CRANK_L - 4.0                # the column's foot reaches inward to the pin at CRANK_L
DECK_SLOT = (PAN_COLUMN[0] - CLEAR, (PAN_COLUMN[1] ** 2 + (PAN_COLUMN[2] / 2) ** 2) ** 0.5 + CLEAR, 76.0)   # r0, r1 (the box's corners), half-angle
PAN_HANGER = 10.0                            # square columns under the deck the servo tabs screw to
PAN_STOP_DEG = 65.0
STOP_POST_R = 60.0
STOP_POST_D = 6.0
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
EAR_R = 9.0
EAR_OUT_Y = HEAD_R + 6.0       # outer face of the ear boss / coupler
YOKE_GAP = 1.0
YOKE_ARM_T = 8.0
YOKE_ARM_W = 28.0              # 4 mm of wall either side of the coupler's hex
YOKE_RING_R_IN = 44.0          # the yoke stands on a ring on the plate's rim
YOKE_RING_T = 3.0
YOKE_SCREW_R = 46.7
YOKE_SCREW_ANGLES = [45.0, 135.0, 225.0, 315.0]
COUPLER_D = 20.0
COUPLER_HEX_AF = 17.0
TILT_SERVO_SHAFT_Y = 25.0      # servo shaft face inside the head, +Y side
BULKHEAD_Y = TILT_SERVO_SHAFT_Y - MG996R["body"][2] + MG996R["tab_z"]   # 10.1
BULKHEAD_T = 2.5
BULKHEAD_BOSS_D = 9.0          # bosses round the four insert holes, INSERT_DEPTH + 1 tall
HEAD_OPENING_R = 15.0          # tube and wires enter through the bottom
FACE_SPLIT_X = 20.0            # the face is the cap in front of this plane
FACE_LIP_T = 2.0
FACE_LIP_L = 5.0
Z_MOUTH = Z_HEAD - 22.0        # 436
MOUTH_D = 12.0
NOZZLE_D = 8.0
NOZZLE_BOSS_Y = 12.0
NOZZLE_HOLDER_X = (15.0, 28.0)
TILT_STOP_TAB_R = 15.0

# --- base, wet zone -----------------------------------------------------------------------
CANISTER = (220.0, 140.0, 110.0)     # lying flat, long axis X, neck towards -X
CAN_THREAD_MAJOR = 38.0
CAN_THREAD_PITCH = 3.0
CAN_THREAD_LEN = 12.0
CAN_NECK_ID = 30.0
CANISTER_XY = (10.0, -20.0)          # centre of the lying canister in plan
PUMP = (160.0, 100.0, 65.0)
PUMP_FEET = (130.0, 70.0)
PUMP_XY = (0.0, 65.0)
VALVE = (45.0, 25.0, 55.0)
FLOAT_HOLE_D = 12.0
DIP_TUBE_D = 8.0
FILLER_D = 20.0
FILLER_CAP_THREAD_MAJOR = 24.0
FILLER_CAP_PITCH = 2.0
Z_FILLER = 150.0
DRAIN_ARCHES = 4
DRAIN_ARCH_W, DRAIN_ARCH_H = 30.0, 12.0
STAKE_HOLE_D = 8.0
STAKE_HOLE_R = 95.0
