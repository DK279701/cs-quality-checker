import streamlit as st
import pandas as pd
import requests
import aiohttp
import asyncio
import time

st.set_page_config(page_title="CS Quality Checker", layout="wide")
st.title("📥 Pobieranie i analiza OUTBOUND wiadomości z Front")

# ——— SIDEBAR: KLUCZE I WYBRANE INBOXY —————————————————
st.sidebar.header("🔑 Klucze API")

front_token = st.sidebar.text_input("Front API Token", type="password")
openai_key  = st.sidebar.text_input("OpenAI API Key",   type="password")

if not front_token or not openai_key:
    st.sidebar.info("Wprowadź oba klucze API (Front i OpenAI), aby kontynuować.")
    st.stop()

# ——— TYLKO TE TRZY INBOXY ———————————————————————
INBOXES = {
    "Customer Service":         "inb_a3xxy",
    "Chat Airbnb - New":        "inb_d2uom",
    "Chat Booking - New":       "inb_d2xee"
}
st.sidebar.markdown("**Wczytane inboxy:**")
for name, iid in INBOXES.items():
    st.sidebar.write(f"- {name} (`{iid}`)")

inbox_ids = list(INBOXES.values())

# ——— POBIERANIE OUTBOUND WIADOMOŚCI —————————————————
@st.cache_data(ttl=300)
def fetch_outbound_messages(token, inbox_ids):
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    base_url = "https://api2.frontapp.com/conversations"
    records = []

    for inbox in inbox_ids:
        params = {"inbox_id": inbox, "page_size": 100}
        convs = []
        # paginacja konwersacji
        while True:
            r = requests.get(base_url, headers=headers, params=params)
            r.raise_for_status()
            data = r.json()
            convs.extend(data.get("_results", []))
            cursor = data.get("_cursor")
            if not cursor:
                break
            params["cursor"] = cursor

        # pobieranie outbound wiadomości
        for c in convs:
            cid = c.get("id", "")
            r2 = requests.get(f"{base_url}/{cid}/messages", headers=headers)
            r2.raise_for_status()
            for m in r2.json().get("_results", []):
                if m.get("direction") != "outbound":
                    continue
                raw = m.get("author")
                author = raw.get("handle") if isinstance(raw, dict) else (str(raw) if raw else "Unknown")
                records.append({
                    "Inbox ID":        inbox,
                    "Conversation ID": cid,
                    "Message ID":      m.get("id", ""),
                    "Author":          author,
                    "Extract":         m.get("body", "")
                })
    return pd.DataFrame(records)

# ——— GŁÓWNY PRZEBIEG ————————————————————————
if st.button("▶️ Pobierz i analizuj OUTBOUND wiadomości"):
    with st.spinner("⏳ Pobieranie wiadomości…"):
        df = fetch_outbound_messages(front_token, inbox_ids)

    if df.empty:
        st.warning("‼️ Nie znaleziono żadnych wiadomości OUTBOUND w wybranych inboxach.")
        st.stop()

    st.success(f"Pobrano {len(df)} wiadomości OUTBOUND z {len(inbox_ids)} inboxów.")
    st.dataframe(df.head(10))

    # ——— ASYNC ANALIZA GPT —————————————————————
    API_URL = "https://api.openai.com/v1/chat/completions"
    HEADERS = {"Authorization": f"Bearer {openai_key}", "Content-Type": "application/json"}
    SYSTEM_PROMPT = (
        "Jesteś Menedżerem Customer Service w Bookinghost.\n"
        "Oceń jakość tej wiadomości OUTBOUND w skali 1–5, weź pod uwagę:\n"
        "• empatię\n• poprawność językową\n• zgodność z procedurami\n• ton"
    )

    async def analyze_one(session, rec):
        payload = {
            "model": "gpt-3.5-turbo",
            "messages": [
                {"role":"system","content":SYSTEM_PROMPT},
                {"role":"user",  "content":rec["Extract"]}
            ],
            "temperature":0.3,
            "max_tokens":200
        }
        async with session.post(API_URL, headers=HEADERS, json=payload) as resp:
            js = await resp.json()
            return js["choices"][0]["message"]["content"].strip()

    async def run_all(recs, prog, stat):
        out, batch = [], 20
        async with aiohttp.ClientSession() as sess:
            for i in range(0, len(recs), batch):
                chunk = recs[i:i+batch]
                res   = await asyncio.gather(*[analyze_one(sess, r) for r in chunk])
                out.extend(res)
                done = min(i+batch, len(recs))
                prog.progress(done/len(recs)); stat.text(f"Przetworzono: {done}/{len(recs)}")
        return out

    recs = df.to_dict(orient="records")
    prog = st.progress(0.0); stat = st.empty(); start=time.time()
    with st.spinner("⚙️ Analiza…"):
        df["Feedback"] = asyncio.run(run_all(recs, prog, stat))
    elapsed = time.time() - start
    st.success(f"✅ Analiza zakończona w {elapsed:.1f}s")

    # ——— PODSUMOWANIE ——————————————————————
    def parse_score(txt):
        for l in txt.splitlines():
            if l.lower().startswith("ocena"):
                try: return float(l.split(":")[1].split("/")[0].strip())
                except: pass
        return None

    df["Score"] = df["Feedback"].map(parse_score)

    st.header("📈 Podsumowanie zespołu")
    st.metric("Średnia ocena", f"{df['Score'].mean():.2f}/5")
    st.metric("Liczba wiadomości", len(df))

    st.header("👤 Raport agentów")
    agg = df.groupby("Author").agg(Średnia=("Score","mean"), Liczba=("Score","count")).round(2).reset_index()
    st.dataframe(agg, use_container_width=True)

    st.header("📥 Pobierz raport CSV")
    st.download_button(
        "⬇️ Pobierz CSV",
        df.to_csv(index=False, sep=";").encode("utf-8"),
        "outbound_report.csv",
        "text/csv"
    )
