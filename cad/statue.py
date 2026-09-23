#!/usr/bin/env python
"""The AI statue, turned into the shell.

`cad/in/gnome_ai.glb` is an image-to-3D reconstruction of the gnome (see `cad/in/fit_report.md`).
This module is the only place that touches it. It

  1. puts it in the project frame - X front, Y left, Z up, mm, origin on the floor under the pan
     axis - straightens its lean and mirrors it about its own sagittal plane,
  2. hollows it in Blender (SOLIDIFY, inward, so the outside keeps the statue's own skin),
  3. measures the cavity and writes `features.json`, which is what every other agent reads
     instead of guessing at the skin, and
  4. cuts the raw printable sections.

Everything it writes lands in `out/statue/`:

    outer.stl          the closed skin, in the project frame
    shell.stl          the skin walled inward by WALL - the shell proper
    cavity.stl         the void inside it
    cavity_grown.stl   the void grown GROW mm back towards the skin; the assembler clips
                       interface parts to this, so a boss ends inside the wall and fuses to it
    features.json      feature heights, the per-5-mm reach table, the legs
    raw/*.stl          the sections, before the assembler cuts openings in them

The sections follow the fit report's 6.3: everything above `Z_TURN` (the beard's bottom edge)
is one turning bell - beard, head, hat - which lifts off, so the coat below it has no belly
hatch and no sculpted skin above the seam. `R_TURN` is the radius the bell's inside keeps clear
for the shroud; `TURN_GAP` is the air in the seam.
"""
import json
import math
import sys
from pathlib import Path

import numpy as np
import trimesh
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import connected_components
from scipy.spatial import cKDTree

CAD = Path(__file__).resolve().parent
sys.path.insert(0, str(CAD))
import params as P  # noqa: E402

OUT = CAD / "out" / "statue"
RAW = OUT / "raw"
FAR = 900.0                  # big enough to swallow the statue, small enough to stay exact
GROW = 1.2                   # how far cavity_grown reaches back towards the skin
KERF = 1.0                   # air between the two base halves
# The hands stick out past the coat; the torso band is 276 mm across with them and 236 without.
HAND = {"y": 118.0, "z": (196.0, 306.0), "x": (-80.0, 106.0)}
STEP = 5.0                   # the reach table's resolution
Z_LEGS = P.Z_FLOOR - 50.0    # where the pump and the valve stand


# --- writing meshes out ---------------------------------------------------------------------

def tidy(mesh):
    """Drop the crumbs a cut leaves and pull apart pinched vertices before writing the file.

    Both are the lessons the assembler learned, and they apply to every mesh here, not only the
    sections. A plane grazing a 200 000-triangle skin leaves closed surfaces with no volume
    behind them; manifold3d is entitled to leave two vertices in one place where a cutter grazed
    a facet. Either is a perfectly good solid in memory and neither survives an STL, which has no
    vertex identity and merges the pair into an edge with four faces on it. The cavity went out
    of here unwatertight that way, and a mesh nothing can test is worse than no mesh.

    Two things this learned the hard way. A crumb is not always loose: a flap welded to the body
    along a pinched edge looks like its own component, because faces meeting at such an edge are
    not adjacent, and dropping it leaves a hole - so a drop that breaks the solid is undone. And
    a vertex of a degenerate triangle has no normal to move along, numpy says NaN rather than
    saying so, and those were the twins that stayed twinned; they now move away from the mesh's
    own centre instead, which is never the zero vector.
    """
    parts = mesh.split(only_watertight=False)
    dropped = 0
    if len(parts) > 1:
        solid = [c for c in parts if abs(c.volume) > 1000.0]
        if len(solid) < len(parts) and solid:
            kept = solid[0] if len(solid) == 1 else trimesh.util.concatenate(solid)
            if kept.is_watertight:
                dropped, mesh = len(parts) - len(solid), kept
    v = np.asarray(mesh.vertices)
    pairs = cKDTree(v).query_pairs(2e-4, output_type="ndarray")
    pinches = 0
    if len(pairs):
        mesh = mesh.copy()
        # Twins come in threes and fours as often as in twos - three surfaces meeting at a point
        # the lathe's cylinder grazed - so the whole cluster is found at once and every member
        # but the first is moved by a different amount. Moving one of a pair, which is what this
        # did before, leaves a four-way pinch four-way.
        n = len(v)
        graph = csr_matrix((np.ones(len(pairs)), (pairs[:, 0], pairs[:, 1])), shape=(n, n))
        count, label = connected_components(graph, directed=False)
        order = np.argsort(label, kind="stable")
        rank = np.empty(n, int)
        rank[order] = np.arange(n) - np.maximum.accumulate(
            np.where(np.r_[True, label[order][1:] != label[order][:-1]], np.arange(n), 0))
        moving = np.isin(np.arange(n), np.unique(pairs)) & (rank > 0)
        idx = np.flatnonzero(moving)
        d = np.nan_to_num(np.asarray(mesh.vertex_normals)[idx], nan=0.0, posinf=0.0, neginf=0.0)
        away = mesh.vertices[idx] - mesh.vertices.mean(axis=0)
        lost = np.linalg.norm(d, axis=1) < 1e-6
        d[lost] = away[lost] / np.maximum(np.linalg.norm(away[lost], axis=1), 1e-9)[:, None]
        mesh.vertices[idx] = mesh.vertices[idx] + d * (2e-3 * rank[idx])[:, None]
        pinches = len(idx)
    return mesh, dropped, pinches


