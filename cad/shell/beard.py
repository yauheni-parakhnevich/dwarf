"""The beard collar: a solid ring round the neck, a beard down the chest, a cape over the fan.

It is a ring and not a shell - a closed profile swept round, BEARD_T thick, no solidify - and
its profile is allowed to change with the angle, which is the whole design. Three things want
different shapes out of the same part:

  the front   hangs to BEARD_BOTTOM_FRONT_Z as strands, standing off the chest far enough to
              clear the coat's own swell and the tops of the sleeves
  the flanks  stop at 352 or higher. The sleeves reach 348 and the collar has to miss them
  the back    hangs to BEARD_BOTTOM_BACK_Z as a cape over the exhaust, standing eight
              millimetres off the wall so the fan's air leaves downward and rain cannot run in

A hem at three heights is a change in z, and a swell can only move a point in radius, so the
collar is built with `loft`: one profile per angle, the same points in the same order, swept
round and closed.

What it may not do: the yoke's arms swing through r 66 between the deck and the head, so the
ring's inside stays at 69 or more over its whole height - the three screw bosses included, and
they are the closest thing to it.
"""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import P, arc, dome, export_raw, finish, fresh_scene, lerp, loft, wrap  # noqa: E402

SEG = 288            # 1.25 degrees: nine columns across a strand
ROWS = 52            # up the inside and down the outside, about two millimetres apart
NOISE = 0.5          # hair, over the locks rather than instead of them
NOISE_SCALE = 4.0
STRANDS = 18         # round the whole circle; twenty degrees each, five and a half of them
STRAND_D = 6.0       # how far a lock stands out of the collar
STRAND_HEM = 10.0    # and how much longer it hangs than the gap beside it

# The hem, by angle from the front. It comes to a point on the centre line - a beard ends in a
# point, a frill ends in a circle - rises across the flanks, where the sleeves top out at 348,
# and drops away again into the cape.
_HEM = [(0.0, P.BEARD_BOTTOM_FRONT_Z), (25.0, 353.0), (45.0, 359.0), (90.0, 360.0),
        (120.0, 353.0), (138.0, P.BEARD_BOTTOM_BACK_Z), (180.0, P.BEARD_BOTTOM_BACK_Z)]
# Air between the torso's skin and the ring's inside: two millimetres where it wraps the
# shoulders, more where it hangs free. The front's four extra clear the coat's chest swell and
# its sleeves; the back's six are the fan's breathing room, held to the top of the fan and shut
# again above it - the air leaves downward, and what closes over it is what keeps the rain out.
_GAP_Z = [(P.Z_FAN + P.FAN / 2 + 2.0, 1.0), (402.0, 0.0)]
FAN_GAP = 6.0
# Three bosses on the inside for the collar's screws. The ring is BEARD_T thick and the insert
# the screws thread into is INSERT_DEPTH deep, so a hole drilled straight into the ring would
# come out the other side. The material comes from the inside, where there is nothing between
# the collar and the torso's neck, and it still leaves the yoke's arms their 69 mm.
SCREW_DEG = (90.0, 210.0, 330.0)
SCREW_Z = P.Z_TORSO_TOP - 4.0
BOSS_DEEP = P.INSERT_DEPTH + 1.5 - P.BEARD_T         # 4.5 in from the ring, 11 mm of stock all told
BOSS_HALF = 11.0                                     # of arc and of height, at the ring's radius


def _front(th):
    """1 across the beard, 0 by seventy degrees out."""
    return max(0.0, min(1.0, (70.0 - abs(math.degrees(wrap(th)))) / 20.0))


def _back(th):
    """1 across the cape, 0 by a hundred and ten degrees."""
    return max(0.0, min(1.0, (abs(math.degrees(wrap(th))) - 110.0) / 20.0))


def _strand(th, z):
    """Where a strand's crest is, from 0 between strands to 1 down the middle of one.

    The phase drifts with height so the strands are not plumb, and the seventh harmonic makes
    some of them fatter than their neighbours. Thirty identical ridges are a lampshade.
    """
    phase = 0.25 * (z - P.BEARD_BOTTOM_FRONT_Z) / 50.0
    v = 0.5 * (1.0 + math.cos(STRANDS * th + phase))
    return v ** 0.8 * (1.0 + 0.3 * math.cos(7.0 * th + 1.1)) / 1.3


def _hem(th):
    """The bottom of the ring at this angle, strands and all."""
    z = lerp(abs(math.degrees(wrap(th))), _HEM)
    return z + STRAND_HEM * _front(th) * (1.0 - _strand(th, z))


def _wall(th, z):
    """The ring's inside before the screw bosses: over the shoulders with air, then in to the neck."""
    if z >= P.Z_TORSO_TOP:
        t = (z - P.Z_TORSO_TOP) / (P.BEARD_TOP_Z - P.Z_TORSO_TOP)
        r0 = P.shell_r(P.TORSO_PROFILE, P.Z_TORSO_TOP) + 2.0
        return r0 + (P.BEARD_R_IN_TOP - r0) * t
    gap = 2.0 + (4.0 * _front(th) + FAN_GAP * _back(th)) * lerp(z, _GAP_Z)
    return P.shell_r(P.TORSO_PROFILE, z) + gap


def _boss(th, z):
    """How far the screw bosses stand in from the ring's inside at this point."""
    r = _wall(th, SCREW_Z)
    return max(dome(arc(th, d, r), z - SCREW_Z, BOSS_HALF, BOSS_HALF, BOSS_DEEP, soft=1.4)
               for d in SCREW_DEG)


def _inner(th, z):
    return _wall(th, z) - _boss(th, z)


def _outer(th, z):
    d = STRAND_D * _front(th) * lerp(z, [(400.0, 1.0), (425.0, 0.0)]) * _strand(th, z)
    return _wall(th, z) + P.BEARD_T + d


def _rows(th):
    """One angle's profile: up the inside, over the top rim, down the outside. `loft` closes it
    across the hem.

    The rim is rolled rather than cut square. Square, it reads as the lip of a bucket the head
    is standing in, which is the one thing this shape must not look like; three points of roll
    cost nothing and break that line.
    """
    z0, z1 = _hem(th), P.BEARD_TOP_Z - 1.4
    zs = [z0 + (z1 - z0) * i / (ROWS - 1) for i in range(ROWS)]
    rows = [(_inner(th, z), z) for z in zs]
    ri, ro = _inner(th, z1), _outer(th, z1)
    rows += [(ri + 0.35, z1 + 0.9), ((ri + ro) / 2, P.BEARD_TOP_Z), (ro - 0.35, z1 + 0.9)]
    return rows + [(_outer(th, z), z) for z in reversed(zs)]


def beard():
    ob = loft("beard", _rows, segments=SEG)
    finish(ob, displace=NOISE, noise_scale=NOISE_SCALE, solidify=False)
    export_raw(ob, "beard")


if __name__ == "__main__":
    fresh_scene()
    beard()
