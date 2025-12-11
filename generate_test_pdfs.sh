#!/usr/bin/env bash
# Скрипт для генерации всех тестовых PDF файлов для ApriliaFin

cd "/home/diamond/Work/BOTS/ApriliaFin"

echo "🚀 Генерируем тестовые PDF файлы для ApriliaFin..."
echo ""

# Генерируем все типы документов
for template in contratto garanzia carta approvazione; do
    echo "📄 Генерируем $template..."
    nix-shell -p python312 python312Packages.weasyprint python312Packages.reportlab python312Packages.pypdf2 python312Packages.pillow --run "python pdf_costructor.py $template"
    echo ""
done

echo "✅ Все тестовые PDF файлы сгенерированы!"
echo ""
echo "📋 Созданные файлы:"
ls -lh test_*.pdf 2>/dev/null || echo "⚠️ PDF файлы не найдены"




