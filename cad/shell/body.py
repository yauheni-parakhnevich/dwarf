"""NOT BUILT. The shell is the statue now: `cad/statue.py` cuts the sections out of
`in/gnome_ai.glb`, and `build.py shell` no longer runs this file. It is kept for its swell
functions, which are the record of what the shape had to clear, and for `common.py`.
"""
"""Base and upper torso, raw. Openings and interface parts are added by assemble.py.

Every height here comes out of `params`, and so does the one rule that shapes the whole
sculpt: the profiles in `params` are the envelope the mechanism was designed against, and the
widest of them is three millimetres inside the bed. A gnome cannot be carved by adding to a
barrel that is already at its limit, so he is carved by taking away. The boot well under the
hem, the ten folds down the skirt, the belt's groove and the tuck along the flanks are all
cut into the profile; what is left standing on it is the hem, the belly and the crest of each
fold. Only the boots, the buckle, the buttons, the sleeves and the window's hood stand proud,
none of them by more than a hand's worth, and none where an interface part meets the wall.

Almost all of that is one function per section, passed to `revolve` as its swell and written
out of the relief helpers in `common`, so the coat is a single smooth surface rather than a
barrel with lumps welded to it. Only the buckle and the hood are joined solids, because both
want the hard edge a union gives.

Where the skin may not move, and why:
  base 214..238    belt_flange_lower follows the wall height by height over its 16 mm
  torso 230..250   belt_flange_upper, and the chassis on top of it
  torso 384..400   the deck ring's four webs reach the wall
  the hatch        the panel's lip is let into the wall at HATCH_HALF_ANGLE and at HATCH_Z
  the window       a flat pane sits against the wall's inside at LENS_FRONT_X, so the glass
                   and five millimetres round it are bare revolve: no feature, no fold, no
                   swell. The hood starts above that margin, the hands beside it, and the
                   coat's placket runs up the far side of the centre line, because the camera
                   sits CAM_Y off it and a centred row of buttons would land on the glass
  the back         the filler neck on the base and the fan on the torso are both sized from
                   shell_r, so the folds fade out over both patches
"""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (P, add_floor, arc, cut_z, dome, ellipsoid, export_raw, finish,  # noqa: E402
                    fresh_scene, join_remesh, lerp, revolve, ridge, sampled, skin_point, smax, wrap)

SEG = 192            # rings of the revolve: 1.9 degrees, three millimetres of arc at the belly
STEP = 1.5           # rows up it, so a swell can carve between the profile's own points
VOXEL = 1.4          # the skin's grain; 1.0 doubles the file for detail the coat does not need
NOISE = 0.7          # outward-only, the felt of the coat
NOISE_SCALE = 14.0
FOLDS = 10






def _folds(th, amp, twist=0.0):
    """Eight cloth folds: the crest of each stays on the profile, the crease sinks `amp` in.

    The power pulls the curve off a cosine's lazy bottom, so the crease is a line and the crest
    a broad face, which is what a heavy coat does and what a fluted vase does not. The third
    harmonic makes some folds deeper than their neighbours: ten identical flutes read as
    turning, ten unequal ones read as cloth. A crest sits on the centre line front and back,
    which is where the coat's front falls and where the filler neck wants flat wall.
    """
    if amp <= 0.0:
        return 0.0
    v = 0.5 * (1.0 - math.cos(FOLDS * th + twist))
    return -amp * v ** 0.7 * (1.0 + 0.22 * math.cos(3.0 * th + 0.6))


def _back(th, keep, fade):
    """0 within `keep` degrees of the back and 1 beyond `fade`.

    The back carries the filler neck on the base and the fan's frame on the torso, and both are
    let into the wall at a radius taken from shell_r, so both want their patch left alone.
    """
    a = 180.0 - abs(math.degrees(wrap(th)))
    return max(0.0, min(1.0, (a - keep) / (fade - keep)))




def _lump(name, profile, z0, z1, swell=None):
    """The section's skin as a closed solid, carried past both cut planes and capped on the axis.

    Closed is the point: the remesh that unions the buckle and the hood in would turn an open
    sheet into a thin slab. `cut_z` opens it again once the union is done.
    """
    below, above = z0 - 8.0, z1 + 8.0
    rows = ([(0.0, below), (P.shell_r(profile, z0), below)]
            + sampled(profile, STEP)
            + [(P.shell_r(profile, z1), above), (0.0, above)])
    return revolve(name, rows, segments=SEG, swell=swell)


