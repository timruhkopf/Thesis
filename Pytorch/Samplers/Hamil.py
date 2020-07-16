import torch
import torch.nn as nn
import torch.distributions as td

import hamiltorch
from Pytorch.Samplers.Samplers import Sampler


class Hamil(Sampler):
    def __init__(self, model, X, y, params_init):
        """An interface to various hamiltorch samplers
        # https://github.com/AdamCobb/hamiltorch
        # https://adamcobb.github.io/journal/hamiltorch.html  (vignette)
        """

        self.model = model
        self.model.closure_log_prob(X, y)
        self.params_init = params_init

        # placeholders
        self.chain = list()  # FIXME: this format of self.chain does not allow to compare multiple samplers!
        self.log_probability = torch.Tensor()

    def logs(self):
        self.log_probability = torch.cat([self.model.log_prob(state) for state in self.chain])

    def sample_NUTS(self, N, step_size=.3, L=5, burn=500):
        """burn = 500,    N_nuts = burn + N"""
        steps = N + burn
        self.chain = hamiltorch.sample(
            log_prob_func=self.model.log_prob, params_init=self.params_init,
            num_samples=steps, step_size=step_size, num_steps_per_sample=L,
            sampler=hamiltorch.Sampler.HMC_NUTS, burn=burn)

        self.logs()
        self.clean_chain()
        return self.chain

    def sample_iRMHMC(self, N, step_size, L):
        self.chain = hamiltorch.sample(
            log_prob_func=self.model.log_prob, params_init=self.params_init, num_samples=N,
            step_size=step_size, num_steps_per_sample=L, sampler=hamiltorch.Sampler.RMHMC,
            integrator=hamiltorch.Integrator.IMPLICIT, fixed_point_max_iterations=1000,
            fixed_point_threshold=1e-05)

        self.logs()
        self.clean_chain()
        return self.chain

    def sample_eRMHMC(self, N, step_size, L, omega=100.):
        self.chain = hamiltorch.sample(
            log_prob_func=self.log_prob, params_init=self.params_init, num_samples=N,
            step_size=step_size, num_steps_per_sample=L, sampler=hamiltorch.Sampler.RMHMC,
            integrator=hamiltorch.Integrator.EXPLICIT, explicit_binding_const=omega)

        self.logs()
        self.clean_chain()
        return self.chain

    def sample_eRMHMC_bad(self):
        """if a model is badly defined, the hessian can be non positive semi definite:
        no longer guaranteed to be positive semi-definite (PSD) if we use the Hessian as above.
        Therefore we introduce a new flag and set is as metric=hamiltorch.Metric.SOFTABS.
        This forces our metric to be PSD as in Betancourt 2013.
        As is common in practice, we must often add jitter along the diagonal of the
        metric tensor to ensure we can invert it (it also allows us to differentiate through it using torch.symeig). We do this via jitter=jitter.
        """
        pass


if __name__ == '__main__':
    from Pytorch.Layer.Hidden import Hidden

    no_in = 10
    no_out = 1

    # single Hidden Unit Example
    reg = Hidden(no_in, no_out, bias=True, activation=nn.Identity())
    reg.true_model = reg.vec

    X_dist = td.Uniform(torch.ones(no_in) * (-10.), torch.ones(no_in) * 10.)
    X = X_dist.sample(torch.Size([100]))
    y = reg.likelihood(X).sample()

    reg.reset_parameters()
    init_theta = reg.vec

    hamil = Hamil(reg, X, y, init_theta)
    hamil.sample_NUTS(1000, 0.3, 5)
    hamil.sample_eRMHMC(1000, 0.3, 5)
    hamil.sample_iRMHMC(1000, 0.3, 5)
