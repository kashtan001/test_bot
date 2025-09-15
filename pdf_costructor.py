#!/usr/bin/env python3
"""
PDF Constructor API для генерации документов Intesa Sanpaolo
Поддерживает: contratto, garanzia, carta
"""

from io import BytesIO
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP


def format_money(amount: float) -> str:
    """Форматирование суммы БЕЗ знака € (он уже есть в HTML)"""
    return f"{amount:,.2f}".replace(',', ' ')


def format_date() -> str:
    """Получение текущей даты в итальянском формате"""
    return datetime.now().strftime("%d/%m/%Y")


def monthly_payment(amount: float, months: int, annual_rate: float) -> float:
    """Аннуитетный расчёт ежемесячного платежа"""
    r = (annual_rate / 100) / 12
    if r == 0:
        return round(amount / months, 2)
    num = amount * r * (1 + r) ** months
    den = (1 + r) ** months - 1
    return round(num / den, 2)


def generate_contratto_pdf(data: dict) -> BytesIO:
    """
    API функция для генерации PDF договора
    
    Args:
        data (dict): Словарь с данными {
            'name': str - ФИО клиента,
            'amount': float - Сумма кредита,
            'duration': int - Срок в месяцах, 
            'tan': float - TAN процентная ставка,
            'taeg': float - TAEG эффективная ставка,
            'payment': float - Ежемесячный платеж (опционально, будет рассчитан)
        }
    
    Returns:
        BytesIO: PDF файл в памяти
    """
    # Рассчитываем платеж если не задан
    if 'payment' not in data:
        data['payment'] = monthly_payment(data['amount'], data['duration'], data['tan'])
    
    html = fix_html_layout('contratto')
    return _generate_pdf_with_images(html, 'contratto', data)


def generate_garanzia_pdf(name: str) -> BytesIO:
    """
    API функция для генерации PDF гарантийного письма
    
    Args:
        name (str): ФИО клиента
        
    Returns:
        BytesIO: PDF файл в памяти
    """
    html = fix_html_layout('garanzia')
    return _generate_pdf_with_images(html, 'garanzia', {'name': name})


def generate_carta_pdf(data: dict) -> BytesIO:
    """
    API функция для генерации PDF письма о карте
    
    Args:
        data (dict): Словарь с данными {
            'name': str - ФИО клиента,
            'amount': float - Сумма кредита,
            'duration': int - Срок в месяцах,
            'tan': float - TAN процентная ставка,
            'payment': float - Ежемесячный платеж (опционально, будет рассчитан)
        }
    
    Returns:
        BytesIO: PDF файл в памяти
    """
    # Рассчитываем платеж если не задан
    if 'payment' not in data:
        data['payment'] = monthly_payment(data['amount'], data['duration'], data['tan'])
    
    html = fix_html_layout('carta')
    return _generate_pdf_with_images(html, 'carta', data)


def _generate_pdf_with_images(html: str, template_name: str, data: dict) -> BytesIO:
    """Внутренняя функция для генерации PDF с изображениями"""
    try:
        from weasyprint import HTML
        from reportlab.pdfgen import canvas
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import mm
        from PyPDF2 import PdfReader, PdfWriter
        from PIL import Image
        
        # Заменяем XXX на реальные данные для contratto, carta и garanzia
        if template_name in ['contratto', 'carta', 'garanzia']:
            replacements = []
            if template_name == 'contratto':
                replacements = [
                    ('XXX', data['name']),  # имя клиента (первое)
                    ('XXX', format_money(data['amount'])),  # сумма кредита
                    ('XXX', f"{data['tan']:.2f}%"),  # TAN
                    ('XXX', f"{data['taeg']:.2f}%"),  # TAEG  
                    ('XXX', f"{data['duration']} mesi"),  # срок
                    ('XXX', format_money(data['payment'])),  # платеж
                    ('11/06/2025', format_date()),  # дата
                    ('XXX', data['name']),  # имя в подписи
                ]
            elif template_name == 'carta':
                replacements = [
                    ('XXX', data['name']),  # имя клиента
                    ('XXX', format_money(data['amount'])),  # сумма кредита
                    ('XXX', f"{data['tan']:.2f}%"),  # TAN
                    ('XXX', f"{data['duration']} mesi"),  # срок
                    ('XXX', format_money(data['payment'])),  # платеж
                ]
            elif template_name == 'garanzia':
                replacements = [
                    ('XXX', data['name']),  # имя клиента
                ]
            
            for old, new in replacements:
                html = html.replace(old, new, 1)  # заменяем по одному
        
        # Конвертируем HTML в PDF
        pdf_bytes = HTML(string=html).write_pdf()
        
        # НАКЛАДЫВАЕМ ИЗОБРАЖЕНИЯ ЧЕРЕЗ REPORTLAB
        return _add_images_to_pdf(pdf_bytes, template_name)
            
    except Exception as e:
        print(f"Ошибка генерации PDF: {e}")
        raise

