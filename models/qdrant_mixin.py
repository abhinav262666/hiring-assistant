from models.generate_embeddings import EmbeddingGenerator


class QdrantMixin:
    def __init__(self) -> None:
        self.embedding_generator = EmbeddingGenerator()

    def get_qdrant_client(self):
        pass

    def upsert_data_point(self) -> None:
        pass

    def retrieve_data_points(self, query):
        self.embedding_generator.generate_vector(query)