def write(mesh, path, label="", quiet=False):
    """Tidy, write, read back, and refuse to go on if the file is not the solid we had."""
    mesh, dropped, pinches = tidy(mesh)
    mesh.merge_vertices()
    path.parent.mkdir(parents=True, exist_ok=True)
    mesh.export(path)
    back = trimesh.load(path)
    note = "".join([f", {dropped} crumbs" if dropped else "", f", {pinches} pinches" if pinches else ""])
    if not quiet:
        print(f"statue {path.stem:13s} {len(back.faces):7d} faces  {back.volume / 1e6:7.3f} L  "
              f"watertight={back.is_watertight}{note}  {label}")
    else:
        e = back.extents
        print(f"       {path.stem:12s} {back.volume / 1e3:8.1f} cm3  {len(back.faces):7d} faces  "
              f"{back.body_count} body  bbox {e[0]:.0f} x {e[1]:.0f} x {e[2]:.0f} mm  "
              f"watertight={back.is_watertight}{note}{label}")
    if not back.is_watertight or not back.is_winding_consistent:
        raise RuntimeError(f"{path.name} is not a solid after the round trip to STL")
    if abs(back.volume - mesh.volume) > 0.001 * abs(mesh.volume) or \
            np.abs(back.bounds - mesh.bounds).max() > 0.01:
        raise RuntimeError(f"{path.name} changed on its way through the STL")
    return back


# --- the frame ------------------------------------------------------------------------------

def cylinder(r, z0, z1, sections=256):
    return trimesh.creation.cylinder(radius=r, height=z1 - z0, sections=sections,
                                     transform=trimesh.transformations.translation_matrix(
                                         (0.0, 0.0, (z0 + z1) / 2)))


def box(lo, hi):
    lo, hi = np.array(lo, float), np.array(hi, float)
    return trimesh.creation.box(extents=hi - lo, transform=trimesh.transformations.translation_matrix((lo + hi) / 2))


def cut(mesh, lo, hi, op="intersection"):
    return trimesh.boolean.boolean_manifold([mesh, box(lo, hi)], op)


