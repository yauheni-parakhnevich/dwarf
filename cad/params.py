"""Every dimension of the printed gnome, in millimetres.

Z is up, +X is the direction the gnome faces, the origin is the centre of the floor.
Both build123d and Blender import this module, so it must stay plain Python.

Bought parts that have not been measured yet carry listing-typical defaults; the README
lists which ones to re-measure on arrival.
"""
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
NUT_M3_AF = 5.5            # across flats
NUT_M3_T = 2.4
SCREW_HEAD_H = 3.0

# --- heights ---------------------------------------------------------------------------
Z_FLOOR = 26.0             # underside of the raised floor; the skirt below has drain arches
Z_BELT = 230.0             # the split; 20 mm higher than first drawn so a 2 L canister and the pump stack below it
Z_BASE_TOP = 238.0         # the base's rim, hidden inside the torso's skirt
Z_TORSO_TOP = 420.0
Z_DECK = 400.0             # top face of the turntable deck
DECK_T = 6.0
RING_T = 8.0               # interface rings unioned into the shell
Z_HEAD = 478.0             # tilt axis and head centre
HEAD_R = 48.0              # the face opening must pass the tilt servo on its cradle; 45 was 2 mm short
Z_HAT = 512.0              # underside of the brim: 34 above the tilt axis, so at +45 the brim clears the yoke arms
Z_TOP = 589.0
Z_LENS = 265.0

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
DIVIDER_PROUD = 0.3        # the divider stands this much above the base's rim so the belt screws load the PU bead, not the rim
GLAND_D = 12.5             # an M12 cable gland's thread, with clearance
GLAND_POS = [(-40.0, 30.0), (-40.0, -30.0)]
CHASSIS_T = 4.0
CHASSIS_R = 90.0
CHASSIS_SCREW_ANGLES = [40.0, 140.0, 220.0, 320.0]   # off the belt screws, the sled and the electronics deck
CHASSIS_SCREW_R = FLANGE_SCREW_R - 2.0
Z_CHASSIS = Z_BASE_TOP + RING_T   # 226, sits on the torso flange

# --- belly hatch: the coat's front between the belt and the shoulders is a screwed-on panel that
#     carries the window and the hood. The phone sled slides out forward through it, and every
#     screw in the dry zone is driven through it. The panel is cut from the torso's raw mesh by the
#     assembler; four bosses and a lip around the opening are interface parts on the torso.
HATCH_Z = (Z_BASE_TOP + 6.0, 398.0)          # 244 .. 398; the sled (250 .. 372) and the phone pass
HATCH_HALF_ANGLE = 33.0                      # degrees either side of +X; 110 mm wide at the belly
HATCH_LIP_W = 6.0                            # lip inside the opening the panel rests on, all round
HATCH_SCREWS = [(HATCH_Z[0] + 10.0, -30.0), (HATCH_Z[0] + 10.0, 30.0), (HATCH_Z[1] - 10.0, -30.0), (HATCH_Z[1] - 10.0, 30.0)]   # (z, angle deg); at 30 deg the lower screw clears the window by 7.5 mm

# --- phone and window ---------------------------------------------------------------------
PHONE_L, PHONE_W, PHONE_T = 138.3, 67.1, 7.1
PHONE_CAM_FROM_END = 11.0      # rear camera centre from the phone's end
PHONE_CAM_FROM_SIDE = 11.0     # ... and from its side
LENS_CLIP_T = 12.0             # clip-on lens in front of the back glass
LENS_CLIP_W = 28.0             # the clip's width across the phone; measure the clip on arrival
ACRYLIC_T = 3.0
LENS_GAP = 2.0
WINDOW_W, WINDOW_H = 40.0, 48.0
WINDOW_Z_BIAS = 10.0           # window centre above the lens: the view needed is mostly above horizontal, and the hatch's lip is just below
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
SLED_FOOT_H = 5.0              # the feet are runners on the chassis; one screw from above locks the sled at home
SLED_GUIDE_H = 3.0             # ribs on the chassis either side of the feet

# --- electronics --------------------------------------------------------------------------
ESP32 = (55.0, 28.0)
XL4015 = (54.0, 23.0)
XL4015_HOLES = (43.0, 15.0)
XL4015_HOLE_D = 3.2
MOSFET = (34.0, 27.0)
EDECK_L, EDECK_W, EDECK_T = 110.0, 90.0, 4.0
EDECK_POS = (-30.0, 0.0)       # centre, x-y; it stands on the chassis
# board footprints on the deck, (x0, y0, x1, y1) relative to EDECK_POS: two columns, A at the back
EDECK_LAYOUT = {
    "xl4015_a": (-50.0, -43.0, 4.0, -20.0),
    "xl4015_b": (-50.0, -17.0, 4.0, 6.0),
    "fuse": (-50.0, 7.0, -20.0, 17.0),
    "mosfet_c": (-50.0, 18.0, -16.0, 45.0),
    "esp32": (-8.0, 16.0, 47.0, 44.0),
    "mosfet_a": (6.0, -45.0, 40.0, -18.0),
    "mosfet_b": (6.0, -16.0, 40.0, 11.0),
}
# deck screws, relative to EDECK_POS: the four corners the layout leaves free
EDECK_HOLES = [(-54.0, -44.0), (-54.0, 44.0), (52.0, -44.0), (52.0, 13.0)]
MOSFET_HOLES = (28.0, 21.0)       # measure the modules on arrival
ESP32_HOLES = None                # devkit boards vary; it sits in a printed cradle (two rails + tie slots)
EDECK_STANDOFF = 8.0
FAN = 40.0
FAN_T = 10.0
FAN_PITCH = 32.0
Z_FAN = 368.0                  # the whole 50 mm frame stays inside the shoulder; the exhaust sits on the back below the collar
VENT_IN_W, VENT_IN_H, Z_VENT_IN = 40.0, 20.0, 265.0   # above the torso flange (246)

