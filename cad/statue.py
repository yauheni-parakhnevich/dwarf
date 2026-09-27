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

The sections part on one sphere. The head pans about Z and nods about Y, and both are
rotations about a single point C = (0, 0, `Z_NOD`) on the pan axis; a rotation about a point
maps every sphere about that point to itself. So the coat is kept inside the ball of radius
`NECK_SPHERE_R` - `TURN_GAP` about C and the turning unit outside the sphere of radius
`NECK_SPHERE_R`, and then no pan and no nod can bring them together. The seam is where the
sculpt's own skin crosses that sphere - low over the shoulders, high at the nape, and in front
it is the beard's own outline, where the relief stands proud of the sphere. Under the beard the
coat is filled out to the sphere inside `BEARD_AZ`, which is the bib the beard rests on.

Below `Z_BEARD_BOT` nothing turns and the coat keeps its skin; that part of the coat is outside
the ball, so it is the one thing the sphere does not protect, and it is the nod - not the pan -
that would run into it. The coat stays whole; the unit's bottom rim is trimmed instead, to what
stays above `Z_BEARD_BOT` at every nod in `NOD_RANGE`, and `sweep()` proves it.
"""
import json
import math
import sys
import time
from pathlib import Path

import numpy as np
import trimesh
from scipy.ndimage import binary_dilation, distance_transform_edt, label
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
MARGIN = 0.2                 # how far under nominal a folded patch is cut back to; `keep_out`
GRID = 0.7                   # the grid that cut-back surface is found on
CELL = 6.0                   # thin patches within this of each other share one region


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

# A cell's eight corners, c = x + 2y + 4z, and the six tetrahedra it is cut into. Every cell is
# cut the same way, along the same body diagonal 0-7, so two cells that share a face cut that
# face along the same diagonal and the two halves of the surface meet. That is the whole reason
# for tetrahedra: marching cubes' 256-case table is ambiguous on a face and leaves a hole where
# neighbours resolve it differently, and a dual contour leaves four faces on an edge wherever
# the surface crosses one grid face twice. manifold3d takes neither - it wants a closed volume.
CORNER = np.array([(c & 1, (c >> 1) & 1, (c >> 2) & 1) for c in range(8)])
TETS = ((0, 1, 3, 7), (0, 1, 5, 7), (0, 2, 3, 7), (0, 2, 6, 7), (0, 4, 5, 7), (0, 4, 6, 7))
TET_EDGES = ((0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3))
# Which of a tetrahedron's six edges the surface crosses, by which of its corners are inside.
# One triangle when a single corner is cut off, two when the tetrahedron is cut in half.
TET_TRI = {1: ((0, 1, 2),), 14: ((0, 1, 2),), 2: ((0, 3, 4),), 13: ((0, 3, 4),),
           4: ((1, 3, 5),), 11: ((1, 3, 5),), 8: ((2, 4, 5),), 7: ((2, 4, 5),),
           3: ((1, 2, 4), (1, 4, 3)), 12: ((1, 2, 4), (1, 4, 3)),
           5: ((0, 2, 5), (0, 5, 3)), 10: ((0, 2, 5), (0, 5, 3)),
           9: ((0, 1, 5), (0, 5, 4)), 6: ((0, 1, 5), (0, 5, 4))}
# Every edge of every tetrahedron runs from its lower-numbered corner to its higher-numbered
# one, and the step between them is one of these seven. An edge is then named by the grid node
# it starts at and which step it takes, which is the same name in both cells that share it.
STEPS = np.array([(1, 0, 0), (0, 1, 0), (0, 0, 1), (1, 1, 0), (1, 0, 1), (0, 1, 1), (1, 1, 1)])


def _wound():
    """The same triangles, turned to face f > 0. There is no networkx in the build venv and so
    no `fix_normals`; but a triangle's side is settled by which corners of its tetrahedron are
    inside, not by where on the edges it ended up, so it can be decided once, here."""
    out = {}
    for t, tet in enumerate(TETS):
        for key, tris in TET_TRI.items():
            away = (CORNER[tet[next(p for p in range(4) if not key >> p & 1)]]
                    - CORNER[tet[next(p for p in range(4) if key >> p & 1)]])
            turned = []
            for tri in tris:
                m = [(CORNER[tet[TET_EDGES[k][0]]] + CORNER[tet[TET_EDGES[k][1]]]) / 2.0
                     for k in tri]
                turned.append(tri if np.cross(m[1] - m[0], m[2] - m[0]) @ away > 0 else tri[::-1])
            out[t, key] = turned
    return out


WOUND = _wound()


def marching_tets(f, origin, h):
    """A watertight mesh of the surface f = 0 in a sampled field, or None if it has none."""
    shape = np.array(f.shape)
    cells = shape - 1
    ins = (f < 0.0).astype(np.int8)
    corners = [ins[tuple(slice(o, o + n) for o, n in zip(CORNER[c], cells))] for c in range(8)]
    live = np.flatnonzero((sum(corners).ravel() % 8) != 0)          # 0 or 8 means no crossing
    if not len(live):
        return None
    vals = [f[tuple(slice(o, o + n) for o, n in zip(CORNER[c], cells))].ravel()[live]
            for c in range(8)]
    sign = [v < 0.0 for v in vals]
    node = np.ravel_multi_index(np.unravel_index(live, tuple(cells)), tuple(shape))
    stride = np.array([shape[1] * shape[2], shape[2], 1])
    faces = []
    for t, tet in enumerate(TETS):
        code = sum(int(1 << i) * sign[c] for i, c in enumerate(tet))
        for key in TET_TRI:
            tris = WOUND[t, key]
            sel = np.flatnonzero(code == key)
            if not len(sel):
                continue
            eid = {}
            for k in set(i for tri in tris for i in tri):
                ca, cb = (tet[TET_EDGES[k][0]], tet[TET_EDGES[k][1]])
                first, second = (ca, cb) if ca < cb else (cb, ca)
                fam = int(np.flatnonzero(
                    (STEPS == CORNER[second] - CORNER[first]).all(axis=1))[0])
                eid[k] = (node[sel] + CORNER[first] @ stride) * 7 + fam
            for tri in tris:
                faces.append(np.stack([eid[i] for i in tri], axis=1))
    if not faces:
        return None
    faces = np.vstack(faces)
    uid, inv = np.unique(faces.ravel(), return_inverse=True)
    start, fam = uid // 7, uid % 7
    end = start + STEPS[fam] @ stride
    flat = f.ravel()
    a, b = flat[start], flat[end]
    den = np.where(np.abs(a - b) > 1e-12, a - b, 1.0)
    along = np.clip(np.where(np.abs(a - b) > 1e-12, a / den, 0.5), 0.0, 1.0)
    p = (np.stack(np.unravel_index(start, tuple(shape)), axis=1).astype(float)
         + along[:, None] * STEPS[fam])
    return trimesh.Trimesh(vertices=origin + h * p, faces=inv.reshape(faces.shape), process=False)


def keep_out(skin, cavity, cut, what):
    """Everything within `cut` of the skin, wherever this void comes closer than that.

    SOLIDIFY offsets each vertex of the skin along its normal, which is an offset surface and
    not an offset solid. Wherever the skin has a ridge thinner than twice the offset - the fold
    of the skirt over the boots, the parting between two strands of the beard - that surface runs
    through itself, and the difference that makes the void then reaches into the ridge as a thin
    spike. The measured wall there was nothing at all in places: a pinhole, at a 0.6 mm nozzle,
    in the two parts of the statue a hand goes to first.

    The honest inward offset is the erosion of the solid by a ball of the offset's radius, which
    simply loses a ridge too thin to hold one, and that is what this builds - but only around the
    patches that need it, because the erosion of a 700 mm figure on a grid fine enough to see a
    beard is fifty million cells. The thin patches are found by measuring, grouped into regions,
    and inside each region the distance to the skin is sampled on a GRID mm lattice and its `cut`
    contour meshed. What comes back is subtracted from the void, so the void keeps its own
    surface everywhere it was already deep enough and the spikes are cut off flush.

    Both voids come through here, each with its own `cut`, one MARGIN under what it is nominally
    offset by. Cutting at the floor instead would leave a repaired patch sitting exactly on the
    floor; cutting just under nominal leaves it indistinguishable from the rest and puts the
    lattice's own error inside the margin. Neither cut is ever deeper than its own offset, so
    `cavity_grown` still contains `cavity` and nothing the mechanism is fitted to moves.
    """
    t0 = time.time()
    probe, _ = trimesh.sample.sample_surface_even(cavity, 150000, seed=3)
    probe = np.vstack([probe, np.asarray(cavity.vertices)])
    _, d, _ = trimesh.proximity.closest_point(skin, probe)
    seed = probe[d < cut]
    if not len(seed):
        print(f"statue keep-out  {what}: nothing closer to the skin than {cut:.1f} mm")
        return []
    cell = np.floor(seed / CELL).astype(int)
    base = cell.min(axis=0) - 1
    grid = np.zeros(cell.max(axis=0) + 2 - base, bool)
    grid[tuple((cell - base).T)] = True
    grid = binary_dilation(grid, np.ones((3, 3, 3), bool))       # a cell of margin all round
    lab, n = label(grid)
    tri = skin.triangles
    tlo, thi = tri.min(axis=1), tri.max(axis=1)
    parts, exact = [], 0
    for i in range(1, n + 1):
        idx = np.argwhere(lab == i)
        lo = (idx.min(axis=0) + base) * CELL - 2 * GRID
        hi = (idx.max(axis=0) + 1 + base) * CELL + 2 * GRID
        near = np.flatnonzero(np.all((thi > lo - 4.0) & (tlo < hi + 4.0), axis=1))
        if not len(near):
            continue
        sub = skin.submesh([near], append=True, repair=False)
        shape = np.ceil((hi - lo) / GRID).astype(int) + 1
        # Which nodes are near enough to the skin to be worth an exact distance: the skin is
        # scattered into the lattice and the lattice's distance to those cells is the estimate.
        spray, _ = trimesh.sample.sample_surface(sub, max(1000, int(8 * sub.area / GRID**2)),
                                                 seed=5)
        occ = np.ones(tuple(shape), bool)
        occ[tuple(np.clip(np.rint((spray - lo) / GRID).astype(int), 0, shape - 1).T)] = False
        rough = distance_transform_edt(occ) * GRID
        f = rough - cut
        band = np.abs(f) < 1.2 + GRID                 # everything the contour could run through
        band[0], band[-1], band[:, 0], band[:, -1], band[:, :, 0], band[:, :, -1] = (False,) * 6
        at = np.argwhere(band)
        if len(at):
            _, ex, _ = trimesh.proximity.closest_point(sub, lo + GRID * at)
            f[tuple(at.T)] = ex - cut
            exact += len(at)
        f[0], f[-1], f[:, 0], f[:, -1], f[:, :, 0], f[:, :, -1] = (1e3,) * 6
        m = marching_tets(f, lo, GRID)
        if m is None or not len(m.faces):
            continue
        if not (m.is_watertight and m.is_winding_consistent and m.volume > 0):
            raise RuntimeError(f"keep-out region {i} is not a solid (watertight "
                               f"{m.is_watertight}, winding {m.is_winding_consistent}, "
                               f"volume {m.volume:.1f}); the contour ran off the lattice "
                               f"between {lo} and {hi}")
        parts.append(m)
    print(f"statue keep-out  {what}: {len(seed)} of {len(probe)} probes under "
          f"{cut:.1f} mm, "
          f"{len(parts)} regions, {sum(len(p.faces) for p in parts)} faces, "
          f"{sum(p.volume for p in parts) / 1000:.1f} cm3, {exact} exact distances, "
          f"{time.time() - t0:.0f} s")
    return parts


def hollow():
    """shell.stl, cavity.stl, cavity_grown.stl. Blender walls; manifold takes the difference.

    Both voids then have their folds cut back by `keep_out`, each to its own offset: the cavity
    so the wall is nowhere thinner than `WALL_MIN`, and `cavity_grown` so that a boss on a part
    clipped to it cannot come out through the skin - it is only 1.2 mm inside to begin with, and
    in the folds it reached the skin exactly. The shell is then taken from the cavity rather than
    from Blender's wall solid, so that the two are each other's complement in the skin to the
    last facet: the sections are cut from the shell and every part is fitted to the cavity, and a
    wall the two disagreed about would be a wall nothing had checked.
    """
    from build import blender
    raw = [OUT / "wall_full.stl", OUT / "wall_thin.stl"]
    blender("statue_hollow.py", wants=raw)
    skin = trimesh.load(OUT / "outer.stl")
    out = {}
    for void_name, wall_file, t in (("cavity", raw[0], P.WALL), ("cavity_grown", raw[1], P.WALL - GROW)):
        w = trimesh.load(wall_file)
        if not w.is_watertight:
            raise RuntimeError(f"{wall_file.name} is not watertight; SOLIDIFY folded somewhere")
        void = trimesh.boolean.boolean_manifold([skin, w], "difference")
        blanks = keep_out(skin, void, t - MARGIN, void_name)
        if blanks:
            void = trimesh.boolean.boolean_manifold([void] + blanks, "difference")
        out[void_name] = write(void, OUT / f"{void_name}.stl", f"{t} mm inside the skin")
    shell = trimesh.boolean.boolean_manifold([skin, out["cavity"]], "difference")
    out["shell"] = write(shell, OUT / "shell.stl",
                         f"wall {P.WALL} mm, {shell.volume * 1.27e-3:.0f} g of PETG")
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
    prof, _, _ = profile(skin, cavity)
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
        "profile_step": [PROF_Z[2], 360.0 / PROF_AZ],
        "profile_band": [PROF_Z[0], PROF_Z[1]],
        "parting": {"z_nod": P.Z_NOD, "r": P.NECK_SPHERE_R, "z_collar": P.Z_COLLAR,
                    "z_beard_bottom": P.Z_BEARD_BOT},
    }
    doc.update(prof)
    (OUT / "features.json").write_text(json.dumps(doc, indent=1))
    print(f"statue features  {len(doc['reach'])} reach rows, "
          f"{len(doc['profile_outer'])} x {PROF_AZ} profile rows, legs {doc['legs']}")
    return doc


# --- the sections ---------------------------------------------------------------------------

def ball(r, sub=5):
    """A sphere about C = (0, 0, Z_NOD). Its facets are 0.05 mm inside the true sphere at r 100,
    which is inside TURN_GAP and on the safe side for the coat and the unsafe side for the
    turning unit by the same 0.05 mm - a fortieth of the gap."""
    m = trimesh.creation.icosphere(subdivisions=sub, radius=r)
    m.apply_translation((0.0, 0.0, P.Z_NOD))
    return m


def wedge(half, z0, z1, r=FAR):
    """The solid |azimuth| <= half, as a prism. A sector is star-shaped about the axis, so the
    fan of triangles from it tiles the face whatever the angle; shapely is not in this venv."""
    n = max(12, int(half))
    a = np.radians(np.linspace(-half, half, n + 1))
    p2 = np.vstack([[0.0, 0.0], np.column_stack([r * np.cos(a), r * np.sin(a)])])
    m = len(p2)
    v = np.vstack([np.column_stack([p2, np.full(m, z0)]),
                   np.column_stack([p2, np.full(m, z1)])])
    f = [[0, i, i + 1] for i in range(1, m - 1)] + [[m, m + i + 1, m + i] for i in range(1, m - 1)]
    for i in range(m):
        j = (i + 1) % m
        f += [[i, m + i, m + j], [i, m + j, j]]
    out = trimesh.Trimesh(vertices=v, faces=np.array(f), process=True)
    out.fix_normals()
    return out


def rays(mesh, zs, naz=72):
    """The outermost crossing of `mesh` in each of `naz` directions from the axis, at each z.

    One `mesh_multiplane` for the whole stack and then plain 2D line-line algebra, which is what
    makes a 72 x 61 table of a 200 000-triangle solid a second's work rather than a minute's.
    A section may be empty (above the statue, below the floor); that row comes back zeros.
    """
    lines, _, _ = trimesh.intersections.mesh_multiplane(
        mesh, np.zeros(3), np.array([0.0, 0.0, 1.0]), np.asarray(zs, float))
    out = np.zeros((len(zs), naz))
    ang = np.radians(np.arange(naz) * (360.0 / naz))
    d = np.stack([np.cos(ang), np.sin(ang)], axis=1)
    for k, segs in enumerate(lines):
        if not len(segs):
            continue
        segs = np.asarray(segs)
        a, e = segs[:, 0], segs[:, 1] - segs[:, 0]
        den = d[:, None, 0] * e[None, :, 1] - d[:, None, 1] * e[None, :, 0]
        ok = np.abs(den) > 1e-12
        q = np.where(ok, den, 1.0)
        t = (a[None, :, 0] * e[None, :, 1] - a[None, :, 1] * e[None, :, 0]) / q
        u = (a[None, :, 0] * d[:, None, 1] - a[None, :, 1] * d[:, None, 0]) / q
        keep = ok & (t > 1e-9) & (u >= 0.0) & (u <= 1.0)
        r = np.where(keep, t, -np.inf).max(axis=1)
        out[k] = np.where(np.isfinite(r), r, 0.0)
    return out


PROF_Z = (300.0, 420.0, 2.0)     # the profile's band and step; the parting lives inside it
PROF_AZ = 72                     # every 5 degrees, az 0 = +x = the front, counterclockwise


def profile(skin, cavity):
    """The skin's and the cavity's outer radius, every 5 degrees, every 2 mm through the parting.

    `reach` answers the mechanism's question - how far out may a part go before it hits a wall -
    in five directions. This answers the parting's question, which is the opposite one and needs
    every direction: how far out does the statue itself stand, so that a sphere about C can be
    put between the coat and the beard. Rows are keyed by z, columns run az 0, 5, ... 355.
    """
    zs = np.arange(PROF_Z[0], PROF_Z[1] + 1e-9, PROF_Z[2])
    out = {}
    for name, mesh in (("profile_outer", skin), ("profile_cavity", cavity)):
        tab = rays(mesh, zs, PROF_AZ)
        out[name] = {str(int(round(z))): [round(float(x), 1) for x in row]
                     for z, row in zip(zs, tab)}
    return out, zs, rays(skin, zs, PROF_AZ)


def collar_height(skin):
    """Where the sphere leaves the skin at the nape: the parting's highest point, measured.

    Z_COLLAR is not a choice - it is this number - and the stage refuses to go on if the sculpt
    or the sphere has moved it, because every section's z bounds are cut from it.
    """
    zs = np.arange(380.0, 425.0, 1.0)
    r = rays(skin, zs, 72)[:, 36]                       # az 180, the back
    d = np.hypot(r, zs - P.Z_NOD)
    over = np.flatnonzero(d >= P.NECK_SPHERE_R)
    if not len(over):
        raise RuntimeError("the sphere never leaves the skin at the nape; NECK_SPHERE_R is too big")
    return float(zs[over[0]])


RIM_STEP = 0.5                   # the rim's grid about C, in degrees of azimuth and of polar angle
RIM_BLUR = 1.5                   # mm over which the rim's cut is feathered into the grid


def polar(mesh, thetas, phi, reach):
    """Every crossing of `mesh` along the rays from C at polar angles `thetas` in the vertical
    half-plane at azimuth `phi`, and each ray point's in-plane distance to the section at `reach`.

    One `mesh_plane` per azimuth and then 2D algebra, as `rays` does horizontally; a ray from C
    stays in its own vertical plane, so this is exact for the direction and only the distance
    (the thickness) is the in-plane one - never less than the true one.
    """
    a = math.radians(phi)
    segs = trimesh.intersections.mesh_plane(mesh, (-math.sin(a), math.cos(a), 0.0),
                                            (0.0, 0.0, P.Z_NOD))
    segs = np.asarray(segs)
    if not len(segs):
        return [np.zeros(0)] * len(thetas), np.full(len(thetas), np.inf)
    rho = segs[..., 0] * math.cos(a) + segs[..., 1] * math.sin(a)
    q = np.stack([rho, segs[..., 2] - P.Z_NOD], axis=-1)            # (k, 2, 2) in (rho, h)
    th = np.radians(thetas)
    d = np.stack([np.sin(th), np.cos(th)], axis=1)
    s0, e = q[:, 0], q[:, 1] - q[:, 0]
    den = d[:, None, 0] * e[None, :, 1] - d[:, None, 1] * e[None, :, 0]
    ok = np.abs(den) > 1e-12
    w = np.where(ok, den, 1.0)
    t = (s0[None, :, 0] * e[None, :, 1] - s0[None, :, 1] * e[None, :, 0]) / w
    u = (s0[None, :, 0] * d[:, None, 1] - s0[None, :, 1] * d[:, None, 0]) / w
    hit = ok & (t > 1e-9) & (u >= 0.0) & (u <= 1.0)
    out = [np.sort(t[i][hit[i]]) for i in range(len(th))]
    pt = d * reach
    ll = np.maximum(np.einsum("ij,ij->i", e, e), 1e-12)
    f = np.clip(np.einsum("tkj,kj->tk", pt[:, None, :] - s0[None], e) / ll, 0.0, 1.0)
    foot = s0[None] + f[..., None] * e[None]
    near = np.linalg.norm(pt[:, None, :] - foot, axis=2).min(axis=1)
    return out, near


def star(radius, thetas, phis):
    """A closed star-shaped solid about C: `radius[i, j]` along azimuth phis[i], polar thetas[j],
    a pole at radius[:, 0].mean() and a fan from the last ring down to C itself. Every such mesh
    is watertight by construction, whatever the radii, which is why the rim is built this way
    rather than by extruding a patch of faces."""
    c = np.array([0.0, 0.0, P.Z_NOD])
    ph, th = np.radians(phis), np.radians(thetas)
    dirs = np.stack([np.sin(th)[None, :] * np.cos(ph)[:, None],
                     np.sin(th)[None, :] * np.sin(ph)[:, None],
                     np.broadcast_to(np.cos(th)[None, :], (len(ph), len(th)))], axis=-1)
    v = c + dirs * radius[..., None]
    n_p, n_t = radius.shape
    verts = np.vstack([v.reshape(-1, 3), [c + (0, 0, radius[:, 0].mean())], [c]])
    top, bot = n_p * n_t, n_p * n_t + 1
    idx = lambda i, j: (i % n_p) * n_t + j
    f = []
    for i in range(n_p):
        f.append([top, idx(i, 0), idx(i + 1, 0)])
        for j in range(n_t - 1):
            f += [[idx(i, j), idx(i, j + 1), idx(i + 1, j + 1)], [idx(i, j), idx(i + 1, j + 1), idx(i + 1, j)]]
        f.append([idx(i, n_t - 1), bot, idx(i + 1, n_t - 1)])
    m = trimesh.Trimesh(vertices=verts, faces=np.array(f), process=False)
    if m.volume < 0:
        m.invert()
    return m


def rim(skin, cavity):
    """Where the unit leaves the sphere, and how its edge there is made printable.

    The sphere cuts the statue's skin at a shallow angle round the nape and behind the ears,
    and there the unit's edge came out as a feather - a skirt of skin thinner than any nozzle
    lays - and the hair strands the sphere crossed came out as loose tongues. On a grid about C
    every RIM_STEP degrees this finds, at radius R, the directions where the unit's material is
    thinner than WALL_MIN (the feather) or part of a region narrower than RIM_MIN_W across (the
    tongues), and cuts the unit back along those rays to just past the skin. What is left meets
    the sphere with at least WALL_MIN of wall, and that edge is then given a flange RIM_FLANGE_T
    thick lying on the sphere, RIM_FLANGE_W wide, turned inward over the cavity - so the edge
    prints as a border and not a knife, and water running off the hair leaves at the outside.

    Returns the cutter (a star about C, radius R except along the cut rays) and the flange.
    """
    r = P.NECK_SPHERE_R
    thetas = np.arange(RIM_STEP, math.degrees(math.acos((P.Z_BEARD_BOT - 4.0 - P.Z_NOD) / r)), RIM_STEP)
    phis = np.arange(0.0, 360.0, RIM_STEP)
    keep = lambda m: m.submesh([np.flatnonzero(np.linalg.norm(
        m.triangles_center - (0.0, 0.0, P.Z_NOD), axis=1) < r + 25.0)], append=True)
    sk, cv = keep(skin), keep(cavity)
    shape = (len(phis), len(thetas))
    ins, inc, exitr, thick = (np.zeros(shape, bool), np.zeros(shape, bool),
                              np.full(shape, np.inf), np.full(shape, np.inf))
    for i, ph in enumerate(phis):
        ts, near = polar(sk, thetas, ph, r)
        tc, _ = polar(cv, thetas, ph, r)
        for j in range(len(thetas)):
            ins[i, j] = (ts[j] < r).sum() % 2 == 0      # C is inside the skin and the cavity
            inc[i, j] = (tc[j] < r).sum() % 2 == 0      # both, so an even count is inside
            beyond = ts[j][ts[j] > r]
            exitr[i, j] = beyond[0] if len(beyond) else np.inf
        thick[i] = near
    z = P.Z_NOD + r * np.cos(np.radians(thetas))[None, :] * np.ones(shape)
    unit = ins & (z >= P.Z_BEARD_BOT)                  # the statue at radius R, above the bottom
    wall = unit & ~inc                                 # ... and there solid, not cavity
    thin = wall & (thick < P.WALL_MIN)
    ph, th = np.radians(phis), np.radians(thetas)
    pts = r * np.stack([np.sin(th)[None, :] * np.cos(ph)[:, None],
                        np.sin(th)[None, :] * np.sin(ph)[:, None],
                        np.broadcast_to(np.cos(th)[None, :], shape)], axis=-1).reshape(-1, 3)
    tree = cKDTree(pts)
    def grow(mask, rad):
        m = mask.ravel()
        hit = tree.query_ball_point(pts[m], rad, return_sorted=False)
        out = np.zeros(len(pts), bool)
        out[np.fromiter((k for h in hit for k in h), int)] = True
        return out.reshape(shape)
    half = P.RIM_MIN_W / 2
    opened = grow(~grow(~unit, half) & unit, half) & unit  # erode then dilate: an opening
    drop = (unit & ~opened) | thin
    # A cutter that jumps from R to past the skin between one grid point and the next leaves a
    # sawtooth at the grid's pitch along the edge. The mask is blurred over RIM_BLUR first, so the
    # cutter ramps across several points and the edge follows a smooth contour of it instead.
    near = tree.query_ball_point(pts, RIM_BLUR, return_sorted=False)
    wgt = drop.ravel().astype(float)
    for _ in range(2):
        wgt = np.array([wgt[h].mean() for h in near])
    wgt = np.clip(2.0 * wgt.reshape(shape), 0.0, 1.0)
    target = np.where(np.isfinite(exitr), exitr + 1.0, r + 15.0)
    cutr = r + wgt * (np.minimum(target, r + 15.0) - r)
    lip = grow(wall & ~drop, P.RIM_FLANGE_W) & unit & ~drop
    lipr = np.where(lip, r + P.RIM_FLANGE_T, r - 1.0)
    # the stars close with a fan from their last ring to C, so a ring that is not at R would
    # leave a sliver inside the ball: the last ring is under Z_BEARD_BOT anyway, and stays plain
    lipr[:, -1], cutr[:, -1] = r - 1.0, r
    print(f"statue rim      {thin.sum()} directions of feather under {P.WALL_MIN} mm and "
          f"{(unit & ~opened).sum()} of tongues under {P.RIM_MIN_W:.0f} mm cut back; "
          f"flange on {lip.sum()} ({P.RIM_FLANGE_W:.0f} x {P.RIM_FLANGE_T} mm), "
          f"grid {RIM_STEP:.0f} deg = {math.radians(RIM_STEP) * r:.1f} mm at R")
    return star(cutr, thetas, phis), star(lipr, thetas, phis), star(np.full(shape, r), thetas, phis)


def chamfer(r0, z0, deg, rim=300.0):
    """The solid under a cone about Z that runs down and out from (r0, z0) at `deg` below the
    horizontal - the coat's top edge, sloped down from the socket instead of stepped."""
    a = math.radians(deg)
    za = z0 - (rim - r0) * math.tan(a)
    prof = np.array([[0.0, -5.0], [rim, -5.0], [rim, za], [r0, z0], [0.0, z0]])
    m = trimesh.creation.revolve(prof, sections=256)
    if m.volume < 0:
        m.invert()
    return m