def raw_frame():
    """Load the GLB and put it in the project frame, lean and all."""
    m = trimesh.load(CAD / P.STATUE_GLB, force="mesh")
    v = m.vertices
    v = np.column_stack([v[:, 2], v[:, 0], v[:, 1]])       # fit report 1: X = z_glb, Y = x_glb, Z = y_glb
    v = v * (P.Z_TOP / (v[:, 2].max() - v[:, 2].min()))    # the statue is exactly Z_TOP tall
    lo, hi = v.min(axis=0), v.max(axis=0)
    v[:, 0] -= (lo[0] + hi[0]) / 2                         # X: the bounding box's centre
    v[:, 1] -= (lo[1] + hi[1]) / 2
    v[:, 2] -= lo[2]                                       # the soles on the floor
    return trimesh.Trimesh(vertices=v, faces=m.faces, process=False)


def sagittal(mesh, step=50.0, half=35.0):
    """Where the statue's own plane of symmetry sits, height by height.

    The reconstruction leans: its lower half is centred near y = +4 and its head near y = +16.
    Mirroring the whole thing about one plane would have to move one end or the other by the
    difference, which fattens whatever it moves. So the plane is measured in bands and the
    statue is sheared straight before it is mirrored - a shear in y only, so every horizontal
    section keeps its shape and only slides sideways.
    """
    pts, _ = trimesh.sample.sample_surface(mesh, 150000, seed=7)
    zs = np.arange(0.0, P.Z_TOP + step / 2, step)
    ys = []
    for z in zs:
        band = pts[(pts[:, 2] >= z - half) & (pts[:, 2] < z + half)]
        if len(band) < 400:
            ys.append(np.nan)
            continue
        tree = cKDTree(band)
        best, arg = None, 0.0
        for y0 in np.arange(-4.0, 26.1, 1.0):
            q = band.copy()
            q[:, 1] = 2 * y0 - q[:, 1]
            d = tree.query(q)[0].mean()
            if best is None or d < best:
                best, arg = d, y0
        ys.append(arg)
    ys = np.array(ys)
    good = ~np.isnan(ys)
    ys = np.interp(zs, zs[good], ys[good])
    ys = np.convolve(np.r_[ys[0], ys[0], ys, ys[-1], ys[-1]], np.ones(5) / 5, "valid")  # smooth
    return zs, ys


def outer():
    """outer.stl: the statue, in the frame, straight and symmetric."""
    m = raw_frame()
    print(f"statue glb  {len(m.faces)} faces, watertight={m.is_watertight}")
    zs, ys = sagittal(m)
    print("statue axis  " + "  ".join(f"{int(z)}:{y:+.1f}" for z, y in zip(zs, ys) if int(z) % 100 == 0))
    v = m.vertices.copy()
    v[:, 1] -= np.interp(v[:, 2], zs, ys)                  # shear the lean out
    m = trimesh.Trimesh(vertices=v, faces=m.faces, process=False)
    m.merge_vertices()
    m.fix_normals()
    half = cut(m, (-FAR, -0.05, -1.0), (FAR, FAR, P.Z_TOP + 1.0))
    mirror = half.copy()
    mirror.apply_transform(np.diag([1.0, -1.0, 1.0, 1.0]))  # trimesh flips the winding for us
    sym = trimesh.boolean.boolean_manifold([half, mirror], "union")
    b = sym.bounds
    sym = write(sym, OUT / "outer.stl",
                f"bounds x{b[0][0]:.0f}..{b[1][0]:.0f} y{b[0][1]:.0f}..{b[1][1]:.0f} "
                f"z{b[0][2]:.0f}..{b[1][2]:.0f}")
    return sym


# --- hollow ---------------------------------------------------------------------------------

def hollow():
    """shell.stl, cavity.stl, cavity_grown.stl. Blender walls; manifold takes the difference."""
    from build import blender
    raw = [OUT / "wall_full.stl", OUT / "wall_thin.stl"]
    blender("statue_hollow.py", wants=raw)
    skin = trimesh.load(OUT / "outer.stl")
    out = {}
    for void_name, wall_file, t in (("cavity", raw[0], P.WALL), ("cavity_grown", raw[1], P.WALL - GROW)):
        w = trimesh.load(wall_file)
        if not w.is_watertight:
            raise RuntimeError(f"{wall_file.name} is not watertight; SOLIDIFY folded somewhere")
        if void_name == "cavity":
            out["shell"] = write(w, OUT / "shell.stl", f"wall {t} mm, {w.volume * 1.24e-3:.0f} g of PLA")
        out[void_name] = write(trimesh.boolean.boolean_manifold([skin, w], "difference"),
                               OUT / f"{void_name}.stl", f"{t} mm inside the skin")
    return out["cavity"], out["cavity_grown"], out["shell"]


