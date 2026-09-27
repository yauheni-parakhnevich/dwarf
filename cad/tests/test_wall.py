"""How thick the shell actually is, measured off the meshes the statue stage writes.

`WALL` is what SOLIDIFY was asked for and the median says it got it, but a median is not what
cracks on the bed. The shell is an inward offset of a 200 000-triangle reconstruction, and an
offset surface folds in on itself wherever the skin's own curvature is tighter than the offset -
along the skirt's hem, between the beard's strands. Where it folds, the difference that makes
the cavity eats into the wall, and the first build measured here had patches of literally zero.
At a 0.6 mm nozzle anything under about 1.2 mm is one bead or a gap: a pinhole in the boot.

So the arbiter is the distance from a void's surface to the skin, sampled evenly over the whole
of it, and three numbers are held for each of the two voids the stage writes:

  * the thinnest sample is at least the floor that void may never go under;
  * under 0.4 mm below nominal is a rounding error's worth of the surface, not a region;
  * the median is still nominal, so a fix that merely fattened the offset fails here.

The last one matters: the cavity is what every part is fitted against (`test_fit.py`), and
buying a minimum by moving the whole inner surface inward would take the room away from the
mechanism instead of from the folds.

`cavity_grown` is held to the same three, `GROW` shallower throughout. It is not a wall - it is
the volume an interface part may reach into so its boss ends inside the wall and fuses to it,
which is `WALL - GROW` = 1.2 mm of skin left over the boss. In the folds that was nothing at
all, and a boss there would have printed as a hole in the statue.
"""
from pathlib import Path

import numpy as np
import pytest
import params as P
from statue import GROW, KERF

OUT = Path(__file__).resolve().parents[1] / "out" / "statue"
CAVITY = OUT / "cavity.stl"
GROWN = OUT / "cavity_grown.stl"
OUTER = OUT / "outer.stl"
SAMPLES = 25000

pytestmark = [pytest.mark.slow, pytest.mark.skipif(not (CAVITY.exists() and GROWN.exists() and OUTER.exists()),
                                reason="the statue stage has not written out/statue/ yet")]


def measure(path):
    """The skin left over every one of SAMPLES points spread evenly over that void's surface."""
    import trimesh
    void = trimesh.load_mesh(str(path))
    skin = trimesh.load_mesh(str(OUTER))
    pts, _ = trimesh.sample.sample_surface_even(void, SAMPLES, seed=7)
    # exact point-to-triangle, not a nearest neighbour in a cloud of samples: a cloud only ever
    # overstates the distance, which is the direction that hides a thin patch.
    _, d, _ = trimesh.proximity.closest_point(skin, pts)
    return pts, d


@pytest.fixture(scope="module")
def thickness():
    return measure(CAVITY)


@pytest.fixture(scope="module")
def grown():
    return measure(GROWN)


def histogram(d, nominal):
    edges = [0.0] + [round(nominal + x, 2) for x in
                     (-2.4, -1.6, -1.2, -0.8, -0.4, -0.2, 0.0, 0.2)] + [1e9]
    edges = sorted(set(e for e in edges if e >= 0.0))
    n, _ = np.histogram(d, bins=edges)
    rows = [f"{lo:6.2f}-{hi:6.2f} mm: {c:6d}  {100 * c / len(d):6.3f} %"
            for lo, hi, c in zip(edges, edges[1:], n)]
    return (f"{len(d)} samples  min {d.min():.3f}  p1 {np.percentile(d, 1):.3f}  "
            f"median {np.median(d):.3f}  max {d.max():.3f}\n" + "\n".join(rows))


# --- the cavity: what is left of the wall over it ---------------------------------------------

def test_the_wall_is_never_thinner_than_the_floor(thickness):
    """No pinholes. The 0.1 is the sampler's own reach, not slack in the shape."""
    pts, d = thickness
    worst = pts[np.argmin(d)]
    assert d.min() >= P.WALL_MIN - 0.1, (
        f"thinnest wall {d.min():.3f} mm at "
        f"({worst[0]:.1f}, {worst[1]:.1f}, {worst[2]:.1f})\n{histogram(d, P.WALL)}")


