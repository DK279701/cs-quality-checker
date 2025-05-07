import streamlit as st
import pandas as pd
import requests
import aiohttp
import asyncio
import time

st.set_page_config(page_title="CS Quality Checker", layout="wide")
st.title("📥 Pobieranie i analiza wiadomości AGENTÓW z Front")

# ——— SIDEBAR: Klucze API ——————————————————
front_token = st.sidebar.text_input("Front API Token", type="password")
openai_key  = st.sidebar.text_input("OpenAI API Key",   type="password")
if not front_token or not openai_key:
    st.sidebar.warning("Wprowadź oba klucze API.")
    st.stop()

# ——— Stałe inboxy ——————————————————
INBOX_IDS = ["inb_a3xxy","inb_d2uom","inb_d2xee"]
st.sidebar.markdown("**Inboxy (stałe):**")
for iid in INBOX_IDS: st.sidebar.write(f"- `{iid}`")

# ——— Pobranie WSZYSTKICH wiadomości —————————————————
@st.cache_data(ttl=300)
def fetch_all(token, inbox_ids):
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    base = "https://api2.frontapp.com/conversations"
    rows = []
    for inbox in inbox_ids:
        # paginacja
        params = {"inbox_id": inbox, "page_size": 100}
        convs = []
        while True:
            r = requests.get(base, headers=headers, params=params); r.raise_for_status()
            js = r.json()
            convs.extend(js.get("_results", []))
            c = js.get("_cursor")
            if not c: break
            params["cursor"] = c

        # wiadomości
        for c in convs:
            cid = c["id"]
            r2 = requests.get(f"{base}/{cid}/messages", headers=headers); r2.raise_for_status()
            for m in r2.json().get("_results", []):
                raw = m.get("author")
                author = raw.get("handle") if isinstance(raw, dict) else (str(raw) if raw else "Unknown")
                rows.append({
                    "Inbox ID":        inbox,
                    "Conversation ID": cid,
                    "Message ID":      m.get("id",""),
                    "Author":          author,
                    "Extract":         m.get("body","")
                })
    return pd.DataFrame(rows)

if st.button("▶️ Pobierz wszystkie wiadomości"):
    with st.spinner("⏳ Pobieranie…"):
        df = fetch_all(front_token, INBOX_IDS)

    if df.empty:
        st.warning("‼️ Brak wiadomości w inboxach.")
        st.stop()

    st.success(f"Pobrano {len(df)} wiadomości.")
    st.dataframe(df.head(5))

    # ——— Wybór autorów do analizy ——————————————————
    authors = sorted(df["Author"].unique())
    selected = st.sidebar.multiselect("👤 Wybierz agentów (Author)", authors, default=authors)
    df = df[df["Author"].isin(selected)].reset_index(drop=True)

    if df.empty:
        st.warning("‼️ Żaden z wybranych Author nie występuje w danych.")
        st.stop()

    st.info(f"Analiza {len(df)} wiadomości od wybranych agentów.")

    # ——— Analiza przez GPT ——————————————————
    API_URL = "https://api.openai.com/v1/chat/completions"
    HEADERS = {"Authorization":f"Bearer {openai_key}","Content-Type":"application/json"}
    SYSTEM_PROMPT = (
        "Jesteś Menedżerem CS w Bookinghost. Oceń jakość wiadomości agentów (1–5):\n"
        "• empatia\n• poprawność językowa\n• zgodność z procedurami\n• ton"
    )

    async def analyze_one(sess, rec):
        payload = {
            "model":"gpt-3.5-turbo",
            "messages":[
                {"role":"system","content":SYSTEM_PROMPT},
                {"role":"user","content":rec["Extract"]}
            ],
            "temperature":0.3,"max_tokens":200
        }
        async with sess.post(API_URL, headers=HEADERS, json=payload) as r:
            js = await r.json()
            return js["choices"][0]["message"]["content"].strip()

    async def run_all(recs, prog, stat):
        out=[]; batch=20
        async with aiohttp.ClientSession() as sess:
            for i in range(0,len(recs),batch):
                chunk = recs[i:i+batch]
                res   = await asyncio.gather(*[analyze_one(sess,r) for r in chunk])
                out.extend(res)
                done = min(i+batch,len(recs))
                prog.progress(done/len(recs)); stat.text(f"Przetworzono {done}/{len(recs)}")
        return out

    recs = df.to_dict("records")
    prog = st.progress(0.0); stat = st.empty(); start=time.time()
    with st.spinner("⚙️ Analiza…"):
        df["Feedback"] = asyncio.run(run_all(recs, prog, stat))
    st.success(f"✅ Zakończono w {time.time()-start:.1f}s")

    df["Score"] = df["Feedback"].apply(
        lambda t: float(next((l for l in t.splitlines() if l.lower().startswith("ocena")), "")
                         .split(":")[1].split("/")[0]) 
                  if "Ocena" in t else None
    )

    st.header("📈 Średnia ocena")
    st.metric("", f"{df['Score'].mean():.2f}/5")
    st.header("👤 Raport agentów")
    agg = df.groupby("Author").agg(Średnia=("Score","mean"),Liczba=("Score","count")).round(2).reset_index()
    st.dataframe(agg, use_container_width=True)

    st.download_button("📥 Pobierz CSV",
        df.to_csv(index=False,sep=";").encode("utf-8"),"report.csv","text/csv")
