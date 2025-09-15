# telegram_document_bot.py — Полный корректный код бота с авто-сбросом на /start
# -----------------------------------------------------------------------------
# Генератор PDF-документов Intesa Sanpaolo:
#   /contratto — кредитный договор
#   /garanzia  — письмо о гарантийном взносе
#   /carta     — письмо о выпуске карты
# -----------------------------------------------------------------------------
# Зависимости:
#   pip install python-telegram-bot==20.* reportlab
# -----------------------------------------------------------------------------
import logging
import os
import re
from io import BytesIO
from decimal import Decimal, ROUND_HALF_UP

from telegram import Update, InputFile, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application, CommandHandler, ConversationHandler, MessageHandler, ContextTypes, filters,
)

from weasyprint import HTML
from jinja2 import Template, FileSystemLoader, Environment
from datetime import datetime
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from PyPDF2 import PdfReader, PdfWriter
from PIL import Image


# ---------------------- Настройки ------------------------------------------
TOKEN = os.getenv("BOT_TOKEN", "YOUR_TOKEN_HERE")
DEFAULT_TAN = 7.86
DEFAULT_TAEG = 8.30
GARANZIA_COST = 180.0
CARTA_COST = 120.0
LOGO_PATH = "logo_intesa.png"      # логотип 4×4 см
SIGNATURE_PATH = "signature.png"   # подпись 4×2 см
HEADER_LOGO_PATH = "Intesa_Sanpaolo_logo.jpg"  # логотип в заголовке
FONT_PATH = "RobotoMono-VariableFont_wght.ttf"  # основной шрифт