def test_almost_none_of_the_wall_is_thin(thickness):
    """A fold may round a facet's worth off the wall; it may not thin a patch of it."""
    _, d = thickness
    thin = float((d < P.WALL - 0.4).mean())
    assert thin < 0.01, (f"{100 * thin:.3f} % of the inner surface is under "
                         f"{P.WALL - 0.4} mm\n{histogram(d, P.WALL)}")


def test_the_wall_was_not_simply_fattened(thickness):
    """The cavity is the mechanism's room. Thickening the folds may not cost it anywhere else."""
    _, d = thickness
    assert abs(float(np.median(d)) - P.WALL) <= 0.15, (
        f"median wall {np.median(d):.3f} mm, not {P.WALL}\n{histogram(d, P.WALL)}")


# --- cavity_grown: what is left of the skin over a boss clipped to it -------------------------

def test_the_grown_cavity_never_reaches_the_skin(grown):
    """A boss clipped to this must still have skin over it, everywhere, not only on average."""
    pts, d = grown
    worst = pts[np.argmin(d)]
    assert d.min() >= P.WALL_MIN - GROW - 0.1, (
        f"the grown cavity comes within {d.min():.3f} mm of the skin at "
        f"({worst[0]:.1f}, {worst[1]:.1f}, {worst[2]:.1f})\n{histogram(d, P.WALL - GROW)}")


def test_almost_none_of_the_grown_cavity_is_shallow(grown):
    _, d = grown
    thin = float((d < P.WALL - GROW - 0.4).mean())
    assert thin < 0.01, (f"{100 * thin:.3f} % of the grown cavity's surface is under "
                         f"{P.WALL - GROW - 0.4} mm from the skin\n{histogram(d, P.WALL - GROW)}")


def test_the_grown_cavity_did_not_shrink_everywhere(grown):
    """It is the reach an interface part is given. Taking that back would starve the bosses."""
    _, d = grown
    assert abs(float(np.median(d)) - (P.WALL - GROW)) <= 0.15, (
        f"the grown cavity's median skin is {np.median(d):.3f} mm, not "
        f"{P.WALL - GROW}\n{histogram(d, P.WALL - GROW)}")


# --- what the parting built: the turning unit, the socket, the rim's flange ---------------------
#
# The two voids above say nothing about the pieces cut from the shell afterwards, and the parting
# cuts and adds: the unit's back is the sphere where the beard stood proud of it, the socket and
# the bib are a new wall on the sphere one wall inside, and the rim carries a flange. Each is
# measured the way its wall runs:
#
#   * the unit's ordinary wall - head, hat, the beard's front - from every sample on the cavity
#     to the skin, as for the cavity above;
#   * the unit's back on the sphere R and its flange, along the radius from C outward, through
#     the material to wherever it ends (the skin, a lift, the flange's top);
#   * the socket and bib, along the radius from its inner sphere out through the wall.
#
# A ray from a sample right beside the end of the face it stands on - a cut, the flange's side,
# the rim - leaves through that end and reads as thin without the wall being so; samples within
# EDGE of where their face ends (for the ordinary wall, of any edge sharper than 60 degrees) are
# left out. That is not a hiding place for a feather: a wedge sharper than about 47 degrees is
# still under WALL_MIN at EDGE from its end, and is caught there.

import math
import numpy as np

RAW = OUT / "raw"
EDGE = 1.5
UNIT = [RAW / f"{n}.stl" for n in ("beard", "head", "hat")]
C = np.array([0.0, 0.0, P.Z_NOD])
R_IN = P.NECK_SPHERE_R - P.TURN_GAP - P.WALL


def _edges(mesh):
    """Points every 0.5 mm along the mesh's sharp edges."""
    sharp = mesh.face_adjacency_angles > math.radians(60.0)
    e = mesh.vertices[mesh.face_adjacency_edges[sharp]]
    pts = [e[:, 0] + (e[:, 1] - e[:, 0]) * f for f in np.linspace(0.0, 1.0, 5)]
    return np.vstack(pts)


