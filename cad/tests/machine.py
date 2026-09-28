"""The whole machine as meshes, posable: what the pose sweep and the assembly sweeps test against.

Mechanism parts come from out/stl through out/placements.json (both written by the build), so
this is the same geometry the printer gets; the bought parts are drawn here from mech/, as
envelopes; the shell's sections come from out/stl. Everything is a trimesh, and every boolean is
manifold3d's.

Poses: `mech.PANS` turn about Z with the pan; `mech.NODS` and the shell's beard, head and hat nod
about Y through C and then pan; the linkage moves on its own axes; everything else stands still.
"""
import json
import math
from functools import lru_cache
from pathlib import Path

import numpy as np
import trimesh

import params as P

CAD = Path(__file__).resolve().parents[1]
STL = CAD / "out" / "stl"
ENGINE = "manifold"
SCRATCH = CAD / "out" / "test_meshes"


def built():
    return (STL / "plate.stl").exists() and (CAD / "out" / "placements.json").exists()


def shell_built():
    return (STL / "collar.stl").exists() and (STL / "head.stl").exists()


def to_mesh(shape, name):
    """A build123d shape as a trimesh, through an STL in out/test_meshes."""
    from build123d import export_stl
    SCRATCH.mkdir(parents=True, exist_ok=True)
    path = SCRATCH / f"{name}.stl"
    export_stl(shape, str(path), tolerance=0.05, angular_tolerance=0.1)
    return trimesh.load(path)


@lru_cache(maxsize=None)
def mech_meshes():
    """Every printed mechanism part, placed, by name; the stop pin twice."""
    places = json.loads((CAD / "out" / "placements.json").read_text())
    out = {}
    for name, info in sorted(places.items()):
        if not (STL / f"{name}.stl").exists():
            continue
        m = trimesh.load(STL / f"{name}.stl")
        m.apply_transform(np.array(info["matrix"], float))
        out[name] = m
        if name == "stop_pin":
            twin = m.copy()
            twin.apply_transform(np.diag([1.0, -1.0, 1.0, 1.0]))
            twin.invert() if twin.volume < 0 else None
            out["stop_pin_mirrored"] = twin
    return out


def interfaces():
    import mech
    mech.load_all()
    return {n for names in mech.INTERFACES.values() for n in names}


@lru_cache(maxsize=None)
def bought():
    """The bought parts as envelopes, by name, with how each moves: 'fixed', 'pans' or 'nods'."""
    import mech
    mech.load_all()
    from mech import nod as N
    from mech.common import box, cyl_z, phone_body, servo_body
    from mech.torso import _rect
    out = {}
    for name, (shape, how) in N.nod_bought().items():
        out[name] = (to_mesh(shape, name), how)
    out["pan_servo"] = (to_mesh(servo_body(P.DS3218, (P.PAN_SERVO_XY[0], P.PAN_SERVO_XY[1],
                                                       P.Z_PAN_SHAFT_FACE), axis="-z"), "pan_servo"), "fixed")
    fx, fy, fh = P.FAN_XY[0], P.FAN_XY[1], P.FAN / 2
    z = P.Z_DECK - P.DECK_T
    out["fan"] = (to_mesh(box(fx - fh, fx + fh, fy - fh, fy + fh, z - P.FAN_T, z), "fan"), "fixed")
    ring = (cyl_z(P.BEARING_OD / 2, P.Z_BEARING, P.Z_BEARING + P.BEARING_B)
            - cyl_z(P.BEARING_ID / 2, P.Z_BEARING - 1, P.Z_BEARING + P.BEARING_B + 1))
    out["bearing"] = (to_mesh(ring, "bearing"), "fixed")
    out["phone"] = (to_mesh(phone_body(), "phone"), "fixed")
    z0 = P.Z_CHASSIS + P.CHASSIS_T + P.EDECK_STANDOFF + P.EDECK_T
    boards = None
    for name in P.EDECK_LAYOUT:
        x0, y0, x1, y1 = _rect(P.EDECK_LAYOUT[name])
        b = box(x0, x1, y0, y1, z0, z0 + 25.0)
        boards = b if boards is None else boards + b
    out["boards"] = (to_mesh(boards, "boards"), "fixed")
    return out


@lru_cache(maxsize=None)
def sections():
    return {n: trimesh.load(STL / f"{n}.stl") for n in P.PRINTED_SECTIONS}


def how_it_moves(name):
    import mech
    if name in mech.NODS or name in mech.SHELL_NODS:
        return "nods"
    if name in mech.PANS:
        return "pans"
    if name in mech.LINKAGE:
        return name
    b = bought()
    return b[name][1] if name in b else "fixed"


