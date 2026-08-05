import logging
import os
import datetime
import asyncio
import re
import hashlib
import json
import httpx
import asyncpg
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, KeyboardButton, WebAppInfo
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    filters, ContextTypes, ConversationHandler
)

# ── NOVA POSHTA API — ЖИВИЙ ПОШУК НАСЕЛЕНИХ ПУНКТІВ ─────────────
NOVA_POSHTA_API_KEY = os.environ.get("NOVA_POSHTA_API_KEY", "")
NOVA_POSHTA_URL = "https://api.novaposhta.ua/v2.0/json/"

async def search_settlements(query: str, oblast: str, limit: int = 8):
    """Шукає населені пункти через API Нової Пошти, фільтрує за областю."""
    query = query.strip()
    if not NOVA_POSHTA_API_KEY or len(query) < 2:
        return []
    payload = {
        "apiKey": NOVA_POSHTA_API_KEY,
        "modelName": "Address",
        "calledMethod": "getCities",
        "methodProperties": {"FindByString": query, "Limit": "40"}
    }
    try:
        async with httpx.AsyncClient(timeout=6.0) as client:
            resp = await client.post(NOVA_POSHTA_URL, json=payload)
            data = resp.json()
        if not data.get("success"):
            return []
        items = data.get("data", [])
        oblast_key = oblast.replace("область", "").replace("м.", "").strip().lower()
        results, seen = [], set()
        for it in items:
            name = it.get("Description", "")
            area = (it.get("AreaDescription", "") or "").lower()
            if not name or name in seen:
                continue
            if oblast_key and oblast_key not in area:
                continue
            seen.add(name)
            results.append(name)
            if len(results) >= limit:
                break
        return results
    except Exception as e:
        logging.error(f"Nova Poshta API error: {e}")
        return []

# ── РАЙОНИ ВЕЛИКИХ МІСТ (офіційний адміністративний поділ) ──────
MAJOR_CITY_DISTRICTS = {
    "Київ": ["Голосіївський","Дарницький","Деснянський","Дніпровський","Оболонський",
             "Печерський","Подільський","Святошинський","Солом'янський","Шевченківський"],
    "Харків": ["Основ'янський","Київський","Слобідський","Шевченківський","Немишлянський",
               "Новобаварський","Холодногірський","Індустріальний","Салтівський"],
    "Одеса": ["Приморський","Київський","Малиновський","Суворовський"],
    "Дніпро": ["Амур-Нижньодніпровський","Індустріальний","Новокодацький","Соборний",
               "Центральний","Чечелівський","Шевченківський"],
    "Львів": ["Галицький","Залізничний","Личаківський","Сихівський","Франківський","Шевченківський"],
    "Запоріжжя": ["Заводський","Комунарський","Олександрівський","Орджонікідзевський",
                  "Шевченківський","Дніпровський","Вознесенівський"],
    "Миколаїв": ["Заводський","Інгульський","Корабельний","Центральний"],
    "Кривий Ріг": ["Дзержинський","Довгинцівський","Інгулецький","Металургійний",
                   "Покровський","Саксаганський","Тернівський"],
}

# ── GOOGLE SHEETS ────────────────────────────────────────────────
import gspread
from google.oauth2.service_account import Credentials

# ── ГЕНЕРАЦІЯ ПАСПОРТА ГРАВЦЯ (за затвердженим макетом) ──────────
import io
from PIL import Image, ImageDraw, ImageFont
import qrcode

FONT_DIR = "fonts"
TEMPLATE_PATH = "templates/passport_template.png"

NAVY = (16, 34, 74)
GRAY_TEXT = (110, 120, 140)
SILHOUETTE_BLUE = (150, 175, 215)
RIGHT_COLUMN_CENTER_X = 851

def font(size, bold=False):
    path = f"{FONT_DIR}/DejaVuSans-Bold.ttf" if bold else f"{FONT_DIR}/DejaVuSans.ttf"
    return ImageFont.truetype(path, size)

# ── Транслітерація українською → англійською (офіційна система) ──
_TRANSLIT_MAP = {
    "а":"a","б":"b","в":"v","г":"h","ґ":"g","д":"d","е":"e","є":"ie","ж":"zh",
    "з":"z","и":"y","і":"i","ї":"i","й":"i","к":"k","л":"l","м":"m","н":"n",
    "о":"o","п":"p","р":"r","с":"s","т":"t","у":"u","ф":"f","х":"kh","ц":"ts",
    "ч":"ch","ш":"sh","щ":"shch","ь":"","ю":"iu","я":"ia","'":"","’":"",
}
_TRANSLIT_FIRST = {"є":"Ye","ї":"Yi","й":"Y","ю":"Yu","я":"Ya"}

def transliterate(text):
    if not text:
        return ""
    words = text.split()
    out_words = []
    for w in words:
        chars = []
        for i, ch in enumerate(w):
            low = ch.lower()
            if i == 0 and low in _TRANSLIT_FIRST:
                piece = _TRANSLIT_FIRST[low]
            else:
                piece = _TRANSLIT_MAP.get(low, ch)
            if ch.isupper() and piece:
                piece = piece[0].upper() + piece[1:]
            chars.append(piece)
        out_words.append("".join(chars))
    return " ".join(out_words)

def make_qr(data, size=170, logo_text="KS"):
    """Генерує QR з високим рівнем корекції помилок, щоб витримати логотип по центру."""
    qr = qrcode.QRCode(border=1, box_size=8, error_correction=qrcode.constants.ERROR_CORRECT_H)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color=NAVY, back_color="white").convert("RGB")
    img = img.resize((size, size))

    # Значок-щит з написом "KS" по центру QR
    draw = ImageDraw.Draw(img)
    shield_r = size // 7
    ccx, ccy = size // 2, size // 2
    draw.ellipse([ccx-shield_r-6, ccy-shield_r-6, ccx+shield_r+6, ccy+shield_r+6], fill="white")
    draw.ellipse([ccx-shield_r, ccy-shield_r, ccx+shield_r, ccy+shield_r], fill=NAVY)
    lf = font(shield_r, bold=True)
    lb = draw.textbbox((0,0), logo_text, font=lf)
    lw, lh = lb[2]-lb[0], lb[3]-lb[1]
    draw.text((ccx-lw/2, ccy-lh/2-lb[1]), logo_text, font=lf, fill="white")
    return img

def draw_silhouette(draw, box):
    """Малює нейтральний силует людини (аватар-заглушка) замість реального фото."""
    x0, y0, x1, y1 = box
    w, h = x1-x0, y1-y0
    cx = (x0+x1)//2

    # Голова
    head_r = w * 0.19
    head_cy = y0 + h*0.34
    draw.ellipse([cx-head_r, head_cy-head_r, cx+head_r, head_cy+head_r], fill=SILHOUETTE_BLUE)

    # Плечі/тулуб — половина еліпса, обрізана рамкою фото
    shoulder_w = w * 0.62
    shoulder_top = y0 + h*0.56
    draw.ellipse([cx-shoulder_w/2, shoulder_top, cx+shoulder_w/2, shoulder_top + shoulder_w*0.9],
                 fill=SILHOUETTE_BLUE)
    # Прямокутник щоб «дообрізати» низ силуету по межі фото-блоку
    draw.rectangle([x0, min(y1-2, shoulder_top+shoulder_w*0.55), x1, y1], fill=None)

