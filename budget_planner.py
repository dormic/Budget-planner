import streamlit as st
from datetime import date, datetime, timedelta
import json, os, requests
from collections import defaultdict

st.set_page_config(page_title="AI-Планировщик 💰", page_icon="💰")
DATA_FILE = "budget_data.json"
OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "qwen2.5:7b"

# ========== КЭШИРОВАНИЕ ==========
def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "categories": [],
        "expenses_history": [],
        "income_history": [],
        "saved_amounts": {},
        "deadlines": {}
    }

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    st.session_state.saved = data

if 'saved' not in st.session_state:
    st.session_state.saved = load_data()

saved = st.session_state.saved
today = date.today()

# ========== АВТООБНУЛЕНИЕ ПО ДЕДЛАЙНАМ ==========
changed = False
for cat_name, deadline_str in list(saved.get("deadlines", {}).items()):
    if deadline_str:
        deadline = datetime.strptime(deadline_str, "%Y-%m-%d").date()
        if deadline <= today:
            old_amount = saved["saved_amounts"].get(cat_name, 0)
            if old_amount > 0:
                saved["saved_amounts"][cat_name] = 0
                changed = True
                # Переносим дедлайн на следующий месяц
                month = today.month + 1 if today.month < 12 else 1
                year = today.year if today.month < 12 else today.year + 1
                saved["deadlines"][cat_name] = date(year, month, 1).strftime("%Y-%m-%d")

if changed:
    save_data(saved)

# ========== OLLAMA ==========
def ask_ollama(prompt):
    try:
        resp = requests.post(OLLAMA_URL, json={
            "model": OLLAMA_MODEL, "prompt": prompt,
            "stream": False, "options": {"temperature": 0.1, "max_tokens": 400}
        }, timeout=60)
        return resp.json()["response"].strip()
    except:
        return "⚠️ Ollama не отвечает"

def ai_categorize(raw_text, categories):
    cat_names = [c["name"] for c in categories] + ["Другое"]
    cat_list = ", ".join(cat_names)
    prompt = f"""Ты — финансовый ассистент. Верни ТОЛЬКО JSON.
Трата: "{raw_text}"
Формат: {{"category": "категория", "amount": число, "comment": "комментарий"}}
Категории: {cat_list}.
Если сумма не указана — 0."""
    response = ask_ollama(prompt)
    try:
        start = response.find('{')
        end = response.rfind('}') + 1
        if start >= 0 and end > start:
            return json.loads(response[start:end])
    except:
        pass
    return {"category": "Другое", "amount": 0, "comment": "Не удалось распознать"}

def ai_distribute(income, categories, saved_amounts):
    items_text = "\n".join([
        f"- {c['name']}: лимит {c['limit']}р, отложено {saved_amounts.get(c['name'], 0)}р, обязательная: {c.get('mandatory', False)}"
        for c in categories
    ])
    prompt = f"""Ты — финансовый ассистент. Распредели поступление {income}р по статьям.
Правила: не больше 50% от недостающей суммы на каждую статью. Обязательные статьи — в первую очередь.
Верни ТОЛЬКО JSON: {{"распределение": [{{"статья": "название", "сумма": число, "причина": "почему"}}], "остаток": число, "совет": "общий совет"}}
Статьи:
{items_text}"""
    response = ask_ollama(prompt)
    try:
        start = response.find('{')
        end = response.rfind('}') + 1
        if start >= 0 and end > start:
            return json.loads(response[start:end])
    except:
        pass
    return {"распределение": [], "остаток": income, "совет": "Не удалось распределить"}

def ai_analyze_full(expenses_data):
    if not expenses_data:
        return "Нет данных."
    stats = "\n".join([f"- {cat}: {total:.0f}р ({count} оп.)" for cat, total, count in expenses_data])
    total = sum(t for _, t, _ in expenses_data)
    prompt = f"""Проанализируй ВСЕ траты за всё время:
{stats}
Всего: {total:.0f}р
Дай анализ (5-7 предложений): тренды, тревожные сигналы, где экономить, конкретные советы."""
    return ask_ollama(prompt)

def ai_forecast_full(income, spending, goal_name, goal_amount):
    savings = income - spending
    months = goal_amount / savings if savings > 0 else 999
    prompt = f"""Сделай прогноз накоплений:
Доход: {income:.0f}р/мес, Траты: {spending:.0f}р/мес, Откладываем: {savings:.0f}р/мес.
Цель: {goal_name} — {goal_amount:.0f}р, Накопим через: {months:.1f} мес.
Дай совет (2-3 предложения): реально ли достичь цели? Что изменить?"""
    return ask_ollama(prompt)

# ========== ИНТЕРФЕЙС ==========
st.title("💰 AI-Планировщик бюджета")

# ========== УПРАВЛЕНИЕ КАТЕГОРИЯМИ ==========
st.sidebar.header("📋 Мои категории")

with st.sidebar.expander("➕ Новая категория"):
    new_name = st.text_input("Название", key="new_cat_name")
    new_limit = st.number_input("Лимит на месяц", min_value=0, step=500, key="new_cat_limit")
    new_mandatory = st.checkbox("Обязательная?", key="new_cat_mandatory")
    new_deadline = st.date_input("Дедлайн (опционально)", value=None, key="new_cat_deadline")
    if st.button("💾 Добавить категорию") and new_name:
        saved["categories"].append({
            "name": new_name,
            "limit": new_limit,
            "mandatory": new_mandatory,
            "deadline": new_deadline.strftime("%Y-%m-%d") if new_deadline else None
        })
        if new_name not in saved["saved_amounts"]:
            saved["saved_amounts"][new_name] = 0
        if new_deadline:
            saved["deadlines"][new_name] = new_deadline.strftime("%Y-%m-%d")
        save_data(saved)
        st.success(f"✅ {new_name} добавлена!")
        st.rerun()

