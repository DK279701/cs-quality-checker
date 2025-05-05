import streamlit as st
import pandas as pd
import aiohttp
import asyncio
import time

st.set_page_config(page_title="Szybka analiza CS – Bookinghost", layout="wide")
st.title("⚡ Szybka analiza jakości wiadomości – Bookinghost")

# 1. Klucz API
api_key = st.text_input("🔑 Wklej OpenAI API Key", type="password")
if not api_key:
    st.warning("Wprowadź swój OpenAI API Key, aby zacząć.")
    st.stop()

# 2. Wczytanie CSV
uploaded = st.file_uploader("📁 Wgraj plik CSV (separator `;`)", type="csv")
if not uploaded:
    st.stop()

try:
    df = pd.read_csv(uploaded, sep=";", encoding="utf-8", on_bad_lines="skip")
except Exception as e:
    st.error(f"Błąd wczytywania CSV: {e}")
    st.stop()

if "Author" not in df.columns or "Extract" not in df.columns:
    st.error("Plik musi mieć kolumny `Author` i `Extract`.")
    st.stop()

# 3. Przygotuj listę wiadomości
records = df[["Author", "Extract"]].dropna().to_dict(orient="records")
n = len(records)
st.write(f"Załadowano **{n}** wiadomości do analizy.")

# 4. Endpoint i nagłówki
API_URL = "https://api.openai.com/v1/chat/completions"
HEADERS = {
    "Authorization": f"Bearer {api_key}",
    "Content-Type": "application/json"
}

# 5. System prompt
SYSTEM_PROMPT = (
    "Jesteś Menedżerem Customer Service w Bookinghost i oceniasz jakość wiadomości agentów. "
    "Oceń w skali 1–5 pod kątem:\n"
    "• empatii i uprzejmości\n"
    "• poprawności językowej\n"
    "• zgodności z procedurami\n"
    "• tonu komunikacji (ciepły, profesjonalny)\n\n"
    "Zwróć krótką odpowiedź:\n"
    "Ocena: X/5\n"
    "Uzasadnienie: • punkt 1\n• punkt 2"
)

# 6. Funkcja analizująca jedną wiadomość
async def analyze(session, rec):
    user = rec["Extract"]
    payload = {
        "model": "gpt-3.5-turbo",
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": user}
        ],
        "temperature": 0.3,
        "max_tokens": 200
    }
    try:
        async with session.post(API_URL, headers=HEADERS, json=payload) as resp:
            js = await resp.json()
            return {
                "Author": rec["Author"],
                "Extract": user,
                "Feedback": js["choices"][0]["message"]["content"].strip()
            }
    except Exception as e:
        return {
            "Author": rec["Author"],
            "Extract": user,
            "Feedback": f"❌ Błąd: {e}"
        }

# 7. Batchowa pętla
async def run_all(records, progress_bar, status_text):
    results = []
    batch_size = 20
    async with aiohttp.ClientSession() as session:
        for i in range(0, len(records), batch_size):
            batch = records[i : i + batch_size]
            tasks = [analyze(session, rec) for rec in batch]
            batch_res = await asyncio.gather(*tasks)
            results.extend(batch_res)
            done = min(i + batch_size, len(records))
            progress_bar.progress(done / len(records))
            status_text.text(f"Przetworzono: {done}/{len(records)}")
    return results

# 8. Wywołanie i mierzenie czasu
if st.button("▶️ Rozpocznij analizę"):
    progress = st.progress(0.0)
    status = st.empty()
    start = time.time()
    with st.spinner("Analiza w toku…"):
        results = asyncio.run(run_all(records, progress, status))
    elapsed = time.time() - start
    st.success(f"✅ Zakończono w {elapsed:.1f} s")

    # 9. Prezentacja wyników
    res_df = pd.DataFrame(results)

    # Parsowanie ocen liczbowych
    def parse_score(txt):
        for ln in txt.splitlines():
            if ln.lower().startswith("ocena"):
                try:
                    return float(ln.split(":")[1].split("/")[0].strip())
                except:
                    pass
        return None

    res_df["Score"] = res_df["Feedback"].apply(parse_score)

    st.subheader("📈 Raport zbiorczy")
    team_avg = res_df["Score"].mean()
    st.metric("Średnia ocena zespołu", f"{team_avg:.2f}/5")
    st.metric("Liczba wiadomości", len(res_df))

    st.subheader("👤 Wyniki agentów")
    ag = (
        res_df
        .groupby("Author")
        .agg(Średnia=("Score","mean"), Liczba=("Score","count"))
        .round(2)
        .sort_values("Średnia", ascending=False)
        .reset_index()
    )
    st.dataframe(ag, use_container_width=True)

    st.subheader("📥 Pobierz pełny raport (CSV)")
    st.download_button("⬇️ CSV", data=res_df.to_csv(index=False, sep=";").encode("utf-8"),
                       file_name="raport_quality.csv", mime="text/csv")
