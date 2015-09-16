
import time
import logging
import numpy as np

from robo.models.gpy_model import GPyModel
from robo.recommendation.optimize_posterior import optimize_posterior_mean_and_std
from robo.solver.base_solver import BaseSolver


class BayesianOptimization(BaseSolver):
    """
    Class implementing general Bayesian optimization.
    """
    def __init__(self, acquisition_func, model,
                 maximize_func, task, save_dir=None,
                 initialization=None, recommendation_strategy=None, num_save=1, train_intervall=1):
        """
        Initializes the Bayesian optimization.
        Either acquisition function, model, maximization function, bounds, dimensions and objective function are
        specified or an existing run can be continued by specifying only save_dir.

        :param acquisition_funct: Any acquisition function
        :param model: A model
        :param maximize_func: The function for maximizing the acquisition function
        :param initialization: The initialization strategy that to find some starting points in order to train the model
        :param task: The task (derived from BaseTask) that should be optimized
        :param recommendation_strategy: A function that recommends which configuration should be return at the end
        :param save_dir: The directory to save the iterations to (or to load an existing run from)
        :param num_save: A number specifying the n-th iteration to be saved
        """

        logging.basicConfig(level=logging.INFO)

        super(BayesianOptimization, self).__init__(acquisition_func, model, maximize_func, task, save_dir)

        self.initialization = initialization

        self.X = None
        self.Y = None
        self.time_func_eval = None
        self.time_optimization_overhead = None
        self.train_intervall = train_intervall

        self.num_save = num_save

        self.model_untrained = True
        self.recommendation_strategy = recommendation_strategy
        self.incumbent = None
        self.n_restarts = 10

    def initialize(self, n_init_points=3):
        """
        Draws a random configuration and initializes the first data point
        """
        #start_time = time.time()
        #if self.initialization is None:
        #    # Draw one random configuration
        #    self.X = np.array([np.random.uniform(self.task.X_lower, self.task.X_upper, self.task.n_dims)])
        #    logging.info("Evaluate randomly chosen candidate %s" % (str(self.X[0])))
        #else:
        #    logging.info("Initialize ...")
        #    self.X = self.initialization()
        #self.time_optimization_overhead = np.array([time.time() - start_time])

        #start_time = time.time()
        
        #self.Y = self.task.evaluate(x[np.newaxis, :])
        
        #self.time_func_eval = np.array([time.time() - start_time])
        #logging.info("Configuration achieved a performance of %f " % (self.Y[0]))
        #logging.info("Evaluation of this configuration took %f seconds" % (self.time_func_eval[0]))
        self.time_func_eval = np.zeros([n_init_points])
        self.time_optimization_overhead = np.zeros([n_init_points])
        self.X = np.zeros([n_init_points, self.task.n_dims])
        self.Y = np.zeros([n_init_points, 1])
        
        for i in range(n_init_points):
            start_time = time.time()                    
            x = np.array([np.random.uniform(self.task.X_lower, self.task.X_upper, self.task.n_dims)])
            self.time_optimization_overhead[i] = time.time() - start_time
    
            start_time = time.time()
            y = self.task.evaluate(x)
            self.time_func_eval[i] = time.time() - start_time
    
            self.X[i] = x[0, :]
            self.Y[i] = y[0, :]
            
            logging.info("Configuration achieved a performance of %f " % (self.Y[i]))
            logging.info("Evaluation of this configuration took %f seconds" % (self.time_func_eval[i]))

    def run(self, num_iterations=10, X=None, Y=None):
        """
        The main Bayesian optimization loop

        :param num_iterations: number of iterations to perform
        :param X: (optional) Initial observations. If a run continues these observations will be overwritten by the load
        :param Y: (optional) Initial observations. If a run continues these observations will be overwritten by the load
        :param overwrite: data present in save_dir will be deleted and overwritten, otherwise the run will be continued.
        :return: the incumbent
        """
        # Save the time where we start the Bayesian optimization procedure
        self.time_start = time.time()

        if X is None and Y is None:
            self.initialize()
            self.incumbent = self.X[0]
            self.incumbent_value = self.Y[0]

            if self.save_dir is not None and (0) % self.num_save == 0:
                self.save_iteration(0, hyperparameters=None, acquisition_value=0)
        else:
            self.X = X
            self.Y = Y
            self.time_func_eval = np.zeros([self.X.shape[0]])
            self.time_optimization_overhead = np.zeros([self.X.shape[0]])

        for it in range(1, num_iterations):
            logging.info("Start iteration %d ... ", it)

            start_time = time.time()
            # Choose next point to evaluate
            if it % self.train_intervall == 0:
                do_optimize = True
            else:
                do_optimize = False
            new_x = self.choose_next(self.X, self.Y, do_optimize)

            start_time_inc = time.time()
            if self.recommendation_strategy is None:
                logging.info("Use best point seen so far as incumbent.")
                best_idx = np.argmin(self.Y)
                self.incumbent = self.X[best_idx]
                self.incumbent_value = self.Y[best_idx]
            elif self.recommendation_strategy is optimize_posterior_mean_and_std:
                logging.info("Optimize the posterior mean and std to find a new incumbent")
                # Start one local search from the best observed point and N - 1 from random points
                startpoints = [np.random.uniform(self.task.X_lower, self.task.X_upper, self.task.n_dims) for i in range(self.n_restarts)]
                best_idx = np.argmin(self.Y)
                startpoints.append(self.X[best_idx])

                self.incumbent, self.incumbent_value = self.recommendation_strategy(self.model, self.task.X_lower, self.task.X_upper, startpoints=startpoints, with_gradients=True)
            else:
                best_idx = np.argmin(self.Y)
                startpoint = self.X[best_idx]
                self.incumbent, self.incumbent_value = self.recommendation_strategy(self.model, self.task.X_lower, self.task.X_upper, startpoints=startpoint)
            logging.info("New incumbent %s found in %f seconds", str(self.incumbent), time.time() - start_time_inc)

            time_optimization_overhead = time.time() - start_time
            self.time_optimization_overhead = np.append(self.time_optimization_overhead, np.array([time_optimization_overhead]))

            logging.info("Optimization overhead was %f seconds" % (self.time_optimization_overhead[-1]))

            logging.info("Evaluate candidate %s" % (str(new_x)))
            start_time = time.time()
            new_y = self.task.evaluate(new_x)
            time_func_eval = time.time() - start_time
            self.time_func_eval = np.append(self.time_func_eval, np.array([time_func_eval]))

            logging.info("Configuration achieved a performance of %f " % (new_y[0, 0]))

            logging.info("Evaluation of this configuration took %f seconds" % (self.time_func_eval[-1]))

            # Update the data
            self.X = np.append(self.X, new_x, axis=0)
            self.Y = np.append(self.Y, new_y, axis=0)

            if self.save_dir is not None and (it) % self.num_save == 0:
                if isinstance(self.model, GPyModel):
                    self.save_iteration(it,
                                        hyperparameters=self.model.m.param_array, 
                                        acquisition_value=self.acquisition_func(new_x))
                else:
                    #TODO: Save also the hyperparameters if we perform mcmc sampling
                    self.save_iteration(it, hyperparameters=None)

