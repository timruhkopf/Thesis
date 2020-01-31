"""
Created on Mon Nov 6 2019
@author: T.Ruhkopf
@email:  tim.ruhkopf@outlook.de
"""

import ndsplines
from scipy.interpolate import BSpline  # FIXME: replace ndspline

from scipy.spatial.distance import pdist, cdist, squareform
from scipy.linalg import eigh
import numpy as np
import tensorflow as tf
import tensorflow_probability as tfp

tfd = tfp.distributions

import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import axes3d

from itertools import product as prd

from Python.bspline import penalize_nullspace


class Effects1D():
    def __init__(self, xgrid):
        self.xgrid = xgrid
        self.x = np.linspace(start=self.xgrid[0], stop=self.xgrid[1],
                             num=100, endpoint=True)

    def _generate_bspline(self, degree):
        """
        mean value of data distribution is the b-spline value f(x)
        f(x) = \gamma B(degree), with \gamma_j | gamma_(i<J) [ ~ N(0, coef_scale)
        i.e. gamma is a random walk
        y = N(f(x), data_scale)

        :param xgrid: tuple: (start, end) of linspace.
        :param n_basis: number of basis functions
        :param degree: basis degree
        :param coef_scale: variance for random walk on basis' coefficents
        :return:
        (1) vector of size n, that is normally distributed with mean f(x)
        (2) self.spl: spline function; return of BSpline. allows evaluating any x
        (3) self.z: \gamma vector, produced by random walk
        """

        # random b-spline function parametrization
        n_knots = degree + self.z.size + 1

        # function generator for one regressor
        self.spl = BSpline(t=np.linspace(start=self.xgrid[0], stop=self.xgrid[1],
                                         num=n_knots, endpoint=True),
                           c=self.z,
                           k=degree,
                           extrapolate=True)

    def log_prob(self):
        pass

    def plot_bspline(self):
        """plotting the bspline resulting from bspline_param"""
        import pylab  # FIXME remove this for plt.scatter!

        fig = plt.figure()
        ax = fig.add_subplot(111)
        ax.plot(self.x, self.spl(self.x))
        pylab.show()