# --- what the mechanism needs to know -------------------------------------------------------

def segments_at(mesh, z):
    """The horizontal section at z, as an (n, 2, 2) array of x-y segments.

    Neither shapely nor networkx is in the build venv, so this stays with `mesh_plane`, which
    hands back unordered segments, and every question below - is the axis inside, how far to the
    wall - is answered with 2D segment maths that does not care about their order.
    """
    segs = trimesh.intersections.mesh_plane(mesh, (0.0, 0.0, 1.0), (0.0, 0.0, float(z)))
    return np.zeros((0, 2, 2)) if not len(segs) else np.asarray(segs)[:, :, :2]


def hits(segs, origin, direction):
    """Distances from `origin` along `direction` to every crossing of `segs`, sorted."""
    a = segs[:, 0] - origin
    e = segs[:, 1] - segs[:, 0]
    d = np.asarray(direction, float)
    den = d[0] * e[:, 1] - d[1] * e[:, 0]
    ok = np.abs(den) > 1e-12
    t = np.where(ok, (a[:, 0] * e[:, 1] - a[:, 1] * e[:, 0]) / np.where(ok, den, 1.0), -1.0)
    u = np.where(ok, (a[:, 0] * d[1] - a[:, 1] * d[0]) / np.where(ok, den, 1.0), -1.0)
    keep = ok & (t > 1e-9) & (u >= 0.0) & (u <= 1.0)
    t = np.sort(t[keep])
    # A ray through a shared vertex crosses twice and a fold left by the inward offset - under
    # the nose, inside the hem - crosses twice more a fraction of a millimetre apart. Neither is
    # a wall you could put a part against, so crossings within a millimetre count once.
    return t[np.r_[True, np.diff(t) > 1.0]] if len(t) else t


def inside(segs, point):
    """Is the point inside the section those segments bound? Crossing parity, in 2D.

    Three rays, best of three. One ray is enough in theory and wrong in practice: send it
    through a vertex shared by two segments, or along a fold the offset left, and it counts two
    crossings where the boundary was crossed once. Three directions that share no such accident
    turn that into a vote, and a level of the head stops reporting itself as solid.
    """
    votes = sum(len(hits(segs, point, d)) % 2 for d in ((1.0, 0.0), (0.0, 1.0), (0.6, 0.8)))
    return votes >= 2


def reach(cavity, shell):
    """How far the cavity reaches from the pan axis, every STEP mm: min, front, back, left, right.

    The fit report's T8 in table form: the distance from the axis to the first wall in each of 72
    directions. A crossing only counts as a wall if there is shell material just past it. That
    test is not fussiness - SOLIDIFY folds the wall in on itself where the skin's own curvature
    is tighter than its thickness, under the brim and behind the ears, and the difference that
    makes the cavity turns each fold into a surface the ray meets and the material behind it into
    something the same ray passes straight through. Both questions are answered on the two
    sections at this height, by crossing parity, which needs no ray cast into either solid.

    Where the axis is not inside the cavity at all - up in the leaning hat - the row is zeros,
    and whatever reads this table knows to stay out rather than to trust a reach of nothing.
    """
    table = {}
    zlo, zhi = cavity.bounds[0][2], cavity.bounds[1][2]
    for z in np.arange(math.ceil(zlo / STEP) * STEP, zhi, STEP):
        segs = segments_at(cavity, z)
        rs = np.zeros(72)
        if len(segs) and inside(segs, (0.0, 0.0)):
            wall = segments_at(shell, z)
            for i in range(72):
                a = math.radians(i * 5)
                d = (math.cos(a), math.sin(a))
                ts = hits(segs, (0.0, 0.0), d)[:4]
                for t in ts:
                    if inside(wall, (d[0] * (t + 0.5), d[1] * (t + 0.5))):
                        rs[i] = t
                        break
                else:
                    rs[i] = ts[-1] if len(ts) else 0.0
        table[str(int(round(z)))] = [round(float(x), 1) for x in
                                     (rs.min(), rs[0], rs[36], rs[18], rs[54])]  # min, +x, -x, +y, -y
    return table


