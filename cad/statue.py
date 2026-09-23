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


# --- the frame ------------------------------------------------------------------------------

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
    sym.merge_vertices()
    OUT.mkdir(parents=True, exist_ok=True)
    sym.export(OUT / "outer.stl")
    b = sym.bounds
    print(f"statue outer  {len(sym.faces)} faces  watertight={sym.is_watertight}  "
          f"volume={sym.volume / 1e6:.2f} L  bounds x{b[0][0]:.0f}..{b[1][0]:.0f} "
          f"y{b[0][1]:.0f}..{b[1][1]:.0f} z{b[0][2]:.0f}..{b[1][2]:.0f}")
    return sym


# --- hollow ---------------------------------------------------------------------------------

def hollow():
    """shell.stl, cavity.stl, cavity_grown.stl. Blender walls; manifold takes the difference."""
    from build import blender
    blender("statue_hollow.py", wants=[OUT / "shell.stl", OUT / "wall_thin.stl"])
    skin = trimesh.load(OUT / "outer.stl")
    out = {}
    for name, wall in (("cavity", "shell"), ("cavity_grown", "wall_thin")):
        w = trimesh.load(OUT / f"{wall}.stl")
        if not w.is_watertight:
            raise RuntimeError(f"{wall}.stl is not watertight; SOLIDIFY folded somewhere")
        void = trimesh.boolean.boolean_manifold([skin, w], "difference")
        void.export(OUT / f"{name}.stl")
        out[name] = void
        print(f"statue {name:13s} {len(void.faces)} faces  watertight={void.is_watertight}  "
              f"volume={void.volume / 1e6:.2f} L")
        if name == "cavity":
            print(f"statue shell        {len(w.faces)} faces  volume={w.volume / 1e6:.2f} L  "
                  f"({w.volume * 1.24e-3:.0f} g of PLA at 1.24 g/cm3)")
    return out["cavity"], out["cavity_grown"]


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


def reach(cavity):
    """How far the cavity reaches from the pan axis, every STEP mm: min, front, back, left, right.

    The fit report's T8 in table form. Distance from the axis to the first wall in each of 72
    directions; where the axis is not inside the cavity at all - up in the hat, where the skin
    closes in - the row is all zeros and the layout tests know to stay out.
    """
    table = {}
    zlo, zhi = cavity.bounds[0][2], cavity.bounds[1][2]
    for z in np.arange(math.ceil(zlo / STEP) * STEP, zhi, STEP):
        segs = segments_at(cavity, z)
        if not len(segs):
            continue
        rs = np.zeros(72)
        if cavity.contains([[0.0, 0.0, float(z)]])[0]:
            for i in range(72):
                a = math.radians(i * 5)
                t = hits(segs, (0.0, 0.0), (math.cos(a), math.sin(a)))
                rs[i] = t[0] if len(t) else 0.0
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
                            if (y >= 0) == (sign > 0) and len(hits(segs, (x, y), (1.0, 0.0))) % 2])
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


def features(skin, cavity):
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
        "reach": reach(cavity),
        "legs_z": Z_LEGS,
        "legs": legs(cavity),
    }
    (OUT / "features.json").write_text(json.dumps(doc, indent=1))
    print(f"statue features  {len(doc['reach'])} reach rows, legs {doc['legs']}")
    return doc


# --- the sections ---------------------------------------------------------------------------

def tidy(mesh, name):
    """Drop the crumbs a cut leaves and pull apart pinched vertices before writing the file.

    Both are the same lessons the assembler learned. A plane grazing a 200 000-triangle skin
    leaves closed surfaces with no volume behind them, which are watertight in memory and not
    watertight once an STL has merged their coincident vertices; and manifold3d may leave two
    vertices in one place, which an STL cannot tell apart either. A crumb here is anything under
    a cubic centimetre - the smallest real section is a hand, at fifty.
    """
    parts = mesh.split(only_watertight=False)
    dropped = 0
    if len(parts) > 1:
        solid = [c for c in parts if abs(c.volume) > 1000.0]
        dropped = len(parts) - len(solid)
        if dropped:
            mesh = solid[0] if len(solid) == 1 else trimesh.util.concatenate(solid)
    v = np.asarray(mesh.vertices)
    pairs = cKDTree(v).query_pairs(2e-4, output_type="ndarray")
    pinches = 0
    if len(pairs):
        mesh = mesh.copy()
        idx = np.unique(pairs[:, 0])
        # A vertex of a degenerate triangle has no normal, and numpy hands back NaN rather than
        # saying so. Exported, a NaN vertex takes its faces with it - the base lost the 10 mm
        # under its rim that way, silently - so the ones without a direction stay where they are.
        n = np.nan_to_num(np.asarray(mesh.vertex_normals)[idx], nan=0.0, posinf=0.0, neginf=0.0)
        mesh.vertices[idx] = mesh.vertices[idx] + n * 2e-3
        pinches = int((np.linalg.norm(n, axis=1) > 0).sum())
    return mesh, dropped, pinches


