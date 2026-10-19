import asyncio
import os
import aiohttp
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    InputMediaPhoto
)

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise ValueError("Ошибка: BOT_TOKEN не найден! Проверьте файл .env или переменные сервера.")

API_BASE_URL = "https://server-node-js-akor.up.railway.app/api/job-agency"
DEFAULT_PHOTO = "https://storage.googleapis.com/job-agency-akor.firebasestorage.app/vacancy-defaults/production.webp"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Хранилища состояний в памяти:
user_languages = {}  # user_id -> lang_code
user_vacancies = {}  # user_id -> list of vacancies
user_page_index = {}  # user_id -> current vacancy index

TEXTS = {
    "en": {
        "welcome": "👋 Welcome to Akor Direct Jobs!\nPlease choose your language:",
        "main_menu": "🎯 Main Menu\nSelect an option below:",
        "btn_jobs": "📋 View Vacancies",
        "btn_change_lang": "🌐 Change Language",
        "lang_saved": "Language set to English 🇬🇧",
        "loading": "⏳ Loading vacancies...",
        "no_vacancies": "No vacancies found at the moment.",
        "salary": "Salary",
        "hours": "hours/week",
        "housing": "Housing",
        "transport": "Transport",
        "yes": "Provided",
        "no": "Not provided",
        "btn_apply": "🌐 Apply on website",
        "btn_back_menu": "🔙 Main Menu",
        "apply_msg": "🔗 Follow this link to submit your application:"
    },
    "nl": {
        "welcome": "👋 Welkom bij Akor Direct Jobs!\nKies uw taal:",
        "main_menu": "🎯 Hoofdmenu\nSelecteer een optie:",
        "btn_jobs": "📋 Bekijk vacatures",
        "btn_change_lang": "🌐 Taal wijzigen",
        "lang_saved": "Taal ingesteld op Nederlands 🇳🇱",
        "loading": "⏳ Vacatures laden...",
        "no_vacancies": "Momenteel geen vacatures gevonden.",
        "salary": "Salaris",
        "hours": "uur/week",
        "housing": "Huisvesting",
        "transport": "Vervoer",
        "yes": "Beschikbaar",
        "no": "Niet inbegrepen",
        "btn_apply": "🌐 Solliciteer op de website",
        "btn_back_menu": "🔙 Hoofdmenu",
        "apply_msg": "🔗 Volg deze link om uw sollicitatie te versturen:"
    },
    "pl": {
        "welcome": "👋 Witamy w Akor Direct Jobs!\nWybierz swój język:",
        "main_menu": "🎯 Menu główne\nWybierz opcję poniżej:",
        "btn_jobs": "📋 Przeglądaj oferty",
        "btn_change_lang": "🌐 Zmień język",
        "lang_saved": "Ustawiono język polski 🇵🇱",
        "loading": "⏳ Ładowanie ofert...",
        "no_vacancies": "Obecnie brak dostępnych ofert pracy.",
        "salary": "Wynagrodzenie",
        "hours": "godz./tydzień",
        "housing": "Zakwaterowanie",
        "transport": "Transport",
        "yes": "Zapewnione",
        "no": "Brak",
        "btn_apply": "🌐 Aplikuj na stronie",
        "btn_back_menu": "🔙 Menu główne",
        "apply_msg": "🔗 Kliknij poniższy link, aby aplikować:"
    },
    "uk": {
        "welcome": "👋 Ласкаво просимо до Akor Direct Jobs!\nБудь ласка, оберіть мову:",
        "main_menu": "🎯 Головне меню\nОберіть дію нижче:",
        "btn_jobs": "📋 Переглянути вакансії",
        "btn_change_lang": "🌐 Змінити мову",
        "lang_saved": "Встановлено українську мову 🇺🇦",
        "loading": "⏳ Завантаження вакансій...",
        "no_vacancies": "Наразі вакансій не знайдено.",
        "salary": "Зарплата",
        "hours": "год/тиждень",
        "housing": "Проживання",
        "transport": "Транспорт",
        "yes": "Надається",
        "no": "Не надається",
        "btn_apply": "🌐 Відгукнутися на сайті",
        "btn_back_menu": "🔙 Головне меню",
        "apply_msg": "🔗 Перейдіть за посиланням, щоб подати заявку:"
    },
    "ru": {
        "welcome": "👋 Добро пожаловать в Akor Direct Jobs!\nПожалуйста, выберите язык:",
        "main_menu": "🎯 Главное меню\nВыберите действие ниже:",
        "btn_jobs": "📋 Посмотреть вакансии",
        "btn_change_lang": "🌐 Сменить язык",
        "lang_saved": "Выбран русский язык 🇷🇺",
        "loading": "⏳ Загружаю вакансии...",
        "no_vacancies": "К сожалению, сейчас нет доступных вакансий.",
        "salary": "Зарплата",
        "hours": "ч/неделю",
        "housing": "Жилье",
        "transport": "Транспорт",
        "yes": "Предоставляется",
        "no": "Нет",
        "btn_apply": "🌐 Откликнуться на сайте",
        "btn_back_menu": "🔙 Главное меню",
        "apply_msg": "🔗 Перейдите по ссылке, чтобы отправить заявку:"
    }
}


