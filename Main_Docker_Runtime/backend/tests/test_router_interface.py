"""
라우터 인터페이스 틀 검증 테스트.
실행: python -m pytest backend/tests/test_router_interface.py
"""
from __future__ import annotations

import unittest
from backend.router.core import Core
from backend.router.protocol import PC1, PC2, PC3, QUST, LLM_Response, T_MK_Item, T_PN_Item


class FakePort1:
    async def request_pc1(self) -> PC1:
        return PC1(USR_ANAL="user", SSN_TPC="topic", SSN_PCL="history")


class FakePort2:
    def __init__(self) -> None:
        self.received: list[PC2] = []
        self.errors: list[str] = []

    async def receive_from_core(self, pc2: PC2) -> None:
        self.received.append(pc2)

    async def on_error(self, msg: str) -> None:
        self.errors.append(msg)


class FakePort3:
    def __init__(self) -> None:
        self.executed: list[PC3] = []

    async def execute(self, pc3: PC3) -> None:
        self.executed.append(pc3)


class RouterInterfaceTests(unittest.IsolatedAsyncioTestCase):
    async def test_core_merge_combines_pc1_and_pc2_for_port3(self) -> None:
        p1, p2, p3 = FakePort1(), FakePort2(), FakePort3()
        core = Core(p1=p1, p2=p2, p3=p3)

        await core.receive_from_p2(PC2(
            CC="hello", T_SL="selected", T_CD=["260519"],
            T_MP=["node-a"],
            T_MK=[T_MK_Item(marker_id="m1")],
            T_PN=[[T_PN_Item(date="260519", order=1, place="place")]],
        ))

        self.assertEqual(len(p3.executed), 1)
        m = p3.executed[0]
        self.assertEqual(m.USR_ANAL, "user")
        self.assertEqual(m.SSN_TPC, "topic")
        self.assertEqual(m.CC, "hello")
        self.assertEqual(m.T_CD, ["260519"])
        self.assertEqual(m.T_MK[0].marker_id, "m1")

    async def test_core_rejects_empty_cc_before_port3(self) -> None:
        p1, p2, p3 = FakePort1(), FakePort2(), FakePort3()
        core = Core(p1=p1, p2=p2, p3=p3)

        await core.receive_from_p2(PC2(CC=""))

        self.assertEqual(len(p3.executed), 0)
        self.assertEqual(len(p2.errors), 1)

    async def test_split_sends_pc2_without_pc1_fields(self) -> None:
        p1, p2, p3 = FakePort1(), FakePort2(), FakePort3()
        core = Core(p1=p1, p2=p2, p3=p3)

        await core.receive_from_p3(PC3(
            USR_ANAL="user", SSN_TPC="topic", SSN_PCL="history",
            CC="answer", T_SL="selected", T_CD=["260519"],
        ))

        self.assertEqual(len(p2.received), 1)
        received = p2.received[0]
        self.assertIsInstance(received, PC2)
        self.assertEqual(received.CC, "answer")
        self.assertFalse(hasattr(received, "USR_ANAL"))

    async def test_empty_list_from_llm_keeps_previous_value(self) -> None:
        """빈 리스트는 "변경 없음"으로 해석 — 스펙 의도 확인용"""
        p1, p2, p3 = FakePort1(), FakePort2(), FakePort3()
        core = Core(p1=p1, p2=p2, p3=p3)
        core._prev_pc2 = PC2(CC="old", T_CD=["260519"])

        await core.receive_from_p3(PC3(CC="answer", T_CD=[]))

        self.assertEqual(p2.received[0].T_CD, ["260519"])


class ProtocolShapeTests(unittest.TestCase):
    def test_field_sets(self) -> None:
        pc1_f = {"USR_ANAL", "SSN_TPC", "SSN_PCL"}
        pc2_f = {"CC", "T_SL", "T_CD", "T_MP", "T_MK", "T_PN"}

        self.assertEqual(set(PC1().__dataclass_fields__), pc1_f)
        self.assertEqual(set(PC2().__dataclass_fields__), pc2_f)
        self.assertEqual(set(PC3().__dataclass_fields__), pc1_f | pc2_f)
        self.assertEqual(set(QUST().__dataclass_fields__), pc1_f | pc2_f | {"sDB", "dDB", "PPL"})
        self.assertEqual(set(LLM_Response().__dataclass_fields__), pc1_f | pc2_f)

    def test_pc3_to_pc2_drops_pc1_fields(self) -> None:
        pc2 = PC3(USR_ANAL="u", SSN_TPC="t", SSN_PCL="h", CC="c", T_CD=["260519"]).to_pc2()
        self.assertNotIn("USR_ANAL", pc2.to_dict())
        self.assertEqual(pc2.to_dict()["CC"], "c")


if __name__ == "__main__":
    unittest.main()
