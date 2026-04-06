from __future__ import annotations

from typing import List, Tuple


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


def build_user_prompt(question: str, context_with_sources: List[Tuple[str, str]]) -> str:
    """
    context_with_sources: список (source_label, chunk_text)
    """
    context_blocks = []
    for label, chunk_text in context_with_sources:
        context_blocks.append(f"{label}\n{chunk_text}")

    context = "\n\n".join(context_blocks)
    return (
        f"Вопрос пользователя:\n{question}\n\n"
        f"Контекст (используй только его):\n{context}\n\n"
        "Сформируй ответ."
    )


