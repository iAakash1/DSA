"""The contest template library.

Knowing an algorithm and being able to type it correctly at minute 210 of a
five-hour contest are different skills. These are the reference implementations
to internalise: short, C++17, and written the way they would actually be typed
under time pressure rather than the way a textbook presents them.

Every template carries `pitfalls` — the mistakes that actually cost teams
penalty time on that specific algorithm. Recall is measured from
`TemplateReview` rows, never guessed.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Template:
    slug: str
    name: str
    topic: str
    #: Roughly how long a fluent contestant needs to type it from memory.
    typing_minutes: int
    #: Why it earns a slot in limited memory.
    why: str
    code: str
    pitfalls: list[str] = field(default_factory=list)
    complexity: str = ""


TEMPLATES: list[Template] = [
    Template(
        slug="scaffold",
        name="Contest scaffold & fast I/O",
        topic="basics",
        typing_minutes=1,
        why=(
            "cin/cout are tied to stdio by default, which makes reading 10^6 "
            "integers slow enough to TLE on its own."
        ),
        complexity="—",
        pitfalls=[
            "Never mix cin/cout with scanf/printf after sync_with_stdio(false).",
            "endl flushes every time; use '\\n' inside loops.",
        ],
        code="""#include <bits/stdc++.h>
using namespace std;
using ll = long long;

void solve() {
}

