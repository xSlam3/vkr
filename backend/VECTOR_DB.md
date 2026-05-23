# Vector DB for Chat Bot (Python)

## Install packages
```powershell
.\venv\Scripts\pip install -r requirements.txt
```

## Environment variables
```powershell
$env:VECTOR_DB_ENABLED="true"
$env:VECTOR_DB_PATH="./vector_db"
$env:VECTOR_COLLECTION="knowledge_chunks"
$env:EMBED_MODEL="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
$env:VECTOR_CHUNK_SIZE="800"
$env:VECTOR_CHUNK_OVERLAP="120"
$env:VECTOR_TOP_K="4"
$env:VECTOR_MIN_SCORE="0.25"
```

## Optional LLM (OpenRouter)
```powershell
$env:CHAT_USE_LLM="true"
$env:LLM_API_URL="https://openrouter.ai/api/v1"
$env:LLM_MODEL="qwen/qwen3-next-80b-a3b-instruct:free"
$env:LLM_API_KEY="replace-with-your-openrouter-key"
$env:LLM_TEMPERATURE="0.1"
```

## How indexing works
- `knowledge` article create/update -> upsert chunks to vector DB.
- `knowledge` article delete -> remove chunks by `article_id`.

## Chat endpoint
- `POST /chat/`
- Body:
```json
{
  "question": "Как чистить кольцо?",
  "top_k": 4,
  "category_id": null
}
```
