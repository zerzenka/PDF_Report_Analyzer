import pandas as pd
import re
from typing import List, Tuple


def _clean_name(s: str) -> str:
    s = str(s).lower()
    s = re.sub(r"[^a-z ]", " ", s)
    s = " ".join(s.split())
    return s


class EmployeeDB:
    def __init__(self, excel_path: str):
        self.df = pd.read_excel(excel_path)

        # normalize
        self.df["EmployeeID"] = self.df["EmployeeID"].astype(str)
        self.df["Department"] = self.df["Department"].astype(str)

        # ---- NEW: clean name column ----
        # adjust column name if yours is different
        self.df["EmployeeNameClean"] = self.df["EmployeeName"].apply(_clean_name)

    # ---- existing method (unchanged) ----
    def get_ids_for_department(self, department: str) -> List[str]:
        subset = self.df[self.df["Department"] == department]
        return subset["EmployeeID"].tolist()

    # ---- NEW method: full records for name+id matching ----
    def get_records_for_department(self, department: str) -> List[Tuple[str, str, str]]:
        """
        Returns:
            (employee_id, name_clean, name_original)
        """
        subset = self.df[self.df["Department"] == department]

        records = []

        for _, row in subset.iterrows():
            records.append(
                (
                    str(row["EmployeeID"]),
                    row["EmployeeNameClean"],
                    str(row["EmployeeName"]),
                )
            )

        return records