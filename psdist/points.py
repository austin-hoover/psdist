import collections
from typing import Callable
from typing import Union

import numpy as np
import scipy.interpolate
import scipy.optimize
import scipy.special
import scipy.stats

from . import ap
from . import cov as cov_utils
from . import utils
from .cov import cov_to_corr
from .cov import norm_matrix_from_twiss_2x2
from .utils import array_like
from .utils import coords_from_edges
from .utils import random_choice_no_replacement


# Analysis
# --------------------------------------------------------------------------------------
def centroid(points: np.ndarray) -> np.ndarray:
    return np.mean(points, axis=0)


def covariance_matrix(points: np.ndarray) -> np.ndarray:
    return np.cov(points.T)


def correlation_matrix(points: np.ndarray) -> np.ndarray:
    return cov_to_corr(covariance_matrix(points))


def get_radii(points: np.ndarray) -> np.ndarray:
    return np.linalg.norm(points, axis=1)


def get_ellipsoid_radii(points: np.ndarray) -> np.ndarray:
    sigma = covariance_matrix(points)
    sigma_inv = np.linalg.inv(sigma)

    def function(point):
        return np.sqrt(np.linalg.multi_dot([point.T, sigma_inv, point]))

    return transform(points, function)


def enclosing_sphere_radius(points: np.ndarray, fraction: float = 1.0) -> float:
    """Scales sphere until it contains some fraction of points."""
    radii = np.sort(get_radii(points))
    index = int(np.round(points.shape[0] * fraction)) - 1
    return radii[index]


def enclosing_ellipsoid_radius(points: np.ndarray, fraction: float = 1.0) -> float:
    """Scale the rms ellipsoid until it contains some fraction of points."""
    radii = np.sort(get_ellipsoid_radii(points))
    index = int(np.round(points.shape[0] * fraction)) - 1
    return radii[index]


def find_min_volume_bounding_ellipse(points: np.ndarray, **opt_kws) -> tuple[np.ndarray, float]:
    """Find the minimum-volume bounding ellipse."""

    def normalize(_points: np.ndarray, _alpha: float, _beta: float) -> np.ndarray:
        return transform_linear(_points, norm_matrix_from_twiss_2x2(_alpha, _beta))

    def bounding_ellipse_area(twiss_params: list[float], _points: np.ndarray) -> float:
        (_alpha, _beta) = twiss_params
        return np.max(np.linalg.norm(normalize(_points, _alpha, _beta), axis=1))

    cov = covariance_matrix(points)
    alpha, beta = cov_utils.twiss(cov)
    guess = [alpha, beta]

    result = scipy.optimize.least_squares(
        bounding_ellipse_area,
        guess,
        bounds=([-np.inf, 1.00e-08], [+np.inf, +np.inf]),
        args=(points,),
        **opt_kws,
    )
    (alpha, beta) = result.x
    Vinv = norm_matrix_from_twiss_2x2(alpha, beta)
    V = np.linalg.inv(Vinv)
    emittance = bounding_ellipse_area([alpha, beta], points)
    return (V, emittance)