def clearance(segs, pts):
    """Distance from each point to the nearest segment."""
    a, b = segs[:, 0], segs[:, 1]
    e = b - a
    ll = np.einsum("ij,ij->i", e, e)
    ll[ll == 0] = 1e-12
    d = pts[:, None, :] - a[None, :, :]
    t = np.clip(np.einsum("ijk,jk->ij", d, e) / ll, 0.0, 1.0)
    foot = a[None, :, :] + t[:, :, None] * e[None, :, :]
    return np.linalg.norm(pts[:, None, :] - foot, axis=2).min(axis=1)


def legs(cavity):
    """Where a bracket can stand in each trouser leg at Z_LEGS, and how much room it has.

    The reconstruction has no split between the legs down there - the coat is one skirt - so
    these are simply the two largest circles that fit in the cavity's section, one per side of
    the axis. `r` is the smaller of the two, which after the mirror is the same number twice.
    """
    segs = segments_at(cavity, Z_LEGS)
    if not len(segs):
        raise RuntimeError(f"no cavity at z={Z_LEGS}")
    lo, hi = segs.reshape(-1, 2).min(axis=0), segs.reshape(-1, 2).max(axis=0)
    out = {}
    for side, sign in (("left", 1.0),):
        best, room = (0.0, 0.0), 0.0
        for grid in (5.0, 1.0):
            if grid == 5.0:
                xs = np.arange(lo[0], hi[0], grid)
                ys = np.arange(max(lo[1], 0.0) if sign > 0 else lo[1],
                               hi[1] if sign > 0 else min(hi[1], 0.0), grid)
            else:
                xs = np.arange(best[0] - 6, best[0] + 6, grid)
                ys = np.arange(best[1] - 6, best[1] + 6, grid)
            pts = np.array([(x, y) for x in xs for y in ys
                            if (y >= 0) == (sign > 0) and inside(segs, (x, y))])
            if not len(pts):
                break
            room_all = clearance(segs, pts)
            i = int(np.argmax(room_all))
            best, room = tuple(pts[i]), float(room_all[i])
        out[side] = (best, room)
    (x, y), r = out["left"]                                 # the statue is mirrored; so is this
    return {"left": [round(float(x), 1), round(float(y), 1)],
            "right": [round(float(x), 1), round(float(-y), 1)], "r": round(float(r), 1)}


