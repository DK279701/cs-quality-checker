import streamlit as st
import pandas as pd
import openai
import asyncio
import aiohttp
import time
from datetime import datetime
import os

# Klucz API
openai.api_key = os.getenv("OPENAI_API_KEY") or st.secrets.get("OPENAI_API_KEY")

st.set_page_config(page_title="CS Quality Checker", layout="wide")
st.title("📊 Narzędzie do analizy jakości wiadomości – Bookinghost")

uploaded_file = st.file_uploader("📎 Wgraj plik CSV", type=["csv"])

if uploaded_file is not None:
    try:
        # Wczytaj plik CSV z domyślnym separatorem ";"
        data = pd.read_csv(uploaded_file, sep=";")
        st.success("✅ Plik wczytany poprawnie.")
    except Exception as e:
        st.error(f"❌ Błąd podczas wczytywania pliku CSV: {e}")
        st.stop()

    # Sprawdzenie wymaganych kolumn
    if "Author" not in data.columns or "Extract" not in data.columns:
        st.error("❌ Plik musi zawierać kolumny 'Author' oraz 'Extract'.")
        st.stop()

    st.write("🧠 Trwa analiza jakości wiadomości...")

    start_time = time.time()

    messages = data[["Author", "Extract"]].dropna()
    messages = messages[messages["Extract"].str.strip().astype(bool)]

    async def analyze_message(session, author, message):
        system_prompt = (
            "Jesteś Managerem Customer Service w Bookinghost. Twoim zadaniem jest ocenić jakość wiadomości wysłanej przez agenta. "
            "Skup się na tonie, poprawności, jasności przekazu, oraz przydatności dla gościa. "
            "Zwróć feedback w formie krótkich punktów. Na końcu dodaj ocenę (1-5) wraz z krótkim uzasadnieniem."
        )

        prompt = f"Wiadomość od agenta:\n\"\"\"\n{message}\n\"\"\"\n\n"

        try:
            response = await session.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {openai.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "gpt-4",
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.4,
                    "max_tokens": 400
                },
                timeout=30,
            )
            result = await response.json()
            content = result["choices"][0]["message"]["content"]
            return {"author": author, "message": message, "feedback": content}
        except Exception as e:
            return {"author": author, "message": message, "feedback": f"Błąd: {e}"}

    async def run_analysis():
        tasks = []
        async with aiohttp.ClientSession() as session:
            for _, row in messages.iterrows():
                tasks.append(analyze_message(session, row["Author"], row["Extract"]))
            return await asyncio.gather(*tasks)

    feedbacks = asyncio.run(run_analysis())

    # Przekształcenie wyników do DataFrame
    feedback_df = pd.DataFrame(feedbacks)

    # Wyciąganie ocen (1-5) z feedbacków
    def extract_score(feedback):
        for line in feedback.splitlines():
            if any(c.isdigit() for c in line):
                for token in line.split():
                    if token.isdigit() and 1 <= int(token) <= 5:
                        return int(token)
        return None

    feedback_df["Score"] = feedback_df["feedback"].apply(extract_score)

    # Raport zbiorczy
    st.header("📋 Raport zespołu")

    team_summary = feedback_df.groupby("author").agg(
        Średnia_ocena=("Score", "mean"),
        Liczba_wiadomości=("Score", "count")
    ).sort_values(by="Średnia_ocena", ascending=False)

    st.dataframe(team_summary.style.format({"Średnia_ocena": "{:.2f}"}))

    st.download_button("⬇️ Pobierz pełny raport (CSV)", data=feedback_df.to_csv(index=False), file_name="raport_jakosci.csv", mime="text/csv")

    st.header("📌 Podsumowanie ogólne")
    avg_score = feedback_df["Score"].mean()
    st.markdown(f"**Średnia ocena zespołu:** `{avg_score:.2f}` / 5")

    st.markdown("🔎 Wnioski (propozycja oparta o średnie oceny):")
    if avg_score >= 4.5:
        st.success("Zespół działa bardzo dobrze. Zachowajcie aktualne standardy!")
    elif avg_score >= 3.5:
        st.warning("Jakość jest dobra, ale są obszary do poprawy.")
    else:
        st.error("Jakość wymaga pilnej poprawy. Wskazane dodatkowe szkolenia i korekta stylu komunikacji.")

    end_time = time.time()
    elapsed = end_time - start_time
    st.info(f"⏱️ Czas analizy: {elapsed:.2f} sekund")
