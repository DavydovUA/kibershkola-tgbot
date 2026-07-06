import logging
import os
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, KeyboardButton
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    filters, ContextTypes, ConversationHandler
)

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("BOT_TOKEN")

(
    CONSENT, GENDER, GRADE,
    REGION, CITY_TYPE, CITY_NAME, DISTRICT, SCHOOL_TYPE, SCHOOL_NAME,
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
    TICKET, CONTACT_NAME, CONTACT_PHONE, CONTACT_TIME,
) = range(70)

SUPPORT_TEXT = (
    "💙 *Важлива інформація*\n\n"
    "Якщо тебе хтось ображає — в іграх, у школі або вдома — це не норма. Ти не один і не одна.\n\n"
    "Поговори з тим, кому довіряєш. Або зателефонуй:\n"
    "📞 *116 111* — безкоштовно з мобільного\n"
    "📞 *0 800 500 225* — безкоштовно\n\n"
    "_Анонімно · конфіденційно · психологи завжди поруч._"
)

def kb(options, cols=2):
    rows = [options[i:i+cols] for i in range(0, len(options), cols)]
    return ReplyKeyboardMarkup([[KeyboardButton(o) for o in row] for row in rows],
                               resize_keyboard=True, one_time_keyboard=True)

def save(ctx, key, val): ctx.user_data[key] = val
def grade_int(ctx): return int(ctx.user_data.get("grade", 0))

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
        "*П2. В якому ти класі?*",
        parse_mode="Markdown",
        reply_markup=kb(["3","4","5","6","7","8","9","10","11"])
    )
    return GRADE

async def grade(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    save(ctx, "grade", update.message.text)
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
        "*П4. Тип населеного пункту?*",
        parse_mode="Markdown",
        reply_markup=kb(["Обласний центр","Місто","Селище / СМТ","Село"])
    )
    return CITY_TYPE

async def city_type(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    save(ctx, "city_type", update.message.text)
    await update.message.reply_text(
        "*П5. Назва міста / селища / села?*\n\nНапиши назву:",
        parse_mode="Markdown", reply_markup=ReplyKeyboardRemove()
    )
    return CITY_NAME

async def city_name(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    save(ctx, "city_name", update.message.text)
    await update.message.reply_text(
        "*П5б. Район міста або громада?*\n_(напиши «-» якщо не знаєш)_",
        parse_mode="Markdown"
    )
    return DISTRICT

async def district(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    save(ctx, "district", update.message.text)
    await update.message.reply_text(
        "*П6. Тип школи?*",
        parse_mode="Markdown",
        reply_markup=kb(["Загальноосвітня","Ліцей","Гімназія","НВК","Інший"])
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
    await update.message.reply_text("*П10. Рівень участі?*", parse_mode="Markdown",
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
    await update.message.reply_text("*П15. Фізична активність поза школою?*", parse_mode="Markdown",
        reply_markup=kb(["Щодня","Кілька разів на тиждень","Рідко","Майже ніколи"]))
    return PHYS_OUT

async def phys_out(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    save(ctx, "phys_out", update.message.text)
    await update.message.reply_text("💻 *БЛОК: ПК*\n\n*П16. Чи граєш на комп'ютері або ноутбуці?*",
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
    await update.message.reply_text("*П21. Твій рівень на ПК?*", parse_mode="Markdown",
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
    await update.message.reply_text("*П25. Скільки годин на консолі?*", parse_mode="Markdown",
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
    await update.message.reply_text("*П29. Хотів би консольну секцію у клубі?*", parse_mode="Markdown",
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
    await update.message.reply_text("*П41. Жанр на мобільному?*", parse_mode="Markdown",
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
    await update.message.reply_text("*П44. Хотів би мобільну секцію у клубі?*", parse_mode="Markdown",
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
            "Якщо тобі зараз важко — не мовчи:\n"
            "📞 *116 111* (безкоштовно з мобільного)\n"
            "📞 *0 800 500 225*\n\n_Анонімно · психологи готові допомогти._",
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
    await update.message.reply_text("*П59. Батьки відпустять тебе на тренування після школи?*", parse_mode="Markdown",
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
    await update.message.reply_text("*Як тебе звуть?* (для квитка)\n\nНапиши ім'я та прізвище:",
        parse_mode="Markdown", reply_markup=ReplyKeyboardRemove())
    return CONTACT_NAME

async def contact_name(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    save(ctx, "contact_name", update.message.text)
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
    logger.info(f"DONE uid={update.effective_user.id} data={d}")
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
            GRADE:[MessageHandler(filters.TEXT&~filters.COMMAND,grade)],
            REGION:[MessageHandler(filters.TEXT&~filters.COMMAND,region)],
            CITY_TYPE:[MessageHandler(filters.TEXT&~filters.COMMAND,city_type)],
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
            CONTACT_NAME:[MessageHandler(filters.TEXT&~filters.COMMAND,contact_name)],
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
