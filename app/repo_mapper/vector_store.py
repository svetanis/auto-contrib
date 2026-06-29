import math

def embed_text(text: str) -> list[float]:
    """Mock embedding generator. In prod, this would call Vertex AI or google.genai."""
    return [float(len(text) % 10) / 10.0, float(len(text) % 5) / 5.0]

def cosine_similarity(vec1: list[float], vec2: list[float]) -> float:
    dot_product = sum(a * b for a, b in zip(vec1, vec2))
    mag1 = math.sqrt(sum(a * a for a in vec1))
    mag2 = math.sqrt(sum(b * b for b in vec2))
    if mag1 == 0 or mag2 == 0: return 0.0
    return dot_product / (mag1 * mag2)

class VectorStore:
    def __init__(self):
        self.documents = []

    def add_document(self, file_path: str, content: str):
        embedding = embed_text(content)
        self.documents.append({
            "file_path": file_path,
            "content": content,
            "embedding": embedding
        })

    def search(self, query: str, top_k: int = 5) -> list[dict]:
        query_embedding = embed_text(query)
        results = []
        for doc in self.documents:
            sim = cosine_similarity(query_embedding, doc["embedding"])
            results.append((sim, doc))
            
        results.sort(key=lambda x: x[0], reverse=True)
        return [doc for sim, doc in results[:top_k]]