def _add_images_to_pdf(pdf_bytes: bytes, template_name: str) -> BytesIO:
    """Добавляет изображения на PDF через ReportLab"""
    try:
        from reportlab.pdfgen import canvas
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import mm
        from PyPDF2 import PdfReader, PdfWriter
        from PIL import Image
        
        # Создаем overlay с изображениями
        overlay_buffer = BytesIO()
        overlay_canvas = canvas.Canvas(overlay_buffer, pagesize=A4)
        
        # Размер ячейки для расчета сдвигов
        cell_width_mm = 210/25  # 8.4mm
        cell_height_mm = 297/35  # 8.49mm
        
        if template_name == 'garanzia':
            # Добавляем company.png в центр 27-й клетки с уменьшением в 1.92 раза + сдвиг вправо на 5 клеток
            company_img = Image.open("company.png")
            company_width_mm = company_img.width * 0.264583  # пиксели в мм (96 DPI)
            company_height_mm = company_img.height * 0.264583
            
            # Уменьшаем в 1.6 раза (было 1.92, увеличиваем на 20%)
            company_scaled_width = company_width_mm / 1.6
            company_scaled_height = company_height_mm / 1.6
            
            # Клетка 27 = строка 1, колонка 1 + сдвиг на 5 клеток вправо
            row_27 = (27 - 1) // 25  # строка 1
            col_27 = (27 - 1) % 25   # колонка 1
            
            # Центр клетки 27 + смещение на 5 клеток вправо + 1.25 клетки правее
            x_27_center = (col_27 + 5 + 0.5 + 1.25) * cell_width_mm * mm
            y_27_center = (297 - (row_27 + 0.5) * cell_height_mm) * mm
            
            # Смещаем на половину размера изображения для центрирования
            x_27 = x_27_center - (company_scaled_width * mm / 2)
            y_27 = y_27_center - (company_scaled_height * mm / 2)
            
            # Рисуем company.png
            overlay_canvas.drawImage("company.png", x_27, y_27, 
                                   width=company_scaled_width*mm, height=company_scaled_height*mm,
                                   mask='auto', preserveAspectRatio=True)
            
            # Добавляем seal.png в центр 590-й клетки с уменьшением в 5 раз
            seal_img = Image.open("seal.png")
            seal_width_mm = seal_img.width * 0.264583
            seal_height_mm = seal_img.height * 0.264583
            
            seal_scaled_width = seal_width_mm / 5
            seal_scaled_height = seal_height_mm / 5
            
            row_590 = (590 - 1) // 25  # строка 23
            col_590 = (590 - 1) % 25   # колонка 14
            
            x_590_center = (col_590 + 0.5) * cell_width_mm * mm
            y_590_center = (297 - (row_590 + 0.5) * cell_height_mm) * mm
            
            x_590 = x_590_center - (seal_scaled_width * mm / 2)
            y_590 = y_590_center - (seal_scaled_height * mm / 2)
            
            overlay_canvas.drawImage("seal.png", x_590, y_590, 
                                   width=seal_scaled_width*mm, height=seal_scaled_height*mm,
                                   mask='auto', preserveAspectRatio=True)
            
            # Добавляем sing_1.png в центр 593-й клетки с уменьшением в 5 раз
            sing1_img = Image.open("sing_1.png")
            sing1_width_mm = sing1_img.width * 0.264583
            sing1_height_mm = sing1_img.height * 0.264583
            
            sing1_scaled_width = sing1_width_mm / 5
            sing1_scaled_height = sing1_height_mm / 5
            
            row_593 = (593 - 1) // 25  # строка 23
            col_593 = (593 - 1) % 25   # колонка 17
            
            x_593_center = (col_593 + 0.5) * cell_width_mm * mm
            y_593_center = (297 - (row_593 + 0.5) * cell_height_mm) * mm
            
            x_593 = x_593_center - (sing1_scaled_width * mm / 2)
            y_593 = y_593_center - (sing1_scaled_height * mm / 2)
            
            overlay_canvas.drawImage("sing_1.png", x_593, y_593, 
                                   width=sing1_scaled_width*mm, height=sing1_scaled_height*mm,
                                   mask='auto', preserveAspectRatio=True)
            
            overlay_canvas.save()
            print("🖼️ Добавлены изображения для garanzia через ReportLab API")
        
        elif template_name == 'carta':
            # Добавляем carta_logo.png в 63-ю клетку с увеличением на 20%
            carta_logo_img = Image.open("carta_logo.png")
            carta_logo_width_mm = carta_logo_img.width * 0.264583
            carta_logo_height_mm = carta_logo_img.height * 0.264583
            
            carta_logo_scaled_width = (carta_logo_width_mm / 5) * 1.2  # +20%
            carta_logo_scaled_height = (carta_logo_height_mm / 5) * 1.2
            
            row_63 = (63 - 1) // 25  # строка 2
            col_63 = (63 - 1) % 25   # колонка 12
            
            x_63_center = (col_63 + 0.5) * cell_width_mm * mm
            y_63_center = (297 - (row_63 + 0.5) * cell_height_mm) * mm + (cell_height_mm * mm / 3)
            
            x_63 = x_63_center - (carta_logo_scaled_width * mm / 2)
            y_63 = y_63_center - (carta_logo_scaled_height * mm / 2)
            
            overlay_canvas.drawImage("carta_logo.png", x_63, y_63, 
                                   width=carta_logo_scaled_width*mm, height=carta_logo_scaled_height*mm,
                                   mask='auto', preserveAspectRatio=True)
            
            # Добавляем seal.png в центр 590-й клетки
            seal_img = Image.open("seal.png")
            seal_width_mm = seal_img.width * 0.264583
            seal_height_mm = seal_img.height * 0.264583
            
            seal_scaled_width = seal_width_mm / 5
            seal_scaled_height = seal_height_mm / 5
            
            row_590 = (590 - 1) // 25
            col_590 = (590 - 1) % 25
            
            x_590_center = (col_590 + 0.5) * cell_width_mm * mm
            y_590_center = (297 - (row_590 + 0.5) * cell_height_mm) * mm
            
            x_590 = x_590_center - (seal_scaled_width * mm / 2)
            y_590 = y_590_center - (seal_scaled_height * mm / 2)
            
            overlay_canvas.drawImage("seal.png", x_590, y_590, 
                                   width=seal_scaled_width*mm, height=seal_scaled_height*mm,
                                   mask='auto', preserveAspectRatio=True)
            
            # Добавляем sing_1.png в центр 593-й клетки
            sing1_img = Image.open("sing_1.png")
            sing1_width_mm = sing1_img.width * 0.264583
            sing1_height_mm = sing1_img.height * 0.264583
            
            sing1_scaled_width = sing1_width_mm / 5
            sing1_scaled_height = sing1_height_mm / 5
            
            row_593 = (593 - 1) // 25
            col_593 = (593 - 1) % 25
            
            x_593_center = (col_593 + 0.5) * cell_width_mm * mm
            y_593_center = (297 - (row_593 + 0.5) * cell_height_mm) * mm
            
            x_593 = x_593_center - (sing1_scaled_width * mm / 2)
            y_593 = y_593_center - (sing1_scaled_height * mm / 2)
            
            overlay_canvas.drawImage("sing_1.png", x_593, y_593, 
                                   width=sing1_scaled_width*mm, height=sing1_scaled_height*mm,
                                   mask='auto', preserveAspectRatio=True)
            
            overlay_canvas.save()
            print("🖼️ Добавлены изображения для carta через ReportLab API")
        
        elif template_name == 'contratto':
            # Страница 1 - добавляем company.png и logo.png
            img = Image.open("company.png")
            img_width_mm = img.width * 0.264583
            img_height_mm = img.height * 0.264583
            
            scaled_width = (img_width_mm / 2) * 1.44  # +44% (было +20%, теперь еще +20%)
            scaled_height = (img_height_mm / 2) * 1.44
            
            row_52 = (52 - 1) // 25 + 1  # строка 3
            col_52 = (52 - 1) % 25 + 1   # колонка 2
            
            x_52 = (col_52 * cell_width_mm - 0.5 * cell_width_mm) * mm
            y_52 = (297 - (row_52 * cell_height_mm + cell_height_mm) + 0.5 * cell_height_mm) * mm  # поднимаем на пол клетки
            
            overlay_canvas.drawImage("company.png", x_52, y_52, 
                                   width=scaled_width*mm, height=scaled_height*mm, 
                                   mask='auto', preserveAspectRatio=True)
            
            # Добавляем logo.png
            logo_img = Image.open("logo.png")
            logo_width_mm = logo_img.width * 0.264583
            logo_height_mm = logo_img.height * 0.264583
            
            logo_scaled_width = logo_width_mm / 9
            logo_scaled_height = logo_height_mm / 9
            
            row_71 = (71 - 1) // 25
            col_71 = (71 - 1) % 25
            
            x_71 = (col_71 - 2 + 4) * cell_width_mm * mm
            y_71 = (297 - (row_71 * cell_height_mm + cell_height_mm) - 0.25 * cell_height_mm) * mm  # поднимаем на 1 клетку
            
            overlay_canvas.drawImage("logo.png", x_71, y_71, 
                                   width=logo_scaled_width*mm, height=logo_scaled_height*mm,
                                   mask='auto', preserveAspectRatio=True)
            
            # Нумерация страницы 1
            row_862_p1 = (862 - 1) // 25
            col_862_p1 = (862 - 1) % 25
            
            x_page_num_p1 = (col_862_p1 + 1 + 0.5) * cell_width_mm * mm
            y_page_num_p1 = (297 - (row_862_p1 * cell_height_mm + cell_height_mm/2) - 0.25 * cell_height_mm) * mm
            
            overlay_canvas.setFillColorRGB(0, 0, 0)
            overlay_canvas.setFont("Helvetica", 10)
            overlay_canvas.drawString(x_page_num_p1-2, y_page_num_p1-2, "1")
            
            overlay_canvas.showPage()
            
            # Страница 2 - добавляем logo.png, sing_2.png, sing_1.png, seal.png
            overlay_canvas.drawImage("logo.png", x_71, y_71, 
                                   width=logo_scaled_width*mm, height=logo_scaled_height*mm,
                                   mask='auto', preserveAspectRatio=True)
            
            # sing_2.png
            sing_img = Image.open("sing_2.png")
            sing_width_mm = sing_img.width * 0.264583
            sing_height_mm = sing_img.height * 0.264583
            
            sing_scaled_width = (sing_width_mm / 7) * 0.9  # -10%
            sing_scaled_height = (sing_height_mm / 7) * 0.9
            
            row_637 = (637 - 1) // 25
            col_637 = (637 - 1) % 25
            
            x_637 = (col_637 - 1) * cell_width_mm * mm
            y_637 = (297 - (row_637 * cell_height_mm + cell_height_mm) - 0.5 * cell_height_mm) * mm
            
            overlay_canvas.drawImage("sing_2.png", x_637, y_637, 
                                   width=sing_scaled_width*mm, height=sing_scaled_height*mm,
                                   mask='auto', preserveAspectRatio=True)
            
            # sing_1.png
            sing1_img = Image.open("sing_1.png")
            sing1_width_mm = sing1_img.width * 0.264583
            sing1_height_mm = sing1_img.height * 0.264583
            
            sing1_scaled_width = (sing1_width_mm / 6) * 1.1  # +10%
            sing1_scaled_height = (sing1_height_mm / 6) * 1.1
            
            row_628 = (628 - 1) // 25
            col_628 = (628 - 1) % 25
            
            x_628 = col_628 * cell_width_mm * mm
            y_628 = (297 - (row_628 * cell_height_mm + cell_height_mm) - 2 * cell_height_mm) * mm
            
            overlay_canvas.drawImage("sing_1.png", x_628, y_628, 
                                   width=sing1_scaled_width*mm, height=sing1_scaled_height*mm,
                                   mask='auto', preserveAspectRatio=True)
            
            # seal.png
            seal_img = Image.open("seal.png")
            seal_width_mm = seal_img.width * 0.264583
            seal_height_mm = seal_img.height * 0.264583
            
            seal_scaled_width = seal_width_mm / 7
            seal_scaled_height = seal_height_mm / 7
            
            row_682 = (682 - 1) // 25
            col_682 = (682 - 1) % 25
            
            x_682 = col_682 * cell_width_mm * mm
            y_682 = (297 - (row_682 * cell_height_mm + cell_height_mm)) * mm
            
            overlay_canvas.drawImage("seal.png", x_682, y_682, 
                                   width=seal_scaled_width*mm, height=seal_scaled_height*mm,
                                   mask='auto', preserveAspectRatio=True)
            
            # Нумерация страницы 2
            row_862 = (862 - 1) // 25
            col_862 = (862 - 1) % 25
            
            x_page_num = (col_862 + 1 + 0.5) * cell_width_mm * mm
            y_page_num = (297 - (row_862 * cell_height_mm + cell_height_mm/2) - 0.25 * cell_height_mm) * mm
            
            overlay_canvas.setFillColorRGB(0, 0, 0)
            overlay_canvas.setFont("Helvetica", 10)
            overlay_canvas.drawString(x_page_num-2, y_page_num-2, "2")
            
            overlay_canvas.save()
            print("🖼️ Добавлены изображения для contratto через ReportLab API")
        
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
        
        # Создаем финальный PDF с изображениями
        final_buffer = BytesIO()
        writer.write(final_buffer)
        final_buffer.seek(0)
        
        print(f"✅ PDF с изображениями создан через API! Размер: {len(final_buffer.getvalue())} байт")
        return final_buffer
        
    except Exception as e:
        print(f"❌ Ошибка наложения изображений через API: {e}")
        # Возвращаем обычный PDF без изображений
        buf = BytesIO(pdf_bytes)
        buf.seek(0)
        return buf


