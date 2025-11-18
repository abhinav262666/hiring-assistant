from openai import OpenAI
from typing import List
from settings import senv

class EmbeddingGenerator:
    def __init__(self) -> None:
        self.client = OpenAI()
    
    def generate_vector(self, query: str) -> List:
        response = self.client.embeddings.create(input=query, model=senv.EMBEDDING_MODEL)
        return response.data[0].embedding