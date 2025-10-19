# customer_balance_app.py
import streamlit as st
import pandas as pd
from datetime import datetime
import os
import sys

FILE_NAME = "customers.csv"
COLUMNS = [
    "DATE",
    "CUSTOMER NAME",
    "AMOUNT OWED",         # total owed by customer
    "BALANCE PAID",        # accumulated payments received so far
    "BALANCE AS OF TODAY", # computed = AMOUNT OWED - BALANCE PAID (but editable)
    "STATUS"
]

# --- Helpers for file handling ------------------------------------------------
def ensure_file():
    if not os.path.exists(FILE_NAME):
        df = pd.DataFrame(columns=COLUMNS)
        df.to_csv(FILE_NAME, index=False)

def load_data():
    ensure_file()
    df = pd.read_csv(FILE_NAME)
    # enforce numeric types and compute balance column if missing or inconsistent
    for col in ["AMOUNT OWED", "BALANCE PAID", "BALANCE AS OF TODAY"]:
        if col not in df.columns:
            df[col] = 0.0
    df["AMOUNT OWED"] = pd.to_numeric(df["AMOUNT OWED"], errors="coerce").fillna(0.0)
    df["BALANCE PAID"] = pd.to_numeric(df["BALANCE PAID"], errors="coerce").fillna(0.0)
    # If BALANCE AS OF TODAY exists but looks wrong, recompute to be safe
    df["BALANCE AS OF TODAY"] = (df["AMOUNT OWED"] - df["BALANCE PAID"]).clip(lower=0.0)
    if "STATUS" not in df.columns:
        df["STATUS"] = df["BALANCE AS OF TODAY"].apply(lambda b: "Cleared ✅" if b <= 0 else "Pending ⏳")
    return df

def save_data(df):
    # ensure columns order
    df = df.reindex(columns=COLUMNS)
    df.to_csv(FILE_NAME, index=False)

def compute_status(balance):
    return "Cleared ✅" if float(balance) <= 0 else "Pending ⏳"

# --- Business logic ---------------------------------------------------------
def add_new_customer(name: str, amount_owed: float, payment_now: float):
    df = load_data()
    key = name.strip().title()
    if key == "":
        st.warning("Enter customer name.")
        return
    if key in df["CUSTOMER NAME"].values:
        st.warning(f"Customer '{key}' already exists. Use Update to add payment.")
        return
    date_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    balance_paid = float(payment_now)
    balance_as_of_today = max(float(amount_owed) - balance_paid, 0.0)
    status = compute_status(balance_as_of_today)
    new = {
        "DATE": date_now,
        "CUSTOMER NAME": key,
        "AMOUNT OWED": float(amount_owed),
        "BALANCE PAID": balance_paid,
        "BALANCE AS OF TODAY": balance_as_of_today,
        "STATUS": status
    }
    df = pd.concat([df, pd.DataFrame([new])], ignore_index=True)
    save_data(df)
    st.success(f"Added customer '{key}' (balance {balance_as_of_today:.2f})")