# --- base ---------------------------------------------------------------------------------
HEM_Z = max(P.BASE_PROFILE, key=lambda rz: rz[0])[1]     # 90: the skirt's widest band is its hem
HEM_SCALLOP = 4.0                                        # how far the hem swings with the folds
Z_FLANGE = P.Z_BELT - 2 * P.RING_T                       # 214: the belt flange's lower edge
R_BASE = 115.0                                           # nominal radius, for arc lengths

# The coat reaches the ground at the sides and the back and is lifted at the front, over the
# boots. That is the one shape this base can hold: the raised floor's rim is at BASE_FLOOR_R
# and the wall has to stay outside it, so a skirt drawn in all the way round would leave a
# ring of a plinth at the ankles whatever else was done. Lifted at the front only, that ring is
# a notch between two boots, and everywhere else there is nothing to hide - just coat.
#
# The well under the lifted hem. The hem itself cannot flare, the profile being already within
# three millimetres of the bed, so it is the well that makes the hem a lip. Its climb back out
# is forty degrees off vertical, and the hem's own edge, the last five millimetres, bridges.
_WELL = [(0.0, 0.0), (14.0, -1.0), (30.0, -4.5), (46.0, -13.0),
         (62.0, -17.0),                  # the waist between the boots, deepest in the hem's shadow
         (74.0, -13.0), (82.0, -7.5),
         (HEM_Z - 3.0, -4.5),            # the cloth's edge, five millimetres of it
         (HEM_Z - 1.0, 0.0)]
HEM_LIFT = (40.0, 58.0)                  # full lift within the first, none beyond the second
# How close to the axis the skin may come. The floor's rim needs a wall's clearance; under it
# there are the floor's own skirt and the annulus that closes on the bottom rim; above it the
# canister's corners at a radius of 100; and near the top of the wet zone the pump's two
# towers, which are the widest thing in the base and reach up to PUMP_Z0. A fold's crease is
# ten millimetres deep and the towers stand two millimetres inside the floor, so without this
# the two would meet around 145.
_TOWER_R = math.hypot(*[c + P.PUMP_LEG / 2 for c in P.PUMP_LEG_XY])     # 105.6, the widest thing inside
_FLOOR_KEEP = [(0.0, 106.0), (18.0, 106.0), (21.0, P.BASE_FLOOR_R + P.WALL + 1.0),
               (27.0, P.BASE_FLOOR_R + P.WALL + 1.0), (33.0, 103.0), (118.0, 103.0),
               (126.0, _TOWER_R + P.WALL + 0.5), (P.PUMP_Z0 + 5.0, _TOWER_R + P.WALL + 0.5), (162.0, 0.0)]
_RIM = [(P.Z_BASE_TOP - 20.0, 0.0), (P.Z_BASE_TOP - 12.0, 1.0)]     # where the torso shingles over
_SKIRT_FOLDS = [(0.0, 6.5), (16.0, 6.5), (24.0, 3.6), (34.0, 5.0), (46.0, 8.0), (80.0, 10.0),
                (HEM_Z + 5.0, 11.0), (120.0, 11.0), (145.0, 8.0), (162.0, 5.5), (180.0, 0.0)]
# The belt: a groove all round below the flange's lower edge, so the band between it and the
# torso's skirt stands out as the belt without anything being added to a wall a ring is let into.
_BELT = [(Z_FLANGE - 36.0, 0.0), (Z_FLANGE - 28.0, -3.5), (Z_FLANGE - 15.0, -3.5), (Z_FLANGE - 9.0, 0.0)]
# The boots fill the lifted part of the skirt, from the ground up to under the hem's own edge,
# and they are barely proud of the profile: what shows them is not how far they stand out but
# how far the well is cut away beside them and in the notch between them. A boot that stopped
# short of the hem would leave a cave under the cloth, which is what the eye reads first.
_BOOT = [(0.0, 2.6), (6.0, 3.0),
         (8.5, 0.8), (10.5, 1.0),                        # the sole's line, a groove round the toe
         (14.0, 4.0), (26.0, 3.6), (44.0, 2.0), (62.0, 0.0), (78.0, -3.0), (HEM_Z - 3.0, -4.5)]
