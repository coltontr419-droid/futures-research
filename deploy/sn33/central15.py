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


def conversation_to_metadata(self, conversation, generateEmbeddings=False):
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
