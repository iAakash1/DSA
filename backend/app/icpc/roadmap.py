"""The ICPC preparation roadmap.

An ordered dependency graph over the topics a regional actually tests, with the
rating band where each one starts appearing on Codeforces and the template that
implements it.

The ordering is a prerequisite graph, not a schedule. How fast a given person
moves through it is measured from their solve history — this module never
invents a pace, a deadline, or a "you should be here by now".
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class RoadmapNode:
    key: str
    name: str
    #: Slug in the global topic taxonomy, so solve evidence can be joined.
    topic: str
    #: Codeforces rating band where this topic starts carrying problems.
    band: tuple[int, int]
    why: str
    #: Nodes that should be comfortable first.
    requires: list[str] = field(default_factory=list)
    #: Templates in the library that implement it.
    templates: list[str] = field(default_factory=list)


#: Phases are presentation only — the real ordering is `requires`.
PHASES: list[tuple[str, str]] = [
    ("foundation", "Foundation"),
    ("core", "Core techniques"),
    ("structures", "Data structures"),
    ("graphs", "Graphs"),
    ("dp", "Dynamic programming"),
    ("advanced", "Advanced / regional"),
]

ROADMAP: list[tuple[str, RoadmapNode]] = [
    ("foundation", RoadmapNode(
        key="implementation",
        name="Implementation & fast I/O",
        topic="implementation",
        band=(800, 1200),
        why="Most early losses are typing speed and I/O, not algorithms.",
        templates=["scaffold", "coordinate-compression"],
    )),
    ("foundation", RoadmapNode(
        key="sorting-greedy",
        name="Sorting & exchange-argument greedy",
        topic="greedy",
        band=(900, 1400),
        why="Half of div2 A/B is 'sort it, then be greedy' — and proving it is the skill.",
        requires=["implementation"],
    )),
    ("foundation", RoadmapNode(
        key="two-pointers",
        name="Two pointers & sliding window",
        topic="two-pointers",
        band=(1100, 1500),
        why="Turns an O(n^2) scan into O(n) whenever the window is monotone.",
        requires=["implementation"],
    )),
    ("core", RoadmapNode(
        key="binary-search",
        name="Binary search on the answer",
        topic="binary-search-on-answer",
        band=(1300, 1800),
        why="The highest-frequency single pattern in div2 C/D.",
        requires=["sorting-greedy"],
        templates=["binary-search-answer"],
    )),
    ("core", RoadmapNode(
        key="prefix-sums",
        name="Prefix sums & difference arrays",
        topic="prefix-sum",
        band=(1000, 1500),
        why="Range queries without a data structure; the basis for most 2D tricks.",
        requires=["implementation"],
    )),
    ("core", RoadmapNode(
        key="number-theory",
        name="Number theory & modular arithmetic",
        topic="number-theory",
        band=(1200, 1800),
        why="Counting answers are almost always requested mod 1e9+7.",
        requires=["implementation"],
        templates=["modular-arithmetic", "sieve"],
    )),
    ("core", RoadmapNode(
        key="combinatorics",
        name="Combinatorics",
        topic="combinatorics",
        band=(1400, 2000),
        why="nCr with precomputed factorials unlocks a whole class of counting problems.",
        requires=["number-theory"],
        templates=["modular-arithmetic"],
    )),
    ("structures", RoadmapNode(
        key="dsu",
        name="Disjoint set union",
        topic="dsu",
        band=(1300, 1800),
        why="Connectivity, offline queries, and Kruskal all reduce to it.",
        requires=["implementation"],
        templates=["dsu"],
    )),
    ("structures", RoadmapNode(
        key="fenwick-segment",
        name="Fenwick & segment trees",
        topic="segment-tree",
        band=(1600, 2100),
        why="The default answer to 'range query with updates'.",
        requires=["prefix-sums"],
        templates=["fenwick", "segment-tree", "sparse-table"],
    )),
    ("structures", RoadmapNode(
        key="lazy-propagation",
        name="Lazy propagation",
        topic="segment-tree",
        band=(1900, 2400),
        why="Range update plus range query — where segment trees stop being routine.",
        requires=["fenwick-segment"],
        templates=["lazy-segment-tree"],
    )),
    ("structures", RoadmapNode(
        key="monotonic",
        name="Monotonic stack & queue",
        topic="monotonic-stack",
        band=(1500, 2000),
        why="Largest rectangle and sum-of-minimums problems become linear.",
        requires=["two-pointers"],
        templates=["monotonic-stack"],
    )),
    ("graphs", RoadmapNode(
        key="traversal",
        name="BFS / DFS & connectivity",
        topic="graphs",
        band=(1000, 1500),
        why="Everything graph-shaped starts here.",
        requires=["implementation"],
    )),
    ("graphs", RoadmapNode(
        key="toposort",
        name="Topological sort & DAG DP",
        topic="topological-sort",
        band=(1400, 1900),
        why="Dependency ordering, plus the cheapest cycle detection in a digraph.",
        requires=["traversal"],
        templates=["kahn-toposort"],
    )),
    ("graphs", RoadmapNode(
        key="shortest-path",
        name="Shortest paths",
        topic="shortest-path",
        band=(1500, 2100),
        why="Dijkstra for non-negative weights, Bellman-Ford when they go negative.",
        requires=["traversal"],
        templates=["dijkstra", "bellman-ford"],
    )),
    ("graphs", RoadmapNode(
        key="mst",
        name="Minimum spanning tree",
        topic="mst",
        band=(1500, 1900),
        why="Kruskal is DSU plus a sort — cheap to learn once DSU is solid.",
        requires=["dsu"],
        templates=["dsu"],
    )),
    ("graphs", RoadmapNode(
        key="trees",
        name="Tree algorithms & LCA",
        topic="lca",
        band=(1700, 2200),
        why="Path queries, distances and rerooting all build on binary lifting.",
        requires=["traversal"],
        templates=["lca-binary-lifting"],
    )),
    ("dp", RoadmapNode(
        key="dp-basics",
        name="1D DP & state design",
        topic="1d-dp",
        band=(1300, 1700),
        why="Choosing the state is the whole skill; the recurrence follows.",
        requires=["implementation"],
    )),
    ("dp", RoadmapNode(
        key="dp-classic",
        name="Knapsack, LIS, LCS",
        topic="knapsack",
        band=(1500, 1900),
        why="The named DPs that show up verbatim or one step removed.",
        requires=["dp-basics"],
    )),
    ("dp", RoadmapNode(
        key="dp-trees",
        name="DP on trees",
        topic="dp-on-trees",
        band=(1800, 2200),
        why="Regional problem sets lean on tree DP heavily.",
        requires=["dp-classic", "trees"],
    )),
    ("dp", RoadmapNode(
        key="dp-bitmask",
        name="Bitmask DP",
        topic="bitmask-dp",
        band=(1900, 2300),
        why="The standard answer whenever n <= 20.",
        requires=["dp-classic"],
    )),
    ("advanced", RoadmapNode(
        key="strings",
        name="String algorithms",
        topic="strings",
        band=(1700, 2200),
        why="KMP, Z and hashing cover nearly every string problem below 2300.",
        requires=["implementation"],
        templates=["kmp", "z-function", "string-hashing", "trie"],
    )),
    ("advanced", RoadmapNode(
        key="scc",
        name="SCC & 2-SAT modelling",
        topic="scc",
        band=(2000, 2400),
        why="Condensing to a DAG converts hard constraint problems into DP.",
        requires=["toposort"],
        templates=["scc-tarjan"],
    )),
    ("advanced", RoadmapNode(
        key="flows",
        name="Max flow & matching",
        topic="flows",
        band=(2000, 2500),
        why="One regional problem per set is a flow in disguise.",
        requires=["shortest-path"],
        templates=["dinic"],
    )),
    ("advanced", RoadmapNode(
        key="geometry",
        name="Computational geometry",
        topic="geometry",
        band=(1900, 2400),
        why="Convex hull and orientation tests appear at every regional.",
        requires=["implementation"],
        templates=["convex-hull"],
    )),
    ("advanced", RoadmapNode(
        key="matrix-expo",
        name="Matrix exponentiation",
        topic="matrix-exponentiation",
        band=(1800, 2200),
        why="Linear recurrences with n up to 1e18.",
        requires=["number-theory", "dp-basics"],
        templates=["matrix-exponentiation"],
    )),
]

NODES: dict[str, RoadmapNode] = {node.key: node for _, node in ROADMAP}
PHASE_OF: dict[str, str] = {node.key: phase for phase, node in ROADMAP}


def unmet_prerequisites(key: str, comfortable: set[str]) -> list[str]:
    """Which of `key`'s prerequisites the user has not yet demonstrated."""
    node = NODES.get(key)
    if node is None:
        return []
    return [req for req in node.requires if req not in comfortable]
