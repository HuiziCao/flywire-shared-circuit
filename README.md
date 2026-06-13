# Largest Shared Isomorphic Directed Induced Subgraph across FlyWire Connectomes

Result: a set of 10,848 neurons present in three of the five connectomes — BANC, MCNS, FAFB — whose induced directed subgraphs are mutually isomorphic (edge-for-edge identical under the row correspondence in network.csv), weakly connected, and free of self-loop neurons. Each induced subgraph has 10,935 directed edges. This is 3.4 times the size of the strongest baseline benchmarked here (a single-hub iterative-extension tree, N about 3,135). Running verify.py gives an independent, from-scratch check (see section 6).

## 1. Problem

Given five directed connectomes (edge lists of source,target, weights ignored), find the largest set of N neurons that appears in at least three datasets and whose induced directed subgraphs are mutually isomorphic under a single neuron-to-neuron correspondence: an edge between two matched neurons must be present, with the same direction, in all three datasets. The matched structure must be weakly connected, and matched neurons may not carry self-loops. The objective is to maximise N.

network.csv encodes the correspondence directly: column k is the chosen dataset, row i is the i-th element of the bijection, so cell (i, k) is the neuron in dataset k that plays role i in the shared circuit.

## 2. Approach

Two ideas did the heavy lifting.

### 2.1 Choose the three sparsest and largest connectomes

The task allows any three of the five datasets. The five differ sharply in edge density, measured here by reciprocity, the fraction of edges that are bidirectional:

| dataset | nodes | edges | reciprocity |
|--------|------:|------:|-----------:|
| BANC | 112,885 | 2.68 M | 0.143 |
| MCNS | 165,820 | 6.24 M | 0.157 |
| FAFB | 138,584 | 3.73 M | 0.166 |
| MAOL | 51,669 | 6.48 M | 0.282 |
| MANC | 23,641 | 5.31 M | 0.304 |

BANC, MCNS and FAFB are simultaneously the three sparsest and the three largest connectomes. Sparsity is exactly the property that lets many high-degree neurons remain mutually non-adjacent under the simultaneous three-way isomorphism constraint, which is what allows a large matched backbone, and hence a large matched circuit, to exist. Swapping the dense MAOL for the sparse BANC enlarged the achievable circuit about 2.5 times in these experiments (roughly 3.8k to 9.6k before any local search).

### 2.2 Sparse, tree-like structures were the highest-yield class

Sparse and nearly-tree structures gave by far the largest matched circuits, for two reasons. Sparser disconnects: a connected graph on a fixed node set needs at least N minus 1 edges (a tree), so going below that violates weak connectivity. Denser is harder to match: every extra edge must be reproduced, with correct direction, in all three graphs at once, and the chance of a three-way edge match falls steeply with density. This is a strong practical strategy, not a proof of global optimality. The solution is tree-like but not a strict tree: 10,848 nodes and 10,935 directed edges, that is, a spanning tree plus a small number of extra edges (about 1.008 edges per node). Concretely it is a deep feed-forward broadcast structure: a high-degree hub-of-hubs core near the root that fans out, plus long, sparsely-branching relay chains reaching up to 35 hops from the root (see figures/network_graph.png).

## 3. Algorithm

The solver (src/solve.py) constructs and then locally optimises this tree.

**Root.** A hub-of-hubs root triple is selected by scoring each neuron by how many of its out-neighbours are themselves high-degree (out-degree at least 300). Self-loop neurons are excluded from every candidate set.

**Phase 1, backbone.** From the root, candidate neurons are grouped by their connection pattern to the current matched set: the sorted tuple of matched-row-index and direction over all edges to and from already-selected neurons. Pattern classes common to all three datasets are kept; within each class the three datasets' neurons are aligned in descending degree order. A degree-thresholded greedy independent set (two candidates conflict if they share a neuron or are adjacent in any dataset) then gives a backbone of mutually non-adjacent high-capacity sub-hubs.

**Phase 2, leaf saturation.** This iterates to closure. Each round recomputes the common pattern classes, tries several alignments within them (sorted by id, sorted by degree, and several random seeds), takes a greedy minimum-degree independent set for each, and keeps the largest conflict-free batch. Every neuron added is adjacent to the current set, so the structure stays connected by construction.

**Degree-aware alignment.** Neurons are paired across datasets by degree. Degree is the most abundant, cross-graph-comparable feature; finer structural signatures fail (see section 4).

