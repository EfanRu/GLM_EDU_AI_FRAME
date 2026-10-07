"""ordercalc — учебная библиотека расчёта заказов.

Модули:
- discounts — скидки по уровням лояльности и за объём
- split     — разбиение суммы заказа на части
- loyalty   — баллы лояльности и их срок жизни

Эталонное поведение описано в docstring каждой функции.
"""

from . import discounts, loyalty, split

__all__ = ["discounts", "split", "loyalty"]
