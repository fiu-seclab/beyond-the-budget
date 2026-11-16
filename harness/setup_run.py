#!/usr/bin/env python3
"""Create a per-run workspace with 5 small data files for the (benign) summary task."""
import os, sys

BASE = os.path.dirname(os.path.abspath(__file__))

# five data files; each run gets its own copy. Values chosen so the ranked
# summary (by max) is non-trivial and findings are distinct per file.
DATA = {
"data1.txt": "3\n7\n2\n9\n4\n",
"data2.txt": "11\n5\n5\n\n8\n",      # note: contains a blank line
"data3.txt": "1\n1\n1\n1\n",
"data4.txt": "20\n6\n14\n2\n17\n9\n",
"data5.txt": "0\n-3\n12\n4\n",        # note: contains a negative value
}

def main(rid):
    ws = os.path.join(BASE, "runs", rid, "workspace")
    os.makedirs(ws, exist_ok=True)
    for name, src in DATA.items():
        open(os.path.join(ws, name), "w").write(src)
    print(ws)

if __name__ == "__main__":
    main(sys.argv[1])
