
import glob
try:
    from ..features.bwa_tools import get_seq
    from ..features.extract_events import get_raw, extract_events, tv_segment
except:
    from features.bwa_tools import get_seq
    from features.extract_events import get_raw, extract_events, tv_segment
import h5py
import numpy as np
from Bio import pairwise2
import pylab
import subprocess
import pandas as pd
import tempfile
import os
import copy


class NotAllign(Exception):

    def __init__(self, delta):
        self.message = "Delta = % i" % delta

REF = "data/external/ref/S288C_reference_sequence_R64-2-1_20150113.fa"
REFH = "data/external/chromFa/all_chra.fa"


class Dataset:

    def __init__(self, samfile, root_files, metadata=""):
        self.root_files = root_files
        self.samfile = samfile
        self.metadata = metadata
        self.substitution = "T"

    def populate(self, maxf=None, minion=True, basecall=True,
                 filter_not_alligned=False,
                 filter_ch=None, realign=False, arange=[], base_call=False, samf=""):
        self.strands = []
        lstrand = glob.glob(self.root_files + "/*")
        lstrand.sort()

        print("Number of strands found %i in %s " % (len(lstrand), self.root_files))

        def find_strand(strand):
            for st in lstrand:
                if strand in st:
                    return st

        if not base_call or samf == "":

            if arange == []:
                self.strands = [Strand(fn) for fn in lstrand]
            else:
                tot = len(lstrand)
                self.strands = []
                for ifn, fn in enumerate(lstrand):
                    if ifn / tot > arange[0] and ifn / tot < arange[1]:
                        self.strands.append(Strand(fn))
            return

        with open(self.samfile, "r") as f:
            fich = f.readlines()
            fich = list(set(fich))
            fich.sort()

            filtered_fich = []
            processed = []
            for ifich in fich:
                if ifich.startswith("@ch") and ifich.split()[0] not in processed:
                    filtered_fich.append(ifich)
                    processed.append(ifich.split()[0])
            fich = filtered_fich
            print("Total number of files", len(fich))

            tot = len(fich)
            for iline, line in enumerate(fich):
                # print(line)

                if arange != []:
                    # print(arange, iline, tot, iline / tot > arange[0] and iline / tot < arange[1])
                    if iline / tot > arange[0] and iline / tot < arange[1]:
                        pass
                    else:
                        continue
                # print("p")
                if maxf is not None and len(self.strands) >= maxf:
                    break
                sp = line.split()
                if len(sp) > 1 and sp[0].startswith("@ch"):
                    # print(sp[:4])
                    if "chr" in sp[2]:
                        X = int(sp[2][3:])
                    else:
                        X = 0

                    fn = "read_%s_ch_%s_" % (sp[0].split("_")[1][4:], sp[0].split("_")[0][3:])
                    # print(fn)
                    # print(find_strand(fn))

                    if filter_ch is not None and X not in filter_ch:
                        print("Skip in ch %i " % X)
                        continue

                    self.strands.append(Strand(find_strand(fn),
                                               X_from_Minion=int(X),
                                               t_from_Minion=0,
                                               sam_line_minion=line))

                    if basecall:
                        try:
                            r = self.strands[-1].get_seq(f="BaseCall")
                            self.strands[-1].signal_bc, self.strands[-1].seq_from_basecall, self.strands[-1].imin, \
                                self.strands[-1].raw, self.strands[-1].to_match, self.strands[
                                -1].sampling_rate = r
                        except NotAllign:
                            print("Strand %i raw not alligned to basecall" % len(self.strands))

                            if filter_not_alligned:
                                print("Removed")
                                self.strands.pop(-1)
                    if minion:
                        if realign:
                            self.strands[-1].seq_from_minion = self.strands[-1].get_ref(
                                self.strands[-1].seq_from_basecall, correct=True)
                        else:
                            self.strands[-1].seq_from_minion = self.strands[-1].get_seq(
                                f="Minion", correct=True)

            """
            chp = kp.split("_")[0][3:]
            readp =  kp.split("_")[1][4:]
"""

