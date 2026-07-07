import streamlit as st
from datetime import date, datetime
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
        "deadlines": {},
        "chat_history": []
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
            if saved["saved_amounts"].get(cat_name, 0) > 0:
                saved["saved_amounts"][cat_name] = 0
                changed = True
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
            "stream": False, "options": {"temperature": 0.3, "max_tokens": 500}
        }, timeout=60)
        return resp.json()["response"].strip()
    except:
        return "⚠️ Ollama не отвечает"

def ai_categorize(raw_text, categories):
    cat_names = [c["name"] for c in categories] + ["Другое"]
    prompt = f"""Ты — финансовый ассистент. Верни ТОЛЬКО JSON.
Трата: "{raw_text}"
Формат: {{"category": "категория", "amount": число, "comment": "комментарий"}}
Категории: {', '.join(cat_names)}.
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
    prompt = f"""Ты — финансовый ассистент. Распредели поступление {income}р.
Правила: не больше 50% от недостающей суммы. Обязательные — в первую очередь.
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
    return ask_ollama(f"""Проанализируй ВСЕ траты за всё время:
{stats}
Всего: {total:.0f}р
Дай анализ (5-7 предложений): тренды, тревожные сигналы, где экономить, конкретные советы.""")

def ai_forecast_full(income, spending, goal_name, goal_amount):
    savings = income - spending
    months = goal_amount / savings if savings > 0 else 999
    return ask_ollama(f"""Сделай прогноз накоплений:
Доход: {income:.0f}р/мес, Траты: {spending:.0f}р/мес, Откладываем: {savings:.0f}р/мес.
Цель: {goal_name} — {goal_amount:.0f}р, Накопим через: {months:.1f} мес.
Дай совет (2-3 предложения): реально ли достичь цели? Что изменить?""")

# ========== ИНТЕРФЕЙС ==========
st.title("💰 AI-Планировщик бюджета")

# ========== ТЕКУЩИЕ СУММЫ ==========
if saved["categories"]:
    st.header("💳 Текущие суммы")
    for i, cat in enumerate(saved["categories"]):
        current = saved["saved_amounts"].get(cat["name"], 0)
        limit = cat["limit"]
        progress = min(current / limit, 1.0) if limit > 0 else 0
        
        col1, col2, col3, col4 = st.columns([2, 1, 1, 1])
        with col1:
            st.write(f"{cat['name']} {'🔒' if cat.get('mandatory') else ''}")
            st.progress(progress)
        with col2:
            st.write(f"**{current:.0f}р** из {limit}р")
        with col3:
            add = st.number_input(f"➕", min_value=0, step=100, key=f"add_{i}")
        with col4:
            sub = st.number_input(f"➖", min_value=0, step=100, key=f"sub_{i}")
        
        c1, c2 = st.columns(2)
        with c1:
            if st.button(f"✅ +{add}р", key=f"btn_add_{i}"):
                saved["saved_amounts"][cat["name"]] = saved["saved_amounts"].get(cat["name"], 0) + add
                save_data(saved)
                st.rerun()
        with c2:
            if st.button(f"❌ -{sub}р", key=f"btn_sub_{i}"):
                saved["saved_amounts"][cat["name"]] = max(0, saved["saved_amounts"].get(cat["name"], 0) - sub)
                save_data(saved)
                st.rerun()
    st.divider()

# ========== КАТЕГОРИИ ==========
st.sidebar.header("📋 Категории")
with st.sidebar.expander("➕ Новая"):
    name = st.text_input("Название", key="new_name")
    limit = st.number_input("Лимит", min_value=0, step=500, key="new_limit")
    mandatory = st.checkbox("Обязательная?", key="new_mandatory")
    deadline = st.date_input("Дедлайн", value=None, key="new_deadline")
    if st.button("💾 Добавить") and name:
        saved["categories"].append({
            "name": name, "limit": limit, "mandatory": mandatory,
            "deadline": deadline.strftime("%Y-%m-%d") if deadline else None
        })
        if name not in saved["saved_amounts"]:
            saved["saved_amounts"][name] = 0
        if deadline:
            saved["deadlines"][name] = deadline.strftime("%Y-%m-%d")
        save_data(saved)
        st.success(f"✅ {name}")
        st.rerun()

if saved["categories"]:
    st.sidebar.write("**Категории:**")
    for i, c in enumerate(saved["categories"]):
        st.sidebar.write(f"{c['name']}: {c['limit']}р")
        if st.sidebar.button(f"🗑️ {c['name']}", key=f"del_{i}"):
            saved["categories"].pop(i)
            save_data(saved)
            st.rerun()

# ========== ПОСТУПЛЕНИЕ ==========
st.header("💵 Поступление")
income = st.number_input("Сумма", value=25000, min_value=0, step=500)
if st.button("🤖 AI-распределить") and income > 0 and saved["categories"]:
    with st.spinner("AI думает..."):
        result = ai_distribute(income, saved["categories"], saved["saved_amounts"])
        for d in result.get("распределение", []):
            st.write(f"✅ {d['статья']}: {d['сумма']}р — {d['причина']}")
            saved["saved_amounts"][d['статья']] = saved["saved_amounts"].get(d['статья'], 0) + d['сумма']
        st.metric("💰 Остаток", f"{result.get('остаток', 0)}р")
        st.info(result.get('совет', ''))
        saved["income_history"].append({"date": today.strftime("%Y-%m-%d"), "amount": income, "distribution": result})
        save_data(saved)

