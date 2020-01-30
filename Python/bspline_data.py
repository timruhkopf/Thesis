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

import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import axes3d

from itertools import product as prd

from Python.bspline import diff_mat

class Effects1D():
    def __init__(self, xgrid):
        self.xgrid=xgrid
        self.x = np.linspace(start=self.xgrid[0], stop=self.xgrid[1],
                        num=100, endpoint=True)

    def generate_bspline(self, degree):
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
        import pylab # FIXME remove this for plt.scatter!

        fig = plt.figure()
        ax = fig.add_subplot(111)
        ax.plot(self.x, self.spl(self.x))
        pylab.show()

class randomData():
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

    def __init__(self, xgrid=(0, 10, 1), ygrid=(0, 10, 1),
                 bspline_param=None,
                 uncond_grf_param=None,
                 cond_grf_param=None,
                 decomp=None,
                 draw_nullspace=None,
                 plt_it=True):

        self.xgrid = xgrid
        self.ygrid = ygrid
        self.bspline_param = bspline_param
        self.uncond_grf_param = uncond_grf_param
        self.cond_grf_param = cond_grf_param
        self.decomp = decomp
        self.draw_nullspace = draw_nullspace

        self.plt_it = plt_it

        if bspline_param is not None:
            self.generate_bspline(**bspline_param)

            if plt_it:
                self.plot_bspline()

        if uncond_grf_param is not None or cond_grf_param is not None:
            # spanning the grid
            x, y = np.arange(xgrid[0], xgrid[1], xgrid[2]), \
                   np.arange(ygrid[0], ygrid[1], ygrid[2])
            self.grid = self.generate_grid(x, y)

            if uncond_grf_param is not None:
                self._generate_precision(**uncond_grf_param)

                if uncond_grf_param['construct_precision'] == 'GMRF_VL':
                    # precision is of full rank and invertible
                    plt.imshow(self.SIGMA, cmap='hot', interpolation='nearest')
                    self.z = np.random.multivariate_normal(mean=np.zeros(self.SIGMA.shape[0]), cov=self.Q)

                elif uncond_grf_param['construct_precision'] == 'GMRF_K':

                    self._sample_with_nullspace_pen(Q=self.Q, **draw_nullspace)
                else:
                    # choose how to sample based on the precision
                    if decomp is not None:
                        self._sample_uncond_from_precisionB(self.Q, self.decomp)
                    elif self.draw_nullspace is not None:
                        self._sample_with_nullspace_pen(Q=self.Q, **draw_nullspace)

            elif cond_grf_param is not None:
                self._sample_conditional_gmrf(**cond_grf_param)

            # generate the interaction effect
            self.generate_surface()

            if plt_it:
                self.plot_interaction()

    def generate_grid(self, x, y):
        xmesh, ymesh = np.meshgrid(x, y)
        # xflat, yflat = xmesh.flatten(), ymesh.flatten()
        # gridvec = np.stack((xflat, yflat), axis=1)

        a = list(prd(x, y))
        gridvec = np.array(a)

        return (xmesh, ymesh), gridvec

    def grid_distances(self, corrfn, lam, phi, delta):
        # (1) Calculate distances & generate R from it
        _, gridvec = self.grid

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

    def construct_precision_GRF(self, tau):
        self.Q = self.kernel_distance
        np.fill_diagonal(self.Q, 1)  # FIXME: Fact checkk if not e.g. rowsum?

        self.Q = tau * self.Q

    def construct_precision_GMRF(self, radius, tau):
        neighbor = squareform(self.dist) <= radius
        self.Q = np.where(neighbor == False, 0, self.kernel_distance)
        np.fill_diagonal(self.Q, 1)

        self.Q = tau * self.Q

    def construct_precision_GMRF_K(self, order, tau):
        (meshx, _), _ = self.grid
        no_coef = meshx.shape[0]

        d, K = diff_mat(dim=no_coef, order=order)  # FIXME: dimensions appropriate determine by grid
        self.Q = tau * np.kron(np.eye(K.shape[0]), K) + np.kron(K, np.eye(K.shape[0]))

    def construct_precision_GMRF_VL(self, radius, rho, tau):
        # ATTEMPT ON GMRF formulation as in LECTURE SLIDES ON GMRF
        # radius : determining the discrete neighborhood structure
        # rho: correlation coefficient, determining how strong the neighbour affects this coef.
        # tau: global variance - how strong
        # mu = 0

        # w_sr \propto exp(-d(s,r)) where d euclidean dist
        # NOTE: d(s,r) is already in self.kernel_distance & all d(s,r)<= radius define s~r neighborhood!
        # 0.5 or 0.25 are radii that define the neighborhood structure on a grid
        neighbor = squareform(self.dist) <= radius
        w_sr = np.where(neighbor == False, 0, self.kernel_distance)

        # np.fill_diagonal(w_sr, 0)

        # w_s+ = sum_r w_sr for all s~r
        # NOTE: each rowsum of squareform(self.kernel_distance) , whose d(s,r) <= radius are w_s+,
        # excluding the point under evaluation
        w_s = w_sr.sum(axis=0)

        # B[s,r] = \beta_sr if s ~ r else 0
        # \beta_sr = \rho * w_sr/ w_s+
        # \rho element [0,1]
        # BS = rho * w_sr.dot(np.diag(w_s ** (-1)))

        BS = rho * np.diag(1 / w_s).dot(w_sr)

        # where SIGMA = diag(tau1, ..., tauS)
        # tau_s = \tau / w_s+
        Sigma_inv = np.diag(w_s / tau)

        self.SIGMA = np.diag(tau / w_s).dot(np.linalg.inv(np.eye(BS.shape[0]) - BS))
        plt.imshow(self.SIGMA, cmap='hot', interpolation='nearest')

        # Q =(I_S - B) SIGMA⁻1
        self.Q = (np.eye(BS.shape[0]) - BS).dot(Sigma_inv)
        plt.imshow(self.Q, cmap='hot', interpolation='nearest')

        print('rank of Q: ', np.linalg.matrix_rank(self.Q))
        print('shape of Q: ', self.Q.shape)

    def _sample_with_nullspace_pen(self, Q, sig_Q=0.01, sig_Q0=0.01, threshold=10 ** -3):

        # trial on null space penalty

        import tensorflow as tf
        import tensorflow_probability as tfp
        tfd = tfp.distributions

        self.Sigma = penalize_nullspace(Q, sig_Q, sig_Q0, threshold)
        rv_z = tfd.MultivariateNormalFullCovariance(
            covariance_matrix=self.Sigma,
            loc=0.)
        self.z = rv_z.sample().numpy()

    def _sample_conditional_gmrf(self, corrfn='gaussian', lam=1, no_neighb=4, decomp=['draw_normal', 'cholesky'][0],
                                 radius=20, tau=0.1, seed=1337):
        """conditional sampling of grf (compare Rue / Held slides p.59, eq (10)) """
        (meshx, meshy), gridvec = self.grid

        # Identify the index positions of points corresponding to
        # no_neighb square at each of the grid's edges
        row_length, col_length = meshx.shape
        edge_ref = [rowbase + col
                    for rowbase in np.linspace(0, (row_length) * (no_neighb - 1), no_neighb, dtype=np.int32)
                    for col in np.arange(0, no_neighb)]
        edge_pos = [0, row_length - no_neighb, (col_length - no_neighb) * row_length,
                    (col_length - no_neighb) * row_length + row_length - no_neighb]
        edges = [x + y for y in edge_pos for x in edge_ref]

        # index workaround for deselection
        mask = np.ones(len(gridvec), np.bool)
        mask[edges] = 0
        Q_AAdata = gridvec[mask]
        Q_ABdata = gridvec[~mask]

        # generate the distance between points
        dist_AA = pdist(X=Q_AAdata, metric='euclidean')
        dist_AB = cdist(XA=Q_AAdata, XB=Q_ABdata, metric='euclidean')
        dist_BB = pdist(Q_ABdata, metric='euclidean')

        # euclidean kernel comparison: GRF Qs
        corr = {
            'gaussian': lambda h: np.exp(-(h / lam) ** 2)
            # consider different kernels: exponential
        }[corrfn]
        Q_AA = squareform(corr(dist_AA))
        Q_AB = corr(dist_AB)
        Q_BB = squareform(corr(dist_BB))

        # deselect neighbours for GMRF Qs
        neighbor = squareform(dist_AA) <= radius
        Q_AA = np.where(neighbor == False, 0, Q_AA)
        np.fill_diagonal(Q_AA, 1)

        # deselect neighbours for GMRF Qs
        neighbor = squareform(dist_BB) <= radius
        Q_BB = np.where(neighbor == False, 0, Q_BB)
        np.fill_diagonal(Q_BB, 1)

        neighbor = dist_AB <= radius
        Q_AB = np.where(neighbor == False, 0, Q_AB)

        # for plotting purposes:
        Q1 = np.concatenate([Q_AA, Q_AB], axis=1)
        Q2 = np.concatenate([Q_AB.T, Q_BB], axis=1)
        self.Q = np.concatenate([Q1, Q2], axis=0)

        if seed is not None:
            np.random.seed(seed=seed)

        if decomp == 'draw_normal':  # flavours of drawing xa
            xb = np.random.multivariate_normal(mean=np.zeros(Q_BB.shape[0]), cov=tau * Q_BB)
            xa = np.random.multivariate_normal(mean=-tau * Q_AB.dot(xb - 0), cov=tau * Q_AA)

            # xa = np.zeros((Q_AA.shape[0],))  # Consider remove this control
        elif decomp == 'cholesky':
            xb = backsolve(L=np.linalg.cholesky(tau * Q_BB),
                           z=np.random.normal(loc=0, scale=1, size=Q_BB.shape[0]),
                           mu=np.zeros(Q_BB.shape[0]))
            xa = backsolve(L=np.linalg.cholesky(tau * Q_AA),
                           z=np.random.normal(loc=0, scale=1, size=Q_AA.shape[0]),
                           mu=-Q_AB.dot(xb - 0))

        # join coefficients of xa, xb in to sorted gridvector
        # (which in generate_surface will be destacked appropriately
        z = np.zeros(shape=gridvec.shape[0])
        z[mask] = xa
        z[~mask] = xb

        self.z = z

    def generate_surface(self):
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

    def plot_interaction(self):  # , pred_error=None):
        """
        # consider plotting both 3d graphics (grf & Tp-BSpline):
            # https://matplotlib.org/mpl_examples/mplot3d/subplot3d_demo.py
        """
        # Plot the grid points with plugged-in gmrf-coef (at the grid points!).
        (meshx, meshy), _ = self.grid
        # meshx, meshy = np.meshgrid(x, y, indexing='ij')
        gridxy = np.stack((meshx, meshy), axis=-1)

        fig = plt.figure()

        if self.uncond_grf_param is not None:
            constructtyp = 'unconditional, ' + self.uncond_grf_param['construct_precision']
        elif self.cond_grf_param is not None:
            constructtyp = 'conditional, '

        plt.title('{} with {}'.format(constructtyp, self.decomp))

        # plot coefficents without TP-Splines
        ax1 = fig.add_subplot(221, projection='3d')
        ax1.plot_wireframe(meshx, meshy, self.z.reshape(meshx.shape), color='C1')
        ax1.set_title('Coefficents at grid position')

        # plot TP-splines with plugged in coeff
        ax2 = fig.add_subplot((222), projection='3d')
        ax2.set_title('TE-Spline with plugged-in gmrf-coef.')
        if False:
            # FIXME: CUTTING AWAY THE EXTREME EDGES IN CHOLESKY!
            ax2.plot_wireframe(meshx[2:20, 2:20], meshy[2:20, 2:20], a(gridxy)[2:20, 2:20], color='C1')
        else:
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

