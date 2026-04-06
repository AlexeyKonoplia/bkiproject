from app.rag.prompts import system_prompt_russian


def test_system_prompt_contains_context_rule():
    p = system_prompt_russian()
    assert "Отвечай ТОЛЬКО на основе предоставленного контекста" in p

