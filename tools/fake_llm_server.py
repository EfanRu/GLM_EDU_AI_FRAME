#!/usr/bin/env python3
"""Фейковый OpenAI-совместимый сервер для smoke-тестов L1/L2/L4 без ключа.

Отдаёт заранее зашитые ответы по номеру запроса: сначала «плохой» тест с
опечаткой + RUN_TESTS, затем исправленный. Позволяет проверить весь цикл
харнесса (запросы, парсинг, инструмент, лимит итераций, подсчёт usage).

    python fake_llm_server.py 8765     # порт
"""

import json
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

BAD = '''Первая версия:
```python
from ordercalc.discounts import apply_tier_discount

def test_gold():
    assert apply_tier_discount(1000, "gold") == 900
    assert apply_tier_discount(99999, "gold") == 89999  # опечатка, упадёт
```
RUN_TESTS'''

GOOD = '''Исправил:
```python
from ordercalc.discounts import apply_tier_discount

def test_gold():
    assert apply_tier_discount(1000, "gold") == 900
    assert apply_tier_discount(99999, "gold") == 89999.1 // 1
```
'''

REPLIES = [BAD, GOOD]


class Handler(BaseHTTPRequestHandler):
    count = 0

    def do_POST(self):  # noqa: N802
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        content = REPLIES[min(Handler.count, len(REPLIES) - 1)]
        Handler.count += 1
        msg = {"role": "assistant", "content": content}
        out = {"choices": [{"message": msg, "finish_reason": "stop"}],
               "usage": {"prompt_tokens": 1234 + Handler.count, "completion_tokens": 222}}
        data = json.dumps(out).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *_):
        pass


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    print(f"fake LLM on :{port}", file=sys.stderr)
    HTTPServer(("127.0.0.1", port), Handler).serve_forever()
