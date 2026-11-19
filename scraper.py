import asyncio
import json
import os
import re
import aiohttp
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "https://werkenbijvankeulen.com/vacature/"
JOB_SERVICE_URL = os.getenv("JOB_SERVICE_URL", "https://server-node-js-akor.up.railway.app").rstrip("/")
IMPORT_API_URL = f"{JOB_SERVICE_URL}/api/job-agency/admin/vacancies/import"
IMPORT_API_KEY = os.getenv("IMPORT_API_KEY", "")
SCRAPE_INTERVAL_SECONDS = int(os.getenv("SCRAPE_INTERVAL_SECONDS", "21600"))

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "nl,en;q=0.9",
}

# GeoNames IDs для городов Van Keulen
CITY_CODES = {
    "tynaarlo": "2746156",
    "nijverdal": "2750111",
}
DEFAULT_CITY_CODE = "2750111"


def extract_number(text: str, pattern: str) -> int:
    """Извлекает целое число по регулярному выражению (например, часы или зарплату)."""
    match = re.search(pattern, text, re.IGNORECASE)
    if not match:
        return 0
    raw = match.group(1).replace(".", "").replace(",", ".")
    try:
        return int(float(raw))
    except ValueError:
        return 0


def parse_sections(soup: BeautifulSoup) -> dict:
    """Разбирает текст страницы по заголовкам H2/H3 на блоки."""
    sections = {
        "responsibilities": [],
        "requirements": [],
        "benefits": [],
    }
    current_key = None

    # Ищем основной контент страницы
    main_content = soup.find("main") or soup.body
    if not main_content:
        return sections

    for el in main_content.find_all(["h2", "h3", "p", "li"]):
        tag = el.name
        text = el.get_text(" ", strip=True)
        if not text:
            continue

        if tag in ("h2", "h3"):
            low = text.lower()
            if "functie" in low or "wat ga je doen" in low:
                current_key = "responsibilities"
            elif "vragen" in low or "profiel" in low or "wie ben jij" in low:
                current_key = "requirements"
            elif "bieden" in low or "arbeidsvoorwaarden" in low:
                current_key = "benefits"
            else:
                # Дошли до формы отклика ("Solliciteer") или похожих вакансий — останавливаем сбор
                if any(stop in low for stop in ("solliciteer", "bekijk ook", "direct onze", "vragen?")):
                    current_key = None
        elif current_key and tag in ("p", "li"):
            # Избегаем дублирования текста, если <p> вложен внутрь <li>
            if tag == "p" and el.find_parent("li"):
                continue
            sections[current_key].append(text)

    return {k: "\n".join(v).strip() for k, v in sections.items()}


async def parse_single_vacancy(session: aiohttp.ClientSession, url: str) -> dict | None:
    """Скачивает и парсит одну страницу вакансии в формат API бэкенда."""
    # Пропускаем страницу свободной заявки (не конкретная вакансия)
    if "open-sollicitatie" in url.lower():
        print(f" Пропускаем страницу свободной заявки: {url}")
        return None

    async with session.get(url, timeout=aiohttp.ClientTimeout(total=20)) as resp:
        if resp.status != 200:
            print(f" Ошибка загрузки {url}: статус {resp.status}")
            return None
        html = await resp.text()

    soup = BeautifulSoup(html, "html.parser")

    # 1. Стабильный externalId из класса body (postid-XXXX)
    external_id = None
    if soup.body:
        for cls in soup.body.get("class", []):
            if cls.startswith("postid-"):
                external_id = cls.replace("postid-", "")
                break
    if not external_id:
        # Резервный вариант — слаг из URL
        external_id = url.rstrip("/").split("/")[-1]

    # 2. Заголовок
    h1 = soup.find("h1")
    title = h1.get_text(strip=True) if h1 else ""
    if not title:
        print(f" Не найден заголовок H1 на {url}")
        return None

    # 3. Разделы текста (plain text без HTML)
    sections = parse_sections(soup)
    responsibilities = sections["responsibilities"]
    requirements = sections["requirements"]
    benefits = sections["benefits"]

    # Если страница пустая по основным разделам — пропускаем
    if len(responsibilities) < 20 and len(requirements) < 20:
        print(f" Пропускаем {url} — недостаточно текстового описания вакансии.")
        return None

    # Гарантируем полноценные предложения на нидерландском для DeepL (требование API)
    if len(responsibilities) < 20:
        responsibilities = f"Je gaat aan de slag in de functie van {title} bij Van Keulen Interieurbouw."
    if len(requirements) < 20:
        requirements = "Je bent gemotiveerd, werkt nauwkeurig en hebt affiniteit met techniek of interieurbouw."
    if len(benefits) < 20:
        benefits = "Wij bieden een goed salaris volgens cao, reiskostenvergoeding en een prettige werksfeer."

    # 4. Город (GeoNames code)
    full_text_lower = soup.get_text(" ", strip=True).lower()
    city_code = DEFAULT_CITY_CODE
    for city_name, code in CITY_CODES.items():
        if city_name in url.lower() or city_name in full_text_lower:
            city_code = code
            break

    # 5. Зарплата и рабочие часы (ищем в тексте условий/всей страницы)
    # Ищем формат вроде "€ 2.500" или "€ 2500"
    salary = extract_number(benefits + " " + full_text_lower, r"€\s*(\d[\d\.,]{2,7})")
    # Ищем формат вроде "40 uur" или "32 - 40 uur" (берем первое число)
    working_hours = extract_number(benefits + " " + full_text_lower, r"\b(\d{1,2})\s*uur\b")

    # 6. Фотография (og:image)
    og_img = soup.find("meta", property="og:image")
    photo_url = og_img["content"].strip() if og_img and og_img.get("content") else None

    vacancy_payload = {
        "externalId": str(external_id),
        "url": url,
        "title": title,
        "company": "Van Keulen Interieurbouw",
        "countryCode": "NL",
        "cityCode": city_code,
        "salary": salary,
        "workingHours": working_hours,
        "responsibilities": responsibilities,
        "requirements": requirements,
        "benefits": benefits,
        "accommodationAvailable": False,
        "transportationAvailable": False,
    }

    if photo_url and photo_url.startswith("https://"):
        vacancy_payload["photoUrl"] = photo_url

    return vacancy_payload


