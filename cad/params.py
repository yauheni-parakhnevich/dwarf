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
WALL_MIN = 1.6             # and never thinner than this anywhere: under it a 0.6 mm nozzle lays
                           # one bead or none, which is a pinhole. See statue.py's `keep_out`.
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
EDECK_HOLES = [(46.0, -34.0), (46.0, 34.0), (-8.0, 6.0)]    # in the free strip and the gap over the
                                                            # fuse, under the ESP32 cradle's near rail.
                                                            # The +Y one is back at 34, square with the
                                                            # -Y one, now that no filler cap stands on
                                                            # the divider there; under 27 it would foul
                                                            # the slot the sled's lock lug comes up through
EDECK_POSTS = [(-30.0, -34.0), (-30.0, 34.0)]               # bare posts under the deck's back end,
                                                            # inboard of the cage's foot ring at r 57
MOSFET_HOLES = (28.0, 21.0)       # measure the modules on arrival; the ESP32 has no standard holes and sits in a printed cradle
EDECK_STANDOFF = 8.0
FAN = 30.0                     # a 30 mm fan. A 40 mm one cannot stand under the deck's back and still let
FAN_T = 10.0                   # the collar down over it: see FAN_XY
FAN_PITCH = 24.0
VENT_IN_W, VENT_IN_H = 40.0, 20.0          # the intake, cut in the belt ring's back at Z_VENT_IN

# --- turntable ----------------------------------------------------------------------------
# The pan bearing is a sealed thin-section deep-groove ball bearing, a 6810-2RS: 50 bore, 65 OD,
# 7 wide. Its bore is what the nod drive reaches C through - the yoke's cheeks hang down it and
# the stem swings in it - so it replaced the 60 mm lazy susan, whose plate had no hole to speak of.
# Outer ring in the deck (fixed), inner ring on the plate's hub (pans). Each is held both ways: the
# outer ring sits on a lip in the deck and a printed cap screws down over it; the inner ring sits
# under a shoulder on the hub and a printed ring clamps it from below with two radial screws.
#
# A single row is enough here. It carries the turning parts' weight, about 0.75 kg (7.4 N) axially,
# and a tilting moment from the wind on the head of at most about 1 N.m at 20 m/s (the nod servo
# stalls there first); across the 57.5 mm pitch circle of its balls that is some 35 N on the most
# loaded side, against a static rating of several kN. What it does not have is a second row to
# resist tilt, so its internal clearance (C0: 5-20 um radial) shows as rocking: a few arc-minutes,
# which is 0.5-1 mm at the hat's tip, 300 mm above it. The printed seats add nothing to that only
# because both rings are clamped face to face; the radial fit alone (BEARING_FIT) would let the hub
# rock 2.5 degrees in a 7 mm ring.
BEARING_ID, BEARING_OD, BEARING_B = 50.0, 65.0, 7.0
BEARING_IN_LAND_R = 26.5       # the inner ring's face runs out to about here (d1 ~ 53.5): a shoulder
                               # that bears on it stays inside this, clear of the seal
BEARING_OUT_LAND_R = 31.0      # ... and the outer ring's face runs in to about here (D1 ~ 61.5)
BEARING_FIT = 0.15             # radial clearance at both printed seats, within the 0.1-0.2 asked for
BEARING_LIP = 1.0              # the deck's lip under the outer ring
CAP_T = 3.0                    # the printed cap over the outer ring (bearing_cap)
CAP_R = 40.0
CAP_SCREW_R = 36.5
CAP_SCREW_ANGLES = [45.0, 135.0, 270.0]   # clear of the fan's hole at 180 and of the column's arc
HUB_RING_R = 30.0              # the ring under the inner ring (hub_ring): it must pass the deck's lip
HUB_RING_H = 7.0               # ... and hangs this far under the bearing, below the deck's underside
HUB_RING_SCREW_ANGLES = [90.0, 270.0]     # radial, where the hub is solid: the cheeks' side
DECK_R = 80.0                  # the statue's front cavity at the deck is 85; a lobe towards -Y covers the servo hangers
DECK_LOBE = dict(angle=270.0, half=45.0, r=86.0)   # the hangers' corners reach 83.2; the socket trims the lobe to 83.2
DECK_BACK_R = 72.0             # over 140..220 degrees the coat's back is only 74..80 out
DECK_SOCKET_MARGIN = 1.5       # the deck, and everything fixed under the collar's dome, stays this far
                               # inside the socket's inner sphere, NECK_SPHERE_R - TURN_GAP - WALL
DECK_SHADOW_MARGIN = 1.5       # ... and this far inside the collar's narrowest opening under it, so
                               # the collar can be lowered over it
CAGE_LEG = 10.0                # the legs' square section. At 12 a leg's inboard corner stood
                               # 0.2 mm inside the electronics deck's edge and the deck could not
                               # be got past it; 10 at CAGE_LEG_R 61 clears that edge by 3.8 mm
CAGE_LEG_R = 61.0              # the legs' centres; the deck's screws sit on the same points. The
                               # bell turns over everything above Z_TURN and the coat's back sweeps
                               # in to r 68.7 there, so a leg's far corner - 66.2 here - may not
                               # pass that: it is the radius, not the cavity, that is the wall
CAGE_FOOT_T = 7.5              # the foot ring that ties the four legs, between the chassis's face
                               # and the electronics deck's underside. It is the cage's only tie:
                               # above it the legs are free so the boards can drop past them
CAGE_FOOT_OPEN = 70.0          # ... and it is open +-this much about +X, where the phone's sled
                               # comes down and where the filler cap stands
DECK_SCREW_R = CAGE_LEG_R
DECK_SCREW_ANGLES = [82.0, 98.0, 238.0, 250.0]    # the cage's legs, and the deck's screws into their
                               # tops: past the electronics deck's two long edges, clear of the pan
                               # servo (x -5..35, y -70..-50) and its hangers, of the fan, of the
                               # stop pins at +-70.7 and of the phone. The -Y pair was at 235 and
                               # 250, where the first of them stood inside the board deck's edge
PLATE_R = 50.0
PLATE_T = 5.0
Z_BEARING = Z_DECK - DECK_T + BEARING_LIP            # 395, the bearing's lower face
Z_PLATE_BOTTOM = Z_BEARING + BEARING_B + CAP_T + 0.5 # 405.5: half a millimetre over the cap
Z_PLATE_TOP = Z_PLATE_BOTTOM + PLATE_T               # 410.5
HUB_R = BEARING_ID / 2 - BEARING_FIT                 # 24.85, the plate's hub in the inner ring
Z_HUB_BOTTOM = Z_BEARING - HUB_RING_H                # 388
# --- pan drive: the servo hangs under the deck, shaft pointing down, and the parallelogram
#     lives below the deck where the torso is wide. The plate's front stop tab carries a column
#     down through an arc slot in the deck to the link. Nothing of the drive is above the deck.
PAN_SERVO_XY = (5.0, -60.1)    # servo axis; the body runs +X from the shaft end (x -5 .. 35, y -70.1 .. -50.1): 1 mm outside the column's sweep
PAN_OFFSET = (PAN_SERVO_XY[0] ** 2 + PAN_SERVO_XY[1] ** 2) ** 0.5   # the link's eye-to-eye length, 60.31
CRANK_L = 26.0                 # shorter than the servo offset, so neither bar can ever cross the pan axis; and
                               # not 30 any more: at pan -65 the link's far eye reached r 93.7 at z 330,
                               # where the collar's socket is 93.3 out
CRANK_REST_DEG = 0.0           # both cranks point +X (front) at rest
Z_PAN_SHAFT_FACE = 337.0       # the servo's output face, looking down; body top 377.5, under the deck. 3 mm lower than
                               # it was: the link's plane has to pass 2.5 under the -Y cheek, which reaches C - 16 = 334
CRANK_T = 5.0
LINK_T = 3.0
PIN_BORE = 3.2                 # link eyes on M3 shanks; ream after printing
PIN_BOSS_H = 0.5
PIN_BOSS_D = 8.0
Z_CRANK_TOP = Z_PAN_SHAFT_FACE               # 337; the crank's top is the shaft face, the horn sits in its pocket
Z_CRANK_BOTTOM = Z_CRANK_TOP - CRANK_T       # 332
Z_LINK_TOP = Z_CRANK_BOTTOM - PIN_BOSS_H     # 331.5; a boss on crank and foot takes the screw's clamp, not the link
Z_LINK_BOTTOM = Z_LINK_TOP - LINK_T          # 328.5
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
STOP_PIN_TOP = Z_PLATE_TOP - 1.5          # separate pins glued into the deck: 3.5 mm of the tab's 5, 1.5 under the plate's top
STOP_PIN_DEPTH = 6.0
STOP_TAB_W = 6.0

# --- servos: (length, width, height), tab span, tab thickness, tab height from the bottom,
#     shaft offset from the near end along the length, hole pitch (along length, across)
DS3218 = dict(body=(40.0, 20.0, 40.5), tab_span=54.5, tab_t=2.5, tab_z=28.0, shaft_off=10.0,
              holes=(49.5, 10.0))
# the nod servo, an MG996R-class metal-gear standard servo on the firmware's tilt channel: about
# 1.0 N.m at 6 V. Here `body` is (length along its tabs, width, height from the shaft face to the
# bottom), and the height leaves out the spline boss, which is SPLINE_BOSS below.
MG996R = dict(body=(40.5, 20.0, 38.0), tab_span=54.0, tab_t=2.5, tab_z=27.0, shaft_off=10.0,
              holes=(49.5, 10.0))
SPLINE_BOSS = (12.0, 4.7)      # the MG996R's top boss and spline as one cylinder: diameter, and how
                               # far the round horn's far face stands off the case
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

# --- the nod drive -----------------------------------------------------------------------------
# The head nods about a Y axis through C = (0, 0, Z_NOD) on a real pin, reached through the pan
# bearing's bore. What pans only: the plate, its hub in the bearing and two cheeks hanging from the
# hub down to C, the nod servo on the +Y side. What pans and nods: the stem - a blade between the
# cheeks with its hub on the pin - the spider on the stem's top, and the turning unit on the spider.
#
# Loads about C. Gravity: the unit (about 500 g, centre of mass (-9, 0, 454)) and the stem and
# spider (about 60 g near (-3, 0, 420)) put 0.10 N.m on the servo nose-down 15 degrees and 0.05 at
# rest. Wind on the head: 0.24, 0.55 and 0.97 N.m at 10, 15 and 20 m/s - the last is the servo's
# stall at 6 V, so a gust past about 15 m/s back-drives the head onto its stops, which is what they
# are for. The pin carries the unit's weight and the wind's side force, at most about 11 N, over a
# 4 x 6 bushing: 0.5 MPa. The stem's neck is 15 x 12 with a 7 mm channel: at the deck, 56 mm under
# the wind's centre of pressure, 9.7 N bends it to 1.3 MPa.
NOD_STOP = (-16.0, 6.0)        # the hard stops, a degree outside NOD_RANGE
NOD_SERVO_FACE_Y = 10.5        # the nod servo's case face; its body runs out to y 48.5, 7 mm inside
                               # the cage's +Y legs (r 56) at every pan
PIN_D = 4.0                    # a steel dowel along Y through C, pressed and set-screwed into the
PIN_L = 14.0                   # stem's hub, turning in a bronze bushing in the -Y cheek
BUSH_OD, BUSH_L = 6.0, 6.0     # a plain 4 x 6 x 6 bushing, pressed into the cheek
CHEEK_Y = (6.4, 12.4)          # the -Y cheek's faces, |y|: it carries the bushing and the stop slot
SERVO_CHEEK_Y = (6.4, 9.9)     # the +Y cheek, which only joins the servo's two posts round its spline
STEM_T = 12.0                  # the stem is a blade |y| <= STEM_T / 2 between the cheeks
STEM_W = 15.0                  # the neck's width in the plane of the nod
STEM_HUB_R = 13.0              # the hub at C: the round horn is let into its +Y face
STEM_LEAN = 5.0                # the neck leans back this much at rest, so that over NOD_RANGE it swings
                               # -10..+10 degrees from vertical and its sweep is centred in the bore