logging.basicConfig(format="%(asctime)s — %(levelname)s — %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# ------------------ Состояния Conversation -------------------------------
CHOOSING_DOC, ASK_NAME, ASK_AMOUNT, ASK_DURATION, ASK_TAN, ASK_TAEG = range(6)

# ---------------------- Утилиты -------------------------------------------
def money(val: float) -> str:
    """Формат суммы: € 0.00"""
    return f"€ {Decimal(val).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)}"


def monthly_payment(amount: float, months: int, annual_rate: float) -> float:
    """Аннуитетный расчёт ежемесячного платежа"""
    r = (annual_rate / 100) / 12
    if r == 0:
        return round(amount / months, 2)
    num = amount * r * (1 + r) ** months
    den = (1 + r) ** months - 1
    return round(num / den, 2)


def init_jinja_env():
    """Инициализация Jinja2 окружения для шаблонов"""
    env = Environment(loader=FileSystemLoader('.'))
    return env


def format_money(amount: float) -> str:
    """Форматирование суммы в евро"""
    return f"€ {amount:,.2f}".replace(',', ' ')


def format_date() -> str:
    """Получение текущей даты в итальянском формате"""
    return datetime.now().strftime("%d/%m/%Y")


def render_template(template_name: str, **kwargs) -> str:
    """Рендеринг HTML шаблона с переданными данными"""
    env = init_jinja_env()
    template = env.get_template(template_name)
    return template.render(**kwargs)

# ---------------------- PDF-строители с WeasyPrint -------------------------
def build_contratto(data: dict) -> BytesIO:
    """PDF конструктор с исправленной разметкой и изображениями через ReportLab - СТРОГО 2 СТРАНИЦЫ!"""
    # Читаем оригинальный HTML шаблон
    with open('contratto.html', 'r', encoding='utf-8') as f:
        html = f.read()
    
    # Добавляем CSS для правильной разметки - СТРОГО 2 СТРАНИЦЫ!
    css_fixes = """
    <style>
    @page {
        size: A4;
        margin: 6mm;  /* Уменьшенный отступ для экономии места */
        border: 3pt solid #f17321;  /* Оранжевая рамка на каждой странице */
        padding: 3mm;  /* Отступ от рамки до контента */
    }
    
    body {
        font-family: "Roboto Mono", monospace;
        font-size: 10pt;  /* Возвращаем нормальный размер шрифта */
        line-height: 1.0;  /* Нормальная высота строки */
        margin: 0;
        padding: 0;
    }
    
    /* КРИТИЧНО: Убираем ВСЕ рамки из элементов, оставляем только @page */
    .c20 {
        border: none !important;
        padding: 3mm !important;  /* Нормальные отступы */
        margin: 0 !important;
    }
    
    /* СТРОГИЙ КОНТРОЛЬ: МАКСИМУМ 2 СТРАНИЦЫ */
    * {
        page-break-after: avoid !important;
        page-break-inside: avoid !important;
    }
    
    .page-break {
        page-break-before: always !important;
        page-break-after: avoid !important;
        height: 0 !important;
        margin: 0 !important;
        padding: 0 !important;
    }
    
    /* ВОССТАНАВЛИВАЕМ НОРМАЛЬНЫЕ ОТСТУПЫ В ТЕКСТЕ */
    p {
        margin: 2pt 0 !important;  /* Нормальные отступы между параграфами */
        padding: 0 !important;
        line-height: 1.0 !important;
    }
    
    div {
        margin: 0 !important;
        padding: 0 !important;
    }
    
    table {
        margin: 3pt 0 !important;  /* Нормальные отступы для таблиц */
        font-size: 10pt !important;  /* Нормальный размер шрифта */
    }
    
    /* Убираем Google Docs стили */
    .c22 {
        max-width: none !important;
        padding: 0 !important;
        margin: 0 !important;
        border: none !important;
    }
    
    .c14, .c25 {
        margin-left: 0 !important;
    }
    
    /* НОРМАЛЬНЫЕ ЗАГОЛОВКИ С ОТСТУПАМИ */
    .c15 {
        font-size: 14pt !important;  /* Возвращаем нормальный размер */
        margin: 4pt 0 !important;    /* Нормальные отступы */
        font-weight: 700 !important;
    }
    
    .c10 {
        font-size: 12pt !important;  /* Возвращаем нормальный размер */
        margin: 3pt 0 !important;    /* Нормальные отступы */
        font-weight: 700 !important;
    }
    
    /* ТОЛЬКО пустые элементы делаем невидимыми - НЕ ТРОГАЕМ текстовые! */
    .c6:empty {
        height: 0pt !important;
        margin: 0 !important;
        padding: 0 !important;
    }
    
    /* Нормальные отступы для списков */
    .c3 {
        margin: 1pt 0 !important;
    }
    
    /* Запрещаем создание страниц после 2-й */
    @page:nth(3) {
        display: none !important;
    }
    
    /* УБИРАЕМ КРАСНОЕ ВЫДЕЛЕНИЕ ТЕКСТА */
    .c1, .c16 {
        background-color: transparent !important;
        background: none !important;
    }
    
    /* СЕТКА ДЛЯ ПОЗИЦИОНИРОВАНИЯ ИЗОБРАЖЕНИЙ 25x35 - НА КАЖДОЙ СТРАНИЦЕ */
    .grid-overlay {
        position: absolute;
        top: 0;
        left: 0;
        width: 210mm;  /* Полная ширина A4 */
        height: 297mm; /* Полная высота A4 */
        pointer-events: none;
        z-index: 1000;
        opacity: 0; /* 0% прозрачности - невидимая */
    }
    
    /* Сетка для каждой страницы отдельно */
    .page-grid {
        position: absolute;
        top: 0;
        left: 0;
        width: 100%;
        height: 100vh;
        pointer-events: none;
        z-index: 1000;
        opacity: 0.3;
    }
    
    .grid-cell {
        position: absolute;
        border: none;
        background-color: transparent;
        display: none;
        font-size: 6pt;
        font-weight: bold;
        color: transparent;
        font-family: Arial, sans-serif;
        box-sizing: border-box;
    }
    
    /* Позиционирование относительно сетки */
    .positioned-image {
        position: absolute;
        z-index: 500;
    }
    </style>
    """
    
    # Вставляем CSS после тега <head>
    html = html.replace('<head>', f'<head>{css_fixes}')
    
    
    # ГЕНЕРИРУЕМ СЕТКУ 25x35 ДЛЯ ПОЗИЦИОНИРОВАНИЯ
    def generate_grid():
        """Генерирует HTML сетку 25x35 с нумерацией для A4"""
        grid_html = '<div class="grid-overlay">\n'
        
        # Размеры страницы A4 в миллиметрах
        page_width_mm = 210  # A4 ширина
        page_height_mm = 297  # A4 высота
        
        cell_width_mm = page_width_mm / 25  # 8.4mm на ячейку
        cell_height_mm = page_height_mm / 35  # 8.49mm на ячейку
        
        cell_number = 1
        
        for row in range(35):
            for col in range(25):
                x_mm = col * cell_width_mm
                y_mm = row * cell_height_mm
                
                grid_html += f'''    <div class="grid-cell" style="
                    left: {x_mm:.1f}mm; 
                    top: {y_mm:.1f}mm; 
                    width: {cell_width_mm:.1f}mm; 
                    height: {cell_height_mm:.1f}mm;">
                    {cell_number}
                </div>\n'''
                
                cell_number += 1
        
        grid_html += '</div>\n'
        return grid_html
    
    # КРИТИЧНО: СНАЧАЛА убираем старые изображения, ПОТОМ добавляем новые!
    import re
    
    # Очистка HTML для contratto (как в fix_layout.py)
    # 1. ПОЛНОСТЬЮ убираем блок с 3 изображениями между разделами
    middle_images_pattern = r'<p class="c3"><span style="overflow: hidden[^>]*><img alt="" src="images/image1\.png"[^>]*></span><span style="overflow: hidden[^>]*><img alt="" src="images/image2\.png"[^>]*></span><span style="overflow: hidden[^>]*><img alt="" src="images/image4\.png"[^>]*></span></p>'
    html = re.sub(middle_images_pattern, '', html)

    # 2. Убираем ВСЕ пустые div и параграфы в конце
    html = re.sub(r'<div><p class="c6 c18"><span class="c7 c23"></span></p></div>$', '', html)
    html = re.sub(r'<p class="c3 c6"><span class="c7 c12"></span></p>$', '', html)
    html = re.sub(r'<p class="c6 c24"><span class="c7 c12"></span></p>$', '', html)
    
    # 3. Убираем избыточные пустые строки между разделами (НЕ в тексте!)
    html = re.sub(r'(<p class="c3 c6"><span class="c7 c12"></span></p>\s*){2,}', '<p class="c3 c6"><span class="c7 c12"></span></p>', html)
    html = re.sub(r'(<p class="c24 c6"><span class="c7 c12"></span></p>\s*)+', '', html)
    
    # 4. Убираем лишние высоты из таблиц
    html = html.replace('class="c13"', 'class="c13" style="height: auto !important;"')
    html = html.replace('class="c19"', 'class="c19" style="height: auto !important;"')
    
    # 5. Принудительно разбиваем на 2 страницы: после раздела 2 (Agevolazioni)
    agevolazioni_end = html.find('• Bonifici SEPA e SDD gratuiti, senza spese aggiuntive')
    if agevolazioni_end != -1:
        # Находим конец этого раздела
        next_section_start = html.find('</td></tr></table>', agevolazioni_end)
        if next_section_start != -1:
            # Вставляем разрыв страницы
            html = html[:next_section_start] + '</td></tr></table><div class="page-break"></div>' + html[next_section_start+len('</td></tr></table>'):]

    # Добавляем сетку в body
    grid_overlay = generate_grid()
    html = html.replace('<body class="c22 doc-content">', f'<body class="c22 doc-content">\n{grid_overlay}')
    
    # Заменяем XXX на реальные данные (ТОЧНО КАК В fix_layout.py!)
    replacements = [
        ('>XXX<', f">{data['name']}<"),  # имя клиента (первое)
        ('>XXX<', f">{format_money(data['amount'])}<"),  # сумма кредита
        ('>XXX<', f">{data['tan']:.2f}%<"),  # TAN
        ('>XXX<', f">{data['taeg']:.2f}%<"),  # TAEG  
        ('>XXX<', f">{data['duration']} mesi<"),  # срок
        ('>XXX<', f">{format_money(data['payment'])}<"),  # платеж
        ('11/06/2025', format_date()),  # дата
        ('>XXX<', f">{data['name']}<"),  # имя в подписи
    ]
    
    for old, new in replacements:
        html = html.replace(old, new, 1)  # заменяем по одному
    
    # Общая очистка для всех шаблонов
    # Убираем лишние высоты из таблиц
    html = html.replace('class="c5"', 'class="c5" style="height: auto !important;"')
    html = html.replace('class="c9"', 'class="c9" style="height: auto !important;"')
    
    # Конвертируем в PDF через WeasyPrint
    pdf_bytes = HTML(string=html).write_pdf()
    
    # НАКЛАДЫВАЕМ ИЗОБРАЖЕНИЯ ЧЕРЕЗ REPORTLAB
    try:
        # Создаем overlay с изображениями
        overlay_buffer = BytesIO()
        overlay_canvas = canvas.Canvas(overlay_buffer, pagesize=A4)
        
        # Получаем размер изображения для масштабирования
        img = Image.open("company.png")
        img_width_mm = img.width * 0.264583  # пиксели в мм (96 DPI)
        img_height_mm = img.height * 0.264583
        
        # Увеличиваем на 20% (было уменьшение в 2 раза, теперь увеличиваем)
        scaled_width = (img_width_mm / 2) * 1.2  # +20% к уменьшенному размеру
        scaled_height = (img_height_mm / 2) * 1.2
        
        # Размер ячейки для расчета сдвигов
        cell_width_mm = 210/25  # 8.4mm
        cell_height_mm = 297/35  # 8.49mm
        
        # Страница 1: изображение в квадрате 52 + сдвиг (влево на 0.5, вниз на 0.5)
        # Квадрат 52 = строка 2, колонка 1 (нумерация с 1)
        row_52 = (52 - 1) // 25 + 1  # строка 2 + 1 = строка 3
        col_52 = (52 - 1) % 25 + 1   # колонка 1 + 1 = колонка 2
        
        # Левая грань квадрата + сдвиги (ReportLab считает от НИЗА страницы!)
        x_52 = (col_52 * cell_width_mm - 0.5 * cell_width_mm) * mm  # влево на пол клетки
        y_52 = (297 - (row_52 * cell_height_mm + cell_height_mm) - 0.5 * cell_height_mm) * mm  # вниз на пол клетки
        
        # Рисуем с увеличением на 20% и сохранением прозрачности
        overlay_canvas.drawImage("company.png", x_52, y_52, 
                               width=scaled_width*mm, height=scaled_height*mm, 
                               mask='auto', preserveAspectRatio=True)
        
        # Добавляем logo.png в квадрат 71 первой страницы с уменьшением на 20% и сдвигом влево на 2 клетки
        # Квадрат 71 = строка 2, колонка 20 (71-1=70, 70//25=2, 70%25=20)
        row_71 = (71 - 1) // 25  # строка 2
        col_71 = (71 - 1) % 25   # колонка 20
        
        # Получаем размер logo.png для уменьшения на 20%
        logo_img = Image.open("logo.png")
        logo_width_mm = logo_img.width * 0.264583  # пиксели в мм (96 DPI)
        logo_height_mm = logo_img.height * 0.264583
        
        # Уменьшаем в 9 раз (3 * 3)
        logo_scaled_width = logo_width_mm / 9  # уменьшение в 9 раз
        logo_scaled_height = logo_height_mm / 9
        
        # Левая грань квадрата 71 + сдвиг вправо на 4 клетки и вниз на 1.25 клетки
        x_71 = (col_71 - 2 + 4) * cell_width_mm * mm  # было влево на 2, теперь вправо на 4
        y_71 = (297 - (row_71 * cell_height_mm + cell_height_mm) - 1.25 * cell_height_mm) * mm  # вниз на 1.25 клетки
        
        # Рисуем logo.png с уменьшением на 20%
        overlay_canvas.drawImage("logo.png", x_71, y_71, 
                               width=logo_scaled_width*mm, height=logo_scaled_height*mm,
                               mask='auto', preserveAspectRatio=True)
        
        # Добавляем нумерацию страницы 1 между клетками 862 и 863 (аналогично второй странице)
        # Используем те же координаты что и для второй страницы
        row_862_p1 = (862 - 1) // 25  # строка 34
        col_862_p1 = (862 - 1) % 25   # колонка 11
        
        # Позиция между клетками 862 и 863 (на границе) + сдвиг на полклетки вправо и на 1/4 клетки вниз
        x_page_num_p1 = (col_862_p1 + 1 + 0.5) * cell_width_mm * mm  # граница между клетками + полклетки вправо
        y_page_num_p1 = (297 - (row_862_p1 * cell_height_mm + cell_height_mm/2) - 0.25 * cell_height_mm) * mm  # середина строки + 1/4 клетки вниз
        
        # Рисуем цифру 1 размером 10pt
        overlay_canvas.setFillColorRGB(0, 0, 0)  # Черный цвет
        overlay_canvas.setFont("Helvetica", 10)
        overlay_canvas.drawString(x_page_num_p1-2, y_page_num_p1-2, "1")
        
        overlay_canvas.showPage()
        
        # Страница 2: Добавляем logo.png точь в точь как на первой странице
        # Сетка убрана - невидимая (0% прозрачности)
        
        # Добавляем logo.png на вторую страницу точь в точь как на первой
        # Используем те же координаты и размеры что и на первой странице
        overlay_canvas.drawImage("logo.png", x_71, y_71, 
                               width=logo_scaled_width*mm, height=logo_scaled_height*mm,
                               mask='auto', preserveAspectRatio=True)
        
        # Добавляем sing_2.png в квадрат 637 второй страницы с уменьшением в 7 раз
        # Квадрат 637 = строка 25, колонка 12 (637-1=636, 636//25=25, 636%25=11)
        row_637 = (637 - 1) // 25  # строка 25
        col_637 = (637 - 1) % 25   # колонка 11
        
        # Получаем размер sing_2.png для уменьшения в 7 раз
        sing_img = Image.open("sing_2.png")
        sing_width_mm = sing_img.width * 0.264583  # пиксели в мм (96 DPI)
        sing_height_mm = sing_img.height * 0.264583
        
        # Уменьшаем в 7 раз и дополнительно на 10%
        sing_scaled_width = (sing_width_mm / 7) * 0.9  # -10%
        sing_scaled_height = (sing_height_mm / 7) * 0.9
        
        # Левая грань квадрата 637 + сдвиг влево на 1 клетку и вверх на 0.5 клетки (было вниз на 0.5)
        x_637 = (col_637 - 1) * cell_width_mm * mm  # влево на 1 клетку
        y_637 = (297 - (row_637 * cell_height_mm + cell_height_mm) + 0.5 * cell_height_mm) * mm  # вверх на 0.5 клетки (было вниз)
        
        # Рисуем sing_2.png с уменьшением в 7 раз и сохранением прозрачности
        overlay_canvas.drawImage("sing_2.png", x_637, y_637, 
                               width=sing_scaled_width*mm, height=sing_scaled_height*mm,
                               mask='auto', preserveAspectRatio=True)
        
        # Добавляем sing_1.png в квадрат 628 второй страницы с уменьшением в 6 раз
        # Квадрат 628 = строка 25, колонка 3 (628-1=627, 627//25=25, 627%25=2)
        row_628 = (628 - 1) // 25  # строка 25
        col_628 = (628 - 1) % 25   # колонка 2
        
        # Получаем размер sing_1.png для уменьшения в 6 раз
        sing1_img = Image.open("sing_1.png")
        sing1_width_mm = sing1_img.width * 0.264583  # пиксели в мм (96 DPI)
        sing1_height_mm = sing1_img.height * 0.264583
        
        # Уменьшаем в 6 раз и увеличиваем на 10%
        sing1_scaled_width = (sing1_width_mm / 6) * 1.1  # +10%
        sing1_scaled_height = (sing1_height_mm / 6) * 1.1
        
        # Левая грань квадрата 628 + сдвиг на 1 клетку вниз (было 2, сместили на 1 вверх)
        x_628 = col_628 * cell_width_mm * mm
        y_628 = (297 - (row_628 * cell_height_mm + cell_height_mm) - 1 * cell_height_mm) * mm  # вниз на 1 клетку (было 2)
        
        # Рисуем sing_1.png с уменьшением в 6 раз и сохранением прозрачности
        overlay_canvas.drawImage("sing_1.png", x_628, y_628, 
                               width=sing1_scaled_width*mm, height=sing1_scaled_height*mm,
                               mask='auto', preserveAspectRatio=True)
        
        # Добавляем seal.png в квадрат 682 второй страницы с уменьшением в 7 раз
        # Квадрат 682 = строка 27, колонка 7 (682-1=681, 681//25=27, 681%25=6)
        row_682 = (682 - 1) // 25  # строка 27
        col_682 = (682 - 1) % 25   # колонка 6
        
        # Получаем размер seal.png для уменьшения в 7 раз
        seal_img = Image.open("seal.png")
        seal_width_mm = seal_img.width * 0.264583  # пиксели в мм (96 DPI)
        seal_height_mm = seal_img.height * 0.264583
        
        # Уменьшаем в 7 раз
        seal_scaled_width = seal_width_mm / 7
        seal_scaled_height = seal_height_mm / 7
        
        # Левая грань квадрата 682 + сдвиг вверх на 1 клетку
        x_682 = col_682 * cell_width_mm * mm
        y_682 = (297 - (row_682 * cell_height_mm + cell_height_mm)) * mm + cell_height_mm * mm  # +1 клетка вверх
        
        # Рисуем seal.png с уменьшением в 7 раз и сохранением прозрачности
        overlay_canvas.drawImage("seal.png", x_682, y_682, 
                               width=seal_scaled_width*mm, height=seal_scaled_height*mm,
                               mask='auto', preserveAspectRatio=True)
        
        # Добавляем нумерацию страницы 2 между клетками 862 и 863
        # Квадрат 862 = строка 34, колонка 12 (862-1=861, 861//25=34, 861%25=11)
        # Квадрат 863 = строка 34, колонка 13 (863-1=862, 862//25=34, 862%25=12)
        row_862 = (862 - 1) // 25  # строка 34
        col_862 = (862 - 1) % 25   # колонка 11
        col_863 = (863 - 1) % 25   # колонка 12
        
        # Позиция между клетками 862 и 863 (на границе) + сдвиг на полклетки вправо и на 1/4 клетки вниз
        x_page_num = (col_862 + 1 + 0.5) * cell_width_mm * mm  # граница между клетками + полклетки вправо
        y_page_num = (297 - (row_862 * cell_height_mm + cell_height_mm/2) - 0.25 * cell_height_mm) * mm  # середина строки + 1/4 клетки вниз
        
        # Рисуем цифру 2 размером 10pt
        overlay_canvas.setFillColorRGB(0, 0, 0)  # Черный цвет
        overlay_canvas.setFont("Helvetica", 10)
        overlay_canvas.drawString(x_page_num-2, y_page_num-2, "2")
        
        overlay_canvas.save()
        
        # Объединяем PDF с overlay
        overlay_buffer.seek(0)
        base_pdf = PdfReader(BytesIO(pdf_bytes))
        overlay_pdf = PdfReader(overlay_buffer)
        
        writer = PdfWriter()
        
        # Накладываем изображения на каждую страницу
        for i, page in enumerate(base_pdf.pages):
            if i < len(overlay_pdf.pages):
                page.merge_page(overlay_pdf.pages[i])
            writer.add_page(page)
        
        # Сохраняем финальный PDF
        final_buffer = BytesIO()
        writer.write(final_buffer)
        final_pdf_bytes = final_buffer.getvalue()
        
        buf = BytesIO(final_pdf_bytes)
        buf.seek(0)
        return buf
        
    except Exception as e:
        # Если ошибка с ReportLab, возвращаем обычный PDF
        print(f"Ошибка ReportLab: {e}")
    buf = BytesIO(pdf_bytes)
    buf.seek(0)
    return buf


def build_lettera_garanzia(name: str) -> BytesIO:
    """Генерация PDF письма о гарантии с исправленной разметкой и изображениями через ReportLab - СТРОГО 1 СТРАНИЦА!"""
    # Читаем оригинальный HTML шаблон
    with open('garanzia.html', 'r', encoding='utf-8') as f:
        html = f.read()
    
    # Добавляем CSS для правильной разметки - СТРОГО 1 СТРАНИЦА!
    css_fixes = """
    <style>
    @page {
        size: A4;
        margin: 3mm;  /* Минимальный отступ - рамка ближе к краям */
        border: 3pt solid #f17321;  /* Оранжевая рамка */
        padding: 5mm;  /* Отступ от рамки до контента */
    }
    
    body {
        font-family: "Roboto Mono", monospace;
        font-size: 11pt;  /* Увеличиваем размер шрифта */
        line-height: 1.2;  /* Увеличиваем межстрочный интервал */
        margin: 0;
        padding: 0;
    }
    
    /* СТРОГИЙ КОНТРОЛЬ: ТОЛЬКО 1 СТРАНИЦА для garanzia */
    * {
        page-break-after: avoid !important;
        page-break-inside: avoid !important;
        page-break-before: avoid !important;
    }
    
    /* Запрещаем создание страниц после 1-й */
    @page:nth(2) {
        display: none !important;
    }
    
    /* Убираем рамки из элементов, оставляем только @page */
    .c9 {
        border: none !important;
        padding: 8pt !important;
        margin: 0 !important;
        width: 100% !important;  /* Занимаем всю ширину */
    }
    
    /* Компактная таблица на всю ширину */
    .c8 {
        margin: 0 !important;
        width: 100% !important;
        margin-left: 0 !important;  /* Убираем отступ слева */
    }
    
    /* Основной контейнер документа */
    .c12 {
        max-width: none !important;
        padding: 0 !important;
        margin: 0 !important;
        width: 100% !important;
    }
    
    /* Параграфы с нормальными отступами */
    .c6 {
        margin: 8pt 0 !important;  /* Возвращаем отступы между абзацами */
        text-align: left !important;
        width: 100% !important;
    }
    
    /* Заголовки */
    .c2 {
        margin: 12pt 0 8pt 0 !important;  /* Отступы для заголовков */
        text-align: left !important;
    }
    
    /* Списки */
    .c0 {
        margin: 4pt 0 4pt 36pt !important;  /* Отступы для списков */
        text-align: left !important;
    }
    
    /* Убираем красное выделение */
    .c15 {
        background-color: transparent !important;
        background: none !important;
    }
    
    </style>
    """
    
    # Вставляем CSS после тега <head>
    html = html.replace('<head>', f'<head>{css_fixes}')
    
    # Убираем ВСЕ изображения из garanzia - они создают лишние страницы
    # Убираем логотип в начале
    logo_pattern = r'<p class="c6"><span style="overflow: hidden[^>]*><img alt="" src="images/image2\.png"[^>]*></span></p>'
    html = re.sub(logo_pattern, '', html)
    
    # Убираем изображения в конце (печать и подпись)
    seal_pattern = r'<p class="c6"><span style="overflow: hidden[^>]*><img alt="" src="images/image1\.png"[^>]*></span></p>'
    html = re.sub(seal_pattern, '', html)
    
    signature_pattern = r'<span style="overflow: hidden[^>]*><img alt="" src="images/image3\.png"[^>]*></span>'
    html = re.sub(signature_pattern, '', html)
    
    # Общая очистка для всех шаблонов
    # Убираем лишние высоты из таблиц
    html = html.replace('class="c5"', 'class="c5" style="height: auto !important;"')
    html = html.replace('class="c9"', 'class="c9" style="height: auto !important;"')
    
    print("🗑️ Удалены все изображения из garanzia для предотвращения лишних страниц")
    
    # Заменяем XXX на реальные данные
    html = html.replace('XXX', name)
    
    # Конвертируем в PDF через WeasyPrint
    pdf_bytes = HTML(string=html).write_pdf()
    
    # НАКЛАДЫВАЕМ ИЗОБРАЖЕНИЯ ЧЕРЕЗ REPORTLAB
    try:
        # Создаем overlay с изображениями и сеткой
        overlay_buffer = BytesIO()
        overlay_canvas = canvas.Canvas(overlay_buffer, pagesize=A4)
        
        # Размер ячейки для расчета сдвигов
        cell_width_mm = 210/25  # 8.4mm
        cell_height_mm = 297/35  # 8.49mm
        
        # Добавляем company.png в 27-й клетке + 5 клеток вправо с уменьшением в 1.92 раза
        company_img = Image.open("company.png")
        company_width_mm = company_img.width * 0.264583  # пиксели в мм (96 DPI)
        company_height_mm = company_img.height * 0.264583
        
        # Уменьшаем в 1.92 раза (было 2.5, увеличиваем на 30%)
        company_scaled_width = company_width_mm / 1.92
        company_scaled_height = company_height_mm / 1.92
        
        # Клетка 27 = строка 1, колонка 1 (27-1=26, 26//25=1, 26%25=1)
        row_27 = (27 - 1) // 25  # строка 1
        col_27 = (27 - 1) % 25   # колонка 1
        
        # Центр клетки 27 + смещение на 5 клеток вправо
        x_27_center = (col_27 + 5 + 0.5) * cell_width_mm * mm  # центр по X + 5 клеток вправо
        y_27_center = (297 - (row_27 + 0.5) * cell_height_mm) * mm  # центр по Y (ReportLab от низа)
        
        # Смещаем на половину размера изображения для центрирования
        x_27 = x_27_center - (company_scaled_width * mm / 2)
        y_27 = y_27_center - (company_scaled_height * mm / 2)
        
        # Рисуем company.png в центре 27-й клетки
        overlay_canvas.drawImage("company.png", x_27, y_27, 
                               width=company_scaled_width*mm, height=company_scaled_height*mm,
                               mask='auto', preserveAspectRatio=True)
        
        # Добавляем seal.png в центр 590-й клетки с уменьшением в 5 раз
        seal_img = Image.open("seal.png")
        seal_width_mm = seal_img.width * 0.264583  # пиксели в мм (96 DPI)
        seal_height_mm = seal_img.height * 0.264583
        
        # Уменьшаем в 5 раз
        seal_scaled_width = seal_width_mm / 5
        seal_scaled_height = seal_height_mm / 5
        
        # Клетка 590 = строка 23, колонка 14 (590-1=589, 589//25=23, 589%25=14)
        row_590 = (590 - 1) // 25  # строка 23
        col_590 = (590 - 1) % 25   # колонка 14
        
        # Центр клетки 590
        x_590_center = (col_590 + 0.5) * cell_width_mm * mm  # центр по X
        y_590_center = (297 - (row_590 + 0.5) * cell_height_mm) * mm  # центр по Y (ReportLab от низа)
        
        # Смещаем на половину размера изображения для центрирования
        x_590 = x_590_center - (seal_scaled_width * mm / 2)
        y_590 = y_590_center - (seal_scaled_height * mm / 2)
        
        # Рисуем seal.png в центре 590-й клетки
        overlay_canvas.drawImage("seal.png", x_590, y_590, 
                               width=seal_scaled_width*mm, height=seal_scaled_height*mm,
                               mask='auto', preserveAspectRatio=True)
        
        # Добавляем sing_1.png в центр 593-й клетки с уменьшением в 5 раз
        sing1_img = Image.open("sing_1.png")
        sing1_width_mm = sing1_img.width * 0.264583  # пиксели в мм (96 DPI)
        sing1_height_mm = sing1_img.height * 0.264583
        
        # Уменьшаем в 5 раз
        sing1_scaled_width = sing1_width_mm / 5
        sing1_scaled_height = sing1_height_mm / 5
        
        # Клетка 593 = строка 23, колонка 17 (593-1=592, 592//25=23, 592%25=17)
        row_593 = (593 - 1) // 25  # строка 23
        col_593 = (593 - 1) % 25   # колонка 17
        
        # Центр клетки 593
        x_593_center = (col_593 + 0.5) * cell_width_mm * mm  # центр по X
        y_593_center = (297 - (row_593 + 0.5) * cell_height_mm) * mm  # центр по Y (ReportLab от низа)
        
        # Смещаем на половину размера изображения для центрирования
        x_593 = x_593_center - (sing1_scaled_width * mm / 2)
        y_593 = y_593_center - (sing1_scaled_height * mm / 2)
        
        # Рисуем sing_1.png в центре 593-й клетки
        overlay_canvas.drawImage("sing_1.png", x_593, y_593, 
                               width=sing1_scaled_width*mm, height=sing1_scaled_height*mm,
                               mask='auto', preserveAspectRatio=True)
        
        overlay_canvas.save()
        
        # Объединяем PDF с overlay
        overlay_buffer.seek(0)
        base_pdf = PdfReader(BytesIO(pdf_bytes))
        overlay_pdf = PdfReader(overlay_buffer)
        
        writer = PdfWriter()
        
        # Накладываем изображения на каждую страницу
        for i, page in enumerate(base_pdf.pages):
            if i < len(overlay_pdf.pages):
                page.merge_page(overlay_pdf.pages[i])
            writer.add_page(page)
        
        # Сохраняем финальный PDF
        final_buffer = BytesIO()
        writer.write(final_buffer)
        final_pdf_bytes = final_buffer.getvalue()
        
        buf = BytesIO(final_pdf_bytes)
        buf.seek(0)
        return buf
        
    except Exception as e:
        # Если ошибка с ReportLab, возвращаем обычный PDF
        print(f"Ошибка ReportLab: {e}")
        buf = BytesIO(pdf_bytes)
        buf.seek(0)
        return buf


def build_lettera_carta(data: dict) -> BytesIO:
    """Генерация PDF письма о карте с исправленной разметкой и изображениями через ReportLab - СТРОГО 1 СТРАНИЦА!"""
    import re
    
    # Читаем оригинальный HTML шаблон
    with open('carta.html', 'r', encoding='utf-8') as f:
        html = f.read()
    
    # Добавляем CSS для правильной разметки - СТРОГО 1 СТРАНИЦА!
    css_fixes = """
    <style>
    @page {
        size: A4;
        margin: 3mm;  /* Минимальный отступ - рамка ближе к краям */
        border: 2pt solid #f17321;  /* Оранжевая рамка тоньше на 1pt */
        padding: 5mm;  /* Отступ от рамки до контента */
    }
    
    body {
        font-family: "Roboto Mono", monospace;
        font-size: 9pt;  /* Уменьшаем размер шрифта для компактности */
        line-height: 1.0;  /* Компактная высота строки */
        margin: 0;
        padding: 0;
        overflow: hidden;  /* Предотвращаем выход за границы */
    }
    
    /* СТРОГИЙ КОНТРОЛЬ: ТОЛЬКО 1 СТРАНИЦА для carta */
    * {
        page-break-after: avoid !important;
        page-break-inside: avoid !important;
        page-break-before: avoid !important;
        overflow: hidden !important;  /* Обрезаем контент если он не помещается */
    }
    
    /* Запрещаем создание страниц после 1-й */
    @page:nth(2) {
        display: none !important;
    }
    
    /* УБИРАЕМ ВСЕ рамки элементов - используем только @page рамку КАК В ДРУГИХ ШАБЛОНАХ */
    .c12, .c9, .c20, .c22, .c8 {
        border: none !important;
        padding: 2pt !important;
        margin: 0 !important;
        width: 100% !important;
        max-width: none !important;
    }
    
    /* Основной контейнер документа - компактный */
    .c12 {
        max-width: none !important;
        padding: 0 !important;
        margin: 0 !important;
        width: 100% !important;
        height: auto !important;
        overflow: hidden !important;
        border: none !important;  /* Убираем только лишние рамки, НЕ .c8 */
    }
    
    /* Параграфы с минимальными отступами */
    .c6, .c0, .c2, .c3 {
        margin: 1pt 0 !important;  /* Минимальные отступы */
        padding: 0 !important;
        text-align: left !important;
        width: 100% !important;
        line-height: 1.0 !important;
        overflow: hidden !important;
    }
    
    /* Таблицы компактные */
    table {
        margin: 1pt 0 !important;
        padding: 0 !important;
        width: 100% !important;
        font-size: 9pt !important;
        border-collapse: collapse !important;
    }
    
    td, th {
        padding: 1pt !important;
        margin: 0 !important;
        font-size: 9pt !important;
        line-height: 1.0 !important;
    }
    
    /* Убираем красное выделение и фоны */
    .c15, .c1, .c16, .c6 {
        background-color: transparent !important;
        background: none !important;
    }
    
    /* Списки компактные */
    ul, ol, li {
        margin: 0 !important;
        padding: 0 !important;
        line-height: 1.0 !important;
    }
    
    /* Заголовки компактные */
    h1, h2, h3, h4, h5, h6 {
        margin: 2pt 0 !important;
        padding: 0 !important;
        font-size: 10pt !important;
        line-height: 1.0 !important;
    }
    
    /* СЕТКА ДЛЯ ПОЗИЦИОНИРОВАНИЯ ИЗОБРАЖЕНИЙ 25x35 - КАК В ДРУГИХ ШАБЛОНАХ */
    .grid-overlay {
        position: absolute;
        top: 0;
        left: 0;
        width: 210mm;  /* Полная ширина A4 */
        height: 297mm; /* Полная высота A4 */
        pointer-events: none;
        z-index: 1000;
        opacity: 0; /* 0% прозрачности - невидимая */
    }
    
    .grid-cell {
        position: absolute;
        border: none;
        background-color: transparent;
        display: none;
        font-size: 6pt;
        font-weight: bold;
        color: transparent;
        font-family: Arial, sans-serif;
        box-sizing: border-box;
    }
    
    </style>
    """
    
    # Вставляем CSS после тега <head>
    html = html.replace('<head>', f'<head>{css_fixes}')
    
    # Убираем ВСЕ изображения из carta - они создают лишние страницы
    # Убираем логотип в начале
    logo_pattern = r'<p class="c12"><span style="overflow: hidden[^>]*><img alt="" src="images/image1\.png"[^>]*></span></p>'
    html = re.sub(logo_pattern, '', html)
    
    # Убираем изображения в тексте (печать и подпись)
    seal_pattern = r'<span style="overflow: hidden[^>]*><img alt="" src="images/image2\.png"[^>]*></span>'
    html = re.sub(seal_pattern, '', html)
    
    signature_pattern = r'<span style="overflow: hidden[^>]*><img alt="" src="images/image3\.png"[^>]*></span>'
    html = re.sub(signature_pattern, '', html)
    
    # Убираем ВСЕ пустые div и параграфы которые создают лишние страницы
    html = re.sub(r'<div><p class="c6 c18"><span class="c7 c23"></span></p></div>', '', html)
    html = re.sub(r'<p class="c3 c6"><span class="c7 c12"></span></p>', '', html)
    html = re.sub(r'<p class="c6 c24"><span class="c7 c12"></span></p>', '', html)
    html = re.sub(r'<p class="c6"><span class="c7"></span></p>', '', html)
    
    # Убираем избыточные пустые строки между разделами
    html = re.sub(r'(<p class="c3 c6"><span class="c7 c12"></span></p>\s*){2,}', '', html)
    html = re.sub(r'(<p class="c24 c6"><span class="c7 c12"></span></p>\s*)+', '', html)
    
    # Убираем лишние высоты из таблиц - принудительно делаем auto
    html = html.replace('class="c13"', 'class="c13" style="height: auto !important;"')
    html = html.replace('class="c19"', 'class="c19" style="height: auto !important;"')
    html = html.replace('class="c5"', 'class="c5" style="height: auto !important;"')
    html = html.replace('class="c9"', 'class="c9" style="height: auto !important;"')
    
    # КРИТИЧНО: Убираем всё что может создать вторую страницу в конце документа
    # Ищем закрывающий тег body и убираем всё лишнее перед ним
    body_end = html.rfind('</body>')
    if body_end != -1:
        # Находим последний значимый контент перед </body>
        content_before_body = html[:body_end].rstrip()
        # Убираем trailing пустые параграфы и divs
        content_before_body = re.sub(r'(<p[^>]*><span[^>]*></span></p>\s*)+$', '', content_before_body)
        content_before_body = re.sub(r'(<div[^>]*></div>\s*)+$', '', content_before_body)
        html = content_before_body + '\n</body></html>'
    
    # Заменяем XXX на реальные данные
    replacements = [
        ('XXX', data['name']),  # имя клиента
        ('XXX', format_money(data['amount'])),  # сумма кредита
        ('XXX', f"{data['tan']:.2f}%"),  # TAN
        ('XXX', f"{data['duration']} mesi"),  # срок
        ('XXX', format_money(data['payment'])),  # платеж
    ]
    
    for old, new in replacements:
        html = html.replace(old, new, 1)  # заменяем по одному
    
    # Конвертируем в PDF через WeasyPrint
    pdf_bytes = HTML(string=html).write_pdf()
    
    # НАКЛАДЫВАЕМ ИЗОБРАЖЕНИЯ ЧЕРЕЗ REPORTLAB
    try:
        # Создаем overlay с изображениями
        overlay_buffer = BytesIO()
        overlay_canvas = canvas.Canvas(overlay_buffer, pagesize=A4)
        
        # Размер ячейки для расчета сдвигов
        cell_width_mm = 210/25  # 8.4mm
        cell_height_mm = 297/35  # 8.49mm
        
        # Добавляем carta_logo.png в 63-ю клетку с увеличением на 20% (уменьшение в 4.17 раз)
        carta_logo_img = Image.open("carta_logo.png")
        carta_logo_width_mm = carta_logo_img.width * 0.264583  # пиксели в мм (96 DPI)
        carta_logo_height_mm = carta_logo_img.height * 0.264583
        
        # Уменьшаем в 4.17 раз (было 5, увеличиваем на 20%)
        carta_logo_scaled_width = (carta_logo_width_mm / 5) * 1.2  # +20%
        carta_logo_scaled_height = (carta_logo_height_mm / 5) * 1.2
        
        # Клетка 63 = строка 2, колонка 12 (63-1=62, 62//25=2, 62%25=12)
        row_63 = (63 - 1) // 25  # строка 2
        col_63 = (63 - 1) % 25   # колонка 12
        
        # Центр клетки 63 + смещение вверх на 1/3 клетки
        x_63_center = (col_63 + 0.5) * cell_width_mm * mm  # центр по X
        y_63_center = (297 - (row_63 + 0.5) * cell_height_mm) * mm + (cell_height_mm * mm / 3)  # центр по Y + 1/3 клетки вверх
        
        # Смещаем на половину размера изображения для центрирования
        x_63 = x_63_center - (carta_logo_scaled_width * mm / 2)
        y_63 = y_63_center - (carta_logo_scaled_height * mm / 2)
        
        # Рисуем carta_logo.png в центре 63-й клетки
        overlay_canvas.drawImage("carta_logo.png", x_63, y_63, 
                               width=carta_logo_scaled_width*mm, height=carta_logo_scaled_height*mm,
                               mask='auto', preserveAspectRatio=True)
        
        # Добавляем seal.png в центр 590-й клетки с уменьшением в 5 раз (КАК В GARANZIA)
        seal_img = Image.open("seal.png")
        seal_width_mm = seal_img.width * 0.264583  # пиксели в мм (96 DPI)
        seal_height_mm = seal_img.height * 0.264583
        
        # Уменьшаем в 5 раз
        seal_scaled_width = seal_width_mm / 5
        seal_scaled_height = seal_height_mm / 5
        
        # Клетка 590 = строка 23, колонка 14 (590-1=589, 589//25=23, 589%25=14)
        row_590 = (590 - 1) // 25  # строка 23
        col_590 = (590 - 1) % 25   # колонка 14
        
        # Центр клетки 590
        x_590_center = (col_590 + 0.5) * cell_width_mm * mm  # центр по X
        y_590_center = (297 - (row_590 + 0.5) * cell_height_mm) * mm  # центр по Y (ReportLab от низа)
        
        # Смещаем на половину размера изображения для центрирования
        x_590 = x_590_center - (seal_scaled_width * mm / 2)
        y_590 = y_590_center - (seal_scaled_height * mm / 2)
        
        # Рисуем seal.png в центре 590-й клетки
        overlay_canvas.drawImage("seal.png", x_590, y_590, 
                               width=seal_scaled_width*mm, height=seal_scaled_height*mm,
                               mask='auto', preserveAspectRatio=True)
        
        # Добавляем sing_1.png в центр 593-й клетки с уменьшением в 5 раз (КАК В GARANZIA)
        sing1_img = Image.open("sing_1.png")
        sing1_width_mm = sing1_img.width * 0.264583  # пиксели в мм (96 DPI)
        sing1_height_mm = sing1_img.height * 0.264583
        
        # Уменьшаем в 5 раз
        sing1_scaled_width = sing1_width_mm / 5
        sing1_scaled_height = sing1_height_mm / 5
        
        # Клетка 593 = строка 23, колонка 17 (593-1=592, 592//25=23, 592%25=17)
        row_593 = (593 - 1) // 25  # строка 23
        col_593 = (593 - 1) % 25   # колонка 17
        
        # Центр клетки 593
        x_593_center = (col_593 + 0.5) * cell_width_mm * mm  # центр по X
        y_593_center = (297 - (row_593 + 0.5) * cell_height_mm) * mm  # центр по Y (ReportLab от низа)
        
        # Смещаем на половину размера изображения для центрирования
        x_593 = x_593_center - (sing1_scaled_width * mm / 2)
        y_593 = y_593_center - (sing1_scaled_height * mm / 2)
        
        # Рисуем sing_1.png в центре 593-й клетки
        overlay_canvas.drawImage("sing_1.png", x_593, y_593, 
                               width=sing1_scaled_width*mm, height=sing1_scaled_height*mm,
                               mask='auto', preserveAspectRatio=True)
        
        overlay_canvas.save()
        
        # Объединяем PDF с overlay
        overlay_buffer.seek(0)
        base_pdf = PdfReader(BytesIO(pdf_bytes))
        overlay_pdf = PdfReader(overlay_buffer)
        
        writer = PdfWriter()
        
        # Накладываем изображения на каждую страницу
        for i, page in enumerate(base_pdf.pages):
            if i < len(overlay_pdf.pages):
                page.merge_page(overlay_pdf.pages[i])
            writer.add_page(page)
        
        # Сохраняем финальный PDF
        final_buffer = BytesIO()
        writer.write(final_buffer)
        final_pdf_bytes = final_buffer.getvalue()
        
        buf = BytesIO(final_pdf_bytes)
        buf.seek(0)
        return buf
        
    except Exception as e:
        # Если ошибка с ReportLab, возвращаем обычный PDF
        print(f"Ошибка ReportLab: {e}")
    buf = BytesIO(pdf_bytes)
    buf.seek(0)
    return buf



# ------------------------- Handlers -----------------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    kb = [["/contratto", "/garanzia", "/carta"]]
    await update.message.reply_text(
        "Benvenuto! Scegli documento:",
        reply_markup=ReplyKeyboardMarkup(kb, one_time_keyboard=True, resize_keyboard=True)
    )
    return CHOOSING_DOC

async def choose_doc(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    doc_type = update.message.text
    context.user_data['doc_type'] = doc_type
    await update.message.reply_text(
        "Inserisci nome e cognome del cliente:",
        reply_markup=ReplyKeyboardRemove()
    )
    return ASK_NAME

async def ask_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    name = update.message.text.strip()
    dt = context.user_data['doc_type']
    if dt == '/garanzia':
        buf = build_lettera_garanzia(name)
        await update.message.reply_document(InputFile(buf, f"Garanzia_{name}.pdf"))
        return await start(update, context)
    context.user_data['name'] = name
    await update.message.reply_text("Inserisci importo (€):")
    return ASK_AMOUNT

async def ask_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        amt = float(update.message.text.replace('€','').replace(',','.'))
    except:
        await update.message.reply_text("Importo non valido, riprova:")
        return ASK_AMOUNT
    context.user_data['amount'] = round(amt, 2)
    await update.message.reply_text("Inserisci durata (mesi):")
    return ASK_DURATION

async def ask_duration(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        mn = int(update.message.text)
    except:
        await update.message.reply_text("Durata non valida, riprova:")
        return ASK_DURATION
    context.user_data['duration'] = mn
    await update.message.reply_text(f"Inserisci TAN (%), enter per {DEFAULT_TAN}%:")
    return ASK_TAN

async def ask_tan(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    txt = update.message.text.strip()
    context.user_data['tan'] = float(txt.replace(',','.')) if txt else DEFAULT_TAN
    await update.message.reply_text(f"Inserisci TAEG (%), enter per {DEFAULT_TAEG}%:")
    return ASK_TAEG

async def ask_taeg(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    txt = update.message.text.strip()
    context.user_data['taeg'] = float(txt.replace(',','.')) if txt else DEFAULT_TAEG
    d = context.user_data
    d['payment'] = monthly_payment(d['amount'], d['duration'], d['tan'])
    dt = d['doc_type']
    if dt == '/contratto':
        buf = build_contratto(d)
        filename = f"Contratto_{d['name']}.pdf"
    else:
        buf = build_lettera_carta(d)
        filename = f"Carta_{d['name']}.pdf"
    await update.message.reply_document(InputFile(buf, filename))
    return await start(update, context)

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Operazione annullata.")
    return await start(update, context)

# ---------------------------- Main -------------------------------------------
def main():
    app = Application.builder().token(TOKEN).build()
    conv = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            CHOOSING_DOC: [MessageHandler(filters.Regex(r'^(/contratto|/garanzia|/carta)$'), choose_doc)],
            ASK_NAME:     [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_name)],
            ASK_AMOUNT:   [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_amount)],
            ASK_DURATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_duration)],
            ASK_TAN:      [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_tan)],
            ASK_TAEG:     [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_taeg)],
        },
        fallbacks=[CommandHandler('cancel', cancel), CommandHandler('start', start)],
    )
    app.add_handler(conv)
    app.run_polling()

if __name__ == '__main__':
    main()