async def scrape_all_vacancies() -> list[dict]:
    """Собирает все актуальные вакансии с сайта Van Keulen."""
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        async with session.get(BASE_URL, timeout=aiohttp.ClientTimeout(total=20)) as resp:
            if resp.status != 200:
                print(f" Ошибка загрузки каталога: {resp.status}")
                return []
            html = await resp.text()

        soup = BeautifulSoup(html, "html.parser")
        links = sorted({
            a["href"]
            for a in soup.find_all("a", href=True)
            if "werkenbijvankeulen.com/vacature/" in a["href"]
            and a["href"].rstrip("/") != BASE_URL.rstrip("/")
        })

        print(f" Найдено ссылок в каталоге: {len(links)}")
        vacancies = []
        for link in links:
            item = await parse_single_vacancy(session, link)
            if item:
                vacancies.append(item)
            await asyncio.sleep(0.5)  # Вежливая пауза между запросами

        return vacancies


async def send_to_backend(vacancies: list[dict]):
    """Отправляет собранные вакансии на бэкенд пачками до 30 штук."""
    if not IMPORT_API_KEY:
        print(" Ошибка: IMPORT_API_KEY не задан в .env!")
        return

    headers = {
        "X-Api-Key": IMPORT_API_KEY,
        "Content-Type": "application/json",
    }

    # Разбиваем на батчи по 30 штук (требование API)
    batch_size = 30
    async with aiohttp.ClientSession() as session:
        for i in range(0, len(vacancies), batch_size):
            batch = vacancies[i:i + batch_size]
            payload = {
                "source": "van_keulen",
                "vacancies": batch,
            }
            print(f" Отправка батча ({len(batch)} вакансий) на {IMPORT_API_URL}...")
            async with session.post(
                IMPORT_API_URL,
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=90),  # Таймаут >= 60s по документации
            ) as resp:
                status = resp.status
                body = await resp.text()
                print(f" Ответ сервера (HTTP {status}):\n{body}")


async def run_sync(dry_run: bool = False):
    vacancies = await scrape_all_vacancies()
    print(f"\n Успешно собрано вакансий: {len(vacancies)}")

    if dry_run:
        print("\n--- ПРЕДПРОСМОТР ПЕРВОЙ ВАКАНСИИ (DRY RUN) ---")
        if vacancies:
            print(json.dumps(vacancies[0], ensure_ascii=False, indent=2))
        print("\n--- СВОДКА ПО ВСЕМ СОБРАННЫМ ВАКАНСИЯМ ---")
        for v in vacancies:
            print(
                f"ID: {v['externalId']} | {v['title']} | "
                f"City: {v['cityCode']} | Salary: EUR {v['salary']} | Hours: {v['workingHours']}"
            )
    else:
        if vacancies:
            await send_to_backend(vacancies)

async def run_scheduler(dry_run: bool = False):
    while True:
        print("\nЗапуск цикла синхронизации вакансий...")
        try:
            await run_sync(dry_run=dry_run)
        except Exception as e:
            print(f"Сбой во время цикла синхронизации: {e}")

        print(f"Следующая проверка через {SCRAPE_INTERVAL_SECONDS} сек.")
        await asyncio.sleep(SCRAPE_INTERVAL_SECONDS)


if __name__ == "__main__":
    run_mode = os.getenv("SCRAPER_MODE", "loop").lower()
    if run_mode == "once":
        asyncio.run(run_sync(dry_run=False))
    else:
        asyncio.run(run_scheduler(dry_run=False))