def parting(skin, cavity, shell):
    """Cut the statue into the fixed coat and the turning unit on the sphere about C.

    The coat is the skin clipped into the ball, with its cavity clipped one wall further in so
    the clipped face comes out as wall and not as a hole; under the beard the ball is filled in
    as well, so the beard rests on a smooth bib rather than on the relief it used to be part of.
    The turning unit is simply the shell outside the sphere, above the beard's bottom.

    The one plane left in the parting is that bottom: the sphere goes on down through the coat's
    belly, which has to stay, so the turning unit is cut off flat at `Z_BEARD_BOT` and the coat's
    own skin stops `TURN_GAP` under it. That plane is what the nod runs into.
    """
    zb, gap = P.Z_BEARD_BOT, P.TURN_GAP
    ro = P.NECK_SPHERE_R - gap                          # the coat may not pass this
    ri = ro - P.WALL                                    # the bib's inner face
    # The ball's own top is up inside the head, and `skin` is a solid, so the band under the
    # collar is cut off at the collar and the dome over it is added separately, as a shell.
    lid = P.Z_COLLAR - gap
    above = box((-FAR, -FAR, zb - gap), (FAR, FAR, lid))
    bib = wedge(P.BEARD_AZ, zb - gap, lid)
    bo, bi = ball(ro), ball(ri)
    # Below the seam the coat keeps its skin, but its top edge is sloped down from the socket at
    # SEAM_CHAMFER_DEG instead of stepping out to the skin: the step was a ledge up to 31 mm
    # wide that every pan uncovered. The unit never comes below Z_BEARD_BOT at any pan or nod,
    # so nothing here can reach it.
    z0 = zb - gap
    r0 = math.sqrt(ro ** 2 - (z0 - P.Z_NOD) ** 2)
    k_out = chamfer(r0, z0, P.SEAM_CHAMFER_DEG)
    k_in = chamfer(r0 - P.WALL / math.sin(math.radians(P.SEAM_CHAMFER_DEG)), z0, P.SEAM_CHAMFER_DEG)
    low = box((-FAR, -FAR, -1.0), (FAR, FAR, z0))
    o1 = trimesh.boolean.boolean_manifold(
        [trimesh.boolean.boolean_manifold([skin, low, k_out], "intersection"),
         trimesh.boolean.boolean_manifold([skin, above, bo], "intersection"),
         trimesh.boolean.boolean_manifold([bo, bib], "intersection")], "union")
    c1 = trimesh.boolean.boolean_manifold(
        [trimesh.boolean.boolean_manifold([cavity, low, k_in], "intersection"),
         trimesh.boolean.boolean_manifold([cavity, above, bi], "intersection"),
         trimesh.boolean.boolean_manifold([bi, bib], "intersection")], "union")
    fixed = trimesh.boolean.boolean_manifold([o1, c1], "difference")
    chamfered = trimesh.boolean.boolean_manifold([cut(shell, (-FAR, -FAR, -1.0), (FAR, FAR, z0)),
                                                  k_out], "difference").volume
    # The dome: the socket closed over the top, one wall thick on the sphere, bored on the axis
    # for the neck. A rim standing up round the bore was tried and cannot be had: the dome's
    # outside already is the ball, so anything raised on it is outside the ball, and the sweep
    # found a 3 mm dam 101.8 mm from C meeting the nape at pan -65, nose down 15. The bore's edge
    # is given a drip skirt instead, hanging NECK_DAM_H under the dome inside the ball, so what
    # does run in over the lip falls clear of the dome's underside rather than tracking along it.
    bore = P.NECK_BORE_R
    zc_out = P.Z_NOD + math.sqrt(ro ** 2 - bore ** 2)
    zs_out = P.Z_NOD + math.sqrt(ro ** 2 - (bore + P.WALL) ** 2)
    zc_in = P.Z_NOD + math.sqrt(ri ** 2 - (bore + P.WALL) ** 2)
    dome = trimesh.boolean.boolean_manifold(
        [trimesh.boolean.boolean_manifold([bo, bi], "difference"), skin,
         box((-FAR, -FAR, lid - 3.0), (FAR, FAR, FAR))], "intersection")
    dam = trimesh.boolean.boolean_manifold(
        [cylinder(bore + P.WALL, zc_in - P.NECK_DAM_H, zs_out),
         cylinder(bore, zc_in - P.NECK_DAM_H - 1.0, zs_out + 1.0)], "difference")
    fixed = trimesh.boolean.boolean_manifold([fixed, dome, dam], "union")
    fixed = trimesh.boolean.boolean_manifold([fixed, cylinder(bore, lid, FAR)], "difference")
    print(f"statue dome     socket closed to its crown: bore r {bore:.0f} (shroud {P.SHROUD_R_OUT:.0f} "
          f"+ 3) at z {zc_out:.1f}, drip skirt {P.NECK_DAM_H:.0f} mm under it to z "
          f"{zc_in - P.NECK_DAM_H:.1f}; seam chamfer {P.SEAM_CHAMFER_DEG:.0f} deg from r {r0:.1f} at z {z0:.0f}, "
          f"{chamfered / 1e3:.1f} cm3 off the coat's top edge")
    cutter, lip, sphere_r = rim(skin, cavity)
    unit = cut(shell, (-FAR, -FAR, zb), (FAR, FAR, P.Z_TOP + 1.0))
    plain = trimesh.boolean.boolean_manifold([unit, sphere_r], "difference")
    moving = trimesh.boolean.boolean_manifold([unit, cutter], "difference")
    lost = plain.volume - moving.volume
    band = trimesh.boolean.boolean_manifold([lip, sphere_r], "difference")
    if len(band.faces):
        flange = trimesh.boolean.boolean_manifold(
            [band, skin, box((-FAR, -FAR, zb), (FAR, FAR, FAR))], "intersection")
        # the two stars close on the same cone to C, and their difference leaves slivers along
        # it, inside the ball: a true ball takes them out, so the flange is outside R, full stop
        flange = trimesh.boolean.boolean_manifold([flange, ball(P.NECK_SPHERE_R)], "difference")
        moving = trimesh.boolean.boolean_manifold([moving, flange], "union")
    print(f"statue rim      {lost / 1e3:.1f} cm3 of feather and tongue off the unit's edge, "
          f"{(moving.volume - plain.volume + lost) / 1e3:.1f} cm3 of flange on")
    # The flat bottom is the one face of the unit that is not on the sphere, and the coat under
    # it is outside the ball, so a nod would drive it in. The coat is not cut; the unit keeps
    # only what stays above Z_BEARD_BOT at every nod in NOD_RANGE. Pan is about Z and leaves z
    # alone, so this one envelope covers every pan as well.
    whole = moving.volume
    nods = np.arange(P.NOD_RANGE[0], P.NOD_RANGE[1] + 1e-9, P.NOD_STEP)
    keep = [turned(box((-FAR, -FAR, zb), (FAR, FAR, FAR)), 0.0, -float(n)) for n in nods]
    moving = trimesh.boolean.boolean_manifold([moving] + keep, "intersection")
    print(f"statue nod trim  the unit's bottom rim cut to the envelope of nods "
          f"{P.NOD_RANGE[0]:+.0f}..{P.NOD_RANGE[1]:+.0f}: {(whole - moving.volume) / 1e3:.1f} cm3 off the beard")
    shaved = shell.volume - fixed.volume - moving.volume
    print(f"statue parting  sphere r {P.NECK_SPHERE_R:.0f} about (0, 0, {P.Z_NOD:.0f}); coat "
          f"<= r {ro:.0f}, turning unit >= r {P.NECK_SPHERE_R:.0f}\n"
          f"       fixed {fixed.volume / 1e3:.0f} cm3 ({fixed.body_count} body), turning "
          f"{moving.volume / 1e3:.0f} cm3 ({moving.body_count} body), "
          f"{-shaved / 1e3:+.1f} cm3 of new wall net (the socket and the bib, less the seam and the trim)")
    return fixed, moving


