from __future__ import annotations

from typing import List, Tuple


ANSWER_MODE_INSTRUCTIONS = {
    "brief": "Дай краткий ответ: 3-6 предложений, только самое важное.",
    "detailed": "Дай подробный разбор: структурируй ответ, объясни основания и укажи важные нюансы.",
    "extract": "Работай в режиме извлечения данных: найди все релевантные требования, условия, сроки, ограничения или сущности и перечисли их списком. Не обобщай то, чего нет в контексте.",
}


def system_prompt_russian() -> str:
    # Важно: запретить модель выходить за рамки контекста снижает галлюцинации.
    return (
        "Ты — ассистент техподдержки. "
        "Отвечай ТОЛЬКО на основе предоставленного контекста. "
        "Если в контексте нет ответа или данных недостаточно — скажи: "
        "\"Информация недостаточна для ответа\". "
        "Не добавляй предположений и не выдумывай факты. "
        "При использовании фрагментов контекста указывай ссылки на источники в формате [source1], [source2] и т.д."
    )


def build_user_prompt(
    question: str,
    context_with_sources: List[Tuple[str, str]],
    answer_mode: str = "detailed",
) -> str:
    """
    context_with_sources: список (source_label, chunk_text)
    """
    context_blocks = []
    for label, chunk_text in context_with_sources:
        context_blocks.append(f"{label}\n{chunk_text}")

    context = "\n\n".join(context_blocks)
    mode_instruction = ANSWER_MODE_INSTRUCTIONS.get(answer_mode, ANSWER_MODE_INSTRUCTIONS["detailed"])
    return (
        f"Вопрос пользователя:\n{question}\n\n"
        f"Режим ответа:\n{mode_instruction}\n\n"
        f"Контекст (используй только его):\n{context}\n\n"
        "Сформируй ответ."
    )


