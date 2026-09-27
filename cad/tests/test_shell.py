"""What the assembled shell has to be true of. Skipped until `build.py statue assemble` has run.

These are slow by the standards of the rest of the suite - several run manifold booleans on a
quarter of a million triangles - so every mesh is loaded once per session and the derived solids,
the bell above all, are cached with it.

The shell is now the statue: a reconstruction hollowed and cut into fixed pieces - the two base
halves, the belt ring, the collar over it, two side panels with the sleeves on them, two mitten
caps - and a turning unit, beard, head and hat glued into one, that pans and nods on the spider.
Most of what follows is about that unit: it has to turn to its stops without touching anything,
it has to go on over the spider, and the jet has to leave it. test_pose.py poses the whole
machine; here the unit is panned at nod 0.
"""
import itertools
import math
from pathlib import Path

import numpy as np
import pytest
import trimesh

import params as P

CAD = Path(__file__).resolve().parents[1]
STL = CAD / "out" / "stl"
STATUE = CAD / "out" / "statue"
ENGINE = "manifold"
SECTIONS = tuple(P.PRINTED_SECTIONS)
BELL = ("beard_left", "beard_right", "head", "hat")
FIXED = ("base_left", "base_right", "hand_left", "hand_right", "torso", "collar", "panel_left", "panel_right")
# Sections are cut from one shell along planes, so neighbours share faces and no volume. The
# budget is for the two microns each pinched vertex was moved by before the file was written.
SHARED_MM3 = 5.0

pytestmark = pytest.mark.skipif(not (STL / "torso.stl").exists() or not (STATUE / "cavity_grown.stl").exists(),
                                reason="run `build.py mech statue assemble` first")


@pytest.fixture(scope="session")
def sections():
    return {n: trimesh.load(STL / f"{n}.stl") for n in SECTIONS}


@pytest.fixture(scope="session")
def bell(sections):
    """Beard, face and hat as the one solid that turns."""
    return trimesh.boolean.union([sections[n] for n in BELL], engine=ENGINE)


@pytest.fixture(scope="session")
def still(sections):
    """Everything that does not turn, as one solid."""
    return trimesh.boolean.union([sections[n] for n in FIXED], engine=ENGINE)


def volume_of(mesh):
    return 0.0 if mesh is None or mesh.is_empty else abs(mesh.volume)


def clash(a, b):
    return volume_of(trimesh.boolean.intersection([a, b], engine=ENGINE))


def turned(mesh, deg):
    out = mesh.copy()
    out.apply_transform(trimesh.transformations.rotation_matrix(math.radians(deg), (0.0, 0.0, 1.0)))
    return out


def hits(mesh, origin, direction, limit=None):
    """Where a ray first meets a mesh, as a distance, or None."""
    loc, _, _ = mesh.ray.intersects_location(np.array([origin], float), np.array([direction], float))
    if not len(loc):
        return None
    d = min(float(np.linalg.norm(np.array(p) - np.array(origin))) for p in loc)
    return d if limit is None or d <= limit else None


# --- the pieces themselves --------------------------------------------------------------------
@pytest.mark.parametrize("name", SECTIONS)
def test_every_section_is_a_solid(sections, name):
    m = sections[name]
    assert m.is_watertight, f"{name} is not watertight"
    assert m.is_winding_consistent, f"{name} has inconsistent winding"
    assert m.volume > 0.0, f"{name} has no volume"
    assert m.body_count == 1, f"{name} is {m.body_count} bodies, not one printable piece"


@pytest.mark.parametrize("name", SECTIONS)
def test_every_section_fits_the_bed(sections, name):
    e = sections[name].extents
    assert max(e) <= P.BED, f"{name} is {max(e):.1f} mm across; the bed is {P.BED}"


@pytest.mark.parametrize("pair", sorted(itertools.combinations(SECTIONS, 2)))
def test_no_two_sections_share_a_millimetre(sections, pair):
    a, b = pair
    lo_a, hi_a = sections[a].bounds
    lo_b, hi_b = sections[b].bounds
    if not (np.all(lo_a <= hi_b + 1.0) and np.all(lo_b <= hi_a + 1.0)):
        return                                    # their bounding boxes do not even meet
    v = clash(sections[a], sections[b])
    assert v <= SHARED_MM3, f"{a} and {b} share {v:.1f} mm3"


