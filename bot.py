import asyncio
import logging
import os
import sqlite3
import random
import html
from datetime import datetime
from aiohttp import web
from html import escape
from typing import Final, Any, Optional

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, or_f
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton,
    Message, CallbackQuery, BotCommand, InlineKeyboardMarkup
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

from dotenv import load_dotenv

# .env faylini yuklash
load_dotenv()

try:
    from groq import Groq
except Exception:
    Groq = None

# ==========================================================================================
# 💎 PREMIUM KONFIGURATSIYA
# ==========================================================================================
class Assets:
    # Qiymatlarni environment variable'dan olish
    TOKEN: Final[str] = os.getenv("BOT_TOKEN")
    GROQ_KEY: Final[str] = os.getenv("GROQ_API_KEY")
    # ADMIN_ID doim int (son) bo'lishi kerak
    ADMIN_ID: Final[int] = int(os.getenv("ADMIN_ID", 0))
    DB_NAME: Final[str] = os.getenv("DB_NAME", "database.db")

    D_LINE = "<b>▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬</b>"
    S_LINE = "<b>────────────────────</b>"

    ICO_TEST = "🧩 Testlar Markazi"
    ICO_CHECK = "📝 Test Topshirish"
    ICO_DAILY = "📅 Kunlik test"
    ICO_AI = "🤖 AI Mentor (Premium)"
    ICO_HIS = "📈 Natijalarim"
    ICO_PROF = "👤 Shaxsiy Kabinet"
    ICO_HELP = "🆘 Yordam / Bog'lanish"
    ICO_ADM = "🛠 Admin Boshqaruvi"
    ICO_BACK = "⬅️ Orqaga"
    ICO_HOME = "🏠 Asosiy Menyu"

    ADM_ADD_TEST = "➕ Yangi Test Qo'shish"
    ADM_ADD_DAILY = "➕ Kunlik Test Qo'shish"
    ADM_STATS = "📊 Umumiy Statistika"
    ADM_DAILY_STATS = "📊 Kunlik Statistika"
    ADM_DEL_TEST = "🗑 Testni O'chirish"
    ADM_BROADCAST = "📢 Barchaga Xabar"
    
    @staticmethod
    def progress_bar(perc: float) -> str:
        full = max(0, min(10, int(perc // 10)))
        empty = 10 - full
        return "🟢" * full + "⚪" * empty


logging.basicConfig(level=logging.INFO)
bot = Bot(token=Assets.TOKEN)
dp = Dispatcher(storage=MemoryStorage())

groq_client = Groq(api_key=Assets.GROQ_KEY) if Groq and Assets.GROQ_KEY else None


# ==========================================================================================
# 🗄 DATABASE
# ==========================================================================================
class DB:
    @staticmethod
    def connect():
        conn = sqlite3.connect(Assets.DB_NAME)
        conn.row_factory = sqlite3.Row
        return conn

    @classmethod
    def setup(cls):
        with cls.connect() as conn:
            c = conn.cursor()
            c.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    uid INTEGER PRIMARY KEY,
                    fullname TEXT,
                    username TEXT,
                    joined_at TIMESTAMP,
                    phone TEXT,
                    student_id TEXT UNIQUE
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS tests (
                    kod TEXT PRIMARY KEY,
                    javoblar TEXT,
                    file_id TEXT,
                    title TEXT,
                    created_at TIMESTAMP
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS results (
                    rid INTEGER PRIMARY KEY AUTOINCREMENT,
                    uid INTEGER,
                    kod TEXT,
                    ball INTEGER,
                    total INTEGER,
                    perc REAL,
                    mistakes TEXT,
                    timestamp TIMESTAMP
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS daily_tests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    kod TEXT,
                    javoblar TEXT,
                    file_id TEXT,
                    title TEXT,
                    created_at TIMESTAMP
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS daily_results (
                    uid INTEGER PRIMARY KEY,
                    kod TEXT,
                    ball INTEGER,
                    total INTEGER,
                    perc REAL,
                    mistakes TEXT,
                    timestamp TIMESTAMP
                )
            """)
            conn.commit()

    @classmethod
    def run(cls, sql: str, params: tuple = (), fetch: str = "none") -> Any:
        with cls.connect() as conn:
            c = conn.cursor()
            c.execute(sql, params)
            if fetch == "all":
                return [dict(r) for r in c.fetchall()]
            if fetch == "one":
                row = c.fetchone()
                return dict(row) if row else None
            conn.commit()
            return c.lastrowid

    @classmethod
    def clear_daily_stats(cls):
        with cls.connect() as conn:
            c = conn.cursor()
            c.execute("DELETE FROM daily_results")
            c.execute("DELETE FROM daily_tests")
            conn.commit()


# ==========================================================================================
# 🧠 STATES
# ==========================================================================================
class Form(StatesGroup):
    reg = State()
    reg_phone = State() # YANGI: Raqam so'rash holati

    check_code = State()
    solve_ans = State()

    daily_solve_ans = State()

    ai_chat = State()
    support = State()
    adm_reply = State()

    adm_add_kod = State()
    adm_add_title = State()
    adm_add_ans = State()
    adm_add_file = State()

    adm_add_daily_kod = State()
    adm_add_daily_title = State()
    adm_add_daily_ans = State()
    adm_add_daily_file = State()
    adm_broadcast = State()

# ==========================================================================================
# 🎨 UI
# ==========================================================================================
class UI:
    @staticmethod
    def main_menu(user_id: int):
        b = ReplyKeyboardBuilder()
        b.row(KeyboardButton(text=Assets.ICO_TEST), KeyboardButton(text=Assets.ICO_CHECK))
        b.row(KeyboardButton(text=Assets.ICO_DAILY), KeyboardButton(text=Assets.ICO_AI))
        b.row(KeyboardButton(text=Assets.ICO_HIS), KeyboardButton(text=Assets.ICO_PROF))
        b.row(KeyboardButton(text=Assets.ICO_HELP))
        if user_id == Assets.ADMIN_ID:
            b.row(KeyboardButton(text=Assets.ICO_ADM))
        b.adjust(2, 2, 2, 1)
        return b.as_markup(resize_keyboard=True)
        
    @staticmethod
    def admin_menu():
        b = ReplyKeyboardBuilder()
        b.row(KeyboardButton(text=Assets.ADM_ADD_TEST), KeyboardButton(text=Assets.ADM_ADD_DAILY))
        b.row(KeyboardButton(text=Assets.ADM_STATS), KeyboardButton(text=Assets.ADM_DAILY_STATS))
        b.row(KeyboardButton(text=Assets.ADM_DEL_TEST), KeyboardButton(text=Assets.ADM_BROADCAST))
        b.row(KeyboardButton(text=Assets.ICO_HOME))
        b.adjust(2, 2, 2, 1)
        return b.as_markup(resize_keyboard=True)

    @staticmethod
    def back_btn():
        return ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text=Assets.ICO_BACK)]],
            resize_keyboard=True
        )


# ==========================================================================================
# HELPERS
# ==========================================================================================
def now_text() -> str:
    return datetime.now().strftime("%d.%m.%Y %H:%M")


def fmt_dt(value: Optional[str]) -> str:
    if not value:
        return "-"
    return str(value)[:16]


def normalize_answers(text: str) -> str:
    return "".join((text or "").lower().split())


def score_answers(user_ans: str, correct_ans: str):
    u = normalize_answers(user_ans)
    t = normalize_answers(correct_ans)
    mistakes = []
    correct = 0

    for i in range(min(len(u), len(t))):
        if u[i] == t[i]:
            correct += 1
        else:
            mistakes.append(f"{i+1}-{u[i].upper()}")

    return u, t, correct, mistakes


def get_active_daily_test():
    return DB.run("SELECT * FROM daily_tests ORDER BY id DESC LIMIT 1", fetch="one")


# ==========================================================================================
# SOZLAMALAR: Majburiy kanallar ro'yxati (Bot bu kanallarda ADMIN bo'lishi shart!)
# ==========================================================================================
REQUIRED_CHANNELS = [
    {"name": "📢 Asosiy Kanal", "id": "@matematika_999"},
]

async def is_subscribed(bot: Bot, user_id: int) -> bool:
    for channel in REQUIRED_CHANNELS:
        try:
            member = await bot.get_chat_member(chat_id=channel["id"], user_id=user_id)
            if member.status in ['left', 'kicked', 'banned']:
                return False
        except Exception:
            return False 
    return True

def get_subscription_keyboard():
    builder = InlineKeyboardBuilder()
    for channel in REQUIRED_CHANNELS:
        url = f"https://t.me/{channel['id'].replace('@', '')}"
        builder.row(InlineKeyboardButton(text=channel["name"], url=url))
    
    builder.row(InlineKeyboardButton(text="✅ Obunani tasdiqlash", callback_data="check_subscription"))
    return builder.as_markup()

# ==========================================================================================
# AVTOMATIK YO'NALTIRISH (Menu yoki Ro'yxatdan o'tish)
# ==========================================================================================
async def process_user_entry(message: Message, state: FSMContext, user_id: int, user_firstname: str):
    DB.setup()
    user = DB.run("SELECT * FROM users WHERE uid=?", (user_id,), fetch="one")

    if not user:
        await state.set_state(Form.reg)
        text = (
            f"🌟 <b>LOGOS PLATINUM ACADEMY</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"👋 Assalomu alaykum, <b>{html.escape(user_firstname)}</b>!\n"
            f"Matematikadan sertifikat botiga xush kelibsiz.\n\n"
            f"✍️ <i>Saytdan va botdan to'liq foydalanish uchun ism va familiyangizni kiriting:</i>\n\n"
            f"💡 <b>Namuna:</b> <i>Aliyev Vali</i>"
        )
        await message.answer(text, parse_mode="HTML")
    else:
        dashboard = (
            f"👑 <b>ASOSIY BOSHQARUV PANELI</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"👤 Foydalanuvchi: <b>{html.escape(user['fullname'])}</b>\n"
            f"🔑 Tizim ID (Sayt uchun): <code>{escape(user['student_id'])}</code>\n"
            f"🎖 Status: <b>Premium A'zo</b> 💎\n\n"
            f"📅 Sana: <b>{datetime.now().strftime('%d.%m.%Y')}</b>\n"
            f"🕒 Vaqt: <b>{datetime.now().strftime('%H:%M')}</b>\n\n"
            f"👇 <i>Kerakli bo'limni tanlang:</i>"
        )
        await message.answer(dashboard, reply_markup=UI.main_menu(user_id), parse_mode="HTML")

# ==========================================================================================
# START / RESET HANDLER
# ==========================================================================================
@dp.message(or_f(Command("start"), F.text == Assets.ICO_HOME, F.text == Assets.ICO_BACK))
async def global_reset(message: Message, state: FSMContext, bot: Bot):
    await state.clear()

    subscribed = await is_subscribed(bot, message.from_user.id)
    if not subscribed:
        text = (
            f"🛑 <b>DIQQAT! Botdan foydalanish uchun obuna bo'ling!</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"Bot xizmatlaridan foydalanish uchun quyidagi rasmiy kanallarimizga a'zo bo'lishingiz majburiy.\n\n"
            f"<i>Obuna bo'lgach, pastdagi <b>«✅ Obunani tasdiqlash»</b> tugmasini bosing.</i>"
        )
        await message.answer(text, reply_markup=get_subscription_keyboard(), parse_mode="HTML")
        return

    await process_user_entry(message, state, message.from_user.id, message.from_user.first_name)

@dp.callback_query(F.data == "check_subscription")
async def check_sub_handler(call: CallbackQuery, state: FSMContext, bot: Bot):
    subscribed = await is_subscribed(bot, call.from_user.id)
    if not subscribed:
        await call.answer("❌ Siz barcha kanallarga obuna bo'lmadingiz! Iltimos, obuna bo'ling.", show_alert=True)
        return

    await call.message.delete()
    await process_user_entry(call.message, state, call.from_user.id, call.from_user.first_name)

# ==========================================================================================
# RO'YXATDAN O'TISHNI YAKUNLASH (YANGILANGAN QISM)
# ==========================================================================================
@dp.message(Form.reg)
async def reg_get_name(message: Message, state: FSMContext):
    await state.update_data(fullname=message.text)
    await state.set_state(Form.reg_phone)
    
    kb = ReplyKeyboardBuilder()
    kb.row(KeyboardButton(text="📱 Telefon raqamni yuborish", request_contact=True))
    
    await message.answer(
        f"Ajoyib, <b>{html.escape(message.text)}</b>!\n\n"
        f"Endi tizim bilan to'liq ulanish uchun pastdagi tugma orqali <b>telefon raqamingizni</b> yuboring:",
        reply_markup=kb.as_markup(resize_keyboard=True, one_time_keyboard=True),
        parse_mode="HTML"
    )

@dp.message(Form.reg_phone)
async def registration_finish(message: Message, state: FSMContext):
    data = await state.get_data()
    fullname = data.get("fullname")
    
    if message.contact is not None:
        phone = message.contact.phone_number
    else:
        phone = message.text
        
    student_id = str(random.randint(100000, 999999))
    
    DB.run(
        "INSERT OR REPLACE INTO users (uid, fullname, username, joined_at, phone, student_id) VALUES (?,?,?,?,?,?)",
        (message.from_user.id, fullname, message.from_user.username, datetime.now().isoformat(), phone, student_id)
    )
    
    success_text = (
        f"🎉 <b>Muvaffaqiyatli ro'yxatdan o'tdingiz!</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👤 <b>Foydalanuvchi:</b> {html.escape(fullname)}\n"
        f"📞 <b>Raqam:</b> {html.escape(phone)}\n"
        f"🔑 <b>TIZIM ID:</b> <code>{student_id}</code>\n\n"
        f"<i>☝️ Saytga kirish uchun yuqoridagi 6 xonali Tizim ID raqamidan nusxa oling.</i>\n"
        f"Endi testlar, kunlik vazifalar va AI xizmatlaridan to'liq foydalana olasiz."
    )
    
    site_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🌐 Saytga o'tish", url="https://sizning-saytingiz-linki.com")] # <-- SHU YERGA SAYT LINKINI QO'YING
    ])
    
    await message.answer(success_text, reply_markup=site_kb, parse_mode="HTML")
    await message.answer("Boshqaruv paneli:", reply_markup=UI.main_menu(message.from_user.id))
    await state.clear()

# ==========================================================================================
# QOLGAN BARCHA FUNKSIYALAR (O'ZGARISHSZ)
# ==========================================================================================
@dp.message(F.text == Assets.ICO_TEST)
async def test_list(message: Message):
    tests = DB.run("SELECT * FROM tests ORDER BY created_at DESC", fetch="all")
    if not tests:
        return await message.answer("📭 <b>Hozircha testlar bazasi bo'sh.</b>", parse_mode="HTML")

    res_text = f"📂 <b>MAVJUD TESTLAR ARXIVI</b>\n{Assets.D_LINE}\n"
    for t in tests:
        res_text += (
            f"📙 <b>{escape(t['title'])}</b>\n"
            f"└ 🔑 Kod: <code>{escape(t['kod'])}</code> | 🕒 {fmt_dt(t['created_at'])}\n"
            f"{Assets.S_LINE}\n"
        )
    res_text += "<i>💡 Test topshirish uchun 'Testni Tekshirish' bo'limiga o'ting.</i>"
    await message.answer(res_text, parse_mode="HTML")

@dp.message(F.text == Assets.ICO_CHECK)
async def check_init(message: Message, state: FSMContext):
    await state.set_state(Form.check_code)
    await message.answer(
        "🆔 <b>TEST KODINI KIRITING</b>\n"
        f"{Assets.S_LINE}\n"
        "Iltimos, kerakli testning kodini yuboring:",
        reply_markup=UI.back_btn(), parse_mode="HTML"
    )

@dp.message(Form.check_code)
async def check_process(message: Message, state: FSMContext):
    test = DB.run("SELECT * FROM tests WHERE kod=?", (message.text.strip(),), fetch="one")
    if not test:
        return await message.answer("🚫 <b>Xatolik:</b> Bunday kodli test mavjud emas!", parse_mode="HTML")

    await state.update_data(active_test=test)
    await state.set_state(Form.solve_ans)

    info = (
        f"📝 <b>TEST MA'LUMOTLARI</b>\n"
        f"{Assets.D_LINE}\n"
        f"📖 Fan: <b>{escape(test['title'])}</b>\n"
        f"🔢 Javoblar soni: <b>{len(normalize_answers(test['javoblar']))} ta</b>\n"
        f"🔑 Kod: <code>{escape(test['kod'])}</code>\n"
        f"{Assets.S_LINE}\n"
        f"📥 <b>Javoblaringizni yuboring:</b>\n"
        f"Format: <code>abcd...</code>"
    )

    if test["file_id"]:
        await message.answer_document(test["file_id"], caption=info, parse_mode="HTML")
    else:
        await message.answer(info, parse_mode="HTML")

@dp.message(Form.solve_ans)
async def test_logic(message: Message, state: FSMContext):
    data = await state.get_data()
    test = data.get("active_test")
    if not test:
        await state.clear()
        return await message.answer("⚠️ Test ma'lumoti topilmadi. Qaytadan urinib ko'ring.")

    u_ans, t_ans, correct, mistakes = score_answers(message.text, test["javoblar"])

    if len(u_ans) != len(t_ans):
        return await message.answer(
            f"❌ <b>Soni mos kelmadi!</b>\n\n"
            f"Siz {len(u_ans)} ta javob berdingiz, testda esa {len(t_ans)} ta savol bor.\n"
            f"Qaytadan diqqat bilan yuboring.", parse_mode="HTML"
        )

    total = len(t_ans)
    perc = (correct / total) * 100 if total else 0

    rid = DB.run(
        "INSERT INTO results (uid, kod, ball, total, perc, mistakes, timestamp) VALUES (?,?,?,?,?,?,?)",
        (message.from_user.id, test["kod"], correct, total, perc, ", ".join(mistakes), datetime.now().isoformat())
    )

    res_msg = (
        f"🏁 <b>TEST NATIJASI</b>\n"
        f"{Assets.D_LINE}\n"
        f"👤 Nom: <b>{escape(message.from_user.full_name)}</b>\n"
        f"📊 Ball: <b>{correct} / {total}</b>\n"
        f"📈 Foiz: <b>{perc:.1f} %</b>\n\n"
        f"{Assets.progress_bar(perc)}\n\n"
        f"❌ Xatolar: <code>{escape(', '.join(mistakes) if mistakes else 'MUKAMMAL!')}</code>\n"
        f"{Assets.S_LINE}\n"
        f"🔖 Natija ID: <code>#{rid}</code>"
    )
    await message.answer(res_msg, reply_markup=UI.main_menu(message.from_user.id), parse_mode="HTML")
    await state.clear()

@dp.message(F.text == Assets.ICO_DAILY)
async def daily_test_start(message: Message, state: FSMContext):
    test = get_active_daily_test()
    if not test:
        return await message.answer("📭 <b>Hozircha kunlik test qo'shilmagan.</b>\nAdmin yangi test qo'shganda bu yerda ko'rinadi.", parse_mode="HTML")

    await state.update_data(active_daily_test=test)
    await state.set_state(Form.daily_solve_ans)

    info = (
        f"🌟 <b>KUNLIK TEST</b>\n"
        f"{Assets.D_LINE}\n"
        f"📖 Test nomi: <b>{escape(test['title'])}</b>\n"
        f"🔢 Javoblar soni: <b>{len(normalize_answers(test['javoblar']))} ta</b>\n"
        f"🕒 Yangilangan: <b>{fmt_dt(test['created_at'])}</b>\n"
        f"{Assets.S_LINE}\n"
        f"📥 <b>Javoblaringizni hozir shu joyda yuboring:</b>\n"
        f"Format: <code>abcd...</code>"
    )

    if test["file_id"]:
        await message.answer_document(test["file_id"], caption=info, parse_mode="HTML")
    else:
        await message.answer(info, parse_mode="HTML")

@dp.message(Form.daily_solve_ans)
async def daily_test_logic(message: Message, state: FSMContext):
    data = await state.get_data()
    test = data.get("active_daily_test")
    if not test:
        await state.clear()
        return await message.answer("⚠️ Kunlik test topilmadi. Qaytadan urinib ko'ring.")

    u_ans, t_ans, correct, mistakes = score_answers(message.text, test["javoblar"])

    if len(u_ans) != len(t_ans):
        return await message.answer(f"❌ <b>Soni mos kelmadi!</b>\n\nSiz {len(u_ans)} ta javob berdingiz, testda esa {len(t_ans)} ta savol bor.", parse_mode="HTML")

    total = len(t_ans)
    perc = (correct / total) * 100 if total else 0

    DB.run(
        "INSERT OR REPLACE INTO daily_results (uid, kod, ball, total, perc, mistakes, timestamp) VALUES (?,?,?,?,?,?,?)",
        (message.from_user.id, test["kod"], correct, total, perc, ", ".join(mistakes), datetime.now().isoformat())
    )

    res_msg = (
        f"🏆 <b>KUNLIK TEST NATIJASI</b>\n"
        f"{Assets.D_LINE}\n"
        f"👤 Nom: <b>{escape(message.from_user.full_name)}</b>\n"
        f"📊 Ball: <b>{correct} / {total}</b>\n"
        f"📈 Foiz: <b>{perc:.1f} %</b>\n\n"
        f"{Assets.progress_bar(perc)}\n\n"
        f"❌ Xatolar: <code>{escape(', '.join(mistakes) if mistakes else 'MUKAMMAL!')}</code>\n"
        f"{Assets.S_LINE}\n"
        f"📅 Bu natija kunlik statistikaga qo'shildi."
    )
    await message.answer(res_msg, reply_markup=UI.main_menu(message.from_user.id), parse_mode="HTML")
    await state.clear()

@dp.message(F.text == Assets.ICO_HELP)
async def support_start(message: Message, state: FSMContext):
    await state.set_state(Form.support)
    await message.answer(
        f"<b>{Assets.S_LINE}</b>\n📬 <b>ADMINISTRATSIYA BILAN ALOQA</b>\n<b>{Assets.S_LINE}</b>\n\n"
        f"Savolingiz, taklifingiz yoki shikoyatingizni yozib qoldiring.\n\n<i>Xabar matnini kiriting:</i>",
        reply_markup=UI.back_btn(), parse_mode="HTML"
    )

@dp.message(Form.support)
async def support_sent(message: Message, state: FSMContext):
    user_id = message.from_user.id
    user_name = message.from_user.full_name
    text = message.text or ""

    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="✍️ Javob yozish", callback_data=f"reply_{user_id}"))

    await bot.send_message(
        Assets.ADMIN_ID,
        f"🆕 <b>YANGI MUROJAAT</b>\n<b>{Assets.D_LINE}</b>\n👤 Kimdan: <b>{escape(user_name)}</b>\n"
        f"🆔 ID: <code>{user_id}</code>\n💬 Xabar: <i>{escape(text)}</i>\n<b>{Assets.D_LINE}</b>",
        reply_markup=kb.as_markup(), parse_mode="HTML"
    )

    await message.answer("✅ <b>Xabaringiz adminga yetkazildi!</b>\nJavobni kuting.", reply_markup=UI.main_menu(message.from_user.id), parse_mode="HTML")
    await state.clear()

@dp.callback_query(F.data.startswith("reply_"))
async def admin_reply_start(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != Assets.ADMIN_ID: return await call.answer("Ruxsat yo'q", show_alert=True)
    target_id = call.data.split("_", 1)[1]
    await state.update_data(reply_to=target_id)
    await state.set_state(Form.adm_reply)
    await call.message.answer(f"📝 <b>Foydalanuvchiga javob yozing:</b>\nID: <code>{target_id}</code>", reply_markup=UI.back_btn(), parse_mode="HTML")
    await call.answer()

@dp.message(Form.adm_reply)
async def admin_reply_sent(message: Message, state: FSMContext):
    if message.from_user.id != Assets.ADMIN_ID: return
    data = await state.get_data()
    target_id = data.get("reply_to")
    reply_text = message.text or ""
    try:
        await bot.send_message(
            int(target_id),
            f"📩 <b>ADMINISTRATSIYA JAVOBI</b>\n<b>{Assets.D_LINE}</b>\n{escape(reply_text)}\n"
            f"<b>{Assets.D_LINE}</b>\n<i>Savollaringiz bo'lsa, yana murojaat qilishingiz mumkin.</i>",
            parse_mode="HTML"
        )
        await message.answer("✅ Javob yuborildi.", reply_markup=UI.admin_menu(), parse_mode="HTML")
    except Exception as e:
        await message.answer(f"❌ Xatolik: foydalanuvchiga yuborib bo'lmadi.\n<code>{escape(str(e))}</code>", parse_mode="HTML")
    await state.clear()

@dp.message(F.text == Assets.ICO_AI)
async def ai_init(message: Message, state: FSMContext):
    await state.set_state(Form.ai_chat)
    await message.answer(
        f"🧠 <b>LOGOS AI MENTOR</b>\n{Assets.S_LINE}\nMen sizga istalgan fanda yordam bera olaman.\nSavolingizni batafsil yozing:",
        reply_markup=UI.back_btn(), parse_mode="HTML"
    )

@dp.message(Form.ai_chat)
async def ai_logic(message: Message):
    if message.text == Assets.ICO_BACK: return
    loading = await message.answer("🔄 <i>Sun'iy intellekt tahlil qilmoqda...</i>")
    try:
        if not groq_client:
            await loading.edit_text("⚠️ <b>AI sozlanmagan.</b> GROQ_KEY topilmadi.", parse_mode="HTML")
            return
        resp = groq_client.chat.completions.create(
            messages=[{"role": "system", "content": "Siz aqlli ta'lim mentorisiz. Savollarga faqat O'zbek tilida, aniq va tushunarli javob bering."}, {"role": "user", "content": message.text}],
            model="llama-3.3-70b-versatile"
        )
        ai_reply = f"🎓 <b>USTOZ JAVOBI:</b>\n{Assets.D_LINE}\n{escape(resp.choices[0].message.content)}\n{Assets.S_LINE}\n<i>Yana biror savolingiz bormi?</i>"
        await loading.edit_text(ai_reply, parse_mode="HTML")
    except Exception:
        await loading.edit_text("⚠️ <b>Texnik nosozlik!</b> AI bilan bog'lanishda xatolik yuz berdi.", parse_mode="HTML")

@dp.message(F.text == Assets.ICO_PROF)
async def profile(message: Message):
    u = DB.run("SELECT * FROM users WHERE uid=?", (message.from_user.id,), fetch="one")
    if not u: return await message.answer("⚠️ Profil topilmadi. /start yuboring.", parse_mode="HTML")
    p_text = (
        f"💎 <b>SHAXSIY PROFIL</b>\n{Assets.D_LINE}\n👤 Ism: <b>{escape(u['fullname'])}</b>\n"
        f"📞 Raqam: <b>{escape(u['phone'])}</b>\n🔑 Tizim ID (Sayt uchun): <code>{escape(u['student_id'])}</code>\n"
        f"🆔 Baza ID: <code>{u['uid']}</code>\n📅 Ro'yxatdan o'tdi: <b>{fmt_dt(u['joined_at'])}</b>\n"
        f"{Assets.S_LINE}\nBarcha natijalaringiz xavfsiz saqlanmoqda."
    )
    await message.answer(p_text, parse_mode="HTML")

@dp.message(F.text == Assets.ICO_HIS)
async def history(message: Message):
    res = DB.run("SELECT * FROM results WHERE uid=? ORDER BY timestamp DESC LIMIT 10", (message.from_user.id,), fetch="all")
    if not res: return await message.answer("<b>Sizda hali natijalar mavjud emas.</b>", parse_mode="HTML")
    msg = f"📊 <b>OXIRGI 10 TA NATIJA</b>\n{Assets.D_LINE}\n"
    for r in res:
        msg += f"📎 <b>Kod: {escape(r['kod'])}</b> | Ball: <b>{r['ball']}/{r['total']}</b> | <b>{r['perc']:.1f}%</b>\n"
    await message.answer(msg, parse_mode="HTML")

@dp.message(F.text == Assets.ICO_ADM)
async def admin_portal(message: Message):
    if message.from_user.id != Assets.ADMIN_ID: return
    daily = get_active_daily_test()
    daily_info = f"📅 Kunlik test: {escape(daily['title'])} | <code>{escape(daily['kod'])}</code>\n" if daily else "📅 Kunlik test: hali yo'q\n"
    await message.answer(
        f"<b>{Assets.D_LINE}</b>\n⚡️ <b>ADMINISTRATOR DASHBOARD</b>\n<b>{Assets.D_LINE}</b>\n\n"
        f"👤 Profil: <b>{escape(message.from_user.full_name)}</b>\n📊 Holat: <code>🟢 SYSTEM ONLINE | v4.8 Platinum</code>\n"
        f"🕒 Vaqt: <code>{datetime.now().strftime('%H:%M:%S')}</code>\n{daily_info}\n<i>Boshqarish uchun menyuni ishlating:</i>",
        reply_markup=UI.admin_menu(), parse_mode="HTML"
    )

@dp.message(F.text == Assets.ADM_ADD_TEST)
async def adm_add_start(message: Message, state: FSMContext):
    if message.from_user.id != Assets.ADMIN_ID: return
    await state.set_state(Form.adm_add_kod)
    await message.answer("🧩 <b>YANGI TEST YARATISH</b>\n<b>1️⃣ QADAM:</b> Test uchun <b>ID KOD</b> kiriting.\n<i>Masalan: <code>2024</code></i>", reply_markup=UI.back_btn(), parse_mode="HTML")

@dp.message(Form.adm_add_kod)
async def adm_add_k(message: Message, state: FSMContext):
    if message.from_user.id != Assets.ADMIN_ID: return
    check = DB.run("SELECT kod FROM tests WHERE kod=?", (message.text.strip(),), fetch="one")
    if check: return await message.answer("❌ <b>Xatolik:</b> Ushbu kod band! Boshqa ID tanlang.", parse_mode="HTML")
    await state.update_data(kod=message.text.strip())
    await state.set_state(Form.adm_add_title)
    await message.answer("<b>2️⃣ QADAM:</b> Fan yoki test sarlavhasini kiriting:", parse_mode="HTML")

@dp.message(Form.adm_add_title)
async def adm_add_t(message: Message, state: FSMContext):
    if message.from_user.id != Assets.ADMIN_ID: return
    await state.update_data(title=message.text.strip())
    await state.set_state(Form.adm_add_ans)
    await message.answer("<b>3️⃣ QADAM:</b> To'g'ri javoblarni yuboring:\n📥 <i>Namuna: <code>abcd...</code></i>", parse_mode="HTML")

@dp.message(Form.adm_add_ans)
async def adm_add_a(message: Message, state: FSMContext):
    if message.from_user.id != Assets.ADMIN_ID: return
    ans = normalize_answers(message.text)
    if not ans: return await message.answer("⚠️ Javoblar bo'sh bo'lmasin.", parse_mode="HTML")
    await state.update_data(ans=ans)
    await state.set_state(Form.adm_add_file)
    await message.answer("<b>4️⃣ QADAM:</b> Test faylini biriktiring (ixtiyoriy):\n➡️ <i>Faylsiz davom etish: /skip</i>", parse_mode="HTML")

@dp.message(Form.adm_add_file)
async def adm_add_f(message: Message, state: FSMContext):
    if message.from_user.id != Assets.ADMIN_ID: return
    data = await state.get_data()
    fid = message.document.file_id if message.document else None
    if not message.document and (message.text or "").strip() != "/skip":
        return await message.answer("⚠️ Iltimos, fayl yuboring yoki /skip buyrug'ini bering.", parse_mode="HTML")
    DB.run("INSERT INTO tests (kod, javoblar, file_id, title, created_at) VALUES (?,?,?,?,?)",
           (data["kod"], data["ans"], fid, data["title"], datetime.now().isoformat()))
    await message.answer(f"✨ <b>TEST YARATILDI!</b>\nFan: {escape(data['title'])}\nKod: <code>{escape(data['kod'])}</code>\nSavollar: {len(data['ans'])} ta", reply_markup=UI.admin_menu(), parse_mode="HTML")
    await state.clear()

@dp.message(F.text == Assets.ADM_ADD_DAILY)
async def adm_add_daily_start(message: Message, state: FSMContext):
    if message.from_user.id != Assets.ADMIN_ID: return
    await state.set_state(Form.adm_add_daily_kod)
    await message.answer("🌟 <b>KUNLIK TEST QO'SHISH</b>\n<b>1️⃣ QADAM:</b> Kunlik test uchun <b>ID KOD</b> kiriting.", reply_markup=UI.back_btn(), parse_mode="HTML")

@dp.message(Form.adm_add_daily_kod)
async def adm_add_daily_k(message: Message, state: FSMContext):
    if message.from_user.id != Assets.ADMIN_ID: return
    await state.update_data(daily_kod=message.text.strip())
    await state.set_state(Form.adm_add_daily_title)
    await message.answer("<b>2️⃣ QADAM:</b> Kunlik test sarlavhasini kiriting:", parse_mode="HTML")

@dp.message(Form.adm_add_daily_title)
async def adm_add_daily_t(message: Message, state: FSMContext):
    if message.from_user.id != Assets.ADMIN_ID: return
    await state.update_data(daily_title=message.text.strip())
    await state.set_state(Form.adm_add_daily_ans)
    await message.answer("<b>3️⃣ QADAM:</b> To'g'ri javoblarni kiriting:\n📥 <i>Namuna: <code>abcd...</code></i>", parse_mode="HTML")

@dp.message(Form.adm_add_daily_ans)
async def adm_add_daily_a(message: Message, state: FSMContext):
    if message.from_user.id != Assets.ADMIN_ID: return
    ans = normalize_answers(message.text)
    if not ans: return await message.answer("⚠️ Javoblar bo'sh bo'lmasin.", parse_mode="HTML")
    await state.update_data(daily_ans=ans)
    await state.set_state(Form.adm_add_daily_file)
    await message.answer("<b>4️⃣ QADAM:</b> Kunlik test faylini biriktiring (ixtiyoriy):\n➡️ <i>Faylsiz davom etish: /skip</i>", parse_mode="HTML")

@dp.message(Form.adm_add_daily_file)
async def adm_add_daily_f(message: Message, state: FSMContext):
    if message.from_user.id != Assets.ADMIN_ID: return
    data = await state.get_data()
    fid = message.document.file_id if message.document else None
    if not message.document and (message.text or "").strip() != "/skip": return await message.answer("⚠️ Fayl yoki /skip yuboring.", parse_mode="HTML")
    DB.clear_daily_stats()
    DB.run("INSERT INTO daily_tests (kod, javoblar, file_id, title, created_at) VALUES (?,?,?,?,?)",
           (data["daily_kod"], data["daily_ans"], fid, data["daily_title"], datetime.now().isoformat()))
    await message.answer(f"🌟 <b>KUNLIK TEST YARATILDI! Eski kunlik statistika tozalandi.</b>", reply_markup=UI.admin_menu(), parse_mode="HTML")
    await state.clear()

@dp.message(F.text == Assets.ADM_DEL_TEST)
async def adm_del_list(message: Message):
    if message.from_user.id != Assets.ADMIN_ID: return
    tests = DB.run("SELECT kod, title FROM tests ORDER BY created_at DESC", fetch="all")
    if not tests: return await message.answer("📂 <b>Tizimda testlar mavjud emas.</b>", parse_mode="HTML")
    kb = InlineKeyboardBuilder()
    for t in tests: kb.row(InlineKeyboardButton(text=f"🗑 {t['kod']} | {t['title']}", callback_data=f"pre_del_{t['kod']}"))
    await message.answer("⚠️ <b>O'chirmoqchi bo'lgan testingizni tanlang 👇</b>", reply_markup=kb.as_markup(), parse_mode="HTML")

@dp.callback_query(F.data.startswith("pre_del_"))
async def pre_del(call: CallbackQuery):
    if call.from_user.id != Assets.ADMIN_ID: return await call.answer("Ruxsat yo'q", show_alert=True)
    kod = call.data.split("_", 2)[2]
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="✅ TASDIQLASH", callback_data=f"confirm_del_{kod}"), InlineKeyboardButton(text="❌ BEKOR QILISH", callback_data="cancel_adm"))
    await call.message.edit_text(f"🛑 <b>DIQQAT! {kod} ni butunlay o'chirib yubormoqchisiz.</b>", reply_markup=kb.as_markup(), parse_mode="HTML")

@dp.callback_query(F.data.startswith("confirm_del_"))
async def confirm_del(call: CallbackQuery):
    if call.from_user.id != Assets.ADMIN_ID: return
    kod = call.data.split("_", 2)[2]
    DB.run("DELETE FROM tests WHERE kod=?", (kod,))
    DB.run("DELETE FROM results WHERE kod=?", (kod,))
    await call.answer("Test o'chirildi!", show_alert=True)
    await call.message.edit_text(f"🏁 <b>{kod}</b> kodli test tizimdan o'chirildi.")

async def show_general_stats(message_or_call):
    tests = DB.run("SELECT kod, title FROM tests ORDER BY created_at DESC", fetch="all")
    u_count = DB.run("SELECT COUNT(*) as c FROM users", fetch="one")["c"]
    r_count = DB.run("SELECT COUNT(*) as c FROM results", fetch="one")["c"]
    res_text = f"📊 <b>UMUMIY TIZIM STATISTIKASI</b>\n{Assets.D_LINE}\n👥 Foydalanuvchilar: <b>{u_count} ta</b>\n📝 Tizimdagi testlar topshirildi: <b>{r_count} marta</b>\n{Assets.S_LINE}\n<i>Batafsil ma'lumot olish uchun quyidagi testlardan birini tanlang:</i>"
    kb = InlineKeyboardBuilder()
    for t in tests: kb.row(InlineKeyboardButton(text=f"📂 {t['title']} ({t['kod']})", callback_data=f"stat_{t['kod']}"))
    if isinstance(message_or_call, Message): await message_or_call.answer(res_text, reply_markup=kb.as_markup(), parse_mode="HTML")
    else: await message_or_call.message.edit_text(res_text, reply_markup=kb.as_markup(), parse_mode="HTML")

@dp.message(F.text == Assets.ADM_STATS)
async def adm_general_stats(message: Message):
    if message.from_user.id != Assets.ADMIN_ID: return
    await show_general_stats(message)

@dp.callback_query(F.data.startswith("stat_"))
async def detailed_test_stats(call: CallbackQuery):
    if call.from_user.id != Assets.ADMIN_ID: return
    kod = call.data.split("_", 1)[1]
    results = DB.run("SELECT u.fullname, COUNT(r.rid) as tries, MAX(r.ball) as m_ball, MAX(r.total) as total, MAX(r.perc) as m_perc FROM results r JOIN users u ON r.uid = u.uid WHERE r.kod = ? GROUP BY u.uid ORDER BY m_perc DESC", (kod,), fetch="all")
    test = DB.run("SELECT title FROM tests WHERE kod=?", (kod,), fetch="one")
    if not results: return await call.answer("Bu testni hali hech kim ishlamagan!", show_alert=True)
    text = f"📈 <b>TEST STATISTIKASI: BATAFSIL</b>\n{Assets.D_LINE}\n🏷 Fan: <b>{test['title'] if test else 'Noma`lum'}</b>\n🔑 Kod: <code>{kod}</code>\n👥 Test ishlaganlar soni: <b>{len(results)} kishi</b>\n{Assets.S_LINE}\n\n"
    for i, r in enumerate(results, 1): text += f"<b>{i}. {escape(r['fullname'])}</b>\n└ 🏆 {r['m_ball']}/{r['total']} ({r['m_perc']:.1f}%) | 🔄 {r['tries']} marta ishlagan\n\n"
    if len(text) > 4000: text = text[:4000] + "...\n(Ro'yxat uzun)"
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Orqaga", callback_data="back_to_stats")]])
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=kb)

@dp.callback_query(F.data == "back_to_stats")
async def back_to_stats_list(call: CallbackQuery):
    if call.from_user.id != Assets.ADMIN_ID: return
    await show_general_stats(call)

@dp.message(F.text == Assets.ADM_DAILY_STATS)
async def adm_daily_stats(message: Message):
    if message.from_user.id != Assets.ADMIN_ID: return
    results = DB.run("SELECT u.fullname, r.ball, r.total, r.perc FROM daily_results r JOIN users u ON r.uid = u.uid ORDER BY r.perc DESC, r.timestamp ASC", fetch="all")
    if not results: return await message.answer("📅 <b>Kunlik test bo'yicha hali natijalar yo'q.</b>", parse_mode="HTML")
    text = f"🏆 <b>KUNLIK TEST REYTINGI</b>\n{Assets.D_LINE}\n"
    for i, r in enumerate(results, 1):
        icon = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else "🔹"
        text += f"{icon} <b>{escape(r['fullname'])}</b> - {r['ball']}/{r['total']} (<b>{r['perc']:.1f}%</b>)\n"
    await message.answer(text, parse_mode="HTML")

@dp.callback_query(F.data == "cancel_adm")
async def cancel_adm(call: CallbackQuery):
    await call.message.edit_text("🚫 <b>Amal bekor qilindi.</b>", parse_mode="HTML")

@dp.message(F.text == Assets.ADM_BROADCAST)
async def broadcast_start(message: Message, state: FSMContext):
    if message.from_user.id != Assets.ADMIN_ID: return
    await state.set_state(Form.adm_broadcast)
    await message.answer("📢 Barcha foydalanuvchilarga yuboriladigan xabarni kiriting:", reply_markup=UI.back_btn(), parse_mode="HTML")

@dp.message(Form.adm_broadcast)
async def broadcast_send(message: Message, state: FSMContext):
    if message.from_user.id != Assets.ADMIN_ID: return
    users = DB.run("SELECT uid FROM users", fetch="all")
    await message.answer("🔄 <i>Xabar barchaga yuborilmoqda, biroz kuting...</i>", parse_mode="HTML")
    success, fail = 0, 0
    for u in users:
        try:
            design_msg = f"✨ <b>LOGOS PLATINUM ACADEMY</b> ✨\n{Assets.D_LINE}\n\n{message.text or ''}\n\n{Assets.D_LINE}\n<i>Hurmat bilan, Ma'muriyat 👑</i>"
            await bot.send_message(u['uid'], design_msg, parse_mode="HTML")
            success += 1
            await asyncio.sleep(0.05)
        except Exception:
            fail += 1
    await message.answer(f"✅ <b>Xabaringiz yetkazildi!</b>\n🟢 Borganlar: <b>{success} ta</b>\n🔴 Bloklaganlar: <b>{fail} ta</b>", reply_markup=UI.admin_menu(), parse_mode="HTML")
    await state.clear()


# ==========================================================================================
# API (Saytdan bazani tekshirish uchun)
# ==========================================================================================
async def handle_login(request):
    # CORS muammosini hal qilish uchun HEADERS
    headers = {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'POST, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type',
    }
    
    # Brauzer API ga ulanayotganda oldin OPTIONS so'rovini yuboradi
    if request.method == 'OPTIONS':
        return web.Response(headers=headers)
        
    try:
        data = await request.json()
        student_id = data.get('student_id')
        
        # Saytda terilgan Tizim ID ni bazadan axtarish
        user = DB.run("SELECT fullname, uid FROM users WHERE student_id=?", (student_id,), fetch="one")
        
        if user:
            return web.json_response({
                "success": True,
                "name": user["fullname"],
                "role": "admin" if user["uid"] == Assets.ADMIN_ID else "student"
            }, headers=headers)
        else:
            return web.json_response({
                "success": False,
                "error": "Tizim ID topilmadi! Iltimos, avval Telegram bot orqali ro'yxatdan o'ting."
            }, headers=headers)
    except Exception as e:
        return web.json_response({"success": False, "error": str(e)}, headers=headers)

# Veb-server (Health Check)
async def handle(request):
    return web.Response(text="Bot va API ishladi! ✨")

# ==========================================================================================
# ASOSIY ISHGA TUSHIRISH (MAIN)
# ==========================================================================================
async def main():
    DB.setup()
    
    # Veb-server va APIni ishga tushirish
    app = web.Application()
    app.router.add_get("/", handle)
    app.router.add_options("/api/login", handle_login) # API CORS 
    app.router.add_post("/api/login", handle_login)    # API Kirish tekshiruv
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", int(os.getenv("PORT", 8080)))
    await site.start()

    await bot.set_my_commands([
        BotCommand(command="start", description="🏠 Asosiy menyu")
    ])
    
    print("💎 LOGOS PLATINUM V4.8 IS RUNNING WITH API...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
