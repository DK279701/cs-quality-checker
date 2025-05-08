import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
import asyncio
import aiohttp
import time

st.set_page_config(page_title="CS Quality Checker", layout="wide")
st.title("💬 Raport agentów")

# Wprowadzenie tokena i inbox ID
token = st.sidebar.text_input("Front API Token", type="password")
inbox_ids = st.sidebar.text_input("Inbox ID(s) (oddzielone przecinkami)", "")

if not token or not inbox_ids:
    st.warning("Podaj token i przynajmniej jeden Inbox ID, aby kontynuować.")
    st.stop()

@st.cache_data(ttl=300)
def fetch_outbound(token, inbox_ids):
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    base = "https://api2.frontapp.com/conversations"
    rows = []

    for inbox in [i.strip() for i in inbox_ids.split(",") if i.strip()]:
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
                    if m.get("is_inbound", True):
                        continue

                    # strip HTML
                    raw_body = m.get("body", "")
                    text = BeautifulSoup(raw_body, "html.parser").get_text(separator="\n")

                    # poprawne wyciągnięcie autora
                    raw = m.get("author")
                    if isinstance(raw, dict):
                        author_ref = (
                            raw.get("handle") or
                            raw.get("username") or
                            raw.get("name") or
                            raw.get("id") or
                            "Unknown"
                        )
                    else:
                        author_ref = str(raw) if raw else "Unknown"

                    rows.append({
                        "Inbox ID":        inbox,
                        "Conversation ID": cid,
                        "Message ID":      m.get("id", ""),
                        "Author":          author_ref,
                        "Extract":         text
                    })
            cursor = js.get("_cursor")
            if not cursor:
                break
            params["cursor"] = cursor

    return pd.DataFrame(rows)

df = fetch_outbound(token, inbox_ids)

# Unikalne wiadomości po Message ID
df = df.drop_duplicates(subset=["Message ID"]).reset_index(drop=True)

# Wyświetlenie wiadomości
st.subheader("📨 Wiadomości do analizy")
st.dataframe(df[["Author", "Extract"]])

# Ładowanie modelu
openai_key = st.sidebar.text_input("OpenAI API Key", type="password")
if not openai_key:
    st.warning("Podaj swój OpenAI API Key.")
    st.stop()

import openai
openai.api_key = openai_key

# prompt
prompt_template = """
Zanalizuj poniższą wiadomość wysłaną przez agenta do klienta i oceń ją w skali 1–5, gdzie:
- 5: wzorowa wiadomość – empatyczna, wyczerpująca, dopasowana do sytuacji
- 4: bardzo dobra wiadomość, z drobnymi brakami
- 3: przeciętna, poprawna, ale bez zaangażowania
- 2: mało pomocna, z brakami w treści lub tonie
- 1: nieakceptowalna – niegrzeczna, błędna lub pusta

Zwróć tylko ocenę liczbową i bardzo krótki feedback (1 zdanie) – np. „Poprawna wiadomość, ale bez personalizacji.”

Wiadomość:
\"\"\"
{message}
\"\"\"
"""

async def analyze_one(session, row):
    msg = row["Extract"]
    prompt = prompt_template.format(message=msg)
    try:
        async with session.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {openai.api_key}",
                "Content-Type": "application/json"
            },
            json={
                "model": "gpt-4",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0,
            },
        ) as resp:
            js = await resp.json()
            return js["choices"][0]["message"]["content"].strip()
    except Exception as e:
        return f"Błąd: {str(e)}"

async def run_all(rows, progress, status):
    async with aiohttp.ClientSession() as session:
        results = []
        total = len(rows)
        for i, row in enumerate(rows):
            res = await analyze_one(session, row)
            results.append(res)
            progress.progress((i + 1) / total)
            status.text(f"Analizuję wiadomość {i + 1} z {total}...")
        return results

st.subheader("⚙️ Analiza wiadomości")

if st.button("Rozpocznij analizę"):
    with st.spinner("Analiza wiadomości w toku..."):
        recs = df.to_dict("records")
        progress = st.progress(0)
        status = st.empty()
        df["Feedback"] = asyncio.run(run_all(recs, progress, status))
        st.success("Gotowe!")

    # Grupowanie po autorze
    st.subheader("👤 Raport agentów")
    def extract_score(text):
        try:
            return float(text.strip().split()[0].replace(",", "."))
        except:
            return None

    df["Score"] = df["Feedback"].apply(extract_score)
    report = df.groupby("Author")["Score"].agg(["mean", "count"]).reset_index()
    report.columns = ["Author", "Śr", "Cnt"]
    st.dataframe(report)

    st.subheader("📥 Pobierz CSV")
    st.download_button("⬇️ CSV", df.to_csv(index=False), file_name="analiza_wiadomosci.csv", mime="text/csv")
