"""The whole machine posed: pan and nod together, the printed parts, the bought ones and the shell.

The head pans +-65 and nods -15..+5 about one point. At every pose of the grid below, what moves
and what does not share nothing: the turning unit and everything that nods with it (the stem,
the spider, the holder in the head, the horn, the pin, the stop lug, the nozzle, the tube), the
plate and everything that pans with it (its hub and yoke, the hub ring, the nod servo, the
bushing), and the pan linkage, against the fixed mechanism, the fixed bought parts and the fixed
shell - the collar's socket above all. What pans and what nods touch each other only where they are
meant to: the pin in its bushing, the horn on the servo's spline, the lug's sleeve on the hub.

And then it is measured: the least gap to each neighbour that matters, at the worst pose, and
the assertion says them all.
"""
import itertools
import math

import numpy as np
import pytest
import trimesh

import params as P
import machine as M

pytestmark = pytest.mark.skipif(not (M.built() and M.shell_built()),
                                reason="run `build.py` (mech, statue, assemble) first")

PANS = (-P.PAN_STOP_DEG, -30.0, 0.0, 30.0, P.PAN_STOP_DEG)
NODS = (P.NOD_STOP[0], P.NOD_RANGE[0], -8.0, 0.0, P.NOD_RANGE[1], P.NOD_STOP[1])   # the stops too:
                                                                            # the head can reach them
GRID = tuple(itertools.product(PANS, NODS))
TOUCH = 0.05          # mm3: two faces that are meant to touch leave a sliver this big in a boolean


@pytest.fixture(scope="module")
def rig():
    """Every mesh in the machine, grouped by how it moves, with the fixed ones in one union."""
    iface = M.interfaces()
    parts = {}
    for name, m in M.mech_meshes().items():
        if name in iface:
            continue                                   # it is in its shell section
        parts[name] = (m, M.how_it_moves(name.replace("_mirrored", "")))
    parts.update(M.bought())
    for name, m in M.sections().items():
        parts[name] = (m, "nods" if name in ("beard_left", "beard_right", "head", "hat") else "fixed")
    # nothing that moves comes below the tube's lowest point, z 300: the fixed parts wholly under
    # it (the base, the wet zone, most of the dry one) are left out of the union that is posed against
    low = min(M.tube(0.0, 0.0).bounds[0][2], P.Z_LINK_BOTTOM) - 5.0
    groups = {how: M.manifold(M.union([m for m, h in parts.values()
                                       if h == how and (how != "fixed" or m.bounds[1][2] > low)]))
              for how in ("fixed", "pans", "nods")}
    groups["servo_crank"] = M.manifold(parts["servo_crank"][0])
    groups["pan_link"] = M.manifold(parts["pan_link"][0])
    return {"parts": parts, "fixed": groups["fixed"], "groups": groups}


def posed_group(rig, how, pan, nod):
    """A group is rigid, so it is united once at rest, as a Manifold, and only moved here."""
    return M.moved(rig["groups"][how], how, pan, nod)


@pytest.mark.parametrize("pan,nod", GRID)
def test_the_machine_poses_without_touching(rig, pan, nod):
    """At this pose nothing that moves is in anything that does not, and what pans is not in what
    nods but for the parts made to touch."""
    fixed = rig["fixed"]
    nods = posed_group(rig, "nods", pan, nod)
    pans = posed_group(rig, "pans", pan, nod)
    tube = M.manifold(M.tube(pan, nod))
    crank = posed_group(rig, "servo_crank", pan, nod)
    link = posed_group(rig, "pan_link", pan, nod)
    said = []
    for what, a, b, allowed in (("what nods / what is fixed", nods, fixed, 0.0),
                                ("what pans / what is fixed", pans, fixed, TOUCH),
                                ("what pans / what nods", pans, nods, TOUCH),
                                ("the tube / what is fixed", tube, fixed, 0.0),
                                ("the tube / what pans", tube, pans, 0.0),
                                ("the tube / what nods", tube, nods, 0.0),
                                ("the crank / what pans", crank, pans, 0.0),
                                ("the crank / what nods", crank, nods, 0.0),
                                ("the link / what nods", link, nods, 0.0),
                                ("the link / the crank", link, crank, TOUCH)):
        v = M.mvolume(a, b)
        if v > allowed + 1e-6:
            said.append(f"{what}: {v:.3f} mm3")
    # the link turns under the plate's pin boss and the crank's, and the crank hangs on the pan
    # servo's horn: those faces touch
    for what, a, b in (("the link / what pans", link, pans), ("the link / what is fixed", link, fixed),
                       ("the crank / what is fixed", crank, fixed)):
        v = M.mvolume(a, b)
        if v > TOUCH:
            said.append(f"{what}: {v:.3f} mm3")
    assert not said, f"pan {pan:+.0f}, nod {nod:+.0f}: " + "; ".join(said)


