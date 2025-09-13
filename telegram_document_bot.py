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
from io import BytesIO
from decimal import Decimal, ROUND_HALF_UP

from telegram import Update, InputFile, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application, CommandHandler, ConversationHandler, MessageHandler, ContextTypes, filters,
)

from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT, TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm, mm
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

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

# ---------------------- Настройки сетки ------------------------------------
DEBUG_GRID_ENABLED = True  # Переключатель отладочной сетки
GRID_OPACITY = 0.3  # Прозрачность сетки (30% = 70% прозрачности)
GRID_ROWS = 20      # Количество строк сетки
GRID_COLS = 20      # Количество столбцов сетки (итого 400 квадратов)

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


def init_fonts():
    """Инициализация кастомных шрифтов"""
    try:
        if os.path.exists(FONT_PATH):
            # Регистрируем основной шрифт RobotoMono
            pdfmetrics.registerFont(TTFont('RobotoMono', FONT_PATH))
            
            # Создаем варианты шрифта (эмуляция жирного и курсива)
            # Для настоящего жирного/курсива нужны отдельные файлы шрифтов
            pdfmetrics.registerFont(TTFont('RobotoMono-Bold', FONT_PATH))
            pdfmetrics.registerFont(TTFont('RobotoMono-Italic', FONT_PATH))
            pdfmetrics.registerFont(TTFont('RobotoMono-BoldItalic', FONT_PATH))
            
            return True
    except Exception as e:
        logger.warning(f"Не удалось загрузить шрифт {FONT_PATH}: {e}")
        return False
    return False


def _styles():
    """Создание расширенной системы стилей с полным контролем дизайна"""
    styles = getSampleStyleSheet()
    
    # Проверяем доступность кастомного шрифта
    font_available = init_fonts()
    base_font = 'RobotoMono' if font_available else 'Helvetica'
    bold_font = 'RobotoMono-Bold' if font_available else 'Helvetica-Bold'
    
    # =================== ЗАГОЛОВКИ ===================
    styles.add(ParagraphStyle(
        name="MainHeader",
        parent=styles['Normal'],
        fontName=bold_font,
        fontSize=16,
        leading=16,  # интервал = размер шрифта
        alignment=TA_CENTER,
        spaceAfter=12*mm,  # отступ после
        spaceBefore=6*mm,  # отступ до
        textColor=colors.black,
        leftIndent=0,
        rightIndent=0
    ))
    
    styles.add(ParagraphStyle(
        name="SubHeader",
        parent=styles['Normal'],
        fontName=bold_font,
        fontSize=14,
        leading=14,
        alignment=TA_LEFT,
        spaceAfter=8*mm,
        spaceBefore=4*mm,
        textColor=colors.black
    ))
    
    styles.add(ParagraphStyle(
        name="Header",
        parent=styles['Normal'],
        fontName=bold_font,
        fontSize=12,
        leading=12,
        alignment=TA_CENTER,
        spaceAfter=6*mm,
        spaceBefore=3*mm,
        textColor=colors.black
    ))
    
    # =================== ОСНОВНОЙ ТЕКСТ ===================
    styles.add(ParagraphStyle(
        name="Body",
        parent=styles['Normal'],
        fontName=base_font,
        fontSize=10,
        leading=10,  # интервал = размер шрифта (1.0)
        alignment=TA_LEFT,
        spaceAfter=3*mm,
        spaceBefore=0,
        textColor=colors.black,
        leftIndent=0,
        rightIndent=0,
        firstLineIndent=0
    ))
    
    styles.add(ParagraphStyle(
        name="BodyBold",
        parent=styles['Body'],
        fontName=bold_font,
        fontSize=10,
        leading=10
    ))
    
    styles.add(ParagraphStyle(
        name="BodySmall",
        parent=styles['Body'],
        fontSize=9,
        leading=9,
        spaceAfter=2*mm
    ))
    
    styles.add(ParagraphStyle(
        name="BodyLarge",
        parent=styles['Body'],
        fontSize=12,
        leading=12,
        spaceAfter=4*mm
    ))
    
    # =================== СПЕЦИАЛЬНЫЕ СТИЛИ ===================
    styles.add(ParagraphStyle(
        name="Centered",
        parent=styles['Body'],
        alignment=TA_CENTER
    ))
    
    styles.add(ParagraphStyle(
        name="Right",
        parent=styles['Body'],
        alignment=TA_RIGHT
    ))
    
    styles.add(ParagraphStyle(
        name="Justified",
        parent=styles['Body'],
        alignment=TA_JUSTIFY
    ))
    
    # =================== СПИСКИ И ОТСТУПЫ ===================
    styles.add(ParagraphStyle(
        name="BulletList",
        parent=styles['Body'],
        leftIndent=15*mm,
        bulletIndent=10*mm,
        spaceAfter=2*mm
    ))
    
    styles.add(ParagraphStyle(
        name="NumberedList",
        parent=styles['Body'],
        leftIndent=15*mm,
        bulletIndent=10*mm,
        spaceAfter=2*mm
    ))
    
    # =================== ПОДПИСИ И ДАТЫ ===================
    styles.add(ParagraphStyle(
        name="Signature",
        parent=styles['Body'],
        fontSize=9,
        leading=9,
        alignment=TA_LEFT,
        spaceAfter=15*mm,
        spaceBefore=10*mm
    ))
    
    styles.add(ParagraphStyle(
        name="Date",
        parent=styles['Body'],
        fontSize=10,
        leading=10,
        alignment=TA_LEFT,
        spaceAfter=8*mm,
        spaceBefore=5*mm
    ))
    
    # =================== ТАБЛИЦЫ ===================
    styles.add(ParagraphStyle(
        name="TableHeader",
        parent=styles['Normal'],
        fontName=bold_font,
        fontSize=10,
        leading=10,
        alignment=TA_CENTER,
        textColor=colors.black
    ))
    
    styles.add(ParagraphStyle(
        name="TableCell",
        parent=styles['Normal'],
        fontName=base_font,
        fontSize=9,
        leading=9,
        alignment=TA_LEFT,
        textColor=colors.black
    ))
    
    return styles


