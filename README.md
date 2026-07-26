# Meta Analytics

Веб-приложение аналитики Dota 2: профиль игрока, история матчей, тренды,
активность за год, мета-гайды и AI Coach. Бэкенд — FastAPI, фронтенд — React,
подключённый прямо на странице через Babel (сборка не нужна).

## Структура

```
main.py                  весь бэкенд: роуты, интеграции, обработка статистики
requirements.txt         прямые зависимости
.env                     ключи и секреты (не коммитится)
.env.example             шаблон .env

templates/               Jinja2-шаблоны, отдаются роутами FastAPI
  home.html                лендинг            GET /
  index.html               дашборд            GET /dashboard

static/                  раздаётся как /static
  style.css
  script.js                корневой React-компонент App + монтирование
  components/              12 компонентов, каждый вешает себя в window.*
  vendor/                  react, react-dom, babel (локально, без CDN)
  data/                    heroes.json, items.json — офлайн-фолбэк справочников
  ranks/                   картинки медалей и звёзд рангов
```

Порядок подключения компонентов задан в `templates/index.html`; `script.js`
ждёт, пока все они появятся в `window`, и только потом монтирует приложение.

## Запуск

```bash
python -m venv .venv
```

```bash
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

```bash
.venv\Scripts\python.exe -m uvicorn main:app --reload --port 8000
```

Открыть http://127.0.0.1:8000

## Деплой

Репозиторий уже готов: есть `render.yaml`, `Procfile` и `Dockerfile`, приложение
слушает `$PORT` и корректно работает за TLS-прокси.

### Render (проще всего, есть бесплатный тариф)

1. Создать пустой репозиторий на GitHub и запушить проект:
   `git remote add origin <ссылка>` → `git push -u origin master`
2. На render.com: **New → Blueprint**, выбрать этот репозиторий. `render.yaml`
   подхватится сам.
3. В разделе **Environment** заполнить `STRATZ_API_TOKEN` и `GEMINI_API_KEY`.
   `SESSION_SECRET` Render сгенерирует сам.
4. Дождаться сборки — приложение будет доступно на `https://<имя>.onrender.com`.

На бесплатном тарифе сервис засыпает без трафика, первый запрос после простоя
занимает ~30 секунд. Для защиты диплома лучше открыть страницу заранее.

### Docker (любой хостинг или свой сервер)

```bash
docker build -t meta-analytics .
```

```bash
docker run -p 8000:8000 --env-file .env meta-analytics
```

### Что обязательно задать на хостинге

| Переменная | Зачем |
|---|---|
| `SESSION_SECRET` | подпись cookie; без неё логин слетает при каждом рестарте |
| `SESSION_HTTPS_ONLY=true` | cookie не уходит по открытому HTTP |
| `STRATZ_API_TOKEN` | предметы в карточках матчей |
| `GEMINI_API_KEY` | ответы AI Coach вместо локальных заготовок |

Секреты задаются переменными окружения хостинга. `.env` в репозиторий не
коммитится — он в `.gitignore`.

## Источники данных

| Источник | Роль | Если недоступен |
|---|---|---|
| STRATZ GraphQL | основной: матчи, предметы, ранг | падение на OpenDota |
| OpenDota REST | фолбэк + союзники и активность | ошибка загрузки профиля |
| Gemini | ответы AI Coach | коуч отвечает по локальным правилам |

Приложение спроектировано так, что отказ любого внешнего API не роняет
дашборд — включается следующий уровень фолбэка.

## API

| Метод | Путь | Назначение |
|---|---|---|
| GET | `/` | лендинг |
| GET | `/dashboard` | дашборд |
| GET | `/api/player/resolve?query=` | Steam ID / ссылка / ник → account_id |
| GET | `/api/player/{player_id}` | вся статистика игрока |
| POST | `/api/coach` | ответ AI Coach |
| GET | `/auth/steam/login` · `/auth/steam/callback` · `/auth/logout` | вход через Steam OpenID |

Ответы `/api/player/{id}` кешируются в памяти на час (`CACHE_TTL`).

## Замечания по окружению

`.env` нужно сохранять в UTF-8 **без BOM** — иначе первая переменная в файле
теряется. Загрузчик читает файл через `utf-8-sig`, так что BOM больше не ломает
конфиг, но лишний символ в начале лучше не заводить.

Запросы к STRATZ уходят с `User-Agent: STRATZ_API`. Браузерный User-Agent
там блокируется Cloudflare с 403 — менять этот заголовок не нужно.
