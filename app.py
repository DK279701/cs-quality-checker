import streamlit as st
import pandas as pd
import requests
import aiohttp
import asyncio
import time
from bs4 import BeautifulSoup
from datetime import datetime, timedelta

st.set_page_config(page_title="CS Quality Checker", layout="wide")
st.title("📥 Analiza wiadomości wyłącznie wybranych agentów (ostatnie 7 dni)")

# --- Sidebar: klucze API ---
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

# zakres czasowy: ostatnie 7 dni
now = datetime.utcnow()
seven_days_ago = now - timedelta(days=7)

def fetch_and_filter(token, inbox_ids, since_dt, progress_bar):
    headers = {"Authorization":f"Bearer {token}","Accept":"application/json"}
    base = "https://api2.frontapp.com/conversations"
    rows = []
    total_inboxes = len(inbox_ids)

    for idx, inbox in enumerate(inbox_ids, start=1):
        params = {"inbox_id":inbox,"page_size":100}
        while True:
            resp = requests.get(base, headers=headers, params=params)
            resp.raise_for_status()
            js = resp.json()
            for conv in js.get("_results", []):
                cid = conv["id"]
                r2 = requests.get(f"{base}/{cid}/messages", headers=headers)
                r2.raise_for_status()
                for m in r2.json().get("_results", []):
                    # 1) tylko outbound
                    if m.get("is_inbound", True):
                        continue

                    # 2) data utworzenia
                    created_at = m.get("created_at")
                    if not created_at:
                        continue
                    created_dt = pd.to_datetime(created_at, utc=True)
                    if created_dt < since_dt:
                        continue

                    # 3) author_id i filtr
                    raw = m.get("author") or {}
                    author_id = raw.get("id") if isinstance(raw, dict) else None
                    if author_id not in ALLOWED_IDS:
                        continue

                    # 4) strip HTML
                    text = BeautifulSoup(m.get("body",""),"html.parser").get_text("\n")

                    # 5) czytelny Author
                    if isinstance(raw, dict):
                        name   = (raw.get("first_name","") + " " + raw.get("last_name","")).strip()
                        handle = raw.get("username") or raw.get("handle") or ""
                        author = f"{name} ({handle})" if handle else name
                    else:
                        author = str(raw)

                    rows.append({
                        "Inbox ID":        inbox,
                        "Created At":      created_dt,
                        "Conversation ID": cid,
                        "Message ID":      m.get("id",""),
                        "Author ID":       author_id,
                        "Author":          author,
                        "Extract":         text
                    })
            cursor = js.get("_cursor")
            if not cursor:
                break
            params["cursor"] = cursor

        # postęp pobierania inboxów
        progress_bar.progress(idx/total_inboxes)

    return pd.DataFrame(rows)

# --- Inicjalizacja paska postępu pobierania ---
fetch_prog = st.sidebar.progress(0.0)

if st.button("▶️ Pobierz i analizuj (ostatnie 7 dni)"):
    # 1) pobieranie i filtrowanie
    df = fetch_and_filter(front_token, INBOX_IDS, seven_days_ago, fetch_prog)
    if df.empty:
        st.warning("❗ Brak outbound-owych wiadomości od wybranych agentów w ostatnich 7 dniach.")
        st.stop()

    st.success(f"Pobrano {len(df)} wiadomości.")
    st.dataframe(df[["Created At","Author","Extract"]].head(10), use_container_width=True)

    # 2) przygotowanie do analizy GPT
    API_URL = "https://api.openai.com/v1/chat/completions"
    HEADERS = {"Authorization":f"Bearer {openai_key}","Content-Type":"application/json"}
    SYSTEM = (
        "Jesteś Menedżerem CS w Bookinghost i oceniasz jakość wiadomości agentów "
        "w skali 1–5 (empatia, poprawność, procedury, ton). "
        "Odpowiedz formatem:\nOcena: X/5\nUzasadnienie: • pkt1\n• pkt2"
    )

    async def analyze_one(sess, rec):
        payload = {
            "model":"gpt-3.5-turbo",
            "messages":[{"role":"system","content":SYSTEM},
                        {"role":"user","content":rec["Extract"]}],
            "temperature":0.3,"max_tokens":200
        }
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
            total=len(recs)
            for i in range(0,total,batch):
                chunk=recs[i:i+batch]
                res=await asyncio.gather(*[analyze_one(sess,r) for r in chunk])
                out.extend(res)
                done=min(i+batch,total)
                prog.progress(done/total)
                stat.text(f"Przetworzono {done}/{total}")
        return out

    recs = df.to_dict("records")
    analyze_prog = st.progress(0.0)
    analyze_stat = st.empty()
    start = time.time()

    with st.spinner("⚙️ Analiza…"):
        df["Feedback"] = asyncio.run(run_all(recs, analyze_prog, analyze_stat))

    st.success(f"✅ Analiza zakończona w {time.time()-start:.1f}s")

    # 3) parsowanie ocen i raport
    def parse_score(txt):
        for l in txt.splitlines():
            if l.lower().startswith("ocena"):
                try:
                    return float(l.split(":")[1].split("/")[0])
                except:
                    pass
        return None

    df["Score"] = df["Feedback"].map(parse_score)

    st.header("📈 Podsumowanie")
    st.metric("Średnia ocena", f"{df['Score'].mean():.2f}/5")
    st.metric("Liczba wiadomości", len(df))

    st.header("👤 Raport agentów")
    report = (
        df.groupby("Author")
          .agg(Średnia=("Score","mean"), Liczba=("Score","count"))
          .round(2)
          .reset_index()
    )
    st.dataframe(report, use_container_width=True)

    st.header("📥 Pobierz CSV")
    csv = df.to_csv(index=False, sep=";").encode("utf-8")
    st.download_button("⬇️ CSV", data=csv, file_name="report.csv", mime="text/csv")
