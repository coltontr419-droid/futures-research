"""Start the stock ReadyAI miner with the central15 patch applied (decisions.md §1186). Same arguments as neurons/miner.py."""

import runpy
import sys

sys.path.insert(0, "/opt/readyai")
import central15  # noqa: E402,F401  (patches LlmLib.conversation_to_metadata)

sys.path.insert(0, "/opt/readyai/repo")
runpy.run_path("/opt/readyai/repo/neurons/miner.py", run_name="__main__")