def get_limits(
    points: np.ndarray,
    rms: float = None,
    pad: float = 0.0,
    zero_center: bool = False,
    share: Union[tuple[int, ...], list[tuple[int, ...]]] = None,
) -> list[tuple[float, float]]:
    """Compute nice limits for binning/plotting.

    Parameters
    ----------
    points: np.ndarray, shape (..., n)
        Particle coordinates.
    rms : float
        If a number is provided, it is used to set the limits relative to the standard
        deviation of the distribution.
    pad : float
        Fractional padding to apply to the limits.
    zero_center : bool
        Whether to center the limits on zero.
    share : tuple[int] or list[tuple[int]]
        Limits are shared between the dimensions in each set. For example, if `share=(0, 1)`,
        axis 0 and 1 will share limits. Or if `share=[(0, 1), (4, 5)]` axis 0/1 will share
        limits, and axis 4/5 will share limits.

    Returns
    -------
    list[tuple[float, float]]
        The limits [(xmin, xmax), (ymin, ymax), ...].
    """
    if points.ndim == 1:
        points = points[:, None]

    if rms is None:
        mins = np.min(points, axis=0)
        maxs = np.max(points, axis=0)
    else:
        means = np.mean(points, axis=0)
        stds = np.std(points, axis=0)
        widths = 2.0 * rms * stds
        mins = means - 0.5 * widths
        maxs = means + 0.5 * widths

    deltas = 0.5 * np.abs(maxs - mins)
    padding = deltas * pad
    mins = mins - padding
    maxs = maxs + padding
    limits = [(_min, _max) for _min, _max in zip(mins, maxs)]

    if share:
        if np.ndim(share[0]) == 0:
            share = [share]
        for axis in share:
            _min = min([limits[i][0] for i in axis])
            _max = max([limits[i][1] for i in axis])
            for i in axis:
                limits[i] = (_min, _max)

    if zero_center:
        mins, maxs = list(zip(*limits))
        maxs = np.max([np.abs(mins), np.abs(maxs)], axis=0)
        limits = list(zip(-maxs, maxs))

    if len(limits) == 1:
        limits = limits[0]
    return limits


limits = get_limits


# Distances (https://journals.aps.org/pre/abstract/10.1103/PhysRevE.106.065302)
# --------------------------------------------------------------------------------------
## - Wasserstein
## - MMD


# Transforms
# --------------------------------------------------------------------------------------


def project(points: np.ndarray, axis: Union[int, tuple[int]]) -> np.ndarray:
    """Axis-aligned projection (points[:, axis])."""
    ndim = points.shape[1]
    if axis is None:
        axis = tuple(np.arange(ndim))
    if array_like(axis) and (len(axis) > ndim):
        raise ValueError("Invalid projection axis.")
    return points[:, axis]


def transform(points: np.ndarray, function: Callable) -> np.ndarray:
    """Apply nonlinear transformation to points."""
    return np.apply_along_axis(lambda point: function(point), 1, points)


