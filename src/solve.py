#!/usr/bin/env python3
"""
solve.py - Reproduce the largest shared isomorphic weakly-connected directed
induced subgraph across the three sparsest+largest FlyWire connectomes
(BANC, MCNS, FAFB).

Pipeline
--------
  1. Load the three chosen edge lists -> out/in adjacency + self-loop sets.
  2. Pick a "hub-of-hubs" root triple (default: the seed that produced the
     shipped solution; can be re-searched with --search).
  3. PHASE 1  build a backbone: a degree-thresholded INDEPENDENT SET of the
              root's high-capacity neighbours, aligned degree-descending inside
              each cross-dataset-common connection "pattern" class.
  4. PHASE 2  leaf saturation: iterate to closure; each step groups outside
              nodes by their (row,direction) pattern to the current matched
              set, intersects pattern classes across all three datasets, tries
              several alignments (id / degree / random seeds), keeps the largest
              conflict-free (independent-set) batch.
  5. LNS      destroy-and-rebuild: repeatedly delete a random sub-tree and
              re-saturate, keeping only verified improvements, for a time budget.
  6. Write network.csv and self-verify.

The optimisation is heuristic and stochastic; the size reached varies with
seed, root region and time budget. The repository ships the best CERTIFIED
solution (network.csv, N=10848); this script reproduces structures of
comparable size. Run verify.py for an independent check.

Usage:
    python src/solve.py --data data --out network.csv --seconds 600
    python src/solve.py --search --seconds 900      # also re-search the root
"""
import argparse, csv, time, heapq, random, math
from collections import defaultdict

DATASETS = ["BANC", "MCNS", "FAFB"]
FILES = {"BANC": "banc_626_edge_list.csv",
         "MCNS": "mcns_0.9_edge_list.csv",
         "FAFB": "fafb_783_edge_list.csv"}

# Seed root triple that produced the shipped solution (row 0 of network.csv).
DEFAULT_ROOT = {"BANC": 720575941546634428,
                "MCNS": 10799,
                "FAFB": 720575940625525740}


# --------------------------------------------------------------------------- #
# data loading
# --------------------------------------------------------------------------- #
def load(data_dir):
    out = {d: defaultdict(list) for d in DATASETS}
    inn = {d: defaultdict(list) for d in DATASETS}
    selfloop = {d: set() for d in DATASETS}
    for d in DATASETS:
        with open(f"{data_dir}/{FILES[d]}", newline="") as f:
            rd = csv.reader(f); next(rd, None)
            for rec in rd:
                if len(rec) < 2:
                    continue
                try:
                    s = int(rec[0]); t = int(rec[1])
                except ValueError:
                    continue
                if s == t:
                    selfloop[d].add(s)
                    continue
                out[d][s].append(t)
                inn[d][t].append(s)
    # freeze to plain dicts of tuples for speed
    out = {d: {k: tuple(v) for k, v in out[d].items()} for d in DATASETS}
    inn = {d: {k: tuple(v) for k, v in inn[d].items()} for d in DATASETS}
    return out, inn, selfloop


