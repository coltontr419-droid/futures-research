/* DLS-MC (Pullan & Hoos 2006) maximum-clique local search, wall-clock limited. decisions.md §1165.
   stdin:  n time_limit_seconds seed, then n lines "deg v1 v2 ..." (adjacency lists, 0-based)
   stdout: size, then the clique's vertices (0-based). */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <time.h>

#define MAXN 1024
static int n, W;
static uint64_t adj[MAXN][MAXN / 64];
static int incl[MAXN], miss[MAXN], pen[MAXN], cl[MAXN], csz, best[MAXN], bsz;
static unsigned long long rs;
static inline unsigned rnd(void) { rs ^= rs << 13; rs ^= rs >> 7; rs ^= rs << 17; return (unsigned)rs; }
static inline int isadj(int a, int b) { return (adj[a][b >> 6] >> (b & 63)) & 1; }
static double now(void) { struct timespec t; clock_gettime(CLOCK_MONOTONIC, &t); return t.tv_sec + t.tv_nsec * 1e-9; }

static void add(int v) {                       /* every non-neighbour of v gains one missing link */
    incl[v] = 1; cl[csz++] = v;
    for (int u = 0; u < n; u++) if (u != v && !isadj(u, v)) miss[u]++;
}
static void del(int v) {
    incl[v] = 0;
    for (int i = 0; i < csz; i++) if (cl[i] == v) { cl[i] = cl[--csz]; break; }
    for (int u = 0; u < n; u++) if (u != v && !isadj(u, v)) miss[u]--;
}
static void clear(void) { while (csz) del(cl[csz - 1]); }
static void save(void) { if (csz > bsz) { bsz = csz; memcpy(best, cl, sizeof(int) * csz); } }

static int pick(int want, int *lastswap) {   /* not-in-clique vertex with miss == want, minimum penalty, random tie */
    int bv = -1, bp = 1 << 30, ties = 0;
    for (int v = 0; v < n; v++) {
        if (incl[v] || miss[v] != want || v == *lastswap) continue;
        if (pen[v] < bp) { bp = pen[v]; bv = v; ties = 1; }
        else if (pen[v] == bp && rnd() % (++ties) == 0) bv = v;
    }
    return bv;
}

int main(void) {
    double tl; unsigned long long seed;
    if (scanf("%d %lf %llu", &n, &tl, &seed) != 3 || n > MAXN) return 1;
    rs = seed * 2654435761ULL + 88172645463325252ULL; W = (n + 63) / 64;
    for (int i = 0; i < n; i++) { int d, v; if (scanf("%d", &d) != 1) return 1; for (int k = 0; k < d; k++) { if (scanf("%d", &v) != 1) return 1; adj[i][v >> 6] |= 1ULL << (v & 63); } }
    double t0 = now(); int pd = 2, cycles = 0, lastswap = -1;
    add(rnd() % n);
    while (now() - t0 < tl) {
        /* expand + plateau */
        int plateau_left = 50; int start_overlap_ref[MAXN]; int ref_sz = 0;
        for (;;) {
            int v = pick(0, &lastswap);
            if (v >= 0) { add(v); continue; }
            if (ref_sz == 0) { ref_sz = csz; memcpy(start_overlap_ref, cl, sizeof(int) * csz); }
            if (plateau_left-- <= 0) break;
            v = pick(1, &lastswap);
            if (v < 0) break;
            int out = -1;                          /* the one clique member v is not adjacent to */
            for (int i = 0; i < csz; i++) if (!isadj(v, cl[i])) { out = cl[i]; break; }
            del(out); add(v); lastswap = out;
            int overlap = 0; for (int i = 0; i < ref_sz; i++) overlap |= incl[start_overlap_ref[i]];
            if (!overlap) break;
        }
        save();
        /* penalties */
        for (int i = 0; i < csz; i++) pen[cl[i]]++;
        if (++cycles % pd == 0) for (int v = 0; v < n; v++) if (pen[v]) pen[v]--;
        /* perturb: keep the neighbours of a random vertex (pd > 1), else restart from it */
        int v = rnd() % n;
        if (pd > 1) {
            int keep[MAXN], k = 0;
            for (int i = 0; i < csz; i++) if (cl[i] != v && isadj(v, cl[i])) keep[k++] = cl[i];
            clear(); for (int i = 0; i < k; i++) add(keep[i]); if (!incl[v]) add(v);
        } else { clear(); add(v); }
        lastswap = -1;
    }
    printf("%d\n", bsz); for (int i = 0; i < bsz; i++) printf("%d ", best[i]); printf("\n");
    return 0;
}