class Effects2D():
    """
    Possible extensions
    (1) consider random data distribution & building a grf upon it.
    eventhough it is possible to calculate the tensorproduct spline,
    thin plate regression splines are better suited to handle sparsely sampled
    regions via linear extrapolation

    # Consider further note: the grids are only relevant at effect construction,
    # but not #  for data sampling; as consequence, non overlapping grids for
    # the effect with smaller support assume an effectsize #  of zero for
    # points out of their bounds.
    """

    def __init__(self, xgrid, ygrid):
        self.xgrid = xgrid
        self.ygrid = ygrid

        x, y = np.arange(xgrid[0], xgrid[1], xgrid[2]), \
               np.arange(ygrid[0], ygrid[1], ygrid[2])
        self.grid = self._generate_grid(x, y)

    # (helper functions) -------------------------------------------------------
    def _generate_grid(self, x, y):
        xmesh, ymesh = np.meshgrid(x, y)
        # xflat, yflat = xmesh.flatten(), ymesh.flatten()
        # gridvec = np.stack((xflat, yflat), axis=1)

        a = list(prd(x, y))
        gridvec = np.array(a)

        return (xmesh, ymesh), gridvec

    def _grid_distances(self, corrfn, lam, phi, delta, gridvec):

        if phi != 0 or delta != 1:
            # anisotropy  # FIXME make this available for conditional
            def rotation(phi):
                return np.array([[np.cos(phi), np.sin(phi)],
                                 [-np.sin(phi), np.cos(phi)]])

            def prolongation(delta):
                return np.diag([delta ** -1, 1])

            r = rotation(phi)
            d = prolongation(delta)
            anisotropy = r.T.dot(d).dot(r)

            self.dist = pdist(X=gridvec, metric=lambda u, v: np.sqrt(((u - v).T.dot(anisotropy).dot((u - v)))))

        else:
            # isotropy
            self.dist = pdist(X=gridvec, metric='euclidean')

        corr = {
            'gaussian': lambda h: np.exp(-(h / lam) ** 2)
            # consider different kernels: exponential
        }[corrfn]
        self.kernel_distance = squareform(corr(self.dist))

    def _keep_neighbour(self, Q, radius, fill_diagonal=True):
        """keep neighbours radius based and optionally fill Q's diagonal"""
        neighbor = squareform(self.dist) <= radius
        Q = np.where(neighbor == False, 0, Q)
        if fill_diagonal:
            np.fill_diagonal(Q, 1)

        return Q

    # (sampling) ---------------------------------------------------------------
    def _sample_with_nullspace_pen(self, Q, sig_Q=0.01, sig_Q0=0.01, threshold=10 ** -3):
        # TENSORFLOW VERSION
        # trial on null space penalty
        self.Sigma = penalize_nullspace(Q, sig_Q, sig_Q0, threshold)
        rv_z = tfd.MultivariateNormalFullCovariance(
            covariance_matrix=self.Sigma,
            loc=0.)
        self.z = rv_z.sample().numpy()

    def _sample_uncond_from_precisionB(self, Q, tau, decomp=['eigenB', 'choleskyB'][0]):
        # independent Normal variabels, upon which correlation will be imposed
        theta = np.random.multivariate_normal(
            mean=np.zeros(Q.shape[0]),
            cov=tau * np.eye(Q.shape[0]))

        if decomp == 'eigenB':
            # DEPREC imaginary part!! - FLOATING POINT PRECISION SEEMS TO BE THE ISSUE IN ITERATIVE ALGORITHMS
            # compare: https://stackoverflow.com/questions/8765310/scipy-linalg-eig-return-complex-eigenvalues-for-covariance-matrix
            # eigval, eigvec = np.linalg.eig(self.Q)
            # self.B = eigvec.dot(np.diag(np.sqrt(eigval)))

            eigval, eigvec = eigh(Q)
            plt.scatter(np.arange(eigval.size), eigval)

            self.B = eigvec.dot(np.diag(np.sqrt(eigval)))
            self.z = self.B.dot(theta)

        elif decomp == 'choleskyB':
            # RUE 2005 / 99: for decomp look at sample_GMRF
            self.B = np.linalg.cholesky(Q).T
            self.z = self._sample_backsolve(self.B, theta)

        else:
            raise ValueError('decomp is not propperly specified')

    def _sample_backsolve(self, L, z, mu=0):
        """
        Solve eq. system L @ x = z for x.
        if z ~ MVN(0,I) and Q = LL^T from cholesky, this allows to generate
        x ~ MVN(0, Q^(-1)

        :param L: upper triangular matrix
        :param z: vector
        :param mu: additional mean vector
        :return x: vector
        """
        if L.shape[1] != z.size:
            raise ValueError('improper dimensions')

        x = np.zeros(L.shape[0])
        x[-1] = z[-1] / L[-1, -1]

        for i in reversed(range(0, L.shape[0] - 1)):
            x[i] = (z[i] - L[i].dot(x)) / L[i, i]

        return x + mu

    def _generate_surface(self):
        """
        Generate a 2d Surface from TE-Splines whose coefficients originated from a Random field

        :return: ndsplines.NDSpline.__call__ object, allows to evaluate the
        exact surface value: fxy.surface(np.stack([x, y], axis=-1))

        """

        # fahrmeir : d = l + m - 1
        # ndsplien package : l : degree, m: number of kappas
        # v = m - l - 1

        # v is the number of coefficients derived from degree l and number of knots m
        # NOTE: given some shape of coef (v,v) and a spline degree, derive what m is:
        l = 2
        v = int(np.sqrt(self.z.shape))
        m = v + l + 1

        # spanning the knots
        x = np.linspace(0, 10, m)
        y = np.linspace(0, 10, m)

        # Tensorproduct Splines with plugged in coefficents
        coeff = self.z.reshape((v, v))
        a = ndsplines.NDSpline(knots=[x, y], degrees=[l, l],
                               coefficients=coeff)

        # INTERPOLATION Function for Datapoints
        self.surface = a.__call__

    # (class methods) ----------------------------------------------------------
    def log_prob(self):
        pass

    def plot_interaction(self, title):  # , pred_error=None):
        """
        # consider plotting both 3d graphics (grf & Tp-BSpline):
            # https://matplotlib.org/mpl_examples/mplot3d/subplot3d_demo.py
        # CONSIDER CONTOUR PLOTs only
        """
        # Plot the grid points with plugged-in gmrf-coef (at the grid points!).
        (meshx, meshy), _ = self.grid
        # meshx, meshy = np.meshgrid(x, y, indexing='ij')
        gridxy = np.stack((meshx, meshy), axis=-1)

        fig = plt.figure()

        plt.title('{}'.format(title))

        # plot coefficents without TP-Splines
        ax1 = fig.add_subplot(221, projection='3d')
        ax1.plot_wireframe(meshx, meshy, self.z.reshape(meshx.shape), color='C1')
        ax1.set_title('Coefficents at grid position')

        # plot TP-splines with plugged in coeff
        ax2 = fig.add_subplot((222), projection='3d')
        ax2.set_title('TE-Spline with plugged-in gmrf-coef.')

        ax2.plot_wireframe(meshx, meshy, self.surface(gridxy), color='C1')

        ax3 = fig.add_subplot(223)
        # plotting the correlation matrix used for sampling effects:
        ax3.imshow(self.Q, cmap='hot', interpolation='nearest')
        ax3.set_title('Precision matrix Q')

        plt.show()

        # Deprec after removing the workaround of fitting TE to GRF instead of plugging in coef
        # fig = plt.figure()
        #
        # (xmesh, ymesh), gridvec = self.grid
        # gridxy = np.stack((xmesh, ymesh), axis=-1)
        # # spline =  self.surface(gridxy) FIXME: this is new version!
        #
        # # DEPREC: scipy.interpol.bivariate Bspline input format:
        # spline = self.surface(xi=gridvec[:, 0], yi=gridvec[:, 1])
        # coord_grf = (xmesh, ymesh,
        #              self.z.reshape((xmesh.shape[0], ymesh.shape[0])).T)
        # # FIXME validate, that [0] is correct for rectangle shaped grid
        # coord_teBspline = (xmesh, ymesh,
        #                    spline.reshape((xmesh.shape[0], ymesh.shape[0])).T)
        #
        # if coord_grf is not None:
        #     if coord_teBspline is not None:
        #         ax = fig.add_subplot(121, projection='3d')
        #     else:
        #         ax = fig.add_subplot(111, projection='3d')
        #     ax.set_title('grf')
        #
        #     # Plot grf in wireframe
        #     X, Y, Z = coord_grf
        #     ax.plot_wireframe(X, Y, Z, rstride=1, cstride=1, alpha=0.7)
        #
        # # optionally plot the Bspline estimate as surface
        # if coord_teBspline is not None:
        #     if coord_grf is not None:
        #         ax1 = fig.add_subplot(122, projection='3d')
        #     else:
        #         ax1 = fig.add_subplot(111, projection='3d')
        #
        #     X, Y, Z = coord_teBspline
        #     ax1.plot_surface(X, Y, Z, rstride=1, cstride=1,
        #                      linewidth=0, antialiased=False, alpha=0.7)
        #     ax1.set_title('B-spline estimate')
        #
        #     plt.show()




if __name__ == '__main__':
    print('')
