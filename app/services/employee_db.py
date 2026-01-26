import pandas as pd
from typing import List


class EmployeeDB:
    def __init__(self, excel_path: str):
        self.df = pd.read_excel(excel_path)

        # normalize
        self.df["EmployeeID"] = self.df["EmployeeID"].astype(str)
        self.df["Department"] = self.df["Department"].astype(str)

    def get_ids_for_department(self, department: str) -> List[str]:
        subset = self.df[self.df["Department"] == department]
        return subset["EmployeeID"].tolist()