def _inside_face(mesh, pts, d, radius):
    """Samples on the sphere of `radius` about C that are more than EDGE from where the mesh's
    face on that sphere ends."""
    from scipy.spatial import cKDTree
    fc = mesh.triangles_center
    dc = np.linalg.norm(fc - C, axis=1)
    radial = np.einsum("ij,ij->i", mesh.face_normals, (fc - C) / dc[:, None])
    off = (np.abs(dc - radius) > 0.1) | (np.abs(radial) < 0.98)
    near = mesh.triangles[off].reshape(-1, 3)
    near = np.vstack([near, fc[off]])
    return (np.abs(d - radius) < 0.05) & (cKDTree(near).query(pts)[0] > EDGE)


def _rays(mesh, pts, dirs):
    o = pts + dirs * 1e-3
    loc, idx, _ = mesh.ray.intersects_location(o, dirs, multiple_hits=False)
    t = np.full(len(pts), np.nan)
    t[idx] = np.linalg.norm(loc - o[idx], axis=1) + 1e-3
    return t[np.isfinite(t)]


@pytest.fixture(scope="module")
def parts():
    import trimesh
    from scipy.spatial import cKDTree
    if not all(p.exists() for p in UNIT + [RAW / "collar.stl"]):
        pytest.skip("the statue stage has not written the parting's sections yet")
    unit = trimesh.util.concatenate([trimesh.load_mesh(str(p)) for p in UNIT])
    skin = trimesh.load_mesh(str(OUTER))
    cavity = trimesh.load_mesh(str(CAVITY))
    pts, fi = trimesh.sample.sample_surface_even(unit, SAMPLES * 4, seed=7)
    clear = cKDTree(_edges(unit)).query(pts)[0] > EDGE
    _, dc, _ = trimesh.proximity.closest_point(cavity, pts)
    wall = clear & (dc < 0.05)
    _, dskin, _ = trimesh.proximity.closest_point(skin, pts[wall])
    # the unit's faces on the sphere - its back and the flange - are sampled on their own, one
    # sample per square millimetre, so a narrow band along the rim is not missed between samples
    fc = unit.triangles_center
    on_face = np.abs(np.linalg.norm(fc - C, axis=1) - P.NECK_SPHERE_R) < 0.05
    sph = unit.submesh([np.flatnonzero(on_face)], append=True)
    pts, _ = trimesh.sample.sample_surface_even(sph, int(sph.area), seed=7)
    d = np.linalg.norm(pts - C, axis=1)
    on = _inside_face(unit, pts, d, P.NECK_SPHERE_R)
    radial = (pts[on] - C) / d[on][:, None]
    t = _rays(unit, pts[on], radial)
    _, ds, _ = trimesh.proximity.closest_point(skin, pts[on])
    ds = ds[: len(t)]
    flange = ds > t + 0.3                        # the flange ends before the skin does
    collar = trimesh.load_mesh(str(RAW / "collar.stl"))
    pc, _ = trimesh.sample.sample_surface_even(collar, SAMPLES, seed=7)
    dcc = np.linalg.norm(pc - C, axis=1)
    sock = _inside_face(collar, pc, dcc, R_IN)
    tc = _rays(collar, pc[sock], (pc[sock] - C) / dcc[sock][:, None])
    return {"unit_wall": dskin, "unit_back": t[~flange], "flange": t[flange], "socket": tc}


def _report(name, d):
    return (f"{name}: {len(d)} samples  min {d.min():.3f}  p1 {np.percentile(d, 1):.3f}  "
            f"median {np.median(d):.3f}  under {P.WALL - 0.4:.1f}: {100 * (d < P.WALL - 0.4).mean():.2f} %")


@pytest.mark.parametrize("region", ["unit_wall", "unit_back", "flange", "socket"])
def test_the_partings_walls_are_never_thinner_than_the_floor(parts, region):
    d = parts[region]
    assert len(d) > 50, f"{region}: only {len(d)} samples"
    assert d.min() >= P.WALL_MIN - 0.1, _report(region, d)