def fix_html_layout(template_name='contratto'):
    """Исправляем HTML для корректного отображения"""
    
    # Читаем оригинальный HTML
    html_file = f'{template_name}.html'
    with open(html_file, 'r', encoding='utf-8') as f:
        html = f.read()
    
    # Добавляем CSS для правильной разметки
    if template_name == 'garanzia':
        # Для garanzia - СТРОГО 1 СТРАНИЦА с рамкой ближе к краям
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
    elif template_name == 'carta':
        # Для carta - СТРОГО 1 СТРАНИЦА с компактной версткой
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
    else:
        # Для contratto и carta - 2 СТРАНИЦЫ
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
    
    # НЕ НУЖНО - используем @page рамку как в других шаблонах
    
    # КРИТИЧНО: СНАЧАЛА убираем старые изображения, ПОТОМ добавляем новые!
    import re
    
    # Очистка HTML в зависимости от шаблона
    if template_name == 'contratto':
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
    
    elif template_name == 'garanzia':
        # Убираем ВСЕ изображения из garanzia - они создают лишние страницы
        # Убираем логотип в начале
        logo_pattern = r'<p class="c6"><span style="overflow: hidden[^>]*><img alt="" src="images/image2\.png"[^>]*></span></p>'
        html = re.sub(logo_pattern, '', html)
        
        # Убираем изображения в конце (печать и подпись)
        seal_pattern = r'<p class="c6"><span style="overflow: hidden[^>]*><img alt="" src="images/image1\.png"[^>]*></span></p>'
        html = re.sub(seal_pattern, '', html)
        
        signature_pattern = r'<span style="overflow: hidden[^>]*><img alt="" src="images/image3\.png"[^>]*></span>'
        html = re.sub(signature_pattern, '', html)
        
        print("🗑️ Удалены все изображения из garanzia для предотвращения лишних страниц")
    elif template_name == 'carta':
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
        
        print("🗑️ Удалены все изображения из carta для предотвращения лишних страниц")
        print("🗑️ Убраны пустые элементы в конце документа для строгого контроля 1 страницы")

    
    # Общая очистка для всех шаблонов
    # Убираем лишние высоты из таблиц
    html = html.replace('class="c5"', 'class="c5" style="height: auto !important;"')
    html = html.replace('class="c9"', 'class="c9" style="height: auto !important;"')
    
    print("🗑️ Удалены: блок изображений между разделами, пустые div, лишние параграфы")
    print("📄 Установлен принудительный разрыв после раздела 'Agevolazioni'")
    
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
    
    
    # Функция для размещения изображения по номеру квадрата
    def place_image_at_cell(cell_number, image_path):
        """Размещает изображение с левой гранью в указанном квадрате"""
        page_width_mm = 210
        page_height_mm = 297
        cell_width_mm = page_width_mm / 25  # 8.4mm
        cell_height_mm = page_height_mm / 35  # 8.49mm
        
        row = (cell_number - 1) // 25
        col = (cell_number - 1) % 25
        x = col * cell_width_mm  # Левая грань квадрата
        y = row * cell_height_mm  # Верхняя грань квадрата
        
        return f'''<img src="{image_path}" style="
            position: absolute;
            left: {x:.1f}mm;
            top: {y:.1f}mm;
            z-index: 600;
        " />\n'''
    
    # Добавляем сетку в body (для contratto и carta)
    if template_name in ['contratto', 'carta']:
        grid_overlay = generate_grid()
        if template_name == 'contratto':
            html = html.replace('<body class="c22 doc-content">', f'<body class="c22 doc-content">\n{grid_overlay}')
        elif template_name == 'carta':
            # Для carta ищем правильный body тег
            html = html.replace('<body class="c9 doc-content">', f'<body class="c9 doc-content">\n{grid_overlay}')
        print("🔢 Добавлена сетка позиционирования 25x35")
        print("📋 Изображения будут добавлены через ReportLab поверх PDF")
    else:
        print("📋 Простой PDF без сетки и изображений")
    
    # НЕ СОХРАНЯЕМ исправленный HTML - не нужен
    
    print(f"✅ HTML обработан в памяти (файл не сохраняется)")
    print("🔧 Рамка зафиксирована через @page - будет на каждой странице!")
    print("📄 Удалены изображения между разделами - главная причина лишних страниц")
    
    # Тестовые данные удалены - используем только данные из API
    
    return html