int main() {
    ios::sync_with_stdio(false);
    cin.tie(nullptr);
    int t = 1;
    cin >> t;              // drop when the problem is single-test
    while (t--) solve();
    return 0;
}""",
    ),
    Template(
        slug="dsu",
        name="Disjoint set union",
        topic="graphs.dsu",
        typing_minutes=2,
        why="Connectivity, Kruskal, and half of all 'merge these groups' problems.",
        complexity="O(alpha(n)) amortised per operation",
        pitfalls=[
            "Union by size/rank AND path compression — one alone is O(log n).",
            "unite() returns false when already joined; that return value is how "
            "you count components or detect a cycle.",
        ],
        code="""struct DSU {
    vector<int> parent, size_;
    explicit DSU(int n) : parent(n), size_(n, 1) {
        iota(parent.begin(), parent.end(), 0);
    }
    int find(int x) {
        while (parent[x] != x) x = parent[x] = parent[parent[x]];
        return x;
    }
    bool unite(int a, int b) {
        a = find(a); b = find(b);
        if (a == b) return false;
        if (size_[a] < size_[b]) swap(a, b);
        parent[b] = a;
        size_[a] += size_[b];
        return true;
    }
    bool same(int a, int b) { return find(a) == find(b); }
};""",
    ),
    Template(
        slug="fenwick",
        name="Fenwick tree (BIT)",
        topic="data-structures.fenwick-tree",
        typing_minutes=2,
        why="Prefix sums with point updates in a third of the code of a segment tree.",
        complexity="O(log n) update and query",
        pitfalls=[
            "1-indexed internally. Passing a 0 index loops forever.",
            "range_sum(l, r) is inclusive; off-by-one here is the classic BIT bug.",
        ],
        code="""struct Fenwick {
    int n;
    vector<ll> bit;
    explicit Fenwick(int n) : n(n), bit(n + 1, 0) {}

    void add(int i, ll delta) {            // 0-indexed position
        for (++i; i <= n; i += i & -i) bit[i] += delta;
    }
    ll prefix(int i) {                     // sum of [0, i]
        ll s = 0;
        for (++i; i > 0; i -= i & -i) s += bit[i];
        return s;
    }
    ll range_sum(int l, int r) {           // inclusive
        return l > r ? 0 : prefix(r) - (l ? prefix(l - 1) : 0);
    }
};""",
    ),
    Template(
        slug="segment-tree",
        name="Iterative segment tree",
        topic="data-structures.segment-tree",
        typing_minutes=3,
        why="Any associative range query with point updates, without recursion overhead.",
        complexity="O(log n) update and query",
        pitfalls=[
            "The identity element must be neutral for combine — 0 for sum, "
            "LLONG_MIN for max, not 0.",
            "Query range is half-open [l, r).",
        ],
        code="""struct SegTree {                        // point update, range query
    int n;
    vector<ll> t;
    static ll combine(ll a, ll b) { return a + b; }
    static constexpr ll IDENTITY = 0;

    explicit SegTree(const vector<ll>& a) : n(a.size()), t(2 * a.size()) {
        copy(a.begin(), a.end(), t.begin() + n);
        for (int i = n - 1; i > 0; --i) t[i] = combine(t[2 * i], t[2 * i + 1]);
    }
    void update(int i, ll value) {
        for (t[i += n] = value; i > 1; i >>= 1)
            t[i >> 1] = combine(t[i], t[i ^ 1]);
    }
    ll query(int l, int r) {               // [l, r)
        ll left = IDENTITY, right = IDENTITY;
        for (l += n, r += n; l < r; l >>= 1, r >>= 1) {
            if (l & 1) left = combine(left, t[l++]);
            if (r & 1) right = combine(t[--r], right);
        }
        return combine(left, right);
    }
};""",
    ),
    Template(
        slug="lazy-segment-tree",
        name="Lazy segment tree (range add, range sum)",
        topic="data-structures.segment-tree",
        typing_minutes=6,
        why="Range update plus range query — the workhorse of hard data-structure problems.",
        complexity="O(log n) amortised",
        pitfalls=[
            "push() must scale the pending add by the segment length.",
            "Apply lazy to a node BEFORE reading it, in both update and query.",
            "Sums overflow int fast; the tree must be long long.",
        ],
        code="""struct LazySeg {
    int n;
    vector<ll> t, lazy;
    explicit LazySeg(int n) : n(n), t(4 * n, 0), lazy(4 * n, 0) {}

    void apply_(int node, int len, ll add) {
        t[node] += add * len;
        lazy[node] += add;
    }
    void push(int node, int len) {
        if (!lazy[node]) return;
        apply_(2 * node, len / 2, lazy[node]);
        apply_(2 * node + 1, len - len / 2, lazy[node]);
        lazy[node] = 0;
    }
    void update(int node, int nl, int nr, int l, int r, ll add) {
        if (r < nl || nr < l) return;
        if (l <= nl && nr <= r) { apply_(node, nr - nl + 1, add); return; }
        push(node, nr - nl + 1);
        int mid = (nl + nr) / 2;
        update(2 * node, nl, mid, l, r, add);
        update(2 * node + 1, mid + 1, nr, l, r, add);
        t[node] = t[2 * node] + t[2 * node + 1];
    }
    ll query(int node, int nl, int nr, int l, int r) {
        if (r < nl || nr < l) return 0;
        if (l <= nl && nr <= r) return t[node];
        push(node, nr - nl + 1);
        int mid = (nl + nr) / 2;
        return query(2 * node, nl, mid, l, r)
             + query(2 * node + 1, mid + 1, nr, l, r);
    }
};""",
    ),
    Template(
        slug="sparse-table",
        name="Sparse table (static RMQ)",
        topic="data-structures.sparse-table",
        typing_minutes=3,
        why="O(1) range minimum when the array never changes — beats a segment tree.",
        complexity="O(n log n) build, O(1) query",
        pitfalls=[
            "Only valid for idempotent operations (min, max, gcd) — not sum.",
            "Query range is inclusive [l, r]; k = log2(r - l + 1).",
        ],
        code="""struct SparseTable {
    vector<vector<ll>> st;
    vector<int> lg;
    explicit SparseTable(const vector<ll>& a) {
        int n = a.size(), k = 1;
        while ((1 << k) <= n) ++k;
        lg.assign(n + 1, 0);
        for (int i = 2; i <= n; ++i) lg[i] = lg[i / 2] + 1;
        st.assign(k, vector<ll>(n));
        st[0] = a;
        for (int j = 1; j < k; ++j)
            for (int i = 0; i + (1 << j) <= n; ++i)
                st[j][i] = min(st[j - 1][i], st[j - 1][i + (1 << (j - 1))]);
    }
    ll query(int l, int r) {               // inclusive
        int j = lg[r - l + 1];
        return min(st[j][l], st[j][r - (1 << j) + 1]);
    }
};""",
    ),
    Template(
        slug="dijkstra",
        name="Dijkstra",
        topic="graphs.shortest-path.dijkstra",
        typing_minutes=3,
        why="Single-source shortest path with non-negative weights.",
        complexity="O((V + E) log V)",
        pitfalls=[
            "Skip stale heap entries with `if (d > dist[u]) continue;` or it degrades badly.",
            "Wrong with negative edges — reach for Bellman-Ford instead.",
            "INF must survive addition: use 4e18 / 2, not LLONG_MAX.",
        ],
        code="""const ll INF = 4e18;

