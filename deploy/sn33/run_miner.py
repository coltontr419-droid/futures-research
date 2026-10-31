"""Start the stock ReadyAI miner with the central15 patch applied (decisions.md §1186). Same arguments as neurons/miner.py.

Also throttles BaseMinerNeuron.sync to once per SYNC_SECONDS (decisions.md §1192): the stock run loop waits for
`block - metagraph.last_update[uid] >= epoch_length`, which is always true for a miner (miners never set weights), so it re-syncs the whole
metagraph back to back, ≈ 40% of a CPU core per miner. Only the run-loop thread calls sync(); requests are served by the axon and never wait on it."""

import os
import runpy
import sys
import time

sys.path.insert(0, "/opt/readyai")
import central15  # noqa: E402,F401  (patches LlmLib.conversation_to_metadata)

sys.path.insert(0, "/opt/readyai/repo")
from conversationgenome.base.miner import BaseMinerNeuron  # noqa: E402

SYNC_SECONDS = float(os.getenv("SYNC_SECONDS", "300"))
_sync = BaseMinerNeuron.sync


def sync(self):
    while not self.should_exit and time.time() - getattr(self, "_last_sync", 0.0) < SYNC_SECONDS:
        time.sleep(1)
    self._last_sync = time.time()
    return _sync(self)


BaseMinerNeuron.sync = sync

# OpenAI usage log (decisions.md §1192): one line per call with the tokens OpenAI reports, for the cost-per-task measurement.
USAGE_LOG = os.getenv("USAGE_LOG", "")
if USAGE_LOG:
    import json
    import threading

    from openai.resources.chat.completions import Completions
    from openai.resources.embeddings import Embeddings

    _lock = threading.Lock()

    def _logged(create, kind):
        def wrapper(self, *args, **kwargs):
            resp = create(self, *args, **kwargs)
            try:
                u = resp.usage
                row = {"t": int(time.time()), "kind": kind, "model": kwargs.get("model", ""), "in": getattr(u, "prompt_tokens", 0),
                       "out": getattr(u, "completion_tokens", 0) or 0}
                with _lock, open(USAGE_LOG, "a") as f:
                    f.write(json.dumps(row) + "\n")
            except Exception:
                pass
            return resp
        return wrapper

    Completions.create = _logged(Completions.create, "chat")
    Embeddings.create = _logged(Embeddings.create, "embed")

# Task log (decisions.md §1198): every task's input and our answer, per task type, to build a lab for the non-tagging types.
TASK_LOG = os.getenv("TASK_LOG", "")
if TASK_LOG:
    import importlib
    import json
    import threading

    _tlock = threading.Lock()
    for _mod, _cls in (("ConversationTaggingTask", "ConversationTaggingTask"), ("SkillGenerationTask", "SkillGenerationTask"),
                       ("SkillCoverageEvaluationTask", "SkillCoverageEvaluationTask"), ("NamedEntitiesExtrationTask", "NamedEntitiesExtractionTask"),
                       ("WebpageMetadataGenerationTask", "WebpageMetadataGenerationTask"), ("SurveyTaggingTask", "SurveyTaggingTask")):
        try:
            cls = getattr(importlib.import_module(f"conversationgenome.task.{_mod}"), _cls)
        except Exception:
            continue

        def _wrap(orig):
            async def mine(self):
                out = await orig(self)
                try:
                    row = {"t": int(time.time()), "type": getattr(self, "type", ""), "input": self.input.model_dump(mode="json") if self.input else None,
                           "output": out}
                    with _tlock, open(TASK_LOG, "a") as f:
                        f.write(json.dumps(row, default=str) + "\n")
                except Exception:
                    pass
                return out
            return mine
        cls.mine = _wrap(cls.mine)

runpy.run_path("/opt/readyai/repo/neurons/miner.py", run_name="__main__")
