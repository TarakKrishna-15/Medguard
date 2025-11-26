import pandas as pd

CATALOG_PATH = "/mnt/data/23d08443-557c-42a4-a8c4-ebc878f19e63.xlsx"

def load_catalog(path=CATALOG_PATH):
    df = pd.read_excel(path)
    # normalize column names
    df.columns = [c.strip() for c in df.columns]
    # ensure expected columns exist
    for col in ["manufacturer", "exp_date"]:
        if col not in df.columns:
            df[col] = None
    # parse dates
    df["exp_date_parsed"] = pd.to_datetime(df["exp_date"], errors="coerce")
    return df
