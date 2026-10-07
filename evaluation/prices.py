"""Ориентировочные цены моделей, USD за 1M токенов (вход/выход).

Дата: 2026-10-06. Источники: публичные прайс-листы и обзоры (z.ai/docs.z.ai,
costgoat.com). Цены меняются — перед бюджетированием сверьтесь с провайдером.
Локальные модели (Ollama) тарифицируются только вашим железом.
"""

# (цена входа, цена выхода, комментарий)
PRICES = {
    "glm-4.6-flash": (0.0, 0.0, "бесплатный тир z.ai (с лимитами)"),
    "glm-4.6": (0.6, 2.2, "флагман z.ai предыдущего поколения"),
    "glm-5.x": (1.4, 4.4, "топовое поколение GLM, ориентировочно"),
    "gpt-4o-mini": (0.15, 0.6, "справочно, OpenAI"),
    "qwen2.5-coder:7b-local": (0.0, 0.0, "локально через Ollama, только cost железа"),
}

# Какой прайс применять к прогонам (для расчётной справочной стоимости)
MODEL_PRICE_KEY = {
    "l1_api_glm53_flash": "glm-4.6-flash",
    "l1_api_glm53": "glm-5.x",
    "l0_chat": "glm-5.x",
    "l2_mini": "glm-5.x",
    "l3_top": "glm-5.x",
    "l4_multi": "glm-5.x",
    "ref": None,  # человек, стоимость не считается
}


def cost_usd(run_id: str, tokens_in: int, tokens_out: int) -> float | None:
    key = MODEL_PRICE_KEY.get(run_id)
    if key is None:
        return None
    pin, pout, _ = PRICES[key]
    return round(tokens_in / 1e6 * pin + tokens_out / 1e6 * pout, 4)
