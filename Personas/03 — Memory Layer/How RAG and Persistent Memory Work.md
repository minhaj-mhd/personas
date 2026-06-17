---
title: "How RAG and Persistent Memory Work"
type: guide
status: active
updated: 2026-06-17
---

# 🧠 How RAG and Persistent Memory Work

This document provides a deep, technical explanation of the Retrieval-Augmented Generation (RAG) and long-term memory architectures implemented in our platform. It covers chunking algorithms, vector distance mathematics, database queries, and background summarizers.

---

## 1. Vector Embeddings (`text-embedding-004`)

Vector embedding is the process of converting unstructured text into a fixed-size array of numbers (a vector) that captures the semantic meaning of the text.

```
┌────────────────────────────────┐       ┌──────────────────────┐       ┌───────────────────────────────┐
│ "Google DeepMind built Gemini" │ ─────►│ text-embedding-004   │ ─────►│ [0.012, -0.045, ..., 0.189]   │
└────────────────────────────────┘       └──────────────────────┘       └───────── Size: 768 ───────────┘
```

- **Model**: We use Google's **`text-embedding-004`** model via the `google-genai` SDK.
- **Dimensionality**: It generates vectors of length **768**.
- **Batching**: Ingesting documents requires generating embeddings for multiple text chunks. Making separate API calls for each chunk would cause high network latency. The `EmbeddingsService` uses batch requests inside [embeddings.py](file:///c:/Users/loq/Desktop/learn/personas/app/services/embeddings.py#L26-L40):
  ```python
  response = await self.client.aio.models.embed_content(
      model=settings.EMBED_MODEL,
      contents=texts  # list[str]
  )
  return [e.values for e in response.embeddings]
  ```

---

## 2. Word-Aligned Sliding Window Chunking

To search documents semantically, we cannot upload a whole book as a single search query—long texts dilute vectors. Instead, we split documents into smaller "chunks".

We implement a **word-aligned sliding window chunker** in [memory.py](file:///c:/Users/loq/Desktop/learn/personas/app/services/memory.py#L11-L42) with these rules:
1. **Size Constraint**: Maximum chunk size is `500` characters.
2. **Overlap Constraint**: Consecutive chunks share an overlap of `100` characters to prevent losing context at splitting boundaries.
3. **Word Alignment**: We split text strictly on space boundaries (`.split()`) rather than character counts. This prevents cutting words in half (e.g. splitting *"transcription"* into *"trans"* and *"cription"*).

### How the Algorithm Works:
```
Text: "The quick brown fox jumps over the lazy dog..."
       ▲                     ▲
       ├───── Chunk 1 ───────┤
                     ▲                     ▲
                     ├───── Chunk 2 ───────┤ (with 100 char overlap)
```

- **Accumulator**: We loop through words and add them to `current_chunk_words` while keeping track of character count.
- **Overlap Rollback**: When character count exceeds 500:
  - We save the current chunk by joining words.
  - We walk backwards from the end of `current_chunk_words` to collect words until their combined length is at least 100 characters.
  - We seed the next chunk with these overlap words.

---

## 3. Vector Similarity Mathematics & `pgvector` Queries

To find RAG document chunks or past facts matching a user's query, we measure the "distance" between their vector embeddings.

### Cosine Distance Mathematics
Given a query vector \(\vec{q}\) and a stored memory vector \(\vec{m}\):

1. **Cosine Similarity** is the cosine of the angle between the two vectors. It measures orientation, ignoring scale:
   \[\text{Similarity}(\vec{q}, \vec{m}) = \cos(\theta) = \frac{\vec{q} \cdot \vec{m}}{\|\vec{q}\| \|\vec{m}\|} = \frac{\sum_{i=1}^{n} q_i m_i}{\sqrt{\sum_{i=1}^{n} q_i^2} \sqrt{\sum_{i=1}^{n} m_i^2}}\]
   - Value ranges from `-1.0` (opposite directions) to `1.0` (identical direction).

2. **Cosine Distance** is the complement of similarity:
   \[\text{Distance}(\vec{q}, \vec{m}) = 1 - \text{Similarity}(\vec{q}, \vec{m})\]
   - Value ranges from `0.0` (identical) to `2.0` (opposite directions).

### Database Retrieval Query
We use PostgreSQL's `pgvector` extension. In SQL, the `<->` operator performs **Cosine Distance** calculations. We map this query using SQLAlchemy's `.cosine_distance()` in [memory.py](file:///c:/Users/loq/Desktop/learn/personas/app/services/memory.py#L102-L115):

```python
# 1. Calculate cosine distance
distance = Memory.embedding.cosine_distance(query_embedding)

# 2. Select top matches
stmt = (
    select(Memory)
    .where(Memory.persona_id == persona_id)
    .where(Memory.memory_type != "summary")  # Summaries are loaded separately
    .where(distance < 0.7)  # Similarity Threshold: distance < 0.7 is similarity > 0.3
    .order_by(distance.asc())  # Smallest distance (highest similarity) first
    .limit(limit)
)
```

- **Threshold justification**: We use a distance threshold of `< 0.7` (cosine similarity `> 0.3`). This acts as a quality gate, preventing the system from injecting random, unrelated noise when the user asks a question that matches nothing in the knowledge base.

---

## 4. Rolling Summarization and structured Fact Extractions

As conversations grow, the system compresses past history to avoid hitting model context limits and to keep token costs down.

### Summarization Watermarks
1. The `conversations` table tracks the watermark `last_summarized_message_id`.
2. When the count of new messages after the watermark reaches `SUMMARIZE_THRESHOLD` (default: 10), the summarization pipeline triggers.
3. The system fetches the previous narrative summary and all unsummarized messages, and sends them to the **`gemini-2.5-pro`** model.

### Structured JSON Outputs via Pydantic
We guarantee that the LLM response is returned as valid JSON matching our database schemas using Pydantic validation inside [summarizer.py](file:///c:/Users/loq/Desktop/learn/personas/app/services/summarizer.py#L17-L20):

```python
class SummaryOutput(BaseModel):
    summary: str      # Consolidated, rolling narrative of the chat history
    facts: list[str]  # Array of user details extracted from the new turns
```

We send this schema to Gemini using the `response_schema` parameter:
```python
response = await self.client.aio.models.generate_content(
    model=settings.SUMMARY_MODEL,
    contents=prompt,
    config=types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=SummaryOutput,
        temperature=0.2
    )
)
result = SummaryOutput.model_validate_json(response.text)
```

- **Saving Summaries**: The updated narrative is saved as a new `summary` memory. Future queries look up the latest summary.
- **Saving Facts**: Each string in the `facts` array is embedded individually using `text-embedding-004` and saved as a `fact` memory, allowing it to be searched semantically in future turns.

---

## 5. System Prompt Assembly

Before sending a user message to Gemini, [prompt_builder.py](file:///c:/Users/loq/Desktop/learn/personas/app/services/prompt_builder.py) merges the persona's core profile with the retrieved RAG chunks and summaries:

```
┌─────────────────────────────────────────────────────────────────┐
│ System instruction:                                             │
│ You are [Persona Name], [Description]...                        │
│                                                                 │
│ ### LONG-TERM MEMORY & CONTEXT                                  │
│ Narrative Summary of Past Conversations:                        │
│   [Latest narrative summary string retrieved by session ID]      │
│                                                                 │
│ Extracted Facts & Uploaded Reference Materials:                 │
│   - [metadata.source] content chunk (from pgvector search)       │
│   - User loves tea (from fact memory pgvector search)           │
└─────────────────────────────────────────────────────────────────┘
```

This dynamically assembled instruction ensures the model stays in character while having access to relevant knowledge and history.

---

## 6. How the Resume-Recall Test Verifies Memory (No API Calls)

To verify the memory layer works without making expensive calls to Google's API during tests, we write mock tests inside [test_memory.py](file:///c:/Users/loq/Desktop/learn/personas/app/tests/test_memory.py):

1. **Mocking Models**:
   - We mock `AsyncModels.embed_content` to return mock 768-dimensional float arrays (e.g. containing `0.1` values).
   - We mock `AsyncModels.generate_content` to return a mock JSON string representing our Pydantic schema:
     ```json
     {
       "summary": "The user told the model they have a pet turtle.",
       "facts": ["User has a pet turtle named Shelly"]
     }
     ```
2. **Simulation Flow**:
   - **Step 1**: Create a conversation for a persona.
   - **Step 2**: Create a message where the user shares a fact.
   - **Step 3**: Invoke `maybe_summarize` directly. This triggers the mock Gemini API call, parses the Pydantic schema, embeds the fact vector, and saves it in the SQLite test database.
   - **Step 4**: Start a new conversation for the same persona.
   - **Step 5**: Query `MemoryService.retrieve_context` using a query.
   - **Step 6**: Assert that the turtle fact is returned. This proves that the database models, vector calculations, and summarizer pipelines work correctly together.
