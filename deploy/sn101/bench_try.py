import json, os, sys
sys.path.insert(0, "/opt/tag101")
os.environ["TAG_MODE"] = sys.argv[1]
from tag101.tasks import ourtags as T
posts = [json.loads(l)["post"] for l in open("/opt/tag101/posts_m3v.jsonl")][-4:]
k = 3
for p in posts:
    f = T._hashtag_tags(p, k) if sys.argv[1] == "hashtag" else T._prompt_tags(p, k, T.PROMPT_MODES[sys.argv[1]])
    print(sys.argv[1], "|", p[:70].replace("\n", " "), "->", f)
