import numpy as np
from numpy import linalg as la


def _twiss(sigma):
    """Return rms Twiss parameters from u-u' covariance matrix."""
    eps = _emittance(sigma)
    beta = sigma[0, 0] / eps
    alpha = -sigma[0, 1] / eps
    return alpha, beta


def _emittance(sigma):
    """Return rms emittance from u-u' covariance matrix."""
    return np.sqrt(la.det(sigma))


def apparent_emittances(Sigma):
    """Return epsx, epsy, epz."""
    _emittances = []
    for i in range(0, Sigma.shape[0], 2):
        _emittances.append(_emittance(Sigma[i:i+2, i:i+2]))
    return _emittances

def twiss(Sigma):
    """Return alpha_x, beta_x, alpha_y, beta_y, ..."""
    n = Sigma.shape[0] // 2
    params = []
    for i in range(n):
        j = i * 2
        params.extend(_twiss(Sigma[j:j+2, j:j+2]))
    return params


def rotation_mat(angle):
    """2x2 clockwise rotation matrix."""
    c, s = np.cos(angle), np.sin(angle)
    return np.array([[c, s], [-s, c]])


def rotation_mat_4x4(angle):
    """4x4 matrix to rotate [x, x', y, y'] clockwise in the x-y plane."""
    c, s = np.cos(angle), np.sin(angle)
    return np.array([[c, 0, s, 0], [0, c, 0, s], [-s, 0, c, 0], [0, -s, 0, c]])


def phase_adv_mat(*phase_advances):
    n = len(phase_advances)
    R = np.zeros((2 * n, 2 * n))
    for i, phase_advance in enumerate(phase_advances):
        i = i * 2
        R[i:i+2, i:i+2] = rotation_mat(phase_advance)
    return R


def norm_mat_2x2(alpha, beta):
    """Normalization matrix for u-u'."""
    return np.array([[beta, 0.0], [-alpha, 1.0]]) / np.sqrt(beta)
    
    
def norm_mat(*twiss_params):
    """Order is (alpha_x, beta_x, alpha_y, beta_y, alpha_z, beta_z). 
    Leave out the dimensions you don't want."""
    n = len(twiss_params) // 2
    V = np.zeros((2 * n, 2 * n))
    for i in range(n):
        j = i * 2
        V[j:j+2, j:j+2] = norm_mat_2x2(*twiss_params[j:j+2])
    return V