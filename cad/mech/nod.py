"""The nod drive: the stem the head stands on, the spider it is screwed to, and the bought parts
between them and the yoke - the nod servo, its horn, the pin, the bushing, the stop lug, the
nozzle and the tube.

Everything here is drawn at rest, pan 0 and nod 0, where it sits. `posed()` in mech.common moves
it; `mech.PANS` and `mech.NODS` say what moves how. Coordinates in comments are (x, z) in the
plane of the nod, y = 0, unless they say otherwise; "above C" means z - Z_NOD.

The stem is a blade 12 thick between the cheeks. Its hub is on the pin at C; its neck rises
through the plate's hub, the bearing, the deck and the plate, leaning back STEM_LEAN at rest so
that over NOD_RANGE it swings -10..+10 degrees from vertical and its sweep sits centred in the
bearing's bore; its head carries the spider inside the dome's bore. It prints flat on its side,
-Y face down: the tube's channel then lies horizontal in the print and bridges 7 mm.

The spider is the old neck shroud's top without the shroud: a hub on the stem's head and four
arms to the same four radial inserts at z 440, 60/120/240/300 degrees, boss faces at r 57, so the
head's four countersunk M3 from outside still apply. The arms are shaped by the coat's dome: the
unit is kept NECK_SPHERE_R from C wherever it faces the coat, and inside SPIDER_CORE_R the spider
stays in the dome's bore at every nod instead, so outside that radius the arms' undersides are
the sphere.
"""
import math
from functools import lru_cache
from build123d import Axis, Location, Plane, Polygon, Pos, extrude
import params as P
from mech import part
from mech.common import (ball, box, cyl_x, cyl_y, cyl_z, insert_holes, polar, polyline, servo_body)

C = (0.0, 0.0, P.Z_NOD)
HALF_T = P.STEM_T / 2
NECK_TOP = P.STEM_HEAD[1]                     # 420: where the neck meets the head block
LEAN = math.radians(P.STEM_LEAN)              # back, towards -x
SAFE_R = P.NECK_SPHERE_R + 0.5                # how far from C the unit's side of the parting keeps


def xz_prism(points, y0, y1):
    """A polygon given in the plane of the nod as (x, z) points, extruded from y0 to y1."""
    f = Plane.XZ * Polygon(*points)              # Plane.XZ: local x = x, local y = z
    return Pos(0, y0, 0) * extrude(f, amount=y1 - y0, dir=(0, 1, 0))   # whichever way it winds


def xz_wedge(a0, a1, r, y0, y1, n=24):
    """The sector between angles a0 and a1 (degrees, atan2(z - Z_NOD, x)) about C, out to r."""
    pts = [(0.0, P.Z_NOD)] + [(r * math.cos(math.radians(a)), P.Z_NOD + r * math.sin(math.radians(a)))
                              for a in (a0 + (a1 - a0) * i / n for i in range(n + 1))]
    return xz_prism(pts, y0, y1)


def neck_angle(nod):
    """The neck's angle from vertical, positive leaning forward (+x), at a nod (nose up +)."""
    return -P.STEM_LEAN - nod


def neck_x_range(z, lo=P.NOD_STOP[0], hi=P.NOD_STOP[1], clear=0.0, steps=88):
    """The x the neck covers at height z over every nod from lo to hi, grown by `clear`.

    The neck is a strip STEM_W wide through C, so at height h above C and angle phi it spans
    h tan(phi) +- (STEM_W / 2 + clear) / cos(phi); the union over the nods is one interval.
    """
    h = z - P.Z_NOD
    xs = []
    for i in range(steps + 1):
        phi = math.radians(neck_angle(lo + (hi - lo) * i / steps))
        half = (P.STEM_W / 2 + clear) / math.cos(phi)
        xs += [h * math.tan(phi) - half, h * math.tan(phi) + half]
    return min(xs), max(xs)


