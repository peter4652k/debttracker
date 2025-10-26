import streamlit as st
import pandas as pd
from datetime import datetime
import os
import sys
import base64
import requests
from io import StringIO

# --- CONFIG -----------------------------------------------------------------
COLUMNS = [
    "DATE",
    "CUSTOMER NAME",
    "AMOUNT OWED",
    "BALANCE PAID",
    "BALANCE AS OF TODAY",
    "STATUS"
]

# --- GITHUB CONFIG ----------------------------------------------------------
GITHUB_TOKEN = st.secrets["GITHUB_TOKEN"]
REPO_NAME = st.secrets["REPO_NAME"]
FILE_PATH = st.secrets["FILE_PATH"]
API_URL = f"https://api.github.com/repos/{REPO_NAME}/contents/{FILE_PATH}"
HEADERS = {"Authorization": f"token {GITHUB_TOKEN}"}


# --- GITHUB HELPERS ---------------------------------------------------------
def github_load_csv():
    """Fetch CSV from GitHub repo (via API). If missing, return empty DataFrame."""
    res = requests.get(API_URL, headers=HEADERS)
    if res.status_code == 200:
        content = base64.b64decode(res.json()["content"]).decode()
        df = pd.read_csv(StringIO(content))
        return df
    else:
        # File not found or empty repo
        return pd.DataFrame(columns=COLUMNS)


def github_save_csv(df):
    """Save CSV back to GitHub (create or update file)."""
    df = df.reindex(columns=COLUMNS)
    csv_content = df.to_csv(index=False)
    encoded = base64.b64encode(csv_content.encode()).decode()

    # Check if file exists (to include its SHA for update)
    get_res = requests.get(API_URL, headers=HEADERS)
    if get_res.status_code == 200:
        sha = get_res.json()["sha"]
    else:
        sha = None

    payload = {
        "message": "Update customers.csv from Streamlit app",
        "content": encoded,
        "sha": sha
    }
    put_res = requests.put(API_URL, headers=HEADERS, json=payload)
    if put_res.status_code not in (200, 201):
        st.error(f"❌ GitHub save failed: {put_res.status_code} {put_res.text}")
    else:
        st.success("✅ Saved to GitHub successfully.")


# --- STATUS COMPUTE ---------------------------------------------------------
def compute_status(balance):
    return "Cleared ✅" if float(balance) <= 0 else "Pending ⏳"


# --- BUSINESS LOGIC ---------------------------------------------------------
def load_data():
    df = github_load_csv()
    for col in ["AMOUNT OWED", "BALANCE PAID", "BALANCE AS OF TODAY"]:
        df[col] = pd.to_numeric(df.get(col, 0.0), errors="coerce").fillna(0.0)
    df["BALANCE AS OF TODAY"] = (df["AMOUNT OWED"] - df["BALANCE PAID"]).clip(lower=0.0)
    df["STATUS"] = df["BALANCE AS OF TODAY"].apply(compute_status)
    return df


def add_new_customer(name, amount_owed, payment_now):
    df = load_data()
    key = name.strip().title()
    if not key:
        st.warning("Enter customer name.")
        return
    if key in df["CUSTOMER NAME"].values:
        st.warning(f"Customer '{key}' already exists. Use Update to add payment.")
        return

    balance_paid = float(payment_now)
    balance_as_of_today = max(float(amount_owed) - balance_paid, 0.0)
    status = compute_status(balance_as_of_today)
    new = {
        "DATE": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "CUSTOMER NAME": key,
        "AMOUNT OWED": float(amount_owed),
        "BALANCE PAID": balance_paid,
        "BALANCE AS OF TODAY": balance_as_of_today,
        "STATUS": status
    }
    df = pd.concat([df, pd.DataFrame([new])], ignore_index=True)
    github_save_csv(df)
    st.success(f"Added customer '{key}' (balance {balance_as_of_today:.2f})")