STEM_HEAD = (14.0, 420.0, 432.0)   # the stem's head the spider sits on: half-width, bottom, top
STEM_CHANNEL_D = 7.0           # the tube runs inside the stem
NOD_CLEAR = 1.5                # the stem clears the hub and the plate by this at every nod in NOD_RANGE
STOP_LUG_R = 9.0               # the stop lug: a sleeve on a screw in the stem hub's -Y face, at this
STOP_LUG_D = 6.0               # radius below C, runs in an arc slot in the -Y cheek
SPIDER_Z = (426.0, 450.0)      # the spider: its hub's underside and top
SPIDER_HUB_R = 20.0
HEAD_SCREWS_Z = 440.0          # four radial M3 from outside through the head into the spider
HEAD_SCREW_ANGLES = [60.0, 120.0, 240.0, 300.0]
SPIDER_BOSS_R = 57.0           # the bosses' faces: the interface the neck shroud had
SPIDER_CORE_R = 30.0           # inside this radius the spider may come nearer C than the sphere, since
                               # it stays inside the dome's bore at every nod; outside it, it may not
NOZZLE_D = 8.0
NOZZLE_L = 10.0                # a short brass jet nozzle. A 25 mm one does not fit: the unit, the
                               # holder with it, must stay NECK_SPHERE_R from C, and at the mouth that
                               # sphere is at x 67 - so the nozzle's back can be no nearer the axis than
                               # x 73.5 and its tip is at the skin, 82.4
NOZZLE_TIP_X = 83.5            # 1.1 mm proud of the skin at the mouth
MOUTH_D = NOZZLE_D + 0.4
JET_HALF_DEG = 3.0             # the jet's cone, for the beard's and moustache's keep-out
TUBE_OD = 6.0
TUBE_BEND_R = 15.0             # 6 x 4 PU tube's static minimum
STAB_TOP = 462.0               # the tube stands this high out of the spider, on the axis: the stab the
                               # head's socket slides down onto as the unit goes on
SOCKET_ENGAGE = 10.0           # how much of the stab the socket takes

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
# The filler is outside, on the coat's back, and refilling needs nothing taken off: unscrew the cap,
# pour. It is a port through the belt ring's wall, beside the air intake, tilted up and out so what
# is poured runs in and rain runs off the cap; an 8 mm hose runs from it down through the belt
# joint - a bore through both flanges and the divider - to the tank head's barb.
FILLER_PORT_AZ = 160.0                      # back-left, beside the air intake (moved 12 mm right for it).
                                            # Not further round: at pan +65 the beard's flank comes to
                                            # az 150 and would stand in a funnel's way
FILLER_PORT_Z = 286.0                       # where the port's axis leaves the skin; the pocket's rim is
                                            # 19.6 above and below on the wall, so it spans 266..306, all
                                            # in the ring, and its lowest inside edge stays over the cage's
                                            # foot ring (z 267.5)
FILLER_PORT_SKIN_R = 78.8                   # the skin's radius there, measured on outer.stl (a test
                                            # holds it to the mesh)
FILLER_PORT_TILT = 30.0                     # the axis above horizontal, outward
FILLER_POCKET_R = 15.0                      # the cap turns in a pocket this wide ...
FILLER_POCKET_D = 6.0                       # ... this deep along the axis, below the skin
FILLER_PASSAGE = (71.0, 147.0)              # the hose's way down through the chassis, both belt flanges
                                            # and the divider, (r, az): the hose grown 3 mm all round still
                                            # outside the cage's foot ring (63.5), its bore inside the
                                            # divider's bead groove (76.6) and the hose outside the belt
                                            # ring's bore below (65.8 there)
