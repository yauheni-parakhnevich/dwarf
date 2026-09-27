"""Inside the head: the nozzle's holder.

The nozzle is fixed in the mouth now; the head nods and the jet goes where the head looks. The
holder is an interface part of the `head` section, printed with it: the assembler clips it into
the face's wall like the belt flanges into the ring, and cuts the mouth through the skin in front
of it, so the bore and the mouth are coaxial by construction and nothing is screwed.

It could not be a bracket off the spider. The unit goes on over the spider from above, and the
face over the mouth comes back in to x 57 at the eyes and to x 52 under the brim: nothing that
reaches forward to the mouth from the spider can be passed by it. So the water joint is made by
the unit going on: the tube stands up out of the spider on the axis as a stab, and the holder
carries a socket on the axis that slides down over it, sealed by an O-ring in the socket. The
water pushes the tube down out of it with 20 N at 7 bar; the spider's clamp screw and the
head's four screws hold that. From the socket a channel runs forward and down to the nozzle's
back. The holder is part of the turning unit, so like the rest of it it keeps NECK_SPHERE_R
from C where it faces the coat's dome; the nozzle's back can therefore be no nearer the axis
than x 73.5, and the nozzle is NOZZLE_L long.
"""
import math
from build123d import Pos
import params as P
from mech import part
from mech.common import ball, box, cyl_x, cyl_z, polyline
from mech.nod import xz_prism

SOCKET_Z0 = P.SPIDER_Z[1] + 2.0                     # 452: the socket's mouth, 2 mm over the spider
SOCKET_BORE = P.TUBE_OD + 0.3
SOCKET_TOP = SOCKET_Z0 + P.SOCKET_ENGAGE + 2.0      # the bore's roof; the stab stops 2 short of it
ORING_Z = SOCKET_Z0 + 4.0                           # a 5 x 1.5 O-ring's groove
ORING_GROOVE = (P.TUBE_OD + 2 * 1.2, 2.0)           # diameter, height
WEB_T = 12.0
NOZZLE_BORE = P.NOZZLE_D - 0.1                      # the nozzle is pressed in
CHAMBER_X = (P.NOZZLE_TIP_X - P.NOZZLE_L - 2.0, P.NOZZLE_TIP_X - P.NOZZLE_L + 0.1)
CHAMBER_Z = P.Z_MOUTH + 0.8                         # above the axis: below it is too near the dome
CHAMBER_D = 4.0
CHANNEL_D = 3.2
BLANK_X = 100.0                                     # the nozzle's block runs out past the skin


def channel_points():
    """The water's way from the socket's roof to the chamber behind the nozzle."""
    x_ch = (CHAMBER_X[0] + CHAMBER_X[1]) / 2
    return [(0.0, 0.0, SOCKET_TOP - 1.0), (40.0, 0.0, 452.0), (x_ch, 0.0, CHAMBER_Z + 0.5)]


@part("nozzle_holder", section="head")
def nozzle_holder():
    """A socket on the axis for the stab, a web forward to the mouth, and the nozzle's bore.

    Drawn as a blank: the nozzle's block runs out past the skin and the assembler clips it into
    the face's wall; the web and the socket stand free inside the head, joined to the face by it.
    """
    zt = SOCKET_TOP + 8.0
    h = box(-8.0, 8.0, -8.0, 8.0, SOCKET_Z0, zt)                                   # the socket
    h = h + xz_prism([(-6.0, zt), (-6.0, SOCKET_Z0), (28.0, SOCKET_Z0), (62.0, 431.0), (BLANK_X, 431.0),
                      (BLANK_X, 434.0), (70.0, 449.0), (6.0, zt)], -WEB_T / 2, WEB_T / 2)
    h = h + box(CHAMBER_X[0] - 2.0, BLANK_X, -7.0, 7.0, P.Z_MOUTH - 7.0, P.Z_MOUTH + 8.0)   # the nozzle's block
    h = h - ball(P.NECK_SPHERE_R + 0.5)
    h = h - cyl_z(SOCKET_BORE / 2, SOCKET_Z0 - 1.0, SOCKET_TOP)
    h = h - cyl_z(ORING_GROOVE[0] / 2, ORING_Z, ORING_Z + ORING_GROOVE[1])
    h = h - (Pos(0, 0, SOCKET_Z0) * _chamfer())                                   # the stab's lead-in
    h = h - polyline(channel_points(), CHANNEL_D / 2)
    h = h - cyl_x(CHAMBER_D / 2, CHAMBER_X[0], CHAMBER_X[1] + 0.5, 0.0, CHAMBER_Z)
    return h - cyl_x(NOZZLE_BORE / 2, CHAMBER_X[1], BLANK_X + 1.0, 0.0, P.Z_MOUTH)