def measured(skin):
    """Feature heights read off the statue where it has a signature, from params where it has not."""
    pts, _ = trimesh.sample.sample_surface(skin, 400000, seed=11)
    zs = np.arange(0.0, P.Z_TOP, 2.0)
    front, side = [], []
    for z in zs:
        b = pts[(pts[:, 2] >= z - 3) & (pts[:, 2] < z + 3)]
        front.append(b[:, 0].max() if len(b) else np.nan)
        side.append(np.abs(b[:, 1]).max() if len(b) else np.nan)
    front, side = np.array(front), np.array(side)
    sm = lambda a: np.convolve(np.r_[[a[0]] * 3, a, [a[-1]] * 3], np.ones(7) / 7, "valid")
    front, side = sm(front), sm(side)

    def where(arr, lo, hi, what):
        s = (zs >= lo) & (zs < hi)
        d = np.gradient(arr, zs)
        if what == "min":
            return float(zs[s][np.argmin(arr[s])])
        if what == "max":
            return float(zs[s][np.argmax(arr[s])])
        if what == "rise":
            return float(zs[s][np.argmax(d[s])])
        if what == "drop":
            return float(zs[s][np.argmin(d[s])])
        return float(zs[s][np.argmin(np.gradient(d, zs)[s])])   # "knee": flat, then falling away

    out, src = {}, {}
    for name, z in ((n, v * P.Z_TOP) for n, v in P.STATUE_FEATURES.items()):
        out[name], src[name] = round(z, 1), "spec"
    # The ear has no signature to find: the side profile is flat from the beard to the brim, so
    # `ear` stays at the fit report's fraction. So do boot_top, belt, mouth and eye.
    for name, (arr, lo, hi, what) in {
        "hem":          (front, 110.0, 200.0, "rise"),
        "beard_bottom": (front, 270.0, 345.0, "min"),
        "chin":         (front, 385.0, 440.0, "min"),
        "nose":         (front, 430.0, 475.0, "max"),
        "brim_side":    (side,  470.0, 540.0, "drop"),
        "brim_front":   (front, 495.0, 545.0, "knee"),
    }.items():
        z = where(arr, lo, hi, what)
        out[name], src[name] = round(z, 1), "measured"
    # the hands: where the widest point runs more than 6 mm past the coat behind it
    bulge = side - np.interp(zs, [150.0, 340.0], [side[np.argmin(abs(zs - 150))], side[np.argmin(abs(zs - 340))]])
    band = (zs > 150) & (zs < 340) & (bulge > 6.0)
    if band.any():
        out["hands_bottom"], src["hands_bottom"] = round(float(zs[band].min()), 1), "measured"
        out["hands_top"], src["hands_top"] = round(float(zs[band].max()), 1), "measured"
    return out, src


def features(skin, cavity, shell):
    feats, src = measured(skin)
    doc = {
        "frame": "mm, Z up, +X front, +Y left, origin on the floor under the pan axis",
        "height": P.Z_TOP,
        "wall": P.WALL,
        "grown": GROW,
        "features": feats,
        "features_source": src,
        "reach_columns": ["min", "front(+x)", "back(-x)", "left(+y)", "right(-y)"],
        "reach_step": STEP,
        "reach": reach(cavity, shell),
        "legs_z": Z_LEGS,
        "legs": legs(cavity),
    }
    (OUT / "features.json").write_text(json.dumps(doc, indent=1))
    print(f"statue features  {len(doc['reach'])} reach rows, legs {doc['legs']}")
    return doc


# --- the sections ---------------------------------------------------------------------------

def min_radius(meshes, z_lo, z_hi, step=2.0):
    """The smallest distance from the pan axis to any of those meshes' material, over a z band."""
    best = None
    for z in np.arange(z_lo, z_hi + 1e-9, step):
        for m in meshes:
            segs = segments_at(m, z)
            if len(segs):
                r = float(np.hypot(segs[..., 0], segs[..., 1]).min())
                best = r if best is None else min(best, r)
    return best


def max_radius(mesh, z_lo, z_hi, step=2.0):
    """The largest radius `mesh` reaches over a z band, and the band where it passes `limit`."""
    out = {}
    for z in np.arange(z_lo, z_hi + 1e-9, step):
        segs = segments_at(mesh, z)
        if len(segs):
            out[float(z)] = float(np.hypot(segs[..., 0], segs[..., 1]).max())
    return out


