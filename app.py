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

st.sidebar.header("📅 Zakres dat (filtr po created_at)")
start_date = st.sidebar.date_input("Start",  value=datetime.utcnow().date() - pd.Timedelta(days=7))
end_date   = st.sidebar.date_input("Koniec", value=datetime.utcnow().date())

# Konwersja do datetime
since_dt = datetime.combine(start_date, dtime.min)
until_dt = datetime.combine(end_date,   dtime.max)
since_iso = since_dt.isoformat() + "Z"
until_iso = until_dt.isoformat() + "Z"

# ——— DEBUGOWANE POBIERANIE Z FRONT —————————————————
def parse_front_date(ct):
    try:
        return datetime.fromisoformat(ct.replace("Z", "+00:00"))
    except:
        return None

@st.cache_data(ttl=300)
def fetch_front_debug(token, inbox, since_dt, until_dt):
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    params = {"inbox_id": inbox, "page_size": 100}
    url = "https://api2.frontapp.com/conversations"

    all_convs = []
    debug = {
        "pages_fetched": 0,
        "total_convs": 0,
        "msgs_per_conv": {},
        "min_created": None,
        "max_created": None
    }

    # paginacja po konwersacjach
    while True:
        resp = requests.get(url, headers=headers, params={k:v for k,v in params.items() if v})
        resp.raise_for_status()
        data = resp.json()
        debug["pages_fetched"] += 1
        convs = data.get("_results", [])
        debug["total_convs"] += len(convs)
        all_convs.extend(convs)
        cursor = data.get("_cursor")
        if not cursor:
            break
        params["cursor"] = cursor

    msgs = []
    for c in all_convs:
        conv_id = c["id"]
        r2 = requests.get(f"{url}/{conv_id}/messages", headers=headers)
        r2.raise_for_status()
        conv_msgs = r2.json().get("_results", [])
        debug["msgs_per_conv"][conv_id] = len(conv_msgs)
        for m in conv_msgs:
            ct = m.get("created_at")
            created = parse_front_date(ct) if ct else None
            if created:
                # aktualizuj min/max
                if debug["min_created"] is None or created < debug["min_created"]:
                    debug["min_created"] = created
                if debug["max_created"] is None or created > debug["max_created"]:
                    debug["max_created"] = created
                # filtr po zakresie
                if since_dt <= created <= until_dt:
                    msgs.append({
                        "Conversation ID": conv_id,
                        "Message ID":      m["id"],
                        "Author":          m["author"]["handle"],
                        "Extract":         m["body"],
                        "Created At":      created
                    })
    return pd.DataFrame(msgs), debug

# ——— POBIERANIE KONWERSACJI —————————————————————
if st.sidebar.button("▶️ Pobierz wiadomości"):
    if not api_token:
        st.sidebar.warning("🔑 Podaj Front API Token")
        st.stop()

    with st.spinner("⏳ Pobieranie…"):
        df, debug = fetch_front_debug(api_token, inbox_id or None, since_dt, until_dt)

    # Wyświetlamy debug info
    with st.expander("🛠️ Debug info"):
        st.write(f"- Stron konwersacji pobrano: **{debug['pages_fetched']}**")
        st.write(f"- Łącznie konwersacji: **{debug['total_convs']}**")
        sample = list(debug["msgs_per_conv"].items())[:10]
        st.write("Przykładowe konwersacje i liczba wiadomości:", sample)
        st.write(f"- Najwcześniejsza data wiadomości: **{debug['min_created']}**")
        st.write(f"- Najpóźniejsza data wiadomości: **{debug['max_created']}**")

    st.success(f"Pobrano {len(df)} wiadomości (z zakresu {since_iso} ↔ {until_iso})")
    st.dataframe(df)

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
        "w skali 1–5. Weź pod uwagę:\n"
        "• empatię i uprzejmość\n"
        "• poprawność językową\n"
        "• zgodność z procedurami\n"
        "• ton (ciepły, profesjonalny)\n\n"
        "Odpowiedz w formacie:\n"
        "Ocena: X/5\n"
        "Uzasadnienie: • punkt 1\n• punkt 2"
    )

    # ——— ASYNC ANALYSIS ————————————————————
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
        try:
            async with session.post(API_URL, headers=HEADERS, json=payload) as resp:
                js = await resp.json()
                return js["choices"][0]["message"]["content"].strip()
        except Exception as e:
            return f"❌ Błąd: {e}"

    async def run_all(recs, progress, status):
        out = []
        batch_size = 20
        async with aiohttp.ClientSession() as sess:
            for i in range(0, len(recs), batch_size):
                batch = recs[i : i + batch_size]
                tasks = [analyze_one(sess, r) for r in batch]
                res   = await asyncio.gather(*tasks)
                out.extend(res)
                done = min(i + batch_size, len(recs))
                progress.progress(done / len(recs))
                status.text(f"Przetworzono: {done}/{len(recs)}")
        return out

    # ——— URUCHOMIENIE ANALIZY ————————————————————
    recs     = df.to_dict(orient="records")
    progress = st.progress(0.0)
    status   = st.empty()
    start    = time.time()
    with st.spinner("⚙️ Analiza…"):
        feedbacks = asyncio.run(run_all(recs, progress, status))
    elapsed = time.time() - start
    st.success(f"✅ Zakończono w {elapsed:.1f}s")

    # ——— PODSUMOWANIE I RAPORT ————————————————————
    df["Feedback"] = feedbacks

    def parse_score(txt):
        for l in txt.splitlines():
            if l.lower().startswith("ocena"):
                try:
                    return float(l.split(":")[1].split("/")[0].strip())
                except:
                    pass
        return None

    df["Score"] = df["Feedback"].map(parse_score)

    st.header("📈 Podsumowanie zespołu")
    st.metric("Średnia ocena", f"{df['Score'].mean():.2f}/5")
    st.metric("Liczba wiadomości", len(df))

    st.header("👤 Raport agentów")
    agg = (
        df.groupby("Author")
          .agg(Średnia_ocena=("Score","mean"), Liczba=("Score","count"))
          .round(2)
          .reset_index()
    )
    st.dataframe(agg, use_container_width=True)

    st.header("📥 Pobierz pełen raport")
    csv = df.to_csv(index=False, sep=";").encode("utf-8")
    st.download_button("⬇️ Pobierz CSV", data=csv, file_name="raport.csv", mime="text/csv")
