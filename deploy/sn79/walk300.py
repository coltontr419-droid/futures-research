import importlib.util, argparse, tempfile, sys
sys.path.insert(0, "/opt/mvtrx/repo")
spec = importlib.util.spec_from_file_location("QAW", "/opt/mvtrx/agents/QuoteAgent.py"); mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
cfg = argparse.Namespace(size=0.036, skew=10.0, max_inv=0.3, edge=1, model="/opt/mvtrx/agents/model30_of.json", alpha_k=0.0, join=1, pull=0.0, max_units=40, lazy_load=1, lean=1, raw=1,
                         cancel_first=1, flow_pull=0, flow_win=10, flow_cool=3, data_dir=tempfile.mkdtemp(), pace_cap=450000, mk_vol_lad="2:5:10", mk_vol_inside=5)
A = mod.QuoteAgent(93, cfg, tempfile.mkdtemp()); B, S = mod.OrderDirection.BUY, mod.OrderDirection.SELL
class R:
    def __init__(s): s.instructions = []
    def limit_order(s, book_id, direction, quantity, price, **k): s.instructions.append(("place", direction, price))
    def cancel_order(s, book_id, oid): s.instructions.append(("cancel", oid, None))
class O:
    def __init__(s, i, side, price): s.id, s.side, s.price, s.quantity = i, side, price, 5.0
others_bid, others_ask = 299.00, 299.08; orders = []; nid = 0
for rnd in range(8):
    bid = max([others_bid] + [o.price for o in orders if o.side == B]); ask = min([others_ask] + [o.price for o in orders if o.side == S])
    want = {B: bid, S: ask}                         # join=1: the main path's target is the book's best = possibly OUR order
    r = R(); A._vol_ladder(r, 7, list(orders), want, {}, 5.0, 10.0, 0.01, 2, inside=5)
    for kind, a, p in r.instructions:
        if kind == "cancel": orders = [o for o in orders if o.id != a]
        else: nid += 1; orders.append(O(nid, a, p))
    print(f"round {rnd}: book best {bid:.2f}/{ask:.2f} spread {round((ask - bid) / 0.01)} ticks | our bids {sorted((o.price for o in orders if o.side == B), reverse=True)}")