def lathe(bell, fixed, skin, cavity, z_lo, z_hi):
    """Turn the bell down over the band where it would foul the fixed panels as it sweeps.

    Rotation about the pan axis is the whole design: under PANEL_TOP the bell has to live inside
    a cylinder, because anything of it at a radius the panels also occupy meets them within
    sixty-five degrees. The radius is the panels' own closest approach to the axis less TURN_GAP,
    measured on their cut sections rather than assumed from PANEL_Y - the coat's wall crosses
    that plane out at the sides, not in front, so there is a little more room than the plane says.

    A lathe turns a surface down; it does not punch a hole. Cutting the wall with the cylinder
    would have done the latter - the wall is 2.4 mm thick and stands out at r 105, so the cut
    took all of it and left the beard's front open. So the skin is turned down instead: inside
    the band the outer solid is intersected with the cylinder and the cavity with a cylinder one
    wall thinner, and the wall between them comes out as a cylindrical face where the beard's
    locks used to stand proud.
    """
    r_fixed = min_radius(fixed, z_lo, z_hi)
    r = r_fixed - P.TURN_GAP
    before = max_radius(bell, z_lo, z_hi)
    over = [z for z, rr in before.items() if rr > r]
    if not over:
        print(f"statue lathe    nothing to do: the bell clears r {r:.1f} under z {z_lo:.0f}..{z_hi:.0f}")
        return bell, r, None, 0.0
    band = (min(over), max(over))
    slab = box((-FAR, -FAR, z_lo), (FAR, FAR, z_hi))
    turned = trimesh.boolean.boolean_manifold(
        [trimesh.boolean.boolean_manifold([skin, slab, cylinder(r, z_lo - 2.0, z_hi + 2.0)], "intersection"),
         trimesh.boolean.boolean_manifold([cavity, slab, cylinder(r - P.WALL, z_lo - 2.0, z_hi + 2.0)],
                                          "intersection")], "difference")
    out = trimesh.boolean.boolean_manifold(
        [trimesh.boolean.boolean_manifold([bell, slab], "difference"), turned], "union")
    print(f"statue lathe    bell turned down to r {r:.1f} (the panels reach r {r_fixed:.1f}) over "
          f"z {band[0]:.0f}..{band[1]:.0f}, where it stood out to r {max(before.values()):.1f}; "
          f"{(out.volume - bell.volume) / 1e3:+.1f} cm3 of wall (locks off, a turned face on)")
    return out, r, band, out.volume - bell.volume


def sweep(bell, fixed, step=5.0):
    """Turn the bell through its stops against the fixed shell and report what it touches."""
    still = trimesh.boolean.boolean_manifold(list(fixed), "union")
    worst = (0.0, 0.0)
    for deg in np.arange(-P.PAN_STOP_DEG, P.PAN_STOP_DEG + 1e-9, step):
        turned = bell.copy()
        turned.apply_transform(trimesh.transformations.rotation_matrix(
            math.radians(float(deg)), (0.0, 0.0, 1.0)))
        hit = trimesh.boolean.boolean_manifold([turned, still], "intersection")
        v = abs(hit.volume) if len(hit.faces) else 0.0
        if v > worst[0]:
            worst = (v, float(deg))
    print(f"statue sweep    +-{P.PAN_STOP_DEG:.0f} deg every {step:.0f}: worst overlap "
          f"{worst[0]:.1f} mm3 at {worst[1]:+.0f} deg")
    return worst


