# Генератор черновиков карточек товаров

Прототип сервиса для B2B-каталога: принимает JSON контрольно-измерительного прибора,
обращается к OpenAI API и возвращает черновик карточки в JSON и Markdown. Технические
характеристики переносятся из входных данных кодом, а не генерируются моделью. Тексты требуют
проверки контент-менеджером перед публикацией.

## Возможности

- SEO-заголовок до 70 символов, описание 800–1 200 символов, 3–5 поисковых запросов и
  коммерческий блок.
- JSON-редактор, предпросмотр результата, вкладки Markdown/JSON и копирование.
- Характеристики и список отсутствующих данных строятся приложением из входа.
- Числа свободного текста сверяются с числами во входе; это предупреждающая эвристика, а не
  доказательство семантической достоверности.
- Одна попытка исправления при нарушении структуры или ограничений.
- OpenAI API вызывается только серверной частью; ключ не передаётся браузеру и не логируется.

## Требования

Python 3.11+, ключ OpenAI API для генерации. Docker Compose необязателен для приложения, но
рекомендован для тестирования. Инструкции подходят Windows (PowerShell), macOS и Linux.

## Установка

Команды выполняются из корня репозитория.

### Windows PowerShell

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
if (!(Test-Path .env)) { Copy-Item .env.example .env }
```

Если PowerShell запрещает активацию окружения, запускайте Python напрямую:
`.\.venv\Scripts\python.exe -m pip install -e ".[dev]"`.

### macOS / Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
if [ ! -f .env ]; then cp .env.example .env; fi
```

Если `.env` уже существует, сохраните его и добавьте/обновите в нём `OPENAI_*` настройки
вручную — не перезаписывайте файл.

## Настройка OpenAI API

Добавьте свой ключ в локальный `.env` (этот файл исключён из Git). Не храните ключ в исходном
коде, браузере или коммитах.

```dotenv
OPENAI_API_KEY=вставьте_свой_ключ
OPENAI_MODEL=gpt-4o-mini
OPENAI_BASE_URL=https://api.openai.com/v1
LLM_TIMEOUT_SECONDS=60
```

Без ключа приложение и `/health` запускаются, но генерация не выполняется. Тайм-аут должен быть
положительным; значение по умолчанию — 30 секунд.

## Запуск

```bash
python -m uvicorn app.main:app --reload
```

Windows без активированного venv:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

- Веб-интерфейс: <http://127.0.0.1:8000>
- Swagger/OpenAPI: <http://127.0.0.1:8000/docs>
- Проверка приложения: `GET /health` (без вызова OpenAI).
- Генерация: `POST /api/products/draft`.

Пример запроса — [`examples/product_1.json`](examples/product_1.json). macOS/Linux:

```bash
curl -X POST http://127.0.0.1:8000/api/products/draft \
  -H 'Content-Type: application/json' \
  --data-binary @examples/product_1.json
```

PowerShell:

```powershell
$body = Get-Content -Raw .\examples\product_1.json
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/products/draft `
  -ContentType 'application/json' -Body $body
```

Ответ включает `draft` и `markdown`. В `draft`: SEO-поля, исходные характеристики, запросы,
коммерческий блок, отсутствующие сведения и предупреждения. Ошибки: `422` — JSON/схема;
`503` — отсутствует ключ или сервис недоступен; `502` — невалидный ответ модели; `504` — тайм-аут.
Детали ответа провайдера пользователю не раскрываются.

## Проверки

Автотесты используют mock и не требуют API-ключа или сетевого доступа. Единый способ для Windows,
macOS и Linux — Docker Compose:

```bash
docker compose -p product-card-generator run --rm tests python -m pytest
docker compose -p product-card-generator run --rm tests python -m ruff check app tests
```

Или локально после установки dev-зависимостей:

```bash
python -m pytest
python -m ruff check app tests
python -m compileall app
```

## Файлы для заказчика и примеры

- [Пример результата для двух товаров](EXAMPLE_RESULTS.md).
- [Описание промпта и принятых решений](PROMPT_AND_DECISIONS.md).
- [Ограничения и возможные улучшения](LIMITATIONS_AND_IMPROVEMENTS.md).
- [Входной JSON: манометр DM 02](examples/product_1.json).
- [Входной JSON: мультиметр Fluke 117](examples/product_2.json); характеристики сверены с
  [официальным источником производителя](examples/SOURCES.md).

**Важно о примерах генерации.** Полные результаты в
[`examples/generated_results.md`](examples/generated_results.md) действительно были получены
моделью `qwen3:8b` до миграции; это исторические ответы Ollama, а не OpenAI. В текущем окружении
OpenAI-ключ не настроен, поэтому я не выдаю их за новые результаты OpenAI. После настройки ключа
выполните `python -m scripts.generate_examples`: файл будет обновлён только после успешной
генерации обоих товаров.

## Безопасность и ограничения

Входной товар передаётся OpenAI API. Не отправляйте данные, передачу которых выбранному
провайдеру запрещают правила заказчика. JSON Schema, валидаторы и числовая эвристика не исключают
семантически недостоверных фраз; свободный текст должен пройти ручную проверку.
Дополнительные детали — в [списке ограничений](LIMITATIONS_AND_IMPROVEMENTS.md).

Подробная архитектура и журнал работ: [`project.md`](project.md).