def generate_passport(answers: dict, passport_number: str, verification_url: str = "") -> io.BytesIO:
    """
    Бере ЗАТВЕРДЖЕНИЙ шаблон паспорта (templates/passport_template.png) як фон
    і накладає ТІЛЬКИ змінні дані. Дизайн шаблону (прапор, заголовок, бейдж
    «ГРАВЕЦЬ», логотип ліги, голограма, підпис, футер) НЕ перемальовується —
    він завжди береться з оригінального файлу як є.
    """
    img = Image.open(TEMPLATE_PATH).convert("RGB")
    draw = ImageDraw.Draw(img)

    # ── Фото: нейтральний силует замість реального фото (приватність дітей) ──
    photo_box = [88, 135, 290, 388]
    draw_silhouette(draw, photo_box)

    # ── Дані у правому інфо-стовпчику ──
    col_x = 384  # +32px відступ від лівого краю поля (виміряно з еталону)

    # Ім'я ВЕЛИКИМИ ЛІТЕРАМИ + транслітерація англійською під ним
    name = answers.get("contact_name", "—")
    name_upper = name.upper()
    name_font = font(24, bold=True)
    # Якщо ім'я задовге — трохи зменшуємо шрифт, щоб не вилазило за лінію
    nb = draw.textbbox((0,0), name_upper, font=name_font)
    if nb[2]-nb[0] > 295:
        name_font = font(19, bold=True)
    draw.text((col_x, 210), name_upper, font=name_font, fill=NAVY)
    translit = transliterate(name).upper()
    draw.text((col_x, 240), translit, font=font(12), fill=GRAY_TEXT)

    nick = answers.get("nickname") or "—"
    draw.text((col_x, 326), nick, font=font(19), fill=NAVY)

    school_raw = answers.get("school_name", "—")
    school = f"ШКОЛА № {school_raw}" if school_raw.strip().isdigit() else school_raw
    draw.text((col_x, 413), school, font=font(19), fill=NAVY)

    grade = answers.get("grade", "—")
    draw.text((col_x, 500), str(grade), font=font(19), fill=NAVY)

    # ── Дати: Видано / Дійсна до ──
    issued = datetime.date.today()
    valid_until = add_one_year(issued)
    date_font = font(15)
    draw.text((65, 542), issued.strftime("%d.%m.%Y"), font=date_font, fill=NAVY)
    draw.text((208, 542), valid_until.strftime("%d.%m.%Y"), font=date_font, fill=NAVY)

    # ── № документа та QR містять один і той самий ідентифікатор ──
    # Канонічний формат: AA-26-00-0001. На картці дефіси лише візуально
    # замінюються крапками: AA • 26 • 00 • 0001.
    doc_pretty = passport_number.replace("-", " • ")
    docnum_font = font(16, bold=True)
    dn = draw.textbbox((0, 0), doc_pretty, font=docnum_font)
    if dn[2]-dn[0] > 150:
        docnum_font = font(13, bold=True)
        dn = draw.textbbox((0, 0), doc_pretty, font=docnum_font)
    draw.text((RIGHT_COLUMN_CENTER_X - (dn[2]-dn[0])/2, 284), doc_pretty, font=docnum_font, fill=NAVY)

    # ── QR-код зі значком «KS» по центру — справжній, скановуваний ──
    # Стара рамка шаблону не квадратна (139×170) — «стираємо» її кольором фону
    # і малюємо нову, точно квадратну, рамку по контуру самого QR
    BG_MATCH = (234, 232, 236)
    draw.rectangle([778, 322, 925, 500], fill=BG_MATCH)

    # QR кодує рівно той самий номер, що надрукований на документі.
    # Якщо відомий username бота, QR відкриває безпечну перевірку саме цієї
    # ліцензії в Telegram. Інакше зберігає номер як запасний варіант.
    qr_data = verification_url or passport_number
    qr_box_size = 150
    qr_img = make_qr(qr_data, size=qr_box_size, logo_text="KS")
    qr_cx, qr_cy = RIGHT_COLUMN_CENTER_X, 411
    qr_x = qr_cx - qr_box_size // 2
    qr_y = qr_cy - qr_box_size // 2

    pad = 6
    draw.rectangle(
        [qr_x - pad, qr_y - pad, qr_x + qr_box_size + pad, qr_y + qr_box_size + pad],
        outline=NAVY, width=3
    )
    img.paste(qr_img, (qr_x, qr_y))

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf
SHEET_ID = "1f61HYd4MQQnBj6z-mWrZ-2arn0r6r9WWbYJ4vphPY1s"
SURVEY_SHEET_TITLE = "Анкети — повні дані"
SURVEY_COLUMNS = [
    ("submitted_at", "Дата й час проходження"),
    ("passport_number", "№ паспорта спортсмена"),
    ("parental_consent", "Згода батьків / законного представника"),
    ("gender", "П1. Стать"),
    ("contact_name", "П2. Ім’я та прізвище"),
    ("birth_date", "П3. Дата народження"),
    ("region", "П4. Область"),
    ("city_name", "П5. Населений пункт"),
    ("district", "П6. Район міста"),
    ("school_type", "П7. Тип школи"),
    ("school_name", "П8. Назва або номер школи"),
    ("grade", "П9–9б. Клас"),
    ("sport_active", "П10. Заняття спортом"),
    ("sport_type", "П11. Вид спорту"),
    ("sport_level", "П12. Рівень занять спортом"),
    ("sport_coach", "П13. Наявність тренера"),
    ("sport_why_not", "П11а. Чому не займається спортом"),
    ("sport_would_like", "П11б. Бажаний вид спорту"),
    ("watch_sport", "П14. Перегляд спорту"),
    ("watch_where", "П15. Де переглядає спорт"),
    ("fav_sport_watch", "П16. Улюблений спорт для перегляду"),
    ("phys_ed", "П17. Ставлення до фізкультури"),
    ("phys_out", "П18. Активність поза школою"),
    ("pc_play", "П19. Грає на ПК"),
    ("pc_hours", "П20. Години гри на ПК"),
    ("pc_genre", "П21. Жанр ігор на ПК"),
    ("pc_game", "П22. Гра на ПК"),
    ("pc_compete", "П23. Змагання на ПК"),
    ("pc_level", "П24. Рівень гри на ПК"),
    ("pc_club", "П25. Клуб / команда на ПК"),
    ("console_play", "П26. Грає на консолі"),
    ("console_model", "П27. Модель консолі"),
    ("console_hours", "П28. Години гри на консолі"),
    ("console_genre", "П29. Жанр ігор на консолі"),
    ("console_game", "П30. Гра на консолі"),
    ("console_compete", "П31. Змагання на консолі"),
    ("console_club", "П32. Клуб / команда на консолі"),
    ("mobile_play", "П33. Грає на мобільному"),
    ("mobile_hours", "П34. Години гри на мобільному"),
    ("game_brawl", "П35. Brawl Stars"),
    ("game_roblox", "П36. Roblox"),
    ("game_minecraft", "П37. Minecraft"),
    ("game_clash", "П38. Clash Royale"),
    ("game_hok", "П39. Honor of Kings"),
    ("game_mlbb", "П40. Mobile Legends: Bang Bang"),
    ("game_pubg", "П41. PUBG Mobile"),
    ("mobile_other", "П42. Інша мобільна гра"),
    ("mobile_genre", "П43. Жанр мобільних ігор"),
    ("mobile_compete", "П44. Змагання в мобільних іграх"),
    ("mobile_level", "П45. Рівень мобільної гри"),
    ("mobile_club", "П46. Клуб / команда в мобільних іграх"),
    ("esports_know", "П47. Обізнаність про кіберспорт"),
    ("esports_watch", "П48. Перегляд кіберспорту"),
    ("esports_watch_where", "П49. Де переглядає кіберспорт"),
    ("esports_compete", "П50. Участь у кіберспортивних змаганнях"),
    ("esports_team", "П51. Наявність кіберспортивної команди"),
    ("motivation", "П52. Мотивація в іграх"),
    ("esports_attract", "П53. Що приваблює в кіберспорті"),
    ("time_ready", "П54. Готовність приділяти час клубу"),
    ("toxic", "П55. Токсична поведінка"),
    ("respect_rule", "П56. Важливість поваги"),
    ("safe_feel", "П57. Що створює безпеку в клубі"),
    ("club_join", "П58. Бажання вступити до клубу"),
    ("club_role", "П59. Бажана роль у клубі"),
    ("club_important", "П60. Найважливіше у клубі"),
    ("parents_support", "П61. Підтримка батьків"),
    ("parents_allow", "П62. Дозвіл на тренування після уроків"),
    ("future", "П63. Бажання пов’язати майбутнє з кіберспортом"),
    ("future_role", "П64. Бажана майбутня професія"),
    ("safety_answer", "П65. Питання про безпеку та підтримку"),
]
SURVEY_COLUMN_INDEX = {key: index for index, (key, _title) in enumerate(SURVEY_COLUMNS)}
SURVEY_HEADERS = [title for _key, title in SURVEY_COLUMNS]

_gsheet = None

def get_sheet():
    """Повертає повний лист анкети; старий перший лист лишається архівом."""
    global _gsheet
    if _gsheet is None:
        try:
            import json
            scopes = [
                "https://www.googleapis.com/auth/spreadsheets",
                "https://www.googleapis.com/auth/drive",
            ]
            creds_json = os.environ.get("GOOGLE_CREDS_JSON")
            if creds_json:
                info = json.loads(creds_json)
                creds = Credentials.from_service_account_info(info, scopes=scopes)
            else:
                creds_file = os.environ.get("GOOGLE_CREDS_FILE", "credentials.json")
                creds = Credentials.from_service_account_file(creds_file, scopes=scopes)
            client = gspread.authorize(creds)
            spreadsheet = client.open_by_key(SHEET_ID)
            try:
                _gsheet = spreadsheet.worksheet(SURVEY_SHEET_TITLE)
            except gspread.WorksheetNotFound:
                _gsheet = spreadsheet.add_worksheet(
                    title=SURVEY_SHEET_TITLE, rows=1000, cols=len(SURVEY_HEADERS)
                )
                _gsheet.append_row(SURVEY_HEADERS)
                _gsheet.freeze(rows=1)
            else:
                # Не змінюємо попередні відповіді. Якщо після оновлення анкети
                # з'явилися нові поля, дописуємо лише відсутні заголовки справа.
                existing_headers = _gsheet.row_values(1)
                for column_index, header in enumerate(SURVEY_HEADERS, start=1):
                    if column_index > len(existing_headers):
                        _gsheet.update_cell(1, column_index, header)
        except Exception as e:
            logging.error(f"Не вдалося підключитись до Google Sheets: {e}")
            _gsheet = False
    return _gsheet

def add_one_year(date_value: datetime.date) -> datetime.date:
    """Безпечно додає рік, зокрема для 29 лютого."""
    try:
        return date_value.replace(year=date_value.year + 1)
    except ValueError:
        return date_value.replace(year=date_value.year + 1, month=2, day=28)

def make_verification_url(bot_username: str, passport_number: str) -> str:
    """Формує Telegram deep-link для безпечної перевірки однієї ліцензії."""
    username = (bot_username or "").lstrip("@").strip()
    if not username:
        return ""
    return f"https://t.me/{username}?start=verify_{passport_number}"

