"""The joint between the belt ring (`torso`) and the collar.

The collar - socket, bib and dome - goes on after the mechanism and comes off for service, so it
is screwed, not glued. Four tabs hang from its bottom edge SPIGOT_H down into the ring's top, a
CLEAR_SHELL inside the ring, and four radial countersunk M3 x 10 go in from outside through the
ring's top edge into inserts in them.

Why tabs and not a ring, and why at 45, 125, 235 and 315 degrees: the collar is lowered over the
deck and everything under it, so whatever hangs from it has to pass all of that on the way down.
A ring would pass the deck's rim by 0.3 mm at the front and the pan servo's hangers not at all at
300 degrees; four tabs miss the hangers (280..305 degrees), the phone and its sled (inside 35
degrees of the front), the fan's corners (167 and 193) and the filler port at 160, and the deck is trimmed to them. They
are also where the turning unit reaches down lowest over the ring - to the beard's bottom edge in
front and to 20 degrees under C at the back corners - so at rest the screws are under it, and a
driver still reaches them straight in under its rim, at rest.

Drawn as a blank: above the joint each tab runs out into the collar's wall and the assembler
clips it to the grown cavity and unions it into `collar`; below it, its outside is the ring's
inside less CLEAR_SHELL, which the statue publishes as `torso_inner`.
"""
import math
from build123d import Axis, Polygon, Pos, extrude
import params as P
from mech import part
from mech.common import cyl_x, cyl_z, inner_table, polar

Z_JOINT = P.Z_TURN - P.TURN_GAP                           # 307
Z_TAB0 = Z_JOINT - P.SPIGOT_H                             # 297, the tabs' foot
Z_TAB1 = Z_JOINT + 12.0                                   # the tabs' root runs this far up the collar
BOSS_D = P.INSERT_D + 5.0
BOSS_T = 8.0                                              # radially, round the insert


def _near(a, rows, step, half):
    idx = [i for i in range(len(next(iter(rows.values()))))
           if abs((i * step - a + 180.0) % 360.0 - 180.0) <= half + step]
    return idx


def ring_inside(a, half=P.SPIGOT_HALF_DEG):
    """The least radius of the ring's inside over the tab's height and width: what the tab's
    outside has to pass, the whole way down."""
    t = inner_table("torso")
    if t is None:
        return 84.0
    rows, step = t
    seen = [row[i] for z, row in rows.items() if Z_TAB0 - 2 <= z <= Z_JOINT
            for i in _near(a, rows, step, half) if row[i] > 0]
    return min(seen)


def collar_inside(a, z0, z1, half=P.SPIGOT_HALF_DEG):
    t = inner_table("collar")
    if t is None:
        return 84.0
    rows, step = t
    seen = [row[i] for z, row in rows.items() if z0 - 2 <= z <= z1
            for i in _near(a, rows, step, half) if row[i] > 0]
    return min(seen)


def tab_out_r(a):
    return ring_inside(a) - P.CLEAR_SHELL


def tab_in_r(a):
    """How far in a tab reaches, the boss round its insert included: the collar's shadow."""
    return tab_out_r(a) - BOSS_T


def _sector(a, half, z0, z1, r=200.0):
    pts = [(0.0, 0.0)] + [polar(r, a + half * (2 * i / 12 - 1)) for i in range(13)]
    return Pos(0, 0, z0) * extrude(Polygon(*pts), z1 - z0)


def screw_head(a):
    """Where a joint screw's head sits, (x, y, z) at the ring's outside, and its inward direction.
    The ring's outside there is read off the section by the assembler; this is the tab's side."""
    r = tab_out_r(a)
    x, y = polar(r, a)
    return (x, y, P.COLLAR_SCREWS_Z), (-math.cos(math.radians(a)), -math.sin(math.radians(a)), 0.0)


@part("collar_spigot", section="collar")
def collar_spigot():
    """Four tabs under the collar that go down into the ring and take its four screws."""
    out = None
    h = P.SPIGOT_HALF_DEG
    for a in P.COLLAR_SCREW_ANGLES:
        ro = tab_out_r(a)
        tab = _sector(a, h, Z_TAB0, Z_JOINT) & (cyl_z(ro, Z_TAB0, Z_JOINT) - cyl_z(ro - P.SPIGOT_T, Z_TAB0 - 1, Z_JOINT + 1))
        # its root, in 2 mm steps up the collar's wall, each embedded 1.2 mm into it
        z = Z_JOINT - 0.01
        while z < Z_TAB1:
            rw = collar_inside(a, z, z + 2.0) + P.WALL - 1.2
            tab = tab + (_sector(a, h, z, z + 2.0) & (cyl_z(rw, z, z + 2.0) - cyl_z(ro - P.SPIGOT_T, z - 1, z + 3)))
            z += 2.0
        boss = (cyl_x(BOSS_D / 2, ro - BOSS_T, ro, 0.0, P.COLLAR_SCREWS_Z)
                - cyl_x(P.INSERT_D / 2, ro - P.INSERT_DEPTH, ro + 1.0, 0.0, P.COLLAR_SCREWS_Z))
        tab = tab + boss.rotate(Axis.Z, a)
        tab = tab - cyl_x(P.INSERT_D / 2, ro - P.INSERT_DEPTH, ro + 1.0, 0.0, P.COLLAR_SCREWS_Z).rotate(Axis.Z, a)
        out = tab if out is None else out + tab
    return out
