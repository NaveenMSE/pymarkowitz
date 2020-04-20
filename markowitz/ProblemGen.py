
import math
import warnings
import inspect
from collections import defaultdict

import numpy as np
import pandas as pd
from scipy.optimize import minimize
import seaborn as sns
import matplotlib.pyplot as plt

from .Exceptions import *
from .ConstraintGen import ConstraintGen as ConstGen
from .ObjectiveGen import ObjectiveGen as ObjGen
from .MetricGen import  MetricGen as MetGen



class ProblemGen:

    def __init__(self, ret_data, moment_data, beta_data=None, asset_names=None):

        self.ret_vec, self.moment_mat, self.assets, self.moment, self.beta_vec = ProblemGen.init_checker(ret_data, moment_data,
                                                                                         asset_names, beta_data)

        self.weight_sols = None

        self.objective = None
        self.objective_sol = None
        self.objective_args = None

        self.obj_creator = ObjGen(self.ret_vec, self.moment_mat, self.moment, self.assets, self.beta_vec)
        self.const_creator = ConstGen(self.ret_vec, self.moment_mat, self.moment, self.assets, self.beta_vec)
        self.metric_creator = MetGen(self.ret_vec, self.moment_mat, self.moment, self.assets, self.beta_vec)

        self.bounds, self.constraints = self.const_creator.create_constraint('weight', weight_bound=(0, 1), leverage=1)
        self.leverage = 1

    ### Add some quick shortcuts

    def add_objective(self, objective_type, **kwargs):
        if objective_type != "custom":
            self.objective_args = tuple(kwargs.values())
            self.objective = self.obj_creator.create_objective(objective_type, **kwargs)
        else:
            self.objective_args = tuple(kwargs.values()[1:])
            self.objective = tuple(kwargs.values())[0]


    def add_constraint(self, constraint_type, **kwargs):
        if constraint_type == "custom":
            self.constraints += tuple(kwargs.values())[0]
        elif constraint_type == "weight":
            bound, leverage = self.const_creator.create_constraint(constraint_type, **kwargs)
            self.bounds = bound
            self.leverage = kwargs['leverage']
            self.constraints[0] = leverage[0] # Total Leverage is always the first constraint
        else:
            self.constraints += self.const_creator.create_constraint(constraint_type, **kwargs)

    def clear(self, clear_obj=True, clear_constraints=True):

        if clear_constraints:
            self.constraints = []
            self.bounds, self.constraints = self.const_creator.create_constraint('weight', weight_bound=(0,1), leverage=1)
        if clear_obj:
            self.objective = None

    @staticmethod
    def gen_random_weight(size, bound, leverage):
        lb = bound[0]
        ub = bound[1]
        # temp = np.random.uniform(size=size, low=lb, high=ub)
        temp = np.random.randn(size)
        # print(temp)
        # print(temp)
        # print(temp/temp.sum())
        # print((temp/temp.sum()).sum())
        temp = temp / temp.sum()
        # print(temp)
        # temp[temp < lb] = lb
        # temp[temp > ub] = ub
        return temp * leverage

    def solve(self, x0=None, round=4, **kwargs):
        if type(self.objective) != np.ndarray:
            # print(self.bounds)
            # print(self.bounds)
            # print(self.constraints
            res = minimize(self.objective, x0=ProblemGen.gen_random_weight(self.ret_vec.shape[0], self.bounds[0], self.leverage) if x0 is None else x0, options={'maxiter': 1000},
                           constraints=self.constraints, bounds=self.bounds, args=self.objective_args)
            if not res.success:
                self.clear(**kwargs)
                raise OptimizeException(f"""Optimization has failed. Error Message: {res.message}. Please adjust constraints/objectives or input an initial guess.""")
            # print(res)
            # try:
            #     ans = prob.solve()
            # except cp.DCPError:
            #     try:
            #         ans = prob.solve(qcp=True)
            #     except (cp.DCPError, cp.SolverError):
            #         try:
            #             ans = prob.solve(solver=cp.SCS, qcp=True)
            #         except cp.DCPError:
            #             raise OptimizeException(f"""The problem formulated is not convex if minimizing,
            #         concave if maximizing""")
            #
            # if "unbounded" in prob.status:
            #     raise OptimizeException("Unbounded Variables")
            # elif "infeasible" in prob.status:
            #     raise OptimizeException("Infeasible Variables")
            # elif "inaccurate" in prob.status:
            #     warnings.warn("Results may be inaccurate.")
            self.clear(**kwargs)
            self.weight_sols = np.round(res.x, round) + 0

        else:
            warnings.warn(f"""The problem formulated is not an optimization problem and is calculated numerically""")
            # self.clear()
            # self.weight_sols = dict(zip(self.assets, self.objective))
            self.weight_sols = self.objective
            self.clear(**kwargs)

    def summary(self, risk_free=None, market_return=None, top_holdings=None, round=3):

        moment_dict = defaultdict(lambda: "Moment")
        moment_dict[3] = "Skewness"
        moment_dict[4] = "Kurtosis"

        weight_dict = dict(zip(self.assets, self.weight_sols))
        metric_dict = {}

        metric_dict['Expected Return'] = self.metric_creator.expected_return(self.weight_sols)

        # Weight Related
        metric_dict["Leverage"] = self.metric_creator.leverage(self.weight_sols)
        metric_dict["Number of Holdings"] = self.metric_creator.num_assets(self.weight_sols)
        if top_holdings:
            metric_dict[f"Top {top_holdings} Holdings Concentrations"] = self.metric_creator.concentration(
                self.weight_sols, top_holdings)

        # Risk Related
        if self.moment == 2:
            metric_dict["Volatility"] = self.metric_creator.volatility(self.weight_sols)
            # metric_dict["Correlation"] = self.metric_creator.correlation(self.weight_sols)
        else:
            metric_dict[f'{moment_dict[int(self.moment)]}'] = self.metric_creator.higher_moment(self.weight_sols)

        # Metrics Related
        if self.beta_vec is not None:
            metric_dict["Portfolio Beta"] = self.metric_creator.beta(self.weight_sols, self.beta_vec)

        if risk_free is not None:
            metric_dict["Sharpe Ratio"] = self.metric_creator.sharpe(self.weight_sols, risk_free)

        if self.beta_vec is not None and risk_free is not None:
            metric_dict["Treynor Ratio"] = self.metric_creator.treynor(self.weight_sols, risk_free, self.beta_vec)
            if market_return is not None:
                metric_dict["Jenson's Alpha"] = self.metric_creator.jenson_alpha(self.weight_sols, risk_free, market_return, self.beta_vec)

        for item in metric_dict:
            metric_dict[item] = np.round(metric_dict[item], round)

        weight_dict = {k: v for k, v in weight_dict.items() if v}
        return weight_dict, metric_dict

    def simulate(self, x='volatility', y='expected_return', iters=1000, weight_bound=(0,1), leverage=1, ret_format='sns', **kwargs):

        x_val = np.zeros(iters)
        y_val = np.zeros(iters)

        for iter in range(iters):
            temp_weights = ProblemGen.gen_random_weight(self.ret_vec.shape[0], weight_bound, leverage)
            x_val[iter] = self.metric_creator.method_dict[x](temp_weights, **kwargs)
            y_val[iter] = self.metric_creator.method_dict[y](temp_weights, **kwargs)

        if ret_format == 'sns':
            sns.scatterplot(x_val, y_val);
            plt.ylim(0, 1);
            plt.xlim(0, 1);
            plt.xlabel(x);
            plt.ylabel(y);
            plt.show()
        else:
            return pd.DataFrame(columns=[x] + [y], data=np.concatenate([x_val.reshape(1,-1), y_val.reshape(1,-1)]).T)
        # return fig

    @staticmethod
    def list_method_options(method_dict):
        res_dict = {}
        for method in method_dict:
            res_dict[method] = inspect.signature(method_dict[method])
        return res_dict

    def objective_options(self):
        return ProblemGen.list_method_options(self.obj_creator.method_dict)

    def constraint_options(self):
        return ProblemGen.list_method_options(self.const_creator.method_dict)

    def metrics_options(self):
        return ProblemGen.list_method_options(self.metric_creator.method_dict)

    @staticmethod
    def init_checker(ret_data, moment_data, asset_names, beta_data):

        asset_candidates = None
        if isinstance(ret_data, pd.Series):
            ret_vec = ret_data.values
            asset_candidates = list(ret_data.index)
        elif isinstance(ret_data, list):
            ret_vec = np.array(ret_data)
        elif isinstance(ret_data, np.ndarray):
            ret_vec = ret_data.reshape(-1)
        else:
            raise FormatException("""Return Vector must be a pd.Series, list or np.ndarray object""")

        if isinstance(moment_data, pd.DataFrame):
            moment_mat = moment_data.values
            asset_candidates = list(moment_data.index)
        elif isinstance(moment_data, np.ndarray):
            moment_mat = moment_data
        else:
            raise FormatException("""Moment Matrix must be a pd.DataFrame or np.ndarray object""")

        moment = math.log(moment_mat.shape[1], moment_mat.shape[0]) + 1

        if asset_names:
            assets = asset_names
        elif asset_candidates:
            assets = asset_candidates
        else:
            assets = [f'ASSET_{x}' for x in range(moment_mat.shape[0])]

        ### Dimensionality Checking
        # print(ret_vec.shape[0])
        # print(moment_mat.shape[1])
        # print(moment)
        # print(int(moment))
        beta_vec = None
        if beta_data is None:
            warnings.warn(""""Detected no beta input. Will not be able to perform any beta-related optimization.""")
        elif isinstance(beta_data, np.ndarray):
            warnings.warn(f"""Assume that beta input is in the sequence of {assets}.""")
        elif isinstance(beta_data, pd.Series):
            if list(beta_data.index) != assets:
                raise DimException(f"""Beta data must include all assets: {assets}""")
            else:
                beta_vec = beta_data[assets].values
        elif len(assets) != beta_data.shape[0]:
            raise DimException("""Inconsistent Shape between Beta Vector and the number of assets""")
        else:
            raise FormatException(f"""Beta data must be passed in as np.ndarray or pd.Series""")

        if ret_vec.shape[0] != moment_mat.shape[0]:
            raise DimException("""Inconsistent Shape between Return Vector and the Moment Matrix""")
        elif int(moment) != moment:
            raise DimException("""Incorrect Dimension of the Moment Matrix""")

        return ret_vec, moment_mat, assets, int(moment), beta_vec




