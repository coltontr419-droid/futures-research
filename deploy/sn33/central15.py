"""ReadyAI (SN33) miner patch: "central15" tagging (decisions.md §1185-§1186). Replaces only LlmLib.conversation_to_metadata in the MINER process:
ask the model for 25 candidate tags (specific topics/entities plus the conversation's broader themes), embed them with the backend's own embedding call
(text-embedding-3-large at 1,536 dimensions, as the validator scores), and return the 15 nearest their centroid. Coding conversations, short answers and
any error fall back to the stock method. Enrichment handling in ConversationTaggingTask.mine() is untouched.
"""

from __future__ import annotations

import os

import numpy as np

from conversationgenome.api.models.raw_metadata import RawMetadata
from conversationgenome.llm.LlmLib import LlmLib
from conversationgenome.utils.Utils import Utils

K = int(os.getenv("CENTRAL_K", "15"))
N_CANDIDATES = 25
PROMPT = ("Analyze conversation in terms of topic interests of the participants. Analyze the conversation (provided in structured XML format) where <p0> has "
          "the questions and <p1> has the answers. Return {n} comma-delimited lower-case tags: the specific topics and entities discussed, and also the broader "
          "themes the whole conversation is likely about. Only return the tags without any English commentary.\n\n\n\n{conv}")

_stock = LlmLib.conversation_to_metadata


def central_tags(cands: list[str], vectors: list) -> list[str]:
    pairs = [(t, np.asarray(v, dtype=float)) for t, v in zip(cands, vectors) if v]
    if len(pairs) < 3:
        return cands[:K]
    m = np.array([v for _, v in pairs]); centre = m.mean(axis=0)
    sims = m @ centre / (np.linalg.norm(m, axis=1) * np.linalg.norm(centre) + 1e-12)
    return [pairs[i][0] for i in np.argsort(-sims)[:K]]


FAST = {"reasoning_effort": "low", "service_tier": "priority"}


def _fast(self):
    """Low effort + priority tier for this instance's calls; returns the previous settings."""
    prev = {k: getattr(self, k, None) for k in FAST}
    for k, v in FAST.items():
        setattr(self, k, v)
    return prev


def conversation_to_metadata(self, conversation, generateEmbeddings=False):
    prev = _fast(self)
    try:
        return _central(self, conversation, generateEmbeddings)
    finally:
        for k, v in prev.items():
            setattr(self, k, v)


def _central(self, conversation, generateEmbeddings=False):
    try:
        if conversation.input_categories and "coding" in conversation.input_categories:
            return _stock(self, conversation, generateEmbeddings)
        convo_xml, _ = Utils.generate_convo_xml(conversation)
        response = self.basic_prompt(PROMPT.format(n=N_CANDIDATES, conv=convo_xml))
        cands = Utils.clean_tags(response.split(",")) if isinstance(response, str) else []
        cands = list(dict.fromkeys(cands))[:N_CANDIDATES]
        if len(cands) < 5 or not hasattr(self, "get_vector_embeddings_batch"):
            return _stock(self, conversation, generateEmbeddings)
        tags = central_tags(cands, self.get_vector_embeddings_batch(cands))
        vectors = self.get_vector_embeddings_set(tags) if generateEmbeddings else None
        return RawMetadata(tags=tags, vectors=vectors, success=True)
    except Exception:
        return _stock(self, conversation, generateEmbeddings)


LlmLib.conversation_to_metadata = conversation_to_metadata

# Parallel enrichment (§1201): same calls and combine step as ConversationTaggingTask.mine, the per-line calls run concurrently.
from concurrent.futures import ThreadPoolExecutor  # noqa: E402

from conversationgenome.llm.llm_factory import get_llm_backend  # noqa: E402
from conversationgenome.task.ConversationTaggingTask import ConversationTaggingTask  # noqa: E402
from conversationgenome.api.models.conversation import Conversation  # noqa: E402


async def _mine(self) -> dict:
    llml = get_llm_backend()
    conversation = Conversation(guid=self.input.guid, lines=self.input.data.window, miner_task_prompt=self.prompt_chain[0].prompt_template,
                                input_categories=self.input.input_categories)
    result = llml.conversation_to_metadata(conversation=conversation, generateEmbeddings=False)
    enrichment_lines = self.input.data.enrichment_lines or []
    if not enrichment_lines:
        return {"tags": result.tags, "vectors": result.vectors}
    prev = _fast(llml)
    try:
        call = lambda content: llml.enrichment_to_metadata(content, generateEmbeddings=False, input_categories=self.input.input_categories)
        with ThreadPoolExecutor(min(8, len(enrichment_lines))) as ex:
            outs = list(ex.map(call, [content for _, content in enrichment_lines]))
        all_tags = ([result.tags] if result and result.tags else []) + [o.tags for o in outs if o and o.tags]
        if not all_tags:
            return {"tags": result.tags, "vectors": result.vectors}
        combined = llml.combine_metadata_tags(all_tags, generateEmbeddings=False)
    finally:
        for k, v in prev.items():
            setattr(llml, k, v)
    if combined:
        return {"tags": combined.tags, "vectors": combined.vectors}
    return {"tags": result.tags, "vectors": result.vectors}


ConversationTaggingTask.mine = _mine