def backsolve(L, z, mu=0):
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


def penalize_nullspace(Q, sig_Q=0.01, sig_Q0=0.01, threshold=10 ** -3):
    """
    Nullspace penalty for rank deficient Precision matrix, to get rank sufficent Covariance matrix

    :param Q: Precision Matrix
    :param sig_Q: inverse variance factor (sig_Q * Q)
    :param sig_Q0: penalty factor
    :param threshold: numerical value, determining which eigenvals are numerical zero

    :return: Covariance : inverse of the resulting penalized precision matrix:
    (sig_Q * Q + sig_Q0 * S0)**-1 with S0 = U0 @ U0.T, where U0 corresponds
    to the matrix of Eigenvectors corresponding to those Eigenvalues < threshold
    """
    eigval, eigvec = eigh(Q)

    # (numeric precision) null space eigenvectors
    U0 = eigvec[:, eigval < threshold]
    S0 = U0.dot(U0.T)
    penQ = sig_Q * Q + sig_Q0 * S0
    penSIGMA = np.linalg.inv(penQ)

    print('Eigenvalues: ', eigval, '\n')
    print('Nullspace Matrix: ', U0)

    fig = plt.figure()
    ax1 = fig.add_subplot(221)
    ax1.scatter(np.arange(eigval.size), eigval)
    ax1.set_title('eigenvalues of Q')

    ax2 = fig.add_subplot(222)
    ax2.imshow(penSIGMA, cmap='hot', interpolation='nearest')
    ax2.set_title('penSIGMA')

    ax3 = fig.add_subplot(223)
    ax3.imshow(Q, cmap='hot', interpolation='nearest')
    ax3.set_title('Q')
    plt.show()

    return penSIGMA


