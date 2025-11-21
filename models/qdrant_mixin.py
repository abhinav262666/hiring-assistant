# models/qdrant_mixin.py  (concise, ready to paste)
from typing import Any, Dict, List, Optional
import logging
import time
import uuid
from random import random

from mongoengine import signals
from qdrant_client.http import models as qm
import qdrant_client.http.exceptions as qdr_ex

from models.generate_embeddings import EmbeddingGenerator
from settings import senv

logger = senv.backend_logger

# ────────────────────────────────────────────────────────────────────────────
# tiny retry helper (exponential back-off + jitter)
# ────────────────────────────────────────────────────────────────────────────

_TRANSIENT = (
    qdr_ex.ResponseHandlingException,
    ConnectionError,
    OSError,
)

def _with_retries(fn, *args, max_tries: int = 5, base_delay: float = 1.0, **kwargs):
    """
    Call `fn(*args, **kwargs)` with retries on known transient Qdrant / HTTPX errors.
    Delays: 1 s · 2 s · 4 s · 8 s · 16 s (±30 % jitter).
    """
    for attempt in range(1, max_tries + 1):
        try:
            return fn(*args, **kwargs)
        except _TRANSIENT as e:
            if attempt == max_tries:
                raise
            sleep_for = base_delay * (2 ** (attempt - 1)) * (0.7 + 0.6 * random())
            logger.warning(
                "Qdrant transient error (%s) – retry %d/%d in %.1fs",
                type(e).__name__,
                attempt,
                max_tries,
                sleep_for,
            )
            time.sleep(sleep_for)

