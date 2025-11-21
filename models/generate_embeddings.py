from typing import List

import litellm
from openai import OpenAI
from qdrant_client.http import models as qm

from settings import senv

logger = senv.backend_logger


class EmbeddingGenerator:
    def __init__(self) -> None:
        self.client = OpenAI()

    def generate_dense_vector(self, text: str) -> List:
        if not text:
            raise ValueError("text is required")
        try:
            response = self.client.embeddings.create(
                input=text, model=senv.EMBEDDING_MODEL
            )
            return response.data[0].embedding
        except Exception as e:
            logger.error("Dense embedding failed: %s", e)
            return []

    def generate_sparse_vector(self, text: str) -> qm.SparseVector | dict:
        if not text:
            logger.error("text is required")
            return {}
        try:
            response = litellm.embedding(
                model="litellm_proxy/" + senv.SPARSE_EMBEDDING_MODEL,
                input=[text],
                api_base=senv.LITELLM_PROXY_URL,
                api_key=senv.LITELLM_PROXY_API_KEY,
            )
            res = response.data[0]["embedding"]
            return qm.SparseVector(
                indices=list(map(int, res.keys())),
                values=list(map(float, res.values())),
            )
        except Exception as e:
            logger.error("Sparse embedding failed: %s", e)
            return {}
