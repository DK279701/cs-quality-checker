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

# --- Funkcja pobierająca i filtrująca tylko outbound ---
@st.cache_data(ttl=300)
def fetch_outbound_messages(token, inbox_ids):
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    base_url = "https://api2.frontapp.com/conversations"
    records = []
    debug_auth = []

    for inbox in inbox_ids:
        params = {"inbox_id": inbox, "page_size": 100}
        while True:
            r = requests.get(base_url, headers=headers, params=params)
            r.raise_for_status()
            js = r.json()
            for conv in js.get("_results", []):
                cid = conv.get("id", "")
                r2 = requests.get(f"{base_url}/{cid}/messages", headers=headers)
                r2.raise_for_status()
                for m in r2.json().get("_results", []):
                    if m.get("is_inbound", True):
                        continue

                    # Strip HTML
                    raw_body = m.get("body", "")
                    text = BeautifulSoup(raw_body, "html.parser").get_text(separator="\n")

                    # Extract author
                    raw_author = m.get("author")
                    if isinstance(raw_author, dict):
                        author = raw_author.get("handle") or raw_author.get("name") or "Unknown"
                    else:
                        author = str(raw_author) if raw_author else "Unknown"
                    if author == "Unknown":
                        debug_auth.append(raw_author)

                    records.append({
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

    df = pd.DataFrame(records)
    df["_raw_author_debug"] = pd.Series(debug_auth + [None] * (len(df) - len(debug_auth)))
    return df

# --- Main flow ---
if st.button("▶️ Pobierz i analizuj OUTBOUND wiadomości"):
    with st.spinner("⏳ Pobieranie wiadomości…"):
        df = fetch_outbound_messages(front_token, INBOX_IDS)

    if df.empty:
        st.warning("❗ Nie znaleziono żadnych wiadomości outbound w wybranych inboxach.")
        st.stop()

    st.success(f"Pobrano {len(df)} wiadomości outbound.")
    st.dataframe(df.head(10))

    # Show raw-author debug
    st.subheader("🔍 Surowe wartości author (debug)")
    st.dataframe(df[["_raw_author_debug"]].dropna().head(10))

    # --- Async GPT analysis setup ---
    API_URL = "https://api.openai.com/v1/chat/completions"
    HEADERS = {"Authorization": f"Bearer {openai_key}", "Content-Type": "application/json"}
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
        batch_size = 20
        async with aiohttp.ClientSession() as sess:
            for i in range(0, len(recs), batch_size):
                batch = recs[i : i + batch_size]
                tasks = [analyze_one(sess, r) for r in batch]
                res = await asyncio.gather(*tasks)
                out.extend(res)
                done = min(i + batch_size, len(recs))
                progress.progress(done / len(recs))
                status.text(f"Przetworzono: {done}/{len(recs)}")
        return out

    recs     = df.to_dict(orient="records")
    progress = st.progress(0.0)
    status   = st.empty()
    start    = time.time()
    with st.spinner("⚙️ Analiza…"):
        df["Feedback"] = asyncio.run(run_all(recs, progress, status))
    elapsed = time.time() - start
    st.success(f"✅ Analiza zakończona w {elapsed:.1f}s")

    # Parse scores
    def parse_score(txt):
        for l in txt.splitlines():
            if l.lower().startswith("ocena"):
                try:
                    return float(l.split(":")[1].split("/")[0].strip())
                except:
                    pass
        return None

    df["Score"] = df["Feedback"].map(parse_score)

    # --- Results / report ---
    st.header("📈 Podsumowanie zespołu")
    st.metric("Średnia ocena", f"{df['Score'].mean():.2f}/5")
    st.metric("Liczba wiadomości", len(df))

    st.header("👤 Raport agentów")
    agg = (
        df.groupby("Author")
          .agg(Średnia_ocena=("Score", "mean"),
               Liczba=("Score", "count"))
          .round(2)
          .reset_index()
    )
    st.dataframe(agg, use_container_width=True)

    st.header("📥 Pobierz pełen raport CSV")
    csv = df.to_csv(index=False, sep=";").encode("utf-8")
    st.download_button("⬇️ Pobierz CSV", data=csv, file_name="outbound_report.csv", mime="text/csv")