#         # Recompute the incumbent before we return it
#         if self.recommendation_strategy is None:
#             best_idx = np.argmin(self.Y)
#             self.incumbent = self.X[best_idx]
#             self.incumbent_value = self.Y[best_idx]
#         else:
#             # TODO: Use GradientAscent here
#             startpoints = [np.random.uniform(self.task.X_lower, self.task.X_upper, self.task.n_dims) for i in range(self.n_restarts)]
#             best_idx = np.argmin(self.Y)
#             startpoints.append(self.X[best_idx])
#             self.incumbent, self.incumbent_value = self.recommendation_strategy(self.model, self.task.X_lower, self.task.X_upper, startpoints=startpoints)
#
        logging.info("Return %s as incumbent with predicted performance %f" % (str(self.incumbent), self.incumbent_value))

        return self.incumbent, self.incumbent_value

    def choose_next(self, X=None, Y=None, do_optimize=True):
        """
        Chooses the next configuration by optimizing the acquisition function.

        :param X: The point that have been where the objective function has been evaluated
        :param Y: The function values of the evaluated points
        :return: The next promising configuration
        """
        if X is not None and Y is not None:
            try:
                logging.info("Train model...")
                t = time.time()
                if do_optimize:
                    self.model.train(X, Y)
                logging.info("Time to train the model: %f", (time.time() - t))
            except Exception, e:
                logging.info("Model could not be trained", X, Y)
                raise
            self.model_untrained = False
            self.acquisition_func.update(self.model)

            logging.info("Maximize acquisition function...")
            t = time.time()
            x = self.maximize_func.maximize()
            logging.info("Time to maximize the acquisition function: %f", (time.time() - t))
        else:
            self.initialize()
            x = self.X
        return x
