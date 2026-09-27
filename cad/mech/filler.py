"""The filler, outside on the coat's back: refilling needs nothing taken off.

A port through the belt ring's wall at FILLER_PORT_AZ, its axis tilted FILLER_PORT_TILT up and
out. The cap - the M22 retention thread and the O-ring groove the filler always had, and a grip bar
a gloved hand can turn - screws onto a neck standing in a pocket in the port, so the cap sits sunk
in the coat and only its top and the bar stand out. Behind the pocket's floor a channel runs in and
down to a barb pointing straight down; the 8 mm hose goes from it down through a bore in the
chassis, both belt flanges and the divider, and on under the flange to the tank head's barb.

The port is an interface part of `torso`, clipped to the grown cavity and welded in like the belt
flanges. The neck is one too, but it stands in the pocket partly outside the skin, so the assembler
unions it unclipped (`UNCLIPPED` in assemble.py) and cuts the pocket round it, the bore through it
and a weep for the pocket's low edge.

Where a spill goes. Poured outside the mouth, it runs down the coat's back. In the pocket, it runs
in through the bore, or out through the weep at the pocket's lowest point. At the one joint inside,
the barb, a leak meets a drip lip that turns it onto the hose's outside, and the hose's bores through
the chassis, the flanges and the divider are 1.5 mm wider than it all round: it runs down the hose
into the wet side, at the back, 120 mm from the phone and 16 mm outside the boards' edge.
"""
import math
from build123d import Cone, Cylinder, Location, Plane, Pos, Sphere
import params as P
from mech import part
from mech.common import BARB_BORE_R, BARB_R, BARB_RING, barb_rings, cyl_z, polyline

TILT = math.radians(P.FILLER_PORT_TILT)
AZ = math.radians(P.FILLER_PORT_AZ)
E_R = (math.cos(AZ), math.sin(AZ), 0.0)                   # outward, horizontal
E_T = (-math.sin(AZ), math.cos(AZ), 0.0)                  # sideways
U = tuple(math.cos(TILT) * a + math.sin(TILT) * b for a, b in zip(E_R, (0, 0, 1)))   # the axis, out
V = tuple(-math.sin(TILT) * a + math.cos(TILT) * b for a, b in zip(E_R, (0, 0, 1)))  # up, across it
O = (P.FILLER_PORT_SKIN_R * E_R[0], P.FILLER_PORT_SKIN_R * E_R[1], P.FILLER_PORT_Z)
FRAME = Plane(origin=O, x_dir=E_T, z_dir=U)               # local z along the axis, y = V

WALL = 2.0                                                # round the pocket
FLOOR_T = 3.0
NECK_H = 10.5                                             # the neck, up from the pocket's floor
THREAD_Z0 = 0.5                                           # its thread starts this far up it
CAP_END = 0.5                                             # the cap's open end over the pocket's floor


def at(local):
    """A point in the port's frame, (x across, y up-across, z along the axis) -> world."""
    x, y, z = local
    return tuple(o + x * a + y * b + z * c for o, a, b, c in zip(O, E_T, V, U))


def barb_root():
    """Where the channel turns down into the barb: over the passage, 5 mm under the pocket's floor."""
    floor = at((0.0, 0.0, -P.FILLER_POCKET_D - FLOOR_T))
    x, y = passage_xy()
    return (x, y, floor[2] - 5.0)


KEEP_R = 64.5                                             # the cage's foot ring is 63.5 out
BARB_TOP = 8.0                                            # the barb starts this far under its root


def barb_mouth():
    """The barb's open end, pointing down."""
    x, y, z = barb_root()
    return (x, y, z - BARB_TOP - P.HOSE_BARB_L)


def hose_start():
    """The hose's first point: its end, pushed up the barb to half a millimetre under the lip."""
    x, y, z = barb_root()
    return (x, y, z - BARB_TOP - 0.5)


def passage_xy():
    r, a = P.FILLER_PASSAGE
    return r * math.cos(math.radians(a)), r * math.sin(math.radians(a))


def _local(shape):
    return FRAME * shape


def _lcyl(r, z0, z1):
    return Pos(0, 0, (z0 + z1) / 2) * Cylinder(r, z1 - z0)