# --- the interface parts ----------------------------------------------------------------------
def test_every_interface_part_is_welded_into_its_section(sections):
    """What the assembler clipped into a section has to be inside that section."""
    import assemble as A

    grown = trimesh.load(STATUE / "cavity_grown.stl")
    seen = 0
    for name, targets in A.INTO.items():
        if not (STL / f"{name}.stl").exists():
            continue
        for target in targets:
            raw = trimesh.load(STATUE / "raw" / f"{target}.stl")
            printed = (trimesh.boolean.union([sections[h] for h, _ in P.FITTING_SPLIT[target]], engine=ENGINE)
                       if target in P.FITTING_SPLIT else sections[target])
            for piece, _ in A.blanks(target, raw, grown):
                seen += 1
                outside = volume_of(trimesh.boolean.difference(
                    [piece, printed], engine=ENGINE))
                assert outside <= 0.02 * abs(piece.volume) + 50.0, (
                    f"{name}: {outside / 1e3:.2f} cm3 of it stands outside {target}")
    assert seen, "no interface part was found at all"


# --- the openings -----------------------------------------------------------------------------
def test_the_window_is_open(sections):
    z = P.Z_LENS + P.WINDOW_Z_BIAS
    assert hits(sections["torso"], (0.0, P.CAM_Y, z), (1.0, 0.0, 0.0)) is None, \
        "the camera looks at the inside of the coat"
    for dy, dz in ((P.WINDOW_W / 2 + 6.0, 0.0), (-P.WINDOW_W / 2 - 6.0, 0.0),
                   (0.0, -P.WINDOW_H / 2 - 8.0)):
        assert hits(sections["torso"], (0.0, P.CAM_Y + dy, z + dz), (1.0, 0.0, 0.0)) is not None, \
            "the window is bigger than it was asked to be"
    # above it there is barely any ring left: the window's top edge and the ring's top are
    # 1.7 mm apart, which is the thinnest the fixed shell gets anywhere.
    top = z + P.WINDOW_H / 2
    assert P.Z_TURN - P.TURN_GAP - top >= 1.0, (
        f"only {P.Z_TURN - P.TURN_GAP - top:.1f} mm of coat is left over the window")


def test_the_intake_is_open(sections):
    assert hits(sections["torso"], (0.0, P.VENT_IN_Y, P.Z_VENT_IN), (-1.0, 0.0, 0.0)) is None, \
        "the intake is blocked"


def test_the_exhaust_path_is_open(sections):
    """The fan blows up through the deck; the air goes up through the dome's bore into the head
    and out down the 2 mm seam between the collar's sphere (98 from C) and the unit's (100). So
    the bore is open on the axis, and the seam is air - in no section - all the way round at the
    height of the beard's back, 20 degrees above C."""
    for name in FIXED + BELL:
        assert hits(sections[name], (0.0, 0.0, 400.0), (0.0, 0.0, 1.0), limit=60.0) is None, \
            f"{name} closes the dome's bore"
    r = P.NECK_SPHERE_R - P.TURN_GAP / 2
    e = math.radians(20.0)
    pts = np.array([(r * math.cos(e) * math.cos(math.radians(a)), r * math.cos(e) * math.sin(math.radians(a)),
                     P.Z_NOD + r * math.sin(e)) for a in range(0, 360, 5)])
    for name in FIXED + BELL:
        inside = sections[name].contains(pts)
        assert not inside.any(), f"{name} fills the seam at {np.flatnonzero(inside) * 5} deg"


def test_the_mouth_is_open_in_front_of_the_nozzle(sections):
    """The mouth is cut through the skin in front of the holder, and the holder's bore behind it
    is the nozzle's own diameter less its press: a ray down the axis from the nozzle's back leaves
    the head, and one at the mouth's own radius does not get past the holder."""
    head = sections["head"]
    back = P.NOZZLE_TIP_X - P.NOZZLE_L + 0.5
    assert hits(head, (back, 0.0, P.Z_MOUTH), (1.0, 0.0, 0.0)) is None, "the mouth is blocked"
    for dy, dz in ((0.0, P.MOUTH_D / 2 - 0.3), (P.MOUTH_D / 2 - 0.3, 0.0)):
        assert hits(head, (back, dy, P.Z_MOUTH + dz), (1.0, 0.0, 0.0)) is None, "the mouth is too small"
    assert hits(head, (back, 0.0, P.Z_MOUTH + P.NOZZLE_D / 2 + 0.2), (1.0, 0.0, 0.0), limit=6.0) is not None, \
        "the holder's bore is wider than the nozzle"