# ========== ТРАТА ==========
st.header("➕ Трата")
if saved["categories"]:
    cats = [c["name"] for c in saved["categories"]] + ["Другое"]
    c1, c2 = st.columns(2)
    with c1:
        cat = st.selectbox("Категория", cats)
    with c2:
        amt = st.number_input("Сумма", min_value=0, step=100, key="man_amt")
    if st.button("💾 Добавить"):
        saved["expenses_history"].append({"date": today.strftime("%Y-%m-%d"), "category": cat, "amount": amt})
        save_data(saved)
        st.success(f"✅ {cat} — {amt}р")

# ========== AI-КАТЕГОРИЗАТОР ==========
if saved["categories"]:
    st.header("🤖 AI-категоризатор")
    raw = st.text_input("Опиши трату")
    if st.button("🔍 Распознать") and raw:
        with st.spinner("..."):
            r = ai_categorize(raw, saved["categories"])
        st.success(f"✅ {r['category']} — {r['amount']}р")
        saved["expenses_history"].append({"date": today.strftime("%Y-%m-%d"), "raw": raw, "category": r["category"], "amount": r["amount"]})
        save_data(saved)

# ========== AI-АНАЛИЗ ==========
st.header("📊 AI-Анализ")
if st.button("🤖 Анализировать"):
    with st.spinner("..."):
        expenses = saved.get("expenses_history", [])
        if expenses:
            cat_data = defaultdict(lambda: [0, 0])
            for e in expenses:
                cat_data[e["category"]][0] += e.get("amount", 0)
                cat_data[e["category"]][1] += 1
            grouped = [(cat, d[0], d[1]) for cat, d in cat_data.items()]
            grouped.sort(key=lambda x: x[1], reverse=True)
            st.write(ai_analyze_full(grouped))
        else:
            st.warning("Нет данных.")

# ========== AI-ПРОГНОЗ ==========
st.header("🎯 AI-Прогноз")
goal = st.text_input("Цель", value="Шри-Ланка")
goal_amt = st.number_input("Сумма цели", value=150000, min_value=0, step=10000)
inc = st.number_input("Доход/мес", value=150000, min_value=0, step=5000)
if st.button("🤖 Прогноз"):
    with st.spinner("..."):
        expenses = saved.get("expenses_history", [])
        cm = today.strftime("%Y-%m")
        sp = sum(e.get("amount", 0) for e in expenses if e["date"].startswith(cm))
        st.write(ai_forecast_full(inc, sp, goal, goal_amt))
        sv = inc - sp
        mo = goal_amt / sv if sv > 0 else 999
        st.metric("💰 Откладываем", f"{sv:.0f}р")
        st.metric("📅 Накопим через", f"{mo:.1f} мес.")

# ========== ИСТОРИЯ ==========
st.header("📜 История трат")
for e in saved.get("expenses_history", [])[-10:]:
    st.write(f"📅 {e['date']} — {e['category']}: {e.get('amount', 0)}р")

# ========== ЧАТ С AI ==========
st.divider()
st.header("💬 Чат с AI-ассистентом")
st.write("Спрашивай о финансах: как экономить, куда распределить, анализ трат.")

# История чата
if "chat_messages" not in st.session_state:
    st.session_state.chat_messages = []

# Показываем историю
for msg in st.session_state.chat_messages[-10:]:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])

# Поле ввода
user_msg = st.chat_input("Твой вопрос...")
if user_msg:
    st.session_state.chat_messages.append({"role": "user", "content": user_msg})
    
    context = ""
    if saved["categories"]:
        context += "Категории:\n"
        for c in saved["categories"]:
            current = saved["saved_amounts"].get(c["name"], 0)
            context += f"- {c['name']}: лимит {c['limit']}р, отложено {current}р\n"
    
    expenses = saved.get("expenses_history", [])
    if expenses:
        cm = today.strftime("%Y-%m")
        month_total = sum(e.get("amount", 0) for e in expenses if e["date"].startswith(cm))
        context += f"\nТраты за месяц: {month_total:.0f}р\n"
    
    income_hist = saved.get("income_history", [])
    if income_hist:
        last_income = income_hist[-1]["amount"]
        context += f"Последнее поступление: {last_income}р\n"
    
    prompt = f"""Ты — личный финансовый ассистент. У тебя есть доступ к данным пользователя.

ДАННЫЕ ПОЛЬЗОВАТЕЛЯ:
{context}

ВОПРОС: {user_msg}

Отвечай полезно, конкретно, ссылаясь на данные. Если данных не хватает — спроси."""
    
    with st.spinner("AI думает..."):
        response = ask_ollama(prompt)
    
    st.session_state.chat_messages.append({"role": "assistant", "content": response})
    st.rerun()
