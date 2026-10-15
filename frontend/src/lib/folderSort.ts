import type { FolderItem } from '../api/client'

export type SortColumn = 'filename' | 'kind'
export type SortDirection = 'asc' | 'desc'

export interface FolderSortState {
  column: SortColumn
  direction: SortDirection
}

const filenameCollator = new Intl.Collator('ko-KR', {
  numeric: true,
  sensitivity: 'base',
})

function compareFilename(left: FolderItem, right: FolderItem) {
  return filenameCollator.compare(left.filename, right.filename)
}

export function nextFolderSort(current: FolderSortState, column: SortColumn): FolderSortState {
  if (current.column !== column) return { column, direction: 'asc' }
  return { column, direction: current.direction === 'asc' ? 'desc' : 'asc' }
}

export function sortFolderItems(
  items: readonly FolderItem[],
  column: SortColumn,
  direction: SortDirection,
) {
  return [...items].sort((left, right) => {
    const primary = column === 'filename'
      ? compareFilename(left, right)
      : filenameCollator.compare(left.kind, right.kind)
    if (primary !== 0) return direction === 'asc' ? primary : -primary

    const filename = compareFilename(left, right)
    if (filename !== 0) return filename
    return filenameCollator.compare(left.id, right.id)
  })
}
