// @vitest-environment jsdom
import { effectScope, ref } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useMermaidProject } from './useMermaidProject'

const scopes: ReturnType<typeof effectScope>[] = []
function workspace(userId = ref<number | undefined>(7)) {
  const scope = effectScope()
  scopes.push(scope)
  return { userId, state: scope.run(() => useMermaidProject(userId))! }
}
beforeEach(() => {
  localStorage.clear()
  vi.useFakeTimers()
})
afterEach(() => {
  scopes.splice(0).forEach((scope) => scope.stop())
  vi.useRealTimers()
  vi.restoreAllMocks()
})

describe('account-scoped Mermaid workspace', () => {
  it('rejects an imported file that finishes after its workspace was disposed', async () => {
    const scope = effectScope()
    scopes.push(scope)
    const state = scope.run(() => useMermaidProject(ref(7)))!
    let finish!: (text: string) => void
    const opening = state.readFile({
      name: 'late.mmdproj',
      size: 100,
      text: () =>
        new Promise<string>((resolve) => {
          finish = resolve
        })
    } as File)
    scope.stop()
    finish(
      JSON.stringify({
        format: 'mermaid-atolyesi-project',
        version: 1,
        name: 'Late',
        activeDiagramId: 'one',
        diagrams: [{ id: 'one', title: 'One', code: 'late import', theme: 'studio' }]
      })
    )
    await expect(opening).rejects.toThrow(/Dosya okunurken/)
  })
  it('rejects a file that finishes reading after the account changed', async () => {
    const { state, userId } = workspace()
    let finish!: (text: string) => void
    const file = {
      name: 'old.mmdproj',
      size: 100,
      text: () =>
        new Promise<string>((resolve) => {
          finish = resolve
        })
    } as File
    const opening = state.readFile(file)
    userId.value = 8
    finish(
      JSON.stringify({
        format: 'mermaid-atolyesi-project',
        version: 1,
        name: 'Old',
        activeDiagramId: 'one',
        diagrams: [{ id: 'one', title: 'One', code: 'old account', theme: 'studio' }]
      })
    )
    await expect(opening).rejects.toThrow(/Dosya okunurken/)
    expect(state.active.value.code).not.toBe('old account')
  })
  it('keeps independent undo histories across tab changes', () => {
    const { state } = workspace()
    const first = state.active.value.id
    state.editCode('first')
    state.editCode('second')
    state.undo()
    expect(state.active.value.code).toBe('first')
    state.addDiagram('other', 'Other')
    state.editCode('other changed')
    state.selectDiagram(first)
    expect(state.active.value.code).toBe('first')
    state.redo()
    expect(state.active.value.code).toBe('second')
  })
  it('creates a blank diagram after removing the last tab', () => {
    const { state } = workspace()
    state.removeDiagram(state.active.value.id)
    expect(state.project.value.diagrams).toHaveLength(1)
    expect(state.active.value.code).toBe('')
  })
  it('flushes old edits to the old account before switching accounts', () => {
    const { state, userId } = workspace()
    state.editCode('account seven')
    userId.value = 8
    expect(state.active.value.code).not.toBe('account seven')
    state.editCode('account eight')
    state.flush()
    userId.value = 7
    expect(state.active.value.code).toBe('account seven')
    userId.value = 8
    expect(state.active.value.code).toBe('account eight')
  })
  it('autosaves after 450 ms and restores the active project', () => {
    const { state } = workspace()
    state.editCode('saved locally')
    vi.advanceTimersByTime(449)
    expect(localStorage.length).toBe(0)
    vi.advanceTimersByTime(1)
    expect(workspace().state.active.value.code).toBe('saved locally')
  })
  it('retains in-memory edits when browser storage fails', () => {
    const { state } = workspace()
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new DOMException('Full', 'QuotaExceededError')
    })
    state.editCode('do not lose this')
    state.flush()
    expect(state.active.value.code).toBe('do not lose this')
    expect(state.storageError.value).toBeTruthy()
  })
  it('does not replace the current project when an imported file is invalid', async () => {
    const { state } = workspace()
    state.editCode('keep')
    await expect(state.readFile(new File(['{}'], 'bad.mmdproj'))).rejects.toThrow()
    expect(state.active.value.code).toBe('keep')
    await expect(state.readFile({ name: 'big.mmdproj', size: 16777217 } as File)).rejects.toThrow(
      /16/
    )
  })
})