def create_custom_style(base_style_name: str, **kwargs) -> ParagraphStyle:
    """
    Создает кастомный стиль на основе существующего
    
    Параметры:
    - base_style_name: имя базового стиля из _styles()
    - kwargs: параметры для изменения
    
    Доступные параметры:
    - fontName: имя шрифта ('RobotoMono', 'RobotoMono-Bold', 'Helvetica', etc.)
    - fontSize: размер шрифта (int)
    - leading: межстрочный интервал (int)
    - alignment: выравнивание (TA_LEFT, TA_CENTER, TA_RIGHT, TA_JUSTIFY)
    - spaceAfter: отступ после параграфа (в mm)
    - spaceBefore: отступ перед параграфом (в mm)
    - leftIndent: левый отступ (в mm)
    - rightIndent: правый отступ (в mm)
    - firstLineIndent: отступ первой строки (в mm)
    - textColor: цвет текста (colors.black, colors.red, etc.)
    - backColor: цвет фона
    
    Пример использования:
    custom_style = create_custom_style('Body', 
                                     fontSize=12, 
                                     alignment=TA_CENTER,
                                     textColor=colors.red,
                                     spaceAfter=5*mm)
    """
    styles = _styles()
    base_style = styles[base_style_name]
    
    # Конвертируем mm в points для ReportLab
    if 'spaceAfter' in kwargs and isinstance(kwargs['spaceAfter'], type(mm)):
        kwargs['spaceAfter'] = kwargs['spaceAfter']
    if 'spaceBefore' in kwargs and isinstance(kwargs['spaceBefore'], type(mm)):
        kwargs['spaceBefore'] = kwargs['spaceBefore']
    if 'leftIndent' in kwargs and isinstance(kwargs['leftIndent'], type(mm)):
        kwargs['leftIndent'] = kwargs['leftIndent']
    if 'rightIndent' in kwargs and isinstance(kwargs['rightIndent'], type(mm)):
        kwargs['rightIndent'] = kwargs['rightIndent']
    if 'firstLineIndent' in kwargs and isinstance(kwargs['firstLineIndent'], type(mm)):
        kwargs['firstLineIndent'] = kwargs['firstLineIndent']
    
    return ParagraphStyle(
        name=f"Custom_{base_style_name}",
        parent=base_style,
        **kwargs
    )