BOOT_DEG, BOOT_HALF = 26.0, 42.0                         # 5 to 47 degrees either side of the front
# Three creases cut round the boots - one down the notch between them, one outside each - so
# there is a line where a boot ends and cloth begins. They are shallow on purpose: the stakes
# pass through the floor at STAKE_HOLE_R and their bosses want the wall left where it is.
_BOOT_CREASE = [(0.0, 14.0, 3.5), (48.0, 12.0, 4.0), (-48.0, 12.0, 4.0)]


def _boot_mask(th):
    """1 down the middle of either boot, 0 off the sides of both and in the notch between them."""
    u = min(abs(arc(th, BOOT_DEG, R_BASE)), abs(arc(th, -BOOT_DEG, R_BASE)))
    return (1.0 - (u / BOOT_HALF) ** 2) ** 1.2 if u < BOOT_HALF else 0.0


def _base_dr(th, z):
    """The base's skin as an offset from BASE_PROFILE: the well, the boots, the belt, the folds.

    The well is read at a height that swings with the folds, which scallops the hem - the cloth
    hangs lowest where a fold's crest runs down into it. It is the cheapest four millimetres in
    the model: nothing else says cloth so plainly at three metres.

    Where a boot stands, the folds give way to it: leather has no folds, and a crease running
    over a toe cap would undo the one place the eye is asked to read a foot.
    """
    prof = P.shell_r(P.BASE_PROFILE, z)
    a = abs(math.degrees(wrap(th)))
    lift = max(0.0, min(1.0, (HEM_LIFT[1] - a) / (HEM_LIFT[1] - HEM_LIFT[0])))
    well = lerp(z + HEM_SCALLOP * math.cos(FOLDS * th), _WELL) * lift
    g = _boot_mask(th)
    boot = max(0.0, lerp(z, _BOOT) - well) * g
    amp = lerp(z, _SKIRT_FOLDS) * _back(th, 10.0, 26.0) * (1.0 - g * min(1.0, boot / 6.0))
    d = well + lerp(z, _BELT) + _folds(th, amp, math.radians(6.0 * (z - HEM_Z) / 110.0))
    # The last twenty millimetres of the rim carry no felt. The torso's skirt shingles over them
    # with CLEAR_SHELL of air, and an outward-only displacement spends exactly that, so the skin
    # is pulled in by the noise's own strength first and the rim comes out on the profile.
    d -= NOISE * lerp(z, _RIM)
    for deg, ru, depth in _BOOT_CREASE:
        d -= dome(arc(th, deg, R_BASE), z - 62.0, ru, 28.0, depth)
    d = smax(d, lerp(z, _FLOOR_KEEP) - prof)           # clear of the raised floor and its skirt
    return d + boot


def base():
    z0, z1 = P.SECTION_Z["base"]
    profile = P.BASE_PROFILE
    parts = [_lump("base", profile, z0, z1, _base_dr)]
    # The buckle: four bars around a hole, on the belt band and clear of the four angles the
    # flange behind it screws at. It is local, so the flange still meets the wall either side.
    for name, y, z, radii in (("buckle_t", 0.0, 227.0, (6.5, 27.0, 2.6)),
                              ("buckle_b", 0.0, 209.0, (6.5, 27.0, 2.6)),
                              ("buckle_l", 25.0, 218.0, (6.5, 2.6, 9.4)),
                              ("buckle_r", -25.0, 218.0, (6.5, 2.6, 9.4))):
        parts.append(ellipsoid(name, radii, skin_point(profile, z, y, sink=1.0)))
    ob = join_remesh("base", parts, voxel=VOXEL)
    finish(ob, displace=NOISE, noise_scale=NOISE_SCALE, solidify=False)
    cut_z(ob, z0=z0, z1=z1)
    add_floor(ob, P.BASE_FLOOR_R, P.Z_FLOOR)
    finish(ob)
    export_raw(ob, "base")


