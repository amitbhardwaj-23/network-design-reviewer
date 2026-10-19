"""
retriever.py — ChromaDB vector store for architectural standards KB.
Seed once with: python retriever.py seed
Query with: retrieve_standards("your query here")
"""
import os, sys
from pathlib import Path
from typing import List
import chromadb
from chromadb.utils.embedding_functions import OllamaEmbeddingFunction
from dotenv import load_dotenv

load_dotenv()

DB_PATH   = os.getenv("CHROMA_DB_PATH", "./chroma_db")
EMBED_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
EMBED_MDL = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
CHUNK_SZ  = int(os.getenv("KB_CHUNK_SIZE", "200"))
CHUNK_OVL = int(os.getenv("KB_CHUNK_OVERLAP", "40"))

client = chromadb.PersistentClient(path=DB_PATH)
embedding_fn = OllamaEmbeddingFunction(url=EMBED_URL, model_name=EMBED_MDL)
collection = client.get_or_create_collection(
    name="architectural_standards",
    embedding_function=embedding_fn,
    metadata={"hnsw:space": "cosine"},
)

CATEGORY_MAP = {
    ("nist","zero_trust","zt","zscaler"): "zero_trust",
    ("togaf","adm","arch_gov"):           "togaf",
    ("cisco","cvd","sda","aci","sdwan"):  "cisco_cvd",
    ("aws","azure","cloud","hybrid"):     "cloud",
    ("cis","security","firewall"):        "security",
}

def infer_category(stem: str) -> str:
    s = stem.lower()
    for keys, cat in CATEGORY_MAP.items():
        if any(k in s for k in keys): return cat
    return "custom"

def chunk_text(text: str) -> List[str]:
    words = text.split()
    chunks, i = [], 0
    while i < len(words):
        chunks.append(" ".join(words[i:i+CHUNK_SZ]))
        i += CHUNK_SZ - CHUNK_OVL
    return chunks

def seed_standards(docs_dir: str = "./knowledge_base"):
    p = Path(docs_dir)
    if not p.exists():
        print(f"Knowledge base directory '{docs_dir}' not found.")
        print("Add .md or .txt files to ./knowledge_base/ then run: python retriever.py seed")
        return
    ids, texts, metas = [], [], []
    md_files = list(p.glob("**/*.md")) + list(p.glob("**/*.txt"))
    md_files = [f for f in md_files if f.name != "README.md"]
    if not md_files:
        print("No .md or .txt files found (excluding README.md). Add your standards documents first.")
        return
    for fp in md_files:
        text = fp.read_text(encoding="utf-8", errors="replace")
        for j, chunk in enumerate(chunk_text(text)):
            ids.append(f"{fp.stem}_{j}")
            texts.append(chunk)
            metas.append({"source": fp.stem, "category": infer_category(fp.stem), "chunk": j})
    if ids:
        collection.upsert(ids=ids, documents=texts, metadatas=metas)
        print(f"Seeded {len(ids)} chunks from {len(md_files)} files in {docs_dir}")
    else:
        print("No content to seed.")

def retrieve_standards(query: str, k: int = 4) -> List[dict]:
    if collection.count() == 0:
        return [{"content": "[KB empty — run: python retriever.py seed]",
                 "source": "system", "category": "system", "score": 0.0}]
    results = collection.query(
        query_texts=[query],
        n_results=min(k, collection.count()),
        include=["documents","metadatas","distances"],
    )
    out = []
    for doc, meta, dist in zip(
        results["documents"][0], results["metadatas"][0], results["distances"][0]
    ):
        score = round(1 - dist, 3)
        if score >= 0.25:
            out.append({"content": doc, "source": meta.get("source","?"),
                        "category": meta.get("category","general"), "score": score})
    return out or [{"content": "[No relevant standards found — add more documents to ./knowledge_base]",
                    "source": "system", "category": "system", "score": 0.0}]

def kb_status() -> dict:
    count = collection.count()
    return {"chunks": count, "status": "ready" if count > 0 else "empty"}

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "seed":
        seed_standards()
    elif len(sys.argv) > 1 and sys.argv[1] == "status":
        s = kb_status()
        print(f"KB status: {s['chunks']} chunks — {s['status']}")
    else:
        print("Usage:")
        print("  python retriever.py seed     — seed KB from ./knowledge_base/")
        print("  python retriever.py status   — check how many chunks are indexed")