if __name__ == '__main__':
    n = 10000
    xgrid = (0, 10, 0.5)
    ygrid = (0, 10, 0.5)

    # fx = randomData(xgrid=xgrid,
    #                 bspline_param={'n_basis': 7, 'coef_scale': 0.5, 'degree': 2},
    #                 plt_it=False)
    #
    # fy = randomData(xgrid=ygrid,
    #                 bspline_param={'n_basis': 7, 'coef_scale': 0.5, 'degree': 2},
    #                 plt_it=False)

    # # working Versions are 'eigenB' with 'GRF' or 'GMRF'

    # fxy = randomData(xgrid=xgrid, ygrid=ygrid,
    #                  uncond_grf_param={'lam': 1, 'phi': 0, 'delta': 1,
    #                                    'construct_precision': ['GRF', 'GMRF', 'GMRF_VL', 'GMRF_K'][1],
    #                                    'radius': 4,  # for index 1-3
    #                                    'rho': 0.9, 'tau': 1,  # for index 2,3 only
    #                                    'seed': 1337},
    #                  decomp=['eigenB', 'choleskyB'][0],
    #                  plt_it=True)
    #
    # fxy = randomData(xgrid=xgrid, ygrid=ygrid,
    #                  uncond_grf_param={'lam': 1, 'phi': 0, 'delta': 1,
    #                                    'construct_precision': ['GRF', 'GMRF', 'GMRF_VL', 'GMRF_K'][2],
    #                                    'radius': 4,  # for index 1-3
    #                                    'rho': 0.9, 'tau': 1,  # for index 2,3 only
    #                                    'seed': 1337},
    #                  decomp=['eigenB', 'choleskyB'][0],
    #                  plt_it=True)

    # working version GMRF_K with NUllspace penalty
    fxy = randomData(xgrid=xgrid, ygrid=ygrid,
                     uncond_grf_param={'lam': 10, 'phi': 0, 'delta': 1,
                                       'construct_precision': ['GRF', 'GMRF', 'GMRF_VL', 'GMRF_K'][3],
                                       'radius': 20,  # for index 1-3
                                       'rho': 0.9, 'tau': 1,  # for index 2,3 only
                                       'seed': 1337},
                     draw_nullspace={'sig_Q': 1, 'sig_Q0': 1, 'threshold': 10 ** -3},
                     plt_it=True)

    # peculiar result with cholesky
    fxy = randomData(xgrid=xgrid, ygrid=ygrid,
                     uncond_grf_param={'lam': 1, 'phi': 0, 'delta': 1,
                                       'construct_precision': ['GRF', 'GMRF', 'GMRF_VL', 'GMRF_K'][1],
                                       'radius': 4,  # for index 1-3
                                       'rho': 0.9, 'tau': 1,  # for index 2,3 only
                                       'seed': 1337},
                     decomp=['eigenB', 'choleskyB'][1],
                     plt_it=True)




    fxy_null = randomData(xgrid=xgrid, ygrid=ygrid,
                     uncond_grf_param={'lam': 1, 'phi': 0, 'delta': 1,
                                       'construct_precision': ['GRF', 'GMRF', 'GMRF_VL'][2],
                                       'radius': 4,  # for index 1-3
                                       'rho': 0.7, 'tau': 1,  # for index 2,3 only
                                       'seed': 1337},
                     draw_nullspace={'sig_Q': 1, 'sig_Q0': 1, 'threshold': 10 ** -3},
                     plt_it=True)

    # working version!
    fxy_cond = randomData(xgrid=xgrid, ygrid=ygrid,
                          cond_grf_param={'corrfn': 'gaussian', 'lam': 1, 'no_neighb': 4,
                                          'decomp': ['draw_normal', 'cholesky'][0],
                                          'radius': 20, 'tau': 0.1, 'seed': 1337},
                          plt_it=True)

    # uniformly sample the coordinates
    # CONSIDER: Bayesian advantage is to declare uncertainty on estimates -
    # particmDatularly in sparse data regions. change sampling scheme to display this
    # effect!

    # sample coordinates
    x, y = np.random.uniform(low=xgrid[0], high=xgrid[1], size=n), \
           np.random.uniform(low=ygrid[0], high=ygrid[1], size=n)

    # mu = fx.spl(x) + fy.spl(y) + fxy.surface(np.stack([x, y], axis=-1))

    # Version: sample GMRF on small grid, plug in Coefficients in NDSpline
    mu = fxy.surface(np.stack([x, y], axis=-1))
    # Consider: the basis representation is calculated somewhere in einsum in
    # ndspline.NDSpline.__call__

    z = np.random.normal(loc=mu.real, scale=0.1, size=n)

    # plot the data
    fig = plt.figure()
    ax = fig.add_subplot(122, projection='3d')
    # ax.plot_wireframe(meshx, meshy, fxy.surface(gridxy))
    ax.scatter(xs=x, ys=y, zs=z, alpha=0.3)
    ax.set_title('N(f(x,y), ...) = z')

    ax1 = fig.add_subplot(121, projection='3d')
    ax1.scatter(xs=x, ys=y, zs=mu.real, alpha=0.3)
    ax1.set_title('mu')

    plt.show()

    # check plot methods are available
    # fx.plot_bspline()
    # fy.plot_bspline()

    fxy.plot_interaction()

    print('')
