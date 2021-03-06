#!/usr/bin/env python2
# -*- coding: utf-8 -*-
"""
This module sets up api functions for dynamical correlation analysis.
"""
from __future__ import print_function

import numpy as np

from tuna.stats.utils import (iter_timeseries_,
                              iter_timeseries_2,
                              Regions,
                              CompuParams)
from tuna.stats.single import (Univariate, StationaryUnivariate,
                               UnivariateIOError, StationaryUnivariateIOError)
from tuna.stats.two import Bivariate, StationaryBivariate
from tuna.stats.compute import (set_dynamics,
                                set_stationary_autocorrelation,
                                set_crosscorrelation,
                                set_stationary_crosscorrelation)


MIN_INTERDIVISION_TIME = 5.  # World record is set by Vibrio natriegens
# See R.G.Eagon, J. Bact. vol 83, pp 736-737 (1962)


# %% SINGLE DYNAMIC ONBSERVABLE

def compute_univariate_dynamics(parser, obs, cset=[], size=None):
    """Computes one-point and two-point functions of statistical analysis.

    This functions handles conditions and time-window binning:
    * all conditions provided in cset are applied independently, in addition
      to the computation with unconditioned data (labelled 'master')
    * A time-binning window is provided with a given offset and a period.
      Explicitely a given time value t found in data will be rounded up to
      closest offset_t + k * delta_t, where k is an integer.

    Parameters
    ----------
    parser : :class:`Parser` instance
    obs : :class:`Observable` instance
    cset : list of :class:`FilterSet` instances
    size : int (default None)
        limit the iterator to size Lineage instances (used for testing)
    binsize : float
        size of binning windows for time values
    decimals : int
        number of decimals to use for binning time values
    max_exponent : int
        maximal time value must be less than 10 to the max_exponent value

    Returns
    -------
    Univariate instance
    """
    regs = Regions(parser.experiment)
    region = regs.get('ALL')
    if obs.timing != 'g':
        period = parser.experiment.period
        tmin = region.tmin
        tmax = region.tmax
    else:
        period = 1
        n_max = (region.tmax - region.tmin)/MIN_INTERDIVISION_TIME
        tmin = - n_max
        tmax = n_max
    eval_times = np.arange(tmin, tmax + period, period)
    # initialize Univariate and each of its item
    univ = Univariate(obs, cset, parser, region, eval_times)  # empty
    # Set iterator over TimeSeries
    timeseries = iter_timeseries_(parser, obs, cset, size=size)
    # call the master function performing computation
    set_dynamics(timeseries, univ, eval_times)
    return univ


def initialize_univariate(parser, obs, cset=[]):
    """Initialize an empty Univariate instance.

    Parameters
    ----------
    parser : :class:`Parser` instance
    obs : :class:`Observable` instance
    cset : sequence of :class:`FilterSet` instances

    Returns
    -------
    :class:`Univariate` instance
        initialized, nothing computed yet
    """
    regs = Regions(parser.experiment)
    region = regs.get('ALL')
    if obs.timing != 'g':
        period = parser.experiment.period
        tmin = region.tmin
        tmax = region.tmax
    else:
        period = 1
        n_max = (region.tmax - region.tmin)/MIN_INTERDIVISION_TIME
        tmin = - n_max
        tmax = n_max
    eval_times = np.arange(tmin, tmax + period, period)
    univ = Univariate(obs, parser=parser, cset=cset, region=region,
                      eval_times=eval_times)
    return univ


# %% SINGLE STATIONARY OBSERVABLE
class ParamsError(ValueError):
    pass


def _check_params(region, options):
    if not isinstance(options, CompuParams):
        raise ParamsError('options must be a CompuParams instance')
    if ((not hasattr(region, 'tmin')) or
        (not hasattr(region, 'tmax')) or
        (not hasattr(region, 'name'))):
        raise ParamsError('region must have name, tmin, tmax attributes')
    return


def initialize_stationary_univariate(univ, region, options):
    """Initialize a StationaryUnivariate instance from its dynamical one.

    Parameters
    -----------
    univ : :class:`Univariate` instance
    region : :class:`pandas.Series` instance
        must have following attributes: 'name', 'tmin', 'tmax'
    options : :class:`CompuParams` instance

    Returns
    -------
    :class:`StationaryInstance` instance
        set up with empty arrays
    """
    _check_params(region, options)
    stat = StationaryUnivariate(univ, region, options)
    _update_univariate_from_stationary(univ, stat)
    return stat


def _update_univariate_from_stationary(univ, stat):
    for lab in stat._condition_labels:
        cdt_stat = stat[lab]
        univ[lab].stationary = cdt_stat
    return


def compute_stationary_univariate(univ, region, options, size=None):
    """Computes stationary autocorrelation. API level.

    Parameters
    ----------
    univ : :class:`Univariate` instance
        the stationary autocorr is based on this object
    region : :class:`pandas.Series` instance
        must have following attributes: 'name', 'tmin', 'tmax', 'adjust_mean'
        name : str
            name of chosen region
        tmin : float
            lower bound for stationarity time range
        tmax : float
            upper bound for stationarity time range
        adjust_mean : str {'global', 'local'}
            how to substract average values: globally, or locally;
            use globally when local statistics are not sufficient,
            use locally is local statistics are sufficient.
    size : int (default None)
        limit number of parsed Lineages

    """
    _check_params(region, options)
    # initialize StationaryUnivariate
    stationary = StationaryUnivariate(univ, region, options)
    # Set iterator over TimeSeries
    timeseries = iter_timeseries_(univ.parser, univ.obs, univ.cset, size=size)
    # call the function performing computation and updating stationary
    set_stationary_autocorrelation(timeseries, univ, stationary,
                                   tmin=region.tmin, tmax=region.tmax,
                                   adjust_mean=options.adjust_mean,
                                   disjoint=options.disjoint)
    _update_univariate_from_stationary(univ, stationary)
    return stationary


