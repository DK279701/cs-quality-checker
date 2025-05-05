import streamlit as st
import pandas as pd
import time
from openai import OpenAI

st.title("System premiowy – analiza jakości wiadomości (GPT-4)")

# Wczytanie klucza API
api_key = st.text_input("Wklej swój OpenAI API Key", type="password")

# Wczytanie pliku CSV
uploaded_file = st.file_uploader("Wgraj plik CSV z danymi z Front", type="csv")

# Opcje filtrowania
filter_date = st.date_input("Filtruj wiadomości po dacie", min_value=pd.to_datetime("2020-01-01"))
filter_agent = st.selectbox("Filtruj po agencie", options=["Wszyscy", "Agent1", "Agent2", "Agent3"])

if api_key and uploaded_file:
    try:
        # Opcjonalne kodowanie i separator (domyślnie UTF-8, średnik jako separator)
        encoding = st.selectbox("Wybierz kodowanie pliku CSV", ["utf-8", "latin1", "windows-1250"], index=0)
        separator = st.selectbox("Wybierz separator w pliku CSV", [",", ";"], index=1)

        # Próba wczytania pliku CSV
        data = pd.read_csv(uploaded_file, encoding=encoding, sep=separator)

        st.success("Plik załadowany – rozpoczynam analizę...")
        
    except Exception as e:
        st.error(f"Błąd podczas wczytywania pliku CSV: {str(e)}")
        st.stop()

    # Filtrowanie danych
    if filter_agent != "Wszyscy":
        data = data[data['Author'] == filter_agent]
    if filter_date:
        data['Message date'] = pd.to_datetime(data['Message date'])
        data = data[data['Message date'] >= filter_date]

    # Przetwarzanie wiadomości w partiach
    progress = st.progress(0)
    status = st.empty()
    results = []
    agent_stats = {agent: {"messages": 0, "feedback_quality": 0} for agent in data['Author'].unique()}

    # Przetwarzanie w partiach
    batch_size = 10
    for i in range(0, len(data), batch_size):
        batch = data.iloc[i:i+batch_size]
        
        for idx, row in batch.iterrows():
            agent = row["Author"]
            message = row["Extract"]
            msg_id = row["Message ID"]

            if not message or pd.isna(message):
                continue

            try:
                # Generowanie feedbacku z GPT
                response = client.chat.completions.create(
                    model="gpt-4",
                    messages=[
                        {"role": "system", "content": 
                            "Jesteś Managerem Customer Service w Bookinghost, odpowiedzialnym za zapewnienie jak najwyższej jakości usług w zespole. "
                            "Twoim zadaniem jest ocenić jakość wiadomości agenta pod kątem poprawności, zgodności z procedurami i tonu komunikacji, "
                            "z uwzględnieniem najwyższych standardów obsługi klienta."},
                        {"role": "user", "content": f"Wiadomość agenta: {message}"}
                    ],
                    temperature=0.3
                )

                feedback = response.choices[0].message.content
                quality_score = response.choices[0].finish_reason  # Przykładowa ocena jakości

                # Zapisanie wyników
                agent_stats[agent]["messages"] += 1
                # Tylko przykładowa ocena, można dodać bardziej skomplikowane mechanizmy
                agent_stats[agent]["feedback_quality"] += 1 if "good" in feedback.lower() else 0

            except Exception as e:
                feedback = f"Błąd: {str(e)}"

            results.append({
                "Message ID": msg_id,
                "Agent": agent,
                "Original Message": message,
                "GPT Feedback": feedback,
                "Quality Score": quality_score,
                "Argumentacja": f"Ocena oparta na tonie i zgodności z procedurami: {feedback[:100]}"  # Przykładowa argumentacja
            })

        # Aktualizacja statusu
        progress.progress((i + batch_size) / len(data))
        status.text(f"Analizuję wiadomości {i + batch_size} z {len(data)}")

    # Raport całego zespołu
    st.success("Analiza zakończona!")
    results_df = pd.DataFrame(results)
    st.dataframe(results_df)

    # Raport jakości dla każdego agenta
    st.header("Raport jakości pracy agentów")
    agent_report = []
    for agent, stats in agent_stats.items():
        avg_quality = stats["feedback_quality"] / stats["messages"] if stats["messages"] > 0 else 0
        agent_report.append({
            "Agent": agent,
            "Messages Processed": stats["messages"],
            "Avg. Quality Score": avg_quality
        })

    agent_report_df = pd.DataFrame(agent_report)
    st.dataframe(agent_report_df)

    # Podsumowanie
    st.header("Podsumowanie analizy")
    overall_feedback = f"Średnia jakość wiadomości: {results_df['Quality Score'].mean():.2f}"
    st.write(overall_feedback)

    # Możliwość pobrania wyników
    csv_download = results_df.to_csv(index=False).encode("utf-8")
    st.download_button("Pobierz wyniki jako CSV", csv_download, "analiza.csv", "text/csv")