def neck_slot(z0, z1, clear=P.NOD_CLEAR, y=HALF_T + 0.4):
    """The slot through the plate and its hub the neck swings in: its sweep over the hard stops,
    NOD_CLEAR wider all round, |y| <= y."""
    zs = [z0 + (z1 - z0) * i / 40 for i in range(41)]
    hi = [(neck_x_range(z, clear=clear)[1], z) for z in zs]
    lo = [(neck_x_range(z, clear=clear)[0], z) for z in reversed(zs)]
    return xz_prism(hi + lo, -y, y)


# --- the tube ------------------------------------------------------------------------------
# The 6 mm PU tube's centreline, in three parts. It stands up out of the spider on the axis - the
# stab - runs down the stem's channel and leaves it through the neck's back face, hangs behind the
# stem's hub, and loops down under the yoke to the pan axis, where it twists with the pan on its
# way down to the valve. The first part moves with the stem, the last with the plate only, and
# the loop between them bends through the nod.
CHANNEL_KINK_Z = 392.0                         # the channel runs down the neck to here ...
CHANNEL_EXIT_DEG = 8.0                         # ... and then out through its back at this from vertical


def _neck_x(z):
    return -(z - P.Z_NOD) * math.tan(LEAN)


def tube_stem_points():
    """The tube where it moves with the stem, as corners: the stab, the stem's head, the channel's
    kink, and where it leaves the neck's back."""
    k = (_neck_x(CHANNEL_KINK_Z), 0.0, CHANNEL_KINK_Z)
    t = math.tan(math.radians(CHANNEL_EXIT_DEG))
    exit_ = (k[0] - (CHANNEL_KINK_Z - TUBE_EXIT_Z) * t, 0.0, TUBE_EXIT_Z)
    return [(0.0, 0.0, P.STAB_TOP), (0.0, 0.0, P.STEM_HEAD[2]), k, exit_]


TUBE_EXIT_Z = 362.0                          # where the channel leaves the neck: near C, so the nod moves
                                             # the tube's end there as little as it can - 5.4 mm of chord
TUBE_CLIP = (-21.0, 0.0, 313.0, 305.0)       # the tube clip, screwed to the -Y cheek: x, y, top, bottom.
                                             # It pans with the plate and holds the tube vertical; below it
                                             # the tube runs free down the board deck's back edge to the
                                             # valve's gland and takes the pan's twist over that length.

TUBE_LOOP = 58.0                             # the free length from the stem's channel to the clip. The
                                             # loop takes the nod: at -18 it is nearly taut, at +8 it bows
                                             # 8 mm more, and its tightest bend at any nod is 23 or more
CLIP_LUG = (-19.0, -12.0, -12.5, -6.5, 328.0, 345.0)    # the lug on the -Y cheek the clip screws to
CLIP_SCREW = (-15.5, 333.0)                             # (x, z) of its M3, along Y into the lug


def _fillet(points, r, n=10):
    """A polyline with every inner corner replaced by an arc of radius r, as dense points."""
    import numpy as np
    pts = [np.array(p, float) for p in points]
    out = [pts[0]]
    for a, b, c in zip(pts, pts[1:], pts[2:]):
        u, v = (a - b) / np.linalg.norm(a - b), (c - b) / np.linalg.norm(c - b)
        ang = math.acos(max(-1.0, min(1.0, float(u @ v))))
        if abs(math.pi - ang) < 1e-6:
            out.append(b)
            continue
        d = r / math.tan(ang / 2)
        d = min(d, 0.49 * np.linalg.norm(a - b), 0.49 * np.linalg.norm(c - b))
        p0, p1 = b + u * d, b + v * d
        for i in range(n + 1):               # a quadratic Bezier through the corner: a fair arc
            t = i / n
            out.append((1 - t) ** 2 * p0 + 2 * (1 - t) * t * b + t ** 2 * p1)
    out.append(pts[-1])
    return [tuple(map(float, p)) for p in out]


def _hermite(p0, d0, p1, d1, t, n=40):
    import numpy as np
    p0, d0, p1, d1 = (np.array(x, float) for x in (p0, d0, p1, d1))
    out = []
    for i in range(n + 1):
        s = i / n
        h00, h10, h01, h11 = 2 * s ** 3 - 3 * s ** 2 + 1, s ** 3 - 2 * s ** 2 + s, -2 * s ** 3 + 3 * s ** 2, s ** 3 - s ** 2
        out.append(h00 * p0 + h10 * t * d0 + h01 * p1 + h11 * t * d1)
    return out


