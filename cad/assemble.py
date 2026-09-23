"""Turn the raw Blender sections into printable ones: interface parts in, openings and splits out.

Every boolean here runs in manifold3d through trimesh. Blender's own exact boolean was measured
to leave non-manifold results on remeshed meshes, which is why the sculpt never cuts anything:
it hands over closed, walled solids and this module does the rest.

The sculpt arrives heavy - the base is half a million triangles - and manifold3d takes it at
that size in about a second a section, so nothing is decimated: `DECIMATE` is there for the day
a section grows past what is comfortable, and is off.

The belly panel is cut from the torso's own wall, so the two are the same surface either side
of one seam. Everything the torso lets into that wall - the hatch lip, the screw bosses, the
deck ring's webs where they reach it - is rebated out of the panel with CLEAR_SHELL, which is
what makes the panel sit flush rather than stand proud of its own frame.
"""
import math
import sys
import time
from pathlib import Path

import numpy as np
import trimesh
from build123d import Location
from scipy.spatial import cKDTree

CAD = Path(__file__).resolve().parent
sys.path.insert(0, str(CAD))
import params as P  # noqa: E402
import mech.base, mech.head, mech.torso, mech.turntable  # noqa: E402,F401
from mech import ALL, INTERFACES  # noqa: E402

RAW, STL = CAD / "out" / "raw", CAD / "out" / "stl"
ENGINE = "manifold"
DECIMATE = None           # a face count to reduce a sculpted section to first; see the note above
SECTIONS = ("base", "torso", "belly", "head_back", "face", "hat")
SLIVER = 1.0              # mm3 under which a component is boolean litter, not a part
FAR = 400.0               # long enough to pass through anything, short enough to stay readable


# --- loading ---------------------------------------------------------------------------------
def load_raw(name, decimate=DECIMATE):
    m = trimesh.load(RAW / f"{name}.stl")
    if decimate and len(m.faces) > decimate:
        m = m.simplify_quadric_decimation(face_count=decimate)
        assert m.is_watertight, f"decimating {name} tore it"
    return m


def load_part(name):
    """An interface part's STL, which `export` writes in its print frame.

    Every interface part is drawn where it sits and declares no placement, so its print frame
    is the machine's frame and the STL can be unioned straight in. Checked, not assumed.
    """
    spec = next(s for s in ALL if s.name == name)
    ident = Location()
    assert tuple(spec.placement.position) == tuple(ident.position), f"{name} is placed, not drawn in place"
    assert tuple(spec.placement.orientation) == tuple(ident.orientation), f"{name} is rotated"
    return trimesh.load(STL / f"{name}.stl")


def interfaces(section):
    return [load_part(n) for n in INTERFACES.get(section, [])]


# --- booleans --------------------------------------------------------------------------------
def union(*meshes):
    return trimesh.boolean.union([m for m in meshes if m is not None], engine=ENGINE)


def cut(mesh, *cutters):
    return trimesh.boolean.difference([mesh, *cutters], engine=ENGINE)


def isect(*meshes):
    return trimesh.boolean.intersection(list(meshes), engine=ENGINE)


