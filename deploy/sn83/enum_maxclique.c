/* Enumerate all cliques of size W (the known maximum) in a graph (decisions.md §1213): bitset branch-and-bound with greedy-colouring bound
   (Tomita MCQ). Input on stdin: n m W cap seconds, then m edges "u v". Output: "COUNT c COMPLETE 0|1 TIME s" then up to `cap` cliques (one
   per line, reservoir-sampled if more), plus per-vertex frequency over ALL enumerated cliques ("FREQ f0 f1 ..."). */
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <time.h>
#define MAXN 1024
#define WORDS (MAXN / 64)
typedef struct { uint64_t w[WORDS]; } bs;
static int n, W, cap, nw; static double tlim; static bs adj[MAXN];
static long long cnt = 0; static int complete = 1; static clock_t t0;
static int R[MAXN]; static int **samp; static long long freq[MAXN];
static unsigned long long rng = 88172645463325252ULL;
static unsigned long long xr(void) { rng ^= rng << 13; rng ^= rng >> 7; rng ^= rng << 17; return rng; }
static inline int popc(const bs *a) { int c = 0; for (int i = 0; i < nw; i++) c += __builtin_popcountll(a->w[i]); return c; }
static void expand(int rs, bs *P) {
    if ((cnt & 1023) == 0 && (double)(clock() - t0) / CLOCKS_PER_SEC > tlim) { complete = 0; return; }
    if (rs == W) {
        for (int i = 0; i < W; i++) freq[R[i]]++;
        if (cnt < cap) memcpy(samp[cnt], R, sizeof(int) * W);
        else { long long j = xr() % (cnt + 1); if (j < cap) memcpy(samp[j], R, sizeof(int) * W); }
        cnt++; return;
    }
    /* greedy colouring of P */
    int order[MAXN], col[MAXN], k = 0, c = 0; bs U = *P;
    while (popc(&U)) {
        c++; bs Q = U;
        for (int i = 0; i < nw; i++) while (Q.w[i]) {
            int b = __builtin_ctzll(Q.w[i]), v = i * 64 + b;
            U.w[i] &= ~(1ULL << b); Q.w[i] &= ~(1ULL << b);
            for (int j = 0; j < nw; j++) Q.w[j] &= ~adj[v].w[j];
            order[k] = v; col[k] = c; k++;
        }
    }
    for (int idx = k - 1; idx >= 0; idx--) {
        if (rs + col[idx] < W) return;
        int v = order[idx]; R[rs] = v;
        bs NP; for (int j = 0; j < nw; j++) NP.w[j] = P->w[j] & adj[v].w[j];
        expand(rs + 1, &NP);
        if (!complete) return;
        P->w[v / 64] &= ~(1ULL << (v % 64));
    }
}
int main(void) {
    int m; if (scanf("%d %d %d %d %lf", &n, &m, &W, &cap, &tlim) != 5) return 1;
    nw = (n + 63) / 64;
    for (int i = 0; i < m; i++) { int u, v; if (scanf("%d %d", &u, &v) != 2) return 1; adj[u].w[v / 64] |= 1ULL << (v % 64); adj[v].w[u / 64] |= 1ULL << (u % 64); }
    samp = malloc(sizeof(int *) * cap); for (int i = 0; i < cap; i++) samp[i] = malloc(sizeof(int) * W);
    bs P; memset(&P, 0, sizeof P); for (int v = 0; v < n; v++) P.w[v / 64] |= 1ULL << (v % 64);
    t0 = clock(); expand(0, &P);
    printf("COUNT %lld COMPLETE %d TIME %.3f\n", cnt, complete, (double)(clock() - t0) / CLOCKS_PER_SEC);
    long long k = cnt < cap ? cnt : cap;
    for (long long i = 0; i < k; i++) { for (int j = 0; j < W; j++) printf("%d ", samp[i][j]); printf("\n"); }
    printf("FREQ"); for (int v = 0; v < n; v++) printf(" %lld", freq[v]); printf("\n");
    return 0;
}