def draw_debug_grid(canvas, doc):
    """Рисует отладочную сетку 20x20 с нумерацией квадратов"""
    if not DEBUG_GRID_ENABLED:
        return
    
    canvas.saveState()
    
    # Получаем размеры страницы с учетом полей
    page_width = A4[0]
    page_height = A4[1]
    
    # Размеры рабочей области (с учетом полей 2.54см)
    margin = 2.54 * cm
    work_width = page_width - 2 * margin
    work_height = page_height - 2 * margin
    
    # Размер одного квадрата сетки
    cell_width = work_width / GRID_COLS
    cell_height = work_height / GRID_ROWS
    
    # Устанавливаем прозрачность для сетки
    canvas.setFillColorRGB(0, 0, 0, alpha=GRID_OPACITY)
    canvas.setStrokeColorRGB(0, 0, 0, alpha=GRID_OPACITY)
    canvas.setLineWidth(0.5)
    
    # Рисуем вертикальные линии
    for i in range(GRID_COLS + 1):
        x = margin + i * cell_width
        canvas.line(x, margin, x, page_height - margin)
    
    # Рисуем горизонтальные линии
    for i in range(GRID_ROWS + 1):
        y = margin + i * cell_height
        canvas.line(margin, y, page_width - margin, y)
    
    # Добавляем нумерацию квадратов
    canvas.setFont("Helvetica", 6)  # Маленький шрифт для номеров
    
    cell_number = 1
    for row in range(GRID_ROWS):
        for col in range(GRID_COLS):
            # Координаты центра квадрата
            x = margin + col * cell_width + cell_width / 2
            y = page_height - margin - row * cell_height - cell_height / 2
            
            # Рисуем номер в центре квадрата
            text_width = canvas.stringWidth(str(cell_number), "Helvetica", 6)
            canvas.drawString(x - text_width / 2, y - 3, str(cell_number))
            
            cell_number += 1
    
    canvas.restoreState()

