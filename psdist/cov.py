"""Covariance matrix analysis."""

import numpy as np

from .ap import unit_symplectic_matrix
from .ap import normalize_eigvecs
from .ap import normalization_matrix_from_eigvecs


def normalization_matrix(S: np.ndarray, scale: bool = False) -> np.ndarray:
    """Compute symplectic matrix that diagonalizes covariance matrix"""
    ndim = S.shape[0]
    
    U = unit_symplectic_matrix(ndim)
    SU = np.matmul(S, U)
    
    eigvals, eigvecs = np.linalg.eig(SU)
    eigvecs = normalize_eigvecs(eigvecs)
    
    V_inv = normalization_matrix_from_eigvecs(eigvecs)

    if scale:
        V = np.linalg.inv(V_inv)
        A = np.sqrt(np.diag(np.repeat(intrinsic_emittances(S), 2)))
        V = np.matmul(V, A)
        V_inv = np.linalg.inv(V)
    
    return V_inv

def normalization_matrix_block_diag(S: np.ndarray, scale: bool = False) -> np.ndarray:
    """Compute block-diagonal symplectic matrix that diagonalizes 2x2 block-diagonal
    elements of covariance matrix (i.e., S[:2, :2])."""
    V_inv = np.identity(S.shape[0])
    for i in range(0, S.shape[0], 2):
        V_inv[i: i + 2, i: i + 2] = normalization_matrix(S[i: i + 2, i: i + 2], scale=scale)
    return V_inv


def cov_to_corr(S: np.ndarray) -> np.ndarray:
    """Compute correlation matrix from covariance matrix."""
    D = np.sqrt(np.diag(S.diagonal()))
    Dinv = np.linalg.inv(D)
    return np.linalg.multi_dot([Dinv, S, Dinv])


def emittance(S: np.ndarray) -> float:
    """Compute emittance from covariance matrix."""
    return np.sqrt(np.linalg.det(S))


def twiss_2x2(S: np.ndarray) -> tuple[float, float]:
    """Compute twiss parameters from 2 x 2 covariance matrix.

    alpha = -<xx'> / sqrt(<xx><x'x'> - <xx'><xx'>)
    beta  =  <xx>  / sqrt(<xx><x'x'> - <xx'><xx'>)
    """
    eps = emittance(S)
    beta = S[0, 0] / eps
    alpha = -S[0, 1] / eps
    return (alpha, beta)


def twiss(S: np.ndarray) -> list[float]:
    """Compute two-dimensional twiss parameters from 2n x 2n covariance matrix.

    Parameters
    ----------
    S : ndarray, shape (2n, 2n)
        Covariance matrix. (Dimensions ordered {x, x', y, y', ...}.)

    Returns
    -------
    alpha_x, beta_x, alpha_y, beta_y, alpha_z, beta_z, ... : float
        The Twiss parameters in each plane.
    """
    params = []
    for i in range(0, S.shape[0], 2):
        params.extend(twiss_2x2(S[i : i + 2, i : i + 2]))
    return params


def apparent_emittances(S: np.ndarray) -> list[float]:
    """Compute rms apparent emittances from 2n x 2n covariance matrix.

    Parameters
    ----------
    S : ndarray, shape (2n, 2n)
        A covariance matrix. (Dimensions ordered {x, x', y, y', ...}.)

    Returns
    -------
    eps_x, eps_y, eps_z, ... : float
        The emittance in each phase-plane (eps_x, eps_y, eps_z, ...)
    """
    emittances = []
    for i in range(0, S.shape[0], 2):
        emittances.append(
            np.sqrt(np.linalg.det(S[i : i + 2, i : i + 2]))
        )
    if len(emittances) == 1:
        emittances = emittances[0]
    return emittances


def intrinsic_emittances(S: np.ndarray) -> tuple[float, ...]:
    """Compute rms intrinsic emittances from covariance matrix."""
    # To do: compute eigvals to extend to 6 x 6, rather than
    # using analytic eigenvalue solution specific to 4 x 4.
    S = np.copy(S[:4, :4])
    U = unit_symplectic_matrix(4)
    tr_SU2 = np.trace(np.linalg.matrix_power(np.matmul(S, U), 2))
    det_S = np.linalg.det(S)
    eps_1 = 0.5 * np.sqrt(-tr_SU2 + np.sqrt(tr_SU2**2 - 16.0 * det_S))
    eps_2 = 0.5 * np.sqrt(-tr_SU2 - np.sqrt(tr_SU2**2 - 16.0 * det_S))
    return (eps_1, eps_2)


projected_emittances = apparent_emittances
eigen_emittances = intrinsic_emittances


def rms_ellipse_dims(S: np.ndarray, axis: tuple[int, ...] = None) -> tuple[float, ...]:
    """Return projected rms ellipse dimensions and orientation.

    Parameters
    ----------
    S : ndarray, shape (2n, 2n)
        The phase space covariance matrix.
    axis : tuple[int]
        Projection axis. Example: if the axes are {x, xp, y, yp}, and axis=(0, 2),
        the four-dimensional ellipsoid is projected onto the x-y plane.

    Returns
    -------
    c1, c2 : float
        The ellipse semi-axis widths.
    angle : float
        The tilt angle below the x axis [radians].
    """
    if S.shape[0] == 2:
        axis = (0, 1)
    (i, j) = axis
    sii = S[i, i]
    sjj = S[j, j]
    sij = S[i, j]
    angle = -0.5 * np.arctan2(2 * sij, sii - sjj)
    _sin = np.sin(angle)
    _cos = np.cos(angle)
    _sin2 = _sin**2
    _cos2 = _cos**2
    c1 = np.sqrt(abs(sii * _cos2 + sjj * _sin2 - 2 * sij * _sin * _cos))
    c2 = np.sqrt(abs(sii * _sin2 + sjj * _cos2 + 2 * sij * _sin * _cos))
    return (c1, c2, angle)


def norm_matrix_from_twiss_2x2(alpha: float, beta: float) -> np.ndarray:
    """2 x 2 normalization matrix for u-u'.

    Parameters
    ----------
    alpha : float
        The alpha parameter.
    beta : float
        The beta parameter.

    Returns
    -------
    ndarray, shape (2, 2)
        Matrix that transforms the ellipse defined by alpha/beta to a circle.
    """
    V = np.array([[beta, 0.0], [-alpha, 1.0]]) / np.sqrt(beta)
    return np.linalg.inv(V)


def norm_matrix_from_twiss(*twiss_params):
    """2n x 2n block-diagonal normalization matrix from Twiss parameters.

    Parameters
    ----------
    alpha_x, beta_x, alpha_y, beta_y, alpha_z, beta_z, ... : float
        Twiss parameters for each dimension.

    Returns
    -------
    V : ndarray, shape (2n, 2n)
        Block-diagonal normalization matrix.
    """
    ndim = len(twiss_params) // 2
    V = np.zeros((ndim, ndim))
    for i in range(0, ndim, 2):
        V[i : i + 2, i : i + 2] = norm_matrix_from_twiss_2x2(*twiss_params[i : i + 2])
    return np.linalg.inv(V)
