# HR-ассистент реестра резюме

Локальное MVP-приложение для HR: импортирует Excel-реестр кандидатов, читает файлы резюме, сопоставляет строки реестра с резюме, проверяет качество данных и выгружает обогащенный Excel.

## Технологии

- Python, FastAPI, Jinja2
- SQLite
- pandas + openpyxl
- PyMuPDF, python-docx
- rapidfuzz, Unidecode
- Обычные HTML/CSS-шаблоны, без React

## Быстрый старт

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Открыть в браузере:

```text
http://127.0.0.1:8000
```

## Порядок работы

1. Загрузить Excel-реестр на странице `Загрузка реестра`.
2. Приложение найдет лист `реестр`.
3. Исходные колонки сохраняются в SQLite без удаления.
4. Загрузить резюме на странице `Загрузка резюме`: PDF, DOCX, TXT.
5. Запустить сопоставление на панели или странице результатов.
6. Проверить спорные строки на странице `Ручная проверка`.
7. Проверить ошибки реестра на странице `Качество данных`.
8. Выгрузить обогащенный Excel на странице `Экспорт`.

## Опциональное ИИ-извлечение

ИИ-извлечение используется только как дополнительный слой:

- основной путь всегда начинается с локального парсинга PDF/DOCX/TXT;
- ИИ не вызывается для каждого файла;
- ИИ вызывается только если локальное извлечение не нашло ключевые поля или если результат сопоставления получил статус `review`;
- в ИИ отправляются только первые 6000 символов текста резюме;
- ответ ИИ кешируется по `file_hash`, повторная обработка того же файла не вызывает API повторно;
- API-ключ хранится только локально в `.env`;
- если ИИ недоступен или вернул невалидный JSON, приложение сохраняет локальное извлечение и пишет `processing_error`.

Настройки доступны на странице `Настройки ИИ`. Первый поддержанный провайдер: Gemini-совместимый.
Модель по умолчанию: `gemini-3-flash-preview`. Для более сложных резюме можно выбрать `gemini-3-pro-preview`.

## Результаты работы

- Исходный Excel-реестр: `project_files/source/registry/`
- Исходные резюме: `project_files/source/resumes/`
- Готовые резюме с номерами кандидатов: `project_files/ready/matched_resumes/`
- Готовый обогащенный Excel-реестр: `project_files/ready/registry/enriched_registry.xlsx`
- SQLite-база проекта: `project_files/data/hr_resume_registry.db`

Исходные файлы не перезаписываются.

## Логика сопоставления

Сигналы:

- точное совпадение email
- точное совпадение телефона
- fuzzy-сопоставление ФИО с учетом транслитерации
- сходство вакансии и позиции в резюме
- пересечение технических навыков между комментарием рекрутера и резюме
- совпадение компании
- сходство имени файла

Статусы:

- `matched`: score >= 90 и разрыв со вторым лучшим результатом >= 10
- `review`: score 70-89 или высокий score без уверенного разрыва
- `unmatched`: score < 70

Каждое сопоставление содержит `match_reason`.

## Проверки качества данных

- не заполнено ФИО
- не заполнена вакансия
- не заполнен статус
- статус не найден на листе `термины`
- статус `в работе` без даты последнего контакта
- прошедшая дата интервью без решения заказчика
- запрос кандидата не соответствует формату `3000р` или `3000$`
- не заполнен ответственный рекрутер

## Тесты

```bash
pytest
```

Текущие тесты покрывают:

- сопоставление через транслитерацию
- извлечение навыков
- расчет score и классификацию результата
- проверки качества данных
- две тестовые фикстуры: Арбузов Глеб / HLEB ARBUZAU и Чечуха Виталий / Vitali Chachukha

## Упаковка под Windows 11

Цель сборки: один установщик `HRResumeRegistryAssistantSetup.exe`. После установки пользователь запускает приложение из меню Пуск или ярлыка, локальный сервер поднимается автоматически, браузер открывается сам.

Метаданные установщика:

- продукт: `HR Resume Registry Assistant`;
- версия: `1.0.0`;
- разработчик: `Nikita Karpuk / AAR Group`;
- издатель: `AAR Group`.

Что входит в сборку:

- Python runtime внутри `.exe`;
- FastAPI/Uvicorn и все зависимости из `requirements.txt`;
- `app/`, `templates/`, `static/`;
- launcher, который находит свободный порт `8000-8010`, запускает сервис и открывает браузер.
- инструкция внутри мастера установки и файл `Инструкция.txt` после установки.

Пользовательские данные в установленной версии хранятся отдельно от программы:

```text
%LOCALAPPDATA%\HRResumeRegistryAssistant\project_files\
```

Там будут база SQLite, загруженные реестры, резюме, экспорт и локальный `.env` с настройками ИИ.

### Сборка на Windows 11

Требования к машине сборки:

- Windows 11 x64;
- Python 3.11+;
- Inno Setup 6 для создания установщика.

Команды в PowerShell из корня проекта:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\packaging\build_windows.ps1
```

Результаты:

```text
dist\HRResumeRegistryAssistant.exe
dist\installer\HRResumeRegistryAssistantSetup.exe
```

По умолчанию сборка считается успешной только если создан установщик:

```text
dist\installer\HRResumeRegistryAssistantSetup.exe
```

Если Inno Setup не установлен, скрипт остановится с ошибкой и установщик не будет считаться готовым. Установить Inno Setup:

```powershell
winget install JRSoftware.InnoSetup
```

Если нужен только standalone `.exe` без установщика, явно запустите:

```powershell
.\packaging\build_windows.ps1 -AllowStandaloneOnly
```

### Быстрая сборка через GitHub Actions

В репозитории есть workflow `.github/workflows/windows-installer.yml`.

1. Откройте GitHub → вкладка `Actions`.
2. Выберите `Build Windows installer`.
3. Нажмите `Run workflow`.
4. После завершения скачайте artifact `HRResumeRegistryAssistant-Windows`.

Внутри artifact должны быть:

```text
HRResumeRegistryAssistant.exe
HRResumeRegistryAssistantSetup.exe
INSTALL_INSTRUCTIONS.txt
```

Важно: архив `packaging/Архив.zip` не является установщиком. Это набор файлов упаковки. Пользователю Windows нужно передавать именно `HRResumeRegistryAssistantSetup.exe`.

### Проверка установщика

1. Установить `dist\installer\HRResumeRegistryAssistantSetup.exe`.
2. Запустить `HR Resume Registry Assistant`.
3. Должен открыться браузер с адресом `http://127.0.0.1:8000` или соседним свободным портом.
4. Загрузить тестовый Excel-реестр и 1-2 резюме.
5. Проверить, что экспорт создается в:

```text
%LOCALAPPDATA%\HRResumeRegistryAssistant\project_files\ready\registry\
```