def test_the_head_screws_reach_the_spider(sections):
    """Four radial screws through the head, into the spider that carries the unit."""
    spider = trimesh.load(STL / "spider.stl")
    head = sections["head"]
    # the screw's own axis runs down the insert's bore and stops on its floor; a ray beside it
    # lands on the boss's face, and that is what tells a boss from nothing at all
    floor = P.SPIDER_BOSS_R - P.INSERT_DEPTH
    for deg in P.HEAD_SCREW_ANGLES:
        a = math.radians(deg)
        out = (math.cos(a), math.sin(a), 0.0)
        start = (300.0 * out[0], 300.0 * out[1], P.HEAD_SCREWS_Z)
        inward = (-out[0], -out[1], 0.0)
        assert hits(head, start, inward) is None, f"the screw at {deg:.0f} deg has no hole"
        d = hits(spider, start, inward)
        assert d is not None, f"the screw at {deg:.0f} deg meets no boss on the spider"
        assert abs((300.0 - d) - floor) <= 0.5, \
            f"the screw at {deg:.0f} deg bottoms at r {300.0 - d:.1f}, not on its insert's floor {floor:.1f}"
        beside = (start[0], start[1], P.HEAD_SCREWS_Z + P.INSERT_D / 2 + 0.5)
        f = hits(spider, beside, inward)
        assert f is not None and 300.0 - f >= P.SPIDER_BOSS_R - 1.0, \
            f"the screw at {deg:.0f} deg has no boss under its head"


# --- the bell turns ----------------------------------------------------------------------------
SWEEP = tuple(range(-int(P.PAN_STOP_DEG), int(P.PAN_STOP_DEG) + 1, 5))


@pytest.fixture(scope="session")
def fixed_mech():
    """Every printed mechanism part that does not turn and stands over the bell's rim, placed.

    Read out of out/placements.json so this is not a second copy of where the parts go or of
    what moves. The stop pin is printed once and fitted twice, so its mirror is added the way
    assembly() does.
    """
    import json
    places = json.loads((CAD / "out" / "placements.json").read_text())
    out = {}
    for name, info in sorted(places.items()):
        if info.get("moves", "fixed") != "fixed" or info.get("section") or not (STL / f"{name}.stl").exists():
            continue
        m = trimesh.load(STL / f"{name}.stl")
        m.apply_transform(np.array(info["matrix"], float))
        if m.bounds[1][2] <= P.Z_TURN:
            continue                                   # it is under the bell, not inside it
        out[name] = m
        if name == "stop_pin":
            twin = m.copy()
            twin.apply_transform(np.diag([1.0, -1.0, 1.0, 1.0]))
            out["stop_pin_mirrored"] = twin
    assert "deck_ring" in out and "deck" in out, sorted(out)
    return out


NEAR_BELL = P.NECK_SPHERE_R - 15.0


def bell_gap(query, mesh, deg):
    """The least distance from `mesh` to the bell with the bell turned `deg`, in millimetres.

    The bell is rigid and its query tree costs seconds to build, so it is built once at rest
    and the points are turned the other way instead. Only the points that could be nearest are
    asked about.
    """
    v = mesh.vertices
    # the bell is the shell outside the sphere NECK_SPHERE_R about C, so a point nearer C than
    # NEAR_BELL is that much less far from it, and only the points past it are asked about
    near = v[(np.linalg.norm(v - np.array([0.0, 0.0, P.Z_NOD]), axis=1) >= NEAR_BELL)
             & (v[:, 2] >= P.Z_TURN - 10.0)]
    if not len(near):
        return math.inf
    a = math.radians(-deg)
    c, s = math.cos(a), math.sin(a)
    spun = near @ np.array([[c, s, 0.0], [-s, c, 0.0], [0.0, 0.0, 1.0]])
    return float(query.on_surface(spun)[1].min())


