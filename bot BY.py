import os, sys, json, time
from datetime import datetime, timedelta, timezone
import requests
import anthropic

FINNHUB_KEY = os.environ["FINNHUB_KEY"]
TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
MODE = os.environ.get("MODE", "daily")  # daily | weekly | monthly
HISTORY_FILE = "history.json"
MODEL = "claude-sonnet-4-6"

# أخبار كتأثر على الذهب
KEYWORDS = [
    "gold", "xau", "bullion", "safe haven", "safe-haven",
    "fed ", "federal reserve", "interest rate", "rate cut", "rate hike",
    "inflation", "cpi", "dollar", "treasury yield", "powell",
    "central bank", "geopolitic", "recession",
]


def load_history():
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_history(h):
    cutoff = (datetime.now(timezone.utc) - timedelta(days=35)).timestamp()
    h = {k: v for k, v in h.items() if v["ts"] >= cutoff}
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(h, f, ensure_ascii=False, indent=1)
    return h


def fetch_news(history):
    r = requests.get(
        "https://finnhub.io/api/v1/news",
        params={"category": "general", "token": FINNHUB_KEY},
        timeout=30,
    )
    r.raise_for_status()
    added = 0
    for n in r.json():
        text = f"{n.get('headline','')} {n.get('summary','')}".lower()
        if not any(k in text for k in KEYWORDS):
            continue
        key = str(n["id"])
        if key not in history:
            history[key] = {
                "ts": n["datetime"],
                "headline": n.get("headline", ""),
                "summary": (n.get("summary") or "")[:300],
                "source": n.get("source", ""),
                "url": n.get("url", ""),
            }
            added += 1
    print(f"added {added} new items")
    return history


def pick(history, days):
    since = (datetime.now(timezone.utc) - timedelta(days=days)).timestamp()
    items = [v for v in history.values() if v["ts"] >= since]
    items.sort(key=lambda x: x["ts"], reverse=True)
    return items[:60]


PROMPTS = {
    "daily": (
        1,
        "ملخص يومي",
        "عطيني: 1) أهم 3 إلى 5 أخبار اليوم اللي كتأثر على الذهب (XAU/USD)، كل خبر فسطر وحدة "
        "مع شرح قصير علاش كيأثر. 2) فالأخير الاتجاه ديال اليوم.",
    ),
    "weekly": (
        7,
        "توقع الأسبوع",
        "حلل أخبار هاد الأسبوع وعطيني: 1) الأفكار الرئيسية اللي كتحرك الذهب (3 إلى 5 نقط). "
        "2) الحكم النهائي ديال الأسبوع.",
    ),
    "monthly": (
        30,
        "توقع الشهر",
        "حلل أخبار هاد الشهر وعطيني: 1) العوامل الكبرى اللي كتحرك الذهب (3 إلى 5 نقط). "
        "2) الحكم النهائي ديال الشهر.",
    ),
}


def analyze(items, mode):
    days, title, task = PROMPTS[mode]
    lines = "\n".join(
        f"- [{datetime.fromtimestamp(i['ts'], timezone.utc).strftime('%m-%d')}] "
        f"{i['headline']} :: {i['summary']}"
        for i in items
    )
    system = (
        "نتا محلل أخبار متخصص فالذهب (XAU/USD) فقط. كتجاوب بالدارجة المغربية بحروف عربية، "
        "قصير وواضح. غير الأخبار اللي عندها علاقة بالذهب (الفائدة، الدولار، التضخم، "
        "الجيوسياسة، البنوك المركزية...). ما تخترع حتى خبر ولا رقم ماشي فاللائحة. "
        "آخر سطر خاصو يكون بالضبط واحد من هاد الثلاثة:\n"
        "الاتجاه: 🟢 إيجابي\nالاتجاه: 🔴 سلبي\nالاتجاه: ⚪ محايد\n"
        "وتزيد جملة وحدة كتعلل الحكم. هادشي تحليل أخبار ماشي نصيحة مالية."
    )
    client = anthropic.Anthropic()
    msg = client.messages.create(
        model=MODEL,
        max_tokens=1000,
        system=system,
        messages=[{"role": "user", "content": f"{task}\n\nالأخبار:\n{lines}"}],
    )
    return title, msg.content[0].text.strip()


def send_telegram(text):
    text = text[:4000]
    r = requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        json={"chat_id": TELEGRAM_CHAT_ID, "text": text, "disable_web_page_preview": True},
        timeout=30,
    )
    r.raise_for_status()


def main():
    history = fetch_news(load_history())
    history = save_history(history)

    days = PROMPTS[MODE][0]
    items = pick(history, days)
    if not items:
        send_telegram("🥇 ما لقيت حتى خبر جديد مرتبط بالذهب دابا.")
        return

    title, body = analyze(items, MODE)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    send_telegram(f"🥇 الذهب | {title} ({today})\n\n{body}")


if __name__ == "__main__":
    main()