def turned(mesh, pan, nod):
    """`mesh` panned about Z and nodded about Y, both about C.

    `nod` is the firmware's sign: positive is nose up, which about +Y is a negative rotation,
    because the nose is on +X. Nod first: the two share a centre, so the order only decides
    whether the nod is in the head's frame or the world's, and the firmware nods the head after
    it has pointed it.
    """
    c = np.array([0.0, 0.0, P.Z_NOD])
    m = mesh.copy()
    m.apply_translation(-c)
    m.apply_transform(trimesh.transformations.rotation_matrix(math.radians(-nod), (0.0, 1.0, 0.0)))
    m.apply_transform(trimesh.transformations.rotation_matrix(math.radians(pan), (0.0, 0.0, 1.0)))
    m.apply_translation(c)
    return m


def overlap(moving, still, pan, nod):
    hit = trimesh.boolean.boolean_manifold([turned(moving, pan, nod), still], "intersection")
    return abs(hit.volume) if len(hit.faces) else 0.0


def sweep(moving, fixed):
    """Turn and tip the unit through its stops against the fixed shell and report what it touches.

    Pan every five degrees at nod 0, then the pan stops and the middle against every five
    degrees of NOD_RANGE, so a path through the coat between the ends is caught too. Anything
    above nothing is an overlap and the stage stops.
    """
    still = trimesh.boolean.boolean_manifold(list(fixed), "union")
    grid = {(float(p), 0.0): 0.0 for p in np.arange(-P.PAN_STOP_DEG, P.PAN_STOP_DEG + 1e-9, 5.0)}
    nods = sorted(set(np.arange(P.NOD_RANGE[0], P.NOD_RANGE[1] + 1e-9, 5.0)) | set(P.NOD_RANGE))
    for n in nods:
        for p in (-P.PAN_STOP_DEG, -30.0, 0.0, 30.0, P.PAN_STOP_DEG):
            grid[(float(p), float(n))] = 0.0
    for k in grid:
        grid[k] = overlap(moving, still, *k)
    worst = max(grid.items(), key=lambda t: t[1])
    print(f"statue sweep    {len(grid)} poses, pan +-{P.PAN_STOP_DEG:.0f} x nod "
          f"{P.NOD_RANGE[0]:+.0f}..{P.NOD_RANGE[1]:+.0f}: worst overlap {worst[1]:.1f} mm3 at "
          f"pan {worst[0][0]:+.0f} nod {worst[0][1]:+.0f}")
    # how the unit's lowest edges move at the ends of the nod
    v = np.asarray(moving.vertices)
    for sign, nod, what in ((1, P.NOD_RANGE[0], "beard's bottom edge"), (-1, P.NOD_RANGE[1], "back edge")):
        low = v[v[:, 2] < P.Z_BEARD_BOT + 30.0]
        p0 = low[np.argmax(sign * low[:, 0])]
        p1 = turned(trimesh.Trimesh(vertices=[p0], faces=np.zeros((0, 3), int), process=False),
                    0.0, nod).vertices[0]
        print(f"       nod {nod:+.0f}: the {what} at x {p0[0]:+.0f} z {p0[2]:.0f} moves "
              f"{p1[0] - p0[0]:+.1f} mm in x and {p1[2] - p0[2]:+.1f} mm in z, to z {p1[2]:.1f}")
    return worst[1]