def _length(pts):
    return sum(math.dist(a, b) for a, b in zip(pts, pts[1:]))


@lru_cache(maxsize=None)
def tube_loop(nod):
    """The free loop from the stem's channel to the clip, in the plate's frame, at a nod.

    A quartic Bezier: it leaves the channel along it, enters the clip straight down, and between
    them bows away from the hub. Its three free numbers - how far each end runs straight, and how
    far the bow stands off the chord - are chosen at each nod for the gentlest bend that makes it
    exactly TUBE_LOOP long, because the tube's length does not change: that is what a loop is.
    """
    import numpy as np
    from mech.common import pose_point
    k, e = tube_stem_points()[2:4]
    e_p = np.array(pose_point(e, 0.0, nod))
    k_p = np.array(pose_point(k, 0.0, nod))
    d0 = (e_p - k_p) / np.linalg.norm(e_p - k_p)
    top = np.array((TUBE_CLIP[0], TUBE_CLIP[1], TUBE_CLIP[2]))
    along = (top - e_p) / np.linalg.norm(top - e_p)
    away = np.cross(along, (0.0, 1.0, 0.0))
    if away @ ((e_p + top) / 2 - np.array((0.0, 0.0, P.Z_NOD))) < 0:
        away = -away

    def curve(x):
        # a quartic Bezier: its end tangents are the channel's and the clip's whatever the bow
        a, b, c = x
        t = np.linspace(0.0, 1.0, 121)[:, None]
        p1, p3 = e_p + a * d0, top + np.array((0.0, 0.0, b))
        p2 = (e_p + top) / 2 + c * away
        return ((1 - t) ** 4 * e_p + 4 * (1 - t) ** 3 * t * p1 + 6 * (1 - t) ** 2 * t ** 2 * p2
                + 4 * (1 - t) * t ** 3 * p3 + t ** 4 * top)

    def fit(a, b):
        """The bow that makes the curve TUBE_LOOP long with these end runs, or None."""
        if _length(curve((a, b, 0.0))) > TUBE_LOOP:
            return None
        lo, hi = 0.0, 80.0
        for _ in range(40):
            c = (lo + hi) / 2
            lo, hi = (c, hi) if _length(curve((a, b, c))) < TUBE_LOOP else (lo, c)
        return lo
    best = None
    for a in np.arange(0.0, 41.0, 2.5):
        for b in np.arange(0.0, 41.0, 2.5):
            c = fit(a, b)
            if c is None:
                continue
            r = _min_radius(curve((a, b, c)))
            if best is None or r > best[0]:
                best = (r, (a, b, c))
    return [tuple(map(float, p)) for p in curve(best[1])]


def _min_radius(pts):
    import numpy as np
    pts = np.asarray(pts, float)
    a, b, c = pts[:-2], pts[1:-1], pts[2:]
    ab, bc = np.linalg.norm(b - a, axis=1), np.linalg.norm(c - b, axis=1)
    ca = np.linalg.norm(a - c, axis=1)
    area = np.linalg.norm(np.cross(b - a, c - a), axis=1) / 2
    ok = (area > 1e-9) & (np.minimum(ab, bc) > 0.2)
    return float((ab * bc * ca / (4 * np.maximum(area, 1e-12)))[ok].min()) if ok.any() else math.inf


def tube_points(pan=0.0, nod=0.0):
    """The tube's centreline at a pose, dense: the stem's part filleted at TUBE_BEND_R and posed
    with the stem, the free loop, the clip and a stub under it, all panned with the plate."""
    from mech.common import pose_point
    fixed = _fillet(tube_stem_points(), P.TUBE_BEND_R + 2.0)     # a Bezier fillet is tighter mid-arc
    stem = [pose_point(p, 0.0, nod) for p in fixed]
    loop = tube_loop(nod)
    n = int(TUBE_CLIP[2] - TUBE_CLIP[3])
    tail = [(TUBE_CLIP[0], TUBE_CLIP[1], TUBE_CLIP[2] - i) for i in range(1, n + 1)]
    pts = stem[:-1] + loop + tail
    return [pose_point(p, pan, 0.0, nods=False) for p in pts]


