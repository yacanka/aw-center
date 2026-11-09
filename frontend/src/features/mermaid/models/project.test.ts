import { describe, expect, it } from 'vitest'
import {
  createDiagram,
  createProject,
  parseProject,
  serializeProject,
  validateProject
} from './project'

const fixture = {
  format: 'mermaid-atolyesi-project',
  version: 1,
  name: 'Örnek proje',
  activeDiagramId: 'flow-1',
  diagrams: [{ id: 'flow-1', title: 'Akış', code: 'flowchart LR\n A --> B', theme: 'studio' }]
}

describe('portable Mermaid projects', () => {
  it('opens the standalone v1 format without changing code, theme or selected tab', () => {
    expect(parseProject('\uFEFF' + JSON.stringify(fixture))).toEqual(fixture)
    expect(JSON.parse(serializeProject(parseProject(JSON.stringify(fixture))))).toEqual(fixture)
  })
  it('rejects malformed JSON and unsupported versions without executing data', () => {
    expect(() => parseProject('{')).toThrow(/JSON/)
    expect(() => validateProject({ ...fixture, version: 2 })).toThrow(/sürüm/)
    expect(() =>
      validateProject({ ...fixture, diagrams: [{ ...fixture.diagrams[0], theme: 'loose' }] })
    ).toThrow(/tema/)
  })
  it('rejects duplicate or missing active diagram identities', () => {
    expect(() =>
      validateProject({ ...fixture, diagrams: [fixture.diagrams[0], fixture.diagrams[0]] })
    ).toThrow(/kimliği/)
    expect(() => validateProject({ ...fixture, activeDiagramId: 'missing' })).toThrow(/seçili/)
  })
  it('enforces source, total source and tab limits at their boundaries', () => {
    expect(createDiagram({ code: 'x'.repeat(120000) }).code).toHaveLength(120000)
    expect(() => createDiagram({ code: 'x'.repeat(120001) })).toThrow(/120.000/)
    expect(
      createProject(
        'Tabs',
        Array.from({ length: 200 }, () => createDiagram())
      ).diagrams
    ).toHaveLength(200)
    expect(() =>
      createProject(
        'Tabs',
        Array.from({ length: 201 }, () => createDiagram())
      )
    ).toThrow(/200/)
    const diagrams = Array.from({ length: 34 }, () => createDiagram({ code: 'x'.repeat(120000) }))
    expect(() => createProject('Large', diagrams)).toThrow(/4.000.000/)
  })
  it('normalizes labels by Unicode code points and rejects control characters', () => {
    expect(createDiagram({ title: '😀'.repeat(100) }).title).toBe('😀'.repeat(90))
    expect(() => createProject('bad\nname')).toThrow(/kontrol/)
  })
})
