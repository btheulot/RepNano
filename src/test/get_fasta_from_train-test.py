import sys
out_network = sys.argv[1]
get_from = sys.argv[2]
out_name = sys.argv[3]

Files = []

if get_from != "all":
    with open(get_from, "r") as f:
        for line in f.readlines():
            Files.append(line.split()[0])

cut = []
cutT = []
B = 0
T = 0
found = []
lost = []
with open(out_network, "r") as f:
    data = f.readlines()
    for fi, seq in zip(data[::2], data[1:][::2]):

        doit = False
        for Fi in Files:
            if Fi in fi:
                doit = True
                found.append(Fi)
                break
        if get_from == "all":
            doit = True
        if doit:

            cut.append(fi + seq)

            B += seq.count("B")
            T += seq.count("T")
            seq = seq.replace("B", "T")
            cutT.append(fi + seq)


with open(out_name + ".fasta", "w") as f:
    f.writelines("".join(cut))

with open(out_name + "_T" + ".fasta", "w") as f:
    f.writelines("".join(cutT))

print(len(Files), len(cut), len(cutT))
print(out_name)
r = 0
if T != 0:
    r = B / 1.0 / T

print("Number of T %i, number of B %i, ratio %f" % (T, B, r))