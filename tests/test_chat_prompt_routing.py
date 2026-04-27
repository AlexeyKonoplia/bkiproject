from uuid import uuid4

from app.api.routes.ask import AskRequest


def test_ask_request_supports_separate_question_for_prompt():
    request = AskRequest(
        question="Что написано в разделе про методологию?",
        question_for_prompt="Пользователь: расскажи кратко про введение\nПользователь: Что написано в разделе про методологию?",
        source_document_id=uuid4(),
    )

    assert request.question == "Что написано в разделе про методологию?"
    assert request.question_for_prompt is not None
