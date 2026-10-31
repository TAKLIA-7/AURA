"""Unit tests for AURA Pinecone RAG and policy context retrieval."""
import pytest
from aura.rag.embeddings import EmbeddingService
from aura.rag.pinecone_service import PineconeRAGService


def test_embedding_service_dimensions():
    service = EmbeddingService(dimension=384)
    vec = service.embed_text("Employee data privacy policy")
    assert len(vec) == 384
    # Check normalized
    magnitude = sum(x * x for x in vec)
    assert pytest.approx(magnitude, rel=1e-3) == 1.0


def test_chunking_and_ingestion():
    rag = PineconeRAGService(api_key="mock-key")
    text = (
        "Policy Section 1: All employee compensation records are restricted. "
        "Policy Section 2: Any updates or salary changes require dual-approval from HR VP. "
        "Policy Section 3: Deletion of records is prohibited."
    )
    res = rag.ingest_policy_document(
        doc_id="doc_hr_001",
        title="Compensation Governance Policy",
        content=text,
        org_id="org_alpha",
    )
    assert res["chunks_ingested"] >= 1
    assert res["org_id"] == "org_alpha"


def test_multi_tenant_isolation():
    rag = PineconeRAGService(api_key="mock-key")
    # Ingest for org_alpha
    rag.ingest_policy_document(
        doc_id="doc_alpha",
        title="Alpha Private Policy",
        content="Secret Alpha Policy on internal project AlphaX.",
        org_id="org_alpha",
    )
    # Ingest for org_beta
    rag.ingest_policy_document(
        doc_id="doc_beta",
        title="Beta Public Policy",
        content="Beta policy regarding external vendors.",
        org_id="org_beta",
    )

    # Searching as org_beta should NEVER return org_alpha documents
    results_beta = rag.search_policies(query="AlphaX", org_id="org_beta")
    assert len(results_beta) == 0

    # Searching as org_alpha finds it
    results_alpha = rag.search_policies(query="AlphaX", org_id="org_alpha")
    assert len(results_alpha) >= 1
    assert results_alpha[0]["doc_id"] == "doc_alpha"


def test_get_policy_context_for_jev():
    rag = PineconeRAGService(api_key="mock-key")
    rag.ingest_policy_document(
        doc_id="policy_sql_001",
        title="Database Access Policy",
        content="Direct UPDATE or DELETE operations on production tables are forbidden without managerial review.",
        org_id="default-org",
    )
    context = rag.get_policy_context_for_action(
        user_intent="Update employee salary",
        tool_name="sqlite.execute",
        org_id="default-org",
    )
    assert "retrieved_policies" in context
    assert context["matched_policy_count"] >= 1
    assert "Database Access Policy" in context["retrieved_policies"][0]