vector<ll> dijkstra(int src, const vector<vector<pair<int, ll>>>& g) {
    vector<ll> dist(g.size(), INF);
    priority_queue<pair<ll, int>, vector<pair<ll, int>>, greater<>> pq;
    dist[src] = 0;
    pq.push({0, src});
    while (!pq.empty()) {
        auto [d, u] = pq.top(); pq.pop();
        if (d > dist[u]) continue;         // stale entry
        for (auto [v, w] : g[u])
            if (d + w < dist[v]) {
                dist[v] = d + w;
                pq.push({dist[v], v});
            }
    }
    return dist;
}""",
    ),
    Template(
        slug="bellman-ford",
        name="Bellman-Ford / negative cycle",
        topic="graphs.shortest-path.bellman-ford",
        typing_minutes=3,
        why="The only simple shortest path that tolerates negative edges, and it detects cycles.",
        complexity="O(V * E)",
        pitfalls=[
            "A relaxation on the V-th pass means a negative cycle exists.",
            "Only cycles reachable from the source are found.",
        ],
        code="""// returns false when a negative cycle is reachable from src
bool bellman_ford(int n, int src, const vector<array<ll, 3>>& edges,
                  vector<ll>& dist) {
    dist.assign(n, INF);
    dist[src] = 0;
    for (int pass = 0; pass < n; ++pass) {
        bool changed = false;
        for (auto [u, v, w] : edges)
            if (dist[u] < INF && dist[u] + w < dist[v]) {
                dist[v] = dist[u] + w;
                changed = true;
                if (pass == n - 1) return false;
            }
        if (!changed) break;
    }
    return true;
}""",
    ),
    Template(
        slug="kahn-toposort",
        name="Topological sort (Kahn)",
        topic="graphs.topological-sort",
        typing_minutes=2,
        why="Ordering with prerequisites, and it detects cycles for free.",
        complexity="O(V + E)",
        pitfalls=[
            "If the result holds fewer than n nodes, the graph has a cycle.",
            "Use a priority_queue when the problem wants the lexicographically smallest order.",
        ],
        code="""// empty result => the graph has a cycle