def matrix(how, pan=0.0, nod=0.0):
    """The 4 x 4 that carries a part that moves `how` to the pose."""
    c = np.array([0.0, 0.0, P.Z_NOD])
    m = np.eye(4)
    if how == "nods":
        m = trimesh.transformations.rotation_matrix(math.radians(-nod), (0, 1, 0), c)
    if how in ("nods", "pans"):
        m = trimesh.transformations.rotation_matrix(math.radians(pan), (0, 0, 1)) @ m
    elif how == "servo_crank":
        m = trimesh.transformations.rotation_matrix(math.radians(pan), (0, 0, 1),
                                                    (P.PAN_SERVO_XY[0], P.PAN_SERVO_XY[1], 0.0))
    elif how == "pan_link":
        rest, _ = P.crank_pins(0)
        pin, _ = P.crank_pins(pan)
        m = trimesh.transformations.translation_matrix((pin[0] - rest[0], pin[1] - rest[1], 0.0))
    return m


def at(mesh, how, pan=0.0, nod=0.0):
    out = mesh.copy()
    out.apply_transform(matrix(how, pan, nod))
    return out


@lru_cache(maxsize=None)
def tube(pan=0.0, nod=0.0):
    from mech.nod import tube_route
    return tube_route(pan, nod)


def union(meshes):
    meshes = [m for m in meshes if m is not None and len(m.faces)]
    return meshes[0] if len(meshes) == 1 else trimesh.boolean.union(meshes, engine=ENGINE)


def overlap(a, b):
    """The volume two meshes share, in mm3, skipping the boolean when their boxes do not meet."""
    lo_a, hi_a = a.bounds
    lo_b, hi_b = b.bounds
    if np.any(lo_a > hi_b) or np.any(lo_b > hi_a):
        return 0.0
    hit = trimesh.boolean.intersection([a, b], engine=ENGINE)
    return 0.0 if hit.is_empty else abs(hit.volume)


def gap(a, b, reach=40.0):
    """The least distance between two meshes' surfaces (0 if they overlap), measured from the
    vertices of each that lie within `reach` of the other's box, both ways."""
    best = math.inf
    for p, q in ((a, b), (b, a)):
        lo, hi = q.bounds
        v = p.vertices
        near = v[np.all((v >= lo - reach) & (v <= hi + reach), axis=1)]
        if not len(near):
            continue
        d = trimesh.proximity.ProximityQuery(q).signed_distance(near)
        best = min(best, float(-d.max()))
    return max(best, 0.0)


class Gaps:
    """Least distances between posed meshes, with one proximity query per mesh, built once.

    A pair is measured both ways - the vertices of each carried into the other's own frame and
    asked for their nearest point on it - so a query tree is never rebuilt for a pose. Only the
    vertices within `reach` of the other's box are asked about.
    """

    def __init__(self):
        self._q = {}

    def query(self, key, mesh):
        if key not in self._q:
            self._q[key] = trimesh.proximity.ProximityQuery(mesh)
        return self._q[key]

    def gap(self, ka, a, ma, kb, b, mb, reach=12.0):
        """a and b are meshes at rest, ma and mb the 4 x 4 that pose them."""
        best = math.inf
        for (kp, p, mp), (kq, q, mq) in (((ka, a, ma), (kb, b, mb)), ((kb, b, mb), (ka, a, ma))):
            to_q = np.linalg.inv(mq) @ mp                       # p's vertices into q's frame
            v = trimesh.transform_points(p.vertices, to_q)
            lo, hi = q.bounds
            near = v[np.all((v >= lo - reach) & (v <= hi + reach), axis=1)]
            if not len(near):
                continue
            if len(near) > 6000:                               # a shell section: a fair sample of it
                near = near[np.random.default_rng(3).choice(len(near), 6000, replace=False)]
            _, d, _ = self.query(kq, q).on_surface(near)
            best = min(best, float(d.min()))
        return best


def manifold(mesh):
    """A trimesh as a manifold3d Manifold, for fast booleans and gaps (its own BVH)."""
    import manifold3d as mf
    m = mf.Manifold(mf.Mesh(vert_properties=np.asarray(mesh.vertices, np.float32),
                            tri_verts=np.asarray(mesh.faces, np.uint32)))
    if m.status() != mf.Error.NoError:
        raise ValueError(f"not a manifold: {m.status()}")
    return m


def moved(man, how, pan=0.0, nod=0.0):
    """A Manifold carried to a pose, the way at() carries a mesh."""
    return man.transform(matrix(how, pan, nod)[:3, :].astype(np.float32).tolist())


def mgap(a, b, reach=40.0):
    """The least distance between two Manifolds, capped at `reach` (0 if they touch)."""
    return float(a.min_gap(b, reach))


def mvolume(a, b):
    """The volume two Manifolds share."""
    return float((a ^ b).volume())
