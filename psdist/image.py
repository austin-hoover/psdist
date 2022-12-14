"""Functions for n-dimensional images."""
import numpy as np
from tqdm import trange
from tqdm import tqdm
from scipy import ndimage

from . import utils
from .utils import edges_from_centers
from .utils import centers_from_edges


def get_grid_coords(*coords):
    """Return list of grid coordinates from coordinate arrays along each axis.

    Parameters
    ----------
    coords : list of 1D arrays
        Coordinates along each axis of regular grid. Example: [[1, 2, 3], [0, 1, 2]].

    Returns
    -------
    ndarray, shape (K, len(coords))
        Coordinate array for all points in the grid. The total number of grid
        points is `K = np.prod([len(c) for c in coords])`.
    """
    return np.vstack([C.ravel() for C in np.meshgrid(*coords, indexing="ij")]).T


def max_indices(f):
    """Return the indices of the maximum element of `f`."""
    return np.unravel_index(np.argmax(f), f.shape)


def make_slice(n=1, axis=0, ind=0):
    """Return planar slice index array.

    Parameters
    ----------
    n : int
        The number of elements in the slice index array. (The number of dimensions
        in the array to be sliced.)
    axis : list[int]
        The sliced axes.
    ind : list[int] or list[tuple]
        The indices along the sliced axes. If a tuple is provided, this
        defines the (min, max) index.

    Returns
    -------
    idx : n-tuple
        The slice index array. A slice of the array `f` may then be accessed as
        `f[idx]`.
    """
    # Make list if only one axis provided.
    if type(axis) is int:
        axis = [axis]
        # Can also provide only one axis but provide a tuple for ind, which
        # selects a range along that axis.
        if type(ind) is tuple:
            ind = [ind]
    # Make list if only one ind provided.
    if type(ind) is int:
        ind = [ind]
    # Initialize the slice index to select all elements.
    idx = n * [slice(None)]
    # If any indices were provided, add them to `idx`.
    for k, item in zip(axis, ind):
        if item is None:
            continue
        elif type(item) is tuple and len(item) == 2:
            idx[k] = slice(item[0], item[1])
        else:
            # Could be int or list of ints
            idx[k] = item
    return tuple(idx)


def make_slice_ellipsoid(f, axis=None, rmin=0.0, rmax=1.0):
    """Compute an ellipsoid slice.

    Ellipsoid is computed from the covariance matrix of `f`.

    Parameters
    ----------
    f : ndarray
        An n-dimensional image.
    axis : list[int]
        Specificies the subspace in which the ellipsoid slices are computed.
        Example: in x-y-z space, we may define a circle in x-y. This could
        select points within a cylinder in x-y-z.
    rmin, rmax : float
        We select the region between two nested ellipsoids with "radius"
        rmin and rmax. The radius is r = x^T Sigma^-1 x, where Sigma is
        the covariance matrix and x is the coordinate vector. r = 1 is
        the covariance ellipsoid.

    Returns
    -------
    np.ma.masked_array
        A version of `f` in which elements outside the slice are masked.
    """
    # Will need to compute an (n-m)-dimensional mask (m = len(axis)), then
    # copy the mask into the remaining dimensions with `copy_into_new_dim`.
    raise NotImplementedError


def make_slice_contour(f, axis=None, lmin=0.0, lmax=1.0):
    """Compute a contour slice.

    Parameters
    ----------
    f : ndarray
        An n-dimensional image.
    axis : list[int]
        Specificies the subspace in which the contours are computed. (See
        `make_slice_ellipsoid`.)
    lmin, lmax : float
        `f`is projected onto `axis` and the projection `fpr` is normalized to
        the range [0, 1]. Then, we find the points in this subspace such that
        `fpr` is within the range [lmin, lmax].

    Returns
    -------
    np.ma.masked_array
        A version of `f` in which elements outside the slice are masked.
    """
    # Will need to compute an (n-m)-dimensional mask (m = len(axis)), then
    # copy the mask into the remaining dimensions with `copy_into_new_dim`.
    raise NotImplementedError


def project(f, axis=0):
    """Project along one or more axes.

    Parameters
    ----------
    f : ndarray
        An n-dimensional image.
    axis : list[int]
        The axes onto which the image is projected, i.e., the
        axes which are not summed over. Can be an int or list
        of ints. Array axes are swapped as required.

    Returns
    -------
    proj : ndarray
        The projection of `image` onto the specified axis.
    """
    # Sum over specified axes.
    n = f.ndim
    if type(axis) is int:
        axis = [axis]
    axis = tuple(axis)
    axis_sum = tuple([i for i in range(f.ndim) if i not in axis])
    proj = np.sum(f, axis_sum)

    # Order the remaining axes.
    n = proj.ndim
    loc = list(range(n))
    destination = np.zeros(n, dtype=int)
    for i, index in enumerate(np.argsort(axis)):
        destination[index] = i
    for i in range(n):
        if loc[i] != destination[i]:
            j = loc.index(destination[i])
            proj = np.swapaxes(proj, i, j)
            loc[i], loc[j] = loc[j], loc[i]
    return proj


