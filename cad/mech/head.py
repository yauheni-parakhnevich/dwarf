"""Inside the face: the nozzle and what holds it."""
from build123d import Pos, Sphere
import params as P
from mech import part
from mech.common import cyl_x, box

BOSS_R = 4.0               # the bosses on the face's inner wall the holder screws into
DRIVER_R = 3.0             # the stubby driver that reaches the screw heads along -X
SCREW_HEAD_R = 3.2         # counterbore for an M3 cheese head

# The cradle's rails reach out to this y beside the mouth, and they are in front of the
# tilt cradle all the way to x 16.5 - right where a screw on NOZZLE_BOSS_Y would want its
# driver. The pair moves out until a DRIVER_R shaft clears the rails by a millimetre.
RAIL_Y_OUT = P.BULKHEAD_Y + P.CLEAR + P.RAIL_T                     # 9.4
BOSS_Y = max(P.NOZZLE_BOSS_Y, RAIL_Y_OUT + DRIVER_R + 1.0)         # 13.4; NOZZLE_BOSS_Y fouls by 0.4

# The holder is trimmed to a sphere a clearance inside the face cap's seating lip, so it can
# neither touch the lip nor reach the shell however the corners of its block would fall.
HOLDER_R = P.HEAD_R - P.WALL - P.CLEAR - P.FACE_LIP_T - P.CLEAR    # 43.0


def screw_points():
    """(y, z) of the two screws that hold the nozzle holder onto the face's bosses."""
    return [(-BOSS_Y, P.Z_MOUTH), (BOSS_Y, P.Z_MOUTH)]


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
    """Block behind the mouth. The brass nozzle presses into the bore; the tube barbs onto its tail.

    It hangs off two bosses on the face cap and goes in with the cap, so its back face stops a
    millimetre short of the tilt cradle. The screws are driven along -X before the cap is seated.
    """
    x0, x1 = P.NOZZLE_HOLDER_X
    z = P.Z_MOUTH
    h = box(x0, x1, -BOSS_Y - 6, BOSS_Y + 6, z - 10, z + 10)
    h = h & (Pos(0, 0, P.Z_HEAD) * Sphere(HOLDER_R))
    h = h - _rail_relief()
    h = h - cyl_x(P.NOZZLE_D / 2, x0 - 1, x1 + 1, 0, z)
    h = h - cyl_x(P.NOZZLE_D / 2 + 1.5, x0 - 1, x0 + 4, 0, z)              # tube's barb seat
    for y, zs in screw_points():
        h = h - cyl_x(P.M3_CLEAR / 2, x0 - 1, x1 + 1, y, zs)
        h = h - cyl_x(SCREW_HEAD_R, x0 - 1, x0 + P.SCREW_HEAD_H, y, zs)      # screw heads
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
