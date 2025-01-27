import h5py
import argparse
import os
import numpy as np
from .model import build_models
from ..features.extract_events import extract_events, scale, scale_clean,scale_ratio,find2
from ..features.helpers import scale_clean_two
from .simple_utilities import transform_reads
from keras.models import Sequential
from keras.layers import Dense
from keras.layers import LSTM
from keras.layers.convolutional import Conv1D
from keras.layers.convolutional import MaxPooling1D


def get_events(h5, already_detected=True, chemistry="r9.5", window_size=None, old=True):
    if already_detected:
        try:
            e = h5["Analyses/Basecall_RNN_1D_000/BaseCalled_template/Events"]
            return e
        except:
            pass
        try:
            e = h5["Analyses/Basecall_1D_000/BaseCalled_template/Events"]
            return e
        except:
            pass
    else:
        return extract_events(h5, chemistry, window_size, old=old)


def basecall_one_file(filename, output_file,output_file2, ntwk,ntwk2, alph, already_detected,
                      n_input=1, filter_size=None, chemistry="r9.5",
                       window_size=None, clean=False, old=True, cut=None, thres=0.5,overlap=None):
    # try:
    assert(os.path.exists(filename)), "File %s does no exists" % filename
    h5 = h5py.File(filename, "r")
    events = get_events(h5, already_detected, chemistry, window_size, old=old)
    if events is None:
        print("No events in file %s" % filename)
        h5.close()
        return 0

    if len(events) < 400:
        print("Read %s too short, not basecalling" % filename)
        h5.close()
        return 0

    # print(len(events))

    #events = events[1:-1]
    """
    v = find2(events)
    first_event,last_event = v
    #print(first_event)
    events = events[first_event:last_event]
    """
    #print(len(events),"La")
    mean = events["mean"]
    std = events["stdv"]
    length = events["length"]
    if clean:

        X = scale_clean_two(
            np.array(np.vstack([mean, mean * mean, std, length]).T, dtype=np.float32))
    else:
        X = scale(np.array(np.vstack([mean, mean * mean, std, length]).T, dtype=np.float32))
    # return
    X2 = scale_ratio(mean.copy())
    X2 = np.array([X2]).T


    #print(np.mean(X[:, 0]))

    if cut is None:

        try:
            o1 = ntwk.predict(np.array(X)[np.newaxis, ::, ::])
            o1 = o1[0]

        except:
            o1, o2 = ntwk.predict(X)

        #print(len(o1))

        icut=200

        if overlap is None:
            lc = icut * (len(X2) // icut)


            X2 = X2[:lc]
            # print(X.shape)

            X2 = np.array(X2).reshape(-1, icut, X2.shape[-1])

            ntw2p = ntwk2.predict(X2)



            res = np.ones_like(X2) * ntw2p[::,np.newaxis]
            res = res.flatten()
        else:
            X2,_ = transform_reads([events],np.array([[0]]),lenv=icut,overlap=overlap)

            X2 = X2[0]
            #print(X2.shape)
            assert X2.shape[0] == overlap
            #print(X2.shape,)
            r = ntwk2.predict(X2.reshape(-1,icut,X2.shape[-1]))
            #print(len(r))
            #print(r,X2,len(events))
            r= r.reshape(overlap,-1,1)
            #print(r.shape)
            #print(r.shape)
            res = np.median(r,axis=0)
            #print(res.shape)
            res0 = np.ones((res.shape[0],icut,1)) * res[::,np.newaxis,::]
            #print("Res0",icut,res0.shape,(res.shape[0],icut,1))
            res0 = res0.flatten()
            #print("Res0",res0.shape)

            res = res0
            #print(len(res),len(o1))
            #print(res)

            lc = len(res)


        o1 = o1[:lc]

        # print(o1[:20])

        om = np.argmax(o1, axis=-1)
        print("T", np.sum(om == 3), "B", np.sum(om == 4), "B/T+B",
              (np.sum(om == 4) / (np.sum(om == 3) + np.sum(om == 4))))
        # print(o2[:20])
        # exit()
        print(res.shape,np.array(om!=5).shape)
        res2 = res[om!=5]


        output = "".join(map(lambda x: alph[x], om)).replace("N", "")
        assert len(output) == len(res2)

        print(om.shape, len(output), len(output) / om.shape[0])

        output_file.writelines(">%s_template_deepnano\n" % filename)
        output_file.writelines(output + "\n")

        output_file2.writelines(">%s_template_deepnano\n" % filename)
        output_file2.writelines(" ".join(["%.2f" % ires2 for ires2 in res2 ])+"\n")

        h5.close()
        #return len(events)
        # except Exception as e:
        #print("Read %s failed with %s" % (filename, e))
        return 0


    else:
        if len(X) > cut:
            lc = cut * (len(X) // cut)
            X = X[:lc]
            # print(X.shape)
            X = np.array(X).reshape(-1, cut, X.shape[-1])
        else:
            X = np.array(X)[np.newaxis, ::, ::]
        # print(X.shape)
        o1 = ntwk.predict(X)

        o1 = o1.reshape(-1, o1.shape[-1])

        ptb = o1[::, -2] / (o1[::, -3] + o1[::, -2])

        om1 = np.argmax(o1, axis=-1)

        toub = (om1 == 3) | (om1 == 4)
        #ptb = ptb[:len(toub)]
        om1[toub & (ptb > thres)] = 4
        om1[toub & (ptb < thres)] = 3

        om = om1

    # print(o1[:20])
    # print(o2[:20])
    # exit()

    output = "".join(map(lambda x: str(alph + "T")[x], om)).replace("N", "")

    print(om.shape, len(output), len(output) /
          om.shape[0], output.count("B") / (1 + output.count("T")
                                            ), output.count("L") / (1 + output.count("T")),
          output.count("E") / (1 + output.count("T")), output.count("I") / (1 + output.count("T")))
    print(output.count("T"), output.count("B"), output.count(
        "L"), output.count("E"), output.count("I"), output.count("U"))

    if filter_size is not None and len(output) < filter_size:
        print("Out too small", filter_size)
        return 0
    output_file.writelines(">%s_template_deepnano\n" % filename)
    output_file.writelines(output + "\n")

    h5.close()
    return len(events)
    # except Exception as e:
    print("Read %s failed with %s" % (filename, e))
    return 0

def load_model2(weight):
    model = Sequential()
    # model.add(Embedding(top_words, embedding_vecor_length, input_length=max_review_length))
    model.add(Conv1D(filters=32, kernel_size=3, padding='same',
                     activation='relu', input_shape=(200, 1)))
    model.add(MaxPooling1D(pool_size=2))
    # model.add(Conv1D(filters=32, kernel_size=5, padding='same',
    #                 activation='relu'))
    # model.add(MaxPooling1D(pool_size=2))
    # model.add(Conv1D(filters=64, kernel_size=5, padding='same',
    #                 activation='relu'))
    # model.add(MaxPooling1D(pool_size=2))
    model.add(LSTM(100))
    model.add(Dense(1, activation='linear'))
    assert(os.path.exists(weight)), "Weights %s does not exist" % weight
    #model.compile(loss='mse', optimizer='adam')  # , metrics=['accuracy'])
    model.load_weights(weight)
    return model

def process(weights,weights1, Nbases, output, directory, reads=[], filter="",
            already_detected=True, Nmax=None, size=20, n_output_network=1, n_input=1, filter_size=None,
            chemistry="r9.5", window_size=None, clean=False, old=True, res=False,
             attention=False, cut=None, thres=0.5,overlap=None):
    assert len(reads) != 0 or len(directory) != 0, "Nothing to basecall"

    alph = "ACGTN"
    if Nbases == 5:
        alph = "ACGTBN"
    if Nbases == 8:
        alph = "ACGTBLEIN"

    import sys
    sys.path.append("../training/")

    n_feat = 4
    if clean:
        n_feat = 3
    ntwk, _ = build_models(size, Nbases - 4, n_output=n_output_network, n_feat=n_feat,
                           res=res, attention=attention)
    assert(os.path.exists(weights)), "Weights %s does not exist" % weights
    ntwk.load_weights(weights)
    print("loaded")

    ntwk2 = load_model2(weights1)

    Files = []
    if filter != "" and filter is not None:
        assert(os.path.exists(filter)), "Filter %s does not exist" % filter
        with open(filter, "r") as f:
            for line in f.readlines():
                Files.append(line.split()[0])

    if len(reads) or len(directory) != 0:
        dire = os.path.split(output)[0]
        if dire != "":
            os.makedirs(dire, exist_ok=True)
        print("Writing on %s" % output)

        fo = open(output, "w")
        fo1 = open(output+"_ratio", "w")

        files = reads
        if reads == "":
            files = []
        if len(directory):
            files += [os.path.join(directory, x) for x in os.listdir(directory)]
            nfiles = []
            for f in files:
                if os.path.isdir(f):
                    nfiles += [os.path.join(f, x) for x in os.listdir(f)]
                else:
                    nfiles.append(f)
            files = nfiles

        # print(Files)
        # print(files)
        # exit()
        if Nmax != None:
            files = files[-Nmax:]
        for i, read in enumerate(files):

            if Files != []:
                if os.path.split(read)[1] not in Files:
                    continue
            print("Processing read %s" % read)
            basecall_one_file(read, fo,fo1, ntwk,ntwk2, alph, already_detected,
                              n_input=n_input, filter_size=filter_size,
                              chemistry=chemistry, window_size=window_size,
                              clean=clean, old=old, cut=cut, thres=thres,overlap=overlap)

        fo.close()


if __name__ == "__main__":

    parser = argparse.ArgumentParser()
    parser.add_argument("--weights", default="None")
    parser.add_argument("--weights1", default="None")

    parser.add_argument('--Nbases', type=int, choices=[4, 5, 8], default=4)
    parser.add_argument('--output', type=str, default="output.fasta")
    parser.add_argument('--directory', type=str, default='',
                        help="Directory where read files are stored")
    parser.add_argument('reads', type=str, nargs='*')
    parser.add_argument('--detect', dest='already_detected', action='store_false')

    parser.add_argument('--filter', type=str, default='')
    parser.add_argument('--filter-size', dest="filter_size", type=int, default=None)
    parser.add_argument('--chemistry', type=str, default='r9.5')
    parser.add_argument('--window-size', type=int, default=6, dest="window_size")
    parser.add_argument('--not-old',  dest="old", action="store_false")
    parser.add_argument('--res', dest="res", action="store_true")
    parser.add_argument('--overlap',type=int,default=None)

    parser.add_argument('--clean', dest="clean", action="store_true")

    parser.add_argument('--attention', dest="attention", action="store_true")
    parser.add_argument('--size', dest="size", type=int, default=20)
    parser.add_argument('--cut', dest="cut", type=int, default=None)
    parser.add_argument('--thres', dest="thres", type=float, default=0.5)
    parser.add_argument('--maxf', dest="Nmax", type=int, default=20)

    args = parser.parse_args()
    # exit()
    process(weights=args.weights,weights1=args.weights1, Nbases=args.Nbases, output=args.output,
            directory=args.directory, Nmax=args.Nmax,reads=args.reads, filter=args.filter,
            already_detected=args.already_detected, filter_size=args.filter_size, size=args.size,
            chemistry=args.chemistry, window_size=args.window_size,
            old=args.old, res=args.res, attention=args.attention,
            clean=args.clean, cut=args.cut, thres=args.thres,overlap=args.overlap)
