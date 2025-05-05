import streamlit as st
import pandas as pd
import openai
import time
import asyncio
import aiohttp
from datetime import datetime

st.set_page_config(page_title="Analiza jakości wiadomości CS", layout="wide")
st.title("📊 Analiza jakości obsługi klienta Bookinghost")

api_key = st.text_input("🔑 Wklej swój OpenAI API Key", type="password")

uploaded_file = st.file_uploader("📁 Wgraj plik CSV z wiadomościami (separator ;)", type=["csv"])

if api_key and uploaded_file:
    openai.api_key = api_key

    try:
        data = pd.read_csv(uploaded_file, sep=";", encoding="utf-8")
    except Exception as e:
        st.error(f"Błąd podczas wczytywania pliku: {e}")
        st.stop()

    if "Extract" not in data.columns or "Author" not in data.columns:
        st.error("Plik musi zawierać kolumny 'Extract' i 'Author'.")
        st.stop()

    messages_to_check = data[["Extract", "Author"]].dropna().reset_index(drop=True)

    st.success(f"✅ Załadowano {len(messages_to_check)} wiadomości do analizy.")

    async def analyze_message(session, message):
        prompt = (
            "Jesteś Managerem Działu Obsługi Klienta w firmie Bookinghost. "
            "Oceniasz jakość odpowiedzi agenta w wiadomości klienta. "
            "Oceń jakość komunikacji w skali 1-5. Weź pod uwagę:\n"
            "- empatię\n"
            "- profesjonalizm\n"
            "- spójność i zrozumiałość\n"
            "- konkretność i przydatność odpowiedzi\n"
            "- ton komunikacji zgodny z marką Bookinghost (ciepły, profesjonalny, proaktywny)\n\n"
            "Zwróć tylko krótką ocenę w postaci:\n"
            "Ocena: X/5\n"
            "Uzasadnienie: • punkt 1\n• punkt 2"
        )

        try:
            response = await session.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "gpt-4",
                    "messages": [
                        {"role": "system", "content": prompt},
                        {"role": "user", "content": message},
                    ],
                    "temperature": 0.3,
                },
                timeout=30
            )
            result = await response.json()
            return result["choices"][0]["message"]["content"]
        except Exception as e:
            return f"Error: {e}"

    async def process_messages():
        results = []
        async with aiohttp.ClientSession() as session:
            tasks = [analyze_message(session, row["Extract"]) for _, row in messages_to_check.iterrows()]
            results = await asyncio.gather(*tasks)
        return results

    if st.button("▶️ Rozpocznij analizę"):
        start = time.time()
        with st.spinner("Analiza w toku..."):
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            feedbacks = loop.run_until_complete(process_messages())
            loop.close()

        data["Feedback"] = feedbacks

        def extract_score(text):
            try:
                return int([line for line in text.splitlines() if "Ocena" in line][0].split(":")[1].split("/")[0])
            except:
                return None

        data["Score"] = data["Feedback"].apply(extract_score)

        # Podsumowanie
        summary = data.groupby("Author").agg(
            Średnia_ocena=("Score", "mean"),
            Liczba_wiadomości=("Score", "count")
        ).sort_values(by="Średnia_ocena", ascending=False).reset_index()

        team_avg = round(data["Score"].mean(), 2)
        total_messages = len(data)

        st.subheader("📈 Podsumowanie zespołu")
        st.metric("Średnia ocena zespołu", f"{team_avg}/5")
        st.metric("Liczba sprawdzonych wiadomości", total_messages)

        st.subheader("👤 Wyniki poszczególnych agentów")
        st.dataframe(summary, use_container_width=True)

        # Insighty
        st.subheader("🧠 Insighty i rekomendacje")
        insights = (
            "• Agentów z niższą średnią warto objąć dodatkowym mentoringiem.\n"
            "• Wysoka jakość (4.5+): świadczy o dobrym tonie, empatii i konkretności.\n"
            "• Częste problemy to: brak konkretu, zbyt techniczny język, brak propozycji rozwiązania.\n"
            "• Rekomendacja: przygotować checklistę idealnej odpowiedzi oraz wdrożyć przegląd tygodniowy."
        )
        st.markdown(insights)

        # Zapis CSV
        now = datetime.now().strftime("%Y-%m-%d_%H-%M")
        csv_name = f"raport_jakosci_{now}.csv"
        data.to_csv(csv_name, index=False)

        st.download_button(
            label="📥 Pobierz szczegółowy raport (CSV)",
            data=data.to_csv(index=False).encode('utf-8'),
            file_name=csv_name,
            mime="text/csv"
        )

        end = time.time()
        st.info(f"⏱️ Analiza zajęła {round(end - start, 2)} sekund.")

