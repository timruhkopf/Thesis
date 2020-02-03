import os
import pandas as pd
from time import gmtime, strftime
from subprocess import check_output

# storing results / logs / pip
import shelve
import os
import sys
import traceback
from pip._internal.operations import freeze

print(pathroot)


class Grid():
    def __init__(self, root, model, configs):
        """
        Grid Object, taking care
        :param model: model object, must have
        :param configs: list of dicts of parameters to run on model
        """

        # file structure (redundant, but easily accessible on server)
        self.pathroot = root
        self.pathresults = self.pathroot + 'results/'  # consider only for plots
        self.pathlogs = self.pathroot + 'logs/'
        self.pathtf = self.pathroot + 'tf/'
        os.mkdir(self.pathroot)
        os.mkdir(self.pathresults)
        os.mkdir(self.pathlogs)
        os.mkdir(self.pathtf)

        # current configuration
        self._pip_freeze()
        self.git_hash = self._get_git_revision_hash()

        self.model = model
        self.configs = configs
        self.result_table = pd.DataFrame(columns=['hash', 'config', 'success'],
                                         index=range(len(configs)))

        # preallocate failure cache
        self.failures = dict()
        self.logs = dict()

    def run_model(self):

        for i, config in enumerate(self.configs):
            # parallelize? threads / processes?

            hash = self._create_hash(model=self.model.__name__)
            print('trying {}\n'.format(hash))

            try:
                # ToDo intercept stdout
                stdout = 'some file'

                # run object config
                instance = self.model(**config)
                self._store_instance(instance)

            except:
                self.result_table.loc[i] = [hash, str(config), False]

                self.failures[hash] = config
                with open(self.pathlogs + hash + '.log', 'w') as logfile:
                    logfile.write(str(config) + '\n')

                traceback.print_exc(file=open(self.pathlogs + hash + '.log', 'a'))


            else:  # passed try
                # ToDo get metrics
                # metric = instance.metric_fn()
                # self.result_table.append(metric)

                # ToDo get & store plots

                # ToDo be more verbose
                # instance.metric = metric
                # instance.stdout = stdout

                self.result_table.loc[i] = [hash, str(config), True]

        # print(stdout)
        # ToDo print result_table to Grid.log

        print(self.failures)
        self._store_grid()

    def _get_git_revision_hash(self):
        return check_output(['git', 'rev-parse', '--short', 'HEAD']).decode('ascii').strip()

    def _create_hash(self, model):
        return '{hash}_{model}{timestamp}'.format(
            hash=self.git_hash,
            model=model,
            timestamp=strftime("%Y%m%d_%H%M%S", gmtime())
        )

    def _pip_freeze(self):
        # write pip to file
        self.pipfreeze = freeze.freeze()
        with open(self.pathroot + 'pip_freeze.txt', 'w') as file:
            file.write('Python ' + sys.version + '\n')
            for line in self.pipfreeze:
                file.write(line + '\n')
            file.close()

    def _store_instance(self, model_object):
        """
        shelving the instance, such that all objects are available
        :param model_object: an executed model instance
        :param stdout
        """

        # ToDo shelve instance with git hash
        hash = self._create_hash()

        # ToDo store tensorflow models also elsewhere -
        # so TB can access all instances from one dir

        pass

    def _store_grid(self):

        # Todo make pip freeze & append it to grid

        # Todo shelve grid

        pass

    def load(self):
        pass


if __name__ == '__main__':
    from Python.model_cases import Xbeta
    G = Grid(model=Xbeta, configs=[{}, {}])

    G.run_model()

print('')
