import streamlit as st
import pandas as pd
import requests
import aiohttp
import asyncio
import time

st.set_page_config(page_title="CS Quality Checker", layout="wide")
st.title("📥 Pobieranie i analiza wiadomości AGENTÓW z Front")

# ——— SIDEBAR: KLUCZE, INBOXY i AGENT HANDLE ——————————
st.sidebar.header("🔑 Klucze API")
front_token = st.sidebar.text_input("Front API Token", type="password")
openai_key  = st.sidebar.text_input("OpenAI API Key",   type="password")

st.sidebar.markdown("**Inboxy (stałe):**")
INBOX_IDS = ["inb_a3xxy","inb_d2uom","inb_d2xee"]
for iid in INBOX_IDS:
    st.sidebar.write(f"- `{iid}`")

agent_handles = st.sidebar.text_input(
    "Handle agentów (oddzielone przecinkami)",
    placeholder="jan.kowalski,anna.nowak,piotr.zielinski"
)

if not front_token or not openai_key:
    st.sidebar.warning("Wprowadź oba klucze API.")
    st.stop()

# ——— FETCH WSZYSTKICH WIADOMOŚCI —————————————————
@st.cache_data(ttl=300)
def fetch_all_messages(token, inbox_ids):
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    base_url = "https://api2.frontapp.com/conversations"
    records = []
    for inbox in inbox_ids:
        params = {"inbox_id": inbox, "page_size": 100}
        # paginacja konwersacji
        convs = []
        while True:
            r = requests.get(base_url, headers=headers, params=params)
            r.raise_for_status()
            js = r.json()
            convs.extend(js.get("_results", []))
            cursor = js.get("_cursor")
            if not cursor: break
            params["cursor"] = cursor

        # pobranie wszystkich wiadomości
        for c in convs:
            cid = c.get("id","")
            r2 = requests.get(f"{base_url}/{cid}/messages", headers=headers)
            r2.raise_for_status()
            for m in r2.json().get("_results", []):
                raw = m.get("author")
                if isinstance(raw, dict):
                    author = raw.get("handle","Unknown")
                else:
                    author = str(raw) if raw else "Unknown"
                records.append({
                    "Inbox ID":        inbox,
                    "Conversation ID": cid,
                    "Message ID":      m.get("id",""),
                    "Author":          author,
                    "Extract":         m.get("body","")
                })
    return pd.DataFrame(records)

# ——— GŁÓWNY PRZEBIEG ————————————————————————
if st.button("▶️ Pobierz i przeanalizuj WIADOMOŚCI AGENTÓW"):
    # 1) fetch
    with st.spinner("⏳ Pobieranie…"):
        df = fetch_all_messages(front_token, INBOX_IDS)

    if df.empty:
        st.warning("‼️ Brak wiadomości w podanych inboxach.")
        st.stop()

    # 2) filtr po agentach
    handles = [h.strip() for h in agent_handles.split(",") if h.strip()]
    if not handles:
        st.warning("‼️ Podaj conajmniej jeden handle agenta.")
        st.stop()

    df = df[df["Author"].isin(handles)]
    if df.empty:
        st.warning("‼️ Żaden record nie pasuje do podanych handle’y.")
        st.stop()

    st.success(f"Pobrano i wyfiltrowano {len(df)} wiadomości od agentów.")
    st.dataframe(df.head(10))

    # ——— ASYNC ANALIZA GPT ————————————————————
    API_URL = "https://api.openai.com/v1/chat/completions"
    HEADERS = {"Authorization": f"Bearer {openai_key}", "Content-Type":"application/json"}
    SYSTEM_PROMPT = (
        "Jesteś Menedżerem Customer Service w Bookinghost i oceniasz jakość wiadomości agentów "
        "w skali 1–5:\n"
        "• empatia\n• poprawność językowa\n• zgodność z procedurami\n• ton"
    )

    async def analyze_one(sess, rec):
        payload = {
            "model": "gpt-3.5-turbo",
            "messages":[
                {"role":"system", "content":SYSTEM_PROMPT},
                {"role":"user",   "content":rec["Extract"]}
            ],
            "temperature":0.3, "max_tokens":200
        }
        async with sess.post(API_URL, headers=HEADERS, json=payload) as resp:
            js = await resp.json()
            return js["choices"][0]["message"]["content"].strip()

    async def run_all(recs, prog, stat):
        out, batch = [], 20
        async with aiohttp.ClientSession() as sess:
            for i in range(0, len(recs), batch):
                chunk = recs[i:i+batch]
                res   = await asyncio.gather(*[analyze_one(sess,r) for r in chunk])
                out.extend(res)
                done = min(i+batch, len(recs))
                prog.progress(done/len(recs)); stat.text(f"Przetworzono: {done}/{len(recs)}")
        return out

    recs = df.to_dict(orient="records")
    prog = st.progress(0.0); stat = st.empty(); start = time.time()
    with st.spinner("⚙️ Analiza…"):
        df["Feedback"] = asyncio.run(run_all(recs, prog, stat))
    elapsed = time.time() - start
    st.success(f"✅ Analiza zakończona w {elapsed:.1f}s")

    df["Score"] = df["Feedback"].apply(lambda txt: float(txt.splitlines()[0].split(":")[1].split("/")[0]) if "Ocena" in txt else None)

    # ——— RAPORT ——————————————————————
    st.header("📈 Średnia ocena")
    st.metric("", f"{df['Score'].mean():.2f}/5")

    st.header("👤 Raport agentów")
    agg = df.groupby("Author").agg(Średnia_ocena=("Score","mean"), Liczba=("Score","count")).round(2).reset_index()
    st.dataframe(agg, use_container_width=True)

    st.header("📥 Pobierz CSV")
    st.download_button("⬇️ CSV", df.to_csv(index=False,sep=";").encode("utf-8"), "agent_report.csv", "text/csv")
