# LeaveLogger Bot

Discord-бот, который логирует уход и баны участников сервера.

## Возможности

- 📋 Логирование ухода участников в отдельный канал
- 🔨 Логирование банов в отдельный канал
- ⚙️ Настройка каналов и сообщений через команды `/setup` и `/config`
- 🎨 Настраиваемые шаблоны сообщений
- 🖼️ Красивые embed-сообщения с аватаром и деталями

## Быстрый старт

### 1. Создать бота на Discord Developer Portal

1. Зайди на https://discord.com/developers/applications
2. Нажми **New Application** → придумай имя
3. Перейди в **Bot** → **Add Bot**
4. Скопируй токен (**Reset Token** → **Copy**)
5. Включи привилегированные намерения:
   - **Server Members Intent** ✅
   - **Message Content Intent** (не обязательно, но полезно)
6. В **OAuth2 → URL Generator**:
   - Выбери scope: `bot`
   - Выбери permissions: `Manage Channels`, `View Channels`, `Send Messages`, `Manage Server`, `Kick Members`, `Ban Members`, `Moderate Members`
   - Скопируй ссылку и открой её — пригласи бота на сервер

### 2. Установка

```bash
cd discord-leave-logger
python -m venv venv
source venv/bin/activate   # Linux/Mac
# или: venv\Scripts\activate   # Windows
pip install -r requirements.txt
```

### 3. Запуск

**Linux/Mac:**
```bash
export DISCORD_BOT_TOKEN="your-token-here"
python bot.py
```

**Windows (cmd):**
```cmd
set DISCORD_BOT_TOKEN=your-token-here
python bot.py
```

**Windows (PowerShell):**
```powershell
$env:DISCORD_BOT_TOKEN="your-token-here"
python bot.py
```

## Команды

| Команда | Описание |
|---------|----------|
| `/setup` | Интерактивная настройка каналов и шаблонов |
| `/config` | Посмотреть текущие настройки |
| `/ping` | Проверить работу бота |

## Шаблоны сообщений

### Для ухода (`quit`):

Переменные:
- `{user}` — имя участника
- `{user_id}` — ID участника
- `{guild}` — имя сервера
- `{time}` — время ухода (ДД.ММ.ГГГГ ЧЧ:ММ)
- `{duration}` — сколько времени был на сервере

Пример:
```
👋 `{user}` покинул сервер `{guild}` | `{time}`
```

### Для бана (`ban`):

Переменные:
- `{user}` — имя участника
- `{user_id}` — ID участника
- `{guild}` — имя сервера
- `{time}` — время бана
- `{reason}` — причина бана

Пример:
```
🔨 `{user}` забанен на `{guild}` | `{time}` | Причина: `{reason}`
```

## Настройка через команду /setup

1. Напиши `/setup` в Discord (нужны права управления сервером)
2. Выбери канал для логов ухода
3. Выбери канал для логов банов
4. Настрой шаблон сообщения об уходе
5. Настрой шаблон сообщения о бане

Готово! Бот будет автоматически отправлять embed-сообщения при каждом событии.
