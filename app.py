import streamlit as st
import pandas as pd
import psycopg2
import re
import os 
from dotenv import load_dotenv
import io

load_dotenv()

st.set_page_config(layout="wide")
st.markdown("""
    <style>
    [data-testid="stMetricValue"] {
        font-size: 18px !important;
    }
    [data-testid="stMetricLabel"] {
        font-size: 12px !important;
    }
    </style>
    """, unsafe_allow_html=True)

def clean_and_sort(data):
    clean = [str(x).replace('С', 'C').strip().upper() for x in data if x and str(x).lower() != 'none']
    clean = list(set(clean))
    def natural_key(string_):
        return [int(s) if s.isdigit() else s for s in re.split(r'(\d+)', string_)]  
    return sorted(clean, key=natural_key)

def writer(df, df_mealtime, meal_time, meal_name):
    query = """
        SELECT dish_category_code,
                AVG(kilocalories) AS kcal,
                AVG(protein)      AS protein,
                AVG(fat)          AS fat,
                AVG(carbohydrate) AS carbohydrate,
                AVG(serving_size_g)
        FROM dishes
        WHERE dish_category_code IN %s
            AND availability_type IN (1, 2)
            AND type IS NOT NULL
        GROUP BY dish_category_code
    """
    cur.execute(query, (tuple(meal_time),))
    rows = cur.fetchall()
    new_rows = pd.DataFrame(rows, columns=["dish_category_code", "kcal", "protein", "fat", "carbohydrate", "serving_size_g"])
    new_rows["meal"] = meal_name
    new_rows[["protein", "fat", "carbohydrate"]] /= 1000
    df = pd.concat([df, new_rows], ignore_index=True)
    df[["kcal", "protein", "fat", "carbohydrate", "serving_size_g"]] = df[["kcal", "protein", "fat", "carbohydrate", "serving_size_g"]].astype(float).fillna(0.0)

    df["kcal"]         = (df["kcal"] * (df["serving_size_g"]/100)).fillna(0.0)
    df["protein"]      = (df["protein"] * (df["serving_size_g"]/100)).fillna(0.0)
    df["fat"]          = (df["fat"] * (df["serving_size_g"]/100)).fillna(0.0)
    df["carbohydrate"] = (df["carbohydrate"] * (df["serving_size_g"]/100)).fillna(0.0)

    total = df["protein"] + df["fat"] + df["carbohydrate"]
    df["protein_%"]      = (df["protein"] * 100 / total).fillna(0.0)
    df["fat_%"]          = (df["fat"] * 100 / total).fillna(0.0)
    df["carbohydrate_%"] = (df["carbohydrate"] * 100 / total).fillna(0.0)

    meal_time = df[df["meal"] == meal_name]
    total = meal_time["protein"].sum() + meal_time["fat"].sum() + meal_time["carbohydrate"].sum()

    kcal_mean = meal_time["kcal"].sum()
    p_sum    = meal_time["protein"].sum()
    f_sum    = meal_time["fat"].sum()
    c_sum    = meal_time["carbohydrate"].sum()

    total_macros = p_sum + f_sum + c_sum
    p_pct = (p_sum * 100 / total_macros) if total_macros else 0.0
    f_pct = (f_sum * 100 / total_macros) if total_macros else 0.0
    c_pct = (c_sum * 100 / total_macros) if total_macros else 0.0

    # calculated_kcal = ((p_sum + c_sum) * 4) + (f_sum * 9)

    st.metric("AVG Ккал:", f"{kcal_mean:.1f}")
    # st.metric("Посчитанные ккал:", f"{calculated_kcal:.2f}")
    st.metric("Белки:", f"{p_sum:.1f} | {p_pct:.1f} %")
    st.metric("Жиры:", f"{f_sum:.1f} | {f_pct:.1f} %")
    st.metric("Углеводы:", f"{c_sum:.1f} | {c_pct:.1f} %")

    new_meal_row = pd.DataFrame([{
        "meal": meal_name,
        "kcal_total": kcal_mean,
        "protein_total": p_sum,
        "fat_total": f_sum,
        "carbohydrate_total": c_sum,
    }])
    df_mealtime = pd.concat([df_mealtime, new_meal_row], ignore_index=True)

    return df, df_mealtime

df = pd.DataFrame(columns=["meal", "dish_category_code", "kcal", "protein", "fat", "carbohydrate", "protein_%", "fat_%", "carbohydrate_%"])
df_mealtime = pd.DataFrame(columns=["meal", "kcal_total", "protein_total", "fat_total", "carbohydrate_total", "kcal_%"])

df = df.round(1)
df_mealtime = df_mealtime.round(1)