def sections(shell):
    """Cut the shell into the printable raw sections.

    The bell - everything above Z_TURN - turns on the shroud, so it takes the sculpted skin with
    it and the coat below keeps a flat rim TURN_GAP under the seam. The hands come off as two
    caps, because with them the coat is 276 mm across and the bed is 256.
    """
    RAW.mkdir(parents=True, exist_ok=True)
    hx, hy, hz = HAND["x"], HAND["y"], HAND["z"]
    hands = {
        "hand_left": ((hx[0], hy, hz[0]), (hx[1], FAR, hz[1])),
        "hand_right": ((hx[0], -FAR, hz[0]), (hx[1], -hy, hz[1])),
    }
    out = {}
    for name, (lo, hi) in hands.items():
        out[name] = cut(shell, lo, hi)
    body = shell
    for name in hands:
        body = trimesh.boolean.boolean_manifold([body, out[name]], "difference")
    top = P.Z_TURN - P.TURN_GAP           # the coat stops TURN_GAP under the bell's skirt
    chin = P.SECTIONS_STATUE["beard"][1]  # where the bell is split for the bed, at the chin
    plan = {
        "base_left":  ((-FAR, KERF / 2, -1.0), (FAR, FAR, P.Z_BELT)),
        "base_right": ((-FAR, -FAR, -1.0), (FAR, -KERF / 2, P.Z_BELT)),
        "torso":      ((-FAR, -FAR, P.Z_BELT), (FAR, FAR, top)),
        "beard":      ((-FAR, -FAR, P.Z_TURN), (FAR, FAR, chin)),
        "head":       ((-FAR, -FAR, chin), (FAR, FAR, P.Z_HAT)),
        "hat":        ((-FAR, -FAR, P.Z_HAT), (FAR, FAR, P.Z_TOP + 1.0)),
    }
    for name, (lo, hi) in plan.items():
        out[name] = cut(body, lo, hi)
    total = 0.0
    print(f"{'section':12s} {'faces':>7s} {'volume cm3':>11s} {'bbox x':>8s} {'y':>7s} {'z':>7s}  bodies")
    for name in ("base_left", "base_right", "torso", "hand_left", "hand_right", "beard", "head", "hat"):
        m, dropped, pinches = tidy(out[name], name)
        m.merge_vertices()
        m.export(RAW / f"{name}.stl")
        out[name] = m
        back = trimesh.load(RAW / f"{name}.stl")
        e = back.extents
        n = back.split(only_watertight=False)
        total += back.volume
        flag = "" if (back.is_watertight and back.is_winding_consistent and max(e) <= P.BED) else "   <-- CHECK"
        note = "".join([f"  {dropped} crumbs" if dropped else "", f"  {pinches} pinches" if pinches else ""])
        print(f"{name:12s} {len(back.faces):7d} {back.volume / 1e3:11.1f} "
              f"{e[0]:8.1f} {e[1]:7.1f} {e[2]:7.1f}  {len(n)}{flag}{note}")
        if not back.is_watertight:
            raise RuntimeError(f"{name} is not watertight after the round trip")
        if abs(back.volume - m.volume) > 0.001 * abs(m.volume) or \
                np.abs(back.bounds - m.bounds).max() > 0.01:
            raise RuntimeError(f"{name} changed on its way through the STL: "
                               f"{m.volume / 1e3:.1f} -> {back.volume / 1e3:.1f} cm3")
        if max(e) > P.BED:
            raise RuntimeError(f"{name} is {max(e):.1f} mm across; the bed is {P.BED}")
    # what the cuts threw away: the kerf between the base halves and the turning seam
    waste = 0.0
    for lo, hi in ((( -FAR, -KERF / 2, -1.0), (FAR, KERF / 2, P.Z_BELT)),
                   ((-FAR, -FAR, top), (FAR, FAR, P.Z_TURN))):
        waste += cut(shell, lo, hi).volume
    err = (total + waste - shell.volume) / shell.volume
    print(f"statue sections  {total / 1e3:.0f} cm3 + {waste / 1e3:.1f} cm3 of kerf "
          f"vs the shell's {shell.volume / 1e3:.0f} cm3: {err * 100:+.2f} %")
    if abs(err) > 0.01:
        raise RuntimeError(f"the sections and the shell disagree by {err * 100:.2f} %")
    return out


def preview():
    from build import blender
    blender("statue_preview.py", fresh_in=(OUT, "preview_*.png"))


def main():
    skin = outer()
    cavity, grown = hollow()
    shell = trimesh.load(OUT / "shell.stl")
    features(skin, cavity)
    sections(shell)
    preview()


if __name__ == "__main__":
    main()