FILLER_PASSAGE_D = 11.0                     # bored this wide, 1.5 round the hose, so a drip down the hose
                                            # goes through to the wet side and not onto the divider's top
HOSE_OD = 8.0                               # the filler hose, port to tank head. It could not be wider:
                                            # where it rises beside the tank head's stub, at y 86.5, the
                                            # belt ring's bore is 90.9 out (it gave 8.9 mm there, and 8 is
                                            # the size sold). The old second limit - the 13 mm between the
                                            # bottle's top and the divider - is gone: over the bottle it
                                            # runs inside the belt ring's bore, up to z 238.5
HOSE_BEND_R = 5.0                           # the shortest straight leg of the route, at the fittings; a
                                            # silicone hose of this bore takes it, a stiff PVC one not
HOSE_BARB_D = 6.5                           # the barb at both ends of that hose: its 5 mm bore and a
                                            # millimetre and a half of stretch. Bored HOSE_BARB_D - 2, so
                                            # filling runs on the head between the port's mouth (z 288) and
                                            # the water - 0.13 m over an empty bottle, 0.06 over a full one:
                                            # about 1.1 L/min falling to 0.75, a minute for a litre.
                                            # The air it displaces leaves by the tank head's vent into the
                                            # belly, not back up the hose
HOSE_BARB_L = 10.0                          # how much of each barb the hose grips
HOSE_BARB_LIP = 0.5                         # how far each barb's two ridges stand off its shank
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
# --- how the statue parts, and where it hinges -----------------------------------------------
# The head does two things: it pans +-PAN_STOP_DEG about Z and it nods about Y. Both are
# rotations about ONE point, C = (0, 0, Z_NOD), on the pan axis. A rotation about a point maps
# every sphere about that point to itself, so if the fixed coat lies wholly inside the ball of
# radius NECK_SPHERE_R - TURN_GAP about C, and the moving unit lies wholly outside the sphere of
# radius NECK_SPHERE_R, the two can never meet, at any pan and any nod. That one sphere is
# therefore the whole parting: the beard's back face, the bib the beard rests on, and the collar
# seam round the shoulders and the back. The seam is where the sculpt's own skin crosses it -
# low over the shoulders, high at the nape - and in front it is handed over to the beard's own
# outline, which is simply where the beard's relief stands proud of the sphere.
Z_NOD = 350.0                               # the pan/nod centre, on the pan axis, in the neck
NECK_SPHERE_R = 100.0                       # the moving unit's inner boundary about C
TURN_GAP = 2.0                              # air in the seam: the coat is kept inside R - this
BEARD_GAP = 2.0                             # air under the beard: the bib is filled to R - this
NOD_RANGE = (-15.0, 5.0)                    # the owner's aim, + is nose up (the firmware's sign).
                                            # The sphere frees pan and nod for everything near the
                                            # joint; what it cannot free is the unit's flat bottom
                                            # at Z_BEARD_BOT, because the coat's belly under it is
                                            # outside the ball. The coat stays uncut, so the unit
                                            # gives way instead: its bottom rim is trimmed to the
                                            # envelope of the coat's top plane seen from every nod
                                            # in this range - 24 mm off the beard's front tips
                                            # (x +92 nosing down 15 deg), 4.6 mm off its back edge
                                            # (x -53 nosing up 5 deg), nothing at the sides.
NOD_STEP = 1.0                              # the envelope is built from a plane every this many
                                            # degrees; the chord it leaves is 0.002 mm at r 41
Z_BEARD_BOT = 309.0                         # the beard's bottom edge (0.441 H): below it nothing
                                            # turns, and the coat keeps its own skin
Z_TURN = Z_BEARD_BOT                        # kept: every reader means "everything above this may
                                            # turn", which is still true of the beard's bottom and
                                            # would not be true of Z_COLLAR
Z_COLLAR = 407.0                            # derived, not chosen: where the sphere crosses the
                                            # skin at the nape (az 180). The statue stage measures
                                            # it on outer.stl and raises if it has moved