def sections(fixed, moving):
    """Cut the fixed coat and the turning unit into the printable raw sections.

    Six pieces are fixed - the two base halves, the two mitten caps, the two sleeve panels - and
    the coat above the belt is one ring that now runs all the way to the collar, because above
    `Z_BEARD_BOT` the coat is inside the ball and never reaches `PANEL_Y` again. Three turn: the
    beard with the collar ring it hangs from, the head, and the hat.
    """
    RAW.mkdir(parents=True, exist_ok=True)
    py, pb, pt = P.PANEL_Y, P.PANEL_BOTTOM, P.PANEL_TOP
    top = P.SECTIONS_STATUE["torso"][1]
    chin = P.SECTIONS_STATUE["beard"][1]
    sides = {
        "panel_left":  ((-FAR, py, P.Z_BELT), (FAR, FAR, pt)),
        "panel_right": ((-FAR, -FAR, P.Z_BELT), (FAR, -py, pt)),
        "hand_left":   ((-FAR, py, pb), (FAR, FAR, P.Z_BELT)),
        "hand_right":  ((-FAR, -FAR, pb), (FAR, -py, P.Z_BELT)),
    }
    out = {name: cut(fixed, lo, hi) for name, (lo, hi) in sides.items()}
    below = cut(fixed, (-FAR, -FAR, -1.0), (FAR, FAR, P.Z_BELT))
    for name in ("hand_left", "hand_right"):
        below = trimesh.boolean.boolean_manifold([below, out[name]], "difference")
    out["base_left"] = cut(below, (-FAR, KERF / 2, -1.0), (FAR, FAR, P.Z_BELT))
    out["base_right"] = cut(below, (-FAR, -FAR, -1.0), (FAR, -KERF / 2, P.Z_BELT))
    # the ring's own region, not the coat less the panels: subtracting the panel meshes left
    # slivers along the chamfer's faces, which coincide with theirs
    region = trimesh.boolean.boolean_manifold(
        [box((-FAR, -py, P.Z_BELT), (FAR, py, pt)), box((-FAR, -FAR, pt), (FAR, FAR, top))], "union")
    out["torso"] = trimesh.boolean.boolean_manifold([fixed, region], "intersection")
    for name, (lo, hi) in {"beard": (P.Z_BEARD_BOT - 1.0, chin), "head": (chin, P.Z_HAT),
                           "hat": (P.Z_HAT, P.Z_TOP + 1.0)}.items():
        out[name] = cut(moving, (-FAR, -FAR, lo), (FAR, FAR, hi))
    glue = cut(moving, (-FAR, -FAR, chin - 0.5), (FAR, FAR, chin + 0.5)).volume
    print(f"statue glue     the beard meets the head at z {chin:.0f} over "
          f"{glue:.0f} mm2 of face (a 1 mm slice of the unit, by volume)")
    total = 0.0
    for name in P.SECTIONS_STATUE:
        back = write(out[name], RAW / f"{name}.stl", quiet=True)
        out[name] = back
        total += back.volume
        if max(back.extents) > P.BED:
            raise RuntimeError(f"{name} is {max(back.extents):.1f} mm across; the bed is {P.BED}")
    kerf = cut(fixed, (-FAR, -KERF / 2, -1.0), (FAR, KERF / 2, P.Z_BELT)).volume
    want = fixed.volume + moving.volume - kerf
    err = (total - want) / want
    print(f"statue sections  {total / 1e3:.1f} cm3 against the coat's {fixed.volume / 1e3:.1f} "
          f"and the unit's {moving.volume / 1e3:.1f} less the y-kerf ({kerf / 1e3:.1f}): "
          f"{err * 100:+.2f} %")
    if abs(err) > 0.01:
        raise RuntimeError(f"the sections and the parting disagree by {err * 100:.2f} %")
    return out


def preview():
    from build import blender
    blender("statue_preview.py", fresh_in=(OUT, "preview_*.png"))


def main():
    skin = outer()
    cavity, grown, shell = hollow()
    features(skin, cavity, shell)
    measured_collar = collar_height(skin)
    if abs(measured_collar - P.Z_COLLAR) > 1.5:
        raise RuntimeError(f"the sphere leaves the skin at the nape at z {measured_collar:.1f}, "
                           f"not Z_COLLAR {P.Z_COLLAR}; set Z_COLLAR to that and rebuild")
    print(f"statue collar   the sphere leaves the nape at z {measured_collar:.1f} "
          f"(Z_COLLAR {P.Z_COLLAR})")
    fixed, moving = parting(skin, cavity, shell)
    out = sections(fixed, moving)
    worst = sweep(moving, [out[n] for n in ("torso", "panel_left", "panel_right",
                                            "hand_left", "hand_right",
                                            "base_left", "base_right")])
    if worst > 0.0:
        raise SystemExit(f"the turning unit fouls the fixed coat by {worst:.1f} mm3 inside "
                         f"pan +-{P.PAN_STOP_DEG:.0f} and nod {P.NOD_RANGE}")
    preview()


if __name__ == "__main__":
    main()
