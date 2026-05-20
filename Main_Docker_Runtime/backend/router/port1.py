"""
port1.py
P1 포트 — 단방향 (Port1 → Core)
"""

from .protocol import PC1


class Port1:

    def __init__(self, usr_anal: str, ssn_tpc: str, ssn_pcl: str) -> None:
        self._usr_anal = usr_anal
        self._ssn_tpc  = ssn_tpc
        self._ssn_pcl  = ssn_pcl

    def request_pc1(self) -> PC1:
        return PC1(USR_ANAL=self._usr_anal, SSN_TPC=self._ssn_tpc, SSN_PCL=self._ssn_pcl)
