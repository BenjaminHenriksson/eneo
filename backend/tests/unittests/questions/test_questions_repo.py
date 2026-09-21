from datetime import datetime, timezone
from unittest.mock import AsyncMock
from uuid import uuid4

from sqlalchemy.dialects import postgresql

from intric.questions.questions_repo import QuestionRepository


async def test_persist_context_snapshot_without_overwriting_cumulative_usage():
    session = AsyncMock()
    repo = QuestionRepository(session)
    question_id, tenant_id = uuid4(), uuid4()
    await repo.update_with_answer(
        question_id=question_id,
        tenant_id=tenant_id,
        answer="done",
        num_tokens_question=93000,
        num_tokens_answer=800,
        context_tokens_question=32000,
        context_tokens_answer=500,
    )
    stmt = session.execute.await_args.args[0]
    params = stmt.compile(dialect=postgresql.dialect()).params
    assert params["num_tokens_question"] == 93000
    assert params["num_tokens_answer"] == 800
    assert params["context_tokens_question"] == 32000
    assert params["context_tokens_answer"] == 500
    assert tenant_id in params.values()


async def test_get_by_tenant_filters_out_questions_without_session_id():
    repo = QuestionRepository(AsyncMock())
    repo.delegate.get_models_from_query = AsyncMock(return_value=[])

    await repo.get_by_tenant(
        tenant_id=uuid4(),
        start_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
        end_date=datetime(2024, 1, 31, tzinfo=timezone.utc),
    )

    stmt = repo.delegate.get_models_from_query.await_args.args[0]
    compiled = str(stmt.compile(dialect=postgresql.dialect()))

    assert "questions.session_id IS NOT NULL" in compiled