async def verify_license(update: Update, passport_number: str):
    """Показує тільки безпечні дані конкретної ліцензії, а не анкету."""
    if db_pool is None:
        await update.message.reply_text("⚠️ Реєстр тимчасово недоступний. Спробуйте пізніше.")
        return ConversationHandler.END
    try:
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                """SELECT status, full_name, school, grade, issued_at, valid_until
                   FROM licenses WHERE passport_number = $1""",
                passport_number
            )
    except Exception as e:
        logging.error(f"Помилка перевірки ліцензії: {e}")
        await update.message.reply_text("⚠️ Не вдалося перевірити ліцензію. Спробуйте пізніше.")
        return ConversationHandler.END

    if row is None:
        await update.message.reply_text("⛔ Ліцензію з таким номером не знайдено.")
        return ConversationHandler.END

    is_active = row["status"] == "active" and row["valid_until"] >= datetime.date.today()
    if is_active:
        await update.message.reply_text(
            "✅ *Ліцензія дійсна*\n\n"
            f"№ {passport_number}\n{row['full_name']}\n{row['school']}, {row['grade']} клас\n"
            f"Видано: {row['issued_at'].strftime('%d.%m.%Y')}\n"
            f"Дійсна до: {row['valid_until'].strftime('%d.%m.%Y')}",
            parse_mode="Markdown",
        )
    else:
        await update.message.reply_text(
            f"⛔ *Ліцензія недійсна*\n\n№ {passport_number}", parse_mode="Markdown"
        )
    return ConversationHandler.END

DOCUMENT_NUMBER_RE = re.compile(r"^([A-Z]{2})-(\d{2})-(\d{2})-(\d{4})$")
DOCUMENTS_PER_BLOCK = 9_999
BLOCKS_PER_SERIES = 100
DOCUMENTS_PER_SERIES = BLOCKS_PER_SERIES * DOCUMENTS_PER_BLOCK

DATABASE_URL = os.environ.get("DATABASE_URL", "")
LICENSE_PEPPER = os.environ.get("LICENSE_PEPPER", "")
db_pool = None  # ініціалізується при старті бота (post_init)

def _series_for_index(index: int) -> str:
    """0 → AA, 1 → AB, ... 25 → AZ, 26 → BA."""
    if index < 0:
        raise ValueError("Індекс серії не може бути від'ємним")
    return f"{chr(65 + index // 26)}{chr(65 + index % 26)}"

def _decode_sequence(seq: int):
    """Перетворює атомарний номер з license_sequence на (серія, блок, порядковий)."""
    idx = seq - 1
    series_index, series_offset = divmod(idx, DOCUMENTS_PER_SERIES)
    block, serial_offset = divmod(series_offset, DOCUMENTS_PER_BLOCK)
    return _series_for_index(series_index), block, serial_offset + 1

def _normalise_identity(value: str) -> str:
    return " ".join((value or "").strip().casefold().split())

def make_participant_key(answers: dict) -> str:
    """Постійний, але незворотний ключ дитини для повторної видачі ліцензії."""
    name = _normalise_identity(answers.get("contact_name", ""))
    bdate = _normalise_identity(answers.get("birth_date", ""))
    if not LICENSE_PEPPER:
        raise RuntimeError("LICENSE_PEPPER не задано")
    raw = f"{name}|{bdate}|{LICENSE_PEPPER}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()

async def init_db(app):
    """Створює пул з'єднань з PostgreSQL при старті бота."""
    global db_pool
    if not DATABASE_URL:
        logging.error("DATABASE_URL не задано — видача номерів працювати не буде")
        return
    if not LICENSE_PEPPER:
        raise RuntimeError("LICENSE_PEPPER не задано — запуск зупинено з міркувань безпеки")
    db_pool = await asyncpg.create_pool(
        DATABASE_URL,
        min_size=1,
        max_size=10,
        statement_cache_size=0,
    )
    logging.info("✅ Підключення до PostgreSQL встановлено")

async def close_db(app):
    global db_pool
    if db_pool:
        await db_pool.close()

async def get_or_create_license(participant_key: str, answers: dict) -> str:
    """
    Атомарно видає номер посвідчення у форматі AA-26-00-0001.

    Нова дитина отримує наступний вільний номер через PostgreSQL SEQUENCE —
    це гарантовано унікально, навіть якщо сотні запитів прийдуть одночасно.
    Дитина, що вже проходила опитування раніше (той самий ПІБ + дата
    народження), отримує ТОЙ САМИЙ номер — змінюється лише рік.
    """
    if db_pool is None:
        raise RuntimeError("Немає з'єднання з базою даних")

    year = datetime.date.today().year % 100
    valid_until = add_one_year(datetime.date.today())

    async with db_pool.acquire() as conn:
        async with conn.transaction():
            # Серіалізує лише повторні запити однієї людини. PostgreSQL sequence
            # безпечно видає номери також при кількох процесах бота.
            await conn.execute("SELECT pg_advisory_xact_lock(hashtext($1))", participant_key)
            row = await conn.fetchrow(
                "SELECT sequence_number FROM licenses WHERE participant_key = $1 FOR UPDATE",
                participant_key
            )
            if row is not None:
                seq = row["sequence_number"]
                series, block, serial = _decode_sequence(seq)
                passport_number = f"{series}-{year:02d}-{block:02d}-{serial:04d}"
                await conn.execute(
                    """UPDATE licenses SET
                           series=$1, year=$2, block=$3, serial=$4,
                           passport_number=$5, full_name=$6, school=$7,
                           grade=$8, nickname=$9, status='active',
                           issued_at=$10, valid_until=$11,
                           updated_at=now()
                       WHERE participant_key=$12""",
                    series, year, block, serial, passport_number,
                    answers.get("contact_name", ""), answers.get("school_name", ""),
                    str(answers.get("grade", "")), answers.get("nickname", ""),
                    datetime.date.today(), valid_until, participant_key
                )
                return passport_number

            seq = await conn.fetchval("SELECT nextval('license_sequence')")
            series, block, serial = _decode_sequence(seq)
            passport_number = f"{series}-{year:02d}-{block:02d}-{serial:04d}"
            await conn.execute(
                """INSERT INTO licenses
                   (participant_key, sequence_number, series, year, block, serial,
                    passport_number, full_name, school, grade, nickname,
                    status, issued_at, valid_until)
                   VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14)""",
                participant_key, seq, series, year, block, serial,
                passport_number, answers.get("contact_name", ""),
                answers.get("school_name", ""), str(answers.get("grade", "")),
                answers.get("nickname", ""), "active", datetime.date.today(), valid_until
            )
            return passport_number

def save_to_sheet(answers: dict):
    """Записує повний набір відповідей строго у порядку питань бота."""
    sheet = get_sheet()
    if not sheet:
        return False
    try:
        row = [
            datetime.datetime.now().strftime("%Y-%m-%d %H:%M") if key == "submitted_at"
            else answers.get(key, "")
            for key, _title in SURVEY_COLUMNS
        ]
        sheet.append_row(row)
        logging.info("Рядок записано у Google Таблицю")
        return True
    except Exception as e:
        logging.error(f"Помилка запису у Google Sheets: {e}")
        return False

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("BOT_TOKEN")
MINI_APP_URL = os.environ.get("MINI_APP_URL", "https://app.eschool.gg").strip().rstrip("/")
MINIAPP_INTERNAL_TOKEN = os.environ.get("MINIAPP_INTERNAL_TOKEN", "").strip()
ALERT_CHAT_IDS = [
    int(value.strip())
    for value in os.environ.get("ALERT_CHAT_IDS", "").split(",")
    if value.strip().lstrip("-").isdigit()
]

(
    CONSENT, GENDER, REGION, FULL_NAME, BIRTH_DATE, GRADE, GRADE_LETTER,
    CITY_TYPE, CITY_SELECT, CITY_NAME, DISTRICT, SCHOOL_TYPE, SCHOOL_NAME,
    SPORT_ACTIVE, SPORT_TYPE, SPORT_LEVEL, SPORT_COACH,
    SPORT_WHY_NOT, SPORT_WOULD_LIKE,
    WATCH_SPORT, WATCH_WHERE, FAV_SPORT_WATCH, PHYS_ED, PHYS_OUT,
    PC_PLAY, PC_HOURS, PC_GENRE, PC_GAME, PC_COMPETE, PC_LEVEL, PC_CLUB,
    CONSOLE_PLAY, CONSOLE_MODEL, CONSOLE_HOURS, CONSOLE_GENRE,
    CONSOLE_GAME, CONSOLE_COMPETE, CONSOLE_CLUB,
    MOBILE_PLAY, MOBILE_HOURS,
    GAME_BRAWL, GAME_ROBLOX, GAME_MINECRAFT, GAME_CLASH,
    GAME_HOK, GAME_MLBB, GAME_PUBG,
    MOBILE_OTHER, MOBILE_GENRE, MOBILE_COMPETE, MOBILE_LEVEL, MOBILE_CLUB,
    ESPORTS_KNOW, ESPORTS_WATCH, ESPORTS_WATCH_WHERE, ESPORTS_COMPETE, ESPORTS_TEAM,
    MOTIVATION, ESPORTS_ATTRACT, TIME_READY,
    TOXIC, RESPECT_RULE, SAFE_FEEL,
    CLUB_JOIN, CLUB_ROLE, CLUB_IMPORTANT, PARENTS_SUPPORT, PARENTS_ALLOW,
    FUTURE, FUTURE_ROLE,
) = range(70)

