"""How thick the shell actually is, measured off the two meshes the statue stage writes.

`WALL` is what SOLIDIFY was asked for and the median says it got it, but a median is not what
cracks on the bed. The shell is an inward offset of a 200 000-triangle reconstruction, and an
offset surface folds in on itself wherever the skin's own curvature is tighter than the offset -
along the skirt's hem, between the beard's strands. Where it folds, the difference that makes
the cavity eats into the wall, and the first build measured here had patches of literally zero.
At a 0.6 mm nozzle anything under about 1.2 mm is one bead or a gap: a pinhole in the boot.

So the arbiter is the distance from the cavity's surface to the skin, sampled evenly over the
whole inner surface, and three numbers are held:

  * the thinnest sample is at least `WALL_MIN`, which is the floor the wall may never go under;
  * under `WALL - 0.4` is a rounding error's worth of the surface, not a region;
  * the median is still `WALL`, so a fix that merely fattened the whole shell fails here.

The last one matters: the cavity is what every part is fitted against (`test_fit.py`), and
buying a minimum by moving the whole inner surface inward would take the room away from the
mechanism instead of from the folds.
"""
from pathlib import Path

import numpy as np
import pytest
import params as P

OUT = Path(__file__).resolve().parents[1] / "out" / "statue"
CAVITY = OUT / "cavity.stl"
OUTER = OUT / "outer.stl"
SAMPLES = 25000

pytestmark = pytest.mark.skipif(not (CAVITY.exists() and OUTER.exists()),
                                reason="the statue stage has not written out/statue/ yet")


@pytest.fixture(scope="module")
def thickness():
    """The wall under every one of SAMPLES points spread evenly over the inner surface."""
    import trimesh
    cavity = trimesh.load_mesh(str(CAVITY))
    skin = trimesh.load_mesh(str(OUTER))
    pts, _ = trimesh.sample.sample_surface_even(cavity, SAMPLES, seed=7)
    # exact point-to-triangle, not a nearest neighbour in a cloud of samples: a cloud only ever
    # overstates the distance, which is the direction that hides a thin patch.
    _, d, _ = trimesh.proximity.closest_point(skin, pts)
    return pts, d


def histogram(d):
    edges = [0.0, 0.8, 1.2, 1.6, 2.0, 2.2, 2.4, 2.6, 1e9]
    n, _ = np.histogram(d, bins=edges)
    rows = [f"{lo:.1f}-{hi:.1f} mm: {c:6d}  {100 * c / len(d):6.3f} %"
            for lo, hi, c in zip(edges, edges[1:], n)]
    return (f"{len(d)} samples  min {d.min():.3f}  p1 {np.percentile(d, 1):.3f}  "
            f"median {np.median(d):.3f}  max {d.max():.3f}\n" + "\n".join(rows))


def test_the_wall_is_never_thinner_than_the_floor(thickness):
    """No pinholes. The 0.1 is the sampler's own reach, not slack in the shape."""
    pts, d = thickness
    worst = pts[np.argmin(d)]
    assert d.min() >= P.WALL_MIN - 0.1, (
        f"thinnest wall {d.min():.3f} mm at "
        f"({worst[0]:.1f}, {worst[1]:.1f}, {worst[2]:.1f})\n{histogram(d)}")


def test_almost_none_of_the_wall_is_thin(thickness):
    """A fold may round a facet's worth off the wall; it may not thin a patch of it."""
    _, d = thickness
    thin = float((d < P.WALL - 0.4).mean())
    assert thin < 0.01, (f"{100 * thin:.3f} % of the inner surface is under "
                         f"{P.WALL - 0.4} mm\n{histogram(d)}")


def test_the_wall_was_not_simply_fattened(thickness):
    """The cavity is the mechanism's room. Thickening the folds may not cost it anywhere else."""
    _, d = thickness
    assert abs(float(np.median(d)) - P.WALL) <= 0.15, (
        f"median wall {np.median(d):.3f} mm, not {P.WALL}\n{histogram(d)}")