# the neighbours measured, with the least gap each must keep, and why
NEIGHBOURS = (
    ("nod_servo", "deck_ring", 3.0, "the cage's legs; the study had 4.6"),
    ("nod_servo", "pan_link", 2.0, "the link's plane passes under the yoke"),
    ("nod_servo", "servo_crank", 2.0, ""),
    ("nod_servo", "pan_servo", 2.0, ""),
    ("nod_servo", "fan", 2.0, ""),
    ("nod_servo", "deck", 2.0, ""),
    ("plate", "deck_ring", 2.0, ""),
    ("plate", "deck", 0.25, "the column in its arc slot, CLEAR each side"),
    ("plate", "bearing_cap", 0.4, ""),
    ("stem", "plate", P.COLLAR_FIT - 0.05, "the collar in the +Y cheek's bore, COLLAR_FIT; the blade "
                            "between the cheeks and the neck's swing in the slot are wider"),
    ("stem", "hub_ring", P.NOD_CLEAR, ""),
    ("stem", "collar", 1.5, "the dome's bore"),
    ("spider", "collar", 1.5, "the dome's bore and its sphere"),
    ("tube", "collar", 1.5, ""),
    ("tube", "plate", 1.0, "the loop behind the yoke"),
    ("tube", "pan_link", 2.0, ""),
    ("beard_left", "collar", P.TURN_GAP - 0.1, "the seam"),
    ("beard_right", "collar", P.TURN_GAP - 0.1, "the seam"),
    ("head", "collar", P.TURN_GAP - 0.1, "the seam at the nape"),
    ("beard_left", "torso", 1.5, "the unit's flat bottom over the ring's top"),
    ("beard_right", "torso", 1.5, "the unit's flat bottom over the ring's top"),
    ("beard_left", "panel_left", 1.5, "the sleeve"),
    ("beard_right", "panel_right", 1.5, "the sleeve"),
    ("stop_lug", "plate", P.STOP_SLOT_FIT - 0.05, "STOP_SLOT_FIT each side in its arc slot, inside the nod range"),
)


def test_what_is_in_the_turning_shell_is_placed_as_turning():
    """out/placements.json says how each part moves, and the scene and previews draw it so: an
    interface part in the beard, the head or the hat nods with them."""
    import json
    places = json.loads((M.CAD / "out" / "placements.json").read_text())
    for name, info in places.items():
        if info["section"] in ("beard", "head", "hat"):
            assert info["moves"] == "nods", (name, info["moves"])
        elif info["section"]:
            assert info["moves"] == "fixed", (name, info["moves"])


def test_the_beards_halves_have_no_fins(rig):
    """The beard is cut in two down its middle, stepping to y +2.5 in front of x 80 where the locks
    meet in a web too thin to halve. A cut that halved it left a face of no thickness on the right
    half's cut, 187 mm2 of it, pointing into the part; manifold's min_gap reads such a fin as 0."""
    k = P.BEARD_KERF / 2
    xs, ys = P.BEARD_STEP
    for name, side in (("beard_left", 1.0), ("beard_right", -1.0)):
        m = rig["parts"][name][0]
        c, n = m.triangles_center, m.face_normals
        bad = 0.0
        for plane, where in ((side * k, c[:, 0] < xs), (ys + side * k, c[:, 0] > xs)):
            on = (np.abs(c[:, 1] - plane) < 1e-3) & where
            wrong = on & (n[:, 1] * side > 0.5)            # a cap that faces into its own half
            bad += float(m.area_faces[wrong].sum())
        assert bad < 1.0, f"{name}: {bad:.1f} mm2 of fin on its cut"