def transform_linear(points: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    """Apply linear transformation to points."""
    return np.matmul(points, matrix.T)


def slice_planar(
    points: np.ndarray,
    axis: Union[int, tuple[int]],
    center: np.ndarray = None,
    width: np.ndarray = None,
    limits: list[tuple[float, float]] = None,
    return_indices: bool = False,
):
    """Return points within a planar slice.

    Parameters
    ----------
    points: np.ndarray, shape (..., n)
        Particle coordinates.
    axis : tuple
        Slice axes. For example, (0, 1) will slice along the first and
        second axes of the array.
    center : ndarray, shape (n,)
        The center of the box.
    width : ndarray, shape (d,)
        The width of the box along each axis.
    limits : ndarray, shape (d, 2)
        The (min, max) along each axis. Overrides `center` and `edges` if provided.

    Returns
    -------
    ndarray, shape (?, n)
        The points within the box.
    """
    ndim = points.shape[1]

    if not array_like(axis):
        axis = (axis,)

    if limits is None:
        if not array_like(center):
            center = np.full(ndim, center)
        if not array_like(width):
            width = np.full(ndim, width)
        center = np.array(center)
        width = np.array(width)
        limits = list(zip(center - 0.5 * width, center + 0.5 * width))

    limits = np.array(limits)
    if limits.ndim == 1:
        limits = limits[None, :]

    conditions = []
    for j, (umin, umax) in zip(axis, limits):
        conditions.append(points[:, j] > umin)
        conditions.append(points[:, j] < umax)
    idx = np.logical_and.reduce(conditions)
    
    if return_indices:
        return (points[idx, :], idx)

    return points[idx, :]


def slice_sphere(
    points: np.ndarray,
    axis: Union[int, tuple[int]] = None,
    rmin: float = 0.0,
    rmax: float = None,
    return_indices: bool = False,
) -> np.ndarray:
    """Return points within a spherical shell slice.

    Parameters
    ----------
    points : ndarray, shape (..., n)
        Particle coordinates.
    axis : tuple
        The subspace in which to define the sphere.
    rmin, rmax : float
        Inner/outer radius of spherical shell.

    Returns
    -------
    ndarray, shape (?, d)
        The points within the sphere.
    """
    if rmax is None:
        rmax = np.inf
    radii = get_radii(project(points, axis))
    idx = np.logical_and(radii > rmin, radii < rmax)
    
    if return_indices:
        return (points[idx, :], idx)

    return points[idx, :]


def slice_ellipsoid(
    points: np.ndarray,
    axis: Union[int, tuple[int]] = None,
    rmin: float = 0.0,
    rmax: float = None,
    return_indices: bool = False,
) -> np.ndarray:
    """Return points within an ellipsoidal shell slice.

    The ellipsoid is defined by the covariance matrix of the
    distribution.

    Parameters
    ----------
    points : ndarray, shape (..., n)
        Particle coordinates.
    axis : tuple
        The subspace in which to define the ellipsoid.
    rmin, rmax : list[float]
        Min/max "radius" (x^T Sigma^-1 x). relative to covariance matrix.

    Returns
    -------
    ndarray, shape (?, d)
        Points within the shell.
    """
    if rmax is None:
        rmax = np.inf
    radii = get_ellipsoid_radii(project(points, axis))
    idx = np.logical_and(rmin < radii, radii < rmax)

    if return_indices:
        return (points[idx, :])

    return points[idx, :]


def slice_contour(
    points: np.ndarray,
    axis: Union[int, tuple[int]] = None,
    lmin: float = 0.0,
    lmax: float = 1.0,
    interp: bool = True,
    interp_kws: dict = None,
    hist_kws: dict = None,
    return_indices: bool = False,
):
    """Return points within a contour shell slice.

    The slice is defined by the density contours in the subspace defined by
    `axis`.

    Parameters
    ----------
    points: np.ndarray, shape (..., n)
        Coordinates of n points in d-dimensional space.
    axis : tuple
        The subspace in which to define the density contours.
    lmin, lmax : list[float]
        If `f` is the density in the subspace defined by `axis`, then we select points
         where lmin <= f / max(f) <= lmax.
    interp : bool
        If True, compute the histogram, then interpolate and evaluate the resulting
        function at each point in `X`. Otherwise, keep track of the indices in which
        each point lands when it is binned and accept the point if its bin value is
        within fmin and fmax.
    interp_kws : dict
        Key word arguments passed to `scipy.interpolate.RegularGridInterpolator`.
    hist_kws : dict
        Key word arguments passed to `numpy.histogramdd`.

    Returns
    -------
    ndarray, shape (?, d)
        Points within the shell.
    """
    if hist_kws is None:
        hist_kws = dict()

    if interp_kws is None:
        interp_kws = dict()
    interp_kws.setdefault("method", "linear")
    interp_kws.setdefault("bounds_error", False)
    interp_kws.setdefault("fill_value", 0.0)

    points_proj = project(points, axis)
    hist, edges = histogram(points_proj, **hist_kws)
    hist = hist / np.max(hist)
    coords = [coords_from_edges(e) for e in edges]

    if interp:
        interpolator = scipy.interpolate.RegularGridInterpolator(coords, hist, **interp_kws)
        values = interpolator(points_proj)
        idx = np.logical_and(lmin <= values, values <= lmax)
    else:
        valid_indices = np.vstack(np.where(np.logical_and(lmin <= hist, hist <= lmax))).T
        indices = np.vstack([np.digitize(points_proj[:, i], edges[i]) for i in range(len(axis))]).T
        idx = []
        for i in range(len(indices)):
            if indices[i].tolist() in valid_indices.tolist():
                idx.append(i)

    if return_indices:
        return points[idx, :], idx

    return points[idx, :]


def normalize_2d_projections(points: np.ndarray, scale_emittance: bool = False) -> np.ndarray:
    """Normalize two-dimensional phase space projections.

    This transformation removes linear correlations between x-x', y-y', etc.
    while preserving the rms emittance (rms area). The covariance matrix in
    each 2 x 2 block after the transformation is [[eps_x, 0], [0, eps_x]].

    Parameters
    ----------
    points: np.ndarray, shape (..., n)
        Particle coordinates in n-dimensional phase space.
    scale_emittance : bool
        Whether to scale the coordinates by the square root of the rms emittance.
        This makes each 2 x 2 covariance matrix the identity matrix.

    Returns
    -------
    np.ndarray, shape (..., n)
        Normalized phase space coordinates.
    """
    ndim = points.shape[1]

    if (ndim % 2) != 0:
        raise ValueError("Must have even number of dimensions")

    cov = covariance_matrix(points)
    points_n = np.zeros(points.shape)
    for i in range(0, ndim, 2):
        cov_sub = cov[i : i + 2, i : i + 2]
        (alpha, beta) = cov_utils.twiss(cov_sub)
        points_n[:, i] = points[:, i] / np.sqrt(beta)
        points_n[:, i + 1] = (np.sqrt(beta) * points[:, i + 1]) + (
            alpha * points[:, i] / np.sqrt(beta)
        )
        if scale_emittance:
            emittance = cov_utils.emittance(cov_sub)
            points_n[:, i : i + 2] = points_n[:, i : i + 2] / np.sqrt(emittance)
    return points_n


def decorrelate_x_y_z(points: np.ndarray) -> np.ndarray:
    """Remove cross-plane correlations by permuting (x, x'), (y, y'), (z, z') pairs.

    Parameters
    ----------
    points: np.ndarray, shape (..., n)
        Particle coordinates in n-dimensional phase space.

    Returns
    -------
    np.ndarray, shape (..., n)
        The decorrelated phase space coordinates..
    """
    ndim = points.shape[1]

    if (ndim % 2) != 0:
        raise ValueError("X must have even number of columns.")

    for i in range(0, ndim, 2):
        idx = np.random.permutation(np.arange(points.shape[0]))
        points[:, i : i + 2] = points[idx, i : i + 2]
    return points


def downsample(points: np.ndarray, size: int = None, frac: float = None) -> np.ndarray:
    """Select a random subset of points.

    Parameters
    ----------
    points: np.ndarray, shape (k, n)
        Particle coordinates in n-dimensional space.
    size : int or float
        The number of points to keep.
    frac : float
        Fraction of points to keep.

    Returns
    -------
    ndarray, shape (<= k, n)
        The selected coordinates.
    """
    if size is None:
        size = int(frac * points.shape[0])
    size = min(size, points.shape[0])
    size = int(size)
    idx = random_choice_no_replacement(np.arange(points.shape[0]), size)
    return points[idx, :]


# Density estimation
# --------------------------------------------------------------------------------------


def histogram_bin_edges(
    points: np.ndarray,
    bins: Union[int, str, np.ndarray],
    limits: list[tuple[float, float]] = None,
) -> list[np.ndarray]:
    """Comopute histogram bin edges.

    This function calls `np.histogram_bin_edges` along each axis.
    See [https://numpy.org/doc/stable/reference/generated/numpy.histogram_bin_edges.html]
    """
    if points.ndim == 1:
        return np.histogram_bin_edges(points, bins, limits)

    # `[2, 3, 4, 5]` could mean "2 bins along axis 0, 3 bins along axis 1, ..."
    # or "bin edges [2.0, 3.0, 4.0, 5.0] along each axis". We assume the
    # former if `bins` is a sequence of int and the latter if `bins` is a
    # sequence of float.
    if array_like(bins) and type(bins[0]) is float:
        bins = X.shape[1] * [bins]

    # If a single int/str is provided, apply to all axes.
    if not array_like(bins):
        bins = points.shape[1] * [bins]

    # Same for `limits`. If a (min, max) tuple (or None) is provided, apply
    # to all axes.
    if limits is None or (limits[0] is not None and not array_like(limits[0])):
        limits = points.shape[1] * [limits]

    bin_edges = [
        np.histogram_bin_edges(points[:, i], bins[i], limits[i]) for i in range(points.shape[1])
    ]
    return bin_edges


def histogram(
    points: np.ndarray,
    bins: Union[int, str, np.ndarray],
    limits: list[tuple[float, float]] = None,
    return_bin_centers: bool = False,
) -> tuple[np.ndarray, list[np.ndarray]]:
    """Compute multidimensional histogram."""
    if points.ndim == 1:
        bins = np.histogram_bin_edges(points, bins, limits)
        hist, _ = np.histogram(points, bins=bins)
        if return_bin_centers:
            bins = utils.coords_from_edges(bins)
        return hist, bins

    bin_edges = histogram_bin_edges(points, bins=bins, limits=limits)
    hist, _ = np.histogramdd(points, bin_edges)
    if return_bin_centers:
        bin_centers = [coords_from_edges(e) for e in bin_edges]
        return hist, bin_centers
    else:
        return hist, bin_edges


def sparse_histogram(
    points: np.ndarray,
    bins: Union[int, str, np.ndarray],
    limits: list[tuple[float, float]] = None,
    return_bin_centers: bool = False,
    eps: float = 1.0e-12,
) -> tuple[np.ndarray, np.ndarray, list[np.ndarray]]:
    """Compute sparse multidimensional histogram.

    Parameters
    ----------
    Same as `histogram`.
    eps : float
        Small constant added to largest bin edge.

    Returns
    ------
    indices : ndarray, shape (k, d)
        Indices of nonzero bins in d-dimensional histogram.
    counts : ndarray, shape (k,)
        Counts of nonzero bins in d-dimensional histogram.
    bins : list(ndarray)
        List of bin edges or centers along each axis.
    """
    bins = histogram_bin_edges(points, bins=bins, limits=limits)
    shape = [len(bins[axis]) for axis in range(points.shape[1])]
    for axis in range(len(bins)):
        bins[axis][-1] = bins[axis][-1] + eps

    # Get multidimensional bin index of each point.
    indices = []
    valid = np.full(points.shape[0], True)
    for axis in range(points.shape[1]):
        idx = np.digitize(points[:, axis], bins[axis])
        valid = np.logical_and(valid, np.logical_and(idx > 0, idx < len(bins[axis])))
        idx = idx - 1  # 0 indexes first bin
        indices.append(idx)
    for axis in range(points.shape[1]):
        indices[axis] = indices[axis][valid]

    # Convert to flat indices.
    shape = [len(bins[axis]) for axis in range(points.shape[1])]
    indices = np.ravel_multi_index(indices, shape)

    # Count the indices/counts of each nonzero bin.
    counter = collections.Counter(indices)
    counts = np.array(list(counter.values()))
    indices = np.array(list(counter.keys()))

    # Convert to multidimensional indices.
    indices = np.unravel_index(indices, shape)
    indices = np.vstack(indices).T
    if return_bin_centers:
        bins = [coords_from_edges(bins[axis]) for axis in range(points.shape[1])]
    return indices, counts, bins


def radial_histogram(points: np.ndarray, **kws) -> None:
    """Count number of points within spherical shells, with counts normalized by shell volume.

    Parameters
    ----------
    points: np.ndarray, shape (..., n)
        Coordinates of n points in d-dimensional space.
    **kws
        Key word arguments for `histogram`.
    """
    radii = get_radii(points)
    hist, bins = histogram(radii, **kws)

    bin_edges = None
    if "centers" in kws and kws["centers"]:
        bin_edges = utils.edges_from_coords(bins)
    else:
        bin_edges = bins

    for i in range(len(bin_edges) - 1):
        rmin = bin_edges[i]
        rmax = bin_edges[i + 1]
        hist[i] = hist[i] / utils.sphere_shell_volume(rmin, rmax, points.shape[1])
    return hist, bins


def gaussian_kde(points: np.ndarray, **kws) -> Callable:
    """Builde kernel density estimator (KDE)."""
    return scipy.stats.gaussian_kde(points.T, **kws)
