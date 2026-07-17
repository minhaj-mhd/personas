import httpx
import pytest
import pytest_asyncio
from unittest.mock import patch
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

from app.config import settings
from app.db import async_session_maker
from app.main import app
from app.models import Persona, Conversation, Message, Memory
from app.services.memory import chunk_text, MemoryService
from app.services.summarizer import SummarizerService
from app.services.prompt_builder import inject_memories_into_prompt


@pytest_asyncio.fixture
async def db_session():
    async with async_session_maker() as session:
        yield session


async def clean_database(session):
    from sqlalchemy import delete

    try:
        await session.execute(delete(Memory))
        await session.execute(delete(Message))
        await session.execute(delete(Conversation))
        await session.execute(delete(Persona).where(Persona.is_builtin == False))  # noqa: E712
        await session.commit()
    except Exception:
        await session.rollback()


class MockHttpxResponse:
    def __init__(self, json_data, status_code=200):
        self._json_data = json_data
        self.status_code = status_code

    def json(self):
        return self._json_data
        
    def raise_for_status(self):
        pass

original_post = AsyncClient.post

async def mock_httpx_post(self, url, json=None, **kwargs):
    url_str = str(url)
    if "/api/embed" in url_str:
        inputs = json.get("input", [])
        return MockHttpxResponse({"embeddings": [[0.01] * 768 for _ in inputs]})
    elif "/api/chat" in url_str:
        return MockHttpxResponse({
            "message": {
                "content": '{"summary": "User shared their favorite color is green.", "facts": ["User\'s favorite color is green"]}'
            }
        })
    else:
        return await original_post(self, url, json=json, **kwargs)


@pytest.mark.asyncio
async def test_chunk_text_boundaries():
    text = "This is a simple text document for testing word boundaries and chunk splitting."
    # Chunk size 15, overlap 5 characters
    chunks = chunk_text(text, chunk_size=15, overlap=5)
    assert len(chunks) > 0
    # Verify no word is cut off mid-way (space-split words)
    for chunk in chunks:
        assert len(chunk.split()) >= 1


@pytest.mark.asyncio
async def test_document_ingestion_and_rag_retrieval(db_session):
    try:
        # 1. Create a persona
        persona = Persona(
            name="RAG Assistant", system_prompt="You have documents.", is_builtin=False
        )
        db_session.add(persona)
        await db_session.commit()

        # Mock embeddings service API calls
        with patch("app.services.embeddings.httpx.AsyncClient.post", mock_httpx_post):
            memory_service = MemoryService()
            # 2. Ingest document
            doc_text = (
                "Google DeepMind developed the Gemini series of multimodal AI models."
            )
            await memory_service.ingest_document(
                persona_id=persona.id, filename="deepmind.txt", text=doc_text
            )

            # Check database chunks
            stmt = (
                select(Memory)
                .where(Memory.persona_id == persona.id)
                .where(Memory.memory_type == "document")
            )
            res = await db_session.execute(stmt)
            chunks = res.scalars().all()
            assert len(chunks) > 0
            assert chunks[0].content == doc_text
            assert chunks[0].metadata_["source"] == "deepmind.txt"
            assert len(chunks[0].embedding) == 768

            # 3. Retrieve context via RAG
            retrieved = await memory_service.retrieve_context(
                persona_id=persona.id, conversation_id=None, user_text="DeepMind models"
            )
            assert len(retrieved) > 0
            assert retrieved[0].content == doc_text

    finally:
        await clean_database(db_session)