vector<int> toposort(int n, const vector<vector<int>>& g) {
    vector<int> indeg(n, 0), order;
    for (int u = 0; u < n; ++u)
        for (int v : g[u]) ++indeg[v];
    queue<int> q;
    for (int u = 0; u < n; ++u)
        if (!indeg[u]) q.push(u);
    while (!q.empty()) {
        int u = q.front(); q.pop();
        order.push_back(u);
        for (int v : g[u])
            if (--indeg[v] == 0) q.push(v);
    }
    return (int)order.size() == n ? order : vector<int>{};
}""",
    ),
    Template(
        slug="scc-tarjan",
        name="Strongly connected components (Tarjan)",
        topic="graphs.scc",
        typing_minutes=5,
        why="Condensing a directed graph into a DAG turns many hard problems into easy DP.",
        complexity="O(V + E)",
        pitfalls=[
            "low[u] uses disc[v] for on-stack back edges, low[v] only for tree edges.",
            "Components come out in reverse topological order of the condensation.",
        ],
        code="""struct SCC {
    int n, timer = 0, count_ = 0;
    vector<vector<int>> g;
    vector<int> disc, low, comp;
    vector<char> on_stack;
    stack<int> st;

    explicit SCC(int n) : n(n), g(n), disc(n, -1), low(n), comp(n, -1),
                          on_stack(n, 0) {}
    void add_edge(int u, int v) { g[u].push_back(v); }

    void dfs(int u) {
        disc[u] = low[u] = timer++;
        st.push(u); on_stack[u] = 1;
        for (int v : g[u]) {
            if (disc[v] == -1) { dfs(v); low[u] = min(low[u], low[v]); }
            else if (on_stack[v]) low[u] = min(low[u], disc[v]);
        }
        if (low[u] == disc[u]) {
            while (true) {
                int v = st.top(); st.pop(); on_stack[v] = 0;
                comp[v] = count_;
                if (v == u) break;
            }
            ++count_;
        }
    }
    void run() { for (int u = 0; u < n; ++u) if (disc[u] == -1) dfs(u); }
};""",
    ),
    Template(
        slug="lca-binary-lifting",
        name="LCA by binary lifting",
        topic="trees.lca",
        typing_minutes=5,
        why="Tree distance, k-th ancestor, and path queries all reduce to this.",
        complexity="O(n log n) build, O(log n) query",
        pitfalls=[
            "Lift the deeper node to equal depth FIRST, then lift both together.",
            "The root's ancestors must all point back at the root (or -1, consistently).",
            "Recursive DFS blows the stack around n = 2*10^5; prefer the iterative build.",
        ],
        code="""struct LCA {
    int n, LOG;
    vector<vector<int>> up, g;
    vector<int> depth;

    explicit LCA(int n) : n(n), LOG(1), g(n), depth(n, 0) {
        while ((1 << LOG) < n) ++LOG;
        ++LOG;
        up.assign(LOG, vector<int>(n, 0));
    }
    void add_edge(int u, int v) { g[u].push_back(v); g[v].push_back(u); }

    void build(int root = 0) {
        vector<int> stack_{root};
        vector<char> seen(n, 0);
        up[0][root] = root;
        seen[root] = 1;
        while (!stack_.empty()) {
            int u = stack_.back(); stack_.pop_back();
            for (int v : g[u])
                if (!seen[v]) {
                    seen[v] = 1;
                    depth[v] = depth[u] + 1;
                    up[0][v] = u;
                    stack_.push_back(v);
                }
        }
        for (int k = 1; k < LOG; ++k)
            for (int v = 0; v < n; ++v)
                up[k][v] = up[k - 1][up[k - 1][v]];
    }
    int lift(int u, int steps) {
        for (int k = 0; k < LOG; ++k)
            if (steps >> k & 1) u = up[k][u];
        return u;
    }
    int lca(int u, int v) {
        if (depth[u] < depth[v]) swap(u, v);
        u = lift(u, depth[u] - depth[v]);
        if (u == v) return u;
        for (int k = LOG - 1; k >= 0; --k)
            if (up[k][u] != up[k][v]) { u = up[k][u]; v = up[k][v]; }
        return up[0][u];
    }
    int dist(int u, int v) { return depth[u] + depth[v] - 2 * depth[lca(u, v)]; }
};""",
    ),
    Template(
        slug="dinic",
        name="Max flow (Dinic)",
        topic="graphs.flows",
        typing_minutes=8,
        why=(
            "Matching, min cut, and project-selection problems collapse to one "
            "flow call. Long to type — worth having truly memorised."
        ),
        complexity="O(V^2 E), O(E sqrt(V)) on unit capacities",
        pitfalls=[
            "Store edges in one vector and pair them as i ^ 1 for the reverse edge.",
            "Reset the `it` iterators every phase, not every DFS.",
            "For bipartite matching, capacities of 1 make this near-linear.",
        ],
        code="""struct Dinic {
    struct Edge { int to; ll cap; };
    vector<Edge> edges;
    vector<vector<int>> g;
    vector<int> level, it;
    int n;

    explicit Dinic(int n) : g(n), level(n), it(n), n(n) {}

    void add_edge(int u, int v, ll cap) {
        g[u].push_back(edges.size()); edges.push_back({v, cap});
        g[v].push_back(edges.size()); edges.push_back({u, 0});
    }
    bool bfs(int s, int t) {
        fill(level.begin(), level.end(), -1);
        queue<int> q; q.push(s); level[s] = 0;
        while (!q.empty()) {
            int u = q.front(); q.pop();
            for (int id : g[u]) {
                if (edges[id].cap > 0 && level[edges[id].to] == -1) {
                    level[edges[id].to] = level[u] + 1;
                    q.push(edges[id].to);
                }
            }
        }
        return level[t] != -1;
    }
    ll dfs(int u, int t, ll pushed) {
        if (u == t || !pushed) return pushed;
        for (int& i = it[u]; i < (int)g[u].size(); ++i) {
            int id = g[u][i], v = edges[id].to;
            if (level[v] != level[u] + 1 || edges[id].cap == 0) continue;
            if (ll got = dfs(v, t, min(pushed, edges[id].cap))) {
                edges[id].cap -= got;
                edges[id ^ 1].cap += got;
                return got;
            }
        }
        return 0;
    }
    ll max_flow(int s, int t) {
        ll flow = 0;
        while (bfs(s, t)) {
            fill(it.begin(), it.end(), 0);
            while (ll pushed = dfs(s, t, LLONG_MAX)) flow += pushed;
        }
        return flow;
    }
};""",
    ),
    Template(
        slug="modular-arithmetic",
        name="Modular power, inverse and nCr",
        topic="math.modular-arithmetic",
        typing_minutes=3,
        why="Almost every counting problem asks for the answer mod 1e9+7.",
        complexity="O(log m) per power, O(n) factorial precompute",
        pitfalls=[
            "Fermat's inverse needs a PRIME modulus. 1e9+7 qualifies; 1e9 does not.",
            "Multiply as (ll) or it overflows silently.",
            "Subtraction mod m can go negative: ((a - b) % m + m) % m.",
        ],
        code="""const ll MOD = 1'000'000'007;