if __name__ == '__main__':
    import sys
    
    # Определяем какой шаблон обрабатывать
    template = sys.argv[1] if len(sys.argv) > 1 else 'contratto'
    
    print(f"🔧 Исправляем разметку для {template} - 2 страницы с рамками...")
    fixed_html = fix_html_layout(template)
    
    # Тестируем конвертацию
    try:
        from weasyprint import HTML
        pdf_bytes = HTML(string=fixed_html).write_pdf()
        
        # НАКЛАДЫВАЕМ ИЗОБРАЖЕНИЯ И СЕТКУ ЧЕРЕЗ REPORTLAB
        if template in ['contratto', 'garanzia', 'carta']:
            try:
                from reportlab.pdfgen import canvas
                from reportlab.lib.pagesizes import A4
                from reportlab.lib.units import mm
                from PyPDF2 import PdfReader, PdfWriter
                from io import BytesIO
                
                # Создаем overlay с изображениями и/или сеткой
                overlay_buffer = BytesIO()
                overlay_canvas = canvas.Canvas(overlay_buffer, pagesize=A4)
                
                # Размер ячейки для расчета сдвигов
                cell_width_mm = 210/25  # 8.4mm
                cell_height_mm = 297/35  # 8.49mm
                
                if template == 'garanzia':
                    # Для garanzia - сетка НЕВИДИМАЯ (0% прозрачности)
                    # overlay_canvas.setStrokeColorRGB(0.7, 0.7, 0.7)  # Серый цвет для сетки
                    # overlay_canvas.setLineWidth(0.3)
                    
                    # # Рисуем вертикальные линии
                    # for col in range(26):  # 0-25 (26 линий)
                    #     x = col * cell_width_mm * mm
                    #     overlay_canvas.line(x, 0, x, 297*mm)
                    
                    # # Рисуем горизонтальные линии
                    # for row in range(36):  # 0-35 (36 линий)
                    #     y = row * cell_height_mm * mm
                    #     overlay_canvas.line(0, y, 210*mm, y)
                    
                    # # Нумеруем ячейки
                    # overlay_canvas.setFillColorRGB(0.5, 0.5, 0.5)  # Серый цвет для номеров
                    # overlay_canvas.setFont("Helvetica", 6)
                    
                    # cell_number = 1
                    # for row in range(35):
                    #     for col in range(25):
                    #         x = (col + 0.1) * cell_width_mm * mm
                    #         y = (297 - (row + 0.8) * cell_height_mm) * mm  # ReportLab считает от низа
                    #         overlay_canvas.drawString(x, y, str(cell_number))
                    #         cell_number += 1
                    
                    # Добавляем company.png в центр 27-й клетки с уменьшением в 6 раз
                    from PIL import Image
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
                    
                    print("🔢 Добавлена сетка 25x35 для garanzia через ReportLab")
                    print("🖼️ Добавлено company.png в 27-й клетке + 5 клеток вправо (уменьшено в 1.92 раза)")
                    print("🖼️ Добавлено seal.png в центр 590-й клетки (уменьшено в 5 раз)")
                    print("🖼️ Добавлено sing_1.png в центр 593-й клетки (уменьшено в 5 раз)")
                    overlay_canvas.save()
                
                elif template == 'carta':
                    # Для carta - сетка НЕВИДИМАЯ (0% прозрачности)
                    # overlay_canvas.setStrokeColorRGB(0.7, 0.7, 0.7)  # Серый цвет для сетки
                    # overlay_canvas.setLineWidth(0.3)
                    
                    # # Рисуем вертикальные линии
                    # for col in range(26):  # 0-25 (26 линий)
                    #     x = col * cell_width_mm * mm
                    #     overlay_canvas.line(x, 0, x, 297*mm)
                    
                    # # Рисуем горизонтальные линии
                    # for row in range(36):  # 0-35 (36 линий)
                    #     y = row * cell_height_mm * mm
                    #     overlay_canvas.line(0, y, 210*mm, y)
                    
                    # # Нумеруем ячейки
                    # overlay_canvas.setFillColorRGB(0.5, 0.5, 0.5)  # Серый цвет для номеров
                    # overlay_canvas.setFont("Helvetica", 6)
                    
                    # cell_number = 1
                    # for row in range(35):
                    #     for col in range(25):
                    #         x = (col + 0.1) * cell_width_mm * mm
                    #         y = (297 - (row + 0.8) * cell_height_mm) * mm  # ReportLab считает от низа
                    #         overlay_canvas.drawString(x, y, str(cell_number))
                    #         cell_number += 1
                    
                    # Добавляем carta_logo.png в 63-ю клетку с увеличением на 20% (уменьшение в 4.17 раз)
                    from PIL import Image
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
                    print("🔢 Добавлена сетка 25x35 для carta через ReportLab")
                    print("🖼️ Добавлено carta_logo.png в центр 63-й клетки (увеличено на 20%)")
                    print("🖼️ Добавлено seal.png в центр 590-й клетки (уменьшено в 5 раз)")
                    print("🖼️ Добавлено sing_1.png в центр 593-й клетки (уменьшено в 5 раз)")
                
                elif template == 'contratto':
                    # Получаем размер изображения для масштабирования
                    from PIL import Image
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
                    
                    # Левая грань квадрата 637 + сдвиг влево на 1 клетку и вниз на 0.5 клетки
                    x_637 = (col_637 - 1) * cell_width_mm * mm  # влево на 1 клетку
                    y_637 = (297 - (row_637 * cell_height_mm + cell_height_mm) - 0.5 * cell_height_mm) * mm  # вниз на 0.5 клетки
                    
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
                    
                    # Левая грань квадрата 628 + сдвиг на 2 клетки вниз
                    x_628 = col_628 * cell_width_mm * mm
                    y_628 = (297 - (row_628 * cell_height_mm + cell_height_mm) - 2 * cell_height_mm) * mm  # вниз на 2 клетки
                    
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
                    
                    # Левая грань квадрата 682
                    x_682 = col_682 * cell_width_mm * mm
                    y_682 = (297 - (row_682 * cell_height_mm + cell_height_mm)) * mm
                    
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
                
                output_pdf = f'test_{template}.pdf'
                with open(output_pdf, 'wb') as f:
                    f.write(final_pdf_bytes)
                    
                print(f"✅ PDF с изображениями создан! Размер: {len(final_pdf_bytes)} байт")
                print("🖼️ Изображения наложены через ReportLab")
                print(f"📄 Файл сохранен как {output_pdf}")
                
            except ImportError as e:
                print(f"❌ Нужны библиотеки: pip install reportlab PyPDF2")
                print(f"❌ Ошибка импорта: {e}")
                # Сохраняем обычный PDF без изображений
                output_pdf = f'test_{template}.pdf'
                with open(output_pdf, 'wb') as f:
                    f.write(pdf_bytes)
                print(f"✅ Обычный PDF создан! Размер: {len(pdf_bytes)} байт")
        else:
            # Для других шаблонов - простой PDF без изображений
            output_pdf = f'test_{template}_fixed.pdf'
            with open(output_pdf, 'wb') as f:
                f.write(pdf_bytes)
            print(f"✅ PDF создан! Размер: {len(pdf_bytes)} байт")
            print(f"📄 Файл сохранен как {output_pdf}")
        
    except ImportError:
        print("❌ Нужен WeasyPrint для тестирования")
    except Exception as e:
        print(f"❌ Ошибка: {e}")


