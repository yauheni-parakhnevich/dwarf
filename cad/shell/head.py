"""NOT BUILT. The shell is the statue now: `cad/statue.py` cuts the sections out of
`in/gnome_ai.glb`, and `build.py shell` no longer runs this file. It is kept for its swell
functions, which are the record of what the shape had to clear, and for `common.py`.
"""
"""The head - one sphere with the face on it - and the hat.

The head is exported whole. The assembler splits it at FACE_SPLIT_X into a face cap and a
back, cuts the mouth, the bottom opening and the ear bore, and unions in the ear boss, the
cradle rails, the face stop and the lip. So three patches of this sphere are not the sculpt's
to touch, and the face is laid out around them:

  the mouth      a MOUTH_D + 6 disc where the nozzle leaves the head, at Z_MOUTH on the front
                 meridian. The moustache's two lobes start above it and sweep out past it, and
                 the nose's underside stops short of it
  the ears       three millimetres either side of the tilt axis at y = +/- HEAD_R, where the
                 coupler comes through one wall and the ear boss sits on the other
  the bottom     twenty millimetres about the lower pole, which the tube and the wires pass

No ears are sculpted: the mechanism's two bosses are the ears. Nothing on the face reaches
past HEAD_R + 16, which is the nose, so the cap still lifts off along +X and the head still
clears the beard collar at both tilt stops.

The face is relief on the revolve itself rather than a heap of joined ellipsoids, for the
reason `body` gives: a voxel remesh keeps every crease a union leaves. Here it also keeps the
sphere exactly the sphere the mechanism was drawn against - no remesh, so no voxel shrinkage -
and the domes are softened at their edges, because solidify walls the inside of a crease and a
crease sharper than the wall folds that inside surface through itself.
"""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (P, arc, dome, export_raw, finish, fresh_scene, revolve, ridge, wrap)  # noqa: E402

R, Z = P.HEAD_R, P.Z_HEAD
SEG = 240            # 1.5 degrees, 1.3 mm of arc at the equator
ROWS = 108           # rows by angle, not by height, so the crown stays as fine as the cheek
NOISE = 0.35         # skin; kept under the half millimetre the bare patches are checked to
NOISE_SCALE = 9.0

# Where the nozzle leaves the head, and how much bare sphere it is owed all round.
MOUTH = (math.sqrt(R ** 2 - (P.Z_MOUTH - Z) ** 2), 0.0, P.Z_MOUTH)
MOUTH_KEEP = P.MOUTH_D / 2 + 3.0

# (degrees from the front, z, half width in arc, half height, how proud, edge softness).
# The bridge and the tip are two domes rather than one: the tip stands two and a half
# millimetres past the bridge, which is what makes a nose a ball and not a beak.
_BRIDGE = (0.0, 480.0, 15.0, 12.0, 13.0, 1.5)
_TIP = (0.0, 473.0, 10.0, 8.0, 15.5, 1.4)
_CHEEK = (44.0, 470.0, 15.0, 13.0, 6.5, 1.6)             # out at the sides, clear of the moustache
_SOCKET = (24.0, 486.0, 14.0, 8.5, 4.0, 1.3)             # subtracted: the eye sits in it
# (degrees, z, half width, height) at each end of a sweep
_BROW = ((6.0, 491.0, 9.0, 5.0), (40.0, 498.0, 8.0, 5.5))
_TACHE = ((15.0, 468.0, 8.5, 8.5), (45.0, 452.0, 8.0, 5.0))
_FOLD = ((28.0, 470.0, 5.0, 2.5), (38.0, 457.0, 5.0, 2.0))   # subtracted: cheek from moustache


def _skull(n=ROWS):
    """The sphere as a profile, stepped by angle so the crown is no coarser than the cheeks."""
    return [(R * math.sin(math.pi * i / n), Z + R * math.cos(math.pi * i / n)) for i in range(n + 1)]


def _face_dr(th, z):
    """The face as an offset from the sphere, in millimetres of radius about the Z axis.

    Near the equator that offset is a push straight forward, which is what a nose is. Every
    feature is mirrored in y, and every one dies out well inside sixty degrees, so all of it
    lands on the face cap rather than across the plane the assembler splits at.
    """
    th = wrap(th)
    u = arc(th, 0.0, R)
    d = max(dome(u, z - _BRIDGE[1], *_BRIDGE[2:]), dome(u, z - _TIP[1], *_TIP[2:]))
    for s in (1, -1):
        deg, zc, ru, rv, h, soft = _CHEEK
        d = max(d, dome(arc(th, s * deg, R), z - zc, ru, rv, h, soft))
        for pair in (_BROW, _TACHE):
            d = max(d, ridge(u, z, [(s * math.radians(a) * R, zc, w, h) for a, zc, w, h in pair],
                             sharp=0.85, soft=1.3))
    for s in (1, -1):                                    # then what is cut into it
        deg, zc, ru, rv, h, soft = _SOCKET
        d -= dome(arc(th, s * deg, R), z - zc, ru, rv, h, soft)
        d -= ridge(u, z, [(s * math.radians(a) * R, zc, w, h) for a, zc, w, h in _FOLD], soft=1.5)
    return d


def head():
    ob = revolve("head", _skull(), segments=SEG, swell=_face_dr)
    finish(ob, displace=NOISE, noise_scale=NOISE_SCALE)
    export_raw(ob, "head")


def hat():
    """A closed cone on a flat brim, leaning forward from the crown's foot.

    The brim's underside is flat and stays flat: it sweeps over the yoke's arms at the tilt
    stops, and Z_HAT is where it clears them. The lean is quadratic from the foot, so the hat
    leaves the brim square to the head and only the tip carries HAT_BEND.

    Closed and then solidified, like every other section. The assembler cuts the spherical
    seat, which is what opens it.
    """
    z0, z1 = P.SECTION_Z["hat"]
    foot = z0 + P.HAT_BRIM_T
    brim, cone, tip = P.HAT_BRIM_R, P.HAT_CONE_R, P.HAT_TIP_R

    def lean(z):
        t = max(0.0, (z - foot) / (z1 - foot))
        return P.HAT_BEND * t * t

    rows = [(0.0, z0), (brim - 12.0, z0)]                                 # the flat underside
    # The edge is rolled over a full HAT_BRIM_T of felt rather than tapered to nothing: a brim
    # thinner than two walls has no room for a cavity, and solidify folds its two insides
    # through each other trying to make one. It also carries the roll half a millimetre past
    # HAT_BRIM_R, so the underside is still flat where the brim is measured, at the radius
    # itself; the tilt sweep has five millimetres in hand at the tighter of the two stops.
    rows += [(brim + 0.2, z0), (brim + 0.6, z0 + 0.6), (brim + 0.6, foot - 1.6),
             (brim + 0.2, foot - 1.0), (brim - 4.0, foot)]
    rows += [(cone + 6.0, foot), (cone, foot + 1.5)]                      # the crown's foot
    n = 22
    for i in range(1, n + 1):
        t = i / n
        rows.append((max(tip * 0.8, cone * (1.0 - t) ** 0.8), foot + 1.5 + (z1 - tip - foot - 1.5) * t))
    rows += [(tip * 0.55, z1 - tip * 0.45), (0.0, z1)]                    # the tip, rounded over
    ob = revolve("hat", rows, segments=SEG, lean=lean)
    finish(ob, displace=NOISE, noise_scale=12.0)
    export_raw(ob, "hat")


if __name__ == "__main__":
    fresh_scene()
    head()
    fresh_scene()
    hat()