ll power(ll base, ll exp, ll mod = MOD) {
    ll result = 1;
    base %= mod;
    while (exp > 0) {
        if (exp & 1) result = result * base % mod;
        base = base * base % mod;
        exp >>= 1;
    }
    return result;
}
ll inverse(ll a, ll mod = MOD) { return power(a, mod - 2, mod); }  // prime mod

vector<ll> fact, inv_fact;
void build_factorials(int n) {
    fact.assign(n + 1, 1);
    inv_fact.assign(n + 1, 1);
    for (int i = 1; i <= n; ++i) fact[i] = fact[i - 1] * i % MOD;
    inv_fact[n] = inverse(fact[n]);
    for (int i = n; i > 0; --i) inv_fact[i - 1] = inv_fact[i] * i % MOD;
}
ll nCr(int n, int r) {
    if (r < 0 || r > n) return 0;
    return fact[n] * inv_fact[r] % MOD * inv_fact[n - r] % MOD;
}""",
    ),
    Template(
        slug="sieve",
        name="Sieve with smallest prime factor",
        topic="math.sieve",
        typing_minutes=2,
        why="Primality plus O(log n) factorisation of any number up to the limit.",
        complexity="O(n log log n) build, O(log n) factorise",
        pitfalls=[
            "spf[1] stays 1 — factorising 1 must not loop.",
            "A plain bool sieve is not enough when the problem wants factorisations.",
        ],
        code="""vector<int> spf;                        // smallest prime factor

