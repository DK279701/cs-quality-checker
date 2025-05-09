import streamlit as st
import pandas as pd
import requests
import aiohttp
import asyncio
import time
from bs4 import BeautifulSoup

st.set_page_config(page_title="CS Quality Checker", layout="wide")
st.title("📥 Produkcyjna wersja: analiza OUTBOUND wiadomości")

# — Sidebar: API keys —
st.sidebar.header("🔑 Klucze API")
front_token = st.sidebar.text_input("Front API Token", type="password")
openai_key  = st.sidebar.text_input("OpenAI API Key",   type="password")
if not front_token or not openai_key:
    st.sidebar.warning("Podaj oba klucze API (Front i OpenAI).")
    st.stop()

# — Stałe inboxy i dozwolone agent IDs —
INBOX_IDS = ["inb_a3xxy","inb_d2uom","inb_d2xee"]
ALLOWED_IDS = {
    "tea_a2k46","tea_cj1ue","tea_cocnq","tea_cs6hi","tea_gs47r",
    "tea_h7x3r","tea_hjadz","tea_hm6zb","tea_hn7h3","tea_hn7iv",
    "tea_hnytz","tea_hnyvr","tea_97fh2"
}

st.sidebar.markdown("**Inboxy (stałe):**")
st.sidebar.write("- Customer Service (`inb_a3xxy`)")
st.sidebar.write("- Chat Airbnb – New (`inb_d2uom`)")
st.sidebar.write("- Chat Booking – New (`inb_d2xee`)")

# — Bezpieczne GET z obsługą błędów —
def safe_get(url, headers, params=None):
    try:
        r = requests.get(url, headers=headers, params=params, timeout=15)
        r.raise_for_status()
        return r.json(), None
    except Exception as e:
        msg = str(e)
        try:
            msg += f" | {r.status_code} {r.text}"
        except:
            pass
        return None, msg

# — Zbieranie wszystkich outbound-owych wiadomości z paginacją —
def collect_data(token, inbox_ids, prog):
    headers = {"Authorization": f"Bearer {token}"}
    records = []
    total_inboxes = len(inbox_ids)

    for idx, inbox in enumerate(inbox_ids, start=1):
        # 1. Paginujemy konwersacje
        convs = []
        url_conv = f"https://api2.frontapp.com/inboxes/{inbox}/conversations"
        params_c = {"limit": 100}
        while True:
            js_c, err_c = safe_get(url_conv, headers, params_c)
            if err_c:
                st.error(f"Błąd pobierania konwersacji `{inbox}`: {err_c}")
                break
            convs.extend(js_c.get("_results", []))
            cursor_c = js_c.get("_cursor")
            if not cursor_c:
                break
            params_c["cursor"] = cursor_c

        # 2. Dla każdej konwersacji paginujemy wiadomości
        for conv in convs:
            cid = conv.get("id")
            url_msg = f"https://api2.frontapp.com/conversations/{cid}/messages"
            params_m = {"limit": 100}
            while True:
                js_m, err_m = safe_get(url_msg, headers, params_m)
                if err_m:
                    st.warning(f"Pominięcie wiadomości z konw `{cid}` ze względu na błąd: {err_m}")
                    break
                for m in js_m.get("_results", []):
                    # tylko outbound
                    if m.get("is_inbound", True):
                        continue
                    # filtr po agentach
                    raw = m.get("author") or {}
                    author_id = raw.get("id") if isinstance(raw, dict) else None
                    if author_id not in ALLOWED_IDS:
                        continue
                    # strip HTML
                    text = BeautifulSoup(m.get("body",""), "html.parser").get_text("\n")
                    # czytelny Author
                    if isinstance(raw, dict):
                        name   = (raw.get("first_name","") + " " + raw.get("last_name","")).strip()
                        handle = raw.get("username") or raw.get("handle") or ""
                        author = f"{name} ({handle})" if handle else name
                    else:
                        author = str(raw)
                    records.append({
                        "Inbox ID":        inbox,
                        "Conversation ID": cid,
                        "Message ID":      m.get("id",""),
                        "Author ID":       author_id,
                        "Author":          author,
                        "Extract":         text
                    })
                cursor_m = js_m.get("_cursor")
                if not cursor_m:
                    break
                params_m["cursor"] = cursor_m

        # aktualizacja paska postępu po każdym inboxie
        prog.progress(idx / total_inboxes)

    return pd.DataFrame(records)

# — UI: przycisk i pasek postępu —
fetch_prog = st.sidebar.progress(0.0)

if st.button("▶️ Pobierz i analizuj wiadomości"):
    with st.spinner("⏳ Pobieram i filtruję…"):
        df = collect_data(front_token, INBOX_IDS, fetch_prog)

    if df.empty:
        st.warning("❗ Nie znaleziono żadnych wiadomości outbound od wybranych agentów.")
        st.stop()

    st.success(f"Pobrano {len(df)} wiadomości od {df['Author'].nunique()} agentów.")
    st.dataframe(df[["Author","Extract"]].head(10), use_container_width=True)

    # — Analiza GPT —
    API_URL = "https://api.openai.com/v1/chat/completions"
    HEADERS = {"Authorization": f"Bearer {openai_key}", "Content-Type":"application/json"}
    SYSTEM = (
        "Jesteś Menedżerem CS w Bookinghost i oceniasz jakość wiadomości agentów "
        "w skali 1–5. Weź pod uwagę empatię, poprawność, zgodność z procedurami i ton."
        "Odpowiedz formatem:\nOcena: X/5\nUzasadnienie: • pkt1\n• pkt2"
    )

    async def analyze_one(sess, rec):
        payload = {
            "model": "gpt-3.5-turbo",
            "messages": [
                {"role":"system","content":SYSTEM},
                {"role":"user",  "content":rec["Extract"]}
            ],
            "temperature": 0.3,
            "max_tokens": 200
        }
        async with sess.post(API_URL, headers=HEADERS, json=payload) as r:
            js = await r.json()
        if js.get("error"):
            return f"❌ {js['error']['message']}"
        choices = js.get("choices") or []
        return choices[0]["message"]["content"].strip() if choices else "❌ no choices"

    async def run_all(recs, prog, stat):
        out=[]; batch=20
        async with aiohttp.ClientSession() as sess:
            total = len(recs)
            for i in range(0, total, batch):
                chunk = recs[i:i+batch]
                res = await asyncio.gather(*[analyze_one(sess, r) for r in chunk])
                out.extend(res)
                done = min(i+batch, total)
                prog.progress(done/total)
                stat.text(f"Analizowano {done}/{total}")
        return out

    recs = df.to_dict("records")
    analyze_prog = st.progress(0.0)
    analyze_stat = st.empty()
    start = time.time()

    with st.spinner("⚙️ Analiza…"):
        df["Feedback"] = asyncio.run(run_all(recs, analyze_prog, analyze_stat))
    st.success(f"✅ Analiza zakończona w {time.time()-start:.1f}s")

    # — Parsowanie ocen i raport —
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
          .round(2).reset_index()
    )
    st.dataframe(report, use_container_width=True)

    st.header("📥 Pobierz raport CSV")
    csv = df.to_csv(index=False, sep=";").encode("utf-8")
    st.download_button("⬇️ Pobierz CSV", csv, "report.csv", "text/csv")