# --- Вспомогательные функции API ---

async def fetch_vacancies(locale: str):
    """Получение вакансий с бэкенда"""
    url = f"{API_BASE_URL}/vacancies?locale={locale}&pageSize=50"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=10) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("items", [])
    except Exception as e:
        print(f"Ошибка запроса вакансий: {e}")
    return []


async def record_transition(vacancy_id: str):
    """Отправка отметки об уникальном переходе"""
    url = f"{API_BASE_URL}/vacancy-unique-transitions"
    payload = {"vacancyId": vacancy_id}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=5) as resp:
                print(f"Отметка перехода для {vacancy_id}: статус {resp.status}")
    except Exception as e:
        print(f"Ошибка трекинга: {e}")


# --- Формирование карточки и клавиатуры ---

def format_vacancy_text(vac: dict, lang: str) -> str:
    t = TEXTS.get(lang, TEXTS["en"])
    title = vac.get("title", "Job")
    company = vac.get("company", "Company")
    city = vac.get("city", {}).get("name", "")
    country = vac.get("country", {}).get("name", "")
    location = f"{city}, {country}".strip(", ")
    salary = vac.get("salary", "—")
    hours = vac.get("workingHours", "—")

    housing = t["yes"] if vac.get("accommodationAvailable") else t["no"]
    transport = t["yes"] if vac.get("transportationAvailable") else t["no"]
    req = vac.get("requirements", "")

    text = (
        f"💼 <b>{title}</b>\n"
        f"🏢 <i>{company}</i>\n"
        f"📍 {location}\n\n"
        f"💶 <b>{t['salary']}:</b> €{salary} ({hours} {t['hours']})\n"
        f"🏠 <b>{t['housing']}:</b> {housing} | 🚗 <b>{t['transport']}:</b> {transport}\n\n"
        f"📝 <b>Требования / Info:</b>\n{req[:300]}..."
    )
    return text


def get_vacancy_keyboard(index: int, total: int, vac_id: str, lang: str):
    t = TEXTS.get(lang, TEXTS["en"])

    nav_buttons = []
    # Кнопка «Назад»
    if index > 0:
        nav_buttons.append(InlineKeyboardButton(text="⬅️", callback_data=f"nav_{index - 1}"))

    # Индикатор номера
    nav_buttons.append(InlineKeyboardButton(text=f"📄 {index + 1} / {total}", callback_data="noop"))

    # Кнопка «Вперёд»
    if index < total - 1:
        nav_buttons.append(InlineKeyboardButton(text="➡️", callback_data=f"nav_{index + 1}"))

    keyboard = [
        nav_buttons,
        [InlineKeyboardButton(text=t["btn_apply"], callback_data=f"apply_{vac_id}")],
        [InlineKeyboardButton(text=t["btn_back_menu"], callback_data="back_to_menu")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_language_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🇬🇧 English", callback_data="lang_en"),
         InlineKeyboardButton(text="🇳🇱 Nederlands", callback_data="lang_nl")],
        [InlineKeyboardButton(text="🇵🇱 Polski", callback_data="lang_pl"),
         InlineKeyboardButton(text="🇺🇦 Українська", callback_data="lang_uk")],
        [InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang_ru")]
    ])


def get_main_menu(lang: str):
    t = TEXTS.get(lang, TEXTS["en"])
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t["btn_jobs"], callback_data="show_vacancies")],
        [InlineKeyboardButton(text=t["btn_change_lang"], callback_data="open_lang_select")]
    ])


# --- Обработчики Telegram ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "👋 Welcome / Welkom / Witamy / Ласкаво просимо / Добро пожаловать!\n\n"
        "Please select your language / Wybierz język:",
        reply_markup=get_language_keyboard()
    )