BEARD_AZ = 85.0                             # the bib's fill sector: inside +-this the coat is
                                            # filled out to the sphere, so the beard sits on a
                                            # smooth bib instead of on its own old relief
RIM_OPEN_R = 5.0                            # the unit's edge on the sphere: any peninsula of it
                                            # with a neck under twice this goes (the stray lock)
RIM_SMOOTH = 3.0                            # the edge is a low-passed curve, a Gaussian of this
RIM_RAMP = 1.0                              # ... cut across over this much, so no grid shows
RIM_ISLAND = 15.0                           # thin or empty patches inside the beard smaller than
                                            # this across (as the diameter of a disc of the same
                                            # area) are closed by lifting the skin, not cut
RIM_TONGUE_W = 10.0                         # a lock narrower than this hanging off the rim behind
                                            # the ears, with nothing under it, is taken off
RIM_EDGE_BAND = 4.0                         # skin thinner than WALL_MIN is cut only this close to
                                            # the unit's edge; further in, it is lifted instead
RIM_MIN_T = WALL - 0.4                      # skin thinner than this over the sphere is feather:
                                            # the wall test's own "thin" line, so what is left
                                            # passes it
RIM_LIFT_T = WALL                           # a pinhole's skin is lifted to R + this
RIM_FLANGE_W = 3.0                          # what is left gets a flange this wide lying on
RIM_FLANGE_T = WALL                         # the sphere, this thick, turned in over the cavity
NECK_BORE_R = 55.0                          # the one hole in the socket's closed dome, on the axis: SHROUD_R_OUT 52 + 3
NECK_DAM_H = 3.0                            # a drip skirt this deep hangs under the bore's edge.
                                            # A rim this tall standing up round the bore would be
                                            # outside the ball (101.8 from C) and the nape meets it
                                            # at pan -65, nose down 15; the dome's top is the ball
SEAM_NOTCH_MAX = 8.0                        # the coat's top edge slopes down from the socket so
                                            # there is no ledge, but never cuts deeper than this
                                            # under the unit's flat bottom: the slope eases where
                                            # the ledge is wide (depth = width x slope)
SEAM_CHAMFER_MAX_DEG = 60.0                 # and is never steeper than this where it is narrow
PANEL_Y = 105.0                             # the sleeves' plane; above Z_BEARD_BOT the coat is
                                            # inside the ball (r <= 98) and never reaches it
PANEL_TOP = Z_BEARD_BOT - TURN_GAP          # so the side panels stop under the beard's bottom
PANEL_BOTTOM = 196.0                        # the mittens' lower edge; below Z_BELT the panel belongs to the base halves
SECTIONS_STATUE = {                         # printable pieces, each within the 256 mm bed
    "base_left": (0.0, Z_BELT), "base_right": (0.0, Z_BELT),        # split at y = 0, sand ballast inside
    "hand_left": (PANEL_BOTTOM, Z_BELT), "hand_right": (PANEL_BOTTOM, Z_BELT),   # mitten caps glued to the base halves
    "torso": (Z_BELT, Z_TURN - TURN_GAP),                             # the belt ring, open on top: the mechanism drops in
    "collar": (Z_TURN - TURN_GAP, Z_NOD + math.sqrt((NECK_SPHERE_R - TURN_GAP) ** 2 - NECK_BORE_R ** 2)
               + 1.0),                                               # socket, bib and dome, fixed onto the ring after it
    "panel_left": (Z_BELT, PANEL_TOP), "panel_right": (Z_BELT, PANEL_TOP),      # the sleeves' sides, fixed, glued to the ring
    "beard": (Z_BEARD_BOT, 412.0), "head": (412.0, Z_HAT), "hat": (Z_HAT, Z_TOP),   # the turning unit, glued
}
# The turning unit cannot go on in one piece. Its back lies on the sphere about C wherever it faces
# the coat, and those directions from C go round more than a hemisphere - down to 22 degrees under
# C at the back corners and 9 in front - so no straight path takes it onto the collar or off it
# (the least, over every direction, of the directions' reach along it is -0.35; it would have to be
# more than 0). The head and the hat on their own go straight down (+0.61); the beard, cut at y = 0,
# goes on in two halves, each from its own side, up and out at FIT_DIR (+0.28 each). So the beard
# is printed in two halves; the head and the hat are glued into one.
FITTING_SPLIT = {"beard": (("beard_left", 1.0), ("beard_right", -1.0))}
BEARD_KERF = 0.4                            # the gap down the beard's middle between the halves
FIT_DIR = (63.0, 66.0)                      # a beard half's way on: this far from vertical, this far
                                            # round from the front towards its own side (mirrored)
