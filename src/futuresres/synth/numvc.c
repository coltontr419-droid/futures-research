/* Max clique via NuMVC (Cai, Su, Luo & Sattar 2013) on the complement graph: a vertex cover C of the complement leaves V \ C as a clique.
   Wall-clock limited. decisions.md §1165.
   stdin:  n time_limit_seconds seed, then n lines "deg v1 v2 ..." (adjacency lists of the ORIGINAL graph, 0-based)
   stdout: clique size, then its vertices. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <time.h>

#define MAXN 1024
static int n, m;
static uint8_t A[MAXN][MAXN];                 /* original adjacency */
static int *eu, *ev, *w;                      /* complement edges and their weights */
static int *nb[MAXN], *ne[MAXN], cdeg[MAXN];   /* complement neighbours and incident edge ids */
static int inC[MAXN], dscore[MAXN], conf[MAXN]; static long long age[MAXN];
static int *unc, *upos, nunc, csize, best[MAXN], bsz;
static unsigned long long rs;
static inline unsigned rnd(void) { rs ^= rs << 13; rs ^= rs >> 7; rs ^= rs << 17; return (unsigned)rs; }
static double now(void) { struct timespec t; clock_gettime(CLOCK_MONOTONIC, &t); return t.tv_sec + t.tv_nsec * 1e-9; }

static inline void unc_add(int e) { upos[e] = nunc; unc[nunc++] = e; }
static inline void unc_del(int e) { int last = unc[--nunc]; unc[upos[e]] = last; upos[last] = upos[e]; }

static void add(int v, long long step) {
    inC[v] = 1; csize++; dscore[v] = -dscore[v]; age[v] = step;
    for (int i = 0; i < cdeg[v]; i++) {
        int u = nb[v][i], e = ne[v][i];
        if (!inC[u]) { dscore[u] -= w[e]; conf[u] = 1; unc_del(e); }   /* edge becomes covered by v alone */
        else dscore[u] += w[e];                                        /* u no longer sole cover */
    }
}
static void rem(int v, long long step) {
    inC[v] = 0; csize--; dscore[v] = -dscore[v]; conf[v] = 0; age[v] = step;
    for (int i = 0; i < cdeg[v]; i++) {
        int u = nb[v][i], e = ne[v][i];
        if (!inC[u]) { dscore[u] += w[e]; conf[u] = 1; unc_add(e); }   /* edge now uncovered */
        else dscore[u] -= w[e];                                        /* u becomes sole cover */
    }
}
static void save(void) {
    if (n - csize > bsz) { bsz = 0; for (int v = 0; v < n; v++) if (!inC[v]) best[bsz++] = v; }
}

int main(void) {
    double tl; unsigned long long seed;
    if (scanf("%d %lf %llu", &n, &tl, &seed) != 3 || n > MAXN) return 1;
    rs = seed * 2654435761ULL + 88172645463325252ULL;
    for (int i = 0; i < n; i++) { int d, v; if (scanf("%d", &d) != 1) return 1; for (int k = 0; k < d; k++) { if (scanf("%d", &v) != 1) return 1; A[i][v] = A[v][i] = 1; } }
    m = 0; for (int i = 0; i < n; i++) for (int j = i + 1; j < n; j++) if (!A[i][j]) m++;
    eu = malloc(sizeof(int) * (m + 1)); ev = malloc(sizeof(int) * (m + 1)); w = malloc(sizeof(int) * (m + 1));
    unc = malloc(sizeof(int) * (m + 1)); upos = malloc(sizeof(int) * (m + 1));
    for (int i = 0; i < n; i++) cdeg[i] = 0;
    int k = 0; for (int i = 0; i < n; i++) for (int j = i + 1; j < n; j++) if (!A[i][j]) { eu[k] = i; ev[k] = j; w[k] = 1; cdeg[i]++; cdeg[j]++; k++; }
    for (int i = 0; i < n; i++) { nb[i] = malloc(sizeof(int) * (cdeg[i] + 1)); ne[i] = malloc(sizeof(int) * (cdeg[i] + 1)); cdeg[i] = 0; }
    for (int e = 0; e < m; e++) { int a = eu[e], b = ev[e]; nb[a][cdeg[a]] = b; ne[a][cdeg[a]++] = e; nb[b][cdeg[b]] = a; ne[b][cdeg[b]++] = e; }
    double t0 = now();
    /* initial cover: all edges uncovered; greedily add the vertex covering most uncovered edges */
    nunc = 0; for (int e = 0; e < m; e++) unc_add(e);
    for (int v = 0; v < n; v++) { dscore[v] = cdeg[v]; conf[v] = 1; age[v] = 0; inC[v] = 0; }
    csize = 0; long long step = 0;
    while (nunc) { int bv = 0; for (int v = 1; v < n; v++) if (!inC[v] && dscore[v] > dscore[bv]) bv = v; if (inC[bv]) break; add(bv, ++step); }
    /* drop redundant vertices (dscore 0: no edge covered by it alone) */
    for (int v = 0; v < n; v++) if (inC[v] && dscore[v] == 0) rem(v, ++step);
    save();
    if (m == 0) { printf("%d\n", n); for (int v = 0; v < n; v++) printf("%d ", v); printf("\n"); return 0; }
    long long wsum = m; const int gamma = n / 2; const double rho = 0.3;
    while ((step & 255) || now() - t0 < tl) {
        step++;
        if (nunc == 0) {                       /* a cover: record, then drop the vertex losing least */
            save();
            int bu = -1; for (int v = 0; v < n; v++) if (inC[v] && (bu < 0 || dscore[v] > dscore[bu])) bu = v;
            rem(bu, step); continue;
        }
        /* remove u in C: highest dscore, ties -> oldest */
        int u = -1; for (int v = 0; v < n; v++) if (inC[v] && (u < 0 || dscore[v] > dscore[u] || (dscore[v] == dscore[u] && age[v] < age[u]))) u = v;
        rem(u, step);
        /* add an endpoint of a random uncovered edge: conf-allowed, higher dscore, ties -> oldest */
        int e = unc[rnd() % nunc], a = eu[e], b = ev[e], v;
        if (!conf[a]) v = b; else if (!conf[b]) v = a;
        else v = (dscore[a] > dscore[b] || (dscore[a] == dscore[b] && age[a] < age[b])) ? a : b;
        add(v, step);
        /* weights of uncovered edges +1 */
        for (int i = 0; i < nunc; i++) { int f = unc[i]; w[f]++; dscore[eu[f]]++; dscore[ev[f]]++; }
        wsum += nunc;
        if (wsum >= (long long)gamma * m) {     /* forget: scale weights, recompute dscores */
            wsum = 0; for (int f = 0; f < m; f++) { w[f] = (int)(rho * w[f]); if (w[f] < 1) w[f] = 1; wsum += w[f]; }
            for (int x = 0; x < n; x++) dscore[x] = 0;
            for (int f = 0; f < m; f++) {
                int p = eu[f], q = ev[f];
                if (!inC[p] && !inC[q]) { dscore[p] += w[f]; dscore[q] += w[f]; }
                else if (inC[p] && !inC[q]) dscore[p] -= w[f];
                else if (!inC[p] && inC[q]) dscore[q] -= w[f];
            }
        }
    }
    printf("%d\n", bsz); for (int i = 0; i < bsz; i++) printf("%d ", best[i]); printf("\n");
    return 0;
}
