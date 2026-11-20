import { expect, it } from 'vitest'
import type { ProjectRegistryItem } from '@/features/projects/models/projectRegistry'
import { certificationCards } from './certificationProjects'

function project(slug: string): ProjectRegistryItem {
  return {
    slug,
    name: slug,
    capabilities: ['compliance'],
    roles: { compliance: 'viewer', jira: null, organization: null }
  }
}

it('keeps the reference order and includes each accessible project exactly once', () => {
  const projects = [
    'other',
    'mmu',
    'havasoj_stc2',
    'hjt',
    'hyeu',
    'navy',
    'gokbey_jandarma',
    'havasoj_stc1',
    'bkm',
    'aesa'
  ].map(project)
  const cards = certificationCards(projects)
  expect(cards.map((card) => card.label)).toEqual([
    'GÖKBEY',
    'KAAN',
    'HÜRKUŞ-2',
    'HÜRJET',
    'ASOJ-STC1',
    'ASOJ-STC2',
    'Özgür',
    'other',
    'bkm'
  ])
  expect(cards.flatMap((card) => card.members.map((item) => item.slug)).sort()).toEqual(
    projects.map((item) => item.slug).sort()
  )
  expect(cards.find((card) => card.key === 'hurjet')?.members).toEqual([
    project('hjt'),
    project('navy')
  ])
})

it('omits families with no accessible projects', () => {
  expect(certificationCards([])).toEqual([])
  expect(certificationCards([project('gokbey_sivil')])).toEqual([
    { key: 'gokbey', label: 'GÖKBEY', members: [project('gokbey_sivil')] }
  ])
})
