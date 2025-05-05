import streamlit as st
import pandas as pd
from openai import OpenAI
import time

st.title("System premiowy – analiza jakości wiadomości (GPT-4)")

api_key = st.text_input("Wklej swój OpenAI API Key", type="password")
uploaded_file = st.file_uploader("Wgraj plik CSV z danymi z Front", type="csv")

# Filtrowanie wiadomości po dacie
filter_date = st.date_input("Wybierz datę początkową", min_value=pd.to_datetime('2020-01-01'))

# Filtrowanie wiadomości po agencie
filter_agent = st.selectbox("Wybierz agenta", options=["Wszyscy"])

if api_key and uploaded_file:
    try:
        # Dodajemy możliwość ustawienia kodowania i separatora
        encoding = st.text_input("Podaj kodowanie pliku (np. 'utf-8')", "utf-8")
        sep = st.text_input("Podaj separator pliku (np. ',' lub ';')", ",")

        # Wczytanie danych z pliku CSV z nową obsługą błędnych wierszy
        try:
            data = pd.read_csv(uploaded_file, encoding=encoding, sep=sep, on_bad_lines='skip')
            st.success("Plik załadowany – rozpoczynam analizę...")
        except Exception as e:
            st.error(f"Błąd podczas ładowania pliku CSV: {str(e)}")
            st.stop()

        # Sprawdzamy dostępne kolumny w pliku CSV
        if 'Message date' not in data.columns:
            st.error(f"Kolumna 'Message date' nie została znaleziona w pliku. Dostępne kolumny to: {', '.join(data.columns)}")
            st.stop()

        # Filtrowanie danych po agencie
        if filter_agent != "Wszyscy":
            data = data[data['Author'] == filter_agent]

        if filter_date:
            # Konwersja kolumny 'Message date' na datetime
            data['Message date'] = pd.to_datetime(data['Message date'], errors='coerce')
            data = data[data['Message date'] >= pd.to_datetime(filter_date)]

        # Konfiguracja API OpenAI
        client = OpenAI(api_key=api_key)

        progress = st.progress(0)
        status = st.empty()
        results = []
        agents_feedback = {}

        for i, row in enumerate(data.itertuples()):
            agent = getattr(row, "Author", "")
            message = getattr(row, "Extract", "")
            msg_id = getattr(row, "Message ID", "")

            if not message or pd.isna(message):
                continue

            try:
                # Wytyczne dla GPT-4
                response = client.chat.completions.create(
                    model="gpt-4",
                    messages=[
                        {"role": "system", "content": "Jesteś Managerem Customer Service w Bookinghost. Chcę, aby jakość usług mojego zespołu była jak najwyższa. Oceń jakość wiadomości agenta pod kątem poprawności, zgodności z procedurami, tonu komunikacji oraz jak oceniłbyś ogólną jakość tej wiadomości."},
                        {"role": "user", "content": f"Wiadomość agenta: {message}"}
                    ],
                    temperature=0.3
                )
                feedback = response.choices[0].message.content

            except Exception as e:
                feedback = f"Błąd: {str(e)}"

            # Przechowywanie wyników
            results.append({
                "Message ID": msg_id,
                "Agent": agent,
                "Original Message": message,
                "GPT Feedback": feedback
            })

            # Przechowywanie feedbacku per agent
            if agent not in agents_feedback:
                agents_feedback[agent] = []
            agents_feedback[agent].append(feedback)

            # Status procesu
            status.text(f"Analizuję wiadomość {i + 1} z {len(data)}")
            progress.progress((i + 1) / len(data))

        st.success("Analiza zakończona!")

        # Generowanie raportu ogólnego
        overall_feedback = "Ogólna ocena zespołu:\n"
        for agent, feedbacks in agents_feedback.items():
            overall_feedback += f"\n\nAgent: {agent}\n"
            overall_feedback += "\n".join(feedbacks)

        # Raport z wynikami
        results_df = pd.DataFrame(results)
        st.dataframe(results_df)

        # Pobieranie raportu do pliku CSV
        csv_download = results_df.to_csv(index=False).encode("utf-8")
        st.download_button("Pobierz wyniki jako CSV", csv_download, "analiza.csv", "text/csv")

        # Pokazywanie podsumowania ogólnego feedbacku
        st.subheader("Podsumowanie analizy zespołu")
        st.text_area("Podsumowanie feedbacku", overall_feedback, height=300)

    except Exception as e:
        st.error(f"Błąd podczas przetwarzania pliku: {str(e)}")
else:
    st.warning("Proszę wprowadzić API Key oraz wgrać plik CSV.")