def update_customer_add_payment(name, payment_now, set_balance_manual):
    df = load_data()
    key = name.strip().title()
    if key not in df["CUSTOMER NAME"].values:
        st.error("Customer not found.")
        return
    idx = df.index[df["CUSTOMER NAME"] == key][0]

    prev_paid = float(df.at[idx, "BALANCE PAID"])
    new_paid = prev_paid + float(payment_now)
    df.at[idx, "BALANCE PAID"] = new_paid

    computed_balance = max(float(df.at[idx, "AMOUNT OWED"]) - new_paid, 0.0)
    if set_balance_manual is None:
        df.at[idx, "BALANCE AS OF TODAY"] = computed_balance
    else:
        df.at[idx, "BALANCE AS OF TODAY"] = max(float(set_balance_manual), 0.0)

    df.at[idx, "DATE"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    df.at[idx, "STATUS"] = compute_status(df.at[idx, "BALANCE AS OF TODAY"])

    github_save_csv(df)
    st.success(f"Updated '{key}': paid {payment_now:.2f}, balance {df.at[idx, 'BALANCE AS OF TODAY']:.2f}")


# --- APP UI -----------------------------------------------------------------
st.set_page_config(page_title="Customer Balance Tracker", page_icon="💰", layout="centered")
st.title("💰 Customer Balance Tracker (GitHub Synced)")

menu = st.sidebar.selectbox("Menu", ["Add New Customer", "Update Customer", "View / Edit Table", "Debug Info"])

if menu == "Add New Customer":
    st.header("Add New Customer")
    with st.form("add_form", clear_on_submit=True):
        name = st.text_input("Customer Name")
        amount_owed = st.number_input("Total Amount Owed (UGX)", min_value=0.0, step=100.0, format="%.2f")
        payment_now = st.number_input("Payment Now (UGX)", min_value=0.0, step=100.0, format="%.2f")
        if st.form_submit_button("Add Customer"):
            add_new_customer(name, amount_owed, payment_now)

elif menu == "Update Customer":
    st.header("Record Payment / Update")
    df = load_data()
    if df.empty:
        st.info("No customers found.")
    else:
        names = df["CUSTOMER NAME"].tolist()
        selected = st.selectbox("Select customer", [""] + names)
        if selected:
            idx = df.index[df["CUSTOMER NAME"] == selected][0]
            st.write(f"**Total owed:** {df.at[idx,'AMOUNT OWED']:.2f}")
            st.write(f"**Balance paid so far:** {df.at[idx,'BALANCE PAID']:.2f}")
            st.write(f"**Balance as of today:** {df.at[idx,'BALANCE AS OF TODAY']:.2f}")
            st.write(f"**Status:** {df.at[idx,'STATUS']}")
            st.markdown("---")
            with st.form("update_form"):
                payment_now = st.number_input("Payment Now (UGX)", min_value=0.0, step=100.0, format="%.2f")
                manual_balance = st.number_input("Manual Balance Override (optional)", min_value=0.0, step=100.0, format="%.2f", value=0.0)
                if st.form_submit_button("Apply Payment / Update"):
                    override = manual_balance if manual_balance != 0 else None
                    update_customer_add_payment(selected, payment_now, override)

elif menu == "View / Edit Table":
    st.header("Customer Records (Editable)")
    df = load_data()
    if df.empty:
        st.info("No records.")
    else:
        edited = st.data_editor(
            df,
            num_rows="dynamic",
            use_container_width=True,
            column_config={
                "BALANCE AS OF TODAY": st.column_config.NumberColumn(
                    "BALANCE AS OF TODAY (editable)", min_value=0.0, format="%.2f"
                )
            },
            disabled=["DATE", "CUSTOMER NAME", "AMOUNT OWED", "BALANCE PAID", "STATUS"]
        )
        if st.button("Save Edits"):
            edited["BALANCE AS OF TODAY"] = edited["BALANCE AS OF TODAY"].clip(lower=0.0)
            edited["STATUS"] = edited["BALANCE AS OF TODAY"].apply(compute_status)
            github_save_csv(edited)

elif menu == "Debug Info":
    st.header("Debug Info")
    st.write(f"Python: {sys.version}")
    st.write(f"Repo: {REPO_NAME}")
    st.write(f"File Path: {FILE_PATH}")
    df = load_data()
    st.dataframe(df.head(10))

