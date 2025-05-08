import streamlit as st
import pandas as pd
import requests
import aiohttp
import asyncio
import time
from bs4 import BeautifulSoup
from datetime import datetime, timedelta

st.set_page_config(page_title="CS Quality Checker", layout="wide")
st.title("📥 Analiza OUTBOUND wiadomości (ostatnie 7 dni)")

# --- Sidebar: API keys ---
st.sidebar.header("🔑 Klucze API")
front_token = st.sidebar.text_input("Front API Token", type="password")
openai_key  = st.sidebar.text_input("OpenAI API Key",   type="password")
if not front_token or not openai_key:
    st.sidebar.warning("Podaj oba klucze API (Front i OpenAI).")
    st.stop()

# --- Stałe inboxy ---
INBOX_IDS = ["inb_a3xxy","inb_d2uom","inb_d2xee"]
st.sidebar.markdown("**Analizowane inboxy:**")
st.sidebar.write("- Customer Service (`inb_a3xxy`)")
st.sidebar.write("- Chat Airbnb – New (`inb_d2uom`)")
st.sidebar.write("- Chat Booking – New (`inb_d2xee`)")

# --- Dozwolone ID agentów ---
ALLOWED_IDS = {
    "tea_a2k46","tea_cj1ue","tea_cocnq","tea_cs6hi","tea_gs47r",
    "tea_h7x3r","tea_hjadz","tea_hm6zb","tea_hn7h3","tea_hn7iv",
    "tea_hnytz","tea_hnyvr","tea_97fh2"
}

# --- Zakres czasowy: ostatnie 7 dni jako ISO8601 ---
since_dt = datetime.utcnow() - timedelta(days=7)
since_iso = since_dt.isoformat() + "Z"

def fetch_messages(token, inbox_ids, since_iso, progress_bar):
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    url = "https://api2.frontapp.com/messages"
    rows = []
    total = len(inbox_ids)
    for idx, inbox in enumerate(inbox_ids, start=1):
        params = {
            "inbox_id": inbox,
            "is_inbound": "false",
            "received_after": since_iso,
            "page_size": 100
        }
        while True:
            r = requests.get(url, headers=headers, params=params)
            r.raise_for_status()
            js = r.json()
            for m in js.get("_results", []):
                # author filtering
                raw = m.get("author") or {}
                author_id = raw.get("id") if isinstance(raw, dict) else None
                if author_id not in ALLOWED_IDS:
                    continue
                # body HTML -> text
                text = BeautifulSoup(m.get("body",""), "html.parser").get_text("\n")
                # author name
                if isinstance(raw, dict):
                    name   = (raw.get("first_name","") + " " + raw.get("last_name","")).strip()
                    handle = raw.get("username") or raw.get("handle") or ""
                    author = f"{name} ({handle})" if handle else name
                else:
                    author = str(raw)
                rows.append({
                    "Created At":      pd.to_datetime(m.get("created_at"), utc=True),
                    "Inbox ID":        inbox,
                    "Message ID":      m.get("id",""),
                    "Author ID":       author_id,
                    "Author":          author,
                    "Extract":         text
                })
            cursor = js.get("_cursor")
            if not cursor:
                break
            params["cursor"] = cursor
        progress_bar.progress(idx/total)
    return pd.DataFrame(rows)

# progress bar for fetch
fetch_prog = st.sidebar.progress(0.0)

if st.button("▶️ Pobierz i analizuj (ostatnie 7 dni)"):
    df = fetch_messages(front_token, INBOX_IDS, since_iso, fetch_prog)
    if df.empty:
        st.warning("❗ Nie znaleziono wiadomości outbound od wybranych agentów w ostatnich 7 dniach.")
        st.stop()

    st.success(f"Pobrano {len(df)} wiadomości.")
    st.dataframe(df[["Created At","Author","Extract"]].head(10), use_container_width=True)

    # --- GPT analysis ---
    API_URL = "https://api.openai.com/v1/chat/completions"
    HEADERS = {"Authorization":f"Bearer {openai_key}", "Content-Type":"application/json"}
    SYSTEM = (
        "Jesteś Menedżerem CS w Bookinghost i oceniasz jakość wiadomości agentów "
        "w skali 1–5. Uwzględnij empatię, poprawność, zgodność z procedurami i ton komunikacji.\n"
        "Odpowiedz formatem:\nOcena: X/5\nUzasadnienie: • pkt1\n• pkt2"
    )

    async def analyze_one(sess, rec):
        payload = {"model":"gpt-3.5-turbo",
                   "messages":[{"role":"system","content":SYSTEM},
                               {"role":"user","content":rec["Extract"]}],
                   "temperature":0.3, "max_tokens":200}
        async with sess.post(API_URL, headers=HEADERS, json=payload) as r:
            js = await r.json()
        if js.get("error"):
            return f"❌ {js['error']['message']}"
        ch = js.get("choices") or []
        if not ch: return "❌ no choices"
        return ch[0]["message"]["content"].strip()

    async def run_all(recs, prog, stat):
        out=[]; batch=20
        async with aiohttp.ClientSession() as sess:
            total = len(recs)
            for i in range(0, total, batch):
                chunk = recs[i:i+batch]
                res = await asyncio.gather(*[analyze_one(sess,r) for r in chunk])
                out.extend(res)
                done = min(i+batch, total)
                prog.progress(done/total); stat.text(f"Przetworzono {done}/{total}")
        return out

    recs = df.to_dict("records")
    analyze_prog = st.progress(0.0); analyze_stat = st.empty(); start=time.time()
    with st.spinner("⚙️ Analiza…"):
        df["Feedback"] = asyncio.run(run_all(recs, analyze_prog, analyze_stat))
    st.success(f"✅ Analiza zakończona w {time.time()-start:.1f}s")

    # parse scores
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
    report = df.groupby("Author").agg(Średnia=("Score","mean"),Liczba=("Score","count")).round(2).reset_index()
    st.dataframe(report, use_container_width=True)

    st.header("📥 Pobierz CSV")
    csv = df.to_csv(index=False, sep=";").encode("utf-8")
    st.download_button("⬇️ CSV", data=csv, file_name="report.csv", mime="text/csv")
