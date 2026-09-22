"""Inside the face: the nozzle and what holds it."""
import math
from build123d import Axis, Location, Plane, Pos, Sphere
import params as P
from mech import part
from mech.common import cyl_x, cyl_z, box

BOSS_R = 4.0               # the bosses on the face's inner wall the holder screws into
DRIVER_R = 3.0             # the stubby driver that reaches the screw heads along -X
SCREW_HEAD_R = 3.2         # counterbore for an M3 cheese head

# The cradle's rails reach out to this y beside the mouth, and they are in front of the
# tilt cradle all the way to x 16.5 - right where a screw on NOZZLE_BOSS_Y would want its
# driver. The pair moves out until a DRIVER_R shaft clears the rails by a millimetre.
RAIL_Y_OUT = P.BULKHEAD_Y + P.CLEAR + P.RAIL_T                     # 9.4
BOSS_Y = max(P.NOZZLE_BOSS_Y, RAIL_Y_OUT + DRIVER_R + 1.0)         # 13.4

# The holder is trimmed to a sphere a clearance inside the face cap's seating lip, so it can
# neither touch the lip nor reach the shell however the corners of its block would fall.
HOLDER_R = P.HEAD_R - P.WALL - P.CLEAR - P.FACE_LIP_T - P.CLEAR    # 43.0

# --- the nozzle and where it bears ----------------------------------------------------------
# On the mouth's axis the head's skin stands at 42.66 and its inner face at 39.94, so the mouth
# the assembler cuts is 2.7 mm of bearing at the far end. The nozzle is a Ø8 x 25 brass part
# pushed in from behind until its tip stands NOZZLE_PROUD past the skin; everything behind it
# follows from that.
SKIN_X = math.sqrt(P.HEAD_R ** 2 - (P.Z_MOUTH - P.Z_HEAD) ** 2)                    # 42.66
WALL_X = math.sqrt((P.HEAD_R - P.WALL) ** 2 - (P.Z_MOUTH - P.Z_HEAD) ** 2)         # 39.94
NOSE_X = math.sqrt(HOLDER_R ** 2 - (P.Z_MOUTH - P.Z_HEAD) ** 2)                    # 36.95
NOZZLE_L = 25.0
NOZZLE_PROUD = 1.0                                                                 # past the skin
NOZZLE_BACK = SKIN_X + NOZZLE_PROUD - NOZZLE_L                                     # 18.66
BORE_X0 = NOZZLE_BACK - 0.2                                                        # 18.46
NOSE_R = P.NOZZLE_D / 2 + 3.0                                                      # 7.0

# --- the tube, and why the barb sits where it does --------------------------------------------
# The tube leaves the barb along -X on the head's centreline and turns straight down through one
# TUBE_BEND_R arc, which puts it on the pan axis exactly when the barb's mouth is at
# NOZZLE_HOLDER_X[0] = 15 - the parameter is not free, it is the bend radius. The height is set
# from below by the cradle rails, whose floor starts at CRADLE_Z[0] - RAIL_H: the tube's own
# radius has to pass under it.
BARB_Z = P.CRADLE_Z[0] - P.RAIL_H - P.TUBE_OD / 2 - 1.0            # 448
BARB_SEAT_R = P.TUBE_OD / 2 + 1.5                                  # 4.5, the fitting's body
FEED_R = P.TUBE_OD / 2 - 1.0                                       # 2.0, the tube's own bore
# The riser joins the barb's bore to the back of the nozzle's. It has to open into that bore
# behind the nozzle's inlet face and still leave wall at the holder's back, and those two are
# only 3.5 mm apart, so it is Ø3 rather than the tube's Ø4.
RISER_R = 1.5
RISER_X = BORE_X0 + RISER_R                                        # 19.96


def screw_points():
    """(y, z) of the two screws that hold the nozzle holder onto the face's bosses."""
    return [(-BOSS_Y, P.Z_MOUTH), (BOSS_Y, P.Z_MOUTH)]


def press_fit_length():
    """Unbroken bore the nozzle is gripped by, from the riser's opening to the nose's face."""
    return NOSE_X - (RISER_X + RISER_R)


