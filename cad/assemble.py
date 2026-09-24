"""Turn the statue's raw sections into printable ones: interface parts in, openings out.

The raw sections come from `statue.py` - the reconstruction's skin, hollowed and cut around a
turning bell. This module does the rest, and every boolean runs in manifold3d through trimesh.

Each interface part is drawn in `mech/` as a blank that overshoots the shell: an elliptical
flange wider than the coat, a floor plate bigger than the boots. That is deliberate. The skin is
a 200 000-triangle reconstruction, not a profile anything can be dimensioned from, so instead of
asking the mechanism to guess where the wall is, the blank is clipped here to `cavity_grown` -
the cavity offset back to within 1.2 mm of the skin - and what is left lands inside the wall and
fuses to it. A part that straddles a section's boundary is clipped again by that section's own
region, so the deck ring's webs go to the panels and its hub to the ring, from one description.

What the openings are for: the window is the phone camera's, in the fixed ring so the view never
turns; the intake is behind it, the air leaves through the bell's turning gap and the parting, so there is no exhaust to cut; the parting
and the mouth are the nozzle's, in the bell, so the jet's slot turns with the head and always
faces where the head faces; the four radial holes in the head are the shroud's screws.
"""
import math
import sys
import time
from pathlib import Path

import numpy as np
import trimesh

CAD = Path(__file__).resolve().parent
sys.path.insert(0, str(CAD))
import params as P  # noqa: E402
from statue import FAR, KERF, write  # noqa: E402

RAW = CAD / "out" / "statue" / "raw"
STL = CAD / "out" / "stl"
ENGINE = "manifold"
SECTIONS = tuple(P.SECTIONS_STATUE)
# Which section each interface blank is unioned into. A blank that spans two of them is named
# in both and clipped by each one's region, which is the same cut the shell itself was given.
INTO = {
    "belt_flange_lower": ("base_left", "base_right"),
    "floor_plate": ("base_left", "base_right"),
    "belt_flange_upper": ("torso", "panel_left", "panel_right"),
}
# Neither the deck ring nor the fan frame is here any more. The ring became a cage standing on
# the chassis; the fan hangs under the deck and blows up through it, so the shell has no exhaust
# to cut and nothing of the fan to carry. `unclaimed()` is what makes sure the next part added to
# `mech`'s registry is not silently left out of the shell the way those two could have been.
STAKE_ANGLES = (45.0, 135.0, 225.0, 315.0)
DRAIN_ANGLES = (55.0, 125.0, 235.0, 305.0)


# --- booleans and cutters --------------------------------------------------------------------
def union(*meshes):
    return trimesh.boolean.union([m for m in meshes if m is not None], engine=ENGINE)


def cut(mesh, *cutters):
    return trimesh.boolean.difference([mesh, *cutters], engine=ENGINE)


def isect(*meshes):
    return trimesh.boolean.intersection(list(meshes), engine=ENGINE)