@pytest.mark.asyncio
async def test_rolling_summarization_and_facts_extraction(db_session):
    try:
        persona = Persona(
            name="Socrates", system_prompt="You seek truth.", is_builtin=False
        )
        db_session.add(persona)
        await db_session.commit()

        conv = Conversation(persona_id=persona.id, title="Socratic Dialogue")
        db_session.add(conv)
        await db_session.commit()

        # Add some messages
        m1 = Message(conversation_id=conv.id, role="user", content="Hello Socrates")
        m2 = Message(
            conversation_id=conv.id,
            role="assistant",
            content="Greetings. What is on your mind?",
        )
        m3 = Message(
            conversation_id=conv.id, role="user", content="My favorite color is green."
        )
        db_session.add_all([m1, m2, m3])
        await db_session.commit()

        # Mock embeddings and summarizer calls
        with patch("app.services.embeddings.httpx.AsyncClient.post", mock_httpx_post), \
             patch("app.services.summarizer.httpx.AsyncClient.post", mock_httpx_post):
            transport = ASGITransport(app=app)
            async with AsyncClient(
                transport=transport, base_url="http://test"
            ) as ac:
                # Trigger manual summarization
                resp = await ac.post(f"/api/conversations/{conv.id}/summarize")
                assert resp.status_code == 200

            # Verify memories populated in database
            stmt = select(Memory).where(Memory.conversation_id == conv.id)
            res = await db_session.execute(stmt)
            memories = res.scalars().all()

            # We expect a summary memory and a fact memory
            types_in_db = [m.memory_type for m in memories]
            assert "summary" in types_in_db
            assert "fact" in types_in_db

            summary_mem = next(m for m in memories if m.memory_type == "summary")
            assert (
                "User shared their favorite color is green" in summary_mem.content
            )

            fact_mem = next(m for m in memories if m.memory_type == "fact")
            assert "User's favorite color is green" in fact_mem.content
            assert len(fact_mem.embedding) == 768

            # Check watermark was updated
            await db_session.refresh(conv)
            assert conv.last_summarized_message_id == m3.id

    finally:
        await clean_database(db_session)


def _make_counting_post(fail_on_chat_calls: set[int] | None = None):
    """Returns an httpx.AsyncClient.post mock that serves valid summary/embed responses
    and raises an empty-message ReadTimeout on the given (1-indexed) /api/chat call
    numbers — the exact failure that stalled real summarization. Exposes a mutable call
    counter."""
    fail_on = fail_on_chat_calls or set()
    state = {"chat_calls": 0}

    async def _post(self, url, json=None, **kwargs):
        url_str = str(url)
        if "/api/embed" in url_str:
            inputs = json.get("input", [])
            return MockHttpxResponse({"embeddings": [[0.01] * 768 for _ in inputs]})
        if "/api/chat" in url_str:
            state["chat_calls"] += 1
            if state["chat_calls"] in fail_on:
                raise httpx.ReadTimeout("")
            return MockHttpxResponse(
                {"message": {"content": '{"summary": "S", "facts": ["F"]}'}}
            )
        return await original_post(self, url, json=json, **kwargs)

    return _post, state


async def _seed_conversation(db_session, n_messages: int):
    persona = Persona(name="Batcher", system_prompt="hi", is_builtin=False)
    db_session.add(persona)
    await db_session.commit()
    conv = Conversation(persona_id=persona.id, title="Backlog")
    db_session.add(conv)
    await db_session.commit()
    msgs = [
        Message(conversation_id=conv.id, role="user", content=f"message {i}")
        for i in range(n_messages)
    ]
    db_session.add_all(msgs)
    await db_session.commit()
    return conv, msgs


@pytest.mark.asyncio
async def test_summarization_drains_backlog_in_batches(db_session):
    """A backlog larger than SUMMARIZE_BATCH_SIZE is processed in multiple bounded
    Ollama calls (not one oversized request), draining fully to the last message."""
    try:
        conv, msgs = await _seed_conversation(db_session, 6)
        post, state = _make_counting_post()
        with patch.object(settings, "SUMMARIZE_BATCH_SIZE", 2), patch(
            "app.services.summarizer.httpx.AsyncClient.post", post
        ):
            await SummarizerService().maybe_summarize(conv.id, force=True)

        # 6 messages / batch of 2 => 3 separate chat calls, one summary each.
        assert state["chat_calls"] == 3
        summaries = (
            await db_session.execute(
                select(Memory)
                .where(Memory.conversation_id == conv.id)
                .where(Memory.memory_type == "summary")
            )
        ).scalars().all()
        assert len(summaries) == 3
        # Watermark reached the final message — the whole backlog drained.
        await db_session.refresh(conv)
        assert conv.last_summarized_message_id == msgs[-1].id
    finally:
        await clean_database(db_session)