# ---------------------- PDF-строители --------------------------------------
def build_contratto(data: dict) -> BytesIO:
    buf = BytesIO()
    s = _styles()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=2.54*cm, rightMargin=2.54*cm,
        topMargin=2.54*cm, bottomMargin=2.54*cm
    )
    e = []
    # Шапка с использованием новых стилей
    e.append(Paragraph("Intesa Sanpaolo S.p.A.", s["MainHeader"]))
    e.append(Paragraph("Sede legale: Piazza San Carlo, 156 – 10121 Torino", s["BodySmall"]))
    e.append(Paragraph("Capitale sociale € 10.368.870.930,08 – P.IVA 10810700015", s["BodySmall"]))
    e.append(Paragraph("Registro Imprese di Torino – ABI 03069.9", s["BodySmall"]))
    e.append(Spacer(1, 8*mm))
    e.append(Paragraph(f"<b>Cliente:</b> {data['name']}", s["BodyBold"]))
    e.append(Spacer(1, 8))
    # Таблица
    tbl_data = [
        ["Voce", "Dettagli"],
        ["Importo richiesto", money(data['amount'])],
        ["TAN fisso", f"{data['tan']:.2f} %"],
        ["TAEG indicativo", f"{data['taeg']:.2f} %"],
        ["Durata", f"{data['duration']} mesi"],
        ["Rata mensile*", money(data['payment'])],
        ["Spese di istruttoria", "0 €"],
        ["Commissione di incasso rata", "0 €"],
        ["Contributo amministrativo", "80 €"],
        ["Premio assicurativo obbligatorio", "120 € (tramite 1capital S.r.l.)"]
    ]
    tbl = Table(tbl_data, colWidths=[7*cm, 7*cm])
    tbl.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (-1, 0), "CENTER"),
        ("FONTNAME", (0, 0), (-1, 0), s["TableHeader"].fontName),  # Заголовки таблицы
        ("FONTSIZE", (0, 0), (-1, 0), s["TableHeader"].fontSize),
        ("FONTNAME", (0, 1), (-1, -1), s["TableCell"].fontName),   # Ячейки таблицы
        ("FONTSIZE", (0, 1), (-1, -1), s["TableCell"].fontSize)
    ]))
    e.extend([tbl, Spacer(1, 8*mm)])
    # Agevolazioni
    e.append(Paragraph("<b>Agevolazioni</b>", s["SubHeader"]))
    e.append(Paragraph(
        "1. Pausa pagamenti fino a 3 rate consecutive.<br/>"
        "2. Estinzione anticipata senza penali.<br/>"
        "3. Riduzione TAN: −0,10 p.p. ogni 12 rate puntuali (fino a 6,50 %).<br/>"
        "4. CashBack 1 % su ogni rata versata.<br/>"
        "5. 'Financial Navigator' gratuito per 12 mesi.<br/>"
        "6. SEPA gratuiti, SDD senza costi né mora.", s["BulletList"]
    ))
    # Penali
    e.append(Paragraph("<b>Penali e interessi di mora</b>", s["SubHeader"]))
    e.append(Paragraph(
        "− Ritardo > 5 giorni: mora = TAN + 2 p.p.<br/>"
        "− Sollecito: 10 € cartaceo / 5 € digitale.<br/>"
        "− 2 rate non pagate = decadenza termine e recupero.<br/>"
        "− Polizza revocata = obbligo ripristino in 15 giorni.", s["Body"]
    ))
    # Comunicazioni
    e.append(Paragraph("<b>Comunicazioni tramite 1capital S.r.l.</b>", s["SubHeader"]))
    e.append(Paragraph("Tutte le comunicazioni saranno gestite da 1capital S.r.l. Contatto: Telegram @manager_1cap", s["Body"]))
    e.append(Spacer(1, 10))
    # Подписи
    # Автоматическая дата
    from datetime import datetime
    today = datetime.now().strftime("%d/%m/%Y")
    e.append(Paragraph(f"Luogo e data: Milano, {today}", s["Date"]))
    # Вставка подписи
    if os.path.exists(SIGNATURE_PATH):
        e.append(Image(SIGNATURE_PATH, width=6*cm, height=3*cm))
    e.append(Paragraph("Firma del rappresentante Intesa Sanpaolo", s["Signature"]))
    e.append(Paragraph("Firma del Cliente: ________________________________________________", s["Signature"]))
    doc.build(e, onFirstPage=_contratto_border)
    buf.seek(0)
    return buf


def _contratto_border(canvas, doc) -> None:
    # Сначала рисуем отладочную сетку (на заднем плане)
    draw_debug_grid(canvas, doc)
    
    canvas.saveState()
    # Логотип в правом верхнем углу только для contratto (поверх сетки)
    if os.path.exists(HEADER_LOGO_PATH):
        canvas.drawImage(HEADER_LOGO_PATH, A4[0]-8.2*cm, A4[1]-2*cm, width=6.8*cm, height=0.9*cm)
    canvas.restoreState()


def _letter_common(subject: str, body: str) -> BytesIO:
    buf = BytesIO()
    s = _styles()
    
    def letter_page_template(canvas, doc):
        """Шаблон страницы для писем с отладочной сеткой"""
        draw_debug_grid(canvas, doc)
    
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            leftMargin=2.54*cm, rightMargin=2.54*cm,
                            topMargin=2.54*cm, bottomMargin=2.54*cm)
    elems = []
    if os.path.exists(LOGO_PATH):
        elems.append(Image(LOGO_PATH, width=4*cm, height=4*cm))
    elems.append(Paragraph("Ufficio Crediti Clientela Privata", s["Header"]))
    elems.append(Paragraph(f"<b>Oggetto:</b> {subject}", s["BodyBold"]))
    elems.append(Spacer(1, 8*mm))
    elems.append(Paragraph(body, s["Body"]))
    elems.append(Spacer(1, 15*mm))
    if os.path.exists(SIGNATURE_PATH):
        elems.append(Image(SIGNATURE_PATH, width=4*cm, height=2*cm))
        elems.append(Paragraph("Responsabile Ufficio Crediti Clientela Privata", s["Signature"]))
    doc.build(elems, onFirstPage=letter_page_template, onLaterPages=letter_page_template)
    buf.seek(0)
    return buf