if saved["categories"]:
    st.sidebar.write("**Текущие категории:**")
    for i, cat in enumerate(saved["categories"]):
        mandatory_label = " 🔒" if cat.get("mandatory") else ""
        deadline_str = f" (дедлайн: {cat.get('deadline', '')})" if cat.get("deadline") else ""
        st.sidebar.write(f"{cat['name']}{mandatory_label}: {cat['limit']}р{deadline_str}")
        if st.sidebar.button(f"🗑️ Удалить {cat['name']}", key=f"del_{i}"):
            saved["categories"].pop(i)
            save_data(saved)
            st.rerun()
else:
    st.sidebar.write("Пока нет категорий.")

# ========== ПОСТУПЛЕНИЕ + AI-РАСПРЕДЕЛЕНИЕ ==========
st.header("💵 Поступление денег")
income = st.number_input("Сколько пришло?", value=25000, min_value=0, step=500)
if st.button("🤖 AI-распределить (лимит 50%)") and income > 0 and saved["categories"]:
    with st.spinner("AI распределяет..."):
        result = ai_distribute(income, saved["categories"], saved["saved_amounts"])
        st.subheader("📊 Результат распределения")
        for dist in result.get("распределение", []):
            st.write(f"✅ {dist['статья']}: {dist['сумма']}р — {dist['причина']}")
            saved["saved_amounts"][dist['статья']] = saved["saved_amounts"].get(dist['статья'], 0) + dist['сумма']
        st.metric("💰 Остаток (подушка)", f"{result.get('остаток', 0)}р")
        st.info(f"💬 {result.get('совет', '')}")
        saved["income_history"].append({
            "date": today.strftime("%Y-%m-%d"),
            "amount": income,
            "distribution": result
        })
        save_data(saved)

# ========== РУЧНОЕ ДОБАВЛЕНИЕ ТРАТЫ ==========
st.header("➕ Добавить трату")
if saved["categories"]:
    cat_names = [c["name"] for c in saved["categories"]] + ["Другое"]
    col1, col2 = st.columns(2)
    with col1:
        manual_cat = st.selectbox("Категория", cat_names)
    with col2:
        manual_amount = st.number_input("Сумма", min_value=0, step=100, key="manual_amount")
    manual_comment = st.text_input("Комментарий (необязательно)", key="manual_comment")
    if st.button("💾 Добавить трату"):
        saved["expenses_history"].append({
            "date": today.strftime("%Y-%m-%d"),
            "category": manual_cat,
            "amount": manual_amount,
            "comment": manual_comment
        })
        save_data(saved)
        st.success(f"✅ Добавлено: {manual_cat} — {manual_amount}р")

# ========== AI-КАТЕГОРИЗАТОР ==========
if saved["categories"]:
    st.header("🤖 AI-категоризатор трат")
    raw = st.text_input("Опиши трату (например: 'Пятёрочка 1500 рублей')")
    if st.button("🔍 Распознать и добавить", key="ai_add") and raw:
        with st.spinner("AI думает..."):
            result = ai_categorize(raw, saved["categories"])
        st.success(f"✅ {result['category']} — {result['amount']}р")
        saved["expenses_history"].append({
            "date": today.strftime("%Y-%m-%d"),
            "raw": raw,
            "category": result["category"],
            "amount": result["amount"]
        })
        save_data(saved)

# ========== AI-АНАЛИЗ ==========
st.header("📊 AI-Анализ всех трат")
if st.button("🤖 Анализировать всё время"):
    with st.spinner("AI анализирует..."):
        expenses = saved.get("expenses_history", [])
        if expenses:
            cat_data = defaultdict(lambda: [0, 0])
            for e in expenses:
                cat_data[e["category"]][0] += e.get("amount", 0)
                cat_data[e["category"]][1] += 1
            grouped = [(cat, data[0], data[1]) for cat, data in cat_data.items()]
            grouped.sort(key=lambda x: x[1], reverse=True)
            st.write(ai_analyze_full(grouped))
        else:
            st.warning("Нет данных.")

# ========== AI-ПРОГНОЗ ==========
st.header("🎯 AI-Прогноз накоплений")
goal_name = st.text_input("Цель", value="Шри-Ланка")
goal_amount = st.number_input("Сумма цели", value=150000, min_value=0, step=10000)
monthly_income = st.number_input("Доход в месяц", value=150000, min_value=0, step=5000)
if st.button("🤖 Спрогнозировать"):
    with st.spinner("AI считает..."):
        expenses = saved.get("expenses_history", [])
        current_month = today.strftime("%Y-%m")
        monthly_spending = sum(e.get("amount", 0) for e in expenses if e["date"].startswith(current_month))
        st.write(ai_forecast_full(monthly_income, monthly_spending, goal_name, goal_amount))
        savings = monthly_income - monthly_spending
        months = goal_amount / savings if savings > 0 else 999
        st.metric("💰 Откладываем в месяц", f"{savings:.0f}р")
        st.metric("📅 Накопим через", f"{months:.1f} мес.")

# ========== ИСТОРИЯ ==========
st.header("📜 История трат")
expenses = saved.get("expenses_history", [])
if expenses:
    for e in expenses[-10:]:
        st.write(f"📅 {e['date']} — {e['category']}: {e.get('amount', 0)}р")