# --- turntable ----------------------------------------------------------------------------
BEARING_SQ = 60.0
BEARING_T = 6.0
BEARING_OPEN = 32.0
BEARING_PITCH = 48.0
BEARING_HOLE = 3.4
SHAFT_OD, SHAFT_ID = 21.0, 13.0   # bore: tube + three wires + 2 mm, spec section 6
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
PAN_OFFSET = (PAN_SERVO_XY[0] ** 2 + PAN_SERVO_XY[1] ** 2) ** 0.5   # the link's eye-to-eye length, 60.21
CRANK_L = 30.0                 # shorter than the servo offset, so neither bar can ever cross the pan axis
CRANK_REST_DEG = 0.0           # both cranks point +X (front) at rest
Z_PAN_SHAFT_FACE = 353.0       # the servo's output face, looking down; body top 393.5, under the deck
Z_PAN_HORN_BOTTOM = Z_PAN_SHAFT_FACE - 2.5
CRANK_T = 5.0
LINK_T = 3.0
PIN_BORE = 3.2                 # link eyes on M3 shanks; ream after printing
PIN_BOSS_H = 0.5
PIN_BOSS_D = 8.0
Z_CRANK_TOP = Z_PAN_SHAFT_FACE               # 333; the crank's top is the shaft face, the horn sits in its pocket
Z_CRANK_BOTTOM = Z_CRANK_TOP - CRANK_T       # 328
Z_LINK_TOP = Z_CRANK_BOTTOM - PIN_BOSS_H     # 327.5; a boss on crank and foot takes the screw's clamp, not the link
Z_LINK_BOTTOM = Z_LINK_TOP - LINK_T          # 324.5
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
Z_MOUTH = Z_HEAD - 22.0        # 436
NOZZLE_D = 8.0
MOUTH_D = NOZZLE_D + 0.4       # the mouth is the nozzle's outboard bearing
NOZZLE_BOSS_Y = 13.4           # an r 3 driver on the screw passes the cradle rails with 1 mm to spare
NOZZLE_HOLDER_X = (15.0, 28.0)
TILT_STOP_TAB_R = 15.0
TUBE_OD = 6.0
TUBE_BEND_R = 15.0             # 6 x 4 PU tube's static minimum; the holder's barb faces -X so one such bend reaches the axis

# --- base, wet zone -----------------------------------------------------------------------
CANISTER = (160.0, 120.0, 105.0)     # lying flat, long axis X, neck towards -X. 2.0 L gross: the base's circle takes no more
CAN_THREAD_MAJOR = 38.0
CAN_THREAD_PITCH = 3.0
CAN_THREAD_LEN = 12.0
CAN_NECK_ID = 30.0
CANISTER_XY = (0.0, 0.0)             # centred: its corners are the tightest thing in the base
CANISTER_Z0 = Z_FLOOR + 6.0          # on its cradle
PUMP = (160.0, 100.0, 65.0)
PUMP_FEET = (130.0, 70.0)
PUMP_XY = (0.0, 0.0)                 # bridged above the canister on the pump mount's legs
PUMP_Z0 = CANISTER_Z0 + CANISTER[2] + 10.0   # 147: mount plate 4 above the canister, grommets 6
PUMP_LEG = 10.0
PUMP_LEG_XY = (CANISTER[0] / 2 + 10.0, 45.0)   # legs stand beside the canister's ends
VALVE = (45.0, 25.0, 55.0)
VALVE_XY = (0.0, 65.0)               # beside the pump, on the pump mount's plate
VALVE_STRAP = (12.0, 3.0)            # a bar across the valve's body, two M3s into the plate's inserts
PUMP_TIE_SLOTS = True                # cable-tie slots beside each grommet pocket hold the pump down
FLOAT_HOLE_D = 12.0
DIP_TUBE_D = 8.0
FILLER_D = 14.0                      # the neck's 30 mm bore must also pass the float switch and the dip tube
FILLER_STUB_DIR = "+z"               # the stub rises from the tank head's shoulder: a hose can climb to the back wall from there
FILLER_CAP_THREAD_MAJOR = 22.0       # 2.8 mm of wall at the neck's thread roots
FILLER_CAP_PITCH = 2.0
Z_FILLER = 150.0
DRAIN_ARCHES = 4
DRAIN_ARCH_W, DRAIN_ARCH_H = 30.0, 12.0
STAKE_HOLE_D = 8.0
STAKE_HOLE_R = 95.0