def test_the_seam_is_two_millimetres_everywhere(rig):
    """The turning unit against the collar needs no pose: a rotation about C keeps every distance
    from C, so the least distance between them at any pose is at least the nearest the unit comes
    to C less the furthest the collar reaches from it. Measured on every vertex of both: the unit,
    the holder in the head and the beard's tongues included, is 100 from C or more; the collar over
    the joint, 98 or less. Its tabs under the joint (98.9 at z 297) face the ring, not the unit,
    whose bottom never comes under Z_TURN - that is the statue stage's sweep."""
    c = np.array([0.0, 0.0, P.Z_NOD])
    parts = rig["parts"]

    def points(m):
        """Its vertices and 20 000 points spread over its surface: a sliver between vertices, or
        a face that is nowhere near one, is not missed."""
        pts, _ = trimesh.sample.sample_surface_even(m, 20000, seed=11)
        return np.vstack([m.vertices, pts])
    unit = min(np.linalg.norm(points(parts[n][0]) - c, axis=1).min() for n in P.TURNING_SECTIONS)
    v = points(parts["collar"][0])
    above = v[v[:, 2] >= P.Z_TURN - P.TURN_GAP]          # the tabs under the joint are inside the ring,
    collar = np.linalg.norm(above - c, axis=1).max()      # under the unit's flat bottom, not facing it
    assert unit - collar >= P.TURN_GAP - 0.05, (unit, collar)
    for n in P.TURNING_SECTIONS:                            # and nothing of the collar is outside it
        assert M.overlap(parts[n][0], parts["collar"][0]) < 1e-6, n


@pytest.mark.slow
def test_the_least_gaps_at_the_worst_poses(rig):
    """Every pair in NEIGHBOURS, measured at every pose of the grid: the least gap, where it is,
    and that it keeps its minimum. The message lists them all, worst first. Measured with
    manifold3d's min_gap out to 10 mm, each part converted once and only moved per pose."""
    parts = dict(rig["parts"])
    names = {n for pair in NEIGHBOURS for n in pair[:2] if n != "tube"}
    man = {n: M.manifold(parts[n][0]) for n in names}
    worst = {}
    for pan, nod in GRID:
        tube = M.manifold(M.tube(pan, nod))
        for a, b, _, _ in NEIGHBOURS:
            if a == "stop_lug" and nod in P.NOD_STOP:
                continue                    # at the stops the lug is on its stop: test_mech's
            if a in P.TURNING_SECTIONS and (abs(pan) not in (0.0, P.PAN_STOP_DEG) or nod not in (P.NOD_STOP[0], 0.0, P.NOD_STOP[1])):
                continue                    # the shell's pieces, 80 000 faces each: at the stops and the middle
            if a in P.TURNING_SECTIONS and b == "collar" and (pan, nod) != (0.0, 0.0):
                continue                    # against the collar, at rest: a rotation about C keeps the
                                            # distance, which test_the_seam_... proves for every pose
            ma = tube if a == "tube" else M.moved(man[a], parts[a][1], pan, nod)
            mb = M.moved(man[b], parts[b][1], pan, nod)
            d = M.mgap(ma, mb, reach=10.0)
            if d < worst.get((a, b), (math.inf,))[0]:
                worst[(a, b)] = (d, pan, nod)
    lines = [(f"{a} / {b}: {d:.2f} mm at pan {p:+.0f} nod {n:+.0f}" if d < 10.0 else f"{a} / {b}: over 10 mm")
             for (a, b), (d, p, n)
             in sorted(worst.items(), key=lambda t: t[1][0])]
    report = "\n".join(lines)
    print("\n" + report)
    for a, b, need, why in NEIGHBOURS:
        d = worst.get((a, b), (math.inf,))[0]
        assert d >= need - 0.01, f"{a} / {b} comes within {d:.2f} mm, under {need} ({why})\n{report}"
