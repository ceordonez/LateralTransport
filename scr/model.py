#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from scipy.optimize import curve_fit
from scipy.interpolate import interp1d


def transport_model(OMP, Fsed, Fhyp, Fdis, Kh, Kch4, modelparam, model_conf, x=None,
                    opt=False, levellog=20):
    """Calculate the lateral tranport from methane C(x,t) from a 1-D model based on finete difference approach.# {{{

    Prameters
    ---------
    OMP : TODO
    Fsed : TODO
    Fhyp : TODO
    Kh : TODO
    Kch4 : TODO
    modelparam: TODO
    model_conf: TODO
    x : TODO
    opt : TODO

    Returns
    -------
    C, r : CH4 concentration along a transect.

    """# }}}

    dr = model_conf['dr']
    tf = model_conf['t_end']
    dt = model_conf['dt']

    R = modelparam.Radius.values[0]
    Hsml = modelparam.Hsml.values[0]
    Rs = modelparam.Rs.values[0]
    Hcp = modelparam.Hcp.values[0]
    Patm = modelparam.Patm.values[0]
    typ = modelparam.Type.values[0]
    Kz = modelparam.Kz.values[0]
    Chyp = modelparam.Chyp.values[0]

    t = np.arange(0, tf + dt, dt)
    r = np.arange(0, R + dr, dr)  # From 0 to R
    Fs = np.zeros(len(r))
    kz = np.zeros(len(r))
    Fz = np.zeros(len(r))
    h = np.ones(len(r)) * Hsml
    m = np.zeros(len(r))

    Fs[r > Rs] = Fsed
    m[r > Rs] = -Hsml / (r.max() - Rs)
    h[r > Rs] = m[r > Rs] * (r[r > Rs] - r.max())
    h[-1] = 1E10000
    kz[r < Rs] = Kz * 60 * 60 * 24  # m/d
    Fz[r < Rs] = Fhyp

    # Initial Conditions
    C = np.ones((len(r), len(t))) * Patm * Hcp
    p1 = np.zeros(len(r) - 1)
    p2 = np.ones(len(r))
    p3 = np.zeros(len(r) - 1)
    # Type of lake elongated ('E') and round ('R')
    if typ == 'R':
        type_dev = 1 / r[1:-1] + m[1:-1] / h[1:-1]
    if typ == 'E':
        type_dev = m[1:-1] / h[1:-1]
    #Crating matrix
    p1[:-1] = -Kh * dt / (dr**2) + Kh * dt / (2 * dr) * (1 / r[1:-1] + m[1:-1] / h[1:-1])
    p2[1:-1] = 1 + 2 * Kh * dt / (dr**2) + Kch4 * dt / h[1:-1] + Kz / h[1:-1]
    p3[1:] = -Kh * dt / (dr**2) - Kh * dt / (2 * dr) * (1 / r[1:-1] + m[1:-1] / h[1:-1])
    B = np.diag(p1, k=-1) + np.diag(p2) + np.diag(p3, k=1)
    Bp = np.linalg.inv(B)
    Ssed = Fs * dt / h
    #Shyp = Fz*dt/h
    Shyp = kz * Chyp * dt / h
    #Shyp = Fz*dt/h
    Ssed[-1] = 0  # Sediment flux = 0 at the sediment
    Somp = OMP * 1E-3 * np.ones(len(Ssed)) * dt
    if Fdis is not None:
        f_dis = interp1d(Fdis['Radius [m]'], Fdis['Diss [micro-mol/m3/d]'], kind='nearest',
                         fill_value='extrapolate')
        Sdis = f_dis(r) * dt / 1000.
    else:
        Sdis = np.zeros(len(Ssed))
    Somp[0] = 0
    Sdis[0] = 0
    sources = Ssed + Somp + Sdis + Shyp  #Kz*Chyp/h
    #for n in range(len(t) - 1):
    n = 0
    err = np.ones(len(t)) * np.inf
    while True:
        C[1:-1, n + 1] = Bp.dot(C[:, n] + sources)[1:-1]
        # Border conditions
        C[0, n + 1] = C[1, n + 1]
        C[-1, n + 1] = C[-2, n + 1]
        err[n + 1] = abs(C[1:-1, n + 1].mean() - C[1:-1, n].mean())
        if n >= len(t) - 2:
            C = C[:, :n + 2]
            if not opt:
                logging.log(levellog, 'Mean model concentration %.2f', C[:, -1].mean())
                logging.log(levellog,'Model finish at maximun days')
            break
        if err[n + 1] < 0.0001:
            C = C[:, :n + 2]
            if not opt:
                logging.log(levellog,'Mean model concentration %.2f', C[:, -1].mean())
                logging.log(levellog,'Model finish after %.0f days', t[n + 1])
            break
        n += 1
    C = C[:, -1]
    Fa = Kch4 * (C - Hcp * Patm)
    Fa = Fa.mean()
    r = r.max() - r
    if opt:
        p = np.polyfit(r, C, 10)  #kind = 'cubic')
        f = np.poly1d(p)
        C = f(x)
        return C
    else:
        return r, C, Fa


# }}}


def opt_test(f_tdata, sources_avg, sources_fr, modelparam, model_conf, levellog=20):  # {{{

    s_r = f_tdata.index.values.copy()
    s_C = f_tdata.CH4.values.copy()
    Fsed = sources_avg.Fsed.values[0]
    Fhyp = sources_avg.Fhyp.values[0]
    Rdis = sources_fr
    R = modelparam.Radius.values[0]
    s_r[s_r > R] = R
    Kh = modelparam.Kh.values[0]
    kch4 = modelparam.kch4.values[0]

    if model_conf['mode_model']['var'] == 'FSED':
        opt, cov = curve_fit(lambda ds_r, Fsed: \
                             transport_model(0, Fsed, Fhyp, Rdis, Kh, kch4, modelparam, model_conf, s_r, True, levellog), s_r, s_C,
                              bounds=(0, np.inf))
        r, C, Fa = transport_model(0, opt, Fhyp, Rdis, Kh, kch4, modelparam, model_conf, levellog=levellog)
        var = 'Fsed_opt'
    elif model_conf['mode_model']['var'] == 'OMP':
        logging.log(levellog, 'Fitting OMP')
        opt, cov = curve_fit(lambda s_r, OMP: \
                             transport_model(OMP, Fsed, Fhyp, Rdis, Kh, kch4, modelparam, model_conf, s_r, True, levellog), s_r, s_C,
                             bounds=(-np.inf, np.inf))
        r, C, Fa = transport_model(opt, Fsed, Fhyp, Rdis, Kh, kch4, modelparam, model_conf, levellog=levellog)
        var = 'OMP_opt'
    elif model_conf['mode_model']['var'] == 'KH':
        opt, cov = curve_fit(lambda s_r, Kh: \
                             transport_model(0, Fsed, Fhyp, Rdis, Kh, kch4, modelparam, model_conf, s_r, True, levellog), s_r, s_C,
                             bounds=(Kh/10.,Kh*10))
        r, C, Fa = transport_model(0, Fsed, Fhyp, Rdis, opt, kch4, modelparam, model_conf, levellog=levellog)
        var = 'kh_opt'
    elif model_conf['mode_model']['var'] == 'KCH4':
        opt, cov = curve_fit(lambda s_r, ks: \
                             transport_model(0, Fsed, Fhyp, Rdis, Kh, kch4, modelparam, model_conf, s_r, True, levellog), s_r, s_C,
                             bounds=(0, np.inf))
        r, C, Fa = transport_model(0, Fsed, Fhyp, Rdis, Kh, opt, modelparam, model_conf, levellog=levellog)
        var = 'kch4_opt'
    return r, C, Fa, opt, var  # }}}