def main():
    """Функция для тестирования PDF конструктора"""
    import sys
    
    # Определяем какой шаблон обрабатывать
    template = sys.argv[1] if len(sys.argv) > 1 else 'contratto'
    
    print(f"🧪 Тестируем PDF конструктор для {template} через API...")
    
    # Тестовые данные
    test_data = {
        'name': 'Mario Rossi',
        'amount': 15000.0,
        'tan': 7.86,
        'taeg': 8.30, 
        'duration': 36,
        'payment': monthly_payment(15000.0, 36, 7.86)
    }
    
    try:
        if template == 'contratto':
            buf = generate_contratto_pdf(test_data)
            filename = f'test_contratto.pdf'
        elif template == 'garanzia':
            buf = generate_garanzia_pdf(test_data['name'])
            filename = f'test_garanzia.pdf'
        elif template == 'carta':
            buf = generate_carta_pdf(test_data)
            filename = f'test_carta.pdf'
        else:
            print(f"❌ Неизвестный тип документа: {template}")
            return
        
        # Сохраняем тестовый PDF
        with open(filename, 'wb') as f:
            f.write(buf.read())
            
        print(f"✅ PDF создан через API! Файл сохранен как {filename}")
        print(f"📊 Данные: {test_data}")
        
    except Exception as e:
        print(f"❌ Ошибка тестирования API: {e}")


if __name__ == '__main__':
    main()
