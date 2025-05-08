import streamlit as st
import pandas as pd
import requests
import aiohttp
import asyncio
import time
from bs4 import BeautifulSoup
from datetime import datetime, timedelta

st.set_page_config(page_title="CS Quality Checker", layout="wide")
st.title("📥 Analiza OUTBOUND wiadomości (ostatnie 7 dni) – odporna na błędy HTTP")

# --- Sidebar: API keys ---
st.sidebar.header("🔑 Klucze API")
front_token = st.sidebar.text_input("Front API Token", type="password")
openai_key  = st.sidebar.text_input("OpenAI API Key",   type="password")
if not front_token or not openai_key:
    st.sidebar.warning("Podaj oba klucze API.")
    st.stop()

# --- Stałe inboxy i agent IDs ---
INBOX_IDS = ["inb_a3xxy","inb_d2uom","inb_d2xee"]
ALLOWED_IDS = {
    "tea_a2k46","tea_cj1ue","tea_cocnq","tea_cs6hi","tea_gs47r",
    "tea_h7x3r","tea_hjadz","tea_hm6zb","tea_hn7h3","tea_hn7iv",
    "tea_hnytz","tea_hnyvr","tea_97fh2"
}

seven_days_ago = pd.to_datetime(datetime.utcnow() - timedelta(days=7), utc=True)

def safe_get(url, headers, params=None):
    """Wrapper around requests.get that returns (json, None) or (None, error_msg)."""
    try:
        r = requests.get(url, headers=headers, params=params, timeout=15)
        r.raise_for_status()
        return r.json(), None
    except requests.exceptions.RequestException as e:
        # Grab status and text if available
        msg = f"{e}"
        try:
            msg += f" | Response: {r.status_code} {r.text}"
        except:
            pass
        return None, msg

def fetch_conversations(token, inbox):
    url = "https://api2.frontapp.com/conversations"
    headers = {"Authorization": f"Bearer {token}"}
    params = {"inbox_id": inbox, "page_size": 100}
    results = []
    while True:
        js, err = safe_get(url, headers, params)
        if err:
            st.error(f"❌ Błąd pobierania konwersji dla inbox `{inbox}`: {err}")
            break
        results.extend(js.get("_results", []))
        cursor = js.get("_cursor")
        if not cursor:
            break
        params["cursor"] = cursor
    return results

def fetch_messages(token, conv_id):
    url = f"https://api2.frontapp.com/conversations/{conv_id}/messages"
    headers = {"Authorization": f"Bearer {token}"}
    js, err = safe_get(url, headers)
    if err:
        st.error(f"❌ Błąd pobierania wiadomości dla konw `{conv_id}`: {err}")
        return []
    return js.get("_results", [])

def collect_data(token, inbox_ids, since_ts, fetch_prog):
    records = []
    total = len(inbox_ids)
    for idx, inbox in enumerate(inbox_ids, start=1):
        convs = fetch_conversations(token, inbox)
        for c in convs:
            cid = c.get("id")
            msgs = fetch_messages(token, cid)
            for m in msgs:
                if m.get("is_inbound", True):
                    continue
                created = m.get("created_at")
                dt = pd.to_datetime(created, utc=True) if created else None
                if dt is None or dt < since_ts:
                    continue
                raw = m.get("author") or {}
                author_id = raw.get("id") if isinstance(raw, dict) else None
                if author_id not in ALLOWED_IDS:
                    continue
                text = BeautifulSoup(m.get("body",""), "html.parser").get_text("\n")
                if isinstance(raw, dict):
                    name = (raw.get("first_name","") + " " + raw.get("last_name","")).strip()
                    handle = raw.get("username") or raw.get("handle") or ""
                    author = f"{name} ({handle})" if handle else name
                else:
                    author = str(raw)
                records.append({
                    "Created At": dt,
                    "Inbox ID":   inbox,
                    "Conv ID":    cid,
                    "Message ID": m.get("id",""),
                    "Author ID":  author_id,
                    "Author":     author,
                    "Extract":    text
                })
        fetch_prog.progress(idx/total)
    return pd.DataFrame(records)

# Paski postępu
fetch_prog   = st.sidebar.progress(0.0)
analyze_prog = st.sidebar.progress(0.0)
analyze_stat = st.sidebar.empty()

if st.button("▶️ Pobierz i analizuj"):
    with st.spinner("⏳ Pobieram i filtruję…"):
        df = collect_data(front_token, INBOX_IDS, seven_days_ago, fetch_prog)
    if df.empty:
        st.warning("Brak wiadomości do analizy.")
        st.stop()
    st.success(f"Pobrano {len(df)} wiadomości.")
    st.dataframe(df[["Created At","Author","Extract"]].head(10), use_container_width=True)

    # GPT analysis
    API_URL = "https://api.openai.com/v1/chat/completions"
    HEADERS = {"Authorization":f"Bearer {openai_key}", "Content-Type":"application/json"}
    SYSTEM = (
        "Jesteś Menedżerem CS w Bookinghost, oceniasz jakościowo "
        "wiadomości w skali 1–5 (empatia, poprawność, procedury, ton).\n"
        "Odpowiedz w formacie:\nOcena: X/5\nUzasadnienie: • pkt1\n• pkt2"
    )

    async def analyze_one(sess, rec):
        payload = {"model":"gpt-3.5-turbo",
                   "messages":[{"role":"system","content":SYSTEM},
                               {"role":"user","content":rec["Extract"]}],
                   "temperature":0.3,"max_tokens":200}
        try:
            async with sess.post(API_URL, headers=HEADERS, json=payload) as r:
                js = await r.json()
        except Exception as e:
            return f"❌ API error: {e}"
        if js.get("error"):
            return f"❌ {js['error'].get('message','')}"
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
                prog.progress(done/total); stat.text(f"Analizowano {done}/{total}")
        return out

    recs = df.to_dict("records")
    start = time.time()
    with st.spinner("⚙️ Analiza…"):
        df["Feedback"] = asyncio.run(run_all(recs, analyze_prog, analyze_stat))
    st.success(f"✅ Analiza zakończona w {time.time()-start:.1f}s")

    df["Score"] = df["Feedback"].map(lambda t: float(t.split()[1].split("/")[0]) if t.lower().startswith("ocena") else None)

    st.header("📈 Podsumowanie")
    st.metric("Średnia", f"{df['Score'].mean():.2f}/5")
    st.metric("Wiadomości", len(df))

    st.header("👤 Raport agentów")
    rep = df.groupby("Author").agg(Śr=("Score","mean"),Cnt=("Score","count")).round(2).reset_index()
    st.dataframe(rep, use_container_width=True)

    st.header("📥 Pobierz CSV")
    csv = df.to_csv(index=False, sep=";").encode("utf-8")
    st.download_button("⬇ CSV", data=csv, file_name="report.csv", mime="text/csv")
