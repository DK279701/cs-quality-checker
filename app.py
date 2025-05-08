import streamlit as st
import pandas as pd
import requests
import aiohttp
import asyncio
import time
from bs4 import BeautifulSoup

st.set_page_config(page_title="CS Quality Checker", layout="wide")
st.title("📥 Analiza wiadomości wyłącznie wybranych agentów")

# ——— SIDEBAR: KLUCZE API ——————————————————
st.sidebar.header("🔑 Klucze API")
front_token = st.sidebar.text_input("Front API Token", type="password")
openai_key  = st.sidebar.text_input("OpenAI API Key",   type="password")
if not front_token or not openai_key:
    st.sidebar.warning("Podaj oba klucze API (Front i OpenAI).")
    st.stop()

# ——— STAŁE INBOXY ———————————————————————
INBOX_IDS = ["inb_a3xxy", "inb_d2uom", "inb_d2xee"]
st.sidebar.markdown("**Analizowane inboxy:**")
st.sidebar.write("- Customer Service (`inb_a3xxy`)")
st.sidebar.write("- Chat Airbnb – New (`inb_d2uom`)")
st.sidebar.write("- Chat Booking – New (`inb_d2xee`)")

# ——— LISTA DOZWOLONYCH AGENTÓW (ID) ——————————
ALLOWED_IDS = {
    "tea_a2k46",  # Ewelina Poszczyk
    "tea_cj1ue",  # Stanisław Krakowski
    "tea_cocnq",  # Kacper Mocny
    "tea_cs6hi",  # Jakub Buryta
    "tea_gs47r",  # Bartłomiej Musiejuk
    "tea_h7x3r",  # Sebastian Dolecki
    "tea_hjadz",  # Kamil Watrak
    "tea_hm6zb",  # Łukasz Drozdowski
    "tea_hn7h3",  # Natalia Drużbicka
    "tea_hn7iv",  # Alicja Piątkiewicz
    "tea_hnytz",  # Oleksandr Styczyński
    "tea_hnyvr",  # Paulina Kupczyk
    "tea_97fh2",  # Kajetan Biernacki
}

# ——— FUNKCJA POBIERANIA I FILTRACJI ——————————
@st.cache_data(ttl=300)
def fetch_and_filter(token, inbox_ids):
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    base = "https://api2.frontapp.com/conversations"
    rows = []

    for inbox in inbox_ids:
        params = {"inbox_id": inbox, "page_size": 100}
        while True:
            resp = requests.get(base, headers=headers, params=params)
            resp.raise_for_status()
            js = resp.json()
            for conv in js.get("_results", []):
                cid = conv.get("id","")
                r2 = requests.get(f"{base}/{cid}/messages", headers=headers)
                r2.raise_for_status()
                for m in r2.json().get("_results", []):
                    # tylko outbound
                    if m.get("is_inbound", True):
                        continue

                    # surowe ID autora
                    raw = m.get("author") or {}
                    author_id = raw.get("id") if isinstance(raw, dict) else None
                    if author_id not in ALLOWED_IDS:
                        continue

                    # strip HTML
                    body = m.get("body","")
                    text = BeautifulSoup(body, "html.parser").get_text(separator="\n")

                    # czytelny Author
                    if isinstance(raw, dict):
                        name = raw.get("first_name","") + " " + raw.get("last_name","")
                        handle = raw.get("username") or raw.get("handle") or ""
                        author = f"{name.strip()} ({handle})".strip()
                    else:
                        author = str(raw)

                    rows.append({
                        "Inbox ID":        inbox,
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

    return pd.DataFrame(rows)

# ——— GŁÓWNY PRZEBIEG ————————————————————————
if st.button("▶️ Pobierz i analizuj wiadomości wybranych agentów"):
    with st.spinner("⏳ Pobieranie i filtrowanie…"):
        df = fetch_and_filter(front_token, INBOX_IDS)

    if df.empty:
        st.warning("❗ Nie znaleziono wiadomości od wskazanych agentów.")
        st.stop()

    st.success(f"Pobrano {len(df)} wiadomości outbound od wybranych agentów.")
    st.dataframe(df[["Author","Extract"]].head(10), use_container_width=True)

    # ——— ANALIZA GPT ——————————————————————
    API_URL = "https://api.openai.com/v1/chat/completions"
    HEADERS = {"Authorization": f"Bearer {openai_key}", "Content-Type":"application/json"}
    SYSTEM_PROMPT = (
        "Jesteś Menedżerem CS w Bookinghost i oceniasz jakość wiadomości agentów "
        "w skali 1–5. Weź pod uwagę:\n"
        "- empatię i uprzejmość\n- poprawność językową\n- zgodność z procedurami\n- ton komunikacji\n\n"
        "Odpowiedz formatem:\nOcena: X/5\nUzasadnienie: • pkt1\n• pkt2"
    )

    async def analyze_one(sess, rec):
        payload = {
            "model":"gpt-3.5-turbo",
            "messages":[
                {"role":"system","content":SYSTEM_PROMPT},
                {"role":"user",  "content":rec["Extract"]}
            ],
            "temperature":0.3,"max_tokens":200
        }
        async with sess.post(API_URL, headers=HEADERS, json=payload) as r:
            js = await r.json()
        if js.get("error"):
            return f"❌ API error: {js['error']['message']}"
        ch = js.get("choices") or []
        if not ch: return "❌ no choices"
        return ch[0]["message"]["content"].strip()

    async def run_all(recs, prog, stat):
        out=[]; batch=20
        async with aiohttp.ClientSession() as sess:
            for i in range(0,len(recs),batch):
                chunk=recs[i:i+batch]
                res=await asyncio.gather(*[analyze_one(sess,r) for r in chunk])
                out.extend(res)
                done=min(i+batch,len(recs))
                prog.progress(done/len(recs)); stat.text(f"Przetworzono {done}/{len(recs)}")
        return out

    recs = df.to_dict("records")
    prog = st.progress(0.0); stat=st.empty(); start=time.time()
    with st.spinner("⚙️ Analiza…"):
        df["Feedback"] = asyncio.run(run_all(recs, prog, stat))
    st.success(f"✅ Analiza zakończona w {time.time()-start:.1f}s")

    # ——— PARSOWANIE I RAPORT ——————————————————
    def parse_score(t):
        for l in t.splitlines():
            if l.lower().startswith("ocena"):
                try: return float(l.split(":")[1].split("/")[0])
                except: pass
        return None

    df["Score"] = df["Feedback"].map(parse_score)

    st.header("📈 Podsumowanie")
    st.metric("Średnia ocena", f"{df['Score'].mean():.2f}/5")
    st.metric("Liczba wiadomości", len(df))

    st.header("👤 Raport agentów")
    rb = (
        df.groupby("Author")
          .agg(Średnia=("Score","mean"), Liczba=("Score","count"))
          .round(2).reset_index()
    )
    st.dataframe(rb, use_container_width=True)

    st.header("📥 Pobierz CSV")
    csv = df.to_csv(index=False,sep=";").encode("utf-8")
    st.download_button("⬇️ CSV", csv, "report.csv", "text/csv")
