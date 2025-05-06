import streamlit as st
import pandas as pd
import requests
import aiohttp
import asyncio
import time

st.set_page_config(page_title="CS Quality Checker", layout="wide")
st.title("📥 Pobieranie i analiza OUTBOUND wiadomości z Front")

# ——— SIDEBAR: KLUCZE I WYBÓR INBOXÓW —————————————————
st.sidebar.header("🔑 Klucze API")

front_token = st.sidebar.text_input("Front API Token", type="password")
openai_key  = st.sidebar.text_input("OpenAI API Key", type="password")

if not front_token or not openai_key:
    st.sidebar.info("Wprowadź oba klucze (Front i OpenAI), aby kontynuować.")
    st.stop()

@st.cache_data(ttl=300)
def list_inboxes(token):
    """Pobiera listę inboxów z Front API."""
    url = "https://api2.frontapp.com/inboxes"
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    resp = requests.get(url, headers=headers)
    resp.raise_for_status()
    return resp.json().get("_results", [])

# pobierz i wyświetl inboxy
try:
    inboxes = list_inboxes(front_token)
    options = {f"{ib['name']} ({ib['id']})": ib["id"] for ib in inboxes}
    selected = st.sidebar.multiselect(
        "🔍 Wybierz inboxy", 
        options.keys()
    )
    inbox_ids = [options[s] for s in selected]
    if not inbox_ids:
        st.sidebar.warning("Wybierz przynajmniej jeden inbox z listy powyżej.")
        st.stop()
except Exception as e:
    st.sidebar.error(f"Nie udało się pobrać inboxów: {e}")
    st.stop()

# ——— FETCH OUTBOUND WIADOMOŚCI —————————————————————
@st.cache_data(ttl=300)
def fetch_outbound_messages(token, inbox_ids):
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    all_records = []
    base_url = "https://api2.frontapp.com/conversations"

    for inbox in inbox_ids:
        # paginacja konwersacji
        params = {"inbox_id": inbox, "page_size": 100}
        convs = []
        while True:
            r = requests.get(base_url, headers=headers, params=params)
            r.raise_for_status()
            data = r.json()
            convs.extend(data.get("_results", []))
            cursor = data.get("_cursor")
            if not cursor:
                break
            params["cursor"] = cursor

        # pobranie outbound wiadomości z każdej konwersacji
        for c in convs:
            conv_id = c.get("id", "")
            r2 = requests.get(f"{base_url}/{conv_id}/messages", headers=headers)
            r2.raise_for_status()
            for m in r2.json().get("_results", []):
                if m.get("direction") != "outbound":
                    continue
                raw_author = m.get("author")
                if isinstance(raw_author, dict):
                    author = raw_author.get("handle", "Unknown")
                else:
                    author = str(raw_author) if raw_author else "Unknown"
                all_records.append({
                    "Inbox ID":        inbox,
                    "Conversation ID": conv_id,
                    "Message ID":      m.get("id", ""),
                    "Author":          author,
                    "Extract":         m.get("body", "")
                })
    return pd.DataFrame(all_records)

# ——— GŁÓWNY PRZEBIEG ————————————————————————
if st.button("▶️ Pobierz i analizuj OUTBOUND wiadomości"):
    with st.spinner("⏳ Pobieranie wiadomości…"):
        df = fetch_outbound_messages(front_token, inbox_ids)

    st.success(f"Pobrano {len(df)} wiadomości OUTBOUND z {len(inbox_ids)} inboxów.")
    st.dataframe(df.head(10))

    # ——— ANALIZA GPT ——————————————————————
    API_URL = "https://api.openai.com/v1/chat/completions"
    HEADERS = {
        "Authorization": f"Bearer {openai_key}",
        "Content-Type":  "application/json"
    }
    SYSTEM_PROMPT = (
        "Jesteś Menedżerem Customer Service w Bookinghost. "
        "Oceń jakość tej wiadomości OUTBOUND w skali 1–5:\n"
        "• empatia\n• poprawność językowa\n• zgodność z procedurami\n• ton"
    )

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

    recs = df.to_dict(orient="records")
    prog = st.progress(0.0)
    stat = st.empty()
    start = time.time()
    with st.spinner("⚙️ Analiza…"):
        df["Feedback"] = asyncio.run(run_all(recs, prog, stat))
    elapsed = time.time() - start
    st.success(f"✅ Analiza zakończona w {elapsed:.1f}s")

    # ——— PODSUMOWANIE ——————————————————————
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
        df
        .groupby("Author")
        .agg(Średnia_ocena=("Score","mean"), Liczba=("Score","count"))
        .round(2)
        .reset_index()
    )
    st.dataframe(agg, use_container_width=True)

    st.header("📥 Pobierz raport CSV")
    st.download_button(
        "⬇️ Pobierz CSV",
        df.to_csv(index=False, sep=";").encode("utf-8"),
        "outbound_report.csv",
        "text/csv"
    )
