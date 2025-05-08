import streamlit as st
import pandas as pd
import requests
import aiohttp
import asyncio
import time
from bs4 import BeautifulSoup
from datetime import datetime, date, timedelta

st.set_page_config(page_title="CS Quality Checker", layout="wide")
st.title("📥 Analiza OUTBOUND wiadomości wybranych agentów")

# --- Sidebar: API keys i filtr dat ---
st.sidebar.header("🔑 Konfiguracja API")
front_token = st.sidebar.text_input("Front API Token", type="password")
openai_key  = st.sidebar.text_input("OpenAI API Key",   type="password")

# filtr dat (lokalnie)
today = date.today()
seven_days_ago = today - timedelta(days=7)
date_from, date_to = st.sidebar.date_input(
    "📆 Zakres dat",
    value=[seven_days_ago, today],
    min_value=date(2020,1,1),
    max_value=today
)

if not front_token or not openai_key:
    st.sidebar.warning("Podaj oba klucze API.")
    st.stop()
if date_from > date_to:
    st.sidebar.error("Data OD nie może być późniejsza niż DO.")
    st.stop()

# --- Stałe inboxy i dozwolone agent IDs ---
INBOX_IDS = ["inb_a3xxy","inb_d2uom","inb_d2xee"]
ALLOWED_IDS = {
    "tea_a2k46","tea_cj1ue","tea_cocnq","tea_cs6hi","tea_gs47r",
    "tea_h7x3r","tea_hjadz","tea_hm6zb","tea_hn7h3","tea_hn7iv",
    "tea_hnytz","tea_hnyvr","tea_97fh2"
}

st.sidebar.markdown("**Inboxy:**")
st.sidebar.write("- Customer Service (`inb_a3xxy`)")
st.sidebar.write("- Chat Airbnb – New (`inb_d2uom`)")
st.sidebar.write("- Chat Booking – New (`inb_d2xee`)")

# --- Bezpieczne GET z obsługą błędów ---
def safe_get(url, headers, params=None):
    try:
        r = requests.get(url, headers=headers, params=params, timeout=15)
        r.raise_for_status()
        return r.json(), None
    except Exception as e:
        msg = str(e)
        try:
            msg += f" | {r.status_code} {r.text}"
        except:
            pass
        return None, msg

# --- Zbieranie danych ---
def collect_data(token, inbox_ids, progress_bar):
    headers = {"Authorization": f"Bearer {token}"}
    records = []
    total = len(inbox_ids)

    for idx, inbox in enumerate(inbox_ids, start=1):
        # pobranie listy konwersacji
        url_conv = "https://api2.frontapp.com/conversations"
        params   = {"inbox_id": inbox, "page_size": 100}
        convs = []
        while True:
            js, err = safe_get(url_conv, headers, params)
            if err:
                st.error(f"Błąd pobierania konwersacji `{inbox}`: {err}")
                break
            convs.extend(js.get("_results", []))
            cursor = js.get("_cursor")
            if not cursor:
                break
            params["cursor"] = cursor

        # pobranie wiadomości w każdej konwersacji
        for conv in convs:
            cid = conv.get("id")
            url_msg = f"https://api2.frontapp.com/conversations/{cid}/messages"
            js2, err2 = safe_get(url_msg, headers)
            if err2:
                st.error(f"Błąd pobierania wiadomości `{cid}`: {err2}")
                continue
            for m in js2.get("_results", []):
                if m.get("is_inbound", True):
                    continue
                created = m.get("created_at")
                dt = pd.to_datetime(created, utc=True) if created else None

                raw = m.get("author") or {}
                author_id = raw.get("id") if isinstance(raw, dict) else None
                if author_id not in ALLOWED_IDS:
                    continue

                text = BeautifulSoup(m.get("body",""), "html.parser").get_text("\n")
                if isinstance(raw, dict):
                    name   = (raw.get("first_name","") + " " + raw.get("last_name","")).strip()
                    handle = raw.get("username") or raw.get("handle") or ""
                    author = f"{name} ({handle})" if handle else name
                else:
                    author = str(raw)

                records.append({
                    "Created At": dt,
                    "Created_date": dt.date() if dt is not None else None,
                    "Inbox ID":   inbox,
                    "Message ID": m.get("id",""),
                    "Author ID":  author_id,
                    "Author":     author,
                    "Extract":    text
                })

        progress_bar.progress(idx/total)

    return pd.DataFrame(records)