def tube_route(end_z=None):
    """The tube's centreline from the barb's mouth to the shaft, as a chain of short cylinders.

    Straight out along -X, one TUBE_BEND_R quarter turn down, then straight down the pan axis.
    """
    end_z = P.Z_PLATE_TOP + 6.0 if end_z is None else end_z            # the shaft's flare mouth
    r = P.TUBE_OD / 2
    x0 = P.NOZZLE_HOLDER_X[0]
    cx, cz = x0, BARB_Z - P.TUBE_BEND_R                                # the arc's centre
    pts = [(x0 + 1.0, BARB_Z)]
    for i in range(41):
        a = math.radians(90.0 + 90.0 * i / 40.0)
        pts.append((cx + P.TUBE_BEND_R * math.cos(a), cz + P.TUBE_BEND_R * math.sin(a)))
    pts.append((cx - P.TUBE_BEND_R, end_z))
    route = None
    for (ax, az), (bx, bz) in zip(pts, pts[1:]):
        d = math.hypot(bx - ax, bz - az)
        if d < 1e-9:
            continue
        seg = Plane(origin=((ax + bx) / 2, 0.0, (az + bz) / 2),
                    z_dir=(bx - ax, 0.0, bz - az)) * Pos(0, 0, -d / 2) * cyl_z(r, 0, d)
        route = seg if route is None else route + seg
    return route


def _rail_relief():
    """Clearance for the cradle rails' front lip.

    The lip stands at x 14 .. 16.5 and the holder's back face is at x 15, so the lip buries
    itself a millimetre and a half in the holder's +Y flank. The face cap carries the holder
    on along -X, so only that much of it is ever in the way.
    """
    y0 = P.BULKHEAD_Y - P.BULKHEAD_T - P.CLEAR - P.RAIL_T - P.CLEAR
    y1 = RAIL_Y_OUT + P.CLEAR
    zb = P.CRADLE_Z[0]
    return box(P.NOZZLE_HOLDER_X[0] - 1.0, P.CRADLE_X[1] + P.RAIL_LIP_L + P.CLEAR, y0, y1,
               zb - P.RAIL_H - P.CLEAR, zb + 3.0 + P.CLEAR)


@part("nozzle_holder")
def nozzle_holder():
    """Block behind the mouth, with a nose that carries the bore out to the face's inner wall.

    The nozzle is held twice: fifteen and a half millimetres of press fit in the nose's bore and
    the mouth the assembler cuts in the face cap, twenty-three millimetres further out. Two
    bearings that far apart are what hold the aim; a press fit alone would not.

    The nose stops short of the screw bosses in y, so the block still ends at NOZZLE_HOLDER_X[1]
    where the screws go through. The tube's fitting pushes into the barb seat low on the back
    face and a riser carries the water up into the back of the nozzle's bore.
    """
    x0, x1 = P.NOZZLE_HOLDER_X
    z = P.Z_MOUTH
    h = box(x0, x1, -BOSS_Y - 6, BOSS_Y + 6, BARB_Z - BARB_SEAT_R - 3.0, z + 10)
    h = h + cyl_x(NOSE_R, x1 - 0.01, HOLDER_R, 0, z)                       # the nose, out to the wall
    h = h & (Pos(0, 0, P.Z_HEAD) * Sphere(HOLDER_R))
    h = h - _rail_relief()
    h = h - cyl_x(P.NOZZLE_D / 2, BORE_X0, HOLDER_R + 1, 0, z)             # the nozzle's bore
    h = h - cyl_x(BARB_SEAT_R, x0 - 1, x0 + 5, 0, BARB_Z)                  # the fitting's seat
    h = h - cyl_x(FEED_R, x0 - 1, RISER_X + RISER_R, 0, BARB_Z)            # ... and its bore
    h = h - cyl_z(RISER_R, BARB_Z - 2, z + 2, RISER_X, 0)                  # the riser between them
    for y, zs in screw_points():
        h = h - cyl_x(P.M3_CLEAR / 2, x0 - 1, x1 + 1, y, zs)
        h = h - cyl_x(SCREW_HEAD_R, x0 - 1, x0 + P.SCREW_HEAD_H, y, zs)    # screw heads
    return h


@part("nozzle_bosses", section="face")
def nozzle_bosses():
    """Two bosses on the face's inner wall the holder screws into. Unioned into the face.

    Two disconnected solids on their own: they only become one part when the face cap is
    revolved around them. Each is clipped to the usual 1.2 mm bite into the wall, so it meets
    the skin but never breaks it, and its insert stops short of the tip.
    """
    x0 = P.NOZZLE_HOLDER_X[1]
    bosses = None
    for y, z in screw_points():
        b = cyl_x(BOSS_R, x0, P.HEAD_R + 8, y, z)
        b = b & (Pos(0, 0, P.Z_HEAD) * Sphere(P.HEAD_R - P.WALL + 1.2))
        b = b - cyl_x(P.INSERT_D / 2, x0 - 1, x0 + P.INSERT_DEPTH, y, z)
        bosses = b if bosses is None else bosses + b
    return bosses