@pytest.mark.parametrize("region", ["unit_wall", "unit_back", "flange", "socket"])
def test_almost_none_of_the_partings_walls_is_thin(parts, region):
    d = parts[region]
    assert (d < P.WALL - 0.4).mean() < 0.01, _report(region, d)


def test_the_partings_walls_are_what_they_were_drawn(parts):
    """The ordinary wall, the socket and the flange are drawn one wall thick; the unit's back is
    the beard standing proud of the sphere, never under a wall where it is kept - and where the
    skin was lifted it is exactly one, so its median is held to the same 0.15 as the others."""
    for region, want in (("unit_wall", P.WALL), ("socket", P.WALL), ("flange", P.RIM_FLANGE_T)):
        assert abs(float(np.median(parts[region])) - want) <= 0.15, _report(region, parts[region])
    assert np.median(parts["unit_back"]) >= P.WALL - 0.15, _report("unit_back", parts["unit_back"])


# --- the backstop: rays that find holes ---------------------------------------------------------
#
# The thickness tests above sample surfaces, and a sample only exists where there is surface: a
# slot where the wall is simply missing has no samples to be thin, and the tests above cannot see
# it. That is how four through-slots at the nape went unnoticed. So rays are cast from inside and
# must be stopped before they leave the statue's skin:
#
#   * from the pan axis, every 2 mm from z 245 to 430, every degree of azimuth, level and at
#     +-20 degrees, against every shell section as assembled (fixed and turning, at rest);
#   * from C, every degree of azimuth and of polar angle, against the turning unit alone.
#
# A ray passes if it meets a shell before it has gone RAY_GRACE past the point where it leaves the
# sculpt's skin: the bib is filled out to the socket's sphere over the beard's central groove, up
# to 11 mm proud of the skin there, and the lifted pinholes up to 3 mm. It is excused if it leaves through a
# designed opening, named in OPENINGS below with its reason. What this does not see: a hole
# smaller than the ray spacing (2 mm and 1 degree), and anything in a direction the rays do not
# go - under z 245, and from C below the unit's rim, which is the coat's business and the first
# sweep's.

import json

STL = OUT.parent / "stl"
RAY_GRACE = 12.0
FIXED = ("torso", "collar", "panel_left", "panel_right", "hand_left", "hand_right",
         "base_left", "base_right")


def _piece(name):
    import trimesh
    for p in (STL / f"{name}.stl", RAW / f"{name}.stl"):
        if p.exists():
            return trimesh.load_mesh(str(p))
    return None


def _unit_pieces():
    got = [m for m in (_piece("beard_left"), _piece("beard_right")) if m is not None]
    if not got:
        got = [_piece("beard")]
    return got + [_piece("head"), _piece("hat")]


def _plane_segments(meshes, phi, centre_z):
    """Every mesh's section by the vertical half-plane at azimuth `phi`, in (rho, z - centre_z)."""
    import trimesh
    a = math.radians(phi)
    out = []
    for m in meshes:
        s = trimesh.intersections.mesh_plane(m, (-math.sin(a), math.cos(a), 0.0), (0.0, 0.0, centre_z))
        s = np.asarray(s)
        if len(s):
            rho = s[..., 0] * math.cos(a) + s[..., 1] * math.sin(a)
            out.append(np.stack([rho, s[..., 2] - centre_z], axis=-1))
    return np.concatenate(out) if out else np.zeros((0, 2, 2))


def _first_hits(segs, origins, dirs):
    """For 2D rays, the distance to the first crossing of `segs` (inf if none)."""
    if not len(segs):
        return np.full(len(origins), np.inf)
    a, e = segs[:, 0], segs[:, 1] - segs[:, 0]
    oa = a[None] - origins[:, None]
    den = dirs[:, None, 0] * e[None, :, 1] - dirs[:, None, 1] * e[None, :, 0]
    ok = np.abs(den) > 1e-12
    w = np.where(ok, den, 1.0)
    t = (oa[..., 0] * e[None, :, 1] - oa[..., 1] * e[None, :, 0]) / w
    u = (oa[..., 0] * dirs[:, None, 1] - oa[..., 1] * dirs[:, None, 0]) / w
    t = np.where(ok & (t > 1e-6) & (u >= 0.0) & (u <= 1.0), t, np.inf)
    return t.min(axis=1)