def _chamfer():
    from build123d import Cone
    return Pos(0, 0, 0.75) * Cone(SOCKET_BORE / 2 + 1.5, SOCKET_BORE / 2, 1.5)


# --- the beard's halves to the head ------------------------------------------------------------
# The beard goes on in two halves before the head (params' FITTING_SPLIT), and each is held to the
# head, not to the other: two tongues rise from each half's top edge TONGUE_H into the head, a
# CLEAR_SHELL inside it, and a radial countersunk M3 through the head's lower band goes into an
# insert in each. They are at 45 and 90 degrees either side: there both the beard and the head have
# a wall at their joint that stands well outside the sphere the unit keeps from C (at 30 degrees the
# insert would have been inside it, and was cut away with it - which a ray test now catches), and
# they are 15 and 30 degrees from the head's own four screws at 60/120/240/300.
TONGUE_H = 10.0
TONGUE_T = 3.0
TONGUE_HALF_DEG = 7.0
TONGUE_ANGLES = (45.0, 90.0, 270.0, 315.0)
TONGUE_SCREWS_Z = 417.0
Z_BEARD_TOP = P.SECTIONS_STATUE["beard"][1]            # 412


def _inside(name, a, z0, z1, half=TONGUE_HALF_DEG):
    from mech.collar import _near
    from mech.common import inner_table
    rows, step = inner_table(name)
    seen = [row[i] for z, row in rows.items() if z0 <= z <= z1 for i in _near(a, rows, step, half) if row[i] > 0]
    return min(seen)


def tongue_out_r(a):
    """A tongue's outside: the head's inside over the tongue's height, less CLEAR_SHELL."""
    return _inside("head", a, Z_BEARD_TOP, Z_BEARD_TOP + TONGUE_H + 2.0) - P.CLEAR_SHELL


@part("beard_tongue", section="beard")
def beard_tongue():
    """Four tongues on the beard's top edge that the head goes down over and is screwed to."""
    from build123d import Axis
    from mech.collar import _sector
    out = None
    for a in TONGUE_ANGLES:
        ro = tongue_out_r(a)
        rw = _inside("beard", a, Z_BEARD_TOP - 8.0, Z_BEARD_TOP) + P.WALL - 1.2
        up = _sector(a, TONGUE_HALF_DEG, Z_BEARD_TOP - 0.01, Z_BEARD_TOP + TONGUE_H) & (
            cyl_z(ro, Z_BEARD_TOP - 1, Z_BEARD_TOP + TONGUE_H + 1) - cyl_z(ro - TONGUE_T, Z_BEARD_TOP - 2, Z_BEARD_TOP + TONGUE_H + 2))
        root = _sector(a, TONGUE_HALF_DEG, Z_BEARD_TOP - 8.0, Z_BEARD_TOP) & (
            cyl_z(max(rw, ro), Z_BEARD_TOP - 9, Z_BEARD_TOP + 1) - cyl_z(ro - TONGUE_T, Z_BEARD_TOP - 10, Z_BEARD_TOP + 2))
        boss = (cyl_x((P.INSERT_D + 5.0) / 2, ro - 8.0, ro, 0.0, TONGUE_SCREWS_Z)
                - cyl_x(P.INSERT_D / 2, ro - P.INSERT_DEPTH, ro + 1.0, 0.0, TONGUE_SCREWS_Z)).rotate(Axis.Z, a)
        t = up + root + (boss & _sector(a, TONGUE_HALF_DEG + 3, Z_BEARD_TOP, Z_BEARD_TOP + TONGUE_H))
        t = t - cyl_x(P.INSERT_D / 2, ro - P.INSERT_DEPTH, ro + 1.0, 0.0, TONGUE_SCREWS_Z).rotate(Axis.Z, a)
        out = t if out is None else out + t
    return out - ball(P.NECK_SPHERE_R + 0.5)          # like the rest of the unit, off the collar
