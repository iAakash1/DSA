"""Topic and pattern taxonomy.

Topic  = the subject area            (Graphs)
Pattern= the recognizable shape      (Shortest Path)
Algorithm/technique = the tool       (Dijkstra, State Compression)

Keeping these on separate axes is what lets the weakness engine say
"you understand DP but you cannot design states" instead of "DP: 42%".
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.models.enums import TopicKind
from app.models.problem import Pattern, Topic

log = get_logger(__name__)

#: Nested topic tree. `kind` describes the node's role; depth is unlimited.
TOPIC_TREE: list[dict[str, Any]] = [
    {
        "slug": "basics",
        "name": "Basics",
        "children": [
            {"slug": "implementation", "name": "Implementation"},
            {"slug": "brute-force", "name": "Brute Force"},
            {"slug": "simulation", "name": "Simulation"},
            {"slug": "constructive", "name": "Constructive Algorithms"},
        ],
    },
    {
        "slug": "arrays",
        "name": "Arrays",
        "children": [
            {"slug": "prefix-sum", "name": "Prefix Sum", "kind": TopicKind.TECHNIQUE},
            {"slug": "difference-array", "name": "Difference Array", "kind": TopicKind.TECHNIQUE},
            {"slug": "sliding-window", "name": "Sliding Window", "kind": TopicKind.TECHNIQUE},
            {"slug": "two-pointers", "name": "Two Pointers", "kind": TopicKind.TECHNIQUE},
            {"slug": "kadane", "name": "Kadane", "kind": TopicKind.ALGORITHM},
            {"slug": "frequency-counting", "name": "Frequency Counting", "kind": TopicKind.TECHNIQUE},
            {"slug": "matrix", "name": "Matrix"},
        ],
    },
    {
        "slug": "sorting",
        "name": "Sorting",
        "children": [
            {"slug": "comparator-sorting", "name": "Custom Comparators", "kind": TopicKind.TECHNIQUE},
            {"slug": "counting-sort", "name": "Counting Sort", "kind": TopicKind.ALGORITHM},
            {"slug": "merge-sort", "name": "Merge Sort", "kind": TopicKind.ALGORITHM},
            {"slug": "inversions", "name": "Inversion Counting", "kind": TopicKind.TECHNIQUE},
        ],
    },
    {
        "slug": "binary-search",
        "name": "Binary Search",
        "children": [
            {"slug": "classic-binary-search", "name": "Classic Binary Search", "kind": TopicKind.ALGORITHM},
            {"slug": "lower-bound", "name": "Lower Bound", "kind": TopicKind.ALGORITHM},
            {"slug": "upper-bound", "name": "Upper Bound", "kind": TopicKind.ALGORITHM},
            {"slug": "binary-search-on-answer", "name": "Binary Search on Answer", "kind": TopicKind.TECHNIQUE},
            {"slug": "monotonic-predicate", "name": "Monotonic Predicate Search", "kind": TopicKind.TECHNIQUE},
            {"slug": "ternary-search", "name": "Ternary Search", "kind": TopicKind.ALGORITHM},
        ],
    },
    {
        "slug": "strings",
        "name": "Strings",
        "children": [
            {"slug": "hashing", "name": "String Hashing", "kind": TopicKind.TECHNIQUE},
            {"slug": "kmp", "name": "KMP / Z-Function", "kind": TopicKind.ALGORITHM},
            {"slug": "tries", "name": "Tries"},
            {"slug": "suffix-structures", "name": "Suffix Structures"},
            {"slug": "palindromes", "name": "Palindromes"},
        ],
    },
    {
        "slug": "linked-list",
        "name": "Linked List",
        "children": [
            {"slug": "fast-slow-pointers", "name": "Fast & Slow Pointers", "kind": TopicKind.TECHNIQUE},
            {"slug": "list-reversal", "name": "List Reversal", "kind": TopicKind.TECHNIQUE},
        ],
    },
    {
        "slug": "recursion",
        "name": "Recursion & Backtracking",
        "children": [
            {"slug": "subsets", "name": "Subsets & Subsequences", "kind": TopicKind.TECHNIQUE},
            {"slug": "permutations", "name": "Permutations", "kind": TopicKind.TECHNIQUE},
            {"slug": "backtracking", "name": "Backtracking", "kind": TopicKind.TECHNIQUE},
            {"slug": "divide-and-conquer", "name": "Divide & Conquer", "kind": TopicKind.TECHNIQUE},
            {"slug": "meet-in-the-middle", "name": "Meet in the Middle", "kind": TopicKind.TECHNIQUE},
        ],
    },
    {
        "slug": "bit-manipulation",
        "name": "Bit Manipulation",
        "children": [
            {"slug": "bitmasks", "name": "Bitmasks", "kind": TopicKind.TECHNIQUE},
            {"slug": "xor-tricks", "name": "XOR Tricks", "kind": TopicKind.TECHNIQUE},
        ],
    },
    {
        "slug": "stack-queue",
        "name": "Stack & Queue",
        "children": [
            {"slug": "monotonic-stack", "name": "Monotonic Stack", "kind": TopicKind.TECHNIQUE},
            {"slug": "monotonic-queue", "name": "Monotonic Queue", "kind": TopicKind.TECHNIQUE},
            {"slug": "deque", "name": "Deque"},
        ],
    },
    {
        "slug": "heaps",
        "name": "Heaps & Priority Queues",
        "children": [
            {"slug": "top-k", "name": "Top-K Selection", "kind": TopicKind.TECHNIQUE},
            {"slug": "two-heaps", "name": "Two Heaps", "kind": TopicKind.TECHNIQUE},
        ],
    },
    {
        "slug": "greedy",
        "name": "Greedy",
        "children": [
            {"slug": "exchange-argument", "name": "Exchange Argument", "kind": TopicKind.TECHNIQUE},
            {"slug": "interval-scheduling", "name": "Interval Scheduling", "kind": TopicKind.TECHNIQUE},
            {"slug": "sorting-greedy", "name": "Sort-then-Greedy", "kind": TopicKind.TECHNIQUE},
        ],
    },
    {
        "slug": "trees",
        "name": "Trees",
        "children": [
            {"slug": "binary-tree", "name": "Binary Trees"},
            {"slug": "bst", "name": "Binary Search Trees"},
            {"slug": "tree-traversal", "name": "Tree Traversal", "kind": TopicKind.TECHNIQUE},
            {"slug": "lca", "name": "Lowest Common Ancestor", "kind": TopicKind.ALGORITHM},
            {"slug": "tree-dp", "name": "Tree DP", "kind": TopicKind.TECHNIQUE},
            {"slug": "euler-tour", "name": "Euler Tour", "kind": TopicKind.TECHNIQUE},
        ],
    },
    {
        "slug": "graphs",
        "name": "Graphs",
        "children": [
            {"slug": "bfs", "name": "BFS", "kind": TopicKind.ALGORITHM},
            {"slug": "dfs", "name": "DFS", "kind": TopicKind.ALGORITHM},
            {"slug": "topological-sort", "name": "Topological Sort", "kind": TopicKind.ALGORITHM},
            {
                "slug": "shortest-path",
                "name": "Shortest Path",
                "children": [
                    {"slug": "dijkstra", "name": "Dijkstra", "kind": TopicKind.ALGORITHM},
                    {"slug": "bellman-ford", "name": "Bellman-Ford", "kind": TopicKind.ALGORITHM},
                    {"slug": "floyd-warshall", "name": "Floyd-Warshall", "kind": TopicKind.ALGORITHM},
                    {"slug": "zero-one-bfs", "name": "0-1 BFS", "kind": TopicKind.ALGORITHM},
                ],
            },
            {
                "slug": "mst",
                "name": "Minimum Spanning Tree",
                "children": [
                    {"slug": "kruskal", "name": "Kruskal", "kind": TopicKind.ALGORITHM},
                    {"slug": "prim", "name": "Prim", "kind": TopicKind.ALGORITHM},
                ],
            },
            {"slug": "dsu", "name": "Disjoint Set Union", "kind": TopicKind.ALGORITHM},
            {"slug": "scc", "name": "Strongly Connected Components", "kind": TopicKind.ALGORITHM},
            {"slug": "bipartite", "name": "Bipartite Checking", "kind": TopicKind.TECHNIQUE},
            {"slug": "flows", "name": "Network Flow"},
            {"slug": "graph-modeling", "name": "Graph Modeling", "kind": TopicKind.TECHNIQUE},
        ],
    },
    {
        "slug": "dynamic-programming",
        "name": "Dynamic Programming",
        "children": [
            {"slug": "1d-dp", "name": "1D DP", "kind": TopicKind.TECHNIQUE},
            {"slug": "2d-dp", "name": "2D DP", "kind": TopicKind.TECHNIQUE},
            {"slug": "knapsack", "name": "Knapsack", "kind": TopicKind.TECHNIQUE},
            {"slug": "grid-dp", "name": "Grid DP", "kind": TopicKind.TECHNIQUE},
            {"slug": "lis", "name": "Longest Increasing Subsequence", "kind": TopicKind.ALGORITHM},
            {"slug": "lcs", "name": "Longest Common Subsequence", "kind": TopicKind.ALGORITHM},
            {"slug": "interval-dp", "name": "Interval DP", "kind": TopicKind.TECHNIQUE},
            {"slug": "bitmask-dp", "name": "Bitmask DP", "kind": TopicKind.TECHNIQUE},
            {"slug": "digit-dp", "name": "Digit DP", "kind": TopicKind.TECHNIQUE},
            {"slug": "dp-on-trees", "name": "DP on Trees", "kind": TopicKind.TECHNIQUE},
            {"slug": "state-compression", "name": "State Compression", "kind": TopicKind.TECHNIQUE},
            {"slug": "dp-state-design", "name": "State Design", "kind": TopicKind.TECHNIQUE},
        ],
    },
    {
        "slug": "math",
        "name": "Mathematics",
        "children": [
            {"slug": "number-theory", "name": "Number Theory"},
            {"slug": "combinatorics", "name": "Combinatorics"},
            {"slug": "probability", "name": "Probability & Expectation"},
            {"slug": "modular-arithmetic", "name": "Modular Arithmetic", "kind": TopicKind.TECHNIQUE},
            {"slug": "sieve", "name": "Sieve of Eratosthenes", "kind": TopicKind.ALGORITHM},
            {"slug": "gcd-lcm", "name": "GCD / LCM", "kind": TopicKind.TECHNIQUE},
            {"slug": "geometry", "name": "Geometry"},
            {"slug": "game-theory", "name": "Game Theory"},
            {"slug": "matrix-exponentiation", "name": "Matrix Exponentiation", "kind": TopicKind.ALGORITHM},
        ],
    },
    {
        "slug": "data-structures",
        "name": "Advanced Data Structures",
        "children": [
            {"slug": "segment-tree", "name": "Segment Tree", "kind": TopicKind.ALGORITHM},
            {"slug": "fenwick-tree", "name": "Fenwick Tree (BIT)", "kind": TopicKind.ALGORITHM},
            {"slug": "sparse-table", "name": "Sparse Table", "kind": TopicKind.ALGORITHM},
            {"slug": "ordered-set", "name": "Ordered Set / Multiset"},
            {"slug": "sqrt-decomposition", "name": "Sqrt Decomposition", "kind": TopicKind.TECHNIQUE},
        ],
    },
]

#: Patterns are recognizable problem shapes. `is_core` marks patterns worth
#: revisiting periodically even after a clean solve.
PATTERNS: list[dict[str, Any]] = [
    {"slug": "p-sliding-window", "name": "Sliding Window", "topic": "arrays", "is_core": True},
    {"slug": "p-two-pointers", "name": "Two Pointers", "topic": "arrays", "is_core": True},
    {"slug": "p-prefix-sum", "name": "Prefix Sum", "topic": "arrays", "is_core": True},
    {"slug": "p-binary-search-answer", "name": "Binary Search on Answer", "topic": "binary-search", "is_core": True},
    {"slug": "p-classic-binary-search", "name": "Classic Binary Search", "topic": "binary-search"},
    {"slug": "p-monotonic-stack", "name": "Monotonic Stack", "topic": "stack-queue", "is_core": True},
    {"slug": "p-monotonic-queue", "name": "Monotonic Deque", "topic": "stack-queue"},
    {"slug": "p-top-k", "name": "Top-K / Heap", "topic": "heaps"},
    {"slug": "p-bfs", "name": "BFS Traversal", "topic": "graphs", "is_core": True},
    {"slug": "p-dfs", "name": "DFS Traversal", "topic": "graphs", "is_core": True},
    {"slug": "p-shortest-path", "name": "Shortest Path", "topic": "graphs", "is_core": True},
    {"slug": "p-dsu", "name": "DSU / Union-Find", "topic": "graphs", "is_core": True},
    {"slug": "p-topological-sort", "name": "Topological Sort", "topic": "graphs"},
    {"slug": "p-mst", "name": "Minimum Spanning Tree", "topic": "graphs"},
    {"slug": "p-graph-modeling", "name": "Graph Modeling", "topic": "graphs", "is_core": True},
    {"slug": "p-1d-dp", "name": "1D DP", "topic": "dynamic-programming", "is_core": True},
    {"slug": "p-2d-dp", "name": "2D DP", "topic": "dynamic-programming", "is_core": True},
    {"slug": "p-knapsack", "name": "Knapsack", "topic": "dynamic-programming", "is_core": True},
    {"slug": "p-grid-dp", "name": "Grid DP", "topic": "dynamic-programming"},
    {"slug": "p-bitmask-dp", "name": "Bitmask DP", "topic": "dynamic-programming"},
    {"slug": "p-digit-dp", "name": "Digit DP", "topic": "dynamic-programming"},
    {"slug": "p-tree-dp", "name": "Tree DP", "topic": "trees"},
    {"slug": "p-interval-dp", "name": "Interval DP", "topic": "dynamic-programming"},
    {"slug": "p-backtracking", "name": "Backtracking", "topic": "recursion", "is_core": True},
    {"slug": "p-meet-in-the-middle", "name": "Meet in the Middle", "topic": "recursion"},
    {"slug": "p-greedy-exchange", "name": "Greedy Exchange Argument", "topic": "greedy", "is_core": True},
    {"slug": "p-interval-scheduling", "name": "Interval Scheduling", "topic": "greedy"},
    {"slug": "p-constructive", "name": "Constructive", "topic": "basics", "is_core": True},
    {"slug": "p-simulation", "name": "Simulation", "topic": "basics"},
    {"slug": "p-string-hashing", "name": "String Hashing", "topic": "strings"},
    {"slug": "p-trie", "name": "Trie", "topic": "strings"},
    {"slug": "p-range-query", "name": "Range Query", "topic": "data-structures", "is_core": True},
    {"slug": "p-combinatorics", "name": "Counting & Combinatorics", "topic": "math", "is_core": True},
    {"slug": "p-number-theory", "name": "Number Theory", "topic": "math"},
    {"slug": "p-game-theory", "name": "Game Theory", "topic": "math"},
    {"slug": "p-bit-tricks", "name": "Bit Manipulation", "topic": "bit-manipulation"},
    {"slug": "p-tree-traversal", "name": "Tree Traversal", "topic": "trees"},
    {"slug": "p-linked-list", "name": "Linked List Manipulation", "topic": "linked-list"},
    {"slug": "p-sorting", "name": "Sort-based Reduction", "topic": "sorting"},
]

#: Raw platform tag -> (topic slugs, pattern slugs).
#: Codeforces and LeetCode use different vocabularies for the same ideas; both
#: are mapped into the single canonical taxonomy above.
TAG_MAP: dict[str, tuple[list[str], list[str]]] = {
    # --- Codeforces -------------------------------------------------------
    "implementation": (["implementation"], ["p-simulation"]),
    "brute force": (["brute-force"], []),
    "constructive algorithms": (["constructive"], ["p-constructive"]),
    "greedy": (["greedy"], ["p-greedy-exchange"]),
    "math": (["math"], []),
    "number theory": (["number-theory"], ["p-number-theory"]),
    "combinatorics": (["combinatorics"], ["p-combinatorics"]),
    "probabilities": (["probability"], []),
    "geometry": (["geometry"], []),
    "games": (["game-theory"], ["p-game-theory"]),
    "dp": (["dynamic-programming"], ["p-1d-dp"]),
    "graphs": (["graphs"], []),
    "dfs and similar": (["dfs"], ["p-dfs"]),
    "shortest paths": (["shortest-path"], ["p-shortest-path"]),
    "trees": (["trees"], ["p-tree-traversal"]),
    "dsu": (["dsu"], ["p-dsu"]),
    "flows": (["flows"], []),
    "graph matchings": (["flows"], []),
    "binary search": (["binary-search"], ["p-classic-binary-search"]),
    "ternary search": (["ternary-search"], []),
    "two pointers": (["two-pointers"], ["p-two-pointers"]),
    "sortings": (["sorting"], ["p-sorting"]),
    "data structures": (["data-structures"], ["p-range-query"]),
    "strings": (["strings"], []),
    "string suffix structures": (["suffix-structures"], []),
    "hashing": (["hashing"], ["p-string-hashing"]),
    "bitmasks": (["bitmasks"], ["p-bitmask-dp"]),
    "divide and conquer": (["divide-and-conquer"], []),
    "meet-in-the-middle": (["meet-in-the-middle"], ["p-meet-in-the-middle"]),
    "matrices": (["matrix"], []),
    "fft": (["math"], []),
    "interactive": (["implementation"], []),
    "2-sat": (["graphs"], []),
    "chinese remainder theorem": (["number-theory"], []),
    "expression parsing": (["strings"], []),
    "schedules": (["greedy"], ["p-interval-scheduling"]),
    # --- LeetCode ---------------------------------------------------------
    "array": (["arrays"], []),
    "hash-table": (["frequency-counting"], []),
    "hash table": (["frequency-counting"], []),
    "string": (["strings"], []),
    "dynamic-programming": (["dynamic-programming"], ["p-1d-dp"]),
    "dynamic programming": (["dynamic-programming"], ["p-1d-dp"]),
    "sorting": (["sorting"], ["p-sorting"]),
    "depth-first-search": (["dfs"], ["p-dfs"]),
    "depth first search": (["dfs"], ["p-dfs"]),
    "breadth-first-search": (["bfs"], ["p-bfs"]),
    "breadth first search": (["bfs"], ["p-bfs"]),
    "binary-search": (["binary-search"], ["p-classic-binary-search"]),
    "matrix": (["matrix"], []),
    "tree": (["trees"], ["p-tree-traversal"]),
    "binary-tree": (["binary-tree"], ["p-tree-traversal"]),
    "binary tree": (["binary-tree"], ["p-tree-traversal"]),
    "binary-search-tree": (["bst"], []),
    "bit-manipulation": (["bit-manipulation"], ["p-bit-tricks"]),
    "bit manipulation": (["bit-manipulation"], ["p-bit-tricks"]),
    "two-pointers": (["two-pointers"], ["p-two-pointers"]),
    "prefix-sum": (["prefix-sum"], ["p-prefix-sum"]),
    "prefix sum": (["prefix-sum"], ["p-prefix-sum"]),
    "heap-priority-queue": (["heaps"], ["p-top-k"]),
    "heap (priority queue)": (["heaps"], ["p-top-k"]),
    "simulation": (["simulation"], ["p-simulation"]),
    "stack": (["stack-queue"], []),
    "monotonic-stack": (["monotonic-stack"], ["p-monotonic-stack"]),
    "monotonic stack": (["monotonic-stack"], ["p-monotonic-stack"]),
    "monotonic-queue": (["monotonic-queue"], ["p-monotonic-queue"]),
    "queue": (["stack-queue"], []),
    "graph": (["graphs"], []),
    "counting": (["frequency-counting"], ["p-combinatorics"]),
    "sliding-window": (["sliding-window"], ["p-sliding-window"]),
    "sliding window": (["sliding-window"], ["p-sliding-window"]),
    "backtracking": (["backtracking"], ["p-backtracking"]),
    "enumeration": (["brute-force"], []),
    "union-find": (["dsu"], ["p-dsu"]),
    "linked-list": (["linked-list"], ["p-linked-list"]),
    "linked list": (["linked-list"], ["p-linked-list"]),
    "trie": (["tries"], ["p-trie"]),
    "segment-tree": (["segment-tree"], ["p-range-query"]),
    "segment tree": (["segment-tree"], ["p-range-query"]),
    "binary-indexed-tree": (["fenwick-tree"], ["p-range-query"]),
    "binary indexed tree": (["fenwick-tree"], ["p-range-query"]),
    "recursion": (["recursion"], []),
    "divide-and-conquer": (["divide-and-conquer"], []),
    "memoization": (["dynamic-programming"], []),
    "topological-sort": (["topological-sort"], ["p-topological-sort"]),
    "topological sort": (["topological-sort"], ["p-topological-sort"]),
    "shortest-path": (["shortest-path"], ["p-shortest-path"]),
    "shortest path": (["shortest-path"], ["p-shortest-path"]),
    "minimum-spanning-tree": (["mst"], ["p-mst"]),
    "minimum spanning tree": (["mst"], ["p-mst"]),
    "bitmask": (["bitmasks"], ["p-bitmask-dp"]),
    "game-theory": (["game-theory"], ["p-game-theory"]),
    "game theory": (["game-theory"], ["p-game-theory"]),
    "number-theory": (["number-theory"], ["p-number-theory"]),
    "design": (["data-structures"], []),
    "ordered-set": (["ordered-set"], []),
    "string-matching": (["kmp"], []),
    "suffix-array": (["suffix-structures"], []),
    "probability-and-statistics": (["probability"], []),
    "quickselect": (["sorting"], []),
    "rolling-hash": (["hashing"], ["p-string-hashing"]),
}


def seed_taxonomy(db: Session) -> dict[str, int]:
    """Idempotently insert the taxonomy. Safe to run on every startup."""
    created_topics = 0
    updated_topics = 0

    def upsert(node: dict[str, Any], parent: Topic | None, order: int) -> Topic:
        nonlocal created_topics, updated_topics
        slug = node["slug"]
        existing = db.scalar(select(Topic).where(Topic.slug == slug))
        path = f"{parent.path}/{slug}" if parent else slug
        depth = (parent.depth + 1) if parent else 0
        kind = node.get(
            "kind", TopicKind.SUBTOPIC if parent is not None else TopicKind.TOPIC
        )
        if existing is None:
            topic = Topic(
                slug=slug,
                name=node["name"],
                parent_id=parent.id if parent else None,
                kind=kind,
                sort_order=order,
                path=path,
                depth=depth,
            )
            db.add(topic)
            db.flush()
            created_topics += 1
            return topic

        # Keep hierarchy metadata in sync if the tree definition changed.
        if (
            existing.path != path
            or existing.depth != depth
            or existing.name != node["name"]
        ):
            existing.path = path
            existing.depth = depth
            existing.name = node["name"]
            existing.parent_id = parent.id if parent else None
            updated_topics += 1
        return existing

    def walk(nodes: list[dict[str, Any]], parent: Topic | None) -> None:
        for order, node in enumerate(nodes):
            topic = upsert(node, parent, order)
            if node.get("children"):
                walk(node["children"], topic)

    walk(TOPIC_TREE, None)
    db.flush()

    topic_by_slug = {t.slug: t for t in db.scalars(select(Topic)).all()}

    created_patterns = 0
    for order, spec in enumerate(PATTERNS):
        existing = db.scalar(select(Pattern).where(Pattern.slug == spec["slug"]))
        topic = topic_by_slug.get(spec.get("topic", ""))
        if existing is None:
            db.add(
                Pattern(
                    slug=spec["slug"],
                    name=spec["name"],
                    topic_id=topic.id if topic else None,
                    is_core=spec.get("is_core", False),
                    sort_order=order,
                )
            )
            created_patterns += 1
        else:
            existing.name = spec["name"]
            existing.topic_id = topic.id if topic else None
            existing.is_core = spec.get("is_core", False)

    db.commit()
    result = {
        "topics_created": created_topics,
        "topics_updated": updated_topics,
        "patterns_created": created_patterns,
    }
    log.info("taxonomy seeded", **result)
    return result


def map_tags(tags: list[str] | None) -> tuple[set[str], set[str]]:
    """Translate raw platform tags into canonical topic/pattern slugs."""
    topic_slugs: set[str] = set()
    pattern_slugs: set[str] = set()
    for tag in tags or []:
        key = str(tag).strip().lower()
        entry = TAG_MAP.get(key)
        if entry is None:
            # Tolerate hyphen/space variants without duplicating the table.
            entry = TAG_MAP.get(key.replace("-", " ")) or TAG_MAP.get(
                key.replace(" ", "-")
            )
        if entry:
            topics, patterns = entry
            topic_slugs.update(topics)
            pattern_slugs.update(patterns)
    return topic_slugs, pattern_slugs