# --- cutters ---------------------------------------------------------------------------------
def box(x0, x1, y0, y1, z0, z1):
    b = trimesh.creation.box(extents=(x1 - x0, y1 - y0, z1 - z0))
    b.apply_translation(((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2))
    return b


def _aim(mesh, deg, at):
    """Point a +Z solid outward along the meridian `deg` and stand it at `at` = (r, z)."""
    mesh.apply_transform(trimesh.transformations.rotation_matrix(math.pi / 2, (0.0, 1.0, 0.0)))
    mesh.apply_transform(trimesh.transformations.rotation_matrix(math.radians(deg), (0.0, 0.0, 1.0)))
    th = math.radians(deg)
    mesh.apply_translation((at[0] * math.cos(th), at[0] * math.sin(th), at[1]))
    return mesh


def cyl_z(r, z0, z1, x=0.0, y=0.0, sections=96):
    c = trimesh.creation.cylinder(radius=r, height=z1 - z0, sections=sections)
    c.apply_translation((x, y, (z0 + z1) / 2))
    return c


def cyl_out(r, r0, r1, deg, z, sections=96):
    """A cylinder lying along the meridian `deg`, from radius r0 to r1 at height z."""
    c = trimesh.creation.cylinder(radius=r, height=r1 - r0, sections=sections)
    c.apply_translation((0.0, 0.0, (r0 + r1) / 2))
    return _aim(c, deg, (0.0, z))


def cyl_x(r, x0, x1, y=0.0, z=0.0, sections=96):
    c = trimesh.creation.cylinder(radius=r, height=x1 - x0, sections=sections)
    c.apply_transform(trimesh.transformations.rotation_matrix(math.pi / 2, (0.0, 1.0, 0.0)))
    c.apply_translation(((x0 + x1) / 2, y, z))
    return c


def cyl_y(r, y0, y1, x=0.0, z=0.0, sections=96):
    c = trimesh.creation.cylinder(radius=r, height=y1 - y0, sections=sections)
    c.apply_transform(trimesh.transformations.rotation_matrix(math.pi / 2, (1.0, 0.0, 0.0)))
    c.apply_translation((x, (y0 + y1) / 2, z))
    return c


def ball(r, at, subdivisions=4):
    s = trimesh.creation.icosphere(subdivisions=subdivisions, radius=r)
    s.apply_translation(at)
    return s


def wedge(half_deg, z0, z1, r=FAR):
    """The solid |atan2(y, x)| <= half_deg between z0 and z1: the belly hatch's outline."""
    ahead = box(0.0, r, -r, r, z0, z1)
    a = ahead.copy().apply_transform(trimesh.transformations.rotation_matrix(
        math.radians(half_deg - 90.0), (0.0, 0.0, 1.0)))
    b = ahead.copy().apply_transform(trimesh.transformations.rotation_matrix(
        math.radians(90.0 - half_deg), (0.0, 0.0, 1.0)))
    return isect(ahead, a, b)


def skin_at(mesh, deg, z):
    """The outermost radius of `mesh` on the meridian `deg` at height z, or None if it misses.

    The sculpt's skin is not its profile - the coat swells and tucks - so a countersink placed
    from `shell_r` sinks into thin air or into the wall. This is where the surface actually is.
    """
    th = math.radians(deg)
    loc, _, _ = mesh.ray.intersects_location(np.array([[0.0, 0.0, z]]),
                                             np.array([[math.cos(th), math.sin(th), 0.0]]))
    return max(math.hypot(p[0], p[1]) for p in loc) if len(loc) else None


def countersunk(deg, z, r_skin, through=30.0):
    """A screw hole drilled inward along a meridian: M3 clearance under a 6 mm sink, 2 deep.

    `r_skin` is where the cone's mouth goes, so it has to be the panel's own outer surface.
    """
    line = [(0.0, -2.0), (3.0, -2.0), (3.0, 0.0), (P.M3_CLEAR / 2, 2.0),
            (P.M3_CLEAR / 2, through), (0.0, through)]
    c = trimesh.creation.revolve(np.array(line), sections=48)
    c.apply_transform(trimesh.transformations.rotation_matrix(math.pi, (1.0, 0.0, 0.0)))
    return _aim(c, deg, (r_skin, z))


def dilate(mesh, d, name=""):
    """`mesh` grown so its faces stand d millimetres off, for use as a clearance cutter.

    Moving vertices along their own normals is not the same as moving faces: at a box's corner
    the vertex normal is the body diagonal, so a vertex pushed d moves each of the three faces
    it belongs to by only d / sqrt(3). These cutters are the build123d interface parts, which
    are slabs, boxes and bands, so the vertex offset is scaled by sqrt(3) and the faces land
    where they were asked to. On a sphere the same scaling would overshoot by the same factor -
    there is none here, and a cutter that takes too much would say so in the wall check.

    Falls back to the part itself if the offset tangles, and says so: a flush rebate is better
    than a broken one, but it is not what was asked for.
    """
    grown = mesh.copy()
    grown.vertices = grown.vertices + grown.vertex_normals * (d * math.sqrt(3.0))
    if grown.is_watertight and grown.volume > mesh.volume:
        return grown
    print(f"      dilate: {name or 'a part'} would not offset cleanly; rebated flush instead")
    return mesh


# --- finishing -------------------------------------------------------------------------------
def unpinch(mesh, tol=2e-4, eps=2e-3):
    """Pull apart vertices that sit on top of one another but belong to different surfaces.

    manifold3d is entitled to leave two vertices in one place - a pinch, where a cutter grazed a
    facet - and in memory that is a perfectly good solid. An STL carries no vertex identity, so
    reading one back merges the pair, and what was a pinch becomes an edge with four faces on it:
    not watertight, and no use to anything downstream. Two microns between the twins before the
    file is written is two microns between them after it is read, and that is four orders of
    magnitude below anything this shell is printed to.

    `tol` is not a guess: a binary STL stores single-precision floats, which at this gnome's
    top of the head are spaced six hundredths of a micron apart, so any two vertices closer
    than that land on the same number whatever their history. Twins are anything inside three
    times that.
    """
    v = np.asarray(mesh.vertices)
    pairs = cKDTree(v).query_pairs(tol, output_type="ndarray")
    if not len(pairs):
        return mesh, 0
    out = mesh.copy()
    idx = np.unique(pairs[:, 0])
    out.vertices[idx] = out.vertices[idx] + out.vertex_normals[idx] * eps
    return out, len(idx)


def tidy(mesh):
    """Drop the zero-volume shells a boolean leaves where a cut plane grazes a sculpted skin.

    The hatch's two radial faces run down a barrel that the remesh made out of thousands of
    little facets, and every facet the plane nearly misses leaves a closed surface with no
    volume behind. They pass every check in memory - a closed surface is watertight whatever
    its volume - but an STL round trip merges their coincident vertices and what comes back is
    not manifold. So they go before the file is written, and the count is reported.
    """
    parts = mesh.split(only_watertight=False)
    if len(parts) < 2:
        return mesh, 0
    solid = [c for c in parts if abs(c.volume) > SLIVER]
    if len(solid) == len(parts):
        return mesh, 0
    kept = solid[0] if len(solid) == 1 else trimesh.util.concatenate(solid)
    return kept, len(parts) - len(solid)


def save(mesh, name, t0):
    STL.mkdir(parents=True, exist_ok=True)
    mesh, slivers = tidy(mesh)
    mesh, pinches = unpinch(mesh)
    assert mesh.is_watertight, f"{name} is not watertight"
    assert mesh.is_winding_consistent, f"{name} has inconsistent winding"
    assert mesh.volume > 0.0, f"{name} has no volume"
    assert mesh.body_count == 1, f"{name} is {mesh.body_count} bodies, not one"
    mesh.export(STL / f"{name}.stl")
    # what the tests will load is the file, not the mesh in hand: check that one
    back = trimesh.load(STL / f"{name}.stl")
    assert back.is_watertight, f"{name} did not survive the round trip to STL"
    bodies = back.body_count
    notes = "".join([f", {slivers} slivers dropped" if slivers else "",
                     f", {pinches} pinches opened" if pinches else ""])
    print(f"stl   {name}: {len(mesh.faces)} faces, {mesh.volume / 1000:.1f} cm3, "
          f"{bodies} {'body' if bodies == 1 else 'bodies'}{notes}, {time.time() - t0:.1f} s")
    return mesh


def probe(name, text):
    print(f"      {name}: {text}")


# --- sections --------------------------------------------------------------------------------
def base():
    t0 = time.time()
    m = union(load_raw("base"), *interfaces("base"))
    # Drain arches round the skirt, at the four angles the boots leave clear. Each is a cylinder
    # lying along a diameter, dropped so its crown is DRAIN_ARCH_H above the ground.
    cutters = [cyl_x(P.DRAIN_ARCH_W / 2, -FAR, FAR, 0.0, P.DRAIN_ARCH_H - P.DRAIN_ARCH_W / 2)]
    cutters.append(cutters[0].copy().apply_transform(
        trimesh.transformations.rotation_matrix(math.pi / 2, (0.0, 0.0, 1.0))))
    # Stake holes through the raised floor, between the arches.
    for a in (45.0, 135.0, 225.0, 315.0):
        x, y = P.STAKE_HOLE_R * math.cos(math.radians(a)), P.STAKE_HOLE_R * math.sin(math.radians(a))
        cutters.append(cyl_z(P.STAKE_HOLE_D / 2, P.Z_FLOOR - 20.0, P.Z_FLOOR + 20.0, x, y))
    # The filler port through the back wall: the neck the cap screws onto is printed with the
    # shell, so the hole is the neck's outside, not the tube's bore.
    r_skin = P.shell_r(P.BASE_PROFILE, P.Z_FILLER)
    cutters.append(cyl_out(P.FILLER_D / 2 + 2.5, r_skin - 30.0, r_skin + 20.0, 180.0, P.Z_FILLER))
    # and the rim is trimmed to Z_BASE_TOP: solidify leaves the cut plane a tenth or two proud,
    # and the torso's flange sits on exactly that plane
    cutters.append(box(-FAR, FAR, -FAR, FAR, P.Z_BASE_TOP, FAR))
    m = cut(m, *cutters)
    m = save(m, "base", t0)
    down = m.ray.intersects_location(np.array([[0.0, 0.0, P.Z_BASE_TOP + 60.0]]), np.array([[0.0, 0.0, -1.0]]))[0]
    zs = sorted((float(p[2]) for p in down), reverse=True)
    probe("open at the top", f"a ray down the axis first meets {zs[0]:.1f} "
                             f"(the floor is at {P.Z_FLOOR}..{P.Z_FLOOR + P.WALL})")
    assert zs[0] < P.Z_FLOOR + P.WALL + 1.0, "the base is lidded"
    return m


def _panel_rebate(skins):
    """Everything the torso lets into the wall inside the hatch, grown by CLEAR_SHELL.

    The panel is the wall, and every interface part bites the wall's inner 1.2 mm, so without
    this the two would want the same millimetre. The lip's own note says the panel is rebated;
    the screw bosses and the deck ring's webs need it for the same reason.

    Except at the screws. A hatch boss is rebated out of the panel like everything else, but
    the screw goes through the panel in the middle of that rebate, and a countersunk M3 in
    0.8 mm of PETG tears out. So the rebate stops CLEAR_SHELL + 4 short of each screw's axis
    and the panel keeps its full wall where the head pulls on it.
    """
    inside = [dilate(p, P.CLEAR_SHELL, n) for p, n in zip(interfaces("torso"), INTERFACES["torso"])]
    keep = [cyl_out(P.CLEAR_SHELL + 4.0, r - 30.0, r + 20.0, a, z)
            for (z, a), r in zip(P.HATCH_SCREWS, skins)]
    return cut(union(*inside), *keep)


def torso_and_belly():
    t0 = time.time()
    raw = load_raw("torso")
    hatch = wedge(P.HATCH_HALF_ANGLE, *P.HATCH_Z)
    panel = isect(raw, hatch)
    m = union(cut(raw, hatch), *interfaces("torso"))
    # measured on the panel before anything is cut out of it, so the ray meets a surface
    skins = [skin_at(panel, a, zs) for zs, a in P.HATCH_SCREWS]
    assert all(r is not None for r in skins), "a hatch screw misses the panel"

    cutters = []
    xb = P.shell_r(P.TORSO_PROFILE, P.Z_FAN)
    cutters.append(cyl_out(P.FAN / 2 - 2.0, xb - 30.0, xb + 20.0, 180.0, P.Z_FAN))
    xi = P.shell_r(P.TORSO_PROFILE, P.Z_VENT_IN)
    vent = box(-xi - 20.0, -xi + 30.0, -P.VENT_IN_W / 2, P.VENT_IN_W / 2,
               P.Z_VENT_IN - P.VENT_IN_H / 2, P.Z_VENT_IN + P.VENT_IN_H / 2)
    cutters.append(vent)
    # And the panel keeps its full wall at the four screws, so the boss gives way instead: the
    # bracket is cut back over a disc round each screw to a CLEAR_SHELL inside the panel's own
    # inner face. That disc is where the insert looks out and where the screw pulls, and 0.8 mm
    # of PETG under a countersunk head is a part that tears rather than one that holds.
    for (zs, a), r in zip(P.HATCH_SCREWS, skins):
        # deep enough for the whole disc, so the shallowest corner of it still clears: the skin
        # is sampled round the disc's rim, not just on the screw's line, because the shoulder
        # draws in through here and a cut sized at the middle leaves the edges proud
        rim = min([r] + [x for x in (skin_at(panel, a + d, zs + dz)
                                     for d, dz in ((3.0, 0.0), (-3.0, 0.0), (0.0, 5.0), (0.0, -5.0)))
                         if x is not None])
        cutters.append(cyl_out(P.CLEAR_SHELL + 4.0, rim - P.WALL - P.CLEAR_SHELL, r + 20.0, a, zs))
    m = cut(m, *cutters)
    m = save(m, "torso", t0)

    t1 = time.time()
    zc = P.Z_LENS + P.WINDOW_Z_BIAS
    xw = P.shell_r(P.TORSO_PROFILE, zc)
    window = box(xw - 30.0, xw + 30.0, P.CAM_Y - P.WINDOW_W / 2, P.CAM_Y + P.WINDOW_W / 2,
                 zc - P.WINDOW_H / 2, zc + P.WINDOW_H / 2)
    probe("panel screws", "the sink's mouth on the skin at r " + ", ".join(f"{r:.2f}" for r in skins))
    screws = [countersunk(a, zs, r) for (zs, a), r in zip(P.HATCH_SCREWS, skins)]
    belly = cut(panel, _panel_rebate(skins), window, *screws)
    belly = save(belly, "belly", t1)
    return m, belly, panel


def head():
    t0 = time.time()
    raw = load_raw("head")
    z = P.Z_HEAD
    openings = [
        cyl_x(P.MOUTH_D / 2, 0.0, P.HEAD_R + 20.0, 0.0, P.Z_MOUTH),                  # the nozzle's bore
        cyl_z(P.HEAD_OPENING_R, z - P.HEAD_R - 20.0, z - P.HEAD_R + 20.0),           # tube and wires
        cyl_y(P.HEAD_BORE_D / 2, P.HEAD_R - 20.0, P.HEAD_R + 20.0, 0.0, z),          # the coupler, +Y
    ]
    raw = cut(raw, *openings)
    front = box(P.FACE_SPLIT_X, FAR, -FAR, FAR, z - FAR, z + FAR)
    back = box(-FAR, P.FACE_SPLIT_X, -FAR, FAR, z - FAR, z + FAR)
    face = save(union(isect(raw, front), *interfaces("face")), "face", t0)
    t1 = time.time()
    # head_lip is drawn a CLEAR inside the wall's inner face, so unioned on its own it floats in
    # the cavity - a ring the printer would drop on the bed. This band fills that gap, radially
    # outward only, so the cap still seats on the lip's own surface; and it gives way to the face
    # cap's stop block, which reaches back over the split plane.
    r_in = P.HEAD_R - P.WALL
    band = cut(ball(r_in + 0.3, (0.0, 0.0, z), 5), ball(r_in - P.CLEAR, (0.0, 0.0, z), 5))
    bridge = isect(band, box(P.FACE_SPLIT_X - P.FACE_LIP_L, P.FACE_SPLIT_X, -FAR, FAR, z - FAR, z + FAR))
    bridge = cut(bridge, dilate(face, P.CLEAR))
    back_half = union(isect(raw, back), *interfaces("head_back"), bridge)
    # The -Y ear's M4 bore is drilled here rather than in the part, because two things stand in
    # it that the part cannot see: the head's own wall, which the union brings, and the stop
    # tab, which ear_boss adds after cutting its hole. Drilled last, it clears both.
    back_half = cut(back_half, cyl_y(P.INSERT_M4_D / 2, -P.EAR_OUT_Y - 1.0,
                                     -P.EAR_OUT_Y + P.INSERT_M4_DEPTH, 0.0, z))
    back_half = save(back_half, "head_back", t1)
    hit = back_half.ray.intersects_location(np.array([[0.0, -FAR, z]]), np.array([[0.0, 1.0, 0.0]]))[0]
    ys = sorted(float(p[1]) for p in hit)
    probe("ear insert", f"a ray up -Y first meets {ys[0]:.1f}, so the bore is "
                        f"{ys[0] + P.EAR_OUT_Y:.1f} mm deep from the boss's face at {-P.EAR_OUT_Y}")
    assert ys[0] + P.EAR_OUT_Y >= P.INSERT_M4_DEPTH - 0.5, "the ear boss's insert is not open to the outside"
    return face, back_half


def hat():
    t0 = time.time()
    m = cut(load_raw("hat"), ball(P.HEAD_R + P.CLEAR, (0.0, 0.0, P.Z_HEAD), subdivisions=5))
    return save(m, "hat", t0)


# --- what the seam came out like --------------------------------------------------------------
def report_seam(panel):
    """How far the hatch lip stands off the panel it is meant to carry.

    The lip is sized from TORSO_PROFILE; the panel's inner face is wherever the sculpt put the
    skin, less a wall. Where the sculpt stands more than the lip's 1.2 mm bite proud of the
    profile - the sleeve crossing the seam is the one place it comes close - the lip stops
    touching and the panel's edge is carried by its neighbours instead.

    Reported past the CLEAR_SHELL the rebate is meant to leave, so the number is what carries
    no load rather than what was designed in. Sampled over the band the lip actually occupies,
    and stopped a fifth of a degree short of the cut itself, where a ray grazes the radial face
    and reports whatever is behind it.
    """
    z0, z1 = P.HATCH_Z
    inset = math.degrees(P.HATCH_LIP_W / P.shell_r(P.TORSO_PROFILE, (z0 + z1) / 2))
    gaps, worst = [], (-9e9, None)
    for z in np.arange(z0 + 1.0, z1 - 1.0, 2.0):
        for a in np.arange(P.HATCH_HALF_ANGLE - inset, P.HATCH_HALF_ANGLE - 0.19, 0.5):
            for s in (1.0, -1.0):
                th = math.radians(s * a)
                hit = panel.ray.intersects_location(np.array([[0.0, 0.0, z]]),
                                                    np.array([[math.cos(th), math.sin(th), 0.0]]))[0]
                if not len(hit):
                    continue
                gap = (min(math.hypot(p[0], p[1]) for p in hit)
                       - (P.shell_r(P.TORSO_PROFILE, z) - 1.2) - P.CLEAR_SHELL)
                gaps.append(gap)
                if gap > worst[0]:
                    worst = (gap, (s * a, z))
    gaps = np.array(gaps)
    probe("hatch seam", f"panel unsupported over the lip, past its CLEAR_SHELL, in {len(gaps)} probes: "
                        f"median {np.median(gaps):+.2f}, worst {worst[0]:+.2f} mm at "
                        f"{worst[1][0]:+.1f}deg z {worst[1][1]:.0f}, over 1 mm: {(gaps > 1.0).sum()}")
    return worst[0]


def main():
    t0 = time.time()
    base()
    _, belly, _ = torso_and_belly()
    head()
    hat()
    report_seam(belly)
    print(f"stl   {len(SECTIONS)} sections in {time.time() - t0:.1f} s")


if __name__ == "__main__":
    main()