void build_sieve(int n) {
    spf.assign(n + 1, 0);
    for (int i = 2; i <= n; ++i) {
        if (!spf[i])
            for (ll j = i; j <= n; j += i)
                if (!spf[j]) spf[j] = i;
    }
}
vector<pair<int, int>> factorise(int x) {
    vector<pair<int, int>> out;
    while (x > 1) {
        int p = spf[x], e = 0;
        while (x % p == 0) { x /= p; ++e; }
        out.push_back({p, e});
    }
    return out;
}""",
    ),
    Template(
        slug="binary-search-answer",
        name="Binary search on the answer",
        topic="binary-search.binary-search-on-answer",
        typing_minutes=1,
        why=(
            "The single highest-frequency pattern in div2 C/D: if feasibility is "
            "monotone in x, you can search for the boundary instead of computing it."
        ),
        complexity="O(log(range) * cost of check)",
        pitfalls=[
            "lo + (hi - lo) / 2 avoids overflow; (lo + hi) / 2 does not.",
            "Decide up front whether you want the first true or the last true, and "
            "keep the invariant consistent with it.",
            "For real-valued answers, iterate a fixed 100 times rather than "
            "comparing floats for equality.",
        ],
        code="""// smallest x in [lo, hi] with feasible(x) == true
ll binary_search_answer(ll lo, ll hi, const function<bool(ll)>& feasible) {
    while (lo < hi) {
        ll mid = lo + (hi - lo) / 2;
        if (feasible(mid)) hi = mid;
        else lo = mid + 1;
    }
    return lo;
}""",
    ),
    Template(
        slug="kmp",
        name="KMP prefix function",
        topic="strings.kmp",
        typing_minutes=2,
        why="Substring search and every 'shortest period' question.",
        complexity="O(n + m)",
        pitfalls=[
            "The separator between pattern and text must not occur in either.",
            "n - pi[n-1] is the smallest period only when it divides n.",
        ],
        code="""vector<int> prefix_function(const string& s) {
    int n = s.size();
    vector<int> pi(n, 0);
    for (int i = 1; i < n; ++i) {
        int j = pi[i - 1];
        while (j > 0 && s[i] != s[j]) j = pi[j - 1];
        if (s[i] == s[j]) ++j;
        pi[i] = j;
    }
    return pi;
}
// occurrences of `pat` in `text`
vector<int> find_all(const string& text, const string& pat) {
    string combined = pat + '\\x01' + text;
    vector<int> pi = prefix_function(combined), out;
    for (int i = pat.size() + 1; i < (int)combined.size(); ++i)
        if (pi[i] == (int)pat.size())
            out.push_back(i - 2 * (int)pat.size());
    return out;
}""",
    ),
    Template(
        slug="z-function",
        name="Z-function",
        topic="strings.hashing",
        typing_minutes=2,
        why="Often shorter than KMP for matching, and directly answers prefix questions.",
        complexity="O(n)",
        pitfalls=[
            "z[0] is conventionally left as 0 (or n); be consistent when you use it.",
            "The [l, r) window must be updated only when i + z[i] pushes past r.",
        ],
        code="""vector<int> z_function(const string& s) {
    int n = s.size(), l = 0, r = 0;
    vector<int> z(n, 0);
    for (int i = 1; i < n; ++i) {
        if (i < r) z[i] = min(r - i, z[i - l]);
        while (i + z[i] < n && s[z[i]] == s[i + z[i]]) ++z[i];
        if (i + z[i] > r) { l = i; r = i + z[i]; }
    }
    return z;
}""",
    ),
    Template(
        slug="string-hashing",
        name="Polynomial string hashing",
        topic="strings.hashing",
        typing_minutes=3,
        why="O(1) substring comparison — the escape hatch when suffix structures are overkill.",
        complexity="O(n) build, O(1) substring hash",
        pitfalls=[
            "A single 32-bit modulus loses to anti-hash tests. Use a 64-bit prime "
            "modulus, or two moduli.",
            "Choosing the base at random at runtime defeats prepared countertests.",
        ],
        code="""struct Hashing {
    static constexpr ll MOD = (1LL << 61) - 1;
    ll base;
    vector<ll> h, p;

    static ll mul(__int128 a, ll b) {
        __int128 r = a * b;
        return (ll)((r >> 61) + (r & MOD)) % MOD;
    }
    explicit Hashing(const string& s) {
        mt19937_64 rng(chrono::steady_clock::now().time_since_epoch().count());
        base = 131 + rng() % 1000;
        int n = s.size();
        h.assign(n + 1, 0);
        p.assign(n + 1, 1);
        for (int i = 0; i < n; ++i) {
            h[i + 1] = (mul(h[i], base) + s[i]) % MOD;
            p[i + 1] = mul(p[i], base);
        }
    }
    ll substring(int l, int len) {          // hash of s[l, l + len)
        return (h[l + len] - mul(h[l], p[len]) % MOD + MOD) % MOD;
    }
};""",
    ),
    Template(
        slug="trie",
        name="Binary trie (XOR queries)",
        topic="strings.tries",
        typing_minutes=4,
        why="Maximum-XOR-pair and XOR-subarray problems become linear.",
        complexity="O(bits) per insert and query",
        pitfalls=[
            "Fix the bit width up front (30 for 1e9, 31 for unsigned, 63 for ll).",
            "Store a count per node if the problem needs deletions.",
        ],
        code="""struct BinaryTrie {
    static constexpr int BITS = 30;
    vector<array<int, 2>> child{{{-1, -1}}};
    vector<int> count_{0};

    void insert(int value) {
        int node = 0;
        for (int b = BITS; b >= 0; --b) {
            int bit = value >> b & 1;
            if (child[node][bit] == -1) {
                child[node][bit] = child.size();
                child.push_back({-1, -1});
                count_.push_back(0);
            }
            node = child[node][bit];
            ++count_[node];
        }
    }
    int max_xor(int value) {                // trie must be non-empty
        int node = 0, best = 0;
        for (int b = BITS; b >= 0; --b) {
            int want = !(value >> b & 1);
            if (child[node][want] != -1 && count_[child[node][want]] > 0) {
                best |= 1 << b;
                node = child[node][want];
            } else {
                node = child[node][!want];
            }
        }
        return best;
    }
};""",
    ),
    Template(
        slug="monotonic-stack",
        name="Monotonic stack (previous smaller)",
        topic="stack-queue.monotonic-stack",
        typing_minutes=2,
        why=(
            "Largest rectangle, sum of subarray minimums, and every 'next greater' "
            "variant are the same eight lines."
        ),
        complexity="O(n)",
        pitfalls=[
            "Strict vs non-strict comparison decides how ties are attributed — "
            "get it wrong and duplicate values are double counted.",
            "Push indices, not values, whenever widths matter.",
        ],
        code="""// prev[i] = index of the nearest j < i with a[j] < a[i], else -1
