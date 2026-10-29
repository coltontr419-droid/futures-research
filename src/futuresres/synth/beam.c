/* Max clique by randomised beam search over (clique, candidate set) states, restarted from high-degree vertices; the method public SN83
   miners use (score = neighbours inside the candidate set), in C with bitsets. Wall-clock limited. decisions.md §1165.
   stdin:  n time_limit_seconds seed [beam_width], then n lines "deg v1 v2 ..." (0-based)
   stdout: clique size, then its vertices (always maximal: a state ends only when no candidate is left). */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <time.h>

#define MAXN 1024
#define MW (MAXN / 64)
#define MAXB 64
static int n, W, BW = 8;
static uint64_t adj[MAXN][MW];
static unsigned long long rs;
static inline unsigned rnd(void) { rs ^= rs << 13; rs ^= rs >> 7; rs ^= rs << 17; return (unsigned)rs; }
static double now(void) { struct timespec t; clock_gettime(CLOCK_MONOTONIC, &t); return t.tv_sec + t.tv_nsec * 1e-9; }
static inline int pc(const uint64_t *a) { int c = 0; for (int w = 0; w < W; w++) c += __builtin_popcountll(a[w]); return c; }
static inline int pc_and(const uint64_t *a, const uint64_t *b) { int c = 0; for (int w = 0; w < W; w++) c += __builtin_popcountll(a[w] & b[w]); return c; }

typedef struct { int cl[MAXN], sz; uint64_t cand[MW]; int ccount; } State;
static State beamA[MAXB], beamB[MAXB * MAXB];
static int best[MAXN], bsz;

static void run_from(int start) {
    int nb = 1; State *s = &beamA[0]; s->sz = 1; s->cl[0] = start; memcpy(s->cand, adj[start], sizeof(uint64_t) * W); s->ccount = pc(s->cand);
    while (nb) {
        int nn = 0;
        for (int b = 0; b < nb; b++) {
            State *st = &beamA[b];
            if (st->ccount == 0) { if (st->sz > bsz) { bsz = st->sz; memcpy(best, st->cl, sizeof(int) * st->sz); } continue; }
            /* score candidates; keep the top 10, shuffled, then take BW of them */
            int top[10], topsc[10], nt = 0;
            for (int w = 0; w < W; w++) for (uint64_t x = st->cand[w]; x; x &= x - 1) {
                int u = w * 64 + __builtin_ctzll(x), c = pc_and(adj[u], st->cand);
                if (nt < 10) { top[nt] = u; topsc[nt++] = c; }
                else { int mi = 0; for (int i = 1; i < 10; i++) if (topsc[i] < topsc[mi]) mi = i; if (c > topsc[mi]) { top[mi] = u; topsc[mi] = c; } }
            }
            for (int i = nt - 1; i > 0; i--) { int j = rnd() % (i + 1), t = top[i]; top[i] = top[j]; top[j] = t; }
            for (int i = 0; i < nt && i < BW; i++) {
                State *c = &beamB[nn++]; int v = top[i];
                memcpy(c->cl, st->cl, sizeof(int) * st->sz); c->sz = st->sz; c->cl[c->sz++] = v;
                for (int w = 0; w < W; w++) c->cand[w] = st->cand[w] & adj[v][w];
                c->ccount = pc(c->cand);
                if (c->sz > bsz && c->ccount == 0) { bsz = c->sz; memcpy(best, c->cl, sizeof(int) * c->sz); }
            }
        }
        /* keep the BW children with most candidates (random tie order) */
        for (int i = nn - 1; i > 0; i--) { int j = rnd() % (i + 1); State t = beamB[i]; beamB[i] = beamB[j]; beamB[j] = t; }
        int keep = nn < BW ? nn : BW;
        for (int k = 0; k < keep; k++) { int bi = k; for (int i = k + 1; i < nn; i++) if (beamB[i].ccount > beamB[bi].ccount) bi = i; State t = beamB[k]; beamB[k] = beamB[bi]; beamB[bi] = t; beamA[k] = beamB[k]; }
        nb = keep;
    }
}

int main(void) {
    double tl; unsigned long long seed;
    if (scanf("%d %lf %llu", &n, &tl, &seed) != 3 || n > MAXN) return 1;
    char *bw = getenv("BEAM"); if (bw) BW = atoi(bw); if (BW > MAXB) BW = MAXB;
    rs = seed * 2654435761ULL + 88172645463325252ULL; W = (n + 63) / 64;
    for (int i = 0; i < n; i++) { int d, v; if (scanf("%d", &d) != 1) return 1; for (int k = 0; k < d; k++) { if (scanf("%d", &v) != 1) return 1; adj[i][v >> 6] |= 1ULL << (v & 63); } }
    int deg[MAXN], order[MAXN]; for (int v = 0; v < n; v++) { deg[v] = pc(adj[v]); order[v] = v; }
    for (int i = 0; i < n; i++) for (int j = i + 1; j < n; j++) if (deg[order[j]] > deg[order[i]]) { int t = order[i]; order[i] = order[j]; order[j] = t; }
    double t0 = now(); int k = 0;
    while (now() - t0 < tl) {
        int start = (k < n / 3) ? order[k] : order[rnd() % n];   /* first the top third by degree, then random */
        run_from(start); k++;
    }
    printf("%d\n", bsz); for (int i = 0; i < bsz; i++) printf("%d ", best[i]); printf("\n");
    return 0;
}