@pytest.mark.asyncio
async def test_summarization_progress_survives_permanent_failure(db_session):
    """If a batch fails every attempt, the watermark and memories from earlier committed
    batches survive — so the backlog shrinks instead of being retried whole every time
    (the bug that let a 362-message backlog build up and time out forever)."""
    try:
        conv, msgs = await _seed_conversation(db_session, 6)
        # batch 1 (msgs 0-1) = chat call 1 (ok); batch 2 = calls 2 (attempt) + 3 (retry),
        # both fail, so batch 2 is abandoned and the drain halts.
        post, state = _make_counting_post(fail_on_chat_calls={2, 3})
        with patch.object(settings, "SUMMARIZE_BATCH_SIZE", 2), patch.object(
            settings, "SUMMARIZE_MAX_RETRIES", 1
        ), patch("app.services.summarizer.httpx.AsyncClient.post", post):
            await SummarizerService().maybe_summarize(conv.id, force=True)

        assert state["chat_calls"] == 3  # batch 2 tried twice, then gave up (no batch 3)
        summaries = (
            await db_session.execute(
                select(Memory)
                .where(Memory.conversation_id == conv.id)
                .where(Memory.memory_type == "summary")
            )
        ).scalars().all()
        assert len(summaries) == 1  # batch 1 persisted despite batch 2 failing
        # Watermark advanced to the end of the successful batch, not rolled back to start.
        await db_session.refresh(conv)
        assert conv.last_summarized_message_id == msgs[1].id
    finally:
        await clean_database(db_session)


@pytest.mark.asyncio
async def test_summarization_retries_transient_failure(db_session):
    """A batch that fails once (a transient timeout) is retried, and on success the drain
    continues to completion instead of abandoning the rest of the backlog."""
    try:
        conv, msgs = await _seed_conversation(db_session, 4)
        # Fail only the first chat call; its retry (call 2) succeeds, then batch 2 (call 3).
        post, state = _make_counting_post(fail_on_chat_calls={1})
        with patch.object(settings, "SUMMARIZE_BATCH_SIZE", 2), patch.object(
            settings, "SUMMARIZE_MAX_RETRIES", 1
        ), patch("app.services.summarizer.httpx.AsyncClient.post", post):
            await SummarizerService().maybe_summarize(conv.id, force=True)

        assert state["chat_calls"] == 3  # batch1: fail + retry-ok; batch2: ok
        # Full drain despite the transient failure.
        await db_session.refresh(conv)
        assert conv.last_summarized_message_id == msgs[-1].id
    finally:
        await clean_database(db_session)


@pytest.mark.asyncio
async def test_cross_session_resume_recall(db_session):
    """
    Automated Resume-Recall Test:
    Verify that facts learned in session 1 are successfully retrieved
    and injected into the system instruction prompt in session 2 for the same persona.
    """
    try:
        # 1. Setup Persona
        persona = Persona(
            name="Memory Bot", system_prompt="I remember things.", is_builtin=False
        )
        db_session.add(persona)
        await db_session.commit()

        # 2. Setup Session 1
        conv1 = Conversation(persona_id=persona.id, title="Session 1")
        db_session.add(conv1)
        await db_session.commit()

        # Mock fact in DB as if extracted from Session 1
        fact_mem = Memory(
            conversation_id=conv1.id,
            persona_id=persona.id,
            memory_type="fact",
            content="User's favorite color is green",
            embedding=[0.01] * 768,
            importance_score=0.8,
        )
        db_session.add(fact_mem)
        await db_session.commit()

        # 3. Setup Session 2 (brand new conversation)
        conv2 = Conversation(persona_id=persona.id, title="Session 2")
        db_session.add(conv2)
        await db_session.commit()

        # 4. Mock retrieve context call and prompt assembly
        with patch("app.services.embeddings.httpx.AsyncClient.post", mock_httpx_post):
            memory_service = MemoryService()
            retrieved = await memory_service.retrieve_context(
                persona_id=persona.id,
                conversation_id=conv2.id,
                user_text="What color do I like?",
            )

            # Assert that the fact from Session 1 is retrieved for Session 2
            assert len(retrieved) > 0
            retrieved_contents = [m.content for m in retrieved]
            assert "User's favorite color is green" in retrieved_contents

            # 5. Verify prompt assembly contains the fact
            injected_prompt = inject_memories_into_prompt(
                persona.system_prompt, retrieved
            )
            assert "### LONG-TERM MEMORY & CONTEXT" in injected_prompt
            assert "User's favorite color is green" in injected_prompt

    finally:
        await clean_database(db_session)
