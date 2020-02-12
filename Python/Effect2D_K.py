"""
        # NEIGHBORHOOD STRUCTURE RELATED
        :param radius=0.25,

        # PRECISION MATRIX RELATED
        :param rho=0.2:
        :param tau=0.1:

        :return:
        z: grf sample vector.
        R: precisionmatrix, which induced z.
        B: used Decomposition of R to create z
        """
import numpy as np
from Python.Effect2D import Effects2D
from Python.bspline import diff_mat2D
from Python.SamplerPrecision import penalize_nullspace


class GMRF_K(Effects2D):
    """Construct GMRF from K_order=D_order @ D_order with nullspace penalty on K.
    coef are drawn from the resulting MVN(0, penK)"""

    def __init__(self, xgrid, ygrid, order=1, tau=1, sig_Q=0.01, sig_Q0=0.01, threshold=10 ** -3):
        """
        # FOLLOWING FAHRMEIR KNEIB LANG
        :param xgrid:
        :param ygrid:
        :param order: CURRENTLY HIGHER ORDERS OF K are not supported due to theoretical issues. implementation works fine
        :param tau:
        :param sig_Q:
        :param sig_Q0:
        :param threshold:
        """
        # generate grid
        super(GMRF_K, self).__init__(xgrid, ygrid)

        self._construct_precision_GMRF_K(tau)
        self._sample_with_nullspace_pen(Q=self.Q, sig_Q=sig_Q, sig_Q0=sig_Q0, threshold=threshold)
        self._generate_surface()

        self.plot()

    def _construct_precision_GMRF_K(self, tau):
        (meshx, _), _ = self.grid
        no_coef = meshx.shape[0]

        D1, D2, K = diff_mat2D(dim=no_coef)

        # \gamma^T K \gamma =   \gamma^T (I_(d2) kron K1 + K2 kron I_(d1) ) \gamma
        # with K1 = D1^T D1 and  K2 = D2^T D2 where D1 and D2 are 1st order difference matrices
        # in z1 & z2 direction respectively.

        self.Q = tau * K
        # self.Q = tau * (np.kron(np.eye(K.shape[0]), K) + np.kron(K, np.eye(K.shape[0])))

        print('rank of Q: ', np.linalg.matrix_rank(self.Q))
        print('shape of Q: ', self.Q.shape)

    def plot(self):
        self.plot_interaction(title='GMRF_K with Nullspace penalty to MVN')


class GMRF_K_cond(GMRF_K):
    """due to rank deficiency of K, sampling conditional on edges"""

    def __init__(self, xgrid, ygrid, order=1, tau=1, ):
        """
        # FOLLOWING FAHRMEIR KNEIB LANG
        :param xgrid:
        :param ygrid:
        :param order: currently not supported
        :param tau:
        """
        # generate grid
        super(GMRF_K, self).__init__(xgrid, ygrid)
        self._construct_precision_GMRF_K(tau)

        # find edges
        (meshx, meshy), gridvec = self.grid
        row_length, col_length = meshx.shape
        no_neighb = 1
        edges = [0, row_length - no_neighb, (col_length - no_neighb) * row_length,
                 (col_length - no_neighb) * row_length + row_length - no_neighb]

        self._sample_conditional_precision(cond_points=edges, tau=tau)
        self._generate_surface()

        self.plot()

    def plot(self):
        self.plot_interaction(title='conditonal GMRF_K')


class GMRF_K_null_cholesky(GMRF_K):
    """Construct GMRF from K_order=D_order @ D_order with nullspace penalty on K.
    coef are drawn using Cholesky (on full rank K)

    different approach: try nullspace penalty & Cholesky afterwards"""

    def __init__(self, xgrid, ygrid, order=2, tau=1, sig_Q=0.01, sig_Q0=0.01, threshold=10 ** -3):
        """
        # FOLLOWING FAHRMEIR KNEIB LANG
        :param xgrid:
        :param ygrid:
        :param order:
        :param tau:
        :param sig_Q:
        :param sig_Q0:
        :param threshold:
        """
        # generate grid
        Effects2D.__init__(self, xgrid=xgrid, ygrid=ygrid)

        self._construct_precision_GMRF_K(tau)
        Sigma, penQ = penalize_nullspace(self.Q, sig_Q, sig_Q0, threshold)
        self.Sigma = Sigma
        self.penQ = penQ
        self._sample_uncond_from_precisionB(penQ, tau, decomp='choleskyB')
        self._generate_surface()

        self.plot()


if __name__ == '__main__':
    xgrid = (0, 10, 0.5)  # FIXME: due to _generate_surface, these must span an square grid!
    ygrid = xgrid

    gmrf_condK = GMRF_K_cond(xgrid, ygrid, order=1, tau=1)
    gmrf_k = GMRF_K(xgrid, ygrid, order=1, tau=1, sig_Q=1, sig_Q0=0.8)
    gmrf_k2 = GMRF_K_null_cholesky(xgrid, ygrid, order=1, tau=1, sig_Q=1, sig_Q0=0.1)



    print('')
