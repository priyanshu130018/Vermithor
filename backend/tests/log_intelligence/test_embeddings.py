import numpy as np
from backend.app.log_intelligence.embedding.service import get_embedding_service


def test_embedding_dimension_and_structure():
    """Verify sentence-transformers outputs 384-D normalized vector."""
    emb_service = get_embedding_service()
    vec = emb_service.embed_text("service: booking-api\nseverity: ERROR\ncategory: DATABASE\nmessage: Connection refused to postgres")

    assert isinstance(vec, list)
    assert len(vec) == 384
    # Check normalized L2 norm is ~1.0
    norm = np.linalg.norm(np.array(vec))
    assert abs(norm - 1.0) < 1e-4


def test_semantic_similarity_relative_ordering():
    """Verify semantically similar logs produce higher cosine similarity than unrelated logs."""
    emb_service = get_embedding_service()

    v_query = np.array(emb_service.embed_text("database connection timeout"))
    v_db1 = np.array(emb_service.embed_text("Connection refused to PostgreSQL database"))
    v_db2 = np.array(emb_service.embed_text("Unable to establish database connection"))
    v_unrelated = np.array(emb_service.embed_text("User login authentication successful"))

    sim_db1 = float(np.dot(v_query, v_db1))
    sim_db2 = float(np.dot(v_query, v_db2))
    sim_unrelated = float(np.dot(v_query, v_unrelated))

    assert sim_db1 > sim_unrelated
    assert sim_db2 > sim_unrelated
