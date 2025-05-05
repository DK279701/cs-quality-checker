import streamlit as st
import pandas as pd
from openai import OpenAI
import time

st.set_page_config(page_title="Analiza jakości wiadomości – Bookinghost", layout="wide")
st.title("📊 Narzędzie do analizy jakości obsługi klienta w Bookinghost")

# 1. Klucz API
api_key = st.text_input("🔑 Wklej swój OpenAI API Key", type="password")
if not api_key:
    st.warning("Wprowadź swój OpenAI API Key, aby rozpocząć.")
    st.stop()

# 2. Wczytanie pliku CSV
uploaded_file = st.file_uploader("📁 Wgraj plik CSV (separator `;`)", type=["csv"])
if not uploaded_file:
    st.stop()

try:
    df = pd.read_csv(uploaded_file, sep=";", encoding="utf-8", on_bad_lines="skip")
except Exception as e:
    st.error(f"Błąd podczas wczytywania pliku CSV:\n{e}")
    st.stop()

if "Author" not in df.columns or "Extract" not in df.columns:
    st.error("Plik musi zawierać kolumny `'Author'` i `'Extract'`.")
    st.stop()

# 3. Inicjalizacja klienta OpenAI
client = OpenAI(api_key=api_key)

# 4. Opcjonalny filtr po agencie
agents = ["Wszyscy"] + sorted(df["Author"].dropna().unique().tolist())
selected = st.selectbox("👤 Wybierz agenta", agents)
if selected != "Wszyscy":
    df = df[df["Author"] == selected]

# 5. Limit wiadomości (opcjonalnie)
max_n = st.slider("🔢 Maksymalna liczba wiadomości do analizy", 10, min(1000, len(df)), 100)
df = df.head(max_n)

# 6. Przygotowanie do pętli analizy
progress = st.progress(0)
status = st.empty()
results = []

system_prompt = (
    "Jesteś Menedżerem Customer Service w Bookinghost. Twoim zadaniem jest "
    "ocenić, w skali 1–5, jakość odpowiedzi agenta na przesłaną wiadomość. "
    "Weź pod uwagę:\n"
    "- empatię i uprzejmość\n"
    "- poprawność językową\n"
    "- zgodność z procedurami i wiedzą produktową\n"
    "- ton komunikacji (ciepły, profesjonalny, proaktywny)\n\n"
    "Twoja odpowiedź powinna zawierać:\n"
    "Ocena: X/5\n"
    "Uzasadnienie: • punkt 1\n• punkt 2"
)

# 7. Pętla analizująca wiadomości
start = time.time()
for i, row in enumerate(df.itertuples(index=False), 1):
    try:
        resp = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": row.Extract}
            ],
            temperature=0.3,
        )
        feedback = resp.choices[0].message.content.strip()
    except Exception as e:
        feedback = f"Błąd analizy: {e}"

    results.append({
        "Author": row.Author,
        "Extract": row.Extract,
        "Feedback": feedback
    })

    progress.progress(i / len(df))
    status.text(f"Przetworzono wiadomości: {i}/{len(df)}")

elapsed = time.time() - start
st.success(f"✅ Analiza zakończona w {elapsed:.1f} s")

# 8. Zapis wyników i prezentacja
res_df = pd.DataFrame(results)

# Wyciągnięcie ocen liczbowych
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
st.metric("Liczba analizowanych wiadomości", len(res_df))

st.subheader("👤 Wyniki poszczególnych agentów")
agent_summary = (
    res_df.groupby("Author")
          .agg(Średnia_ocena=("Score", "mean"), Liczba=("Score", "count"))
          .sort_values("Średnia_ocena", ascending=False)
          .reset_index()
)
st.dataframe(agent_summary.style.format({"Średnia_ocena": "{:.2f}"}), use_container_width=True)

st.subheader("📥 Pobierz pełen raport (CSV)")
csv_data = res_df.to_csv(index=False, sep=";").encode("utf-8")
st.download_button("⬇️ Pobierz CSV", data=csv_data, file_name="raport_quality.csv", mime="text/csv")
