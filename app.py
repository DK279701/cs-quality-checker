import streamlit as st
import pandas as pd
import requests
import asyncio
import aiohttp
import time
from bs4 import BeautifulSoup

# --- Konfiguracja strony ---
st.set_page_config(page_title="CS Quality Checker", layout="wide")
st.title("📥 Pobieranie i analiza OUTBOUND wiadomości z Front")

# --- Sidebar: klucze API ---
st.sidebar.header("🔑 Klucze API")
front_token = st.sidebar.text_input("Front API Token", type="password")
openai_key  = st.sidebar.text_input("OpenAI API Key",   type="password")
if not front_token or not openai_key:
    st.sidebar.warning("Podaj oba klucze API (Front i OpenAI).")
    st.stop()

# --- Stałe inboxy (tylko trzy) ---
INBOX_IDS = ["inb_a3xxy", "inb_d2uom", "inb_d2xee"]
st.sidebar.markdown("**Analizowane inboxy:**")
st.sidebar.write("- Customer Service: `inb_a3xxy`")
st.sidebar.write("- Chat Airbnb – New: `inb_d2uom`")
st.sidebar.write("- Chat Booking – New: `inb_d2xee`")

# --- Funkcja pobierająca i filtrowalna tylko outbound wiadomości ---
@st.cache_data(ttl=300)
def fetch_outbound(token, inbox_ids):
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    base = "https://api2.frontapp.com/conversations"
    rows = []

    for inbox in inbox_ids:
        params = {"inbox_id": inbox, "page_size": 100}
        while True:
            r = requests.get(base, headers=headers, params=params)
            r.raise_for_status()
            js = r.json()
            for conv in js.get("_results", []):
                cid = conv.get("id", "")
                r2 = requests.get(f"{base}/{cid}/messages", headers=headers)
                r2.raise_for_status()
                for m in r2.json().get("_results", []):
                    # filtrujemy tylko outbound
                    if m.get("is_inbound", True):
                        continue
                    # stripping HTML
                    raw_body = m.get("body", "")
                    text = BeautifulSoup(raw_body, "html.parser").get_text(separator="\n")
                    # wyciągnięcie autora
                    raw = m.get("author")
                    if isinstance(raw, dict):
                        author = (
                            raw.get("handle")
                            or raw.get("username")
                            or raw.get("name")
                            or raw.get("id")
                            or "Unknown"
                        )
                    else:
                        author = str(raw) if raw else "Unknown"
                    rows.append({
                        "Inbox ID":        inbox,
                        "Conversation ID": cid,
                        "Message ID":      m.get("id", ""),
                        "Author":          author,
                        "Extract":         text
                    })
            cursor = js.get("_cursor")
            if not cursor:
                break
            params["cursor"] = cursor

    return pd.DataFrame(rows)

# --- Main flow ---
if st.button("▶️ Pobierz i analizuj OUTBOUND wiadomości"):
    with st.spinner("⏳ Pobieram wiadomości…"):
        df = fetch_outbound(front_token, INBOX_IDS)

    if df.empty:
        st.warning("❗ Nie znaleziono żadnych wiadomości outbound.")
        st.stop()

    # opcjonalnie wyklucz autorów
    st.sidebar.header("🚫 Wyklucz autorów")
    authors = sorted(df["Author"].unique())
    exclude = st.sidebar.multiselect("Autorzy do wykluczenia:", options=authors)
    if exclude:
        df = df[~df["Author"].isin(exclude)].reset_index(drop=True)
    if df.empty:
        st.warning("❗ Po wykluczeniu autorów brak wiadomości do analizy.")
        st.stop()

    st.success(f"Analiza {len(df)} wiadomości od {len(df['Author'].unique())} autorów.")
    st.dataframe(df.head(10), use_container_width=True)

    # --- Przygotowanie OpenAI ---
    API_URL = "https://api.openai.com/v1/chat/completions"
    HEADERS = {"Authorization": f"Bearer {openai_key}", "Content-Type": "application/json"}
    SYSTEM_PROMPT = (
        "Jesteś Menedżerem Customer Service w Bookinghost i oceniasz jakość wiadomości agentów "
        "w skali 1–5. Weź pod uwagę:\n"
        "• empatia i uprzejmość\n"
        "• poprawność językową\n"
        "• zgodność z procedurami\n"
        "• ton komunikacji\n\n"
        "Odpowiedz w formacie:\n"
        "Ocena: X/5\n"
        "Uzasadnienie: • punkt 1\n• punkt 2"
    )

    async def analyze_one(session, rec):
        payload = {
            "model": "gpt-3.5-turbo",
            "messages": [
                {"role":"system", "content":SYSTEM_PROMPT},
                {"role":"user",   "content":rec["Extract"]}
            ],
            "temperature":0.3,
            "max_tokens":200
        }
        try:
            async with session.post(API_URL, headers=HEADERS, json=payload) as resp:
                js = await resp.json()
        except Exception as e:
            return f"❌ API error: {e}"
        if js.get("error"):
            return f"❌ API error: {js['error'].get('message','')}"
        choices = js.get("choices") or []
        if not choices:
            return "❌ No choices"
        content = choices[0].get("message",{}).get("content")
        return content.strip() if content else "❌ Empty content"

    async def run_all(recs, prog, stat):
        out=[]; batch=20
        async with aiohttp.ClientSession() as sess:
            for i in range(0, len(recs), batch):
                chunk = recs[i:i+batch]
                res = await asyncio.gather(*[analyze_one(sess,r) for r in chunk])
                out.extend(res)
                done = min(i+batch, len(recs))
                prog.progress(done/len(recs)); stat.text(f"Przetworzono: {done}/{len(recs)}")
        return out

    recs = df.to_dict("records")
    prog = st.progress(0.0); stat = st.empty(); start=time.time()
    with st.spinner("⚙️ Analiza…"):
        df["Feedback"] = asyncio.run(run_all(recs, prog, stat))
    st.success(f"✅ Zakończono w {time.time()-start:.1f}s")

    # parsowanie oceny
    def parse_score(txt):
        for l in txt.splitlines():
            if l.lower().startswith("ocena"):
                try: return float(l.split(":")[1].split("/")[0].strip())
                except: pass
        return None
    df["Score"] = df["Feedback"].map(parse_score)

    # --- Raport ---
    st.header("📈 Podsumowanie zespołu")
    st.metric("Średnia ocena", f"{df['Score'].mean():.2f}/5")
    st.metric("Liczba analizowanych wiadomości", len(df))

    st.header("👤 Raport agentów")
    agg = (
        df.groupby("Author")
          .agg(Średnia_ocena=("Score","mean"), Liczba=("Score","count"))
          .round(2)
          .reset_index()
    )
    st.dataframe(agg, use_container_width=True)

    st.header("📥 Pobierz CSV")
    csv = df.to_csv(index=False, sep=";").encode("utf-8")
    st.download_button("⬇️ CSV", data=csv, file_name="outbound_report.csv", mime="text/csv")