vector<int> previous_smaller(const vector<ll>& a) {
    int n = a.size();
    vector<int> prev(n, -1);
    stack<int> st;
    for (int i = 0; i < n; ++i) {
        while (!st.empty() && a[st.top()] >= a[i]) st.pop();
        prev[i] = st.empty() ? -1 : st.top();
        st.push(i);
    }
    return prev;
}""",
    ),
    Template(
        slug="convex-hull",
        name="Convex hull (monotone chain)",
        topic="math.geometry",
        typing_minutes=4,
        why="The entry point to computational geometry, and it appears every regional.",
        complexity="O(n log n)",
        pitfalls=[
            "cross() must be long long — coordinates up to 1e9 overflow int when multiplied.",
            "`<= 0` drops collinear points, `< 0` keeps them. The problem decides.",
            "Fewer than 3 distinct points needs a special case.",
        ],
        code="""struct Point { ll x, y; };

ll cross(const Point& o, const Point& a, const Point& b) {
    return (a.x - o.x) * (b.y - o.y) - (a.y - o.y) * (b.x - o.x);
}
// counter-clockwise hull; collinear points are dropped
vector<Point> convex_hull(vector<Point> pts) {
    sort(pts.begin(), pts.end(),
         [](const Point& a, const Point& b) {
             return a.x != b.x ? a.x < b.x : a.y < b.y;
         });
    pts.erase(unique(pts.begin(), pts.end(),
                     [](const Point& a, const Point& b) {
                         return a.x == b.x && a.y == b.y;
                     }),
              pts.end());
    if (pts.size() < 3) return pts;

    vector<Point> hull;
    for (int pass = 0; pass < 2; ++pass) {
        size_t start = hull.size();
        for (const Point& p : pts) {
            while (hull.size() >= start + 2 &&
                   cross(hull[hull.size() - 2], hull.back(), p) <= 0)
                hull.pop_back();
            hull.push_back(p);
        }
        hull.pop_back();
        reverse(pts.begin(), pts.end());
    }
    return hull;
}""",
    ),
    Template(
        slug="matrix-exponentiation",
        name="Matrix exponentiation",
        topic="math.matrix-exponentiation",
        typing_minutes=4,
        why="Linear recurrences with n up to 1e18 — Fibonacci-style problems in log time.",
        complexity="O(k^3 log n)",
        pitfalls=[
            "The identity matrix, not a zero matrix, is the starting accumulator.",
            "Reduce mod inside the innermost loop or it overflows.",
        ],
        code="""using Matrix = vector<vector<ll>>;

