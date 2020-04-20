#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import numpy as np
import logging
import pandas as pd
import pdb
import cmath

from scipy.special import iv, jv, yn, i0
from scipy.interpolate import interp1d
#import warnings
#warnings.filterwarnings("error")

def delsontro(C, L, kch4, r, kop, Zml, Ty, kht=0):
    """
    C: Concentration (umol/l)
    L: Lenght scale (m)
    r: lake radio (m)
    Zml: Mixed layer depth (m)
    Ty : type (round R or elongated E)
    kop:
    kht: horizontal diffusivite (Peeters and Hofmann 2015 = 0
        Lawrence et al 1995 = 1)
    """
    if kht == 0:
        Kh = 1.4*10**(-4)*L**(1.07)*86400 #(m2/d)
    elif kht == 1:
        Kh = 3.2*10**(-4)*L**(1.10)*86400 #(m2/d)

    indmin = C.index.min()
    indmax = C.index.max()
    r = indmax
    x = np.linspace(0, r, 50) #Change in config_lake and use r if you want use another radio
    if kop+kch4/Zml < 0: ## Case 1: Very high production!
        lda = np.sqrt(-(kch4/Zml + kop)/Kh)
        if Ty == 'R':
            Co = C.loc[indmin]
            ic = complex(0,1)
            Cx = x*np.NAN#Co*iv(0, ic*lda*(r-x))/iv(0, ic*lda*r)
        elif Ty == 'E':
            Co = C.loc[indmin]
            Cf = Co
            A = (Cf - Co*np.cos(lda*2*r))/np.sin(lda*2*r)
            Cx = A*np.sin(lda*x) + Co*np.cos(lda*(x))
    else:
        lda = np.sqrt((kch4/Zml + kop)/Kh)
        if Ty == 'R':
            Co = C.loc[indmin]
            Cx = Co*iv(0,lda*(r-x))/iv(0,lda*r)
            #x = r - x

        elif Ty == 'E':
            Co = C.loc[indmin]
            Cf = Co
            A = Co/(1+np.exp(-lda*2*r))
            Cx = A*(np.exp(-lda*x) + np.exp(-lda*(2*r-x)))
    return Cx, x, lda, Kh
def Hcp(T):
    T = T + 273.15
    H = 1.4E-5 # mol/m3/Pa Sander 2015
    lndHdt = 1750
    Hcp = H*np.exp(lndHdt*(1/T-1/298.15))*1000 # umol/l/Pa
    return Hcp

def keeling(C, dC):
    pol = np.polyfit(1/C, dC, 1)
    ds = pol[1]
    return ds, pol[0]

def f_k600(U10, A):
    """
    A: Lake area (km2)
    U10: wind speed at 10m (m/s)
    """
    k600 = 2.51 + 1.48*U10 + 0.39*U10*np.log10(A) # (cm/h) Vachon and Praire (2013)
    k600 = k600*24/100. #(m/d)
    return k600

def fractionation(C, dC, ds, a=1.02):
    try:
        y = np.log(((a-1)*1000)-(dC-ds))
        pol = np.polyfit(np.log(C), y, 1)
    except Exception:
        pdb.set_trace()
    b0 = pol[1]
    b1 = pol[0]
    return b0, b1

def f_kop(b0, b1, kch4, Zml):
    kop = b1*kch4/Zml/(1-b1)
    return kop

def Sc_ch4(T):
    sc = 1897.8-114.28*T+3.2902*T**2-0.039061*T**3
    return sc

def f_kch4(T, k600, U10):
    # Prairie and del Giorgo 2013
    if U10 > 3.7:
        n = 1/2.
    else:
        n = 2/3.
    kch4 = k600*(600/Sc_ch4(T))**n
    return kch4.mean()


def pross_data(data, clake, Kh_model, Bio_model):
    r_lake = []
    r_date = []
    params = []
    allres = dict()
    ladate = dict()
    for lake in data:
        for date in data[lake]:
            logging.info('Processing data from lake %s on %s', lake, date)
            L = clake[lake][date][2]
            r = clake[lake][date][3]
            filt = clake[lake][date][4]
            tym = clake[lake][date][5]
            zml = clake[lake][date][1]
            A = clake[lake][date][0]
            if filt: # filter data
                ld_data = data[lake][date].reset_index()
                fdata = ld_data.drop(filt)
                fdata = fdata.set_index(['Distance'])
            else:
                fdata = data[lake][date]
            # Getting data from transect file
            C = fdata.CH4
            dC = fdata.dCH4
            T = fdata.Temp
            Hch4 = Hcp(T).mean() #umol/l/Pa
            Patm = fdata.CH4_atm.mean() # Atmospheric partial pressure (Pa)
            # Processing data Transect
            U10 = fdata.U10.mean()
            k600 = f_k600(U10, A)
            kch4 = f_kch4(T, k600, U10)
            Temp = T.mean()
            # Bio model with kop
            ds, pol0 = keeling(C, dC)
            b0, b1 = fractionation(C, dC, ds)
            kop = f_kop(b0, b1, k600, zml)
            Cxop, x, ldaop, Kh = delsontro(C, L, kch4, r, kop, zml, tym, Kh_model)
            # Physical model
            Cx, x, lda, Kh = delsontro(C, L, kch4, r, 0, zml, tym, Kh_model)

            # Results Surface fluxes
            Fads = kch4*(Cx - Hch4*Patm) # Flux from model DelSontro
            Fa = kch4*(C - Hch4*Patm) # Flux k model data transect
            Fa = np.mean(Fa)
            Fa_fc = fdata.Fa_fc.mean() # Flux from chambers transect
            kch4_fc = fdata.Fa_fc/(C - Hch4*Patm) # kch4 from flux chambers
            kch4_fc = kch4_fc.mean()
            Fads = np.mean(Fads)
            Cavg = C.mean()

            # Saving results
            datares = {'CH4_op': Cxop, 'CH4': Cx}
            datares = pd.DataFrame(datares, index=x)
            r_lake.append(lake)
            r_date.append(date)
            params.append([k600, kch4, Temp, U10, Fa, Fads, Fa_fc, kch4_fc, Cavg, Patm, Hch4, Kh])
            ladate.update({date: datares})
        allres.update({lake: ladate})
    nameres = ['k600', 'kch4', 'Temp', 'U10', 'Fa', 'Fa_ds', 'Fa_fc', 'kch4_fc', 'Cavg', 'Patm', 'Hcp','Kh']
    pindex = [np.array(r_lake), np.array(r_date)]
    paramres = pd.DataFrame(data = params, columns = nameres,
                            index=pindex)
    paramres.index.names = ['Lake', 'Date']
    return allres, paramres

