import streamlit as st
import pandas as pd
import requests
import aiohttp
import asyncio
import time
from bs4 import BeautifulSoup
from datetime import datetime, date

st.set_page_config(page_title="CS Quality Checker", layout="wide")
st.title("📥 Analiza OUTBOUND wiadomości wybranych agentów")

# --- Sidebar: klucze API i filtr dat ---
st.sidebar.header("🔑 Konfiguracja")
front_token = st.sidebar.text_input("Front API Token", type="password")
openai_key  = st.sidebar.text_input("OpenAI API Key",   type="password")

st.sidebar.markdown("📆 Filtr po dacie (lokalnie)")
# domyślnie ustawiamy ostatnie 7 dni
today = date.today()
default_from = today - pd.Timedelta(days=7)
date_from, date_to = st.sidebar.date_input("Zakres dat", [default_from, today])

if not front_token or not openai_key:
    st.sidebar.warning("Podaj oba klucze API.")
    st.stop()
if date_from > date_to:
    st.sidebar.error("Data od nie może być później niż data do.")
    st.stop()

# --- Stałe inboxy i dozwolone agent IDs ---
INBOX_IDS = ["inb_a3xxy","inb_d2uom","inb_d2xee"]
ALLOWED_IDS = {
    "tea_a2k46","tea_cj1ue","tea_cocnq","tea_cs6hi","tea_gs47r",
    "tea_h7x3r","tea_hjadz","tea_hm6zb","tea_hn7h3","tea_hn7iv",
    "tea_hnytz","tea_hnyvr","tea_97fh2"
}

st.sidebar.markdown("**Inboxy:**")
st.sidebar.write("- Customer Service: `inb_a3xxy`")
st.sidebar.write("- Chat Airbnb – New: `inb_d2uom`")
st.sidebar.write("- Chat Booking – New: `inb_d2xee`")

# --- Funkcje HTTP z obsługą błędów ---
def safe_get(url, headers, params=None):
    try:
        r = requests.get(url, headers=headers, params=params, timeout=15)
        r.raise_for_status()
        return r.json(), None
    except requests.exceptions.RequestException as e:
        msg = str(e)
        try:
            msg += f" | {r.status_code} {r.text}"
        except:
            pass
        return None, msg

# --- Zbieranie danych z konwersacji i wiadomości ---
def collect_data(token, inbox_ids, fetch_prog):
    headers = {"Authorization": f"Bearer {token}"}
    records = []
    total = len(inbox_ids)
    for idx, inbox in enumerate(inbox_ids, start=1):
        # pobieramy wszystkie konwersacje w inboxie
        url_c = "https://api2.frontapp.com/conversations"
        params = {"inbox_id": inbox, "page_size": 100}
        conversations = []
        while True:
            js, err = safe_get(url_c, headers, params)
            if err:
                st.error(f"Błąd pobierania konwersacji `{inbox}`: {err}")
                break
            conversations.extend(js.get("_results", []))
            if not js.get("_cursor"):
                break
            params["cursor"] = js["_cursor"]

        # dla każdej konwersacji pobieramy jej wiadomości
        for conv in conversations:
            cid = conv.get("id")
            url_m = f"https://api2.frontapp.com/conversations/{cid}/messages"
            js2, err2 = safe_get(url_m, headers)
            if err2:
                st.error(f"Błąd pobierania wiadomości `{cid}`: {err2}")
                continue
            for m in js2.get("_results", []):
                # outbound only
                if m.get("is_inbound", True):
                    continue
                # data utworzenia
                created = m.get("created_at")
                dt = pd.to_datetime(created, utc=True) if created else None
                # author
                raw = m.get("author") or {}
                author_id = raw.get("id") if isinstance(raw, dict) else None
                # filtr agentów
                if author_id not in ALLOWED_IDS:
                    continue
                # strip HTML body
                text = BeautifulSoup(m.get("body",""), "html.parser").get_text("\n")
                # czytelny Author
                if isinstance(raw, dict):
                    name   = (raw.get("first_name","") + " " + raw.get("last_name","")).strip()
                    handle = raw.get("username") or raw.get("handle") or ""
                    author = f"{name} ({handle})" if handle else name
                else:
                    author = str(raw)
                records.append({
                    "Created At": dt,
                    "Inbox ID":   inbox,
                    "Message ID": m.get("id",""),
                    "Author ID":  author_id,
                    "Author":     author,
                    "Extract":    text
                })

        fetch_prog.progress(idx/total)

    return pd.DataFrame(records)