# %% CROSS CORRELATION
def _update_univariate_from_bivariate(univs, two):
    for cdt_lab in two._condition_labels:
        cdt_two = two[cdt_lab]
        for k in range(2):
            univs[k][cdt_lab].two[str(univs[k-1].obs)] = cdt_two
    return


def initialize_bivariate(row_univariate, col_univariate):
    """Initialize a StationaryBivariate instance from its dynamical one.

    Parameters
    -----------
    row_univariate : :class:`Univariate` instance
    col_univariate : :class:`Univariate` instance

    Returns
    -------
    :class:`Bivariate` instance
        set up with empty arrays
    """
    two = Bivariate(row_univariate, col_univariate)
    univs = row_univariate, col_univariate
    _update_univariate_from_bivariate(univs, two)
    return two


def compute_bivariate(row_univariate, col_univariate, size=None):
    """Computes cross-correlation between observables defiend in univs.

    This functions handles conditions and time-window binning:
    * all conditions provided in cset are applied independently, in addition
      to the computation with unconditioned data (labelled 'master')
    * A time-binning window is provided with a given offset and a period.
      Explicitely a given time value t found in data will be rounded up to
      closest offset_t + k * delta_t, where k is an integer.

    Parameters
    ----------
    univs : couple of Univariate instances
    size : int (default None)
        limit the iterator to size Lineage instances (used for testing)

    Returns
    -------
    TwoObservable instance
    """
    univs = row_univariate, col_univariate
    s1, s2 = univs
    obs1 = s1.obs
    obs2 = s2.obs
    # check that the two observables are either two dynamics mode, either zero
    if obs1.mode != obs2.mode:
        if obs1.mode == 'dynamics' or obs2.mode == 'dynamics':
            msg = ('Cannot mix time-lapse and cell-cycle observables:\n'
                   'Here obs1.mode = {} and obs2.mode = {}'.format(obs1.mode,
                                                                   obs2.mode))
            raise TypeError(msg)
        elif obs1.timing == 'g':
            if obs2.timing != 'g':
                msg = ('If one observable is evaluated in generation time, '
                       'the other one must be as well in generation time.')
                raise TypeError(msg)
        elif obs2.timing == 'g':
            if obs1.timing != 'g':
                msg = ('If one observable is evaluated in generation time, '
                       'the other one must be as well in generation time.')
                raise TypeError(msg)
    # initialize Univariate and each of its item
    two = Bivariate(row_univariate, col_univariate)  # empty
    parser = two.parser
    cset = two.cset
    timeseries = iter_timeseries_2(parser, obs1, obs2, cset, size=size)
    # call the master function performing computation
    set_crosscorrelation(timeseries, row_univariate, col_univariate, two)
    # update conditioned univ cross-correlation
    _update_univariate_from_bivariate(univs, two)
    return two


def _update_univariate_from_stationary_bivariate(univs, stwo):
    for cdt_lab in stwo._condition_labels:
        cdt_two = stwo[cdt_lab]
        for k in range(2):
            univs[k][cdt_lab].two_stationary[str(univs[k-1].obs)] = cdt_two
    return


def initialize_stationary_bivariate(row_univariate, col_univariate,
                                    region, options):
    """Initialize a StationaryBivariate instance from its dynamical one.

    Parameters
    -----------
    univs : couple of :class:`Univariate` instances
    tmin : float (default None)
    tmax : float (default None)

    Returns
    -------
    :class:`StationaryBivariate` instance
        set up with empty arrays
    """
    stwo = StationaryBivariate(row_univariate, col_univariate,
                               region, options)
    univs = row_univariate, col_univariate
    _update_univariate_from_stationary_bivariate(univs, stwo)
    return stwo


def compute_stationary_bivariate(row_univariate, col_univariate,
                                 region, options, size=None):
    """Computes stationary cross-correlation function from couple of univs

    Need to compute stationary univariates as well.
    """
    s1, s2 = row_univariate, col_univariate
    obs1 = s1.obs
    obs2 = s2.obs
    univs = row_univariate, col_univariate
    # stationary univariate need to be computed for full inspection
    for univ in univs:
        try:
            suniv = initialize_stationary_univariate(univ, region, options)
            suniv.import_from_text()
        except StationaryUnivariateIOError:
            suniv = compute_stationary_univariate(univ, region, options)
            suniv.export_text()
        _update_univariate_from_stationary(univ, suniv)
    sbivar = StationaryBivariate(row_univariate, col_univariate,
                                 region, options)
    parser = sbivar.parser
    cset = sbivar.cset
    timeseries = iter_timeseries_2(parser, obs1, obs2, cset, size=size)
    set_stationary_crosscorrelation(timeseries, row_univariate, col_univariate,
                                    sbivar,
                                    tmin=region.tmin, tmax=region.tmax,
                                    adjust_mean=options.adjust_mean,
                                    disjoint=options.disjoint)
    # update conditioned univ stationary cross-correlation
    _update_univariate_from_stationary_bivariate(univs, sbivar)
    return sbivar