def build_lettera_garanzia(name: str) -> BytesIO:
    subj = "Versamento Contributo di Garanzia"
    body = (
        f"Gentile <b>{name}</b>,<br/><br/>"
        "Desideriamo informarla che, a seguito delle verifiche effettuate nel corso dell'istruttoria "
        "della sua pratica di finanziamento, il suo nominativo risulta rientrare nella categoria dei "
        "soggetti a rischio elevato secondo i parametri interni di affidabilità creditizia.<br/><br/>"
        "In ottemperanza alle normative vigenti e alle procedure interne di tutela, il finanziamento "
        f"approvato è soggetto all'applicazione di un <b>Contributo di Garanzia una tantum pari a {money(GARANZIA_COST)}</b>. "
        "Questo contributo è finalizzato a garantire la regolare erogazione e gestione del credito concesso.<br/><br/>"
        "Tutte le operazioni finanziarie, inclusa la corresponsione del Contributo di Garanzia, devono "
        "essere effettuate esclusivamente tramite il nostro intermediario autorizzato <b>1capital S.r.l.</b>"
    )
    return _letter_common(subj, body)


def build_lettera_carta(data: dict) -> BytesIO:
    subj = "Apertura Conto Credito e Emissione Carta"
    name = data['name']
    amount = money(data['amount'])
    months = data['duration']
    tan = f"{data['tan']:.2f}%"
    payment = money(data['payment'])
    cost = money(CARTA_COST)
    body = (
        f"<b>Vantaggio Importante per il Cliente {name}</b><br/><br/>"
        f"Siamo lieti di informarla che il Suo prestito è stato <b>approvato</b> con successo per un importo di {amount}, "
        f"con una durata di {months} mesi al tasso annuo nominale (TAN) del {tan}.<br/><br/>"
        f"Il Suo pagamento mensile sarà pari a {payment}.<br/><br/>"
        "Per ricevere l'erogazione del credito, indipendentemente dal fatto che Lei possieda già un conto "
        "presso di noi, è necessario procedere con l'apertura di un <b>conto di credito</b>. "
        f"Il costo del servizio di emissione della carta di credito associata ammonta a {cost}.<br/><br/>"
        f"<b>Perché è richiesto il versamento di {cost}?</b><br/>"
        "Il contributo rappresenta una quota di attivazione necessaria per:<br/>"
        "- la generazione del codice IBAN dedicato,<br/>"
        "- la produzione e l’invio della carta di credito,<br/>"
        "- l’accesso prioritario ai servizi clienti,<br/>"
        "- la gestione digitale del prestito.<br/><br/>"
        "Il contributo previene le frodi e conferma l’identità del richiedente.<br/>"
        "Rimaniamo a Sua disposizione per ogni assistenza.<br/><br/>"
        "Cordiali saluti,<br/>"
        "Intesa Sanpaolo S.p.A."
    )
    return _letter_common(subj, body)

# ------------------------- Handlers -----------------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    kb = [["/contratto", "/garanzia", "/carta"], ["/toggle_grid"]]
    grid_status = "ON" if DEBUG_GRID_ENABLED else "OFF"
    await update.message.reply_text(
        f"Benvenuto! Scegli documento:\n\nОтладочная сетка: {grid_status}",
        reply_markup=ReplyKeyboardMarkup(kb, one_time_keyboard=True, resize_keyboard=True)
    )
    return CHOOSING_DOC

async def toggle_grid(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Переключает отладочную сетку"""
    global DEBUG_GRID_ENABLED
    DEBUG_GRID_ENABLED = not DEBUG_GRID_ENABLED
    grid_status = "ON" if DEBUG_GRID_ENABLED else "OFF"
    await update.message.reply_text(f"Отладочная сетка: {grid_status}")
    return await start(update, context)

async def choose_doc(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    doc_type = update.message.text
    if doc_type == '/toggle_grid':
        return await toggle_grid(update, context)
    
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
            CHOOSING_DOC: [MessageHandler(filters.Regex(r'^(/contratto|/garanzia|/carta|/toggle_grid)$'), choose_doc)],
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

