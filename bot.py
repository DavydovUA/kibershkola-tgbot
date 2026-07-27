import logging
import os
import datetime
import httpx
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, KeyboardButton
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

NAVY = (16, 34, 74)
BLUE_ACCENT = (30, 80, 200)
GOLD = (240, 180, 60)
LIGHT_BG = (238, 241, 245)
GRAY_TEXT = (110, 120, 140)

def font(size, bold=False):
    path = f"{FONT_DIR}/DejaVuSans-Bold.ttf" if bold else f"{FONT_DIR}/DejaVuSans.ttf"
    return ImageFont.truetype(path, size)

def get_initials(name):
    parts = (name or "").strip().split()
    if len(parts) >= 2:
        return (parts[0][0] + parts[1][0]).upper()
    return (name[:2] if name else "??").upper()

def make_qr(data, size=170):
    qr = qrcode.QRCode(border=1, box_size=6)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color=NAVY, back_color="white").convert("RGB")
    return img.resize((size, size))

def draw_ukraine_flag(draw, x, y, w, h):
    draw.rectangle([x, y, x+w, y+h//2], fill=(0, 87, 183))
    draw.rectangle([x, y+h//2, x+w, y+h], fill=(255, 215, 0))

def generate_passport(answers: dict, passport_number: str) -> io.BytesIO:
    W, H = 1011, 638
    img = Image.new("RGB", (W, H), "#ffffff")
    draw = ImageDraw.Draw(img)

    # Фон з легким відтінком
    draw.rounded_rectangle([0, 0, W, H], radius=28, fill=LIGHT_BG)
    draw.rounded_rectangle([6, 6, W-6, H-6], radius=24, outline=BLUE_ACCENT, width=5)

    pad = 46

    # Прапор України
    draw_ukraine_flag(draw, pad, 40, 76, 50)

    # Заголовок
    title_font = font(40, bold=True)
    draw.text((pad+96, 30), "ПАСПОРТ СПОРТСМЕНА", font=title_font, fill=NAVY)
    sub_font = font(17, bold=True)
    draw.text((pad+98, 78), "ШКІЛЬНА СПОРТИВНА ЛІГА", font=sub_font, fill=BLUE_ACCENT)

    # ── Фото (ліворуч) — ініціали замість реального фото ──
    photo_x, photo_y = pad, 140
    photo_w, photo_h = 210, 260
    role = answers.get("club_role") or "Гравець"
    draw.rounded_rectangle([photo_x, photo_y, photo_x+photo_w, photo_y+photo_h],
                            radius=10, fill=(220, 226, 235), outline=BLUE_ACCENT, width=2)
    initials = get_initials(answers.get("contact_name", ""))
    init_font = font(64, bold=True)
    ib = draw.textbbox((0,0), initials, font=init_font)
    iw, ih = ib[2]-ib[0], ib[3]-ib[1]
    draw.text((photo_x+photo_w/2-iw/2, photo_y+photo_h/2-ih/2-30), initials,
               font=init_font, fill=BLUE_ACCENT)
    cap_font = font(13)
    cap_text = "ФОТО"
    cb = draw.textbbox((0,0), cap_text, font=cap_font)
    draw.text((photo_x+photo_w/2-(cb[2]-cb[0])/2, photo_y+photo_h-28),
               cap_text, font=cap_font, fill=GRAY_TEXT)

    # ── Бейдж типу ліцензії (під фото) ──
    badge_y = photo_y + photo_h + 16
    badge_h = 78
    draw.rounded_rectangle([photo_x, badge_y, photo_x+photo_w, badge_y+badge_h],
                            radius=10, fill=(225, 232, 250), outline=GOLD, width=2)
    lic_label_font = font(12, bold=True)
    draw.text((photo_x+14, badge_y+10), "ТИП ЛІЦЕНЗІЇ", font=lic_label_font, fill=BLUE_ACCENT)
    role_font = font(24, bold=True)
    draw.text((photo_x+14, badge_y+30), role.upper(), font=role_font, fill=NAVY)

    # ── Видано / Дійсна до ──
    dates_y = badge_y + badge_h + 12
    dates_h = 62
    draw.rounded_rectangle([photo_x, dates_y, photo_x+photo_w, dates_y+dates_h],
                            radius=10, outline=(180, 190, 205), width=1)
    small_font = font(11, bold=True)
    val_font = font(13)
    today = datetime.date.today()
    valid_until = today.replace(year=today.year + 1)
    draw.text((photo_x+12, dates_y+8), "ВИДАНО", font=small_font, fill=GRAY_TEXT)
    draw.text((photo_x+12, dates_y+24), today.strftime("%d.%m.%Y"), font=val_font, fill=NAVY)
    draw.line([photo_x+photo_w/2, dates_y+6, photo_x+photo_w/2, dates_y+dates_h-6],
               fill=(200,200,200), width=1)
    draw.text((photo_x+photo_w/2+12, dates_y+8), "ДІЙСНА ДО", font=small_font, fill=GRAY_TEXT)
    draw.text((photo_x+photo_w/2+12, dates_y+24), valid_until.strftime("%d.%m.%Y"), font=val_font, fill=NAVY)
    lic_foot_font = font(10)
    foot_text = "СПОРТИВНА ІГРОВА ЛІЦЕНЗІЯ"
    fb = draw.textbbox((0,0), foot_text, font=lic_foot_font)
    draw.text((photo_x+photo_w/2-(fb[2]-fb[0])/2, dates_y+dates_h+6), foot_text,
               font=lic_foot_font, fill=GRAY_TEXT)

    # ── Права колонка: дані ──
    info_x = photo_x + photo_w + 44
    info_y = 150
    label_font = font(13, bold=True)
    value_font = font(24, bold=True)

    def info_row(y, label_ua, label_en, value):
        label_text = f"{label_ua} / {label_en}" if label_en else label_ua
        draw.text((info_x, y), label_text, font=label_font, fill=BLUE_ACCENT)
        draw.text((info_x, y+22), str(value) if value else "—", font=value_font, fill=NAVY)
        line_y = y + 58
        draw.line([info_x, line_y, info_x + 380, line_y], fill=(170,180,200), width=1)
        return line_y + 22

    y = info_row(info_y, "ІМ'Я ТА ПРІЗВИЩЕ", "NAME AND SURNAME", answers.get("contact_name", ""))
    nickname = answers.get("nickname") or "—"
    y = info_row(y, "НІК", None, nickname)
    y = info_row(y, "ШКОЛА", None, answers.get("school_name", ""))
    y = info_row(y, "КЛАС", None, answers.get("grade", ""))

    # ── Логотип школи (заглушка) — праворуч вгорі ──
    logo_x, logo_y = W - pad - 150, 60
    logo_size = 150
    draw.rounded_rectangle([logo_x, logo_y, logo_x+logo_size, logo_y+logo_size],
                            radius=10, outline=BLUE_ACCENT, width=2, fill=(230,235,245))
    logo_font = font(11)
    logo_text = "ЛОГОТИП ШКОЛИ"
    lb = draw.textbbox((0,0), logo_text, font=logo_font)
    draw.text((logo_x+logo_size/2-(lb[2]-lb[0])/2, logo_y+logo_size/2-8),
               logo_text, font=logo_font, fill=GRAY_TEXT)

    # № документа
    docnum_font = font(14, bold=True)
    docnum_text = f"№ ДОКУМЕНТА"
    dn = draw.textbbox((0,0), docnum_text, font=docnum_font)
    draw.text((logo_x+logo_size/2-(dn[2]-dn[0])/2, logo_y+logo_size+14),
               docnum_text, font=docnum_font, fill=BLUE_ACCENT)
    num_val_font = font(16, bold=True)
    nv = draw.textbbox((0,0), passport_number, font=num_val_font)
    draw.text((logo_x+logo_size/2-(nv[2]-nv[0])/2, logo_y+logo_size+34),
               passport_number, font=num_val_font, fill=NAVY)

    # ── QR-код — праворуч знизу ──
    qr_size = 170
    qr_x = W - pad - qr_size
    qr_y = logo_y + logo_size + 70
    qr_data = f"KIBERSHKOLA-{passport_number}"
    qr_img = make_qr(qr_data, size=qr_size-14)
    draw.rounded_rectangle([qr_x, qr_y, qr_x+qr_size, qr_y+qr_size],
                            radius=10, outline=NAVY, width=3)
    img.paste(qr_img, (qr_x+7, qr_y+7))

    # ── Голографічний декоративний круг (спрощено) ──
    circle_cx = info_x + 200
    circle_cy = qr_y + qr_size//2
    for i, r in enumerate(range(70, 40, -6)):
        shade = GOLD if i % 2 == 0 else BLUE_ACCENT
        draw.ellipse([circle_cx-r, circle_cy-r, circle_cx+r, circle_cy+r],
                      outline=shade, width=2)

    # ── Підпис (стилізований) ──
    sig_font = font(13)
    draw.line([info_x, H-70, info_x+250, H-70], fill=(120,120,120), width=1)
    # проста стилізована лінія підпису
    import math
    sig_points = []
    sx, sy = info_x+20, H-95
    for i in range(40):
        t = i / 40
        sig_points.append((sx + t*200, sy + 18*math.sin(t*10) - t*8))
    draw.line(sig_points, fill=NAVY, width=2, joint="curve")

    # ── Підвал ──
    footer_font = font(13, bold=True)
    footer_text = "СТРОК ДІЇ — ОДИН РІК"
    fo = draw.textbbox((0,0), footer_text, font=footer_font)
    draw.line([pad, H-36, W/2-(fo[2]-fo[0])/2-20, H-36], fill=GOLD, width=2)
    draw.line([W/2+(fo[2]-fo[0])/2+20, H-36, W-pad, H-36], fill=GOLD, width=2)
    draw.text((W/2-(fo[2]-fo[0])/2, H-44), footer_text, font=footer_font, fill=NAVY)
    draw.ellipse([pad-4, H-40, pad+4, H-32], fill=BLUE_ACCENT)
    draw.ellipse([W-pad-4, H-40, W-pad+4, H-32], fill=BLUE_ACCENT)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf

SHEET_ID = "1f61HYd4MQQnBj6z-mWrZ-2arn0r6r9WWbYJ4vphPY1s"

_gsheet = None

def get_sheet():
    """Повертає з'єднання з Google Таблицею (кешується)."""
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
            _gsheet = client.open_by_key(SHEET_ID).sheet1
        except Exception as e:
            logging.error(f"Не вдалося підключитись до Google Sheets: {e}")
            _gsheet = False
    return _gsheet

def save_to_sheet(answers: dict):
    """Записує один рядок відповідей у Google Таблицю."""
    sheet = get_sheet()
    if not sheet:
        return
    try:
        row = [
            datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
            answers.get("gender", ""),
            answers.get("grade", ""),
            answers.get("region", ""),
            answers.get("city_type", ""),
            answers.get("city_name", ""),
            answers.get("district", ""),
            answers.get("school_type", ""),
            answers.get("school_name", ""),
            answers.get("sport_active", ""),
            answers.get("sport_type", answers.get("sport_why_not", "")),
            answers.get("esports_know", ""),
            answers.get("clubJoin", answers.get("club_join", "")),
            answers.get("clubRole", answers.get("club_role", "")),
            answers.get("ticket", ""),
            answers.get("contact_name", ""),
            answers.get("parent_name", ""),
            answers.get("contact_phone", ""),
        ]
        sheet.append_row(row)
        logging.info("Рядок записано у Google Таблицю")
    except Exception as e:
        logging.error(f"Помилка запису у Google Sheets: {e}")

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("BOT_TOKEN")

(
    CONSENT, GENDER, REGION, FULL_NAME, GRADE, GRADE_LETTER,
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
    TICKET, PARENT_NAME, CONTACT_PHONE, CONTACT_TIME,
) = range(73)

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

async def consent(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.message.text.startswith("❌"):
        await update.message.reply_text(
            "Зрозуміло. Опитування потребує згоди батьків.\nДо побачення! 👋",
            reply_markup=ReplyKeyboardRemove()
        )
        return ConversationHandler.END
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
        "*П3. Яка твоя область?*",
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
        "*П4. В якому ти класі?*",
        parse_mode="Markdown",
        reply_markup=kb(["3","4","5","6","7","8","9","10","11"])
    )
    return GRADE

async def grade(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    save(ctx, "grade_number", update.message.text)
    await update.message.reply_text(
        "*П4б. Буква класу?*",
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
        "*П7. Назва або номер школи?*",
        parse_mode="Markdown", reply_markup=ReplyKeyboardRemove()
    )
    return SCHOOL_NAME

async def school_name(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    save(ctx, "school_name", update.message.text)
    await update.message.reply_text(
        "🏃 *БЛОК: СПОРТ*\n\n*П8. Чи займаєшся спортом?*",
        parse_mode="Markdown",
        reply_markup=kb(["Так, регулярно","Так, іноді","Ні"])
    )
    return SPORT_ACTIVE

# ── СПОРТ ──────────────────────────────────────────────────────────
async def sport_active(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    val = update.message.text; save(ctx, "sport_active", val)
    if val == "Ні":
        await update.message.reply_text("*П9б. Чому не займаєшся спортом?*", parse_mode="Markdown",
            reply_markup=kb(["Немає часу","Немає секції поруч","Не цікаво","Інша причина"]))
        return SPORT_WHY_NOT
    await update.message.reply_text("*П9. Який вид спорту?*\n\nНапиши:", parse_mode="Markdown", reply_markup=ReplyKeyboardRemove())
    return SPORT_TYPE

async def sport_type(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    save(ctx, "sport_type", update.message.text)
    await update.message.reply_text("*П10. Де займаєшся спортом?*", parse_mode="Markdown",
        reply_markup=kb(["Шкільна секція","Спортивний клуб","Міські змагання","Обласні змагання"]))
    return SPORT_LEVEL

async def sport_level(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    save(ctx, "sport_level", update.message.text)
    await update.message.reply_text("*П11. Чи є тренер або наставник?*", parse_mode="Markdown", reply_markup=kb(["Так","Ні"]))
    return SPORT_COACH

async def sport_coach(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    save(ctx, "sport_coach", update.message.text)
    await _ask_watch_sport(update)
    return WATCH_SPORT

async def sport_why_not(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    save(ctx, "sport_why_not", update.message.text)
    await update.message.reply_text("*П9в. Хотів би займатись спортом?*", parse_mode="Markdown",
        reply_markup=kb(["Так","Можливо","Ні"]))
    return SPORT_WOULD_LIKE

async def sport_would_like(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    save(ctx, "sport_would_like", update.message.text)
    await _ask_watch_sport(update)
    return WATCH_SPORT

async def _ask_watch_sport(update):
    await update.message.reply_text("*П12. Чи дивишся спортивні трансляції?*", parse_mode="Markdown",
        reply_markup=kb(["Так, часто","Іноді","Ні"]))

async def watch_sport(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    val = update.message.text; save(ctx, "watch_sport", val)
    if val == "Ні":
        await _ask_phys_ed(update); return PHYS_ED
    await update.message.reply_text("*П13. Де дивишся трансляції?*", parse_mode="Markdown",
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
        reply_markup=kb(["Гравець","Стример / коментатор","Організатор турнірів","Контент-мейкер","Суддя / рефері","Спостерігач"]))
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
        reply_markup=kb(["Профі-гравець","Тренер команди","Менеджер / продюсер","Суддя / аналітик","Коментатор","Розробник ігор","Не планую"]))
    return FUTURE_ROLE

async def future_role(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    save(ctx, "future_role", update.message.text)
    await update.message.reply_text(SUPPORT_TEXT, parse_mode="Markdown", reply_markup=ReplyKeyboardRemove())
    await update.message.reply_text(
        "*П62. Хочеш отримати квиток до кіберспортивного клубу або на найближчу подію?*",
        parse_mode="Markdown", reply_markup=kb(["🎟 Так, хочу квиток!","Ні, дякую"]))
    return TICKET

# ── ФІНАЛ ──────────────────────────────────────────────────────────
async def ticket(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    val = update.message.text; save(ctx, "ticket", val)
    if val.startswith("Ні"): return await _finish(update, ctx)
    await update.message.reply_text("*Як звати одного з батьків?* (для зв'язку)\n\nНапиши ім'я та прізвище:",
        parse_mode="Markdown", reply_markup=ReplyKeyboardRemove())
    return PARENT_NAME

async def parent_name(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    save(ctx, "parent_name", update.message.text)
    await update.message.reply_text("*Телефон батьків для зв'язку:*\n\nНаприклад: +380991234567", parse_mode="Markdown")
    return CONTACT_PHONE

async def contact_phone(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    save(ctx, "contact_phone", update.message.text)
    await update.message.reply_text("*Зручний час для зв'язку?*", parse_mode="Markdown",
        reply_markup=kb(["Вранці (до 12:00)","Вдень (12–17)","Ввечері (17–20)"]))
    return CONTACT_TIME

async def contact_time(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    save(ctx, "contact_time", update.message.text)
    return await _finish(update, ctx)

async def _finish(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    d = ctx.user_data
    club = d.get("club_join","")
    has_ticket = d.get("ticket","").startswith("🎟")

    if has_ticket:
        msg = "🎟️ *Квиток оформлюється!*\n\nОчікуй дзвінка від організаторів. До зустрічі в клубі!"
    elif club == "Так, одразу!":
        msg = "🏆 *Ти — саме та людина, заради якої ми відкриваємо клуб!*\n\nЧекаємо тебе на першому тренуванні!"
    elif club == "Можливо":
        msg = "😊 *Сподіваємось, що ти заглянеш до клубу* і знайдеш щось цікаве для себе!"
    else:
        msg = "👍 *Дякуємо за участь!*\n\nЯкщо колись зміниш думку — двері клубу завжди відкриті."

    await update.message.reply_text(
        f"✅ *Опитування завершено!*\n\n{msg}\n\n"
        "💙 Пам'ятай: якщо потрібна допомога — *116 111* (безкоштовно, анонімно)",
        parse_mode="Markdown", reply_markup=ReplyKeyboardRemove()
    )

    # Генеруємо і надсилаємо паспорт гравця
    try:
        passport_data = dict(d)
        tg_user = update.effective_user
        if not passport_data.get("contact_name"):
            passport_data["contact_name"] = f"{tg_user.first_name or ''} {tg_user.last_name or ''}".strip() or "Гравець"
        passport_data["nickname"] = f"@{tg_user.username}" if tg_user.username else "—"
        passport_number = f"KS-2026-{update.effective_user.id % 10000:04d}"
        photo_buf = generate_passport(passport_data, passport_number)
        await update.message.reply_photo(
            photo=photo_buf,
            caption=f"🎫 *Твій паспорт гравця* {passport_number}\n\nЗбережи собі на телефон!",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Не вдалося згенерувати паспорт: {e}")

    logger.info(f"DONE uid={update.effective_user.id} data={d}")
    save_to_sheet(d)
    return ConversationHandler.END

async def cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Опитування скасовано. Напиши /start щоб почати знову.",
        reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

# ── ЗАПУСК ─────────────────────────────────────────────────────────
def main():
    app = Application.builder().token(TOKEN).build()
    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            CONSENT:[MessageHandler(filters.TEXT&~filters.COMMAND,consent)],
            GENDER:[MessageHandler(filters.TEXT&~filters.COMMAND,gender)],
            REGION:[MessageHandler(filters.TEXT&~filters.COMMAND,region)],
            FULL_NAME:[MessageHandler(filters.TEXT&~filters.COMMAND,full_name)],
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
            TICKET:[MessageHandler(filters.TEXT&~filters.COMMAND,ticket)],
            PARENT_NAME:[MessageHandler(filters.TEXT&~filters.COMMAND,parent_name)],
            CONTACT_PHONE:[MessageHandler(filters.TEXT&~filters.COMMAND,contact_phone)],
            CONTACT_TIME:[MessageHandler(filters.TEXT&~filters.COMMAND,contact_time)],
        },
        fallbacks=[CommandHandler("cancel",cancel)],
        allow_reentry=True
    )
    app.add_handler(conv)
    print("✅ Бот запущено! Натисни Ctrl+C для зупинки.")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