def update_customer_add_payment(name: str, payment_now: float, set_balance_manual: float | None):
    df = load_data()
    key = name.strip().title()
    if key == "":
        st.warning("Select customer.")
        return
    if key not in df["CUSTOMER NAME"].values:
        st.error("Customer not found.")
        return
    idx = df.index[df["CUSTOMER NAME"] == key][0]
    # increment balance paid
    prev_paid = float(df.at[idx, "BALANCE PAID"])
    new_paid = prev_paid + float(payment_now)
    df.at[idx, "BALANCE PAID"] = new_paid
    # compute new balance, unless manual override provided
    computed_balance = max(float(df.at[idx, "AMOUNT OWED"]) - new_paid, 0.0)
    if set_balance_manual is None:
        df.at[idx, "BALANCE AS OF TODAY"] = computed_balance
    else:
        # allow manual adjustment but ensure non-negative
        df.at[idx, "BALANCE AS OF TODAY"] = max(float(set_balance_manual), 0.0)
    df.at[idx, "DATE"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    df.at[idx, "STATUS"] = compute_status(df.at[idx, "BALANCE AS OF TODAY"])
    save_data(df)
    st.success(f"Updated '{key}': paid now {payment_now:.2f}, balance {df.at[idx, 'BALANCE AS OF TODAY']:.2f}")

# --- App UI -----------------------------------------------------------------
st.set_page_config(page_title="Customer Balance Tracker", page_icon="💰", layout="centered")
st.title("💰 Customer Balance Tracker — Shopkeeper workflow")

menu = st.sidebar.selectbox("Menu", ["Add New Customer", "Update Customer (Record Payment)", "View / Edit Table", "Debug Info"])

if menu == "Add New Customer":
    st.header("Add new customer record")
    with st.form("add_form", clear_on_submit=True):
        name = st.text_input("Customer Name")
        amount_owed = st.number_input("Total Amount Owed (UGX)", min_value=0.0, step=100.0, format="%.2f")
        payment_now = st.number_input("Payment Now (UGX) — amount customer pays now", min_value=0.0, step=100.0, format="%.2f")
        submitted = st.form_submit_button("Add Customer")
        if submitted:
            add_new_customer(name, amount_owed, payment_now)

elif menu == "Update Customer (Record Payment)":
    st.header("Update existing customer — record a payment")
    df = load_data()
    if df.empty:
        st.info("No customers found — add a new customer first.")
    else:
        names = df["CUSTOMER NAME"].tolist()
        selected = st.selectbox("Select customer", [""] + names)
        if selected:
            idx = df.index[df["CUSTOMER NAME"] == selected][0]
            st.write("**Current values:**")
            st.write(f"- Total owed: {df.at[idx,'AMOUNT OWED']:.2f}")
            st.write(f"- Balance paid so far: {df.at[idx,'BALANCE PAID']:.2f}")
            st.write(f"- Balance as of today (computed): {df.at[idx,'BALANCE AS OF TODAY']:.2f}")
            st.write(f"- Status: {df.at[idx,'STATUS']}")
            st.markdown("---")
            with st.form("update_form", clear_on_submit=False):
                payment_now = st.number_input("Payment Now (UGX) — add to Balance Paid", min_value=0.0, step=100.0, format="%.2f")
                manual_balance = st.number_input(
                    "Manual Balance As Of Today (optional) — leave 0 to use computed", 
                    min_value=0.0, step=100.0, format="%.2f", value=0.0
                )
                submit_update = st.form_submit_button("Apply Payment / Update")
                if submit_update:
                    # If manual_balance is 0 but computed balance truly is 0, that's fine.
                    # We interpret manual_balance==0.0 as 'no manual override' only when computed balance != 0.
                    override = None
                    if manual_balance != 0.0:
                        override = manual_balance
                    update_customer_add_payment(selected, payment_now, override)

elif menu == "View / Edit Table":
    st.header("View and (optionally) edit balances")
    df = load_data()
    if df.empty:
        st.info("No records. Add customers first.")
    else:
        st.write("You can edit `BALANCE AS OF TODAY` directly below (then click Save Edited Table).")
        # keep DATE,CUSTOMER,AMOUNT,BALANCE_PAID read-only; BALANCE AS OF TODAY editable
        # Using st.data_editor if available:
        try:
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
            if st.button("Save Edited Table"):
                # Update STATUS based on edited balance
                edited["BALANCE AS OF TODAY"] = edited["BALANCE AS OF TODAY"].clip(lower=0.0)
                edited["STATUS"] = edited["BALANCE AS OF TODAY"].apply(compute_status)
                save_data(edited)
                st.success("Saved edits and updated statuses.")
        except Exception:
            # Fallback: show simple table and provide a simple edit/save route
            st.warning("Interactive table editor not available. Showing plain table.")
            st.dataframe(df, use_container_width=True)
            if st.button("Recompute statuses and save (no edits)"):
                df["STATUS"] = df["BALANCE AS OF TODAY"].apply(compute_status)
                save_data(df)
                st.success("Saved.")

    st.download_button("Download CSV", data=df.to_csv(index=False).encode("utf-8"), file_name="customers.csv", mime="text/csv")

elif menu == "Debug Info":
    st.header("Debug / Environment Info")
    st.write(f"Script path: {os.path.abspath(__file__)}")
    st.write(f"Data file exists: {os.path.exists(FILE_NAME)}")
    st.write(f"Python: {sys.version}")
    try:
        st.write("Data preview:")
        st.dataframe(load_data().head(20))
    except Exception as e:
        st.exception(e)

# --- end --------------------------------------------------------------------
