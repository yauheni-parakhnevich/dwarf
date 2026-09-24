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
from statue import GROW

OUT = Path(__file__).resolve().parents[1] / "out" / "statue"
CAVITY = OUT / "cavity.stl"
GROWN = OUT / "cavity_grown.stl"
OUTER = OUT / "outer.stl"
SAMPLES = 25000

pytestmark = pytest.mark.skipif(not (CAVITY.exists() and GROWN.exists() and OUTER.exists()),
                                reason="the statue stage has not written out/statue/ yet")


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