# --- Główny przebieg ---
fetch_prog   = st.sidebar.progress(0.0)

if st.button("▶️ Pobierz i analizuj"):
    with st.spinner("⏳ Pobieram dane…"):
        df = collect_data(front_token, INBOX_IDS, fetch_prog)

    if df.empty:
        st.warning("❗ Brak wiadomości od wybranych agentów.")
        st.stop()

    # Konwersja Created At i filtrowanie po zakresie dat lokalnie
    df["Created At"] = pd.to_datetime(df["Created At"], utc=True)
    # konwertujemy date_from/do do Timestamp
    start_ts = pd.to_datetime(date_from).tz_localize("UTC")
    end_ts   = pd.to_datetime(date_to).tz_localize("UTC") + pd.Timedelta(days=1) - pd.Timedelta(microseconds=1)
    df = df[(df["Created At"] >= start_ts) & (df["Created At"] <= end_ts)]
    if df.empty:
        st.warning(f"❗ Brak wiadomości w okresie {date_from} – {date_to}.")
        st.stop()

    st.success(f"Pobrano {len(df)} wiadomości w wybranym okresie.")
    st.dataframe(df[["Created At","Author","Extract"]].head(10), use_container_width=True)

    # --- Analiza GPT ---
    API_URL = "https://api.openai.com/v1/chat/completions"
    HEADERS = {"Authorization":f"Bearer {openai_key}", "Content-Type":"application/json"}
    SYSTEM = (
        "Jesteś Menedżerem CS w Bookinghost i oceniasz jakość wiadomości agentów "
        "w skali 1–5. Uwzględnij empatię, poprawność, zgodność z procedurami i ton.\n"
        "Odpowiedz formatem:\nOcena: X/5\nUzasadnienie: • pkt1\n• pkt2"
    )

    async def analyze_one(sess, rec):
        payload = {"model":"gpt-3.5-turbo",
                   "messages":[{"role":"system","content":SYSTEM},
                               {"role":"user","content":rec["Extract"]}],
                   "temperature":0.3,"max_tokens":200}
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
                prog.progress(done/total); stat.text(f"Analizowano {done}/{total}")
        return out

    recs = df.to_dict("records")
    analyze_prog = st.progress(0.0)
    analyze_stat = st.empty()
    start = time.time()
    with st.spinner("⚙️ Analiza…"):
        df["Feedback"] = asyncio.run(run_all(recs, analyze_prog, analyze_stat))
    st.success(f"✅ Analiza zakończona w {time.time()-start:.1f}s")

    # Parsowanie i raport
    df["Score"] = df["Feedback"].map(lambda t: float(t.split()[1].split("/")[0]) if t.lower().startswith("ocena") else None)

    st.header("📈 Podsumowanie")
    st.metric("Średnia ocena", f"{df['Score'].mean():.2f}/5")
    st.metric("Licza wiadomości", len(df))

    st.header("👤 Raport agentów")
    report = df.groupby("Author").agg(Śr=("Score","mean"),Cnt=("Score","count")).round(2).reset_index()
    st.dataframe(report, use_container_width=True)

    st.header("📥 Pobierz CSV")
    csv = df.to_csv(index=False, sep=";").encode("utf-8")
    st.download_button("⬇ CSV", data=csv, file_name="report.csv", mime="text/csv")
