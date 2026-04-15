import streamlit as st
import pandas as pd
import psycopg2
import re
import os 
from dotenv import load_dotenv
import io

load_dotenv()

st.set_page_config(layout="wide")

# Инициализация session_state (чтобы данные сохранялись между запусками)
if 'df' not in st.session_state:
    st.session_state.df = pd.DataFrame(columns=["meal", "dish_category_code", "kcal", "protein", "fat", "carbohydrate", "protein_%", "fat_%", "carbohydrate_%"])
if 'df_mealtime' not in st.session_state:
    st.session_state.df_mealtime = pd.DataFrame(columns=["meal", "kcal_total", "protein_total", "fat_total", "carbohydrate_total", "kcal_%"])

st.markdown("""
    <style>
    [data-testid="stMetricValue"] { font-size: 18px !important; }
    [data-testid="stMetricLabel"] { font-size: 12px !important; }
    </style>
    """, unsafe_allow_html=True)

def clean_and_sort(data):
    clean = [str(x).replace('С', 'C').strip().upper() for x in data if x and str(x).lower() != 'none']
    clean = list(set(clean))
    def natural_key(string_):
        return [int(s) if s.isdigit() else s for s in re.split(r'(\d+)', string_)]  
    return sorted(clean, key=natural_key)

def writer(df_input, df_meal_input, meal_codes, meal_name):
    """
    Принимает текущие датафреймы, список кодов и название приема пищи.
    Возвращает обновленные датафреймы.
    """
    query = """
        SELECT dish_category_code,
                AVG(kcal_portion) AS kcal,
                AVG(protein_portion)      AS protein,
                AVG(fat_portion)          AS fat,
                AVG(carbohydrate_portion) AS carbohydrate
        FROM dishes
        WHERE dish_category_code IN %s
            AND availability_type IN (1, 2)
            AND type IS NOT NULL
        GROUP BY dish_category_code
    """
    cur.execute(query, (tuple(meal_codes),))
    rows = cur.fetchall()
    
    new_rows = pd.DataFrame(rows, columns=["dish_category_code", "kcal", "protein", "fat", "carbohydrate"])
    new_rows["meal"] = meal_name
    
    # Конвертация и очистка
    new_rows[["protein", "fat", "carbohydrate"]] = new_rows[["protein", "fat", "carbohydrate"]].astype(float) / 1000
    new_rows["kcal"] = new_rows["kcal"].astype(float)
    new_rows = new_rows.fillna(0.0)

    # Расчет процентов внутри категорий
    total_m = new_rows["protein"] + new_rows["fat"] + new_rows["carbohydrate"]
    new_rows["protein_%"] = (new_rows["protein"] * 100 / total_m).fillna(0.0)
    new_rows["fat_%"] = (new_rows["fat"] * 100 / total_m).fillna(0.0)
    new_rows["carbohydrate_%"] = (new_rows["carbohydrate"] * 100 / total_m).fillna(0.0)

    # Обновляем основной DF
    df_output = pd.concat([df_input, new_rows], ignore_index=True)

    # Метрики для отображения в колонке
    kcal_sum = new_rows["kcal"].sum()
    p_sum = new_rows["protein"].sum()
    f_sum = new_rows["fat"].sum()
    c_sum = new_rows["carbohydrate"].sum()
    
    total_macros = p_sum + f_sum + c_sum
    st.metric("AVG Ккал:", f"{kcal_sum:.1f}")
    st.metric("Белки:", f"{p_sum:.1f} | {(p_sum*100/total_macros if total_macros else 0):.1f} %")
    st.metric("Жиры:", f"{f_sum:.1f} | {(f_sum*100/total_macros if total_macros else 0):.1f} %")
    st.metric("Углеводы:", f"{c_sum:.1f} | {(c_sum*100/total_macros if total_macros else 0):.1f} %")

    # Обновляем DF по приемам пищи
    new_meal_row = pd.DataFrame([{
        "meal": meal_name,
        "kcal_total": kcal_sum,
        "protein_total": p_sum,
        "fat_total": f_sum,
        "carbohydrate_total": c_sum,
    }])
    df_meal_output = pd.concat([df_meal_input, new_meal_row], ignore_index=True)

    return df_output, df_meal_output