# --- torso --------------------------------------------------------------------------------
Z_WIN = P.Z_LENS + P.WINDOW_Z_BIAS                       # the window's centre, 275
Z_WIN_TOP = Z_WIN + P.WINDOW_H / 2                       # and its top edge, 299
Y_PLACKET = -24.0                                        # the coat closes clear of the camera
R_TORSO = 100.0
DEG_PLACKET = -13.5                                      # where Y_PLACKET lands on the belly
# Nothing all the way round may stand proud below 250 or above 384. What the torso adds to the
# belt is the shingle step the profile already has at Z_BELT.
_TUCK = [(P.Z_BASE_TOP + 10.0, 0.0), (272.0, 1.0), (360.0, 1.0), (384.0, 0.0)]
_BACK_FOLDS = [(262.0, 0.0), (285.0, 1.0), (350.0, 1.0), (380.0, 0.0)]
_CHEST = [(Z_WIN_TOP + 7.0, 0.0), (320.0, 1.0), (344.0, 1.0), (360.0, 0.0)]
TUCK_D, FOLD_D, CHEST_D = 4.0, 4.0, 3.5
# The sleeve, shoulder to mitten: (angle from +X, z, half width in arc, how far it stands out).
# It has to pass between the hood below it and the beard collar's hem above, and there is just
# room for a pair of arms folded over the belly with the mittens either side of the window.
_ARM = [(76.0, 334.0, 13.0, 4.0), (57.0, 327.0, 12.0, 5.0), (40.0, 318.0, 16.0, 7.0)]
_BUTTONS = (264.0, 288.0, 312.0)


def _front(th):
    """1 on the centre line, 0 three degrees inside the hatch panel's edge.

    Everything the coat's front carries has to die out before HATCH_HALF_ANGLE: that is where
    the panel's lip is let into the wall, and a lip cannot bite a wall that has moved.
    """
    a = abs(math.degrees(th)) * 90.0 / (P.HATCH_HALF_ANGLE - 3.0)
    return math.cos(math.radians(a)) if a < 90.0 else 0.0


def _flank(th):
    """0 across the coat's front and across the fan's patch at the back, 1 on the flanks."""
    a = abs(math.degrees(th))
    return max(0.0, min(1.0, (a - 30.0) / 25.0, (180.0 - a - 30.0) / 25.0))


def _torso_feat(th, z):
    """What the coat wears: two sleeves, the placket and its buttons. Nothing else is proud.

    Kept apart from the cloth so the window's rule can be checked against it on its own.
    """
    th = wrap(th)
    d = ridge(arc(th, DEG_PLACKET, R_TORSO), z,
               [(0.0, 252.0, 13.0, 0.0), (0.0, 262.0, 13.0, 3.0),
                (0.0, 314.0, 13.0, 3.0), (0.0, 324.0, 13.0, 0.0)], sharp=2.0)
    for zb in _BUTTONS:
        d = max(d, dome(arc(th, DEG_PLACKET, R_TORSO), z - zb, 9.0, 9.0, 6.0))
    for s in (1, -1):
        d = max(d, ridge(arc(th, 0.0, R_TORSO), z,
                          [(s * math.radians(deg) * R_TORSO, zv, w, h) for deg, zv, w, h in _ARM]))
    return d


def _torso_dr(th, z):
    """The torso's skin as an offset from TORSO_PROFILE.

    The belly is fuller in front than behind because the flanks are tucked in, not because the
    front is pushed out: in front of the hatch the profile is the pane's datum and has to be
    left where it is, all the way up to the window's margin. Above that margin the chest does
    swell, and the sides carry the coat's folds, which stop short of the fan's patch.
    """
    th = wrap(th)
    s4 = math.sin(th) ** 4                        # 0 on the centre line, 0 at the back
    d = -TUCK_D * s4 * lerp(z, _TUCK)
    d += _folds(th, FOLD_D * _flank(th) * lerp(z, _BACK_FOLDS))
    d += CHEST_D * _front(th) * lerp(z, _CHEST)
    return d + _torso_feat(th, z)


def torso():
    z0, z1 = P.SECTION_Z["torso"]
    profile = P.TORSO_PROFILE
    parts = [_lump("torso", profile, z0, z1, _torso_dr)]
    # The hood: a brow over the window, pitched down HOOD_PITCH_DEG. A joined solid and not a
    # swell, because what shades the glass is its hard lower edge, which a relief cannot have.
    parts.append(ellipsoid("hood", (16.0, 23.0, 11.0),
                           skin_point(profile, Z_WIN_TOP + 17.0, P.CAM_Y, sink=8.0),
                           rot=(0.0, P.HOOD_PITCH_DEG, 0.0)))
    ob = join_remesh("torso", parts, voxel=VOXEL)
    finish(ob, displace=NOISE, noise_scale=NOISE_SCALE, solidify=False)
    cut_z(ob, z0=z0, z1=z1)
    finish(ob)
    export_raw(ob, "torso")


if __name__ == "__main__":
    fresh_scene()
    base()
    fresh_scene()
    torso()
