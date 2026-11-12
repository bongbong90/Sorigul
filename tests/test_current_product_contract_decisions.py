"""Issue #147 contracts: #127 parity decisions are locked in the canonical product contract."""

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
CONTRACT = REPO_ROOT / "docs" / "project" / "CURRENT_PRODUCT_CONTRACT.md"


def contract_text():
    return CONTRACT.read_text(encoding="utf-8")


def section(text, start_heading, end_prefix):
    start = text.index(start_heading)
    end = text.index(end_prefix, start + len(start_heading))
    return text[start:end]


def decision_rows(text):
    lock = section(text, "### #127 parity decision lock", "## 5.")
    rows = {}
    for line in lock.splitlines():
        match = re.match(r"^\|\s*(A[1-5])\s*\|(.+)\|\s*$", line)
        if match:
            rows[match.group(1)] = [cell.strip() for cell in match.group(2).split("|")]
    return rows


def test_contract_remains_locked_and_cites_127_provenance():
    text = contract_text()
    assert "Status: `LOCKED`" in text
    assert "#127" in text
    for issue in ("#130", "#131", "#132", "#133"):
        assert issue in text


def test_all_five_decisions_are_recorded_with_expected_classification():
    rows = decision_rows(contract_text())
    assert sorted(rows) == ["A1", "A2", "A3", "A4", "A5"]
    expected = {
        "A1": ("RESTORE", "PRESERVED", "#130"),
        "A2": ("RESTORE", "PRESERVED", "#131"),
        "A3": ("RESTORE", "PRESERVED", "#132"),
        "A4": ("APPROVED REMOVAL", "APPROVED_INTENTIONAL_CHANGE", None),
        "A5": ("RESTORE FOR DISPLAY ONLY", "PRESERVED", "#133"),
    }
    for key, (decision, classification, implementation) in expected.items():
        _, row_decision, row_classification, row_implementation, _ = rows[key]
        assert row_decision == decision
        assert row_classification == classification
        if implementation is not None:
            assert implementation in row_implementation
    assert "#127 기준 AMBIGUOUS 잔여: **0**" in contract_text()


def test_a4_queue_clear_is_an_approved_removal_not_a_restoration():
    text = contract_text()
    rows = decision_rows(text)
    assert "RESTORE" not in rows["A4"][1]
    assert "PRESERVED" not in rows["A4"][2]

    changes = section(text, "## 5. Approved Intentional Changes", "## 6.")
    queue = changes[changes.index("### N. Queue clear"):]
    assert "복구하지 않는다" in queue
    assert "filesystem truth" in queue
    assert "§5D" in queue
    assert "파일 삭제" in queue

    preserved = section(text, "## 4. Preserved Legacy contracts", "### #127 parity decision lock")
    assert "queue clear" not in preserved.lower()

    supersession = section(text, "## 11. Contract supersession map", "## 12.")
    queue_rows = [line for line in supersession.splitlines() if line.startswith("| Queue clear")]
    assert len(queue_rows) == 1
    assert "Removed" in queue_rows[0]
    assert "Approved Intentional Change" in queue_rows[0]
    assert "#127 A4" in queue_rows[0]


def test_restored_affordances_carry_their_current_constraints():
    text = contract_text()
    preserved = section(text, "## 4. Preserved Legacy contracts", "### #127 parity decision lock")

    colab = section(preserved, "### Colab", "### Folders and Desktop")
    assert "Colab 열기" in colab
    assert "bootstrap" in colab

    desktop = preserved[preserved.index("### Folders and Desktop"):]
    assert "Tray tooltip" in desktop
    assert "fabricated progress/ETA는 금지" in desktop
    assert "파일명/유형만 sortable" in desktop
    assert "상태/수정일은 non-sortable" in desktop
    assert "utf-8-sig → utf-8 → cp949 → euc-kr → utf-8 errors=replace" in desktop
    assert "display only" in desktop
    assert "rewrite/transcode하지 않는다" in desktop
