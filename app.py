import streamlit as st
import pandas as pd
from openai import OpenAI
import time

st.title("System premiowy – analiza jakości wiadomości (GPT-4)")

api_key = st.text_input("Wklej swój OpenAI API Key", type="password")
uploaded_file = st.file_uploader("Wgraj plik CSV z danymi z Front", type="csv")

# Filtrowanie wiadomości po agencie
filter_agent = st.selectbox("Wybierz agenta", options=["Wszyscy"])

if api_key and uploaded_file:
    try:
        # Wczytywanie CSV z domyślnym kodowaniem i separatorem ";"
        try:
            data = pd.read_csv(uploaded_file, encoding='utf-8', sep=';', on_bad_lines='skip')
            st.success("Plik załadowany – rozpoczynam analizę...")
        except Exception as e:
            st.error(f"Błąd podczas ładowania pliku CSV: {str(e)}")
            st.stop()

        # Czyszczenie nazw kolumn z białych znaków
        data.columns = data.columns.str.strip()

        # Filtrowanie danych po agencie
        if filter_agent != "Wszyscy":
            data = data[data['Author'] == filter_agent]

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

            results.append({
                "Message ID": msg_id,
                "Agent": agent,
                "Original Message": message,
                "GPT Feedback": feedback
            })

            if agent not in agents_feedback:
                agents_feedback[agent] = []
            agents_feedback[agent].append(feedback)

            status.text(f"Analizuję wiadomość {i + 1} z {len(data)}")
            progress.progress((i + 1) / len(data))

        st.success("Analiza zakończona!")

        # Raport z wynikami
        results_df = pd.DataFrame(results)
        st.dataframe(results_df)

        csv_download = results_df.to_csv(index=False).encode("utf-8")
        st.download_button("Pobierz wyniki jako CSV", csv_download, "analiza.csv", "text/csv")

        # Feedback ogólny (po agencie)
        st.subheader("Podsumowanie analizy zespołu")
        for agent, feedbacks in agents_feedback.items():
            st.markdown(f"### {agent}")
            summarized_feedback = "\n".join(f"- {f}" for f in feedbacks[:3])  # Pokazujemy tylko pierwsze 3 wpisy
            st.text_area(f"Feedback dla {agent}", summarized_feedback, height=150)

    except Exception as e:
        st.error(f"Błąd podczas przetwarzania pliku: {str(e)}")
else:
    st.warning("Proszę wprowadzić API Key oraz wgrać plik CSV.")