def _holes_table():
    """(az, z, radius) of every radial screw hole the assembler cut, from its holes.json."""
    f = STL / "holes.json"
    if not f.exists():
        return []
    out = []
    for key, v in json.loads(f.read_text()).items():
        az, z = (float(x) for x in key.split("@"))
        out.append((az, z, v.get("skin", 90.0)))
    return out


def _opening(p, screws):
    """Why a ray that left the skin at `p` is allowed out, or None."""
    x, y, z = p
    az = math.degrees(math.atan2(y, x)) % 360.0
    for a, zz, rr in screws:
        if abs(((az - a + 180.0) % 360.0) - 180.0) * math.pi / 180.0 * rr < 4.0 and abs(z - zz) < 4.0:
            return "a screw hole"
    if x > 0 and abs(y - P.CAM_Y) <= P.WINDOW_W / 2 + 2 and abs(z - (P.Z_LENS + P.WINDOW_Z_BIAS)) <= P.WINDOW_H / 2 + 2:
        return "the camera window"
    if x < 0 and abs(y - P.VENT_IN_Y) <= P.VENT_IN_W / 2 + 2 and abs(z - P.Z_VENT_IN) <= P.VENT_IN_H / 2 + 2:
        return "the air intake"
    fa = math.radians(P.FILLER_PORT_AZ)
    port = np.array([P.FILLER_PORT_SKIN_R * math.cos(fa), P.FILLER_PORT_SKIN_R * math.sin(fa), P.FILLER_PORT_Z])
    if np.linalg.norm(np.asarray(p) - port) <= P.FILLER_POCKET_R + 4.0:
        return "the filler's pocket and its weep"
    if x > 0 and abs(y) <= P.MOUTH_D / 2 + 2 and abs(z - P.Z_MOUTH) <= P.MOUTH_D / 2 + 2:
        return "the mouth"
    if x > 0 and abs(y) <= P.BEARD_KERF / 2 + 1.0 and P.Z_BEARD_BOT <= z <= 412.0:
        return "the kerf between the beard's halves"
    if abs(y) <= KERF / 2 + 0.5 and z <= P.Z_BELT:
        return "the kerf between the base halves"
    d = math.dist(p, C)
    if z >= P.Z_BEARD_BOT - P.TURN_GAP - 0.5 and P.NECK_SPHERE_R - P.TURN_GAP - 0.3 <= d <= P.NECK_SPHERE_R + 0.3:
        return "the turning gap"
    if P.Z_BEARD_BOT - P.TURN_GAP - 0.5 <= z <= P.Z_BEARD_BOT + 0.5:
        return "the turning gap under the unit's flat bottom"
    return None


def _cast(pieces, skin, origin_z, zs, angles, phis, screws, grace=RAY_GRACE):
    """Rays from (0, 0, z) for z in zs (relative to origin_z) in directions `angles` (radians from
    horizontal, in the vertical half-plane), every azimuth in `phis`. Returns the escapes."""
    escapes = []
    for phi in phis:
        segs = _plane_segments(pieces, phi, origin_z)
        sk = _plane_segments([skin], phi, origin_z)
        o = np.array([(0.0, z) for z in zs for _ in angles])
        dv = np.array([(math.cos(a), math.sin(a)) for _ in zs for a in angles])
        t_skin = _first_hits(sk, o, dv)
        t_hit = _first_hits(segs, o, dv)
        bad = np.isfinite(t_skin) & (t_hit > t_skin + grace)
        for k in np.flatnonzero(bad):
            q = o[k] + dv[k] * t_skin[k]
            a = math.radians(phi)
            p = (q[0] * math.cos(a), q[0] * math.sin(a), q[1] + origin_z)
            why = _opening(p, screws)
            if why is None:
                escapes.append((round(phi, 1), round(p[2], 1), p))
    return escapes