def sections(shell, skin, cavity):
    """Cut the shell into the printable raw sections.

    Three things are fixed and three turn. The coat's belt ring and the two side panels - the
    sleeves, the mittens under them and the shoulders' sides - never move; the bell, which is
    everything above Z_TURN inside the panels and everything at all above PANEL_TOP, turns with
    the shroud and carries the beard, the face and the hat. The mitten caps come off the base
    halves for the bed and glue back on, and the panels glue to the ring.

    The bell is lathed where it would foul the panels; `lathe` says what that cost.
    """
    RAW.mkdir(parents=True, exist_ok=True)
    py, pb, pt = P.PANEL_Y, P.PANEL_BOTTOM, P.PANEL_TOP
    top = P.Z_TURN - P.TURN_GAP           # the coat's ring stops TURN_GAP under the bell's rim
    chin = P.SECTIONS_STATUE["beard"][1]  # where the bell is split for the bed, at the chin
    sides = {                             # the fixed sides: panels above the belt, mittens below
        "panel_left":  ((-FAR, py, P.Z_BELT), (FAR, FAR, pt)),
        "panel_right": ((-FAR, -FAR, P.Z_BELT), (FAR, -py, pt)),
        "hand_left":   ((-FAR, py, pb), (FAR, FAR, P.Z_BELT)),
        "hand_right":  ((-FAR, -FAR, pb), (FAR, -py, P.Z_BELT)),
    }
    out = {name: cut(shell, lo, hi) for name, (lo, hi) in sides.items()}
    # the base halves keep everything below the belt except the mitten caps
    below = cut(shell, (-FAR, -FAR, -1.0), (FAR, FAR, P.Z_BELT))
    for name in ("hand_left", "hand_right"):
        below = trimesh.boolean.boolean_manifold([below, out[name]], "difference")
    out["base_left"] = cut(below, (-FAR, KERF / 2, -1.0), (FAR, FAR, P.Z_BELT))
    out["base_right"] = cut(below, (-FAR, -FAR, -1.0), (FAR, -KERF / 2, P.Z_BELT))
    # the ring: the coat between the panels, from the belt to under the bell's rim
    out["torso"] = cut(shell, (-FAR, -py, P.Z_BELT), (FAR, py, top))
    # the bell: inside the panels above Z_TURN, everything above them
    bell = trimesh.boolean.boolean_manifold(
        [cut(shell, (-FAR, -py, P.Z_TURN), (FAR, py, pt)),
         cut(shell, (-FAR, -FAR, pt), (FAR, FAR, P.Z_TOP + 1.0))], "union")
    bell, r_lathe, band, turned_off = lathe(bell, [out["panel_left"], out["panel_right"]],
                                            skin, cavity, P.Z_TURN, pt)
    sweep(bell, [out["torso"], out["panel_left"], out["panel_right"],
                 out["hand_left"], out["hand_right"]])
    rim = bell.bounds
    print(f"statue bell     z {rim[0][2]:.1f}..{rim[1][2]:.1f}, "
          f"{bell.volume / 1e3:.0f} cm3; rim at the sides {pt:.0f}, in front {P.Z_TURN:.0f}")
    if rim[0][2] < P.Z_TURN - 1e-6:
        raise RuntimeError(f"the bell dips to z {rim[0][2]:.1f}, under Z_TURN")
    side_low = cut(bell, (-FAR, py - 1.0, -1.0), (FAR, FAR, P.Z_TOP + 1.0)).bounds[0][2]
    if side_low < pt - 1e-6:
        raise RuntimeError(f"the bell reaches z {side_low:.1f} outside the panels, under their top {pt}")
    for name, (lo, hi) in {"beard": (P.Z_TURN, chin), "head": (chin, P.Z_HAT),
                           "hat": (P.Z_HAT, P.Z_TOP + 1.0)}.items():
        out[name] = cut(bell, (-FAR, -FAR, lo), (FAR, FAR, hi))
    total = 0.0
    for name in P.SECTIONS_STATUE:
        back = write(out[name], RAW / f"{name}.stl", quiet=True)
        out[name] = back
        total += back.volume
        if max(back.extents) > P.BED:
            raise RuntimeError(f"{name} is {max(back.extents):.1f} mm across; the bed is {P.BED}")
    kerf = cut(shell, (-FAR, -KERF / 2, -1.0), (FAR, KERF / 2, P.Z_BELT)).volume
    seam = cut(shell, (-FAR, -py, top), (FAR, py, P.Z_TURN)).volume
    want = shell.volume - kerf - seam + turned_off
    err = (total - want) / shell.volume
    print(f"statue sections  {total / 1e3:.1f} cm3 against the shell's {shell.volume / 1e3:.1f} "
          f"less the y-kerf ({kerf / 1e3:.1f}) and the bell's seam ({seam / 1e3:.1f}), "
          f"plus the lathe ({turned_off / 1e3:+.1f}): {err * 100:+.2f} %")
    if abs(err) > 0.01:
        raise RuntimeError(f"the sections and the shell disagree by {err * 100:.2f} %")
    return out


def preview():
    from build import blender
    blender("statue_preview.py", fresh_in=(OUT, "preview_*.png"))


def main():
    skin = outer()
    cavity, grown, shell = hollow()
    features(skin, cavity, shell)
    sections(shell, skin, cavity)
    preview()


if __name__ == "__main__":
    main()
