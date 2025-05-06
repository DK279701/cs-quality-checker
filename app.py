import streamlit as st
import pandas as pd
import requests
import aiohttp
import asyncio
import time
from dateutil.parser import parse as parse_date

st.set_page_config(page_title="CS Quality Checker", layout="wide")
st.title("📥 Pobieranie i analiza OUTBOUND wiadomości z Front")

# ——— SIDEBAR: API KEYS I INBOXY ——————————————————
st.sidebar.header("🔑 Klucze i filtry")
front_token = st.sidebar.text_input("Front API Token", type="password")
openai_key  = st.sidebar.text_input("OpenAI API Key", type="password")

inboxes_raw = st.sidebar.text_input(
    "Inbox IDs (oddzielone przecinkami)", 
    placeholder="inb_123...,inb_456...,inb_789..."
)

if not front_token or not openai_key:
    st.sidebar.info("Musisz podać oba klucze API.")
    st.stop()

# Parsujemy listę inboxów
inbox_ids = [i.strip() for i in inboxes_raw.split(",") if i.strip()]
if not inbox_ids:
    st.sidebar.info("Wprowadź przynajmniej jedno ID inboxu.")
    st.stop()

# ——— POBIERANIE WIADOMOŚCI —————————————————————
@st.cache_data(ttl=300)
def fetch_outbound_messages(token, inbox_ids):
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    all_records = []

    for inbox in inbox_ids:
        # 1) paginacja konwersacji w danym inboxie
        convs = []
        params = {"inbox_id": inbox, "page_size": 100}
        url = "https://api2.frontapp.com/conversations"
        while True:
            r = requests.get(url, headers=headers, params=params)
            r.raise_for_status()
            data = r.json()
            convs.extend(data.get("_results", []))
            cursor = data.get("_cursor")
            if not cursor:
                break
            params["cursor"] = cursor

        # 2) pobieranie wiadomości wychodzących
        for c in convs:
            conv_id = c.get("id", "")
            r2 = requests.get(f"{url}/{conv_id}/messages", headers=headers)
            r2.raise_for_status()
            for m in r2.json().get("_results", []):
                # filtruj wg kierunku
                if m.get("direction") != "outbound":
                    continue

                # autor
                raw_author = m.get("author")
                if isinstance(raw_author, dict):
                    author = raw_author.get("handle", "Unknown")
                else:
                    author = str(raw_author) if raw_author else "Unknown"

                # treść
                body = m.get("body", "")

                all_records.append({
                    "Inbox ID":        inbox,
                    "Conversation ID": conv_id,
                    "Message ID":      m.get("id", ""),
                    "Author":          author,
                    "Extract":         body
                })

    return pd.DataFrame(all_records)

# ——— GŁÓWNY PRZEBIEG ————————————————————————
if st.button("▶️ Pobierz i analizuj OUTBOUND wiadomości"):
    with st.spinner("⏳ Pobieranie…"):
        df = fetch_outbound_messages(front_token, inbox_ids)

    st.success(f"Pobrano {len(df)} OUTBOUND wiadomości z {len(inbox_ids)} inboxów.")
    st.dataframe(df.head(10))

    # ——— ANALIZA GPT ——————————————————————
    API_URL = "https://api.openai.com/v1/chat/completions"
    HEADERS = {"Authorization": f"Bearer {openai_key}", "Content-Type": "application/json"}
    SYSTEM_PROMPT = (
        "Jesteś Menedżerem Customer Service w Bookinghost. "
        "Oceń jakość tej wiadomości OUTBOUND w skali 1–5:\n"
        "• empatia\n• poprawność językowa\n• zgodność z procedurami\n• ton"
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
        out=[]; batch=20
        async with aiohttp.ClientSession() as sess:
            for i in range(0,len(recs),batch):
                chunk=recs[i:i+batch]
                res=await asyncio.gather(*[analyze_one(sess,r) for r in chunk])
                out.extend(res)
                done=min(i+batch,len(recs))
                prog.progress(done/len(recs)); stat.text(f"Przetworzono: {done}/{len(recs)}")
        return out

    recs = df.to_dict(orient="records")
    prog = st.progress(0.0); stat = st.empty(); start=time.time()
    with st.spinner("⚙️ Analiza…"):
        df["Feedback"] = asyncio.run(run_all(recs, prog, stat))
    st.success(f"✅ Analiza zakończona w {time.time()-start:.1f}s")

    # ——— RAPORT ——————————————————————
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
    agg = df.groupby("Author").agg(Śr=("Score","mean"),Cnt=("Score","count")).round(2).reset_index()
    st.dataframe(agg, use_container_width=True)

    st.header("📥 Pobierz CSV")
    st.download_button("⬇️ CSV",df.to_csv(index=False,sep=";"),"outbound_report.csv","text/csv")