def project1d_contour(f, axis=0, lmin=0.0, lmax=1.0, fpr=None):
    """Apply contour slice in n-1 dimensions, then project onto the remaining dimension.

    Parameters
    ----------
    f : ndarray
        An n-dimensional image.
    axis : int
        The 1D projection axis.
    lmin, lmax : float
        Min and max contour levels of the (n-1)-dimensional projection of `f`,
        normalized the the range [0, 1].
    fpr : ndarray, shape [f.shape[i] for i in range(f.ndim) if i != axis]
        The (n-1)-dimensional projection of `f` onto all dimensions other than `axis`.
        (If not provided, it will be computed within the function.)

    Returns
    -------
    ndarray, shape (f.shape[axis],)
        The 1D projection of the slice.
    """
    axis_proj = [i for i in range(f.ndim) if i != axis]
    if fpr is None:
        fpr = project(f, axis=axis_proj)
    fpr = fpr / np.max(fpr)
    idx = make_slice(
        n=f.ndim,
        axis=axis_proj,
        ind=np.where(np.logical_and(fpr >= lmin, fpr <= lmax)),
    )
    # `f[idx]` will give a two-dimensional array. Normally we need to sum over
    # the first axis. If `axis == 0`, we need to sum over the second axis.
    return np.sum(f[idx], axis=int(axis == 0))


def project2d_contour(f, axis=(0, 1), lmin=0.0, lmax=1.0, fpr=None):
    """Apply contour slice in n-2 dimensions, then project onto the remaining two dimensions.

    Parameters
    ----------
    f : ndarray
        An n-dimensional image.
    axis : tuple
        The 2D projection axis.
    lmin, lmax : float
        Min and max contour levels of the (n-2)-dimensional projection of `f`,
        normalized the the range [0, 1].
    fpr : ndarray, shape [f.shape[i] for i in range(f.ndim) if i != axis]
        The (n-1)-dimensional projection of `f` onto all dimensions other than `axis`.
        (If not provided, it will be computed within the function.)

    Returns
    -------
    ndarray, shape (f.shape[axis[0]], f.shape[axis[1]])
        The 2D projection of the slice.
    """
    axis_proj = [k for k in range(f.ndim) if k not in axis]
    if fpr is None:
        fpr = project(f, axis=axis_proj)
    fpr = fpr / np.max(fpr)
    idx = make_slice(
        f.ndim, axis_proj, np.where(np.logical_and(fpr >= lmin, fpr <= lmax))
    )
    # `f[idx]` will give a three-dimensional array. Normally we need to sum over
    # the first axis. If `axis == (0, 1)`, we need to sum over the third axis.
    # If `axis == (0, n - 1), we need to sum over the second axis.
    _axis_proj = (1, 2)
    if axis == (0, 1):
        _axis_proj = (0, 1)
    elif axis == (0, f.ndim - 1):
        _axis_proj = (0, 2)
    # Two elements of `idx` will be `slice(None)`; these are the elements in `axis`.
    # These will always be in order. So, if `axis[0] > axis[1]`, we need to flip
    # `axis_proj`. Need a way to handle this automatically, especially if we
    # are going to consider m-dimensional projections after applying a contour
    # slice in (n-m) dimensions.
    if axis[0] > axis[1]:
        _axis_proj = tuple(reversed(_axis_proj))
    return project(f[idx], axis=_axis_proj)


def copy_into_new_dim(f, shape=None, axis=-1, method="broadcast", copy=False):
    """Copy image into one or more new dimensions.

    See 'https://stackoverflow.com/questions/32171917/how-to-copy-a-2d-array-into-a-3rd-dimension-n-times'

    Parameters
    ----------
    f : ndarray
        An n-dimensional image.
    shape : n-tuple of ints
        The shape of the new dimensions.
    axis : int (0 or -1)
        If 0, the new dimensions will be inserted before the first axis. If -1,
        the new dimensions will be inserted after the last axis. I think
        values other than 0 or -1 should work; this does not currently
        work, at least for `method='broadcast'`, last I checked.
    method : {'repeat', 'broadcast'}
        Whether to use `np.repeat` or `np.expand_dims` and `np.broadcast_to`. The
        'broadcast' method is faster.
    """
    if type(shape) in [int, np.int32, np.int64]:
        shape = (shape,)
    if method == "repeat":
        for i in range(len(shape)):
            f = np.repeat(np.expand_dims(f, axis), shape[i], axis=axis)
        return f
    elif method == "broadcast":
        if axis == 0:
            new_shape = shape + f.shape
        elif axis == -1:
            new_shape = f.shape + shape
        else:
            raise ValueError("Cannot yet handle axis != 0, -1.")
        for _ in range(len(shape)):
            f = np.expand_dims(f, axis)
        if copy:
            return np.broadcast_to(f, new_shape).copy()
        else:
            return np.broadcast_to(f, new_shape)
    return None