def test_the_bell_turns_over_the_fixed_mechanism(bell, fixed_mech):
    """The bell against the mechanism it turns over, swept, not inferred from a radius.

    test_mech holds the cage inside the narrowest radius the statue's reach table has over the
    bell's height, which is a proxy: the real question is what the bell's own inner wall does as
    it comes round, and this asks it. Every 5 degrees of the pan travel, the built bell is turned
    and intersected with each fixed part, and then measured. Everything fixed under the collar is
    inside its socket, so the least gap is at least the socket's 2 mm seam plus the margin the
    parts keep inside it.
    """
    together = trimesh.boolean.union(list(fixed_mech.values()), engine=ENGINE)
    for deg in SWEEP:
        v = clash(turned(bell, deg), together)
        assert v < 1e-6, f"the bell fouls the fixed mechanism by {v:.1f} mm3 at {deg:+.0f} deg"
    query = trimesh.proximity.ProximityQuery(bell)
    gaps = {name: min((bell_gap(query, part, deg), deg) for deg in SWEEP[::2] + (SWEEP[-1],))
            for name, part in fixed_mech.items()}
    said = ", ".join(f"{n} {g:.2f} mm at {d:+.0f}" for n, (g, d) in sorted(gaps.items()) if g < math.inf)
    assert min(g for g, _ in gaps.values()) >= 1.0, said


def test_the_bell_clears_the_turntable_deck(bell, fixed_mech):
    """The deck used to be trimmed to the statue's section at one pan angle, and the bell swept
    that section 130 degrees round over it: 1.8 cm3 at the +65 stop. Now the unit is outside the
    sphere NECK_SPHERE_R about C and the deck inside the collar's socket, 94.1 from C, so no pan
    and no nod can bring them together - measured here, at the whole pan travel, and the least
    gap is the seam's 2 mm and the socket's wall and the deck's margin: 6 mm or more."""
    for deg in SWEEP:
        v = clash(turned(bell, deg), fixed_mech["deck"])
        assert v < 1e-6, f"the bell fouls the deck by {v:.0f} mm3 at {deg:+.0f} deg"
    query = trimesh.proximity.ProximityQuery(bell)
    g = min(bell_gap(query, fixed_mech["deck"], deg) for deg in SWEEP)
    assert g >= P.TURN_GAP + P.WALL + P.DECK_SOCKET_MARGIN - 0.2, g


@pytest.mark.parametrize("deg", (-P.PAN_STOP_DEG, -30.0, 0.0, 30.0, P.PAN_STOP_DEG))
def test_the_bell_turns_to_its_stops(bell, still, deg):
    v = clash(turned(bell, deg), still)
    assert v <= SHARED_MM3, f"the bell fouls the fixed shell by {v:.1f} mm3 at {deg:+.0f} deg"


def test_the_bells_rim_stays_between_its_neighbours(sections, bell):
    lo = bell.bounds[0][2]
    assert lo >= P.Z_TURN - 0.01, f"the bell dips to z {lo:.1f}, under Z_TURN"
    outside = trimesh.boolean.intersection(
        [bell, trimesh.creation.box(extents=(2000.0, 2000.0 - 2 * P.PANEL_Y, 2000.0),
                                    transform=trimesh.transformations.translation_matrix(
                                        (0.0, 1000.0 + P.PANEL_Y, 0.0)))], engine=ENGINE)
    if volume_of(outside) > SHARED_MM3:
        assert outside.bounds[0][2] >= P.PANEL_TOP - 0.01, (
            f"the bell reaches z {outside.bounds[0][2]:.1f} outside the panels, "
            f"whose tops are at {P.PANEL_TOP}")


# --- the jet -----------------------------------------------------------------------------------
def test_the_jet_leaves_the_statue(sections):
    """The jet leaves the nozzle's tip along +X in a JET_HALF_DEG cone and meets nothing of the
    statue - the beard and the moustache least of all. The nozzle and the beard nod together, so
    one look at rest is every nod; and the fixed coat is all below the mouth and behind it."""
    tip = np.array([P.NOZZLE_TIP_X, 0.0, P.Z_MOUTH])
    a = math.radians(P.JET_HALF_DEG)
    dirs = [(1.0, 0.0, 0.0)] + [(math.cos(a), math.sin(a) * math.cos(t), math.sin(a) * math.sin(t))
                                for t in np.radians(np.arange(0.0, 360.0, 30.0))]
    origins = np.tile(tip, (len(dirs), 1))
    for name, m in sections.items():
        loc, _, _ = m.ray.intersects_location(origins, np.array(dirs))
        assert not len(loc), f"the jet's cone hits {name} at {np.round(loc[:3], 1).tolist()}"