class QdrantMixin:
    """
    Mixin to be used with MongoEngine DynamicDocument / Document.
    Expectation on models:
      - class attribute `qdrant_collection` (optional). If absent, uses meta.collection or class name.
      - class attribute `payload_fields` (list[str]) specifying fields to store in payload.
      - class attribute `dense_embed_fields` (list[str]) specifying fields to combine for dense embed.
      - class attribute `sparse_embed_fields` (list[str]) specifying fields to combine for sparse embed.
    """

    # MongoEngine signal handlers for automatic sync
    @classmethod
    def register_signals(cls):
        """Register MongoEngine signals for automatic Qdrant sync."""
        signals.post_save.connect(cls._on_post_save, sender=cls)
        signals.post_delete.connect(cls._on_post_delete, sender=cls)

    # NOTE: QuerySet.update() and bulk operations do NOT trigger post_save signals.
    # For bulk updates that require Qdrant sync, you must:
    # 1. Use instance.save() for individual updates, or
    # 2. Manually re-upsert affected documents, or
    # 3. Run a periodic reindex job

    @classmethod
    def patch_queryset_update(cls):
        """
        Monkeypatch QuerySet.update() to trigger Qdrant re-sync for affected documents.
        WARNING: This can be expensive for large bulk updates.
        """
        from mongoengine.queryset import QuerySet
        original_update = QuerySet.update

        def patched_update(self, *args, **kwargs):
            affected_ids = cls._get_affected_ids_before_update(self)
            result = original_update(self, *args, **kwargs)
            cls._resync_affected_documents(self, affected_ids)
            return result

        QuerySet.update = patched_update
        logger.info("Patched QuerySet.update() for QdrantMixin models")

    @classmethod
    def _get_affected_ids_before_update(cls, queryset):
        """Get IDs of documents that will be affected by update."""
        if not (hasattr(queryset, '_document_class') and issubclass(queryset._document_class, QdrantMixin)):
            return []

        try:
            affected_docs = list(queryset.only('id'))
            return [str(doc.id) for doc in affected_docs]
        except Exception:
            return []

    @classmethod
    def _resync_affected_documents(cls, queryset, affected_ids):
        """Re-sync affected documents to Qdrant after bulk update."""
        if not affected_ids:
            return

        try:
            for doc_id in affected_ids:
                updated_doc = queryset._document_class.objects(id=doc_id).first()
                if updated_doc:
                    updated_doc.upsert_data_point()
        except Exception as e:
            logger.warning("Failed to re-sync Qdrant after bulk update: %s", e)

    @classmethod
    def _on_post_save(cls, sender, document, **kwargs):
        """Handle post-save signal to upsert to Qdrant."""
        if isinstance(document, QdrantMixin):
            try:
                document.upsert_data_point()
            except Exception as e:
                logger.exception("Failed to upsert document to Qdrant on save: %s", e)

    @classmethod
    def _on_post_delete(cls, sender, document, **kwargs):
        """Handle post-delete signal to remove from Qdrant."""
        if isinstance(document, QdrantMixin):
            try:
                document.delete_data_point()
            except Exception as e:
                logger.exception("Failed to delete document from Qdrant on delete: %s", e)

 
    @property
    def embed_gen(self):
        if not hasattr(self, "_embed_gen"):
            self._embed_gen = EmbeddingGenerator()
        return self._embed_gen

    # -------------------- Qdrant client access --------------------
    def get_qdrant_client(self):
        """Return the global Qdrant client from settings (raises if not initialized)."""
        if getattr(senv, "qdrant_client", None) is None:
            raise RuntimeError("Qdrant client not initialized. Initialize senv.qdrant_client on startup.")
        return senv.qdrant_client

    # -------------------- ID / collection helpers --------------------
    def _point_id(self) -> str:
        """
        Stable point id to use in Qdrant. Uses MongoEngine object's id (stringified).
        """
        return str(getattr(self, "id"))

    @classmethod
    def _collection_name_for_class(cls) -> str:
        return getattr(cls, "qdrant_collection", None) or getattr(cls, "meta", {}).get("collection", cls.__name__.lower()) 

    def _collection_name(self) -> str:
        # instance-level override: allow instance to choose per-org collections if desired
        if getattr(self, "qdrant_collection", None):
            return self.qdrant_collection
        # allow instance-level per-org naming (optional, safe to override)
        if hasattr(self, "org") and getattr(self, "org", None) is not None:
            # comment: change this pattern if you prefer different per-org naming
            base = self._collection_name_for_class()
            return f"{base}__org__{str(getattr(self, 'org').id)}"
        return self._collection_name_for_class()

    # -------------------- Payload builder --------------------
    def _build_payload(self) -> Dict[str, Any]:
        """
        Build a JSON-serializable payload from `payload_fields`.
        Converts ReferenceField-like objects to string ids.
        Always includes `_id` and `_collection`.
        """
        payload: Dict[str, Any] = {}
        fields = getattr(self, "payload_fields", None)
        # default: include a small set if user did not provide payload_fields
        if not fields:
            fields = [k for k in getattr(self, "_fields", {}).keys() if k not in ("id",)]
        for f in fields:
            try:
                v = getattr(self, f, None)
                # convert referenced documents to their id string
                if v is None:
                    payload[f] = None
                elif hasattr(v, "id"):
                    payload[f] = str(getattr(v, "id"))
                else:
                    payload[f] = v
            except Exception:
                # best-effort; avoid failing the whole payload build
                logger.debug("Failed to read field %s for payload on %s", f, type(self).__name__)
                payload[f] = None
        # always include doc id and collection marker
        payload["_id"] = self._point_id()
        payload["_collection"] = self._collection_name_for_class()
        return payload

    # -------------------- Embedding builders --------------------
    def _dense_text_for_embedding(self) -> str:
        """Concatenate configured dense_embed_fields into a single text blob for dense embedder."""
        fields = getattr(self, "dense_embed_fields", None) or []
        parts: List[str] = []
        for f in fields:
            v = getattr(self, f, None)
            if isinstance(v, list):
                parts.append(" ".join(map(str, v)))
            elif v:
                parts.append(str(v))
        return " ".join(parts).strip()

    def _sparse_text_for_embedding(self) -> str:
        """Concatenate configured sparse_embed_fields into a single string for sparse embedder."""
        fields = getattr(self, "sparse_embed_fields", None) or []
        parts: List[str] = []
        for f in fields:
            v = getattr(self, f, None)
            if isinstance(v, list):
                parts.append(" ".join(map(str, v)))
            elif v:
                parts.append(str(v))
        return " ".join(parts).strip()

    def _build_dense_vector(self) -> Optional[List[float]]:
        """Call your embedding generator to get a dense vector (or None)."""
        text = self._dense_text_for_embedding()
        if not text:
            return None
        try:
            vec = self.embed_gen.generate_dense_vector(text)
            # sanitize: ensure list of floats
            if not isinstance(vec, list):
                return None
            return [float(x) for x in vec]
        except Exception as e:
            logger.exception("Dense embedding generation failed: %s", e)
            return None

    def _build_sparse_vector(self) -> Optional[qm.SparseVector]:
        """Call your embedding generator to get a sparse vector (qm.SparseVector) or None."""
        text = self._sparse_text_for_embedding()
        if not text:
            return None
        try:
            res = self.embed_gen.generate_sparse_vector(text)
            # Expect either qm.SparseVector or dict-like {index: value}
            if isinstance(res, qm.SparseVector):
                return res
            if isinstance(res, dict):
                # convert keys and values to the types expected by qm.SparseVector
                indices = list(map(int, res.keys()))
                values = list(map(float, res.values()))
                return qm.SparseVector(indices=indices, values=values)
            # fallback: nothing usable
            logger.debug("Sparse embedder returned unsupported type %s", type(res))
            return None
        except Exception as e:
            logger.exception("Sparse embedding generation failed: %s", e)
            return None

    # -------------------- Ensure collection --------------------
    def _ensure_collection(self) -> None:
        """
        Ensure a Qdrant collection exists with settings for dense and sparse vectors.
        This is best-effort: if the collection already exists, creation attempts are ignored.
        """
        client = self.get_qdrant_client()
        coll = self._collection_name()
        try:
            # get_collection can raise if not exists; we try to create if missing
            try:
                client.get_collection(collection_name=coll)
            except Exception:
                # create collection with dense and sparse vector configs
                client.create_collection(
                    collection_name=coll,
                    vectors_config={
                        "text-dense": qm.VectorParams(
                            size=senv.DENSE_VECTOR_SIZE,  # OpenAI Embeddings
                            distance=qm.Distance.COSINE,
                        )
                    },
                    sparse_vectors_config={
                        "text-sparse": qm.SparseVectorParams(
                            index=qm.SparseIndexParams(
                                on_disk=False,
                            )
                        )
                    },
                )
                logger.debug("Created qdrant collection %s with dense and sparse vector configs", coll)
        except Exception as e:
            # non-fatal: log and continue (collection may already exist or creation failed)
            logger.exception("Failed to ensure collection %s: %s", coll, e)

    # -------------------- Upsert / Delete --------------------
    def upsert_data_point(self) -> bool:
        """
        Build payload + vectors and upsert to Qdrant.
        Returns True on success, False on failure.
        """
        client = self.get_qdrant_client()
        coll = self._collection_name()
        payload = self._build_payload()

        # build vectors
        dense_vec = self._build_dense_vector()
        sparse_vec = self._build_sparse_vector()

        # at least one vector is required by Qdrant point (dense or sparse)
        if dense_vec is None and sparse_vec is None:
            logger.debug("No dense or sparse vector for %s; skipping upsert for id %s", coll, self._point_id())
            return False

        # ensure collection exists (best-effort)
        try:
            self._ensure_collection()
        except Exception:
            pass

        # construct PointStruct: include dense and sparse vectors with named configs
        try:
            vector_dict = {}
            if dense_vec is not None:
                vector_dict["text-dense"] = dense_vec
            if sparse_vec is not None:
                vector_dict["text-sparse"] = sparse_vec

            point = qm.PointStruct(
                id=self._point_id(),
                vectors=vector_dict if vector_dict else None,
                payload=payload,
            )
            client.upsert(collection_name=coll, points=[point])
            logger.debug("Upserted point %s into collection %s", self._point_id(), coll)
            return True
        except Exception as e:
            logger.exception("Failed to upsert point %s into qdrant collection %s: %s", self._point_id(), coll, e)
            return False

    def delete_data_point(self) -> bool:
        """
        Delete point from Qdrant by id. Returns True on success, False on error.
        """
        client = self.get_qdrant_client()
        coll = self._collection_name()
        try:
            client.delete(collection_name=coll, points=[self._point_id()])
            logger.debug("Deleted point %s from collection %s", self._point_id(), coll)
            return True
        except Exception as e:
            logger.exception("Failed to delete point %s from qdrant collection %s: %s", self._point_id(), coll, e)
            return False

    # -------------------- Search functionality --------------------

    def _search_qdrant(
        self,
        query: str,
        limit: int = 10,
        org_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Search Qdrant collection using hybrid search (dense + sparse vectors with RRF fusion).

        Args:
            query: Search query text
            limit: Maximum number of results to return
            org_id: Optional organization ID filter

        Returns:
            List of search results with payload data
        """
        client = self.get_qdrant_client()
        coll = self._collection_name()

        if not _with_retries(client.collection_exists, coll):
            return []

        # Generate embeddings for the query
        dense_vec = self.embed_gen.generate_dense_vector(query)
        sparse_vec = self.embed_gen.generate_sparse_vector(query)

        # Build filter conditions
        filter_conditions = []
        if org_id:
            # Filter by organization ID - stored in payload as org field
            filter_conditions.append(
                qm.FieldCondition(
                    key="org", match=qm.MatchValue(value=org_id)
                )
            )

        query_filter = qm.Filter(must=filter_conditions) if filter_conditions else None

        # Perform hybrid search with RRF fusion
        try:
            res = _with_retries(
                client.query_points,
                collection_name=coll,
                prefetch=[
                    qm.Prefetch(query=sparse_vec, using="text-sparse", limit=50),
                    qm.Prefetch(query=dense_vec, using="text-dense", limit=limit),
                ],
                query=qm.FusionQuery(fusion=qm.Fusion.RRF),
                query_filter=query_filter,
                with_payload=True,
                limit=limit,
            )
            return res.points if res and hasattr(res, 'points') else []
        except Exception as e:
            logger.exception("Failed to search qdrant collection %s: %s", coll, e)
            return []

    def _calculate_similarity_scores(
        self,
        source_mongo_id: str,
        target_mongo_ids: List[str],
        org_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Calculate similarity scores between a source document and a list of target documents.
        """
        client = self.get_qdrant_client()
        coll = self._collection_name()

        if not _with_retries(client.collection_exists, coll):
            return []

        source_vector = self._get_source_vector(client, coll, source_mongo_id)
        if not source_vector:
            return []

        target_points = self._get_target_points(client, coll, target_mongo_ids)
        similarity_results = self._compute_similarities(
            source_vector, target_points, org_id
        )

        # Sort by similarity score (highest first)
        similarity_results.sort(key=lambda x: x["similarity_score"], reverse=True)
        return similarity_results

    def _get_source_vector(self, client, coll: str, source_mongo_id: str) -> Optional[Dict]:
        """Retrieve source document vector from Qdrant."""
        try:
            # Use retrieve to get specific points by ID
            source_points = _with_retries(
                client.retrieve,
                collection_name=coll,
                ids=[source_mongo_id],
                with_vectors=True,
            )

            if not source_points or len(source_points) == 0:
                logger.warning("Source document %s not found in Qdrant", source_mongo_id)
                return None

            point = source_points[0]
            # Handle both old and new client API
            vector = getattr(point, "vector", None) or getattr(point, "vectors", {})
            logger.debug("Found source document %s in Qdrant", source_mongo_id)
            return vector

        except Exception as e:
            logger.error("Failed to retrieve source document %s: %s", source_mongo_id, e)
            return None

    def _get_target_points(self, client, coll: str, target_mongo_ids: List[str]) -> List:
        """Retrieve target document points from Qdrant."""
        try:
            # Use retrieve to get specific points by ID
            target_points = _with_retries(
                client.retrieve,
                collection_name=coll,
                ids=target_mongo_ids,
                with_vectors=True,
                with_payload=True,
            )

            logger.debug("Found %d target documents in Qdrant", len(target_points))
            return target_points

        except Exception as e:
            logger.error("Failed to retrieve target documents: %s", e)
            return []

    def _compute_similarities(
        self,
        source_vector: Dict,
        target_points: List,
        org_id: Optional[str]
    ) -> List[Dict[str, Any]]:
        """Compute similarity scores for target points."""
        similarity_results = []

        for point in target_points:
            if not point.vector or not point.payload:
                continue

            point_mongo_id = point.payload.get("_id")
            if not point_mongo_id:
                continue

            if not self._passes_filters(point.payload, org_id):
                continue

            similarity_score = self._calculate_point_similarity(source_vector, point.vector)
            if similarity_score is not None:
                similarity_results.append(
                    {"mongo_id": point_mongo_id, "similarity_score": similarity_score}
                )

        return similarity_results

    def _passes_filters(self, payload: Dict, org_id: Optional[str]) -> bool:
        """Check if point passes RBAC filters."""
        if org_id and payload.get("org") != org_id:
            return False
        return True

    def _calculate_point_similarity(self, source_vector: Dict, target_vector: Dict) -> Optional[float]:
        """Calculate similarity between source and target vectors."""
        try:
            source_dense = source_vector.get("text-dense", [])
            target_dense = target_vector.get("text-dense", [])

            if not source_dense or not target_dense:
                return None

            return self._cosine_similarity(source_dense, target_dense)

        except Exception as e:
            logger.error("Failed to calculate similarity: %s", e)
            return None

    def _cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """
        Calculate cosine similarity between two vectors.

        Args:
            vec1: First vector
            vec2: Second vector

        Returns:
            Cosine similarity score between 0 and 1
        """
        try:
            # Convert to lists if needed
            if not isinstance(vec1, list):
                vec1 = list(vec1)
            if not isinstance(vec2, list):
                vec2 = list(vec2)

            # Calculate dot product
            dot_product = sum(a * b for a, b in zip(vec1, vec2))

            # Calculate magnitudes
            norm1 = (sum(x ** 2 for x in vec1)) ** 0.5
            norm2 = (sum(x ** 2 for x in vec2)) ** 0.5

            # Avoid division by zero
            if norm1 == 0 or norm2 == 0:
                return 0.0

            return dot_product / (norm1 * norm2)

        except Exception as e:
            logger.error("Failed to calculate cosine similarity: %s", e)
            return 0.0


