import streamlit as st
import pandas as pd
import requests
import aiohttp
import asyncio
import time
from datetime import datetime, time as dtime

st.set_page_config(page_title="CS Quality Checker – Bookinghost", layout="wide")
st.title("📥 Pobieranie i analiza wiadomości z Front")

# ——— SIDEBAR: FRONT API & DATE RANGE —————————————————
st.sidebar.header("🔗 Ustawienia Front API")
api_token = st.sidebar.text_input("Front API Token", type="password")
inbox_id   = st.sidebar.text_input("Inbox ID (opcjonalnie)")

st.sidebar.header("📅 Zakres dat")
start_date = st.sidebar.date_input("Start", value=datetime.utcnow().date() - pd.Timedelta(days=7))
end_date   = st.sidebar.date_input("Koniec", value=datetime.utcnow().date())
# formatuj do ISO
since = datetime.combine(start_date, dtime.min).isoformat() + "Z"
until = datetime.combine(end_date, dtime.max).isoformat() + "Z"

# ——— FETCHING WIADOMOŚCI Z FRONT ————————————————————
@st.cache_data(ttl=300)
def fetch_front(token, inbox=None):
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    params = {"inbox_id": inbox} if inbox else {}
    resp = requests.get("https://api2.frontapp.com/conversations", headers=headers, params=params)
    resp.raise_for_status()
    convs = resp.json()["_results"]
    msgs = []
    for c in convs:
        r2 = requests.get(f"https://api2.frontapp.com/conversations/{c['id']}/messages", headers=headers)
        r2.raise_for_status()
        for m in r2.json()["_results"]:
            ct = m.get("created_at")
            if ct and since <= ct <= until:
                msgs.append({
                    "Conversation ID": c["id"],
                    "Message ID": m["id"],
                    "Author": m["author"]["handle"],
                    "Extract": m["body"],
                    "Created At": ct
                })
    return pd.DataFrame(msgs)

if not api_token:
    st.warning("Wprowadź Front API Token w panelu bocznym.")
    st.stop()

if st.sidebar.button("▶️ Pobierz wiadomości"):
    with st.spinner("Pobieranie…"):
        df = fetch_front(api_token, inbox_id or None)
    st.success(f"Pobrano {len(df)} wiadomości ({since} ↔ {until})")
    st.dataframe(df)

    # ——— ANALIZA BATCH + RAG ————————————————————
    SYSTEM_PROMPT = (
        "Jesteś Managerem Customer Service w Bookinghost i oceniasz jakość odpowiedzi agentów "
        "w skali 1–5. Weź pod uwagę:\n"
        "• empatię i uprzejmość\n"
        "• poprawność językową\n"
        "• zgodność z procedurami\n"
        "• ton (ciepły, profesjonalny)\n\n"
        "Odpowiedz w formacie:\n"
        "Ocena: X/5\n"
        "Uzasadnienie: • punkt 1\n• punkt 2"
    )
    API_URL = "https://api.openai.com/v1/chat/completions"
    HEADERS = {"Authorization": f"Bearer {st.text_input('🔑 Wklej OpenAI API Key', type='password')}"}

    async def analyze_one(session, rec):
        payload = {
            "model": "gpt-3.5-turbo",
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": rec["Extract"]},
            ],
            "temperature": 0.3,
            "max_tokens": 200
        }
        async with session.post(API_URL, headers=HEADERS, json=payload) as r:
            j = await r.json()
            return j["choices"][0]["message"]["content"].strip()

    async def run_all(recs, progress, status):
        out = []
        batch = 20
        async with aiohttp.ClientSession() as sess:
            for i in range(0, len(recs), batch):
                slice_ = recs[i : i + batch]
                tasks = [analyze_one(sess, r) for r in slice_]
                res = await asyncio.gather(*tasks)
                out.extend(res)
                done = min(i + batch, len(recs))
                progress.progress(done / len(recs))
                status.text(f"Przetworzono {done}/{len(recs)}")
        return out

    # uruchomienie
    recs = df.to_dict(orient="records")
    progress = st.progress(0.0)
    status   = st.empty()
    start = time.time()
    with st.spinner("Analiza…"):
        feedbacks = asyncio.run(run_all(recs, progress, status))
    elapsed = time.time() - start
    st.success(f"Analiza zakończona w {elapsed:.1f}s")

    df["Feedback"] = feedbacks
    # wyciąganie score
    def parse_score(t):
        for l in t.splitlines():
            if l.lower().startswith("ocena"):
                try: return float(l.split(":")[1].split("/")[0])
                except: pass
        return None
    df["Score"] = df["Feedback"].map(parse_score)

    # prezentacja
    st.header("📈 Podsumowanie zespołu")
    st.metric("Średnia ocena", f"{df['Score'].mean():.2f}/5")
    st.metric("Wiadomości", len(df))

    st.header("👤 Raport agentów")
    agg = df.groupby("Author").agg(Śr_Ocena=("Score","mean"), Liczba=("Score","count")).round(2).reset_index()
    st.dataframe(agg, use_container_width=True)

    st.header("📥 Pobierz pełen raport")
    st.download_button("⬇️ CSV", df.to_csv(index=False, sep=";"), "raport.csv", "text/csv")