# --------------------------------------------------------------------------- #
# core matching primitives
# --------------------------------------------------------------------------- #
class Solver:
    def __init__(self, out, inn, selfloop):
        self.out, self.inn, self.SL = out, inn, selfloop
        self.od = {d: {k: len(v) for k, v in out[d].items()} for d in DATASETS}
        self.idg = {d: {k: len(v) for k, v in inn[d].items()} for d in DATASETS}

    def OA(self, d, x):  return self.out[d].get(x, ())
    def IA(self, d, x):  return self.inn[d].get(x, ())
    def fdeg(self, d, x): return self.od[d].get(x, 0) + self.idg[d].get(x, 0)

    def patterns(self, M):
        """For each dataset, group outside (non-self-loop) nodes by the sorted
        tuple of (matched-row-index, direction) edges they share with M.
        Returns the per-dataset maps and the list of pattern keys common to
        all three datasets."""
        pat = {}
        for d in DATASETS:
            S = set(M[d]); SLd = self.SL[d]; tok = defaultdict(list)
            for i, n in enumerate(M[d]):
                for v in self.OA(d, n):
                    if v not in S and v not in SLd:
                        tok[v].append((i, 1))
                for v in self.IA(d, n):
                    if v not in S and v not in SLd:
                        tok[v].append((i, 0))
            pm = defaultdict(list)
            for node, ts in tok.items():
                pm[tuple(sorted(ts))].append(node)
            pat[d] = pm
        common = set(pat[DATASETS[0]])
        for d in DATASETS[1:]:
            common &= set(pat[d])
        return pat, sorted(common)

    def make_cand(self, pat, common, mode, seed=0):
        """Build candidate row-triples by aligning, within each common pattern
        class, the three datasets' node lists under `mode`
        (deg / id / random)."""
        rng = random.Random(seed); cand = []
        for p in common:
            lim = min(len(pat[d][p]) for d in DATASETS); lists = []
            for d in DATASETS:
                ns = list(pat[d][p])
                if mode == "deg":  ns.sort(key=lambda x: -self.fdeg(d, x))
                elif mode == "id": ns.sort()
                else:              rng.shuffle(ns)
                lists.append(ns[:lim])
            for k in range(lim):
                cand.append(tuple(lists[c][k] for c in range(3)))
        return cand

    def conflict(self, cand):
        """Conflict graph over candidate rows: two rows conflict if they share a
        node OR are adjacent in ANY dataset (would create an unmatched edge)."""
        nc = len(cand); adj = [set() for _ in range(nc)]
        def add(a, b):
            if a != b: adj[a].add(b); adj[b].add(a)
        for ci, d in enumerate(DATASETS):
            node_of = [c[ci] for c in cand]; rows_by = defaultdict(list)
            for ri, nd in enumerate(node_of):
                rows_by[nd].append(ri)
            for nd, rs in rows_by.items():
                if len(rs) > 1:
                    for a in range(len(rs)):
                        for b in range(a + 1, len(rs)):
                            add(rs[a], rs[b])
            cset = set(node_of)
            for ri, nd in enumerate(node_of):
                for v in self.OA(d, nd):
                    if v in cset:
                        for rb in rows_by[v]:
                            add(ri, rb)
        return adj

    @staticmethod
    def greedy_mis(adj):
        """Min-degree greedy maximal independent set."""
        nc = len(adj); deg = {i: len(adj[i]) for i in range(nc)}
        heap = [(deg[i], i) for i in range(nc)]; heapq.heapify(heap)
        alive = set(range(nc)); chosen = []
        while heap:
            dd, v = heapq.heappop(heap)
            if v not in alive or dd != deg[v]:
                continue
            chosen.append(v); rem = {v} | (adj[v] & alive)
            for u in rem:
                alive.discard(u)
            for u in rem:
                for w in adj[u]:
                    if w in alive:
                        deg[w] -= 1; heapq.heappush(heap, (deg[w], w))
        return chosen

    def saturate(self, M, tcap):
        seeds = [("id", 0), ("deg", 0)] + [("rand", s) for s in range(1, 6)]
        t0 = time.time()
        while time.time() - t0 < tcap:
            pat, common = self.patterns(M)
            if not common:
                break
            best = None
            for mode, sd in seeds:
                cand = self.make_cand(pat, common, mode, sd)
                if not cand:
                    continue
                ch = self.greedy_mis(self.conflict(cand))
                if best is None or len(ch) > len(best[1]):
                    best = (cand, ch)
            if not best or not best[1]:
                break
            for r in best[1]:
                c = best[0][r]
                for ci, d in enumerate(DATASETS):
                    M[d].append(c[ci])
        return M

    def build(self, root, thr, tcap):
        M = {d: [root[d]] for d in DATASETS}
        # PHASE 1 - high-degree independent backbone
        pat, common = self.patterns(M)
        cand = self.make_cand(pat, common, "deg")
        keep = [c for c in cand
                if min(self.fdeg(DATASETS[i], c[i]) for i in range(3)) >= thr]
        if keep:
            adj = self.conflict(keep)
            dm = [min(self.fdeg(DATASETS[i], keep[r][i]) for i in range(3))
                  for r in range(len(keep))]
            order = sorted(range(len(keep)), key=lambda r: -dm[r])
            alive = set(range(len(keep))); sub = []
            for r in order:
                if r in alive:
                    sub.append(r); alive.discard(r); alive -= adj[r]
            for r in sub:
                for ci, d in enumerate(DATASETS):
                    M[d].append(keep[r][ci])
        # PHASE 2 - leaf saturation
        return self.saturate(M, tcap)

    def induced_edges(self, M, d):
        S = set(M[d]); idx = {n: i for i, n in enumerate(M[d])}; E = set()
        for i, n in enumerate(M[d]):
            for v in self.OA(d, n):
                if v in S:
                    E.add((i, idx[v]))
        return E

    def verify(self, M):
        N = len(M[DATASETS[0]])
        for d in DATASETS:
            if len(set(M[d])) != N:
                return False, 0, N
            if any(x in self.SL[d] for x in M[d]):
                return False, 0, N
        Es = [self.induced_edges(M, d) for d in DATASETS]
        if not all(e == Es[0] for e in Es):
            return False, 0, N
        # weak connectivity: BFS from row 0 over the (undirected) induced edges
        from collections import deque
        adj = defaultdict(set)
        for a, b in Es[0]:
            adj[a].add(b); adj[b].add(a)
        seen = {0}; dq = deque([0])
        while dq:
            u = dq.popleft()
            for w in adj[u]:
                if w not in seen:
                    seen.add(w); dq.append(w)
        if len(seen) != N:
            return False, len(Es[0]), N
        return True, len(Es[0]), N

    # --------------------------------------------------------------------- #
    # large-neighbourhood search
    # --------------------------------------------------------------------- #
    def _undirected_adj(self, M):
        S = set(M["BANC"]); idx = {M["BANC"][i]: i for i in range(len(M["BANC"]))}
        adj = defaultdict(set)
        for i, n in enumerate(M["BANC"]):
            for v in self.OA("BANC", n):
                if v in S:
                    j = idx[v]; adj[i].add(j); adj[j].add(i)
        return adj

    def _parent_tree(self, M):
        """Reconstruct a spanning parent tree from the induced edges:
        parent[q] = smallest row index adjacent to q (in any dataset).
        Row 0 (the root) is the tree root. Removing a node together with all
        its descendants therefore leaves the remainder weakly connected."""
        N = len(M[DATASETS[0]]); nbr = defaultdict(set)
        for d in DATASETS:
            idxd = {n: i for i, n in enumerate(M[d])}; Sd = set(M[d])
            for i, n in enumerate(M[d]):
                for v in self.OA(d, n):
                    if v in Sd:
                        j = idxd[v]; nbr[i].add(j); nbr[j].add(i)
        parent = [-1] * N
        for q in range(1, N):
            pe = [p for p in nbr[q] if p < q]
            parent[q] = min(pe) if pe else 0
        return parent

    def lns(self, M, tcap, rng, log=False):
        from collections import deque
        t0 = time.time(); imp = 0
        while time.time() - t0 < tcap:
            N = len(M[DATASETS[0]])
            parent = self._parent_tree(M)
            children = defaultdict(list)
            for q in range(1, N):
                children[parent[q]].append(q)
            internal = [p for p in range(N) if children[p]]
            if not internal:
                break
            big = rng.random() < 0.5
            s = rng.choice(internal)
            # remove s together with its whole descendant sub-tree (pendant) ->
            # the rest of the structure stays weakly connected.
            rem = set(); dq = deque([s])
            while dq:
                u = dq.popleft(); rem.add(u)
                for c in children[u]:
                    dq.append(c)
            cap = 0.55 if big else 0.22
            if s == 0 or len(rem) > N * cap or len(rem) < 3:
                continue
            keep = [i for i in range(N) if i not in rem]
            M2 = {d: [M[d][i] for i in keep] for d in DATASETS}
            M2 = self.saturate(M2, 40 if big else 24)
            ok, e, N2 = self.verify(M2)          # verify() enforces connectivity
            if ok and N2 > N:
                M = M2; imp += 1
                if log:
                    print(f"    LNS improve -> N={N2}", flush=True)
        return M, imp

    # --------------------------------------------------------------------- #
    # optional root re-search (hub-of-hubs scoring)
    # --------------------------------------------------------------------- #
    def hub_of_hubs_top(self, d, k=8):
        sc = {}
        for v, arr in self.out[d].items():
            if v in self.SL[d]:
                continue
            c = sum(1 for u in arr if self.od[d].get(u, 0) >= 300)
            if c > 0:
                sc[v] = c
        return sorted(sc, key=lambda x: -sc[x])[:k]


