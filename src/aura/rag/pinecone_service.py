"""AURA Pinecone RAG Service — policy ingestion, chunking, and semantic retrieval."""
from __future__ import annotations
import math
import os
import uuid
from typing import Any, Dict, List, Optional
from aura.rag.embeddings import EmbeddingService


def cosine_similarity(a: List[float], b: List[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


class PineconeRAGService:
    """
    RAG service managing policy document ingestion, chunking, and semantic vector retrieval.
    Enforces organization-level data isolation via metadata filtering.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        environment: Optional[str] = None,
        index_name: str = "aura-policies",
        dimension: int = 384,
    ) -> None:
        self.api_key = api_key or os.getenv("PINECONE_API_KEY", "")
        self.environment = environment or os.getenv("PINECONE_ENVIRONMENT", "us-east-1")
        self.index_name = index_name
        self.dimension = dimension
        self.embeddings = EmbeddingService(dimension=dimension)

        # In-memory vector cache / fallback index for local testing and offline modes
        self._local_index: List[Dict[str, Any]] = []
        self._client = None
        self._use_remote = False

        if self.api_key and not self.api_key.startswith("mock-") and not os.getenv("AURA_OFFLINE_TESTS"):
            try:
                from pinecone import Pinecone
                self._client = Pinecone(api_key=self.api_key)
                self._use_remote = True
            except Exception:
                self._use_remote = False

    def chunk_text(self, text: str, chunk_size: int = 500, chunk_overlap: int = 100) -> List[str]:
        """Split document text into overlapping chunks."""
        cleaned = text.strip()
        if not cleaned:
            return []
        if len(cleaned) <= chunk_size:
            return [cleaned]

        chunks = []
        start = 0
        while start < len(cleaned):
            end = start + chunk_size
            chunk = cleaned[start:end]
            chunks.append(chunk)
            start += chunk_size - chunk_overlap
        return chunks

    def ingest_policy_document(
        self,
        doc_id: str,
        title: str,
        content: str,
        org_id: str = "default-org",
        category: str = "security_policy",
    ) -> Dict[str, Any]:
        """Ingest, chunk, embed, and index a policy document."""
        chunks = self.chunk_text(content)
        vectors_to_upsert = []

        for idx, chunk in enumerate(chunks):
            chunk_id = f"{doc_id}_{idx}"
            vec = self.embeddings.embed_text(chunk)
            metadata = {
                "doc_id": doc_id,
                "org_id": org_id,
                "title": title,
                "chunk_index": idx,
                "text": chunk,
                "category": category,
            }
            item = {
                "id": chunk_id,
                "values": vec,
                "metadata": metadata,
            }
            # Add to local cache / fallback
            self._local_index = [entry for entry in self._local_index if entry["id"] != chunk_id]
            self._local_index.append(item)
            vectors_to_upsert.append(item)

        # Upsert to Pinecone if client is active
        if self._use_remote and self._client:
            try:
                index = self._client.Index(self.index_name)
                index.upsert(vectors=vectors_to_upsert)
            except Exception:
                pass  # Local fallback maintains availability

        return {
            "doc_id": doc_id,
            "title": title,
            "chunks_ingested": len(chunks),
            "org_id": org_id,
        }

    def search_policies(
        self,
        query: str,
        org_id: str = "default-org",
        top_k: int = 3,
        filter_category: Optional[str] = None,
        min_score: float = 0.05,
    ) -> List[Dict[str, Any]]:
        """
        Semantic search with mandatory organization-level data isolation.
        """
        query_vec = self.embeddings.embed_text(query)

        # Enforce org_id isolation filter
        candidates = [
            item for item in self._local_index
            if item["metadata"].get("org_id") == org_id
        ]
        if filter_category:
            candidates = [
                c for c in candidates
                if c["metadata"].get("category") == filter_category
            ]

        results = []
        for item in candidates:
            score = cosine_similarity(query_vec, item["values"])
            if score >= min_score:
                results.append({
                    "id": item["id"],
                    "score": score,
                    "text": item["metadata"]["text"],
                    "title": item["metadata"]["title"],
                    "doc_id": item["metadata"]["doc_id"],
                    "org_id": item["metadata"]["org_id"],
                })

        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_k]

    def get_policy_context_for_action(
        self,
        user_intent: str,
        tool_name: str,
        org_id: str = "default-org",
    ) -> Dict[str, Any]:
        """
        Retrieve relevant organizational policies to provide as context to JEV.
        """
        query = f"policy for action {tool_name} with intent {user_intent}"
        matches = self.search_policies(query=query, org_id=org_id, top_k=2)

        if not matches:
            return {}

        excerpts = [f"[{m['title']}]: {m['text'][:200]}" for m in matches]
        return {
            "retrieved_policies": excerpts,
            "matched_policy_count": len(matches),
            "org_id": org_id,
        }