def tube_bend_radii(nod):
    """The least radius of curvature along the tube at a nod, from its dense centreline."""
    return _min_radius(tube_points(0.0, nod))


def tube_route(pan=0.0, nod=0.0, r=None):
    """The tube at a pose, as a mesh (trimesh): its dense centreline swept as a chain of cylinders
    with a ball at every joint, united in manifold3d. A build123d solid of two hundred cylinders
    takes minutes; this takes a fraction of a second."""
    return tube_mesh(tube_points(pan, nod), P.TUBE_OD / 2 if r is None else r)


def tube_mesh(points, r, step=1.5, sections=20):
    import manifold3d as mf
    import numpy as np
    import trimesh
    pts = [np.array(points[0], float)]
    for p in points[1:]:                             # thin the dense points to about `step` apart
        p = np.array(p, float)
        if np.linalg.norm(p - pts[-1]) >= step or p is points[-1]:
            pts.append(p)
    if np.linalg.norm(np.array(points[-1]) - pts[-1]) > 1e-6:
        pts.append(np.array(points[-1], float))
    parts = []
    for a, b in zip(pts, pts[1:]):
        d = b - a
        h = float(np.linalg.norm(d))
        if h < 1e-6:
            continue
        z = d / h
        x = np.cross(z, (1.0, 0.0, 0.0) if abs(z[0]) < 0.9 else (0.0, 1.0, 0.0))
        x /= np.linalg.norm(x)
        y = np.cross(z, x)
        m = np.column_stack([x, y, z, a])
        parts.append(mf.Manifold.cylinder(h, r, r, sections).transform(m.tolist()))
    for p in pts[1:-1]:
        parts.append(mf.Manifold.sphere(r, sections).translate(tuple(map(float, p))))
    out = mf.Manifold.batch_boolean(parts, mf.OpType.Add).to_mesh()
    return trimesh.Trimesh(vertices=np.asarray(out.vert_properties)[:, :3], faces=np.asarray(out.tri_verts))


# --- the stem --------------------------------------------------------------------------------
PIN_BORE = P.PIN_D - 0.1                      # the dowel is pressed into the hub (and set-screwed)
HORN_Y = P.NOD_SERVO_FACE_Y - P.SPLINE_BOSS[1] - P.HORN_T    # 6.3: the horn's near face, in the cup
DRIVE_ANGLES = (45.0, 225.0)                  # two of the horn's four holes carry drive pins ...
DRIVE_SLOT = (3.4, 4.5, 9.5, 3.0)             # ... into two radial slots in the hub's face: width,
                                              # r from, r to, depth. An Oldham-style drive: torque
                                              # passes, a millimetre of misalignment between the
                                              # servo's shaft and the collar's bore does not
SPIDER_SCREW_X = 9.0                          # the spider's two screws into the stem's head
SET_SCREW_Y = -2.5                            # the pin's M2 set screw, from behind


def _neck(inset=0.0):
    """The neck as a strip in the plane of the nod, from C up to NECK_TOP, leaning back."""
    h = NECK_TOP - P.Z_NOD
    top = -h * math.tan(LEAN)
    w = (P.STEM_W / 2 - inset) / math.cos(LEAN)
    return [(-w, P.Z_NOD), (w, P.Z_NOD), (top + w, NECK_TOP), (top - w, NECK_TOP)]


