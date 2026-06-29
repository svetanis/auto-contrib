import unittest
from unittest.mock import patch
from app.repo_mapper import vector_store

class TestVectorStore(unittest.TestCase):
    
    @patch("app.repo_mapper.vector_store.embed_text")
    def test_semantic_search(self, mock_embed):
        # Mock embeddings to avoid hitting the real API during tests
        mock_embed.side_effect = [
            [0.1, 0.9], # Doc 1 embedding
            [0.9, 0.1], # Doc 2 embedding
            [0.8, 0.2]  # Query embedding (Cosine similarity matches Doc 2)
        ]
        
        store = vector_store.VectorStore()
        store.add_document("doc1.py", "database connection code")
        store.add_document("doc2.py", "UI button component")
        
        # Query for "frontend button"
        results = store.search("frontend button", top_k=1)
        
        # It should return doc2.py because the embeddings align
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["file_path"], "doc2.py")

if __name__ == "__main__":
    unittest.main()