"""
def compare_metrichor(file_netw,type_b="B",show_identical=False,ntwk=None):

    if type_b == "T":
        contrl = "BTF_AG_ONT_1_FAH14273_A-select.sam"
    if type_b == "B":
        contrl = "BTF_AH_ONT_1_FAH14319_A-select.sam"
    if type_b == "L":
        contrl = "BTF_AI_ONT_1_FAH14242_A-select.sam"
    if type_b == "E":
        contrl = "BTF_AK_ONT_1_FAH14211_A-select.sam"
    if type_b == "I":
        contrl = "BTF_AL_ONT_1_FAH14352_A-select.sam"

    with open(file_netw +"/"+ contrl.replace("select","select_pass_test_T"),"r") as f:
        datan = {}
        for line in f.readlines():
            sp = line.split()

            if len(sp) > 1 and sp[0].startswith("data"):
                datan[sp[0].split("/")[-1]] = sp[1:4]
            else:
                pass
                # print(sp)

"""


class Strand:

    def __init__(self, filename, X_from_Minion=0, t_from_Minion=0, sam_line_minion=""):
        self.filename = filename
        self.X_from_Minion = X_from_Minion
        self.t_from_Minion = t_from_Minion
        self.sam_line_minion = sam_line_minion
        self.Bprop = 0
        self.Eprop = 0
        self.Iprop = 0

    def get_seq(self, f, correct=False, window_size=5, method="FW",
                allinfos=False, maxlen=70, minlen=1, gamma=40, flatten=False):
        if f == "Minion":
            seq, sucess = get_seq(self.sam_line_minion, ref=REF, from_line=True, correct=correct)
            self.seq_from_minion = seq
            return self.seq_from_minion

        if f == "no_basecall":
            sig = self.segmentation(w=window_size, method=method,
                                    allinfos=allinfos, maxlen=maxlen, minlen=minlen, gamma=gamma, flatten=flatten)
            names = ["mean", "stdv", "length", "start", "all"]

            return pd.DataFrame({n: sig[n] for n in names}).convert_objects(convert_numeric=True)

        if f == "BaseCall":
            h5 = h5py.File(self.filename, "r")
            e2bis = h5["Analyses/Basecall_1D_000/BaseCalled_template/Events"]

            s2 = ""
            self.signal_bc = []
            left = None
            dimer = True
            sup = []
            for ie, (s, length, m, ms, move, stdv) in enumerate(zip(e2bis["start"], e2bis["length"],
                                                                    e2bis["mean"], e2bis["model_state"], e2bis["move"], e2bis["stdv"])):

                state = "%s" % ms.tostring()
                state = state[2:-1]  # to remove b' and '
                # print(s)
                # state = state[2]
                # sup.append("N")
                if move == 1:
                    s2 += state[2]
                    state = state[2]
                    self.signal_bc.append(["N" + state, m, stdv, length, s])
                    left = None
                elif move >= 2:
                    s2 += state[1:3]
                    state = state[1:3]

                    if self.signal_bc[-1][0] == "N" and not dimer:
                        self.signal_bc[-1][0] = state[0]
                        self.signal_bc.append([state[1], m, stdv, length, s])
                    else:

                        self.signal_bc.append([state, m, stdv, length, s])
                        # sup[-1] = state[0]
                        if not dimer:
                            left = state[1]

                elif move == 0:
                    self.signal_bc.append(["NN", m, stdv, length, s])
                    if left is not None:
                        self.signal_bc[-1][0] = left
                    left = None
                else:
                    left = None

            names = ["seq", "mean", "stdv", "length", "start"]
            D = {na: [] for na in names}
            for s in self.signal_bc:
                for i, na in enumerate(names):
                    D[na].append(s[i])

            for name in names[1:]:
                D[name] = np.array(D[name])

            self.csignal = self.signal_bc.copy()

            self.signal_bc = pd.DataFrame(D)

            self.allign_basecall_raw()
            # print(self.signal_bc)

            self.signal_bc["start"] += (self.imin / self.sampling_rate - self.signal_bc["start"][0])

            self.seq_from_basecall = s2
            # print(self.signal_bc)
            self.D = D
            return self.signal_bc, self.seq_from_basecall, self.imin, self.raw, self.to_match, self.sampling_rate

    def score_ref(self, maxlen=1000):
        s1 = self.seq_from_minion
        s2 = self.seq_from_basecall
        self.score(s1, s2, maxlen=maxlen)

    def get_ref(self, sequence, correct=False, pos=False, find_ref=True, human=False):

        import time
        t0 = time.time()
        h, name = tempfile.mkstemp(prefix="", dir="./")
        os.close(h)
        with open(name + ".fasta", "w") as output_file:
            filename = "tmp"
            output_file.writelines(">%s_template_deepnano\n" % filename)
            output_file.writelines(sequence.replace("B", "T") + "\n")

        # try to add some prefix to the ref:

        ref = REF
        if human:
            ref = REFH
        if not os.path.exists(ref):
            if os.path.exists("../../" + ref):
                pre = "../../"

            elif os.path.exists("/data/bioinfo@borvo/users/jarbona/deepnano5bases/" + ref):
                pre = "/data/bioinfo@borvo/users/jarbona/deepnano5bases/"
            else:
                print(ref, "not found")
        else:
            pre = ""
        print("Ref", pre + ref)
        exex = "bwa mem -x ont2d  %s  %s.fasta > %s.sam" % (pre + ref, name, name)
        try:
            subprocess.check_output(exex, shell=True, stderr=subprocess.STDOUT, close_fds=True)
        except subprocess.CalledProcessError as e:
            print(e.output)
            print(exex)

        print(time.time() - t0)

        t0 = time.time()
        ref, succes, X1, P1 = get_seq("%s.sam" % name, ref=pre + ref,
                                      ret_pos=True, correct=correct, find_ref=find_ref)
        # print(X1, P1)
        print(time.time() - t0)
        os.remove("%s.sam" % name)
        os.remove("%s.fasta" % name)
        os.remove(name)
        if not pos:
            return ref
        else:
            return ref, X1, P1

    def score(self, s1, s2, maxlen=None, all_info=False, c1=-0.5, c2=-0.5):

        if s1 == "":
            return None
        if s2 == "":
            return None

        if maxlen is not None:
            s1 = s1[:maxlen]
            s2 = s2[:maxlen]

        al = pairwise2.align.globalxs(s1, s2, c1, c2, one_alignment_only=True)[0]

        if all_info:
            return al
        else:
            return al[2] / len(s1)

    def allign_basecall_raw(self):

        h5 = h5py.File(self.filename, "r")
        raw, amp = get_raw(h5)

        e2bis = h5["Analyses/Basecall_1D_000/BaseCalled_template/Events"]
        to_match = np.zeros(int((e2bis["length"][-1] + e2bis["start"]
                                 [-1] - e2bis["start"][0]) * amp)) * np.nan

        s0 = e2bis["start"][0]

        for ie, (s, l, m) in enumerate(zip(e2bis["start"], e2bis["length"], e2bis["mean"])):
            to_match[int((s - s0) * amp):int(((s + l - s0) * amp))] = m

        mini = 100000
        lmatch = len(to_match)
        imin = 0
        for i in range(len(raw) - lmatch)[:5000]:
            delta = np.nanmean((raw[i:i + lmatch] - to_match)**2)
            if delta < mini:
                imin = i + 0
                mini = delta + 0
                # print(delta)

        if mini > 100:
            raise NotAllign(mini)
        # print(delta,imin)
        self.imin = imin
        self.to_match = np.array(to_match, dtype=np.float16)
        self.raw = np.array(raw, dtype=np.float16)
        self.sampling_rate = amp

    def get_seq_mean(self, motif, ref, short=True, void="N", caract="mean"):

        seq = "".join(ref["seq"]).replace(void, "")
        # print("Look")
        if motif in seq:
            num = [i for i, l in(enumerate(ref["seq"])) if l != void + void]
            index = seq.index(motif)
            if short:
                return motif, np.array(ref[caract][num[index:index + len(motif)]])
            else:
                return motif, np.array(ref[caract][num[index]:num[index + len(motif)]])
        else:
            return motif, None

    def give_map(self, ref, allgn):
        """
        given a ref from basecall or network, and an allignment with
        the true sequence, return a new ref, matching more closely
        the true sequence
        """
        indexes = [i for i, l in enumerate(ref) if l != "N"]
        # print(indexes)
        i = 0
        alb = []
        for l in allgn[0]:
            if l != "-":
                alb.append(indexes[i])
                i += 1
            else:

                # if in alb there are "-" which are surrounded by non adjacent integer we
                # can add insert letters:
                if alb != [] and type(alb[-1]) == int and i < len(indexes) and indexes[i] - 1 > alb[-1]:
                    alb.append(alb[-1] + 1)
                else:
                    alb.append("-")

        """print(allgn[0])
        print("".join(map(str, alb)))
        print(allgn[1])"""

        # Look for numeric which correspend to "-" to see if we can insert more of the sequence
        # Look for diagonal pattern of "-"
        switch = []
        for ind, (num, nump, l, lp) in enumerate(zip(alb[:-1], alb[1:], allgn[1][:-1], allgn[1][1:])):

            if (num == "-" and lp == "-") or (nump == "-" and l == "-"):
                switch.append(ind)
        # print(switch)
        for ind in switch:
            alb[ind], alb[ind + 1] = alb[ind + 1], alb[ind]

        mapped = ["N" for l in ref]
        for num, l in zip(alb, allgn[1]):
            if type(num) == int:
                if l != "-":
                    mapped[num] = l

        correction = ["N" for l in ref]
        for ind, (num, nump, l, lp) in enumerate(zip(alb[:-1], alb[1:], allgn[1][:-1], allgn[1][1:])):

            if num != "-" and nump == "-" and lp != "-":
                correction[num] = lp

        return "".join(mapped), "".join(correction)

    def show_segmentation_bc(self):
        self.allign_basecall_raw()
        # l = len(self.to_match)

        # pylab.plot(self.raw[:l + self.imin])
        pylab.plot(self.raw)

        pylab.plot(*self.segmentation_to_plot(self.signal_bc, shift=self.imin))

    def segmentation_to_plot(self, sign, shift=None, sl=6024, nanoraw=False):
        X = []
        Y = []
        s0 = 0
        if shift is not None:
            s0 = sign["start"][0]
        else:
            shift = 0
        # print("shift", shift)
        f2 = "mean"
        if nanoraw:
            f2 = "norm_mean"
        for i, (s, l, m) in enumerate(zip(sign["start"], sign["length"], sign[f2])):
            X += [(s - s0) * sl + shift, (s - s0 + l) * sl + shift]
            Y += [m, m]

        return np.array(X), np.array(Y)

    def plot_sequence(self, sign, window=[None, None], color="k", up=5, sl=None, nanoraw=False, shift=0, empty=True):
        if sl is None:
            sl = self.sampling_rate

        f2 = "mean"
        f3 = "seq"
        if nanoraw:
            f2 = "norm_mean"
            f3 = "base"
        seq = ""
        for i, (s, l, m, base) in enumerate(zip(sign["start"], sign["length"], sign[f2], sign[f3])):

            if (window[0] is None or (window[0] is not None and (s + shift) * sl  > window[0])) and \
                    (window[1] is None or (window[1] is not None and (s + shift) * sl < window[1])):

                if not empty:
                    if base == "N" or base == "NN":
                        continue
                    base = base.replace("N", "")
                pylab.text((s + l / 2 + shift) * sl - 1.5, m + up, base,
                           color=color)  # 1.5 size of character
                seq += base
        return seq

    def segmentation(self, chem="rf", w=5, prefix="", method="FW", minlen=2, maxlen=70, gamma=70, allinfos=False, flatten=False, totallen=None):
        h5 = h5py.File(prefix + self.filename, "r")
        if method == "FW":
            self.segments = extract_events(h5, chem="rf", window_size=w, old=False)
        elif method == "TV":
            raw, sl = get_raw(h5)
            # self.segments = tv_segment(raw, gamma=130, maxlen=45, minlen=2, sl=sl)
            self.segments = tv_segment(raw, gamma=gamma, maxlen=maxlen,
                                       minlen=minlen, sl=sl, allinfos=allinfos, flatten=flatten)
            self.sl = sl
            # print(self.segments.columns)
        elif method == "TVb":
            raw, sl = get_raw(h5)
            # self.segments = tv_segment(raw, gamma=130, maxlen=45, minlen=2, sl=sl)
            self.segments = tv_segment(raw, gamma=gamma, maxlen=100,
                                       minlen=1, sl=sl, allinfos=allinfos)
        elif method == "TV45":
            raw, sl = get_raw(h5)
            # self.segments = tv_segment(raw, gamma=130, maxlen=45, minlen=2, sl=sl)
            self.segments = tv_segment(raw, gamma=45, maxlen=70, minlen=2, sl=sl, allinfos=allinfos)
        elif method == "TV25":
            raw, sl = get_raw(h5)
            # self.segments = tv_segment(raw, gamma=130, maxlen=45, minlen=2, sl=sl)
            self.segments = tv_segment(raw, gamma=25, maxlen=70, minlen=2, sl=sl, allinfos=allinfos)
        elif method == "TV5":
            raw, sl = get_raw(h5)
            # self.segments = tv_segment(raw, gamma=130, maxlen=45, minlen=2, sl=sl)
            self.segments = tv_segment(raw, gamma=5, maxlen=30, minlen=2, sl=sl, allinfos=allinfos)

        return self.segments

    def analyse_segmentation(self, ntwk, signal, no2=False, already_pre=None, cut=None, overlap=None, thres=0.5):

        if already_pre is None:
            if overlap is None or overlap == 1:
                if cut is None:
                    pre = ntwk.predict(signal[np.newaxis, ::, ::])
                else:
                    print("Signal", signal.shape)
                    if len(signal) > cut:
                        lc = cut * (len(signal) // cut)
                        signal = signal[:lc]
                        # print(X.shape)
                        signal = np.array(signal).reshape(-1, cut, signal.shape[-1])
                    else:
                        signal = np.array(signal)[np.newaxis, ::, ::]
                    print("Signal", signal.shape)
                    pre = ntwk.predict(signal)

            else:
                cut = int(overlap * (cut // overlap))
                lw = cut // overlap
                lc = cut * (len(signal) // cut)

                signal = signal[:lc]
                An = []
                for i in range(overlap - 1):
                    print(lc, cut, lw, i * lw, -cut + (i + 1) * lw)
                    An.append(signal[i * lw:-cut + (i + 1) * lw])

                An.append(signal[(overlap - 1) * lw:])
                Signal = np.array(An)

                pre = ntwk.predict(Signal)
        else:
            pre = already_pre

        if no2:

            om1, om2, *other = pre
            om1 = np.argmax(om1[0], axis=-1)
            om2 = np.argmax(om2[0], axis=-1)

            outputs = [om1, om2]
            # return np.concatenate((output1, output2, signal), axis=-1)

        else:
            if cut is None:
                om1, *other = pre
                om1 = om1.reshape(-1, om1.shape[-1])[np.newaxis, ::, ::]
                # print(om1)
                om1 = np.argmax(om1, axis=-1)
                om1 = om1[0]
            else:
                if overlap is None or overlap == 1:
                    om1 = pre
                    other = []
                    signal = signal.reshape(-1, signal.shape[-1])
                    om1 = om1.reshape(-1, om1.shape[-1])
                    # print(om1)
                    ptb = om1[::, -2] / (om1[::, -3] + om1[::, -2])

                    om1 = np.argmax(om1, axis=-1)

                    toub = (om1 == 3) | (om1 == 4)
                    #ptb = ptb[:len(toub)]
                    om1[toub & (ptb > thres)] = 4
                    om1[toub & (ptb < thres)] = 3

                    #om1 = om1[0]
                else:
                    other = []
                    o1 = pre
                    res = np.ones((lc, o1.shape[-1]))
                    for i in range(overlap - 1):
                        # print(i * lw, -cut + (i + 1) * lw)
                        res[i * lw:-cut + (i + 1) * lw] *= o1[i]
                    res[(overlap - 1) * lw:] *= o1[i]
                    ptb = res[::, -2] / (res[::, -3] + res[::, -2])
                    for i in range(overlap):
                        om1 = np.argmax(pre[i], axis=-1)
                        # print(om1)
                        toub = (om1 == 3) | (om1 == 4)
                        print("vaules", np.sum(om1 == 4), np.sum(om1 == 4) / np.sum(toub))
                    om1 = np.argmax(pre[0], axis=-1)
                    toub = (om1 == 3) | (om1 == 4)
                    ptb = ptb[:len(toub)]
                    om1[toub & (ptb > thres)] = 4
                    om1[toub & (ptb < thres)] = 3
                    signal = signal[:len(om1)]
                    # om1 = res

            # print(om1)

            outputs = [om1]

        if other == []:

            n = outputs[0].shape[-1]
            n = 6

        else:

            if len(other) == 1:
                tmp_outputs = []
                for b in outputs:

                    TouB = b == 3
                    empty = b == pre[0][0].shape[-1] - 1
                    IsB = other[0][0][::, 0] > 0.5
                    b[TouB & IsB] = 4
                    b[empty] = 5
                    n = 6
                    tmp_outputs.append(copy.deepcopy(b))
                outputs = tmp_outputs

            elif len(other) == 3:
                print("Warning, not implemented")
                # pre = pre[0][0]
                b = np.argmax(pre[0][0], axis=-1)
                TouB = np.argmax(pre[0][0], axis=-1) == 3
                empty = np.argmax(pre[0][0], axis=-1) == pre[0][0].shape[-1] - 1

                Base = np.concatenate([np.zeros_like(pre[1][0][::, ]) + 0.500001,
                                       pre[1][0][::, ], pre[2][0][::, ], pre[3][0][::, ]], axis=-1)

                KBase = np.argmax(Base, axis=1) + 3

                b[TouB] = KBase[TouB]

                b[empty] = 7
                n = 8

        if n == 4 + 1:
            alph = "ACGTN"
        if n == 5 + 1:
            alph = "ACGTBN"
        if n == 7 + 1:
            alph = "ACGTBEIN"
        if n == 8 + 1:
            alph = "ACGTBLEIN"

        outputs = [np.array(list(map(lambda x: str(alph)[x], o)))
                   [::, np.newaxis] for o in outputs]

        # print(outputs)
        if len(outputs) == 2:

            # print(outputs[0].shape, outputs[1].shape, signal.shape)

            return np.concatenate((outputs[0], outputs[1], signal), axis=-1)
        else:
            return np.concatenate((outputs[0], signal), axis=-1)

    def transfer(self, root_signal, signal_to_label, center_of_mass=False, seqt="seq", allinfos=False):
        # Compute center:

        r_center = root_signal["start"] + root_signal["length"] / 2
        stl_center = signal_to_label["start"] + signal_to_label["length"] / 2

        stl_base = []

        if center_of_mass:

            for c in stl_center:
                where = np.argmin(np.abs(r_center - c))
                stl_base.append(root_signal[seqt][where])

        else:
            # Force assignation of bases
            stl_base = ["NN" for i in range(len(signal_to_label))]
            for ib, b in enumerate(root_signal[seqt]):
                if b != "NN":

                    s = (r_center[ib] > signal_to_label["start"]) &  \
                        (r_center[ib] < (signal_to_label["start"] + signal_to_label["length"]))

                    # where = np.argmin( np.abs(stl_center-r_center[ib]))
                    where = np.argmax(s)
                    if stl_base[where] == "NN":
                        stl_base[where] == b
                        # print("one")
                        # print(stl_base[where], b)
                    stl_base[where] += b
                    stl_base[where] = stl_base[where].replace("N", "")
                    # First try to transfer at previouss:
                    # print(stl_base[where - 1], stl_base[where], stl_base[where + 1])
                    if len(stl_base[where]) > 2 and where > 0:
                        if "NN" in stl_base[where - 1]:

                            #
                            stl_base[where - 1] = stl_base[where][:2]
                            stl_base[where] = stl_base[where][2:]
                        elif "N" in stl_base[where - 1]:
                            stl_base[where - 1] += stl_base[where][:1]
                            stl_base[where - 1] = stl_base[where - 1].replace("N", "")
                            # print(stl_base[where - 1])
                            stl_base[where] = stl_base[where][1:]

                    elif len(stl_base[where]) == 2 and where > 0:
                        if "NN" in stl_base[where - 1]:

                            #
                            stl_base[where - 1] = stl_base[where][:1] + "N"
                            stl_base[where] = stl_base[where][1:] + "N"
                            # print(stl_base[where])"""

                    if len(stl_base[where]) > 2 and where < len(stl_base):

                        stl_base[where + 1] = stl_base[where][2:] + \
                            "N" * (2 - len(stl_base[where][2:]))

                        stl_base[where] = stl_base[where][:2]

                    if len(stl_base[where]) > 2:
                        print("Loss", stl_base[where])
                    stl_base[where] = stl_base[where][:2]
                    stl_base[where] = stl_base[where] + \
                        "N" * (2 - len(stl_base[where]))
                    # print(stl_base[where - 1], stl_base[where], stl_base[where + 1])

                    # print("After", stl_base[where])

        new_signal = []
        if not allinfos:
            for s, m, std, l, start in zip(stl_base, signal_to_label["mean"], signal_to_label["stdv"],
                                           signal_to_label["length"], signal_to_label["start"]):
                new_signal.append([s, m, std, l, start])

            names = [seqt, "mean", "stdv", "length", "start"]
            return pd.DataFrame({n: v for n, v in zip(
                names, np.array(new_signal).T)}).convert_objects(convert_numeric=True)
        else:
            Alls = []
            for s, m, std, l, start, alls in zip(stl_base, signal_to_label["mean"], signal_to_label["stdv"],
                                                 signal_to_label["length"], signal_to_label["start"], signal_to_label["all"]):
                new_signal.append([s, m, std, l, start])
                Alls.append(alls)

            names = [seqt, "mean", "stdv", "length", "start"]
            df = pd.DataFrame({n: v for n, v in zip(
                names, np.array(new_signal).T)}).convert_objects(convert_numeric=True)
            df["all"] = Alls
            return df

"""
ref = "../../data/processed/results/ctc_20170908-R9.5/BTF_AG_ONT_1_FAH14273_A-select_pass_test_T.sam"
new = "../../data/processed/results/v9p5-new_ctc_20170908-R9.5/BTF_AG_ONT_1_FAH14273_A-select_pass_test_T.sam"
root = "../../data/raw/20170908-R9.5/"
D = Dataset(samfile = root + "BTF_AG_ONT_1_FAH14273_A-select.sam",
            root_files=root+"AG-basecalled/")
D.populate(maxf=10,filter_not_alligned=True,filter_ch =range(1,11) )
s = D.strands[0]"""
