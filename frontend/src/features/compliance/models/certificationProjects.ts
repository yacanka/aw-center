import type { ProjectRegistryItem } from '@/features/projects/models/projectRegistry'

const families = [
  { key: 'gokbey', label: 'GÖKBEY', slugs: ['gokbey', 'gokbey_jandarma', 'gokbey_sivil'] },
  { key: 'kaan', label: 'KAAN', slugs: ['mmu'] },
  { key: 'hurkus', label: 'HÜRKUŞ-2', slugs: ['hyeu', 'hurkus_aviyonik'] },
  { key: 'hurjet', label: 'HÜRJET', slugs: ['hjt', 'hsp', 'navy', 'hurjet'] },
  { key: 'stc1', label: 'ASOJ-STC1', slugs: ['havasoj_stc1'] },
  { key: 'stc2', label: 'ASOJ-STC2', slugs: ['havasoj_stc2'] },
  { key: 'ozgur', label: 'Özgür', slugs: ['aesa', 'blok30', 'blok4050', 'hys', 'ozgur'] }
]

export function certificationCards(projects: ProjectRegistryItem[]) {
  const remaining = new Map(projects.map((project) => [project.slug, project]))
  const cards = families.flatMap(({ key, label, slugs }) => {
    const members = slugs.flatMap((slug) => {
      const project = remaining.get(slug)
      remaining.delete(slug)
      return project ? [project] : []
    })
    return members.length ? [{ key, label, members }] : []
  })
  return cards.concat(
    [...remaining.values()].map((project) => ({
      key: project.slug,
      label: project.name,
      members: [project]
    }))
  )
}