Matrix multiply(const Matrix& a, const Matrix& b, ll mod = MOD) {
    int n = a.size(), m = b[0].size(), k = b.size();
    Matrix c(n, vector<ll>(m, 0));
    for (int i = 0; i < n; ++i)
        for (int t = 0; t < k; ++t) {
            if (!a[i][t]) continue;
            for (int j = 0; j < m; ++j)
                c[i][j] = (c[i][j] + a[i][t] * b[t][j]) % mod;
        }
    return c;
}
Matrix matrix_power(Matrix base, ll exp, ll mod = MOD) {
    int n = base.size();
    Matrix result(n, vector<ll>(n, 0));
    for (int i = 0; i < n; ++i) result[i][i] = 1;
    while (exp > 0) {
        if (exp & 1) result = multiply(result, base, mod);
        base = multiply(base, base, mod);
        exp >>= 1;
    }
    return result;
}""",
    ),
    Template(
        slug="coordinate-compression",
        name="Coordinate compression",
        topic="basics.implementation",
        typing_minutes=1,
        why=(
            "Turns values up to 1e18 into indices up to n, which is what makes a "
            "BIT or segment tree usable on them at all."
        ),
        complexity="O(n log n)",
        pitfalls=[
            "Compress the union of every value the problem touches, including query "
            "bounds — not just the array.",
            "lower_bound on a vector that was not sorted-and-uniqued returns nonsense.",
        ],
        code="""struct Compressor {
    vector<ll> values;
    explicit Compressor(vector<ll> raw) : values(std::move(raw)) {
        sort(values.begin(), values.end());
        values.erase(unique(values.begin(), values.end()), values.end());
    }
    int index(ll v) const {                 // 0-based rank
        return lower_bound(values.begin(), values.end(), v) - values.begin();
    }
    int size() const { return values.size(); }
};""",
    ),
]

TEMPLATES_BY_SLUG: dict[str, Template] = {t.slug: t for t in TEMPLATES}


def template_summaries() -> list[dict]:
    """Library listing without the code bodies, for index views."""
    return [
        {
            "slug": t.slug,
            "name": t.name,
            "topic": t.topic,
            "typing_minutes": t.typing_minutes,
            "complexity": t.complexity,
            "why": t.why,
        }
        for t in TEMPLATES
    ]


def template_detail(slug: str) -> dict | None:
    template = TEMPLATES_BY_SLUG.get(slug)
    if template is None:
        return None
    return {
        "slug": template.slug,
        "name": template.name,
        "topic": template.topic,
        "typing_minutes": template.typing_minutes,
        "complexity": template.complexity,
        "why": template.why,
        "pitfalls": list(template.pitfalls),
        "code": template.code,
    }