# Подключение к БД
DB_CONFIG = {
    "host": os.getenv("DB_HOST"),
    "database": os.getenv("DB_NAME"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "port": os.getenv("DB_PORT"),
}
conn = psycopg2.connect(**DB_CONFIG)
cur = conn.cursor()

# Получение кодов категорий
cur.execute("SELECT DISTINCT dish_category_code FROM dishes WHERE dish_category_code IS NOT NULL AND availability_type IN (1,2) AND type IS NOT NULL ORDER BY dish_category_code ASC;")
dish_codes_raw = [row[0] for row in cur.fetchall() if row[0]]
dish_codes = clean_and_sort(dish_codes_raw)

# Создаем временные контейнеры для этого прогона (скрипт выполняется сверху вниз)
current_df = pd.DataFrame()
current_mealtime = pd.DataFrame()

kcal_col, prot_col, fat_col, carb_col = st.columns(4)
st.divider()

col1, col2, col3, col4, col5 = st.columns(5)

# Словарь для итерации по колонкам (чтобы сохранить порядок строк)
meal_configs = [
    (col1, "Завтрак", "bf"),
    (col2, "Перекус 1", "s1"),
    (col3, "Обед", "lunch"),
    (col4, "Перекус 2", "s2"),
    (col5, "Ужин", "dinner")
]

for col, name, key in meal_configs:
    with col:
        selected = st.multiselect(f"{name}:", options=dish_codes, key=key)
        if selected:
            current_df, current_mealtime = writer(current_df, current_mealtime, selected, name)
        else:
            st.info("Выберите категории")

# Финальные расчеты
total_kcal = current_mealtime["kcal_total"].sum() if not current_mealtime.empty else 0
if total_kcal > 0:
    current_mealtime["kcal_%"] = (current_mealtime["kcal_total"] * 100 / total_kcal).round(1)

# Вывод общих итогов в верхние метрики
p_total = current_mealtime["protein_total"].sum() if not current_mealtime.empty else 0
f_total = current_mealtime["fat_total"].sum() if not current_mealtime.empty else 0
c_total = current_mealtime["carbohydrate_total"].sum() if not current_mealtime.empty else 0
bzu_sum = p_total + f_total + c_total

with kcal_col: st.metric("Итого Ккал", f"{total_kcal:.1f}")
with prot_col: st.metric("Белки", f"{p_total:.1f} | {(p_total*100/bzu_sum if bzu_sum else 0):.1f}%")
with fat_col:  st.metric("Жиры", f"{f_total:.1f} | {(f_total*100/bzu_sum if bzu_sum else 0):.1f}%")
with carb_col: st.metric("Углеводы", f"{c_total:.1f} | {(c_total*100/bzu_sum if bzu_sum else 0):.1f}%")

# Отображение таблиц
if not current_mealtime.empty:
    st.subheader("Сводка по приемам пищи")
    st.dataframe(current_mealtime.round(1), use_container_width=True)

if not current_df.empty:
    st.subheader("Детальная статистика по категориям")
    st.dataframe(current_df.round(1), use_container_width=True)

# Экспорт в Excel
if not current_df.empty:
    current_df = current_df.round(1)
    current_mealtime = current_mealtime.round(1)
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer_engine:
        current_mealtime.to_excel(writer_engine, index=False, sheet_name='Summary')
        current_df.to_excel(writer_engine, index=False, sheet_name='Details')
    
    st.download_button(
        label="📥 Скачать отчет (Excel)",
        data=buffer.getvalue(),
        file_name="diet_analysis.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )