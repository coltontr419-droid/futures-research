p = "/opt/tag101/repo/tasks/ourtags.py"; s = open(p).read()
assert "PROMPT_MODES" not in s
a = '''def _entity_tags(post: str, n: int) -> list[str]:'''
b = '''# Bench families (§1211 add. 13): six LLM post-specific styles all landed ≈ 0.3 below the median live, so test families outside that style.
PROMPT_MODES = {
    "generic": ("Classify a social post from an AI-focused account into {n} broad topic categories, 1-3 words each, the kind of general "
                "category names many posts share (for example: artificial intelligence, ai agents, large language models, startups, "
                "open source, robotics). Prefer widely used category names over details specific to this post. Return only a JSON array of "
                "lower-case strings.\\nOutput exactly {n} tags.\\n"),
    "keywords": ("Give the {n} most important single-word keywords of a social post (one word each, no phrases). Return only a JSON array of "
                 "lower-case strings.\\nOutput exactly {n} tags.\\n"),
}


def _prompt_tags(post: str, n: int, system: str) -> list[str]:
    m = base.ReferenceMiner(n_tags=n, timeout_sec=int(base.SN101_TIME_LIMIT))
    payload = {"model": m.model, "messages": [{"role": "system", "content": system.format(n=n)},
                                              {"role": "user", "content": ENTITY_USER.format(post=post.strip())}]}
    return list(dict.fromkeys(str(t).strip().lower() for t in m._parse_tags(m._call_chat_completions(payload)) if str(t).strip()))[:n]


def _hashtag_tags(post: str, n: int) -> list[str]:
    """Literal hashtags, @handles and $tickers from the post (in order), topped up with the entity prompt's named entities."""
    text = re.sub(r"^RT @\\w+:\\s*", "", post)
    found = [x.lower() for x in re.findall(r"[#@$]([A-Za-z][\\w.]{1,30})", text)]
    out = list(dict.fromkeys(found))[:n]
    if len(out) < n:
        for t in _entity_tags(post, n):
            t = str(t).strip().lower()
            if t and t not in out:
                out.append(t)
            if len(out) >= n:
                break
    return out[:n]


''' + a
assert s.count(a) == 1; s = s.replace(a, b)
a2 = '''    if MODE == "verbatim":'''
b2 = '''    if MODE in PROMPT_MODES or MODE == "hashtag":
        try:
            tags = _hashtag_tags(post, k) if MODE == "hashtag" else _prompt_tags(post, k, PROMPT_MODES[MODE])
        except Exception:
            tags = []
        if len(tags) >= k:
            _log(post, [MODE], tags)
            return {"tags": tags}
        return base.solve_problem(envelope, chain_runtime)
''' + a2
assert s.count(a2) == 1; s = s.replace(a2, b2); open(p, "w").write(s); print("patched")