def box(x0, x1, y0, y1, z0, z1):
    b = trimesh.creation.box(extents=(x1 - x0, y1 - y0, z1 - z0))
    b.apply_translation(((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2))
    return b


def cyl_z(r, z0, z1, x=0.0, y=0.0, sections=96):
    c = trimesh.creation.cylinder(radius=r, height=z1 - z0, sections=sections)
    c.apply_translation((x, y, (z0 + z1) / 2))
    return c


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


def aim(mesh, deg, r, z):
    """Point a +Z solid outward along the meridian `deg`, standing at radius r, height z."""
    mesh.apply_transform(trimesh.transformations.rotation_matrix(math.pi / 2, (0.0, 1.0, 0.0)))
    mesh.apply_transform(trimesh.transformations.rotation_matrix(math.radians(deg), (0.0, 0.0, 1.0)))
    th = math.radians(deg)
    mesh.apply_translation((r * math.cos(th), r * math.sin(th), z))
    return mesh


def skin_at(mesh, deg, z):
    """The outermost radius of `mesh` on the meridian `deg` at height z, or None if it misses."""
    th = math.radians(deg)
    loc, _, _ = mesh.ray.intersects_location(np.array([[0.0, 0.0, z]]),
                                             np.array([[math.cos(th), math.sin(th), 0.0]]))
    return max(math.hypot(p[0], p[1]) for p in loc) if len(loc) else None


def countersunk(deg, z, r_skin, through=30.0):
    """A screw hole drilled inward along a meridian: M3 clearance under a 6 mm sink, 2 deep."""
    line = [(0.0, -2.0), (3.0, -2.0), (3.0, 0.0), (P.M3_CLEAR / 2, 2.0),
            (P.M3_CLEAR / 2, through), (0.0, through)]
    c = trimesh.creation.revolve(np.array(line), sections=48)
    c.apply_transform(trimesh.transformations.rotation_matrix(math.pi, (1.0, 0.0, 0.0)))
    return aim(c, deg, r_skin, z)


def parting(step=2.5):
    """The beard's parting: the solid the jet sweeps out as the nozzle tilts.

    The brief's slot was Z_MOUTH +- 22, and it is not enough. The nozzle's tip sits three
    millimetres inside the skin at the mouth, but the face above the mouth is the nose, and by
    the top of the tilt the jet has seventeen millimetres of statue to cross before it is out -
    it would leave at z 455, nine above the slot's top. So the cutter is the swept envelope
    itself: a JET_D-thick, NOZZLE_SLOT_W-wide slab through the pivot, turned through every tilt
    the firmware allows, which is by construction exactly the parting the jet needs and no more.
    """
    lo, hi = P.TILT_STOP
    cutters = []
    for deg in np.arange(lo, hi + 1e-9, step):
        slab = box(0.0, FAR, -P.NOZZLE_SLOT_W / 2, P.NOZZLE_SLOT_W / 2, -P.JET_D / 2, P.JET_D / 2)
        slab.apply_transform(trimesh.transformations.rotation_matrix(
            math.radians(-float(deg)), (0.0, 1.0, 0.0)))     # about +Y, positive is nose-down
        slab.apply_translation(P.NOZZLE_PIVOT)
        cutters.append(slab)
    return union(*cutters)


def arch(deg, w, h, r0=0.0, r1=FAR):
    """A drain arch through the sole's wall on the meridian `deg`.

    Half an ellipse w wide and h tall, sitting on the ground: wider than it is tall, which a
    circular arch of this width could not be, and no overhang for the printer to bridge.
    """
    top = trimesh.creation.cylinder(radius=1.0, height=r1 - r0, sections=64)
    top.apply_transform(trimesh.transformations.rotation_matrix(math.pi / 2, (0.0, 1.0, 0.0)))
    top.apply_transform(np.diag([1.0, w / 2, h, 1.0]))
    top.apply_translation(((r0 + r1) / 2, 0.0, 0.0))
    both = union(top, box(r0, r1, -w / 2, w / 2, -2.0, 0.0))
    both.apply_transform(trimesh.transformations.rotation_matrix(math.radians(deg), (0.0, 0.0, 1.0)))
    return both


# --- the sections' own regions ---------------------------------------------------------------
def region(name):
    """The solid a section was cut from, so a part that straddles a seam is split the same way.

    The base halves are the one that is not a box: the mitten caps come out of them, and a belt
    flange 210 mm across reaches into exactly that corner, so a flange clipped by the box alone
    would be unioned into the base and into the cap both.
    """
    if name.startswith("base_"):
        side = 1.0 if name.endswith("left") else -1.0
        whole = box(*((-FAR, FAR, KERF / 2, FAR) if side > 0 else (-FAR, FAR, -FAR, -KERF / 2)),
                    -1.0, P.Z_BELT)
        return cut(whole, box(*region_box(f"hand_{'left' if side > 0 else 'right'}")))
    return box(*region_box(name))


def region_box(name):
    py, pt, pb = P.PANEL_Y, P.PANEL_TOP, P.PANEL_BOTTOM
    top = P.Z_TURN - P.TURN_GAP
    return {
        "base_left": (-FAR, FAR, KERF / 2, FAR, -1.0, P.Z_BELT),
        "base_right": (-FAR, FAR, -FAR, -KERF / 2, -1.0, P.Z_BELT),
        "hand_left": (-FAR, FAR, py, FAR, pb, P.Z_BELT),
        "hand_right": (-FAR, FAR, -FAR, -py, pb, P.Z_BELT),
        "torso": (-FAR, FAR, -py, py, P.Z_BELT, top),
        "panel_left": (-FAR, FAR, py, FAR, P.Z_BELT, pt),
        "panel_right": (-FAR, FAR, -FAR, -py, P.Z_BELT, pt),
        "beard": (-FAR, FAR, -FAR, FAR, P.Z_TURN, P.SECTIONS_STATUE["beard"][1]),
        "head": (-FAR, FAR, -FAR, FAR, P.SECTIONS_STATUE["head"][0], P.Z_HAT),
        "hat": (-FAR, FAR, -FAR, FAR, P.Z_HAT, P.Z_TOP + 1.0),
    }[name]


def load_part(name):
    """An interface part's STL, checked to be drawn where it sits rather than placed."""
    try:
        from build123d import Location
        from mech import ALL
        spec = next((s for s in ALL if s.name == name), None)
        if spec is not None:
            ident = Location()
            assert tuple(spec.placement.position) == tuple(ident.position), f"{name} is placed"
            assert tuple(spec.placement.orientation) == tuple(ident.orientation), f"{name} is rotated"
    except Exception as exc:                      # the mechanism is being reworked next door
        print(f"      {name}: could not check its placement ({exc.__class__.__name__}); trusting the STL")
    return trimesh.load(STL / f"{name}.stl")


def blanks(section, raw, grown):
    """Every interface part that belongs to this section, clipped into its wall.

    Clipping alone is not enough to belong. A blank drawn across the whole cavity - the deck
    ring, whose hub stands in the middle and whose webs reach out to the panels - leaves pieces
    inside a section's box that touch none of its wall, and unioning those would ship a section
    with a lump rattling inside it. So each piece has to overlap the raw section itself, which is
    what `cavity_grown` reaching 1.2 mm into the wall is for, and the rest is said aloud and left
    to be its own part.
    """
    out = []
    for name, targets in INTO.items():
        if section not in targets:
            continue
        path = STL / f"{name}.stl"
        if not path.exists():
            print(f"      {section}: {name}.stl is not built; skipped")
            continue
        clipped = isect(load_part(name), grown, region(section))
        if clipped.is_empty or abs(clipped.volume) < 1.0:
            print(f"      {section}: {name} has nothing inside this section's wall; skipped")
            continue
        welded, loose = [], 0.0
        for piece in clipped.split(only_watertight=False):
            if abs(piece.volume) < 1.0:
                continue
            joined = isect(piece, raw)
            if not joined.is_empty and abs(joined.volume) > 1.0:
                welded.append(piece)
            else:
                loose += abs(piece.volume)
        note = f", {loose / 1e3:.1f} cm3 of it standing free and left out" if loose else ""
        if not welded:
            print(f"      {section}: {name} touches no wall here ({clipped.volume / 1e3:.1f} cm3); skipped")
            continue
        print(f"      {section}: {name} {sum(abs(p.volume) for p in welded) / 1e3:.1f} cm3 in{note}")
        out.extend(welded)
    return out


# --- what is cut out of each section ----------------------------------------------------------
def openings(name, mesh):
    if name == "torso":
        window = box(0.0, FAR, P.CAM_Y - P.WINDOW_W / 2, P.CAM_Y + P.WINDOW_W / 2,
                     P.Z_LENS + P.WINDOW_Z_BIAS - P.WINDOW_H / 2,
                     P.Z_LENS + P.WINDOW_Z_BIAS + P.WINDOW_H / 2)
        intake = box(-FAR, 0.0, -P.VENT_IN_W / 2, P.VENT_IN_W / 2,
                     P.Z_VENT_IN - P.VENT_IN_H / 2, P.Z_VENT_IN + P.VENT_IN_H / 2)
        return cut(mesh, window, intake)
    if name in ("beard", "head"):
        # the parting the nozzle arm swings through, and the mouth it points out of
        mesh = cut(mesh, parting(), cyl_x(P.MOUTH_D / 2, 0.0, FAR, 0.0, P.Z_MOUTH))
        holes = []
        for deg in P.SHROUD_SCREW_ANGLES:
            r = skin_at(mesh, deg, P.SHROUD_SCREWS_Z)
            if r is not None:
                holes.append(countersunk(deg, P.SHROUD_SCREWS_Z, r, through=r - P.SHROUD_R_OUT + 6.0))
        return cut(mesh, *holes) if holes else mesh
    if name.startswith("base_"):
        side = 1.0 if name.endswith("left") else -1.0
        cutters = [arch(deg, P.DRAIN_ARCH_W, P.DRAIN_ARCH_H)
                   for deg in DRAIN_ANGLES if math.sin(math.radians(deg)) * side > 0]
        for deg in STAKE_ANGLES:
            if math.sin(math.radians(deg)) * side <= 0:
                continue
            th = math.radians(deg)
            cutters.append(cyl_z(P.STAKE_HOLE_D / 2, -1.0, P.STAKE_HOLE_D * 2,
                                 P.STAKE_HOLE_R * math.cos(th), P.STAKE_HOLE_R * math.sin(th)))
        return cut(mesh, *cutters)
    return mesh


def debris(mesh, name, limit=5000.0):
    """Drop the loose crumbs a cut frees inside a section.

    The skin's inward offset folds on itself under the nose and behind the ears, and those folds
    hang off the wall by a hair; cut the nozzle's parting past one and it comes away as a lump of
    plastic floating in the head. Anything disconnected and under five cubic centimetres is that,
    not a part - a real one is fifty at the smallest - and it is named as it goes.
    """
    parts = mesh.split(only_watertight=False)
    if len(parts) < 2:
        return mesh
    main = max(parts, key=lambda c: abs(c.volume))
    keep = [c for c in parts if c is main or abs(c.volume) >= limit]
    for c in parts:
        if c not in keep:
            b = c.bounds.mean(axis=0)
            print(f"       {name}: {abs(c.volume) / 1e3:.2f} cm3 of loose skin at "
                  f"({b[0]:.0f}, {b[1]:.0f}, {b[2]:.0f}) dropped")
    return keep[0] if len(keep) == 1 else union(*keep) if len(keep) > 1 else mesh


def unclaimed():
    """Interface parts the mechanism declares that this module would not union into anything."""
    try:
        import mech.base, mech.head, mech.torso, mech.turntable  # noqa: F401
        from mech import INTERFACES
    except Exception as exc:
        print(f"      could not read the mechanism's registry ({exc.__class__.__name__}); "
              f"not checking for parts left out")
        return ()
    named = {n for names in INTERFACES.values() for n in names}
    missing = sorted(named - set(INTO))
    # One that is registered but not built is a part on its way out of the mechanism - the fan
    # frame was, while the fan moved under the deck - so it is said and not raised on.
    gone = [n for n in missing if not (STL / f"{n}.stl").exists()]
    for n in gone:
        print(f"      {n} still declares a shell section in mech/ but is not built; ignored")
    return tuple(n for n in missing if n not in gone)


def main():
    STL.mkdir(parents=True, exist_ok=True)
    missed = unclaimed()
    if missed:
        raise RuntimeError(f"{', '.join(missed)} declare a shell section in mech/ but this "
                           f"module does not know where to put them; add them to INTO")
    grown = trimesh.load(CAD / "out" / "statue" / "cavity_grown.stl")
    print(f"assemble cavity_grown {grown.volume / 1e6:.2f} L; sections from {RAW}")
    for name in SECTIONS:
        t0 = time.time()
        mesh = trimesh.load(RAW / f"{name}.stl")
        raw_volume = mesh.volume
        parts = blanks(name, mesh, grown)
        if parts:
            mesh = union(mesh, *parts)
        mesh = debris(openings(name, mesh), name)
        back = write(mesh, STL / f"{name}.stl", quiet=True,
                     label=f"  raw {raw_volume / 1e3:.1f} + {len(parts)} parts, {time.time() - t0:.1f} s")
        if max(back.extents) > P.BED:
            raise RuntimeError(f"{name} is {max(back.extents):.1f} mm across; the bed is {P.BED}")
        if back.body_count != 1:
            print(f"       {name}: {back.body_count} bodies - it needs something to join them")


if __name__ == "__main__":
    main()