def _summary(esc):
    """The escapes grouped into runs of neighbouring azimuths, as (az from..to, z from..to, count)."""
    if not esc:
        return "none"
    esc = sorted(esc)
    groups, cur = [], [esc[0]]
    for e in esc[1:]:
        if e[0] - cur[-1][0] <= 1.5:
            cur.append(e)
        else:
            groups.append(cur)
            cur = [e]
    groups.append(cur)
    return "; ".join(f"az {g[0][0]:.0f}..{g[-1][0]:.0f} z {min(x[1] for x in g):.0f}..{max(x[1] for x in g):.0f}"
                     f" ({len(g)} rays)" for g in groups)


def test_no_ray_from_the_axis_gets_out_of_the_statue_shut():
    import trimesh
    if not OUTER.exists():
        pytest.skip("no statue")
    pieces = [m for m in [_piece(n) for n in FIXED] + _unit_pieces() if m is not None]
    if len(pieces) < len(FIXED) + 3:
        pytest.skip("the statue's sections are not all built")
    skin = trimesh.load_mesh(str(OUTER))
    esc = _cast(pieces, skin, 0.0, np.arange(245.0, 430.1, 2.0),
                [0.0, math.radians(20.0), math.radians(-20.0)], np.arange(0.0, 360.0, 1.0),
                _holes_table())
    assert not esc, f"{len(esc)} rays from the pan axis leave through the shell: {_summary(esc)}"


def test_no_hole_in_the_turning_unit():
    """From C, every degree of azimuth and polar angle, against the unit alone.

    Along its edge the unit is cut back on purpose - skin thinner than RIM_MIN_T, the nod trim -
    and there the socket shows through by design; a ray there leaves unmet, but its miss borders
    the coat's ground. A hole is a miss walled in by the unit's own material on every side, as
    the flank's pinhole was: those are what this finds. Misses on the coat's ground (the ray left
    the statue inside the ball, below the unit's flat bottom, or through what the nod trim takes
    off) and through designed openings (the mouth, the screw holes, the beard's kerf) do not count.
    """
    import trimesh
    from scipy.ndimage import binary_fill_holes
    if not OUTER.exists():
        pytest.skip("no statue")
    unit = [m for m in _unit_pieces() if m is not None]
    skin = trimesh.load_mesh(str(OUTER))
    screws = _holes_table()
    polar = np.radians(np.arange(1.0, 120.0, 1.0))
    phis = np.arange(0.0, 360.0, 1.0)
    hit = np.zeros((len(phis), len(polar)), bool)
    excused = np.zeros_like(hit)
    trims = [math.radians(-n) for n in np.arange(P.NOD_RANGE[0], P.NOD_RANGE[1] + 1e-9, 1.0)]
    for i, phi in enumerate(phis):
        segs = _plane_segments(unit, phi, P.Z_NOD)
        sk = _plane_segments([skin], phi, P.Z_NOD)
        o = np.zeros((len(polar), 2))
        dv = np.stack([np.sin(polar), np.cos(polar)], axis=1)
        ts, th = _first_hits(sk, o, dv), _first_hits(segs, o, dv)
        hit[i] = th <= ts + RAY_GRACE
        a = math.radians(phi)
        for j in np.flatnonzero(~hit[i] & np.isfinite(ts)):
            q = dv[j] * ts[j]
            pnt = (q[0] * math.cos(a), q[0] * math.sin(a), q[1] + P.Z_NOD)
            coat = (math.dist(pnt, C) < P.NECK_SPHERE_R + 0.3 or pnt[2] < P.Z_BEARD_BOT + 0.5 or
                    any(-pnt[0] * math.sin(t) + q[1] * math.cos(t) + P.Z_NOD < P.Z_BEARD_BOT for t in trims))
            excused[i, j] = coat or _opening(pnt, screws) is not None
        excused[i] |= ~np.isfinite(ts)
    tiled = np.vstack([hit, hit, hit])                    # azimuth wraps round
    walled = binary_fill_holes(tiled)[len(phis):2 * len(phis)] & ~hit
    holes = walled & ~excused
    found = [(float(phis[i]), float(np.degrees(polar[j]))) for i, j in zip(*np.nonzero(holes))]
    assert not found, (f"{len(found)} directions from C leave through a hole in the turning unit, "
                       f"(az, polar): {found[:40]}")