# --------------------------------------------------------------------------- #
def read_csv(path):
    """Load an existing solution CSV into the M structure (keyed by dataset)."""
    with open(path, newline="") as f:
        rows = list(csv.reader(f))
    hdr = [h.strip() for h in rows[0]]
    pos = {d: hdr.index(d) for d in DATASETS}      # header must name the 3 sets
    M = {d: [] for d in DATASETS}
    for r in rows[1:]:
        if not any(c.strip() for c in r):
            continue
        for d in DATASETS:
            M[d].append(int(r[pos[d]]))
    return M


def write_csv(M, path):
    N = len(M[DATASETS[0]])
    with open(path, "w", newline="") as f:
        w = csv.writer(f); w.writerow(DATASETS)
        for i in range(N):
            w.writerow([M[d][i] for d in DATASETS])
    return N


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data")
    ap.add_argument("--out", default="network.csv")
    ap.add_argument("--seconds", type=float, default=600.0,
                    help="total LNS time budget")
    ap.add_argument("--thr", type=int, default=450,
                    help="phase-1 backbone min full-degree threshold")
    ap.add_argument("--search", action="store_true",
                    help="re-search the root over hub-of-hubs candidates")
    ap.add_argument("--warm", default=None,
                    help="load an existing solution CSV and continue LNS from it "
                         "(e.g. the shipped network.csv) instead of building fresh")
    ap.add_argument("--seed", type=int, default=12345)
    args = ap.parse_args()

    print("loading edge lists ...", flush=True)
    out, inn, sl = load(args.data)
    S = Solver(out, inn, sl)
    rng = random.Random(args.seed)

    if args.warm:
        M = read_csv(args.warm)
        ok, e, N = S.verify(M)
        print(f"warm-start from {args.warm}: N={N}  ({'OK' if ok else 'INVALID'})",
              flush=True)
        assert ok, "warm-start solution failed verification"
    elif args.search:
        tops = {d: S.hub_of_hubs_top(d, 8) for d in DATASETS}
        roots = [{d: tops[d][i % len(tops[d])] for d in DATASETS} for i in range(6)]
        roots = [DEFAULT_ROOT] + roots
        best = None
        for r in roots:
            M = S.build(r, args.thr, min(90, args.seconds * 0.3))
            ok, e, N = S.verify(M)
            if ok and (best is None or N > best[2]):
                best = (M, r, N)
            print(f"  build root {[r[d] for d in DATASETS]} -> N={N} ok={ok}",
                  flush=True)
        M = best[0]
        print(f"best build N={best[2]}", flush=True)
    else:
        M = S.build(DEFAULT_ROOT, args.thr, 90)
        ok, e, N = S.verify(M)
        print(f"build root {[DEFAULT_ROOT[d] for d in DATASETS]} -> "
              f"N={N} ok={ok}", flush=True)

    print(f"running LNS for ~{args.seconds:.0f}s ...", flush=True)
    # LNS in chunks so progress is reported
    spent = 0.0; chunk = max(30.0, args.seconds / 10)
    while spent < args.seconds:
        M, imp = S.lns(M, min(chunk, args.seconds - spent), rng)
        spent += chunk
        ok, e, N = S.verify(M)
        print(f"  [{spent:5.0f}s] N={N}  ({'OK' if ok else 'INVALID'})",
              flush=True)

    ok, e, N = S.verify(M)
    assert ok, "internal verification failed"
    N = write_csv(M, args.out)
    print(f"\nwrote {args.out}: N={N}, induced edges per dataset={e}")
    print("run  `python verify.py`  for an independent check.")


if __name__ == "__main__":
    main()
