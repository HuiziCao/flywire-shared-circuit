#!/usr/bin/env python3
"""
verify.py - Independent verifier for the FlyWire shared-circuit solution.

Streams the RAW edge-list CSVs (never trusting any precomputed state) and checks
that the neuron correspondence in network.csv defines *mutually isomorphic,
weakly-connected, self-loop-free* directed induced subgraphs across the three
chosen datasets.

Usage:
    python verify.py [network.csv] [data_dir]

Defaults: network.csv in the current directory, raw edge lists in ./data/

Checks performed
----------------
1. Each column contains N distinct integer neuron IDs.
2. No selected neuron carries a self-loop in any dataset.
3. The induced directed edge set (expressed in row indices = the bijection) is
   IDENTICAL across all three datasets  ->  mutually isomorphic.
4. The shared structure is weakly connected (single component).

Exit code 0 iff every check passes.
"""
import sys, csv
from collections import defaultdict

# Map (case-insensitive) dataset name -> raw edge-list filename.
FILES = {
    "banc": "banc_626_edge_list.csv",
    "fafb": "fafb_783_edge_list.csv",
    "manc": "manc_1.2.1_edge_list.csv",
    "maol": "maol_1.1_edge_list.csv",
    "mcns": "mcns_0.9_edge_list.csv",
}


def resolve(name):
    key = name.strip().lower()
    if key in FILES:
        return FILES[key]
    for k, v in FILES.items():          # tolerate extra suffixes in the header
        if key.startswith(k):
            return v
    raise SystemExit(f"Unknown dataset name in header: {name!r}")


def main():
    sol_path = sys.argv[1] if len(sys.argv) > 1 else "network.csv"
    data_dir = sys.argv[2] if len(sys.argv) > 2 else "data"

    # ---- read the solution table -------------------------------------------
    with open(sol_path, newline="") as f:
        rows = list(csv.reader(f))
    header = [h.strip() for h in rows[0]]
    if len(header) != 3:
        raise SystemExit(f"Expected 3 columns, found {len(header)}: {header}")
    body = [r for r in rows[1:] if any(c.strip() for c in r)]
    N = len(body)
    print(f"solution: columns={header}  N={N}")

    # per-column integer id lists (row i = the i-th element of the bijection)
    cols = {}
    for j, name in enumerate(header):
        try:
            ids = [int(r[j]) for r in body]
        except ValueError as e:
            raise SystemExit(f"Non-integer id in column {name}: {e}")
        if len(set(ids)) != N:
            raise SystemExit(f"Column {name}: ids are not distinct "
                             f"({N - len(set(ids))} duplicates)")
        cols[name] = ids
    print("  per-column ids integer & distinct: OK")

    # ---- per dataset: stream raw edges, build induced edge set --------------
    induced = {}
    for name in header:
        path = f"{data_dir}/{resolve(name)}"
        node_row = {nid: i for i, nid in enumerate(cols[name])}
        sel = set(node_row)
        edges = set()
        selfloops = 0
        with open(path, newline="") as f:
            rd = csv.reader(f)
            next(rd, None)              # skip header
            for rec in rd:
                if len(rec) < 2:
                    continue
                try:
                    s = int(rec[0]); t = int(rec[1])
                except ValueError:
                    continue
                if s in sel and t in sel:
                    if s == t:
                        selfloops += 1
                    else:
                        edges.add((node_row[s], node_row[t]))
        induced[name] = edges
        print(f"  induced edges [{name}] = {len(edges)}   "
              f"self-loops among selected = {selfloops}")
        if selfloops:
            raise SystemExit(f"FAIL: {selfloops} self-loop(s) among selected "
                             f"neurons in {name}")

    # ---- isomorphism: identical edge sets under the row correspondence ------
    ref = induced[header[0]]
    iso = all(induced[name] == ref for name in header[1:])
    print(f"ISOMORPHIC across all 3 datasets: {'OK' if iso else 'FAIL'}")
    if not iso:
        for name in header[1:]:
            d = induced[name] ^ ref
            if d:
                print(f"  {name} differs from {header[0]} by {len(d)} edges")
        raise SystemExit("FAIL: induced subgraphs are not isomorphic")

    # ---- weak connectivity --------------------------------------------------
    parent = list(range(N))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a, b in ref:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb
    comps = len({find(i) for i in range(N)})
    print(f"WEAKLY CONNECTED: {'OK' if comps == 1 else 'FAIL'} "
          f"({N - comps + 1 if comps == 1 else comps} / {N})"
          if comps == 1 else f"WEAKLY CONNECTED: FAIL ({comps} components)")
    if comps != 1:
        raise SystemExit(f"FAIL: structure has {comps} weakly-connected components")

    print(f"\nVERIFICATION PASSED: N={N}, induced edges per dataset={len(ref)}")


if __name__ == "__main__":
    main()