# --- Pasek postępu do pobierania ---
fetch_prog = st.sidebar.progress(0.0)

if st.button("▶️ Pobierz i analizuj"):
    with st.spinner("⏳ Pobieram dane…"):
        df = collect_data(front_token, INBOX_IDS, fetch_prog)

    if df.empty:
        st.warning("❗ Brak wiadomości od wybranych agentów.")
        st.stop()

    # lokalne filtrowanie po dacie
    df = df.dropna(subset=["Created_date"])
    df = df[(df["Created_date"] >= date_from) & (df["Created_date"] <= date_to)]
    if df.empty:
        st.warning(f"❗ Brak wiadomości w okresie {date_from} – {date_to}.")
        st.stop()

    st.success(f"Pobrano {len(df)} wiadomości w wybranym okresie.")
    st.dataframe(df[["Created_date","Author","Extract"]].head(10), use_container_width=True)

    # --- Analiza GPT ---
    API_URL = "https://api.openai.com/v1/chat/completions"
    HEADERS = {"Authorization":f"Bearer {openai_key}", "Content-Type":"application/json"}
    SYSTEM = (
        "Jesteś Menedżerem CS w Bookinghost. Oceń jakość wiadomości agentów "
        "w skali 1–5 (empatia, poprawność, procedury, ton). "
        "Odpowiedz formatem:\nOcena: X/5\nUzasadnienie: • pkt1\n• pkt2"
    )

    async def analyze_one(sess, rec):
        payload = {
            "model":"gpt-3.5-turbo",
            "messages":[{"role":"system","content":SYSTEM},
                        {"role":"user","content":rec["Extract"]}],
            "temperature":0.3,"max_tokens":200
        }
        async with sess.post(API_URL, headers=HEADERS, json=payload) as r:
            js = await r.json()
        if js.get("error"):
            return f"❌ {js['error']['message']}"
        ch = js.get("choices") or []
        return ch[0]["message"]["content"].strip() if ch else "❌ no choices"

    async def run_all(recs, prog, stat):
        out=[]; batch=20
        async with aiohttp.ClientSession() as sess:
            total = len(recs)
            for i in range(0, total, batch):
                chunk = recs[i:i+batch]
                res = await asyncio.gather(*[analyze_one(sess,r) for r in chunk])
                out.extend(res)
                done = min(i+batch, total)
                prog.progress(done/total)
                stat.text(f"Analizowano {done}/{total}")
        return out

    recs = df.to_dict("records")
    analyze_prog = st.progress(0.0)
    analyze_stat = st.empty()
    start = time.time()

    with st.spinner("⚙️ Analiza…"):
        df["Feedback"] = asyncio.run(run_all(recs, analyze_prog, analyze_stat))

    st.success(f"✅ Analiza zakończona w {time.time()-start:.1f}s")

    # parsowanie i raport
    def parse_score(txt):
        for l in txt.splitlines():
            if l.lower().startswith("ocena"):
                try: return float(l.split(":")[1].split("/")[0])
                except: pass
        return None

    df["Score"] = df["Feedback"].map(parse_score)

    st.header("📈 Podsumowanie")
    st.metric("Średnia ocena", f"{df['Score'].mean():.2f}/5")
    st.metric("Liczba wiadomości", len(df))

    st.header("👤 Raport agentów")
    report = (
        df.groupby("Author")
          .agg(Średnia=("Score","mean"), Liczba=("Score","count"))
          .round(2).reset_index()
    )
    st.dataframe(report, use_container_width=True)

    st.header("📥 Pobierz CSV")
    csv = df.to_csv(index=False, sep=";").encode("utf-8")
    st.download_button("⬇ CSV", data=csv, file_name="report.csv", mime="text/csv")
