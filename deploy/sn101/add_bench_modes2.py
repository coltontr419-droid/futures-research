p = "/opt/tag101/repo/tasks/ourtags.py"; s = open(p).read()
assert '"genre"' not in s
a = '''    "keywords": ('''
b = '''    "genre": ("Label a social post from an AI-focused account with {n} short tags for what KIND of post it is (for example: product launch, "
              "research paper, benchmark result, opinion, tutorial, event announcement, hiring, funding news, open source release). Return only "
              "a JSON array of lower-case strings.\\nOutput exactly {n} tags.\\n"),
    "summary": ("Describe what a social post is about with {n} descriptive phrases of 3-6 words each. Return only a JSON array of lower-case "
                "strings.\\nOutput exactly {n} tags.\\n"),
''' + a
assert s.count(a) == 1; s = s.replace(a, b)
a2 = '''    if MODE in PROMPT_MODES or MODE == "hashtag":'''
b2 = '''    if MODE == "fixed":                                # the same broad set for every post: tests whether the consensus is post-independent
        tags = ["artificial intelligence", "machine learning", "large language models"][:k]
        _log(post, ["fixed"], tags)
        return {"tags": tags}
''' + a2
assert s.count(a2) == 1; s = s.replace(a2, b2); open(p, "w").write(s); print("patched")