# ── ДАНІ ПРО ОБЛАСТІ: ЦЕНТРИ ТА ВЕЛИКІ МІСТА ────────────────────
OBLAST_CENTERS = {
    "Вінницька": "Вінниця", "Волинська": "Луцьк", "Дніпропетровська": "Дніпро",
    "Донецька": "Донецьк", "Житомирська": "Житомир", "Закарпатська": "Ужгород",
    "Запорізька": "Запоріжжя", "Івано-Франківська": "Івано-Франківськ",
    "Київська": "Київ", "Кіровоградська": "Кропивницький", "Луганська": "Луганськ",
    "Львівська": "Львів", "Миколаївська": "Миколаїв", "Одеська": "Одеса",
    "Полтавська": "Полтава", "Рівненська": "Рівне", "Сумська": "Суми",
    "Тернопільська": "Тернопіль", "Харківська": "Харків", "Херсонська": "Херсон",
    "Хмельницька": "Хмельницький", "Черкаська": "Черкаси", "Чернівецька": "Чернівці",
    "Чернігівська": "Чернігів", "м. Київ": "Київ",
}

OBLAST_CITIES = {
    "Вінницька": ["Жмеринка", "Могилів-Подільський", "Козятин", "Ладижин"],
    "Волинська": ["Ковель", "Володимир", "Нововолинськ", "Камінь-Каширський"],
    "Дніпропетровська": ["Кривий Ріг", "Кам'янське", "Нікополь", "Павлоград"],
    "Донецька": ["Маріуполь", "Краматорськ", "Слов'янськ", "Бахмут"],
    "Житомирська": ["Бердичів", "Новоград-Волинський", "Коростень"],
    "Закарпатська": ["Мукачево", "Хуст", "Берегове", "Виноградів"],
    "Запорізька": ["Мелітополь", "Бердянськ", "Енергодар"],
    "Івано-Франківська": ["Калуш", "Коломия", "Надвірна"],
    "Київська": ["Біла Церква", "Бровари", "Бориспіль", "Ірпінь"],
    "Кіровоградська": ["Олександрія", "Знам'янка"],
    "Луганська": ["Сєвєродонецьк", "Лисичанськ", "Рубіжне"],
    "Львівська": ["Дрогобич", "Червоноград", "Стрий", "Самбір"],
    "Миколаївська": ["Вознесенськ", "Первомайськ", "Южноукраїнськ"],
    "Одеська": ["Ізмаїл", "Білгород-Дністровський", "Чорноморськ"],
    "Полтавська": ["Кременчук", "Горішні Плавні", "Миргород"],
    "Рівненська": ["Дубно", "Костопіль", "Сарни"],
    "Сумська": ["Конотоп", "Шостка", "Охтирка"],
    "Тернопільська": ["Чортків", "Кременець", "Бережани"],
    "Харківська": ["Лозова", "Ізюм", "Куп'янськ", "Чугуїв"],
    "Херсонська": ["Нова Каховка", "Каховка", "Скадовськ"],
    "Хмельницька": ["Кам'янець-Подільський", "Шепетівка", "Нетішин"],
    "Черкаська": ["Умань", "Сміла", "Золотоноша"],
    "Чернівецька": ["Новодністровськ", "Хотин", "Кіцмань"],
    "Чернігівська": ["Ніжин", "Прилуки", "Новгород-Сіверський"],
    "м. Київ": [],
}

SUPPORT_TEXT = (
    "💙 *Національна дитяча лінія психологічної підтримки*\n\n"
    "Це безкоштовна лінія, куди можна зателефонувати, якщо тобі важко, сумно, "
    "тебе хтось ображає (в іграх, у школі чи вдома), або просто хочеться з кимось поговорити.\n\n"
    "📞 *116 111* — безкоштовно з мобільного\n"
    "📞 *0 800 500 225* — безкоштовно\n\n"
    "_Анонімно · конфіденційно · працює цілодобово._"
)

def kb(options, cols=2):
    rows = [options[i:i+cols] for i in range(0, len(options), cols)]
    return ReplyKeyboardMarkup([[KeyboardButton(o) for o in row] for row in rows],
                               resize_keyboard=True, one_time_keyboard=True)

def save(ctx, key, val): ctx.user_data[key] = val
def grade_int(ctx):
    raw = str(ctx.user_data.get("grade", 0))
    digits = "".join(ch for ch in raw if ch.isdigit())
    return int(digits) if digits else 0

# ── СТАРТ ──────────────────────────────────────────────────────────
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Головний вхід: перевірка QR або запуск Telegram Mini App."""
    if ctx.args and ctx.args[0].startswith("verify_"):
        passport_number = ctx.args[0][len("verify_"):].upper()
        if DOCUMENT_NUMBER_RE.fullmatch(passport_number):
            return await verify_license(update, passport_number)
        await update.message.reply_text("⛔ Некоректний номер ліцензії.")
        return ConversationHandler.END

    ctx.user_data.clear()
    await update.message.reply_text(
        "👋 *Привіт!*\n\n"
        "Відкрий офіційну анкету ESUL Underground. Вона збереже прогрес "
        "після кожного блоку, а після завершення бот сформує паспорт спортсмена.",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup(
            [[KeyboardButton("🚀 Розпочни свій шлях", web_app=WebAppInfo(url=MINI_APP_URL))]],
            resize_keyboard=True,
            one_time_keyboard=True,
        ),
    )
    return ConversationHandler.END

async def legacy_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Резервна стара анкета у чаті, доступна через /legacy."""
    # QR відкриває бота з параметром verify_AA-26-00-0001.
    if ctx.args and ctx.args[0].startswith("verify_"):
        passport_number = ctx.args[0][len("verify_"):].upper()
        if DOCUMENT_NUMBER_RE.fullmatch(passport_number):
            return await verify_license(update, passport_number)
        await update.message.reply_text("⛔ Некоректний номер ліцензії.")
        return ConversationHandler.END

    ctx.user_data.clear()
    await update.message.reply_text(
        "👋 Привіт!\n\n"
        "Це *офіційне опитування* для школярів України про спорт та кіберспорт.\n\n"
        "🏆 *Мета:* створити кіберспортивний клуб у твоїй школі!\n\n"
        "⏱ Займе приблизно 10 хвилин\n\n"
        "Перед початком потрібна *згода батьків або законного представника*.",
        parse_mode="Markdown",
        reply_markup=kb(["✅ Батьки дають згоду — починаємо", "❌ Без згоди — вийти"], cols=1)
    )
    return CONSENT

