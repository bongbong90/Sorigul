"""Issue #132 contracts for Legacy-compatible Folders sorting."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SORT_HELPER = REPO_ROOT / "frontend" / "src" / "lib" / "folderSort.ts"


def read_repo(path):
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def test_only_filename_and_kind_headers_are_sortable():
    page = read_repo("frontend/src/pages/FoldersPage.tsx")
    helper = SORT_HELPER.read_text(encoding="utf-8")

    assert "type SortColumn = 'filename' | 'kind'" in helper
    assert "changeSort('filename')" in page
    assert "changeSort('kind')" in page
    assert "changeSort('status')" not in page
    assert "changeSort('modified_at')" not in page
    assert page.count("aria-sort=") == 2
    assert "<th>상태</th><th>수정일</th>" in page


def test_sort_is_presentation_only_and_refresh_preserves_sort_state():
    page = read_repo("frontend/src/pages/FoldersPage.tsx")
    helper = SORT_HELPER.read_text(encoding="utf-8")

    assert "const [sortColumn, setSortColumn] = useState<SortColumn>('filename')" in page
    assert "const [sortDirection, setSortDirection] = useState<SortDirection>('asc')" in page
    refresh = page[page.index("const refresh = useCallback(") : page.index("useEffect(() => { void refresh()")]
    assert "setSortColumn" not in refresh and "setSortDirection" not in refresh
    assert "sortFolderItems(files, sortColumn, sortDirection)" in page
    assert "[...items].sort(" in helper
    assert "items.sort(" not in helper
    assert "/folders/scan" not in helper


HARNESS = r"""
import { pathToFileURL } from 'node:url'
const { nextFolderSort, sortFolderItems } = await import(pathToFileURL(process.argv[2]).href)

const item = (id, filename, kind) => ({
  id, filename, kind, status: 'RESULT', size: 1,
  modified_at: '2026-09-30T00:00:00Z', has_source: false,
})
const source = [
  item('10', '민법_10강.txt', 'TXT'),
  item('2', '민법_2강.txt', 'TXT'),
  item('1', '민법_1강.txt', 'TXT'),
  item('j-b', '나.json', 'JSON'),
  item('j-a', '가.json', 'JSON'),
  item('same-b', '같음.srt', 'SRT'),
  item('same-a', '같음.srt', 'SRT'),
]
const names = (column, direction) => sortFolderItems(source, column, direction).map((entry) => entry.filename)
const ids = (column, direction) => sortFolderItems(source, column, direction).map((entry) => entry.id)

let state = { column: 'filename', direction: 'asc' }
const transitions = [`${state.column}:${state.direction}`]
for (const column of ['filename', 'filename', 'kind', 'kind', 'filename']) {
  state = nextFolderSort(state, column)
  transitions.push(`${state.column}:${state.direction}`)
}

console.log(JSON.stringify({
  filenameAsc: names('filename', 'asc'),
  filenameDesc: names('filename', 'desc'),
  kindAsc: names('kind', 'asc'),
  kindDesc: names('kind', 'desc'),
  stableIds: ids('kind', 'asc').filter((id) => id.startsWith('same-')),
  sourceOrder: source.map((entry) => entry.id),
  transitions,
}))
"""


def test_sort_helper_behavior_and_state_transitions(tmp_path):
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not available")
    harness = tmp_path / "folders-sort.mjs"
    harness.write_text(HARNESS, encoding="utf-8")
    completed = subprocess.run(
        [node, str(harness), str(SORT_HELPER)],
        capture_output=True, text=True, encoding="utf-8", timeout=60,
    )
    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout.strip().splitlines()[-1])

    numeric = [name for name in result["filenameAsc"] if name.startswith("민법_")]
    assert numeric == ["민법_1강.txt", "민법_2강.txt", "민법_10강.txt"]
    numeric_desc = [name for name in result["filenameDesc"] if name.startswith("민법_")]
    assert numeric_desc == list(reversed(numeric))
    assert result["kindAsc"].index("가.json") < result["kindAsc"].index("나.json")
    assert result["kindDesc"].index("같음.srt") < result["kindDesc"].index("가.json")
    assert result["stableIds"] == ["same-a", "same-b"]
    assert result["sourceOrder"] == ["10", "2", "1", "j-b", "j-a", "same-b", "same-a"]
    assert result["transitions"] == [
        "filename:asc", "filename:desc", "filename:asc",
        "kind:asc", "kind:desc", "filename:asc",
    ]
