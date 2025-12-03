#!/bin/bash
# Скрипт для быстрого запуска Streamlit приложения

echo "🚀 Запуск Streamlit приложения..."
echo ""

# Проверка установки зависимостей
if [ ! -d ".venv" ]; then
    echo "📦 Создание виртуального окружения..."
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
else
    source .venv/bin/activate
fi

echo "✅ Зависимости готовы"
echo ""
echo "🌐 Приложение будет доступно по адресу: http://localhost:8501"
echo ""
echo "Для остановки нажмите Ctrl+C"
echo ""

# Запуск Streamlit
streamlit run app.py
