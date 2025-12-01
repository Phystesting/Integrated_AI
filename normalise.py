import chromadb 
import numpy as np

db = chromadb.PersistentClient()
memories = db.get_collection("ai_memories")
result = memories.get()

ids=[]
embeddings=[]
documents=[]
metadatas=[]

print(result.items())

"""
def normalise_vec(vectors):
    vec = v / np.linalg.norm(v)
    return vec.tolist()
    
for i in range(len(result["ids"])):
    vector = np.array(result["embeddings"][i])
    embeddings.append(normalise_vec(vector))
    ids.append(result["ids"][i])
    documents.append(result["documents"][i])
    metadatas.append(result["metadatas"][i])
    
collection.upsert(
    ids=ids,
    embeddings=embeddings,
    documents=documents,
    metadatas=metadatas
)
"""