@dp.callback_query(F.data.startswith("lang_"))
async def process_language_choice(callback: types.CallbackQuery):
    lang_code = callback.data.split("_")[1]
    user_languages[callback.from_user.id] = lang_code

    t = TEXTS.get(lang_code, TEXTS["en"])
    await callback.answer(t["lang_saved"])

    # Если сообщение было фото, удаляем и шлем текстовое меню
    if callback.message.photo:
        await callback.message.delete()
        await callback.message.answer(t["main_menu"], reply_markup=get_main_menu(lang_code))
    else:
        await callback.message.edit_text(t["main_menu"], reply_markup=get_main_menu(lang_code))


@dp.callback_query(F.data == "open_lang_select")
async def process_change_lang(callback: types.CallbackQuery):
    await callback.answer()
    if callback.message.photo:
        await callback.message.delete()
        await callback.message.answer(
            "Please select your language / Wybierz język:",
            reply_markup=get_language_keyboard()
        )
    else:
        await callback.message.edit_text(
            "Please select your language / Wybierz język:",
            reply_markup=get_language_keyboard()
        )


@dp.callback_query(F.data == "back_to_menu")
async def process_back_menu(callback: types.CallbackQuery):
    await callback.answer()
    user_id = callback.from_user.id
    lang = user_languages.get(user_id, "en")
    t = TEXTS.get(lang, TEXTS["en"])

    await callback.message.delete()
    await callback.message.answer(t["main_menu"], reply_markup=get_main_menu(lang))


@dp.callback_query(F.data == "show_vacancies")
async def process_show_vacancies(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    lang = user_languages.get(user_id, "en")
    t = TEXTS.get(lang, TEXTS["en"])

    await callback.answer(t["loading"])
    vacancies = await fetch_vacancies(lang)

    if not vacancies:
        await callback.message.answer(t["no_vacancies"])
        return

    user_vacancies[user_id] = vacancies
    user_page_index[user_id] = 0

    vac = vacancies[0]
    text = format_vacancy_text(vac, lang)
    kb = get_vacancy_keyboard(0, len(vacancies), vac["id"], lang)
    photo_url = vac.get("photo") or DEFAULT_PHOTO

    await callback.message.delete()
    try:
        await callback.message.answer_photo(photo=photo_url, caption=text, parse_mode="HTML", reply_markup=kb)
    except Exception:
        # Если фото битое, отправляем с дефолтной картинкой
        await callback.message.answer_photo(photo=DEFAULT_PHOTO, caption=text, parse_mode="HTML", reply_markup=kb)


@dp.callback_query(F.data.startswith("nav_"))
async def process_navigation(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    lang = user_languages.get(user_id, "en")
    index = int(callback.data.split("_")[1])

    vacancies = user_vacancies.get(user_id, [])
    if not vacancies or index >= len(vacancies) or index < 0:
        await callback.answer()
        return

    user_page_index[user_id] = index
    vac = vacancies[index]
    text = format_vacancy_text(vac, lang)
    kb = get_vacancy_keyboard(index, len(vacancies), vac["id"], lang)
    photo_url = vac.get("photo") or DEFAULT_PHOTO

    await callback.answer()
    try:
        await callback.message.edit_media(
            media=InputMediaPhoto(media=photo_url, caption=text, parse_mode="HTML"),
            reply_markup=kb
        )
    except Exception:
        # Если фото не поменялось или Telegram выдал ошибку, просто обновляем подпись
        try:
            await callback.message.edit_caption(caption=text, parse_mode="HTML", reply_markup=kb)
        except Exception:
            pass


@dp.callback_query(F.data.startswith("apply_"))
async def process_apply(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    lang = user_languages.get(user_id, "en")
    t = TEXTS.get(lang, TEXTS["en"])
    vac_id = callback.data.split("_")[1]

    # 1. Отправляем фоновый трекинг на сервер бэкенда!
    asyncio.create_task(record_transition(vac_id))

    # 2. Ищем вакансию, чтобы отдать ссылку на сайт
    vacancies = user_vacancies.get(user_id, [])
    vac = next((v for v in vacancies if v["id"] == vac_id), None)

    # Формируем прямую ссылку на сайт job.akordirect.com
    site_url = f"https://job.akordirect.com/{lang}/vacancies"
    if vac and vac.get("url") and vac.get("url") != "https://example.com":
        site_url = vac.get("url")

    await callback.answer("Переход зафиксирован! ✅")

    apply_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👉 Перейти к вакансии", url=site_url)]
    ])
    await callback.message.answer(f"{t['apply_msg']}\n{site_url}", reply_markup=apply_kb)


@dp.callback_query(F.data == "noop")
async def process_noop(callback: types.CallbackQuery):
    await callback.answer()


async def main():
    print("🚀 Бот обновлен и запущен...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())