DB_CONFIG = {
    "host": os.getenv("DB_HOST"),
    "database": os.getenv("DB_NAME"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "port": os.getenv("DB_PORT"),
}

conn = psycopg2.connect(**DB_CONFIG)
cur = conn.cursor()
cur.execute("select distinct(dish_category_code) from dishes WHERE dish_category_code IS NOT NULL AND dish_category_code != '' AND availability_type in (1,2) and type is not null and dish_category_code is not null ORDER BY dish_category_code ASC;")

dish_codes_raw = list(set([row[0] for row in cur.fetchall() if row[0]]))
dish_codes = clean_and_sort(dish_codes_raw)
print(dish_codes)

st.markdown("<h2 style='text-align: center;'>Total</h2>", unsafe_allow_html=True)
kcal, protein, fat, carb = st.columns(4)
col1, col2, col3, col4, col5 = st.columns(5)

with col1:
    # breakfast_threshold = st.number_input("Max breakfast %", step=1)
    breakfast = st.multiselect(
        "Завтрак:",
        options=dish_codes, 
        key="bf"
    )
    # st.write(f"Вы выбрали: {breakfast}")
    if breakfast:
        df, df_mealtime = writer(df, df_mealtime, breakfast, 'breakfast')
    else:
        st.info("Выберите блюда, чтобы рассчитать среднее.")
with col2:
    # snack1_threshold = st.number_input("Max Snack1 %", step=1)
    snack1 = st.multiselect(
        "Перекус 1:",
        options=dish_codes, 
        key="s1"
    )
    # st.write(f"Вы выбрали: {snack1}")
    if snack1:
        df, df_mealtime = writer(df, df_mealtime, snack1, 'snack1')
    else:
        st.info("Выберите блюда, чтобы рассчитать среднее.")
with col3:
    # lunch_threshold = st.number_input("Max lunch %", step=1)
    lunch = st.multiselect(
        "Обед:",
        options=dish_codes, 
        key="lunch"
    )
    # st.write(f"Вы выбрали: {lunch}")
    if lunch:
        df, df_mealtime = writer(df, df_mealtime, lunch, 'lunch')
    else:
        st.info("Выберите блюда, чтобы рассчитать среднее.")
with col4:
    # snack2_threshold = st.number_input("Max snack2 %", step=1)
    snack2 = st.multiselect(
        "Перекус 2:",
        options=dish_codes, 
        key="s2"
    )
    # st.write(f"Вы выбрали: {snack2}")
    if snack2:
        df, df_mealtime = writer(df, df_mealtime, snack2, 'snack2')
    else:
        st.info("Выберите блюда, чтобы рассчитать среднее.")
with col5:
    # dinner_threshold = st.number_input("Max dinner %", step=1)
    dinner = st.multiselect(
        "Ужин:",
        options=dish_codes, 
        key="dinner"
    )
    # st.write(f"Вы выбрали: {dinner}")
    if dinner:
        df, df_mealtime = writer(df, df_mealtime, dinner, 'dinner')
    else:
        st.info("Выберите блюда, чтобы рассчитать среднее.")

total_kcal = df_mealtime["kcal_total"].sum()
df_mealtime["kcal_%"] = df_mealtime["kcal_total"] * 100 / total_kcal if total_kcal else 0.0

df = df.round(1)
df_mealtime = df_mealtime.round(1)

if not df_mealtime.empty:
    st.dataframe(df_mealtime)

if not df.empty:
    st.dataframe(df)

kcal_total         = df_mealtime["kcal_total"].sum()
protein_total      = df_mealtime["protein_total"].sum()
fat_total          = df_mealtime["fat_total"].sum()
carbohydrate_total = df_mealtime["carbohydrate_total"].sum()

bzu_total = protein_total + fat_total + carbohydrate_total

with kcal:
    st.metric("sum AVG Ккал:", f"{kcal_total:.1f}" if kcal_total else 0)
with protein:
    st.metric("Белки:", f"{protein_total:.1f} | {(protein_total*100/bzu_total):.1f} %" if protein_total else 0)
with fat:
    st.metric("Жиры:", f"{fat_total:.1f} | {(fat_total*100/bzu_total):.1f} %" if fat_total else 0)
with carb:
    st.metric("Углеводы:", f"{carbohydrate_total:.1f} | {(carbohydrate_total*100/bzu_total):.1f} %" if carbohydrate_total else 0)

if not df_mealtime.empty or not df.empty:
    st.divider()
    st.subheader("Выгрузка результатов")
    
    buffer = io.BytesIO()
    
    with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer_engine:
        if not df_mealtime.empty:
            df_mealtime.to_excel(writer_engine, index=False, sheet_name='Summary_Meals')
        if not df.empty:
            df.to_excel(writer_engine, index=False, sheet_name='Detailed_Stats')
            
    st.download_button(
        label="📥 Скачать расчет в Excel",
        data=buffer.getvalue(),
        file_name="diet_report.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )