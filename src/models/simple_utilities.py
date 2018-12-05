import pandas as pd
from ..features.extract_events import extract_events,get_events
import h5py
import numpy as np
import os

import itertools

def list_transition(length=5):
    lt = [list(s) for s in itertools.product(["A","T","C","G"], repeat=length)]
    return lt,{"".join(s):lt.index(s) for s in lt}
list_trans,d_trans=list_transition(5)

def get_signal_expected(x,Tt):
    real = []
    th = np.zeros((len(x["bases"])-8))
    real = np.zeros((len(x["bases"])-8))

    for n in range(2,len(x["bases"])-6):
        delta = x["mean"][n+1]-x["mean"][n]

        i1 = d_trans["".join(x["bases"][n-2:n+3].tolist())]
        i2 = d_trans["".join(x["bases"][n-1:n+4].tolist())]
        real[n-2]=delta
        th[n-2]=Tt[i1,i2]
    return real,th

def get_tmiddle(x):
    Tm = []
    for n in range(2,len(x["bases"])-6):
        if x["bases"][n] == "T" or x["bases"][n+1]=="T":
            Tm.append(True)
        else:
            Tm.append(False)
    return np.array(Tm)

from scipy import optimize

def rescale_deltas(real,th,Tm):

    def f(x):
        return np.median(((real[~Tm]-x[0])/x[1] - th[~Tm])**2)
    return optimize.minimize(f, [0,1], method="CG")
def deltas(which,th,Tm):
    return np.mean((which-th)**2),np.mean((which[~Tm]-th[~Tm])**2),np.mean((which[Tm]-th[Tm])**2)


def load_data(lfiles, values=["saved_weights_ratio.05-0.03","init_B"], root=".", per_dataset=None):
    X = []
    y = []
    for file in lfiles:
        d = pd.read_csv(file)
        #print(file, d)
        X1 = [os.path.join(root,f) for f in d["filename"]]
        found = False
        for value in values:
            if value in d.columns:

                y1 = d[value]
                print("using value",value)
                found=True
                break
        if not found:
            print("Values not found",values)
            print("Available",d.columns)
            raise
        #print(np.mean(y1), np.std(y1),len(y1),len(X1))
        yw = d["init_w"]
        #print("Weight", np.mean(yw),len(yw))
        y1 = [[iy1, iyw] for iy1, iyw in zip(y1, yw)]
        #print(len(y1))
        if per_dataset is None:
            X.extend(X1)
            y.extend(y1)
        else:
            X.extend(X1[:per_dataset])
            y.extend(y1[:per_dataset])
    assert (len(X) == len(y))
    #print(y)
    return X, y



def load_events(X, y, min_length=1000,ws=5,raw=False,base=False,maxf=None,extra=False):
    Xt = []
    indexes = []
    yt = []
    fnames = []
    empty = 0
    extra_e =[]
    for ifi, filename in enumerate(X):
        # print(filename)

        h5 = h5py.File(filename, "r")
        tomb=False
        if base:
            tomb=True
        events,rawV,sl = get_events(h5, already_detected=False,
                            chemistry="rf", window_size=np.random.randint(ws, ws+3),
                            old=False, verbose=False,
                             about_max_len=None,extra=True,tomb=tomb)

        if events is None:
            empty += 1
            events={"mean":[],"bases":[]}
        if raw:
            #print(len(rawV))
            events={"mean":rawV}



        #events = events[1:-1]

        if min_length is not None and  len(events["mean"]) < min_length:
            continue

        if extra:
            extra_e.append([rawV,sl])
        # print(y[ifi])
        if base:
            Xt.append({"mean":events["mean"],"bases":events["bases"]})
        else:
            Xt.append({"mean":events["mean"]})


        h5.close()

        yt.append(y[ifi])
        indexes.append(ifi)
        fnames.append(filename)
        if maxf is not None:
            if ifi -empty> maxf:
                break
    print("N empty %i, N files %i"%(empty,ifi))
    if not extra:
        return Xt, np.array(yt),fnames
    else:
        return Xt, np.array(yt),fnames,extra_e


def scale(x,rescale=False):
    x -= np.percentile(x, 25)
    if rescale:

        scale = np.percentile(x, 60) - np.percentile(x, 20)
        #print("la")
    else:
        scale=20
    # print(scale,np.percentile(x, 75) , np.percentile(x, 25))
    #x /= scale
    x /= scale
    if np.sum(x > 10) > len(x) * 0.05:
        print("Warning lotl of rare events")
        print(np.sum(x > 10), len(x))
    x[x > 5] = 0
    x[x < -5] = 0

    return x

def scale_one_read(events,rescale=False):
    mean = events["mean"]
    #std = events["stdv"]
    #length = events["length"]

    mean = scale(mean.copy(),rescale=rescale)
    """
    mean -= np.percentile(mean, 50)
    delta = mean[1:] - mean[:-1]
    rmuninf = (delta > -15) & (delta < 15)
    mean = delta[~rmuninf]"""
    #std = scale(std.copy())
    # print("stl")
    #length = scale(length.copy())
    # print("el")
    V = np.array([mean]).T
    return V

def transform_reads(X, y, lenv=200,max_len=None,overlap=None,delta=False,rescale=False,noise=False,extra_e=[],Tt=[]):
    Xt = []
    yt = []
    # print(y.shape)
    # print(y)
    def mapb(B):
        s ="ATCG"
        r = [0,0,0,0]
        r[s.index(B)]=1
        return r

    for ip,(events, yi) in enumerate(zip(X, y)):
        if type(events) == dict and "bases" in events.keys():
            V = np.array([ [m] + mapb(b) for m,b in zip(events["mean"],events["bases"])])
            if rescale and extra_e !=[] and len(V) !=0:


                real,th = get_signal_expected(events,Tt)
                Tm = get_tmiddle(events)
                rs = rescale_deltas(real,th,Tm)
                new = real.copy()
                new = (new-rs["x"][0])/rs["x"][1]
                V=V[2:2+len(new)]
                V[::,0]=new

        else:
            V = scale_one_read(events,rescale=rescale)

        if delta:
            V = V[1:]-V[:-1]

        if max_len is not None:
            V = V[:max_len]

        if overlap is None:
            if lenv is not None:
                #print(V.shape,yi.shape)
                if len(V) < lenv:
                    continue
                # print(V.shape,yi.shape)

                lc = lenv * (len(V) // lenv)
                V = V[:lc]
                V = np.array(V).reshape(-1, lenv, V.shape[-1])

                yip = np.zeros((V.shape[0], yi.shape[0]))
                yip[::] = yi
            else:
                ypi=yi
        else:
            lw = int(lenv // overlap)


            An = []
            for i in range(overlap - 1):
                An.append(V[i * lw:])

            An.append(V[(overlap - 1) * lw:])

            minl = np.min([len(r)//lenv for r in An])
            An = np.array([np.array(ian[:int(minl*lenv)]).reshape(-1,lenv,V.shape[-1]) for ian in An])
            V= np.array(An)

            yip = np.zeros((V.shape[0], yi.shape[0]))
            yip[::] = yi

        if noise:
            #print(V.shape)
            if overlap:
                V[::,::,::,0] *= (0.9+0.2*np.random.rand(V.shape[1])[np.newaxis,::,np.newaxis])
            else:
                V[::,::,0] *= (0.9+0.2*np.random.rand(V.shape[0])[::,np.newaxis])

        Xt.append(V)
        yt.append(yip)
    return Xt, np.array(yt)
