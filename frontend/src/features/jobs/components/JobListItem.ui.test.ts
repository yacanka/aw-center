// @vitest-environment jsdom

import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import JobListItem from '@/features/jobs/components/JobListItem.vue'
import type { Job } from '@/features/jobs/api/jobs'

describe('JobListItem', () => {
  it('renders reconciliation as terminal and never exposes generic retry', () => {
    const wrapper = mount(JobListItem, {
      props: { job: reconciliationJob(), active: false },
      global: {
        stubs: {
          NListItem: { template: '<section><slot /></section>' },
          NThing: {
            template:
              '<article><slot name="header-extra" /><slot /><slot name="action" /></article>'
          },
          NTag: { template: '<span><slot /></span>' },
          NSpace: { template: '<div><slot /></div>' },
          NProgress: { template: '<progress />' },
          NText: { template: '<span><slot /></span>' },
          NAlert: { template: '<aside><slot /></aside>' },
          NButton: { template: '<button><slot /></button>' }
        }
      }
    })

    expect(wrapper.text()).toContain('reconciliation required')
    expect(wrapper.text()).toContain('Reconcile the provider result before continuing.')
    expect(wrapper.findAll('button').map((button) => button.text())).toEqual(['Details'])
  })
})

function reconciliationJob(): Job {
  return {
    id: '00000000-0000-0000-0000-000000000001',
    kind: 'doors.update_object',
    title: 'Update DOORS object',
    status: 'reconciliation_required',
    progress: 100,
    message: 'Provider outcome is uncertain.',
    error_code: 'RECONCILIATION_REQUIRED',
    input_name: '',
    output_name: '',
    result_summary: {},
    attempt: 1,
    max_attempts: 3,
    source_job: null,
    workflow_run: null,
    workflow_step: null,
    request_id: 'request-1',
    created_at: '2026-08-17T00:00:00Z',
    started_at: '2026-08-17T00:00:01Z',
    completed_at: '2026-08-17T00:00:02Z',
    confirmation_expires_at: null,
    updated_at: '2026-08-17T00:00:02Z',
    can_cancel: false,
    download_url: null,
    recovery_hint: 'Reconcile the provider result before continuing.',
    jira_draft: null
  }
}
