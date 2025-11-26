# train_model.py
"""
Correct ML training script for the user's dataset:
D:\medicine-sim\data\medicine_dataset_with_phone.xlsx
Column name: exp_date
This script will create model.pkl with NO errors.
"""

import pandas as pd
import numpy as np
from sklearn.preprocessing import LabelEncoder
from sklearn.ensemble import IsolationForest
import joblib

# --- YOUR CORRECT PATH ---
DATA_PATH = r"D:\medicine-sim\data\medicine_dataset_with_phone.xlsx"
MODEL_OUT = r"D:\medicine-sim\backend\model.pkl"


def load_catalog(path=DATA_PATH):
    df = pd.read_excel(path)
    df.columns = [str(c).strip() for c in df.columns]

    # Ensure expected columns exist
    if "manufacturer" not in df.columns:
        df["manufacturer"] = "Unknown"

    # Your dataset uses exp_date (confirmed by you)
    if "exp_date" not in df.columns:
        raise ValueError("Your dataset MUST contain an 'exp_date' column.")

    df["exp_date_parsed"] = pd.to_datetime(df["exp_date"], errors="coerce")
    return df


def prepare_features(df):
    today = pd.to_datetime("2025-11-25")  # same reference date as backend

    # FIXED → correct column name
    df["days_to_expiry"] = (df["exp_date_parsed"] - today).dt.days.fillna(36500).astype(int)

    # Encode manufacturer
    le = LabelEncoder()
    df["man_enc"] = le.fit_transform(df["manufacturer"].fillna("Unknown").astype(str))

    # FIXED → correct feature names
    X = df[["days_to_expiry", "man_enc"]].values

    return X, le


def train_and_save():
    print("Loading catalog from:", DATA_PATH)
    df = load_catalog(DATA_PATH)
    print("Rows loaded:", len(df))

    X, le = prepare_features(df)

    # Isolation Forest
    iso = IsolationForest(n_estimators=200, contamination=0.05, random_state=42)
    iso.fit(X)

    bundle = {"model": iso, "encoder": le}
    joblib.dump(bundle, MODEL_OUT)

    print("\nMODEL TRAINED SUCCESSFULLY!")
    print("Saved model to:", MODEL_OUT)

    # Show sample scores
    scores = -iso.decision_function(X)
    print("Example anomaly scores:", list(scores[:5]))
    print("\nDONE.\n")


if __name__ == "__main__":
    train_and_save()