**Large-neighbourhood search.** A destroy-and-rebuild local search. Each step reconstructs a spanning parent-tree of the current circuit, deletes a randomly chosen node together with its entire descendant sub-tree (a pendant sub-tree, so the remainder stays weakly connected), re-saturates with Phase 2, and keeps the result only if it is verified valid and strictly larger. A mix of small and large destroys is used; larger destroys escape local optima that small moves cannot. The search climbed monotonically from about 9.6k to 10,848, each accepted state re-verified for isomorphism and weak connectivity.

## 4. What was tried and rejected

These negative results are evidence that the tree-like structure near 10.8k is close to the practical ceiling reached here, rather than an arbitrary stopping point. They bound the search that was run; they are not proofs that larger, non-tree, or multi-module solutions are impossible.

**Structure-signature alignment (Weisfeiler-Leman style).** Pairing neurons by local structural fingerprint (own in-degree and out-degree plus neighbour-degree profile) instead of by degree, in the hope that paired sub-trees stay isomorphic deeper, collapsed: a pure-signature build reached only about N=355, because exact cross-connectome structural matches are vanishingly rare across three different specimens and reconstructions. Degree alignment is near-optimal precisely because degree is coarse and abundant.

**Stitching two regions with a co-designed bridge edge.** An attempt to roughly double N by growing two trees and joining them is closed off by two findings. Across distinct regions, between the 10.8k circuit and an independently grown second circuit there were zero matched bridge edges among about 146 million candidate row-pairs; a density estimate explains it, since a random row-pair is a simultaneous edge in all three graphs with probability about (2e-4) cubed, roughly 9e-12, so even 1e8 pairs give an expected count near 0.001. Within one region, a co-designed bridge merely re-partitions the same neurons into two mutually non-adjacent trees and loses total size. Together these indicate that multi-module stitching was unproductive in this bounded search and that the single connected tree-like structure was the most effective class found here, not that non-tree or multi-module solutions are impossible in principle.

**Multi-region search.** Alternative hub-of-hubs regions build to only about 9.0 to 9.3k versus this region's 9.6k, that is, lower ceilings; none beat 10,848.

**Per-batch integer programming, multi-level backbones, finer per-batch optimisation.** All hurt: greedily maximising the immediate batch starves future growth, whereas greedy minimum-degree independent-set selection implicitly preserves future options.

## 5. Assumptions

Edge weights are ignored and edge direction is preserved, per the task. Input edge lists are treated as already de-duplicated (verified true for all five files). Isomorphic is taken in the strict sense required: the induced directed edge set is identical under the row correspondence across all three datasets. Neuron IDs are opaque integers, and the cross-dataset correspondence is structural (graph-isomorphic) only; there is no claim that matched BANC, MCNS and FAFB neurons are the same biological cell type. Biological annotation, in science.md, is performed for the FAFB neurons only, where public cell-type metadata exist.

## 6. Reproduction

The repository root contains README.md, science.md and network.csv (the solution: three columns BANC,MCNS,FAFB and 10,848 rows), together with verify.py (the independent verifier), src/solve.py (the solver), a figures/ folder (network graph and 3-D meshes), and structure_summary.json.

Place the five raw edge-list CSVs in a data/ folder: banc_626_edge_list.csv, fafb_783_edge_list.csv, mcns_0.9_edge_list.csv, manc_1.2.1_edge_list.csv, maol_1.1_edge_list.csv. These are the public connectome edge lists distributed via FlyWire and Codex (codex.flywire.ai) and the associated connectome releases (FAFB v783, MANC, MAOL, MCNS, BANC); they total about 0.5 GB, are git-ignored, and are not committed to this repository.

To verify the shipped solution, which is instant and fully independent because it re-reads the raw edge lists and re-checks isomorphism, weak connectivity, self-loops and distinctness, run python verify.py network.csv data. It prints VERIFICATION PASSED: N=10848, induced edges per dataset=10935.

To reproduce the method from scratch, run python src/solve.py --data data --out my_solution.csv --seconds 600 and then python verify.py my_solution.csv data. The optimisation is heuristic and stochastic, so the size reached depends on the time budget and random seed: the shipped network.csv (10,848) is the product of an extended search, a short run reproduces smaller but valid circuits, and a long run approaches it. To continue optimising the shipped solution directly, run python src/solve.py --data data --warm network.csv --out improved.csv --seconds 1800.

## 7. Limitations

This is a greedy and large-neighbourhood-search heuristic, not a certified global maximum-common-isomorphic-subgraph solver, a problem that is NP-hard; no optimality guarantee is made, only the evidence in section 4 that 10.8k is near the practical ceiling for this triple and structure class. The achieved size is region- and seed-dependent, and the best certified solution is the one shipped. The cross-dataset correspondence is structural only (see section 5).