@part("stem")
def stem():
    """The blade the head stands on: its hub on the pin at C, driven by the nod servo's horn let
    into its +Y face, and its head under the spider. The tube runs down inside it.

    Drawn at rest; it prints flat on its side, -Y face down.
    """
    x0 = P.Z_NOD
    s = cyl_y(P.STEM_HUB_R, -HALF_T, HALF_T, 0.0, x0)
    s = s + xz_prism(_neck(), -HALF_T, HALF_T)
    hw, z0, z1 = P.STEM_HEAD
    s = s + box(-hw, hw, -HALF_T, HALF_T, z0, z1)
    # the tube's channel, round at its bend so the tube is never kinked
    pts = tube_stem_points()
    s = s - polyline([(0.0, 0.0, z1 + 1.0)] + pts[2:4] + [(pts[3][0] - 8.0, 0.0, pts[3][2] - 17.0)],
                     P.STEM_CHANNEL_D / 2)
    # the collar on the +Y face: a cup the round horn sits in, its outside the stem's second journal
    ci, co = P.HUB_COLLAR
    s = s + (cyl_y(co, HALF_T - 0.01, P.NOD_SERVO_FACE_Y - 0.5, 0.0, x0)
             - cyl_y(ci, HALF_T, P.NOD_SERVO_FACE_Y, 0.0, x0))
    # two radial slots in the hub's face the horn's drive pins run in
    w, r0, r1, depth = DRIVE_SLOT
    for a in DRIVE_ANGLES:
        slot = box(r0, r1, HALF_T - depth, HALF_T + 0.01, -w / 2, w / 2)
        s = s - slot.rotate(Axis.Y, -a).moved(Location((0.0, 0.0, x0)))
    # the pin, pressed in from the -Y face and held by an M2 set screw on its flat from behind:
    # in front the plate's column stands in a driver's way
    s = s - cyl_y(PIN_BORE / 2, -HALF_T - 1.0, 2.5, 0.0, x0)
    s = s - cyl_x(1.6 / 2, -P.STEM_HUB_R - 1.0, -1.0, SET_SCREW_Y, x0)
    # the stop lug: an M3 insert in the -Y face, below C, for the screw and sleeve that run in the
    # cheek's arc slot
    s = s - cyl_y(P.INSERT_D / 2, -HALF_T - 0.01, -HALF_T + P.INSERT_DEPTH, 0.0, x0 - P.STOP_LUG_R)
    # two inserts in the head's top for the spider's screws
    s = insert_holes(s, [(x, 0.0, z1) for x in (-SPIDER_SCREW_X, SPIDER_SCREW_X)])
    # the -Y face prints on the bed and spreads there (the elephant's foot): its first STEM_CHAMFER
    # of height is stepped in by as much all round, so the spread stays inside the blade's width
    c = P.STEM_CHAMFER
    y0, y1 = -HALF_T - 1.0, -HALF_T + c
    keep = (cyl_y(P.STEM_HUB_R - c, y0, y1, 0.0, x0)
            + xz_prism(_neck(inset=c), y0, y1)
            + box(-hw + c, hw - c, y0, y1, z0 + c, z1 - c))
    return s - (box(-60, 60, y0, y1, x0 - 30, z1 + 5) - keep)


# --- the spider -------------------------------------------------------------------------------
BOSS_D = P.INSERT_D + 5.0                     # 9: round a radial insert
ARM_W = 10.0
ARM_Z0 = 434.0
SPIDER_CB_Z = 440.0                           # the spider screws' heads sit here, sunk
CLAMP_Z = 441.0                               # an M3 across the tube's bore holds it against the water


def spider_safe():
    """What the spider may not enter: the ball SAFE_R about C, except near the axis."""
    return ball(SAFE_R) - cyl_z(P.SPIDER_CORE_R, P.Z_NOD - 120, P.Z_NOD + 120)