def get_radii(coords, Sigma):
    """Return "radii" (x^T Sigma^-1^T x) from grid coordinates and covariance matrix.

    This is quite slow when n > 4 due to creating a mesh grid.

    Parameters
    ----------
    coords : list[ndarray], length n
        Coordinate array for each dimension of the regular grid.
    Sigma : ndarray, shape (n, n)
        Covariance matrix of some distribution on the grid.

    Returns
    -------
    R : ndarray
        "Radius" x^T Sigma^-1^T x at each point in grid.
    """
    COORDS = np.meshgrid(*coords, indexing="ij")
    shape = tuple([len(c) for c in coords])
    R = np.zeros(shape)
    Sigma_inv = np.linalg.inv(Sigma)
    for ii in tqdm(np.ndindex(shape)):
        vec = np.array([C[ii] for C in COORDS])
        R[ii] = np.sqrt(np.linalg.multi_dot([vec.T, Sigma_inv, vec]))
    return R


def radial_density(f, R, radii, dr=None):
    """Return average density within ellipsoidal shells.

    Parameters
    ----------
    f : ndarray
        An n-dimensional image.
    R : ndarray, same shape as `f`.
        Gives the "radius" at each pixel in f.
    radii : ndarray, shape (k,)
        Radii at which to evaluate the density.
    dr : float
        The shell width.

    Returns
    -------
    fr : ndarray, shape (k,)
        The average density within each ellipsoidal shell.
    """
    if dr is None:
        dr = 0.5 * np.max(R) / (len(R) - 1)
    fr = []
    for r in tqdm(radii):
        f_masked = np.ma.masked_where(np.logical_or(R < r, R > r + dr), f)
        # mean density within this shell...
        fr.append(np.mean(f_masked))
    return np.array(fr)


def cov(f, coords=None):
    """Compute the n x n covariance matrix.

    Parameters
    ----------
    f : ndarray
        An n-dimensional image.
    coords : list[ndarray]
        Coordinates along each axis of the image.

    Returns
    -------
    ndarray, shape (n, n)
        The covariance matrix.
    """

    def cov_2x2(_f, _coords):
        COORDS = np.meshgrid(*_coords, indexing="ij")
        Sigma = np.zeros((_f.ndim, _f.ndim))
        mean = np.zeros(_f.ndim)
        _f_sum = np.sum(_f)
        if _f_sum > 0:
            mean = np.array([np.average(C, weights=_f) for C in COORDS])
            for i in range(_f.ndim):
                for j in range(i + 1):
                    X = COORDS[i] - mean[i]
                    Y = COORDS[j] - mean[j]
                    EX = np.sum(_f * X) / _f_sum
                    EY = np.sum(_f * Y) / _f_sum
                    EXY = np.sum(_f * X * Y) / _f_sum
                    Sigma[i, j] = Sigma[j, i] = EXY - EX * EY
        return Sigma

    if coords is None:
        coords = [np.arange(s) for s in f.shape]

    n = f.ndim
    if n < 3:
        return cov_2x2(f, coords)

    Sigma = np.zeros((n, n))
    for i in range(n):
        for j in range(i):
            axis = (i, j)
            _image = project(f, axis=axis)
            _coords = [coords[k] for k in axis]
            # Compute 2 x 2 covariance matrix from this projection.
            _sigma = cov_2x2(_image, _coords)
            # Update elements of n x n covariance matrix. This will update
            # some elements multiple times, but it should not matter.
            Sigma[i, i] = _sigma[0, 0]
            Sigma[j, j] = _sigma[1, 1]
            Sigma[i, j] = Sigma[j, i] = _sigma[0, 1]
    return Sigma


def corr(f, coords=None):
    """Compute the n x n correlation matrix.

    Parameters
    ----------
    f : ndarray
        An n-dimensional image.
    coords : list[ndarray]
        Coordinates along each axis of the image.

    Returns
    -------
    ndarray, shape (n, n)
        The correlation matrix.
    """
    return utils.cov2corr(cov(f, coords))


def sample_grid(f, coords, samples=1):
    """Sample from histogram.

    Parameters
    ----------
    f : ndarray
        An n-dimensional histogram.
    coords : list[ndarray]
        Coordinates along each axis of the image.
    samples : int
        The number of samples to draw.

    Returns
    -------
    ndarray, shape (samples, n)
        Samples drawn from the distribution.
    """
    if f.ndim == 1:
        coords = [coords]
    edges = [edges_from_centers(c) for c in coords]
    f_sum = np.sum(f)
    idx = np.random.choice(
        np.arange(f.size), size=samples, replace=True, p=(f.ravel() / f_sum)
    )
    idx = np.unravel_index(idx, shape=f.shape)
    lb = [edges[axis][idx[axis]] for axis in range(f.ndim)]
    ub = [edges[axis][idx[axis] + 1] for axis in range(f.ndim)]
    return np.squeeze(np.random.uniform(lb, ub).T)