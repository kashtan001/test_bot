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
import subprocess
import tempfile
from io import BytesIO
from decimal import Decimal, ROUND_HALF_UP

from telegram import Update, InputFile, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application, CommandHandler, ConversationHandler, MessageHandler, ContextTypes, filters,
)

from datetime import datetime


# ---------------------- Настройки ------------------------------------------
TOKEN = os.getenv("BOT_TOKEN", "YOUR_TOKEN_HERE")
DEFAULT_TAN = 7.86
DEFAULT_TAEG = 8.30
GARANZIA_COST = 180.0
CARTA_COST = 120.0


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


def format_money(amount: float) -> str:
    """Форматирование суммы в евро"""
    return f"€ {amount:,.2f}".replace(',', ' ')


def format_date() -> str:
    """Получение текущей даты в итальянском формате"""
    return datetime.now().strftime("%d/%m/%Y")


# ---------------------- Вызов внешнего сборщика PDF -------------------------
def build_pdf_external(doc: str, payload: dict) -> BytesIO:
    """Строит PDF через внешний скрипт pdf_costructor.py и возвращает BytesIO."""
    tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.pdf')
    tmp_path = tmp_file.name
    tmp_file.close()

    args = [
        'python3', 'pdf_costructor.py',
        '--doc', doc,
        '--output', tmp_path,
    ]

    # Опциональные аргументы
    if 'name' in payload:
        args += ['--name', str(payload['name'])]
    if 'amount' in payload:
        args += ['--amount', str(payload['amount'])]
    if 'duration' in payload:
        args += ['--duration', str(payload['duration'])]
    if 'tan' in payload:
        args += ['--tan', str(payload['tan'])]
    if 'taeg' in payload:
        args += ['--taeg', str(payload['taeg'])]
    if 'payment' in payload:
        args += ['--payment', str(payload['payment'])]
    if 'date' in payload:
        args += ['--date', str(payload['date'])]

    try:
        completed = subprocess.run(args, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        logging.info("pdf_costructor output: %s", completed.stdout)
        with open(tmp_path, 'rb') as f:
            pdf_bytes = f.read()
        buf = BytesIO(pdf_bytes)
        buf.seek(0)
        return buf
    except subprocess.CalledProcessError as e:
        logging.error("pdf_costructor failed: %s", e.stderr)
        raise
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass

# ---------------------- Handlers -----------------------------------------
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
        # Внешняя генерация через pdf_costructor.py
        buf = build_pdf_external('garanzia', {'name': name})
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
    # Внешняя генерация через pdf_costructor.py
    if dt == '/contratto':
        buf = build_pdf_external('contratto', d)
        filename = f"Contratto_{d['name']}.pdf"
    elif dt == '/garanzia':
        buf = build_pdf_external('garanzia', {'name': d['name']})
        filename = f"Garanzia_{d['name']}.pdf"
    else:
        buf = build_pdf_external('carta', d)
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

