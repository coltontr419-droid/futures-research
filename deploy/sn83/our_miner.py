"""CliqueAI (SN83) miner with our solver portfolio (decisions.md §1195). Replaces Miner.forward_graph only: decode the graph, solve it
once per graph (cached by encoded matrix, shared by every UID on this box through a small file cache), and hand each of our UIDs a
DIFFERENT maximum clique (index = this hotkey's position among our hotkeys) so our own UIDs never split diversity credit.

    python our_miner.py <stock CliqueAI miner arguments>   (env: CLIQUE_CORES, CLIQUE_RESTARTS, CLIQUE_FRAC, CLIQUE_SLOT, CLIQUE_CACHE)
"""

import asyncio
import hashlib
import json
import os
import sys
import time

sys.path.insert(0, "/opt/clique/repo")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bittensor as bt  # noqa: E402
from CliqueAI.graph.codec import GraphCodec  # noqa: E402
from CliqueAI.miner import Miner  # noqa: E402

import portfolio  # noqa: E402

CORES = int(os.getenv("CLIQUE_CORES", "4"))
RESTARTS = int(os.getenv("CLIQUE_RESTARTS", "8"))
FRAC = float(os.getenv("CLIQUE_FRAC", "0.5"))          # share of the synapse timeout spent solving
SLOT = int(os.getenv("CLIQUE_SLOT", "0"))              # this UID's index among our UIDs on the box
CACHE = os.getenv("CLIQUE_CACHE", "/opt/clique/cache")


def _cached_solve(key: str, n: int, adj, budget: float) -> list:
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, key + ".json"); lock = path + ".lock"
    for _ in range(int(budget * 10) + 20):              # another of our UIDs may be solving this graph right now
        if os.path.exists(path):
            return json.load(open(path))
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL); os.close(fd); break
        except FileExistsError:
            time.sleep(0.1)
    cliques = [list(c) for c in portfolio.solve(n, adj, budget, CORES, RESTARTS, int(key[:8], 16))]
    json.dump(cliques, open(path + ".tmp", "w")); os.replace(path + ".tmp", path)
    return cliques


async def forward_graph(self, synapse):
    codec = GraphCodec()
    adj = codec.matrix_to_list(codec.decode_matrix(synapse.encoded_matrix))
    key = hashlib.sha256(synapse.encoded_matrix.encode()).hexdigest()[:32]
    budget = FRAC * float(getattr(synapse, "timeout", None) or 10.0)
    cliques = await asyncio.get_running_loop().run_in_executor(None, _cached_solve, key, synapse.number_of_nodes, adj, budget)
    synapse.maximum_clique = cliques[SLOT % len(cliques)] if cliques else []
    bt.logging.info(f"clique size {len(synapse.maximum_clique)} (distinct best {len(cliques)}, slot {SLOT}) n={synapse.number_of_nodes}")
    return synapse


Miner.forward_graph = forward_graph

if __name__ == "__main__":
    with Miner() as miner:
        while not miner.should_exit:
            time.sleep(1)