@part("filler_port", section="torso")
def filler_port():
    """The port's body: a cup round the pocket, its floor, the channel behind it and the barb.

    Drawn as a blank past the skin; the assembler clips it into the ring's wall.
    """
    d = P.FILLER_POCKET_D
    body = _local(_lcyl(P.FILLER_POCKET_R + WALL, -d - FLOOR_T, 30.0) - _lcyl(P.FILLER_POCKET_R, -d, 31.0))
    root = barb_root()
    start = at((0.0, 0.0, -d - FLOOR_T + 0.5))
    body = body + polyline([start, root], 5.5) + Pos(*root) * Sphere(5.5)
    x, y, z = root
    mouth = barb_mouth()[2]
    body = body + cyl_z(BARB_R, mouth, z, x, y)                                     # the barb
    for off in barb_rings():
        body = body + cyl_z(BARB_R + P.HOSE_BARB_LIP, mouth + off, mouth + off + BARB_RING, x, y)
    # the drip lip: a funnel from the boss down round the hose's end, so what runs down the body
    # is led onto the hose's outside and not dropped beside it
    lip = Pos(x, y, z - BARB_TOP + 2.0) * Cone(P.HOSE_OD / 2 + 0.6, 6.5, 4.0)
    body = body + (lip - cyl_z(P.HOSE_OD / 2 + 0.1, z - BARB_TOP - 1.0, z - BARB_TOP + 4.0, x, y))
    body = body - polyline([at((0.0, 0.0, -d + 0.5)), root], BARB_BORE_R)             # the water's way
    body = body - cyl_z(BARB_BORE_R, mouth - 1.0, z + 0.5, x, y)
    body = body - _local(_lcyl(P.FILLER_D / 2, -d - FLOOR_T - 0.5, -d + 1.0))       # the neck's bore on
    # the cage's foot ring goes down past it when the chassis goes in: nothing inside KEEP_R
    return body - weep() - cyl_z(KEEP_R, 200.0, 350.0)


@part("filler_neck", section="torso")
def filler_neck():
    """The M22 neck the cap screws onto, standing on the pocket's floor. Welded in unclipped."""
    from bd_warehouse.thread import IsoThread
    d = P.FILLER_POCKET_D
    thread = IsoThread(major_diameter=P.FILLER_CAP_THREAD_MAJOR, pitch=P.FILLER_CAP_PITCH,
                       length=NECK_H - THREAD_Z0 - 1.0, external=True, end_finishes=("square", "square"))
    neck = _lcyl(thread.min_radius, -d - 0.5, -d + NECK_H) + Pos(0, 0, -d + THREAD_Z0) * thread
    neck = neck - _lcyl(P.FILLER_D / 2, -d - 1.0, -d + NECK_H + 1.0)
    return _local(neck)


def cap_location():
    """Where the cap sits: its open end CAP_END over the pocket's floor, its axis the port's."""
    return Location(Plane(origin=at((0.0, 0.0, -P.FILLER_POCKET_D + CAP_END)), x_dir=E_T, z_dir=U))


def pocket_cut():
    """What the assembler cuts through the skin: the pocket round the neck, and the bore."""
    d = P.FILLER_POCKET_D
    return _local(_lcyl(P.FILLER_POCKET_R, -d, 40.0) + _lcyl(P.FILLER_D / 2, -d - FLOOR_T - 0.5, 40.0))


def weep():
    """A 3 mm drain from the pocket's lowest point out through the wall, 10 degrees down."""
    start = at((0.0, -(P.FILLER_POCKET_R - 1.5), -P.FILLER_POCKET_D + 1.5))
    dn = math.radians(10.0)
    d = (math.cos(dn) * E_R[0], math.cos(dn) * E_R[1], -math.sin(dn))
    end = tuple(s + 25.0 * c for s, c in zip(start, d))
    return polyline([start, end], 1.5)


def funnel(length=80.0, r=12.5):
    """A funnel's spout, or a bottle's: a cylinder along the axis out from the pocket's mouth."""
    return _local(_lcyl(r, 0.5, 0.5 + length))
