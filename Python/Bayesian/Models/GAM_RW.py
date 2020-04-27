from Python.Effects.bspline import get_design, diff_mat1D
# from Python.Bayesian.Models.Regression import Regression
from Python.Bayesian.RandomWalkPrior import RandomWalkPrior

import tensorflow as tf
import tensorflow_probability as tfp

tfd = tfp.distributions
tfb = tfp.bijectors


class GAM_RW:
    def __init__(self, no_basis, no_units=1, activation='identity', *args, **kwargs):
        """:param input_shape: is number of basis! = dim of gamma"""
        self.rw = RandomWalkPrior(no_basis)
        self.prior_sigma = tfd.InverseGamma(1., 1., name='sigma')

        self.bijectors = {'W': tfb.Identity(),
                          'sigma': tfb.Exp(),
                          'tau': tfb.Exp()}

        identity = lambda x: x
        self.activation = {
            'relu': tf.nn.relu,
            'tanh': tf.math.tanh,
            'sigmoid': tf.math.sigmoid,
            'identity': identity}[activation]

    def sample(self):
        s = self.rw.sample()
        s['sigma'] = self.prior_sigma.sample()
        return s

    def likelihood_model(self, Z, W, sigma):
        # W = tf.concat([tf.reshape(W0, (1,)), W], axis=0)
        return tfd.Sample(tfd.Normal(
            loc=self.dense(Z, W),  # mu
            scale=sigma, name='y'),
            sample_shape=1)

    def _closure_log_prob(self, X, y):

        @tf.function
        def GAM_RW_log_prob(tau, W, sigma):  # precise arg ordering as sample!
            likelihood = self.likelihood_model(X, W, sigma)
            return tf.reduce_sum(likelihood.log_prob(y)) + \
                   self.rw.log_prob(gamma=W, tau=tau) + \
                   self.prior_sigma.log_prob(sigma)

        return GAM_RW_log_prob

    @tf.function
    def dense(self, X, W):
        return self.activation(tf.linalg.matvec(X, W))

    def OLS(self, X, y):
        XXinv = tf.linalg.inv(tf.linalg.matmul(X, X, transpose_a=True))
        return tf.linalg.matvec(tf.linalg.matmul(XXinv, X, transpose_b=True), y)



if __name__ == '__main__':
    from Python.Bayesian.Samplers.AdaptiveHMC import AdaptiveHMC

    no_basis = 20
    gam_rw = GAM_RW(no_basis=no_basis)

    # (0) SETTING UP THE DATA
    true_param = gam_rw.sample()

    n = 200
    X = tfd.Uniform(-10., 10.).sample(n)
    Z = tf.convert_to_tensor(
        get_design(X.numpy(), degree=2, no_basis=no_basis),
        tf.float32)

    likelihood = gam_rw.likelihood_model(Z, true_param['W'], true_param['sigma'])
    y = likelihood.sample()

    # (1) SETTING UP THE ESTIMATION
    init_param = gam_rw.sample()
    gam_rw.unnormalized_log_prob = gam_rw._closure_log_prob(Z, y)

    print(gam_rw.unnormalized_log_prob(**init_param))
    print(gam_rw.unnormalized_log_prob(**true_param))

    # look at init
    f_true = gam_rw.dense(Z, true_param['W'])
    f_init = gam_rw.dense(Z, init_param['W'])

    # CAREFULL! the true pls_estimate is not known!!! as we do not know sigma & tau
    # pls_param = true_param
    # pls_param['W'] = gam_rw.rw.PLS_estimate(
    #     Z, y, true_param['sigma'] / true_param['tau'])
    #
    # f_pls = gam_rw.dense(Z, pls_param['W'])

    import seaborn as sns
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(nrows=1, ncols=1)
    fig.subplots_adjust(hspace=0.5)
    fig.suptitle('init-, true-, mean function & sampled points')

    sns.lineplot(
        x=X.numpy(),
        y=tf.reshape(f_true, (X.shape[0],)).numpy(), ax=ax)
    sns.lineplot(
        x=X.numpy(),
        y=tf.reshape(f_init, (X.shape[0],)).numpy(), ax=ax)
    sns.scatterplot(
        x=X.numpy(),
        y=tf.reshape(y, (X.shape[0],)).numpy(), ax=ax)

    # sns.lineplot(
    #     x=X.numpy(),
    #     y=tf.reshape(f_pls, (X.shape[0],)).numpy(), ax=ax)

    plt.plot()

    adHMC = AdaptiveHMC(
        initial=list(init_param.values()),
        bijectors=[gam_rw.bijectors[k] for k in init_param.keys()],
        log_prob=gam_rw.unnormalized_log_prob)

    # FIXME: sample_chain has no y
    samples, traced = adHMC.sample_chain(
        num_burnin_steps=int(1 * 10e2),
        num_results=int(10e2),
        logdir='/home/tim/PycharmProjects/Thesis/TFResults')

    acceptance = tf.reduce_mean(tf.cast(traced.inner_results.is_accepted, tf.float32), axis=0)

    # prediction
    meanPost = adHMC.predict_mean()
    modePost = adHMC.predict_mode(gam_rw.unnormalized_log_prob)

    # plotting
    f_true =  gam_rw.dense(Z, true_param['W'])
    f_init = gam_rw.dense(Z, init_param['W'])
    f_mean = gam_rw.dense(Z, meanPost[1])
    f_mode = gam_rw.dense(Z, modePost[1])

    import seaborn as sns
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(nrows=1, ncols=1)
    fig.subplots_adjust(hspace=0.5)
    fig.suptitle('init-, true-, mean function & sampled points')

    sns.lineplot(
        x=X.numpy(),
        y=tf.reshape(f_true, (X.shape[0],)).numpy(), ax=ax)
    sns.lineplot(
        x=X.numpy(),
        y=tf.reshape(f_init, (X.shape[0],)).numpy(), ax=ax)
    sns.scatterplot(
        x=X.numpy(),
        y=tf.reshape(y, (X.shape[0],)).numpy(), ax=ax)
    sns.lineplot(
        x=X.numpy(),
        y=tf.reshape(f_mean, (X.shape[0],)).numpy(), ax=ax)
    sns.lineplot(
        x=X.numpy(),
        y=tf.reshape(f_mode, (X.shape[0],)).numpy(), ax=ax)
