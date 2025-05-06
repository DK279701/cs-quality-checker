import streamlit as st
import pandas as pd
import requests
import aiohttp
import asyncio
import time
from datetime import datetime
from dateutil.parser import parse as parse_date

st.set_page_config(page_title="CS Quality Checker – Bookinghost", layout="wide")
st.title("📥 Pobieranie i analiza wiadomości z Front (bez filtra API)")

# ——— SIDEBAR: FRONT API —————————————————————————
st.sidebar.header("🔗 Ustawienia Front API")
api_token = st.sidebar.text_input("Front API Token", type="password")
inbox_id   = st.sidebar.text_input("Inbox ID (opcjonalnie)")

if not api_token:
    st.sidebar.warning("🔑 Podaj Front API Token")
    st.stop()

# ——— POBIERANIE WSZYSTKICH WIADOMOŚCI —————————————————
@st.cache_data(ttl=300)
def fetch_all_messages(token, inbox):
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    params = {"inbox_id": inbox, "page_size": 100} if inbox else {"page_size":100}
    url = "https://api2.frontapp.com/conversations"

    # 1) fetch conversations (paginated)
    convs = []
    while True:
        r = requests.get(url, headers=headers, params=params)
        r.raise_for_status()
        data = r.json()
        convs.extend(data.get("_results", []))
        cursor = data.get("_cursor")
        if not cursor:
            break
        params["cursor"] = cursor

    # 2) fetch messages for each conversation
    records = []
    for c in convs:
        conv_id = c.get("id")
        r2 = requests.get(f"{url}/{conv_id}/messages", headers=headers)
        r2.raise_for_status()
        for m in r2.json().get("_results", []):
            author = m.get("author", {}).get("handle", "Unknown")
            body   = m.get("body", "")
            ct_raw = m.get("created_at", "")
            try:
                created = parse_date(ct_raw) if ct_raw else None
            except:
                created = None
            records.append({
                "Conversation ID": conv_id,
                "Message ID":      m.get("id", ""),
                "Author":          author,
                "Extract":         body,
                "Created At":      created
            })
    return pd.DataFrame(records)

if st.sidebar.button("▶️ POBIERZ WSZYSTKIE WIADOMOŚCI"):
    with st.spinner("⏳ Pobieranie…"):
        df = fetch_all_messages(api_token, inbox_id or None)
    st.success(f"Pobrano {len(df)} wiadomości (bez filtra).")
    st.write("#### Pierwsze 10 rekordów z kolumną `Created At`")
    st.dataframe(df.head(10))

    # ——— WYBÓR ZAKRESU DAT ——————————————————————
    st.sidebar.header("📅 Filtr po dacie wiadomości")
    min_date = df["Created At"].min().date()
    max_date = df["Created At"].max().date()
    start_date = st.sidebar.date_input("Start", value=min_date, min_value=min_date, max_value=max_date)
    end_date   = st.sidebar.date_input("Koniec", value=max_date, min_value=min_date, max_value=max_date)

    mask = df["Created At"].between(
        datetime.combine(start_date, datetime.min.time()),
        datetime.combine(end_date,   datetime.max.time())
    )
    filtered = df[mask].reset_index(drop=True)
    st.write(f"Po filtrze: **{len(filtered)}** wiadomości z zakresu {start_date} ↔ {end_date}")
    st.dataframe(filtered.head(10))

    # ——— USTAWIENIA OPENAI ————————————————————
    openai_key = st.sidebar.text_input("🗝️ OpenAI API Key", type="password")
    if not openai_key:
        st.sidebar.warning("🗝️ Podaj OpenAI API Key")
        st.stop()

    API_URL = "https://api.openai.com/v1/chat/completions"
    HEADERS = {
        "Authorization": f"Bearer {openai_key}",
        "Content-Type":  "application/json"
    }
    SYSTEM_PROMPT = (
        "Jesteś Menedżerem Customer Service w Bookinghost i oceniasz jakość wiadomości agentów "
        "w skali 1–5.\nWeź pod uwagę:\n"
        "• empatię i uprzejmość\n"
        "• poprawność językową\n"
        "• zgodność z procedurami\n"
        "• ton (ciepły, profesjonalny)\n\n"
        "Odpowiedz w formacie:\n"
        "Ocena: X/5\n"
        "Uzasadnienie: • punkt 1\n• punkt 2"
    )

    # ——— ASYNC BATCH ANALYSIS ————————————————————
    async def analyze_one(session, rec):
        payload = {
            "model": "gpt-3.5-turbo",
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": rec["Extract"]}
            ],
            "temperature": 0.3,
            "max_tokens": 200
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(API_URL, headers=HEADERS, json=payload) as resp:
                js = await resp.json()
                return js["choices"][0]["message"]["content"].strip()

    async def run_all(recs, prog, stat):
        out = []
        batch = 20
        async with aiohttp.ClientSession() as sess:
            for i in range(0, len(recs), batch):
                chunk = recs[i : i + batch]
                tasks = [analyze_one(sess, r) for r in chunk]
                res = await asyncio.gather(*tasks)
                out.extend(res)
                done = min(i + batch, len(recs))
                prog.progress(done / len(recs))
                stat.text(f"Przetworzono: {done}/{len(recs)}")
        return out

    recs = filtered.to_dict(orient="records")
    prog = st.progress(0.0)
    stat = st.empty()
    start = time.time()
    with st.spinner("⚙️ Analiza…"):
        feedbacks = asyncio.run(run_all(recs, prog, stat))
    st.success(f"✅ Zakończono w {time.time() - start:.1f}s")

    filtered["Feedback"] = feedbacks
    def parse_score(txt):
        for l in txt.splitlines():
            if l.lower().startswith("ocena"):
                try:
                    return float(l.split(":")[1].split("/")[0].strip())
                except:
                    pass
        return None
    filtered["Score"] = filtered["Feedback"].map(parse_score)

    st.header("📈 Podsumowanie zespołu")
    st.metric("Średnia ocena", f"{filtered['Score'].mean():.2f}/5")
    st.metric("Liczba wiadomości", len(filtered))

    st.header("👤 Raport agentów")
    agg = (
        filtered
        .groupby("Author")
        .agg(Średnia_ocena=("Score","mean"), Liczba=("Score","count"))
        .round(2)
        .reset_index()
    )
    st.dataframe(agg, use_container_width=True)

    st.header("📥 Pobierz pełen raport")
    csv = filtered.to_csv(index=False, sep=";").encode("utf-8")
    st.download_button("⬇️ CSV", data=csv, file_name="raport.csv", mime="text/csv")