@part("spider")
def spider():
    """Bolted to the stem's head; carries the turning unit on four radial inserts.

    Two M3 x 12 go down through it into the stem's head, driven from above before the unit goes
    on. The tube comes up through its middle and stands out of its top as the stab the head's
    socket slides onto, clamped by a third M3 from the side so the water cannot push it down.
    Prints top face down: the hub's and the arms' tops are one plane, and what hangs is the four
    bosses' undersides and the sphere under the arms - 344 mm2 measured, against 1 933 hub down.
    """
    z0, z1 = P.SPIDER_Z
    s = cyl_z(P.SPIDER_HUB_R, z0, z1)
    for a in P.HEAD_SCREW_ANGLES:
        arm = box(P.SPIDER_HUB_R - 5.0, P.SPIDER_BOSS_R - 6.0, -ARM_W / 2, ARM_W / 2, ARM_Z0, z1)
        boss = cyl_x(BOSS_D / 2, P.SPIDER_BOSS_R - 9.0, P.SPIDER_BOSS_R, 0.0, P.HEAD_SCREWS_Z)
        s = s + (arm + boss).rotate(Axis.Z, a)
    s = s - spider_safe()
    for a in P.HEAD_SCREW_ANGLES:                                   # the head's four inserts
        bore = cyl_x(P.INSERT_D / 2, P.SPIDER_BOSS_R - P.INSERT_DEPTH, P.SPIDER_BOSS_R + 1.0,
                     0.0, P.HEAD_SCREWS_Z)
        s = s - bore.rotate(Axis.Z, a)
    hw, _, top = P.STEM_HEAD                                        # the stem's head fits up into it
    s = s - box(-hw - 0.3, hw + 0.3, -HALF_T - 0.3, HALF_T + 0.3, z0 - 1.0, top)
    for x in (-SPIDER_SCREW_X, SPIDER_SCREW_X):                     # down into the stem's head
        s = s - cyl_z(P.M3_CLEAR / 2, top - 1.0, z1 + 1.0, x, 0.0)
        s = s - cyl_z(6.5 / 2, SPIDER_CB_Z, z1 + 1.0, x, 0.0)
    s = s - cyl_z(P.STEM_CHANNEL_D / 2, z0 - 1.0, z1 + 1.0)         # the tube
    s = s - cyl_y(P.INSERT_D / 2, P.SPIDER_HUB_R - P.INSERT_DEPTH, P.SPIDER_HUB_R + 1.0, 0.0, CLAMP_Z)
    return s - cyl_y(P.M3_CLEAR / 2, 0.0, P.SPIDER_HUB_R, 0.0, CLAMP_Z)


@part("tube_clip")
def tube_clip():
    """Holds the tube vertical under the yoke, where the loop from the stem ends; pans with the plate.

    A ring the tube snaps into from behind, an arm up to a plate on the -Y cheek's lug, one M3 into an
    insert in the lug. It is its own part because the ring stands 25.5 out from the pan axis and the
    plate and yoke have to drop through the bearing's 50 mm bore; it goes on after them, on the bench,
    driven along +Y from the -Y side. Prints on its plate's outer face.
    """
    x, y, top, bottom = TUBE_CLIP
    x0, x1, y0, y1, z0, z1 = CLIP_LUG
    ring = cyl_z(P.TUBE_OD / 2 + 2.3, bottom, top, x, y)
    arm = box(x - 3.0, x0 - 0.5, y0 - 3.0, y - 3.0, bottom, z0 + 4.0)       # beside the lug, not in it
    plate = box(x0 - 1.0, x1, y0 - 3.0, y0, z0, z0 + 10.0)
    c = ring + arm + plate
    c = c - cyl_z(P.TUBE_OD / 2 + 0.3, bottom - 1, top + 1, x, y)
    c = c - box(x - 20.0, x, y - 2.6, y + 2.6, bottom - 1, top + 1)          # the tube snaps in here
    sx, sz = CLIP_SCREW
    c = c - cyl_y(P.M3_CLEAR / 2, y0 - 5.0, y0 + 1.0, sx, sz)
    return c


# --- bought parts, as envelopes ------------------------------------------------------------------
def nod_servo():
    """The MG996R's case and tabs: shaft on the Y axis at C pointing -Y, case out to +Y, upright."""
    spec = P.MG996R
    L, W, H = spec["body"]
    body = servo_body(spec, (0.0, P.NOD_SERVO_FACE_Y, P.Z_NOD), axis="-y")
    y_tab = P.NOD_SERVO_FACE_Y + H - spec["tab_z"]
    z_lo = P.Z_NOD - spec["shaft_off"] - (spec["tab_span"] - L) / 2
    tabs = box(-W / 2, W / 2, y_tab, y_tab + spec["tab_t"], z_lo, z_lo + spec["tab_span"])
    boss = cyl_y(P.SPLINE_BOSS[0] / 2, P.NOD_SERVO_FACE_Y - P.SPLINE_BOSS[1], P.NOD_SERVO_FACE_Y,
                 0.0, P.Z_NOD)
    return body + tabs + boss