PRINTED_SECTIONS = tuple(n for s in SECTIONS_STATUE
                         for n in ([h for h, _ in FITTING_SPLIT[s]] if s in FITTING_SPLIT else [s]))
TURNING_SECTIONS = ("beard_left", "beard_right", "head", "hat")
# With the bell off, everything inside is reached from the top: there is no belly hatch. The
# window is cut in the ring; the exhaust fan sits on the left panel's inner face, the intake
# in the ring's back.
# The fan hangs under the deck and blows upward through a hole in it; the intake is in the belt
# ring's back and the air leaves through the bell's turning gap and the beard's parting, a chimney.
# The sleeves are too thin to hold a fan and everything else above the belt turns.
FAN_XY = (-49.0, 0.0)                       # the fan's axis, under the deck's back. Two things bound it: its
                                            # hole clears the bearing's outer ring (r 32.5) by 2 mm or more,
                                            # so the axis is at least 47.5 out; and the collar is lowered
                                            # over the deck after it, so its frame has to stay inside the
                                            # collar's narrowest opening under it, which at the back is 69.
                                            # A 40 mm frame needs both 52.5 and at most 44.5 there; a 30 mm
                                            # one at 49 straight back has its corners at r 65.7
FAN_HOLE_D = FAN - 4.0
Z_VENT_IN = 272.0
VENT_IN_Y = -12.0                           # the intake's centre across the back: 12 mm to the right of
                                            # the back meridian, so the filler port can stand at 160
# the belt joint follows the coat's section: an ellipse, not a circle
BELT_RX, BELT_RY = 74.0, 105.0             # outer, at Z_BELT; the assembler clips every interface part to the cavity anyway
BELT_IN_RX, BELT_IN_RY = 60.0, 91.0
BELT_SCREW_ANGLES = [55.0, 140.0, 220.0, 305.0]   # the front pair sits away from the filler neck at (48, 54)
CHASSIS_RX, CHASSIS_RY = 71.5, 77.0        # not 70 x 100: it goes in through the ring's top, which the
                                            # parting's seam chamfer leaves only 79.9 out at the sides
                                            # and 73.3 at the back
# the dry zone, re-stacked
FRONT_SKIN_X_AT_WINDOW = 89.4               # the statue's front at the window (LENS_FRONT_X is derived from it above)
EDECK_L, EDECK_W = 100.0, 92.0             # its corner sits at 0.68 of the chassis ellipse
EDECK_POS = (0.0, 5.0)                      # 5 mm off the axis: the cage's two -Y legs pass its
                                            # back edge and its two +Y legs its front one, which
                                            # is what lets the deck drop in between them
Z_MOUTH = 424.0                             # the statue's mouth (0.603 H); the nozzle is fixed in it
# the collar joint: the collar is fitted after the mechanism and comes off for service. Four tabs
# hang from the collar SPIGOT_H down into the ring's top, CLEAR_SHELL inside it, and four radial
# countersunk M3 go in from outside through the ring's top edge into inserts in them, where the
# turning unit's rim overhangs them. See mech/collar.py
SPIGOT_H = 10.0                             # how far the tabs go down into the ring
SPIGOT_T = 3.0
SPIGOT_HALF_DEG = 8.0
COLLAR_SCREWS_Z = 302.0
COLLAR_SCREW_ANGLES = [45.0, 125.0, 235.0, 315.0]   # the back pair clear of the filler port at 150