async def myid(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Показує числовий chat_id для підключення службових сповіщень."""
    await update.message.reply_text(
        f"Ваш Telegram chat_id: `{update.effective_chat.id}`\n\n"
        "Надішліть це число адміністратору бота.",
        parse_mode="Markdown"
    )

async def web_app_submission(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Забирає завершену Mini App-анкету та запускає видачу паспорта."""
    try:
        if not MINIAPP_INTERNAL_TOKEN:
            raise RuntimeError("MINIAPP_INTERNAL_TOKEN не налаштований")

        payload = json.loads(update.message.web_app_data.data)
        submission_id = str(payload.get("submissionId", ""))
        if payload.get("type") != "survey_complete" or not re.fullmatch(
            r"[0-9a-fA-F-]{36}", submission_id
        ):
            raise ValueError("Некоректний ідентифікатор анкети")

        async with httpx.AsyncClient(timeout=12.0) as client:
            response = await client.get(
                f"{MINI_APP_URL}/api/submissions/{submission_id}",
                headers={"X-Internal-Token": MINIAPP_INTERNAL_TOKEN},
            )
            response.raise_for_status()
            record = response.json()

        record_user_id = record.get("telegramUserId")
        current_user_id = str(update.effective_user.id)
        if not record_user_id or str(record_user_id) != current_user_id:
            raise ValueError("Анкета належить іншому користувачу")

        answers = record.get("answers")
        if not isinstance(answers, dict) or answers.get("parental_consent") != "Надано":
            raise ValueError("Анкета не завершена")

        grade_number = str(answers.get("grade_number", ""))
        grade_letter = str(answers.get("grade_letter", ""))
        answers["grade"] = (
            f"{grade_number}-{grade_letter}"
            if grade_letter and grade_letter != "Немає букви"
            else grade_number
        )
        answers["nickname"] = (
            f"@{update.effective_user.username}"
            if update.effective_user.username
            else "—"
        )

        participant_key = make_participant_key(answers)
        passport_number = await get_or_create_license(participant_key, answers)
        answers["passport_number"] = passport_number
        answers["response_saved"] = True
        ctx.user_data.clear()
        ctx.user_data.update(answers)

        if answers.get("safety_answer") != "Ні, такого не було":
            alert_text = (
                "⚠️ *Обратить внимание*\n"
                "Получен ответ, требующий проверки.\n"
                f"Код лицензии: `{passport_number}`"
            )
            for chat_id in ALERT_CHAT_IDS:
                try:
                    await ctx.bot.send_message(chat_id, alert_text, parse_mode="Markdown")
                except Exception as alert_error:
                    logger.error(f"Не вдалося надіслати службове сповіщення: {alert_error}")

        await update.message.reply_text(
            "🎫 Анкету отримано. Ліцензію формуємо, зачекай кілька секунд…",
            reply_markup=ReplyKeyboardRemove(),
        )
        asyncio.create_task(
            _deliver_passport_and_log(update, ctx, dict(answers), passport_number)
        )
        return await _finish(update, ctx)
    except Exception as error:
        logger.exception(f"Помилка обробки Mini App анкети: {error}")
        await update.message.reply_text(
            "⚠️ Анкету збережено, але паспорт поки не вдалося сформувати. "
            "Адміністратор зможе повторити видачу без повторного проходження анкети."
        )
        return ConversationHandler.END

async def consent(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.message.text.startswith("❌"):
        await update.message.reply_text(
            "Зрозуміло. Опитування потребує згоди батьків.\nДо побачення! 👋",
            reply_markup=ReplyKeyboardRemove()
        )
        return ConversationHandler.END
    save(ctx, "parental_consent", "Надано")
    await update.message.reply_text(
        "Чудово! Починаємо 🚀\n\n*П1. Яка твоя стать?*",
        parse_mode="Markdown",
        reply_markup=kb(["Хлопець", "Дівчина", "Не хочу вказувати"])
    )
    return GENDER

# ── ДЕМОГРАФІЯ ─────────────────────────────────────────────────────
async def gender(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    save(ctx, "gender", update.message.text)
    await update.message.reply_text(
        "*П2. Напиши своє Ім'я та Прізвище повністю українською мовою.*",
        parse_mode="Markdown", reply_markup=ReplyKeyboardRemove()
    )
    return FULL_NAME

async def full_name(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    save(ctx, "contact_name", update.message.text)
    await update.message.reply_text(
        "*П3. Напиши дату свого народження у форматі ДД.ММ.РРРР*\n\n"
        "_Наприклад: 15.03.2015_",
        parse_mode="Markdown", reply_markup=ReplyKeyboardRemove()
    )
    return BIRTH_DATE

async def birth_date(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    save(ctx, "birth_date", update.message.text.strip())
    await update.message.reply_text(
        "*П4. Яка твоя область?*",
        parse_mode="Markdown",
        reply_markup=kb([
            "Вінницька","Волинська","Дніпропетровська","Донецька",
            "Житомирська","Закарпатська","Запорізька","Івано-Франківська",
            "Київська","Кіровоградська","Луганська","Львівська",
            "Миколаївська","Одеська","Полтавська","Рівненська",
            "Сумська","Тернопільська","Харківська","Херсонська",
            "Хмельницька","Черкаська","Чернівецька","Чернігівська",
            "м. Київ","Тимчасово за кордоном"
        ])
    )
    return REGION

async def region(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    save(ctx, "region", update.message.text)
    await update.message.reply_text(
        "*П5. Де ти живеш?*\n\n"
        "Напиши перші 3-4 літери назви свого міста, селища або села — "
        "бот покаже список схожих варіантів, і ти обереш потрібний.\n\n"
        "_Наприклад: «Бров» → покаже Бровари_",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove()
    )
    return CITY_TYPE

async def city_type(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.message.text.strip()
    region_name = ctx.user_data.get("region", "")

    matches = await search_settlements(query, region_name)

    if matches:
        options = matches + ["Не знайшов — напишу сам"]
        await update.message.reply_text(
            "*Ось що знайшлось. Обери свій населений пункт зі списку,*\n"
            "*або натисни «Не знайшов — напишу сам», якщо його немає в переліку:*",
            parse_mode="Markdown",
            reply_markup=kb(options, cols=2)
        )
        return CITY_SELECT
    else:
        await update.message.reply_text(
            "Нічого не знайшли за цим запитом у твоїй області.\n\n"
            "Спробуй ввести назву інакше, або просто напиши повну назву "
            "свого населеного пункту — і ми запишемо її як є:",
            reply_markup=ReplyKeyboardRemove()
        )
        return CITY_NAME

async def city_select(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    val = update.message.text
    if val == "Не знайшов — напишу сам":
        await update.message.reply_text(
            "Напиши повну назву населеного пункту:",
            reply_markup=ReplyKeyboardRemove()
        )
        return CITY_NAME
    save(ctx, "city_name", val)
    return await _after_city_selected(update, ctx)

async def city_name(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    save(ctx, "city_name", update.message.text)
    return await _after_city_selected(update, ctx)

async def _after_city_selected(update, ctx):
    city = ctx.user_data.get("city_name", "")
    city_clean = city.replace("м.", "").strip()

    if city_clean in MAJOR_CITY_DISTRICTS:
        await update.message.reply_text(
            f"*Обери район міста {city_clean}:*",
            parse_mode="Markdown",
            reply_markup=kb(MAJOR_CITY_DISTRICTS[city_clean], cols=2)
        )
        return DISTRICT
    else:
        # Немає офіційних районів — питання пропускається повністю
        save(ctx, "district", "")
        await update.message.reply_text(
            "*П7. Тип школи?*\n_(якщо не впевнений — обери «Не знаю точно»)_",
            parse_mode="Markdown",
            reply_markup=kb(["Звичайна школа","Ліцей / гімназія","Не знаю точно"])
        )
        return SCHOOL_TYPE

async def district(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    save(ctx, "district", update.message.text)
    await update.message.reply_text(
        "*П7. Тип школи?*\n_(якщо не впевнений — обери «Не знаю точно»)_",
        parse_mode="Markdown",
        reply_markup=kb(["Звичайна школа","Ліцей / гімназія","Не знаю точно"])
    )
    return SCHOOL_TYPE

async def school_type(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    save(ctx, "school_type", update.message.text)
    await update.message.reply_text(
        "*П8. Назва або номер школи?*",
        parse_mode="Markdown", reply_markup=ReplyKeyboardRemove()
    )
    return SCHOOL_NAME

async def school_name(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    save(ctx, "school_name", update.message.text)
    await update.message.reply_text(
        "*П9. В якому ти класі?*",
        parse_mode="Markdown",
        reply_markup=kb(["3","4","5","6","7","8","9","10","11"])
    )
    return GRADE

async def grade(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    save(ctx, "grade_number", update.message.text)
    await update.message.reply_text(
        "*П9б. Буква класу?*",
        parse_mode="Markdown",
        reply_markup=kb(["А","Б","В","Г","Немає букви"])
    )
    return GRADE_LETTER

async def grade_letter(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    letter = update.message.text
    num = ctx.user_data.get("grade_number", "")
    if letter and letter != "Немає букви":
        save(ctx, "grade", f"{num}-{letter}")
    else:
        save(ctx, "grade", num)
    await update.message.reply_text(
        "🏃 *БЛОК: СПОРТ*\n\n*П10. Чи займаєшся спортом?*",
        parse_mode="Markdown",
        reply_markup=kb(["Так, регулярно","Так, іноді","Ні"])
    )
    return SPORT_ACTIVE

# ── СПОРТ ──────────────────────────────────────────────────────────
async def sport_active(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    val = update.message.text; save(ctx, "sport_active", val)
    if val == "Ні":
        await update.message.reply_text("*П10б. Чому не займаєшся спортом?*", parse_mode="Markdown",
            reply_markup=kb(["Немає часу","Немає секції поруч","Не цікаво","Інша причина"]))
        return SPORT_WHY_NOT
    await update.message.reply_text("*П10а. Який вид спорту?*\n\nНапиши:", parse_mode="Markdown", reply_markup=ReplyKeyboardRemove())
    return SPORT_TYPE

async def sport_type(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    save(ctx, "sport_type", update.message.text)
    await update.message.reply_text("*П11. Де займаєшся спортом?*", parse_mode="Markdown",
        reply_markup=kb(["Шкільна секція","Спортивний клуб","На вулиці","Самостійно"]))
    return SPORT_LEVEL

async def sport_level(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    save(ctx, "sport_level", update.message.text)
    await update.message.reply_text("*П12. Чи є тренер або наставник?*", parse_mode="Markdown", reply_markup=kb(["Так","Ні"]))
    return SPORT_COACH

async def sport_coach(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    save(ctx, "sport_coach", update.message.text)
    await _ask_watch_sport(update)
    return WATCH_SPORT

async def sport_why_not(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    save(ctx, "sport_why_not", update.message.text)
    await update.message.reply_text("*П10в. Хотів би займатись спортом?*", parse_mode="Markdown",
        reply_markup=kb(["Так","Можливо","Ні"]))
    return SPORT_WOULD_LIKE

async def sport_would_like(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    save(ctx, "sport_would_like", update.message.text)
    await _ask_watch_sport(update)
    return WATCH_SPORT

async def _ask_watch_sport(update):
    await update.message.reply_text("*П13. Чи дивишся спортивні трансляції?*", parse_mode="Markdown",
        reply_markup=kb(["Так, часто","Іноді","Ні"]))

async def watch_sport(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    val = update.message.text; save(ctx, "watch_sport", val)
    if val == "Ні":
        await _ask_phys_ed(update); return PHYS_ED
    await update.message.reply_text("*П13а. Де дивишся трансляції?*", parse_mode="Markdown",
        reply_markup=kb(["YouTube","Twitch","Телебачення","Кілька платформ"]))
    return WATCH_WHERE

async def watch_where(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    save(ctx, "watch_where", update.message.text)
    await update.message.reply_text("*П13б. Який вид спорту найцікавіше дивитись?*\n\nНапиши:",
        parse_mode="Markdown", reply_markup=ReplyKeyboardRemove())
    return FAV_SPORT_WATCH

async def fav_sport_watch(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    save(ctx, "fav_sport_watch", update.message.text)
    await _ask_phys_ed(update); return PHYS_ED

async def _ask_phys_ed(update):
    await update.message.reply_text("*П14. Як ставишся до фізкультури в школі?*", parse_mode="Markdown",
        reply_markup=kb(["Подобається","Нейтрально","Не подобається"]))

async def phys_ed(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    save(ctx, "phys_ed", update.message.text)
    await update.message.reply_text("*П15. Як часто займаєшся фізичними вправами?*", parse_mode="Markdown",
        reply_markup=kb(["Щодня","Кілька разів на тиждень","Рідко","Майже ніколи"]))
    return PHYS_OUT

async def phys_out(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    save(ctx, "phys_out", update.message.text)
    await update.message.reply_text("💻 *БЛОК: ПК*\n\n*П16. Чи граєш на комп'ютері або ноутбуці (далі ПК)?*",
        parse_mode="Markdown", reply_markup=kb(["Так","Ні"]))
    return PC_PLAY

# ── ПК ─────────────────────────────────────────────────────────────
async def pc_play(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    val = update.message.text; save(ctx, "pc_play", val)
    if val == "Ні":
        await _ask_console(update); return CONSOLE_PLAY
    await update.message.reply_text("*П17. Скільки годин на день на ПК?*", parse_mode="Markdown",
        reply_markup=kb(["Менше 1 год","1–2 год","3–4 год","4+ год"]))
    return PC_HOURS

async def pc_hours(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    save(ctx, "pc_hours", update.message.text)
    await update.message.reply_text("*П18. Улюблений жанр на ПК?*", parse_mode="Markdown",
        reply_markup=kb(["Шутер (FPS)","Стратегія","РПГ","MOBA","Спортивна","Гонки","Казуальна"]))
    return PC_GENRE

async def pc_genre(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    save(ctx, "pc_genre", update.message.text)
    await update.message.reply_text("*П19. Улюблена гра на ПК?*\n\nНапиши назву:", parse_mode="Markdown", reply_markup=ReplyKeyboardRemove())
    return PC_GAME

async def pc_game(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    save(ctx, "pc_game", update.message.text)
    await update.message.reply_text("*П20. Брав участь у ПК-змаганнях?*", parse_mode="Markdown",
        reply_markup=kb(["Так, онлайн","Так, офлайн","Ні"]))
    return PC_COMPETE

async def pc_compete(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    save(ctx, "pc_compete", update.message.text)
    await update.message.reply_text("*П21. Як ти оцінюєш свій рівень користування ПК?*", parse_mode="Markdown",
        reply_markup=kb(["Початківець","Середній","Просунутий","Про / топ"]))
    return PC_LEVEL

async def pc_level(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    save(ctx, "pc_level", update.message.text)
    await update.message.reply_text("*П22. Хотів би ПК-секцію у шкільному клубі?*", parse_mode="Markdown",
        reply_markup=kb(["Так","Можливо","Ні"]))
    return PC_CLUB

async def pc_club(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    save(ctx, "pc_club", update.message.text)
    await _ask_console(update); return CONSOLE_PLAY

async def _ask_console(update):
    await update.message.reply_text("🎮 *БЛОК: КОНСОЛЬ*\n\n*П23. Чи граєш на консолі (PlayStation, Xbox, Nintendo)?*",
        parse_mode="Markdown", reply_markup=kb(["Так","Ні"]))

# ── КОНСОЛЬ ────────────────────────────────────────────────────────
async def console_play(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    val = update.message.text; save(ctx, "console_play", val)
    if val == "Ні":
        await _ask_mobile(update); return MOBILE_PLAY
    await update.message.reply_text("*П24. Яка консоль?*", parse_mode="Markdown",
        reply_markup=kb(["PlayStation 4","PlayStation 5","Xbox One","Xbox Series","Nintendo Switch","Інша"]))
    return CONSOLE_MODEL

async def console_model(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    save(ctx, "console_model", update.message.text)
    await update.message.reply_text("*П25. Скільки годин на день граєш на консолі?*", parse_mode="Markdown",
        reply_markup=kb(["Менше 1 год","1–2 год","3–4 год","4+ год"]))
    return CONSOLE_HOURS

async def console_hours(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    save(ctx, "console_hours", update.message.text)
    await update.message.reply_text("*П26. Жанр на консолі?*", parse_mode="Markdown",
        reply_markup=kb(["Шутер","Спортивні (FIFA, NBA)","Файтинг","РПГ","Гонки","Пригоди"]))
    return CONSOLE_GENRE

async def console_genre(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    save(ctx, "console_genre", update.message.text)
    await update.message.reply_text("*П27. Улюблена гра на консолі?*\n\nНапиши:", parse_mode="Markdown", reply_markup=ReplyKeyboardRemove())
    return CONSOLE_GAME

async def console_game(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    save(ctx, "console_game", update.message.text)
    await update.message.reply_text("*П28. Брав участь у консольних змаганнях?*", parse_mode="Markdown", reply_markup=kb(["Так","Ні"]))
    return CONSOLE_COMPETE

async def console_compete(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    save(ctx, "console_compete", update.message.text)
    await update.message.reply_text("*П29. Хотів би Консольну секцію у шкільному клубі?*", parse_mode="Markdown",
        reply_markup=kb(["Так","Можливо","Ні"]))
    return CONSOLE_CLUB

async def console_club(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    save(ctx, "console_club", update.message.text)
    await _ask_mobile(update); return MOBILE_PLAY

async def _ask_mobile(update):
    await update.message.reply_text("📱 *БЛОК: МОБІЛЬНИЙ*\n\n*П30. Чи граєш на мобільному телефоні?*",
        parse_mode="Markdown", reply_markup=kb(["Так","Ні"]))

# ── МОБІЛЬНИЙ ──────────────────────────────────────────────────────
async def mobile_play(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    val = update.message.text; save(ctx, "mobile_play", val)
    if val == "Ні": return await _go_esports(update, ctx)
    await update.message.reply_text("*П31. Скільки годин на день на телефоні?*", parse_mode="Markdown",
        reply_markup=kb(["Менше 1 год","1–2 год","3–4 год","4+ год"]))
    return MOBILE_HOURS

async def mobile_hours(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    save(ctx, "mobile_hours", update.message.text)
    await update.message.reply_text(
        "🎮 *Ігри на телефоні — відповідай Так або Ні на кожну:*\n\n*П32. Brawl Stars — граєш?*",
        parse_mode="Markdown", reply_markup=kb(["Так","Ні"]))
    return GAME_BRAWL

async def game_brawl(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    save(ctx, "game_brawl", update.message.text)
    await update.message.reply_text("*П33. Roblox — граєш?*", parse_mode="Markdown", reply_markup=kb(["Так","Ні"]))
    return GAME_ROBLOX

async def game_roblox(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    save(ctx, "game_roblox", update.message.text)
    await update.message.reply_text("*П34. Minecraft — граєш?*", parse_mode="Markdown", reply_markup=kb(["Так","Ні"]))
    return GAME_MINECRAFT

async def game_minecraft(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    save(ctx, "game_minecraft", update.message.text)
    await update.message.reply_text("*П35. Clash Royale — граєш?*", parse_mode="Markdown", reply_markup=kb(["Так","Ні"]))
    return GAME_CLASH

async def game_clash(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    save(ctx, "game_clash", update.message.text)
    if grade_int(ctx) >= 5:
        await update.message.reply_text("*П36. Honor of Kings — граєш?*", parse_mode="Markdown", reply_markup=kb(["Так","Ні"]))
        return GAME_HOK
    await _ask_mobile_other(update); return MOBILE_OTHER

async def game_hok(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    save(ctx, "game_hok", update.message.text)
    await update.message.reply_text("*П37. MLBB — граєш?*", parse_mode="Markdown", reply_markup=kb(["Так","Ні"]))
    return GAME_MLBB

async def game_mlbb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    save(ctx, "game_mlbb", update.message.text)
    if grade_int(ctx) >= 9:
        await update.message.reply_text("*П38. PUBG Mobile — граєш?*", parse_mode="Markdown", reply_markup=kb(["Так","Ні"]))
        return GAME_PUBG
    await _ask_mobile_other(update); return MOBILE_OTHER

async def game_pubg(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    save(ctx, "game_pubg", update.message.text)
    await _ask_mobile_other(update); return MOBILE_OTHER

async def _ask_mobile_other(update):
    await update.message.reply_text("*П40. Інша улюблена мобільна гра?*\n\nНапиши або надішли «-»",
        parse_mode="Markdown", reply_markup=ReplyKeyboardRemove())

async def mobile_other(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    save(ctx, "mobile_other", update.message.text)
    await update.message.reply_text("*П41. Твій улюблений жанр мобільних ігор?*", parse_mode="Markdown",
        reply_markup=kb(["Battle Royale","MOBA","Стратегія","Казуальна","Спортивна","Інший"]))
    return MOBILE_GENRE

async def mobile_genre(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    save(ctx, "mobile_genre", update.message.text)
    await update.message.reply_text("*П42. Брав участь у мобільних змаганнях?*", parse_mode="Markdown",
        reply_markup=kb(["Так, онлайн","Так, офлайн-турнір","Ні"]))
    return MOBILE_COMPETE

async def mobile_compete(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    save(ctx, "mobile_compete", update.message.text)
    await update.message.reply_text("*П43. Рівень гри на мобільному?*", parse_mode="Markdown",
        reply_markup=kb(["Початківець","Середній","Просунутий","Топ"]))
    return MOBILE_LEVEL

async def mobile_level(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    save(ctx, "mobile_level", update.message.text)
    await update.message.reply_text("*П44. Хотів би Мобільну секцію у шкільному клубі?*", parse_mode="Markdown",
        reply_markup=kb(["Так","Можливо","Ні"]))
    return MOBILE_CLUB

async def mobile_club(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    save(ctx, "mobile_club", update.message.text)
    return await _go_esports(update, ctx)

async def _go_esports(update, ctx):
    await update.message.reply_text(
        "🏆 *БЛОК: КІБЕРСПОРТ*\n\n"
        "*П45. Чи знаєш, що таке кіберспорт?*\n\n"
        "_(Кіберспорт — офіційні змагання з відеоігор за призи та рейтинг.)_",
        parse_mode="Markdown", reply_markup=kb(["Знаю добре","Чув, але не дуже","Вперше чую"]))
    return ESPORTS_KNOW

# ── КІБЕРСПОРТ ─────────────────────────────────────────────────────
async def esports_know(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    save(ctx, "esports_know", update.message.text)
    await update.message.reply_text("*П46. Дивишся кіберспортивні турніри?*", parse_mode="Markdown",
        reply_markup=kb(["Так, регулярно","Іноді","Ні","Хочу подивитись"]))
    return ESPORTS_WATCH

async def esports_watch(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    val = update.message.text; save(ctx, "esports_watch", val)
    if val in ("Ні","Хочу подивитись"):
        await _ask_esports_compete(update); return ESPORTS_COMPETE
    await update.message.reply_text("*П46б. Де дивишся турніри?*", parse_mode="Markdown",
        reply_markup=kb(["YouTube","Twitch","Телебачення","Кілька платформ"]))
    return ESPORTS_WATCH_WHERE

async def esports_watch_where(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    save(ctx, "esports_watch_where", update.message.text)
    await _ask_esports_compete(update); return ESPORTS_COMPETE

async def _ask_esports_compete(update):
    await update.message.reply_text("*П47. Хочеш грати кіберспорт змагально?*", parse_mode="Markdown",
        reply_markup=kb(["Так, дуже хочу","Можливо","Ні, не цікаво"]))

async def esports_compete(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    save(ctx, "esports_compete", update.message.text)
    await update.message.reply_text("*П48. Є друзі або команда, з якими граєш?*", parse_mode="Markdown",
        reply_markup=kb(["Так, є команда","Є друзі без команди","Граю сам / сама","Хочу знайти команду"]))
    return ESPORTS_TEAM

async def esports_team(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    save(ctx, "esports_team", update.message.text)
    await update.message.reply_text("💡 *БЛОК: МОТИВАЦІЯ*\n\n*П49. Що тебе мотивує грати?*", parse_mode="Markdown",
        reply_markup=kb(["Перемога та рейтинг","Спілкування з друзями","Розвиток навичок","Задоволення та відпочинок","Заробіток / призи"]))
    return MOTIVATION

# ── МОТИВАЦІЯ ──────────────────────────────────────────────────────
async def motivation(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    save(ctx, "motivation", update.message.text)
    await update.message.reply_text("*П50. Що приваблює у кіберспорті?*", parse_mode="Markdown",
        reply_markup=kb(["Команда та дружба","Слава та визнання","Грошові призи","Розвиток мислення","Мені не цікаво"]))
    return ESPORTS_ATTRACT

async def esports_attract(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    save(ctx, "esports_attract", update.message.text)
    await update.message.reply_text("*П51. Скільки часу готовий витрачати на клуб щотижня?*", parse_mode="Markdown",
        reply_markup=kb(["1–2 год / тиждень","3–5 год / тиждень","5–10 год / тиждень","Більше 10 год"]))
    return TIME_READY

async def time_ready(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    save(ctx, "time_ready", update.message.text)
    await update.message.reply_text(
        "🛡 *БЛОК: СЕРЕДОВИЩЕ ТА ПОВАГА*\n\n"
        "*П52. Чи стикався з образами або токсичністю в онлайн-іграх?*\n\n"
        "_Відповідь необов'язкова._",
        parse_mode="Markdown", reply_markup=kb(["Так, часто","Іноді","Ні","Пропустити"]))
    return TOXIC

# ── ПОВАГА ─────────────────────────────────────────────────────────
async def toxic(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    val = update.message.text; save(ctx, "toxic", val)
    if val == "Так, часто":
        await update.message.reply_text(
            "Дякую, що довірився.\n\n"
            "Якщо тобі зараз важко — можеш звернутись на Національну дитячу лінію психологічної підтримки:\n"
            "📞 *116 111* (безкоштовно з мобільного)\n"
            "📞 *0 800 500 225*\n\n_Анонімно · конфіденційно · цілодобово._",
            parse_mode="Markdown")
    await update.message.reply_text("*П53. Наскільки важливо правило поваги у клубі?*", parse_mode="Markdown",
        reply_markup=kb(["Дуже важливо","Важливо","Байдуже"]))
    return RESPECT_RULE

async def respect_rule(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    save(ctx, "respect_rule", update.message.text)
    await update.message.reply_text("*П54. Що допомогло б почуватись безпечно у клубі?*", parse_mode="Markdown",
        reply_markup=kb(["Тренер, який стежить","Чіткі правила","Модератор у чаті","Дружня атмосфера","Система скарг"]))
    return SAFE_FEEL

async def safe_feel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    save(ctx, "safe_feel", update.message.text)
    await update.message.reply_text("🏫 *БЛОК: КЛУБ У ШКОЛІ*\n\n*П55. Вступив би до кіберспортивного клубу у своїй школі?*",
        parse_mode="Markdown", reply_markup=kb(["Так, одразу!","Можливо","Ні"]))
    return CLUB_JOIN

# ── КЛУБ ───────────────────────────────────────────────────────────
async def club_join(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    save(ctx, "club_join", update.message.text)
    await update.message.reply_text("*П56. Яка роль у клубі тобі цікава?*", parse_mode="Markdown",
        reply_markup=kb(["Гравець","Стример / коментатор","Організатор турнірів","Контент-мейкер","Суддя / рефері","Спостерігач","На даний момент не знаю"]))
    return CLUB_ROLE

async def club_role(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    save(ctx, "club_role", update.message.text)
    await update.message.reply_text("*П57. Що найважливіше для тебе у клубі?*", parse_mode="Markdown",
        reply_markup=kb(["Регулярні тренування","Участь у змаганнях","Дружня атмосфера","Навчання та розвиток","Призи та нагороди"]))
    return CLUB_IMPORTANT

async def club_important(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    save(ctx, "club_important", update.message.text)
    await update.message.reply_text("*П58. Чи підтримують батьки твоє захоплення іграми?*", parse_mode="Markdown",
        reply_markup=kb(["Так, повністю","Частково","Ні","Вони не знають"]))
    return PARENTS_SUPPORT

async def parents_support(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    save(ctx, "parents_support", update.message.text)
    await update.message.reply_text("*П59. Батьки відпустять тебе на тренування у клубі після уроків?*", parse_mode="Markdown",
        reply_markup=kb(["Так","Можливо","Ні"]))
    return PARENTS_ALLOW

async def parents_allow(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    save(ctx, "parents_allow", update.message.text)
    await update.message.reply_text("🚀 *БЛОК: МАЙБУТНЄ*\n\n*П60. Хочеш пов'язати майбутнє з кіберспортом?*",
        parse_mode="Markdown", reply_markup=kb(["Так, мрію про це","Можливо","Ні"]))
    return FUTURE

# ── МАЙБУТНЄ ───────────────────────────────────────────────────────
async def future(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    save(ctx, "future", update.message.text)
    await update.message.reply_text("*П61. Яка роль цікава як майбутня професія?*", parse_mode="Markdown",
        reply_markup=kb(["Профі-гравець","Тренер команди","Менеджер / продюсер","Суддя / аналітик","Коментатор","Розробник ігор","Не планую","На даний момент не знаю"]))
    return FUTURE_ROLE

async def future_role(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    save(ctx, "future_role", update.message.text)
    d = ctx.user_data

    tg_user = update.effective_user
    if not d.get("contact_name"):
        d["contact_name"] = f"{tg_user.first_name or ''} {tg_user.last_name or ''}".strip() or "Гравець"
    d["nickname"] = f"@{tg_user.username}" if tg_user.username else "—"

    # Номер видається атомарно через PostgreSQL — швидко, без блокування
    # інших дітей, що завершують опитування одночасно.
    try:
        participant_key = make_participant_key(d)
        passport_number = await get_or_create_license(participant_key, d)
        save(ctx, "passport_number", passport_number)
        save(ctx, "response_saved", True)
    except Exception as e:
        logger.error(f"Не вдалося видати номер ліцензії: {e}")
        await update.message.reply_text(
            "⚠️ Виникла технічна помилка при видачі паспорта. "
            "Спробуй, будь ласка, ще раз трохи пізніше через команду /start."
        )
        return await _finish(update, ctx)

    await update.message.reply_text("🎫 Ліцензію формуємо, зачекай кілька секунд...")

    # Малювання картинки і запис у Google Таблицю — важкі операції, тому
    # виконуються у фоні й НЕ блокують відповідь іншим дітям.
    asyncio.create_task(_deliver_passport_and_log(update, ctx, dict(d), passport_number))

    return await _finish(update, ctx)

async def _deliver_passport_and_log(update: Update, ctx: ContextTypes.DEFAULT_TYPE,
                                     passport_data: dict, passport_number: str):
    """Фонова задача: генерує картинку паспорта і пише повний запис у Google Таблицю."""
    loop = asyncio.get_running_loop()
    try:
        bot_profile = await ctx.bot.get_me()
        verification_url = make_verification_url(bot_profile.username, passport_number)
        # PIL-малювання — важка для процесора операція, виконуємо в окремому потоці
        photo_buf = await loop.run_in_executor(
            None, generate_passport, passport_data, passport_number, verification_url
        )
        await update.message.reply_photo(
            photo=photo_buf,
            caption=f"🎫 *Твій паспорт гравця* {passport_number}\n\nЗбережи собі на телефон!",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Не вдалося згенерувати паспорт: {e}")

    try:
        await loop.run_in_executor(None, save_to_sheet, passport_data)
    except Exception as e:
        logger.error(f"Помилка запису у Google Sheets: {e}")

# ── ФІНАЛ ──────────────────────────────────────────────────────────
async def _finish(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    d = ctx.user_data
    club = d.get("club_join", "")

    if club == "Так, одразу!":
        club_msg = "🏆 Ти — саме та людина, заради якої ми відкриваємо клуб! Чекаємо тебе на першому тренуванні!"
    elif club == "Можливо":
        club_msg = "😊 Сподіваємось, що ти заглянеш до клубу і знайдеш щось цікаве для себе!"
    else:
        club_msg = "Якщо колись зміниш думку — двері клубу завжди відкриті."

    await update.message.reply_text(
        "✅ *Дякуємо, що ти з нами!*\n\n"
        f"{club_msg}\n\n"
        "💙 *Якщо виникли питання — телефонуй:*\n"
        "📞 116 111 — безкоштовно з мобільного\n"
        "📞 0 800 500 225 — безкоштовно\n\n"
        "_Анонімно · конфіденційно · цілодобово_",
        parse_mode="Markdown", reply_markup=ReplyKeyboardRemove()
    )

    logger.info(f"DONE uid={update.effective_user.id} data={d}")
    if not d.get("response_saved"):
        save_to_sheet(d)
    return ConversationHandler.END

async def cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Опитування скасовано. Напиши /start щоб почати знову.",
        reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

# ── ЗАПУСК ─────────────────────────────────────────────────────────
def main():
    app = (
        Application.builder()
        .token(TOKEN)
        .concurrent_updates(True)
        .post_init(init_db)
        .post_shutdown(close_db)
        .build()
    )
    app.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, web_app_submission), group=-1)
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("myid", myid))
    conv = ConversationHandler(
        entry_points=[CommandHandler("legacy", legacy_start)],
        states={
            CONSENT:[MessageHandler(filters.TEXT&~filters.COMMAND,consent)],
            GENDER:[MessageHandler(filters.TEXT&~filters.COMMAND,gender)],
            REGION:[MessageHandler(filters.TEXT&~filters.COMMAND,region)],
            FULL_NAME:[MessageHandler(filters.TEXT&~filters.COMMAND,full_name)],
            BIRTH_DATE:[MessageHandler(filters.TEXT&~filters.COMMAND,birth_date)],
            GRADE:[MessageHandler(filters.TEXT&~filters.COMMAND,grade)],
            GRADE_LETTER:[MessageHandler(filters.TEXT&~filters.COMMAND,grade_letter)],
            CITY_TYPE:[MessageHandler(filters.TEXT&~filters.COMMAND,city_type)],
            CITY_SELECT:[MessageHandler(filters.TEXT&~filters.COMMAND,city_select)],
            CITY_NAME:[MessageHandler(filters.TEXT&~filters.COMMAND,city_name)],
            DISTRICT:[MessageHandler(filters.TEXT&~filters.COMMAND,district)],
            SCHOOL_TYPE:[MessageHandler(filters.TEXT&~filters.COMMAND,school_type)],
            SCHOOL_NAME:[MessageHandler(filters.TEXT&~filters.COMMAND,school_name)],
            SPORT_ACTIVE:[MessageHandler(filters.TEXT&~filters.COMMAND,sport_active)],
            SPORT_TYPE:[MessageHandler(filters.TEXT&~filters.COMMAND,sport_type)],
            SPORT_LEVEL:[MessageHandler(filters.TEXT&~filters.COMMAND,sport_level)],
            SPORT_COACH:[MessageHandler(filters.TEXT&~filters.COMMAND,sport_coach)],
            SPORT_WHY_NOT:[MessageHandler(filters.TEXT&~filters.COMMAND,sport_why_not)],
            SPORT_WOULD_LIKE:[MessageHandler(filters.TEXT&~filters.COMMAND,sport_would_like)],
            WATCH_SPORT:[MessageHandler(filters.TEXT&~filters.COMMAND,watch_sport)],
            WATCH_WHERE:[MessageHandler(filters.TEXT&~filters.COMMAND,watch_where)],
            FAV_SPORT_WATCH:[MessageHandler(filters.TEXT&~filters.COMMAND,fav_sport_watch)],
            PHYS_ED:[MessageHandler(filters.TEXT&~filters.COMMAND,phys_ed)],
            PHYS_OUT:[MessageHandler(filters.TEXT&~filters.COMMAND,phys_out)],
            PC_PLAY:[MessageHandler(filters.TEXT&~filters.COMMAND,pc_play)],
            PC_HOURS:[MessageHandler(filters.TEXT&~filters.COMMAND,pc_hours)],
            PC_GENRE:[MessageHandler(filters.TEXT&~filters.COMMAND,pc_genre)],
            PC_GAME:[MessageHandler(filters.TEXT&~filters.COMMAND,pc_game)],
            PC_COMPETE:[MessageHandler(filters.TEXT&~filters.COMMAND,pc_compete)],
            PC_LEVEL:[MessageHandler(filters.TEXT&~filters.COMMAND,pc_level)],
            PC_CLUB:[MessageHandler(filters.TEXT&~filters.COMMAND,pc_club)],
            CONSOLE_PLAY:[MessageHandler(filters.TEXT&~filters.COMMAND,console_play)],
            CONSOLE_MODEL:[MessageHandler(filters.TEXT&~filters.COMMAND,console_model)],
            CONSOLE_HOURS:[MessageHandler(filters.TEXT&~filters.COMMAND,console_hours)],
            CONSOLE_GENRE:[MessageHandler(filters.TEXT&~filters.COMMAND,console_genre)],
            CONSOLE_GAME:[MessageHandler(filters.TEXT&~filters.COMMAND,console_game)],
            CONSOLE_COMPETE:[MessageHandler(filters.TEXT&~filters.COMMAND,console_compete)],
            CONSOLE_CLUB:[MessageHandler(filters.TEXT&~filters.COMMAND,console_club)],
            MOBILE_PLAY:[MessageHandler(filters.TEXT&~filters.COMMAND,mobile_play)],
            MOBILE_HOURS:[MessageHandler(filters.TEXT&~filters.COMMAND,mobile_hours)],
            GAME_BRAWL:[MessageHandler(filters.TEXT&~filters.COMMAND,game_brawl)],
            GAME_ROBLOX:[MessageHandler(filters.TEXT&~filters.COMMAND,game_roblox)],
            GAME_MINECRAFT:[MessageHandler(filters.TEXT&~filters.COMMAND,game_minecraft)],
            GAME_CLASH:[MessageHandler(filters.TEXT&~filters.COMMAND,game_clash)],
            GAME_HOK:[MessageHandler(filters.TEXT&~filters.COMMAND,game_hok)],
            GAME_MLBB:[MessageHandler(filters.TEXT&~filters.COMMAND,game_mlbb)],
            GAME_PUBG:[MessageHandler(filters.TEXT&~filters.COMMAND,game_pubg)],
            MOBILE_OTHER:[MessageHandler(filters.TEXT&~filters.COMMAND,mobile_other)],
            MOBILE_GENRE:[MessageHandler(filters.TEXT&~filters.COMMAND,mobile_genre)],
            MOBILE_COMPETE:[MessageHandler(filters.TEXT&~filters.COMMAND,mobile_compete)],
            MOBILE_LEVEL:[MessageHandler(filters.TEXT&~filters.COMMAND,mobile_level)],
            MOBILE_CLUB:[MessageHandler(filters.TEXT&~filters.COMMAND,mobile_club)],
            ESPORTS_KNOW:[MessageHandler(filters.TEXT&~filters.COMMAND,esports_know)],
            ESPORTS_WATCH:[MessageHandler(filters.TEXT&~filters.COMMAND,esports_watch)],
            ESPORTS_WATCH_WHERE:[MessageHandler(filters.TEXT&~filters.COMMAND,esports_watch_where)],
            ESPORTS_COMPETE:[MessageHandler(filters.TEXT&~filters.COMMAND,esports_compete)],
            ESPORTS_TEAM:[MessageHandler(filters.TEXT&~filters.COMMAND,esports_team)],
            MOTIVATION:[MessageHandler(filters.TEXT&~filters.COMMAND,motivation)],
            ESPORTS_ATTRACT:[MessageHandler(filters.TEXT&~filters.COMMAND,esports_attract)],
            TIME_READY:[MessageHandler(filters.TEXT&~filters.COMMAND,time_ready)],
            TOXIC:[MessageHandler(filters.TEXT&~filters.COMMAND,toxic)],
            RESPECT_RULE:[MessageHandler(filters.TEXT&~filters.COMMAND,respect_rule)],
            SAFE_FEEL:[MessageHandler(filters.TEXT&~filters.COMMAND,safe_feel)],
            CLUB_JOIN:[MessageHandler(filters.TEXT&~filters.COMMAND,club_join)],
            CLUB_ROLE:[MessageHandler(filters.TEXT&~filters.COMMAND,club_role)],
            CLUB_IMPORTANT:[MessageHandler(filters.TEXT&~filters.COMMAND,club_important)],
            PARENTS_SUPPORT:[MessageHandler(filters.TEXT&~filters.COMMAND,parents_support)],
            PARENTS_ALLOW:[MessageHandler(filters.TEXT&~filters.COMMAND,parents_allow)],
            FUTURE:[MessageHandler(filters.TEXT&~filters.COMMAND,future)],
            FUTURE_ROLE:[MessageHandler(filters.TEXT&~filters.COMMAND,future_role)],
        },
        fallbacks=[CommandHandler("cancel",cancel)],
        allow_reentry=True
    )
    # Legacy text survey is intentionally not registered. The Telegram Mini App
    # opened from /start is the only supported registration path.
    print("✅ Бот запущено! Натисни Ctrl+C для зупинки.")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