def nod_servo_tab_y():
    """The tabs' face towards the yoke: the servo's posts end here."""
    return P.NOD_SERVO_FACE_Y + P.MG996R["body"][2] - P.MG996R["tab_z"]


def nod_servo_holes():
    """The four tab screws, (x, z), into inserts in the posts."""
    spec = P.MG996R
    zc = P.Z_NOD - spec["shaft_off"] + spec["body"][0] / 2
    along, across = spec["holes"]
    return [(dx, zc + dz) for dz in (-along / 2, along / 2) for dx in (-across / 2, across / 2)]


def horn():
    """The round horn on the servo's spline, in the collar's cup, and its two drive pins - M2.5
    screws through it standing 3 mm out into the hub's slots; it nods with the stem."""
    h = cyl_y(P.HORN_D / 2, HORN_Y, HORN_Y + P.HORN_T, 0.0, P.Z_NOD)
    for a in DRIVE_ANGLES:
        x, z = polar(P.HORN_SCREW_R, a)
        h = h + cyl_y(1.25, HORN_Y - 3.0, HORN_Y + 0.01, x, P.Z_NOD + z)
    return h


def pin():
    """The dowel: from the -Y cheek's outer face into the stem's hub."""
    y0 = -P.CHEEK_Y[1]
    return cyl_y(P.PIN_D / 2, y0, y0 + P.PIN_L, 0.0, P.Z_NOD)


def bushing():
    y0, y1 = -P.CHEEK_Y[1], -P.CHEEK_Y[0]
    return cyl_y(P.BUSH_OD / 2, y0, y1, 0.0, P.Z_NOD) - cyl_y(P.PIN_D / 2, y0 - 1, y1 + 1, 0.0, P.Z_NOD)


LUG_SLEEVE_Y = (-P.CHEEK_Y[1] - 0.2, -HALF_T)  # the sleeve, hub face to just past the cheek
LUG_HEAD = (5.5, 3.0)


def stop_lug():
    """The stop lug: a sleeve on an M3 screw into the stem's hub, and the screw's head."""
    z = P.Z_NOD - P.STOP_LUG_R
    y0, y1 = LUG_SLEEVE_Y
    return (cyl_y(P.STOP_LUG_D / 2, y0, y1, 0.0, z)
            + cyl_y(LUG_HEAD[0] / 2, y0 - LUG_HEAD[1], y0, 0.0, z))


def stop_slot_angles():
    """The -Y cheek's arc slot's two end faces, as angles about C (atan2(z - Z_NOD, x)), so the
    lug's flank meets them at exactly NOD_STOP.

    At rest the lug is straight below C, at -90; a nod of n (nose up +) turns it to -90 + n.
    A radial end face touches a peg of STOP_LUG_D at STOP_LUG_R when it is asin(half / R) past
    the peg's centre."""
    half = math.degrees(math.asin((P.STOP_LUG_D / 2) / P.STOP_LUG_R))
    return -90.0 + P.NOD_STOP[0] - half, -90.0 + P.NOD_STOP[1] + half


def nozzle():
    """The brass nozzle, fixed in the mouth, along +X."""
    return cyl_x(P.NOZZLE_D / 2, P.NOZZLE_TIP_X - P.NOZZLE_L, P.NOZZLE_TIP_X, 0.0, P.Z_MOUTH)


def nod_bought():
    """Every bought part of the nod drive at rest, by name, with how it moves."""
    return {"nod_servo": (nod_servo(), "pans"), "bushing": (bushing(), "pans"),
            "horn": (horn(), "nods"), "pin": (pin(), "nods"), "stop_lug": (stop_lug(), "nods"),
            "nozzle": (nozzle(), "nods")}
