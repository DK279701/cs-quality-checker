import streamlit as st
import pandas as pd
from openai import OpenAI
import time

# Tytuł aplikacji
st.title("System premiowy – analiza jakości wiadomości (GPT-3.5)")

# Klucz API i plik CSV
api_key = st.text_input("Wklej swój OpenAI API Key", type="password")
uploaded_file = st.file_uploader("Wgraj plik CSV z danymi z Front", type="csv")

if api_key and uploaded_file:
    # Wczytanie danych
    data = pd.read_csv(uploaded_file)

    # Filtracja pustych wiadomości
    data = data.dropna(subset=["Extract"])
    
    # Ustawienie limitu liczby wiadomości do analizy
    max_msgs = st.slider("Ile wiadomości chcesz przeanalizować?", 1, len(data), 50)

    # Połączenie z OpenAI
    client = OpenAI(api_key=api_key)

    st.success("Plik załadowany – rozpoczynam analizę...")

    # Przygotowanie do analizy
    progress = st.progress(0)
    status = st.empty()
    results = []
    agent_feedback = {}

    for i, row in enumerate(data.itertuples()):
        if i >= max_msgs:
            break

        agent = getattr(row, "Author", "")
        message = getattr(row, "Extract", "")
        msg_id = getattr(row, "Message_ID", "")

        # Pominięcie pustych wiadomości
        if not message or pd.isna(message):
            continue

        try:
            # Użycie modelu GPT-3.5-Turbo dla szybszej analizy
            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "Jesteś ekspertem od obsługi klienta. Oceń jakość wiadomości agenta pod kątem poprawności, zgodności z procedurami i tonu komunikacji."},
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

        # Zbieranie ocen per agent
        if agent not in agent_feedback:
            agent_feedback[agent] = {"feedbacks": [], "count": 0}
        agent_feedback[agent]["feedbacks"].append(feedback)
        agent_feedback[agent]["count"] += 1

        status.text(f"Analizuję wiadomość {i + 1} z {len(data)}")
        progress.progress((i + 1) / len(data))

    st.success("Analiza zakończona!")

    # Wyświetlenie wyników w tabeli
    results_df = pd.DataFrame(results)
    st.dataframe(results_df)

    # Opcja pobrania wyników jako CSV
    csv_download = results_df.to_csv(index=False).encode("utf-8")
    st.download_button("Pobierz wyniki jako CSV", csv_download, "analiza.csv", "text/csv")

    # Przygotowanie raportu per agent
    agent_report = []
    for agent, feedback_data in agent_feedback.items():
        average_feedback = "\n".join(feedback_data["feedbacks"])  # Możemy tu dodać średnią ocenę lub szczegóły
        agent_report.append({
            "Agent": agent,
            "Total Messages": feedback_data["count"],
            "Average Feedback": average_feedback
        })

    agent_report_df = pd.DataFrame(agent_report)

    st.subheader("Raport per agent:")
    st.dataframe(agent_report_df)

    # Opcja pobrania raportu per agent
    agent_csv_download = agent_report_df.to_csv(index=False).encode("utf-8")
    st.download_button("Pobierz raport per agent", agent_csv_download, "raport_per_agent.csv", "text/csv")
