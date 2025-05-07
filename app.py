import streamlit as st
import pandas as pd
import requests
import aiohttp
import asyncio
import time
from bs4 import BeautifulSoup

# --- Streamlit page config ---
st.set_page_config(page_title="CS Quality Checker", layout="wide")
st.title("📥 Pobieranie i analiza OUTBOUND wiadomości z Front")

# --- Sidebar: API keys ---
st.sidebar.header("🔑 Klucze API")
front_token = st.sidebar.text_input("Front API Token", type="password")
openai_key  = st.sidebar.text_input("OpenAI API Key",   type="password")
if not front_token or not openai_key:
    st.sidebar.warning("Wprowadź oba klucze API (Front i OpenAI).")
    st.stop()

# --- Stałe inboxy ---
INBOX_IDS = ["inb_a3xxy", "inb_d2uom", "inb_d2xee"]
st.sidebar.markdown("**Wykorzystywane inboxy:**")
for iid in INBOX_IDS:
    st.sidebar.write(f"- `{iid}`")

# --- Pobierz dane konkretnego teammate'a i cache'uj ---
@st.cache_data(ttl=3600)
def get_teammate_info(token, teammate_id):
    url = f"https://api2.frontapp.com/teammates/{teammate_id}"
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(url, headers=headers)
    resp.raise_for_status()
    data = resp.json()
    return {
        "username":   data.get("username", ""),
        "first_name": data.get("first_name", ""),
        "last_name":  data.get("last_name", "")
    }

# --- Funkcja pobierająca i filtrująca tylko outbound ---
@st.cache_data(ttl=300)
def fetch_outbound_messages(token, inbox_ids):
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    base_url = "https://api2.frontapp.com/conversations"
    records = []
    teammate_ids = set()

    for inbox in inbox_ids:
        params = {"inbox_id": inbox, "page_size": 100}
        while True:
            r = requests.get(base_url, headers=headers, params=params)
            r.raise_for_status()
            js = r.json()
            for conv in js.get("_results", []):
                cid = conv["id"]
                r2 = requests.get(f"{base_url}/{cid}/messages", headers=headers)
                r2.raise_for_status()
                for m in r2.json().get("_results", []):
                    if m.get("is_inbound", True):
                        continue
                    raw_body = m.get("body", "")
                    text = BeautifulSoup(raw_body, "html.parser").get_text(separator="\n")
                    raw_author = m.get("author", {})
                    if isinstance(raw_author, dict) and raw_author.get("id", "").startswith("tea_"):
                        tid = raw_author["id"]
                        teammate_ids.add(tid)
                        author_ref = tid
                    else:
                        author_ref = (raw_author.get("handle") if isinstance(raw_author, dict)
                                      else str(raw_author) if raw_author else "Unknown")
                    records.append({
                        "Inbox ID":        inbox,
                        "Conversation ID": cid,
                        "Message ID":      m.get("id", ""),
                        "__author_ref":    author_ref,
                        "Extract":         text
                    })
            cursor = js.get("_cursor")
            if not cursor:
                break
            params["cursor"] = cursor

    teammates = {tid: get_teammate_info(token, tid) for tid in teammate_ids}

    df = pd.DataFrame(records)
    def resolve_author(ref):
        if isinstance(ref, str) and ref.startswith("tea_"):
            info = teammates.get(ref, {})
            return f"{info.get('first_name','')} {info.get('last_name','')} ({info.get('username','')})"
        return ref or "Unknown"
    df["Author"] = df["__author_ref"].map(resolve_author)
    df.drop(columns="__author_ref", inplace=True)
    return df

# --- Główny flow aplikacji ---
if st.button("▶️ Pobierz i analizuj OUTBOUND wiadomości"):
    with st.spinner("⏳ Pobieranie wiadomości…"):
        df = fetch_outbound_messages(front_token, INBOX_IDS)

    if df.empty:
        st.warning("❗ Nie znaleziono żadnych wiadomości outbound.")
        st.stop()

    # --- Wybór autorów do wykluczenia ---
    st.sidebar.header("🚫 Wyklucz autorów")
    all_authors = sorted(df["Author"].unique())
    exclude = st.sidebar.multiselect("Wybierz autorów do wykluczenia", all_authors)
    if exclude:
        df = df[~df["Author"].isin(exclude)]
        st.info(f"Wykluczono {len(exclude)} autorów, pozostało {len(df)} wiadomości.")

    if df.empty:
        st.warning("❗ Po wykluczeniu autorów nie pozostały żadne wiadomości.")
        st.stop()

    st.success(f"Pobrano i przygotowano do analizy {len(df)} wiadomości.")
    st.dataframe(df.head(10))

    # --- Async GPT analysis ---
    API_URL = "https://api.openai.com/v1/chat/completions"
    HEADERS  = {"Authorization": f"Bearer {openai_key}", "Content-Type": "application/json"}
    SYSTEM_PROMPT = (
        "Jesteś Menedżerem Customer Service w Bookinghost i oceniasz jakość wiadomości agentów "
        "w skali 1–5. Weź pod uwagę:\n"
        "• empatię i uprzejmość\n"
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
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": rec["Extract"]}
            ],
            "temperature": 0.3,
            "max_tokens": 200
        }
        try:
            async with session.post(API_URL, headers=HEADERS, json=payload) as resp:
                js = await resp.json()
        except Exception as e:
            return f"❌ Network/API error: {e}"
        if "error" in js:
            return f"❌ API error: {js['error'].get('message','Unknown')}"
        choices = js.get("choices")
        if not choices or not isinstance(choices, list):
            return "❌ Unexpected response format: missing 'choices'"
        content = choices[0].get("message", {}).get("content")
        if content is None:
            return "❌ Unexpected response format: missing 'message.content'"
        return content.strip()

    async def run_all(recs, progress, status):
        out = []
        batch = 20
        async with aiohttp.ClientSession() as sess:
            for i in range(0, len(recs), batch):
                chunk = recs[i : i + batch]
                res   = await asyncio.gather(*[analyze_one(sess, r) for r in chunk])
                out.extend(res)
                done = min(i + batch, len(recs))
                progress.progress(done / len(recs))
                status.text(f"Przetworzono: {done}/{len(recs)}")
        return out

    recs     = df.to_dict(orient="records")
    progress = st.progress(0.0)
    status   = st.empty()
    start    = time.time()
    with st.spinner("⚙️ Analiza…"):
        df["Feedback"] = asyncio.run(run_all(recs, progress, status))
    st.success(f"✅ Analiza zakończona w {time.time() - start:.1f}s")

    # --- Parsowanie ocen ---
    def parse_score(txt):
        for l in txt.splitlines():
            if l.lower().startswith("ocena"):
                try:
                    return float(l.split(":")[1].split("/")[0].strip())
                except:
                    pass
        return None
    df["Score"] = df["Feedback"].map(parse_score)

    # --- Raport ---
    st.header("📈 Podsumowanie zespołu")
    st.metric("Średnia ocena", f"{df['Score'].mean():.2f}/5")
    st.metric("Liczba analizowanych wiadomości", len(df))

    st.header("👤 Raport agentów")
    agg = (
        df.groupby("Author")
          .agg(Średnia_ocena=("Score", "mean"), Liczba=("Score", "count"))
          .round(2)
          .reset_index()
    )
    st.dataframe(agg, use_container_width=True)

    st.header("📥 Pobierz pełen raport CSV")
    csv = df.to_csv(index=False, sep=";").encode("utf-8")
    st.download_button("⬇️ Pobierz CSV", data=csv, file_name="outbound_report.csv", mime="text/csv")
