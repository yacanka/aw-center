<template>
  <n-space vertical size="large">
    <n-card title="Requirement PoC Linker">
      <n-alert :type="runner?.available ? 'success' : 'warning'" :bordered="false">
        {{ readinessMessage }} The operation runs as a validated, durable Windows automation job.
      </n-alert>

      <n-form label-placement="top" style="margin-top: 16px">
        <n-grid :cols="12" :x-gap="12" responsive="self" item-responsive>
          <n-form-item-gi :span="12" label="Reference module">
            <n-input v-model:value="form.ref_module_name" placeholder="/Project/Reference Module" />
          </n-form-item-gi>
          <n-form-item-gi :span="12" label="Target module">
            <n-input v-model:value="form.target_module_name" placeholder="/Project/Target Module" />
          </n-form-item-gi>
          <n-form-item-gi :span="12" label="Link module">
            <n-input v-model:value="form.link_module_name" placeholder="/Project/Links" />
          </n-form-item-gi>
          <n-form-item-gi span="0:12 700:4" label="Reference PoC-list attribute">
            <n-input v-model:value="form.ref_attr_poc" placeholder="PoC List" />
          </n-form-item-gi>
          <n-form-item-gi span="0:12 700:4" label="Reference requirement attribute">
            <n-input v-model:value="form.ref_attr_req" placeholder="Requirement" />
          </n-form-item-gi>
          <n-form-item-gi span="0:12 700:4" label="Target PoC attribute">
            <n-input v-model:value="form.target_attr_poc" placeholder="PoC Info" />
          </n-form-item-gi>
          <n-form-item-gi span="0:12 700:3" label="Start index">
            <n-input-number v-model:value="form.start_index" :min="0" style="width: 100%" />
          </n-form-item-gi>
          <n-form-item-gi span="0:12 700:3" label="Text length (-1 = remaining text)">
            <n-input-number v-model:value="form.text_length" :min="-1" style="width: 100%" />
          </n-form-item-gi>
          <n-form-item-gi span="0:12 700:3" label="Example text">
            <n-input v-model:value="testText" />
          </n-form-item-gi>
          <n-form-item-gi span="0:12 700:3" label="Derived PoC key">
            <n-input :value="cropPreview" readonly />
          </n-form-item-gi>
        </n-grid>

        <n-grid :cols="12" :x-gap="12" responsive="self" item-responsive>
          <n-form-item-gi span="0:12 700:3" label="Mode">
            <n-switch
              v-model:value="form.activeness"
              :disabled="!canCreateLinks"
              :checked-value="true"
              :unchecked-value="false"
            >
              <template #checked>Link</template>
              <template #unchecked>Show only</template>
            </n-switch>
          </n-form-item-gi>
          <n-form-item-gi v-if="form.activeness" span="0:12 700:4" label="Link direction">
            <n-select v-model:value="form.direction" :options="directionOptions" />
          </n-form-item-gi>
          <n-form-item-gi :span="form.activeness ? '0:12 700:5' : '0:12 700:9'" label="Behavior">
            <n-text>
              {{
                form.activeness
                  ? `Creates missing links; ${sourceDescription} is the link source.`
                  : 'Groups requirements and reports matching targets without changing DOORS.'
              }}
            </n-text>
          </n-form-item-gi>
        </n-grid>

        <n-alert v-if="!canCreateLinks" type="info" :bordered="false" style="margin-bottom: 16px">
          Preview is available to authenticated users. Creating links requires administrator access.
        </n-alert>
        <n-space justify="center">
          <n-button :loading="statusLoading" @click="loadStatus">Refresh runner status</n-button>
          <n-popconfirm
            v-if="form.activeness"
            positive-text="Create links"
            negative-text="Cancel"
            @positive-click="queue"
          >
            <template #trigger>
              <n-button type="error" :loading="queueing" :disabled="!canQueue">
                Queue link creation
              </n-button>
            </template>
            This writes links to DOORS in the selected direction. Continue?
          </n-popconfirm>
          <n-button v-else type="primary" :loading="queueing" :disabled="!canQueue" @click="queue">
            Queue preview
          </n-button>
        </n-space>
      </n-form>
    </n-card>

    <n-alert v-if="errorMessage" type="error" closable @close="errorMessage = ''">
      {{ errorMessage }}
    </n-alert>
    <PageJobStatus
      :job="job"
      :cancelling="cancelling"
      :downloading="downloading"
      download-label="Download complete JSON"
      @cancel="cancel"
      @download="download"
      @open="openJobCenter"
    />

    <n-card v-if="result" title="Linker result">
      <n-grid cols="1 480:2 900:4" responsive="screen" :x-gap="12" :y-gap="12">
        <n-gi><n-statistic label="PoC groups" :value="result.summary.groups" /></n-gi>
        <n-gi><n-statistic label="Matched targets" :value="result.summary.matched_targets" /></n-gi>
        <n-gi><n-statistic label="Created links" :value="result.summary.created_links" /></n-gi>
        <n-gi><n-statistic label="Existing links" :value="result.summary.existing_links" /></n-gi>
      </n-grid>
      <n-alert
        v-if="result.missing_targets.length"
        type="warning"
        title="Target objects not found"
        style="margin: 16px 0"
      >
        {{ result.missing_targets.slice(0, 20).join(', ') }}
        <template v-if="result.missing_targets.length > 20">
          — download the JSON result for the complete list.
        </template>
      </n-alert>
      <n-spin :show="resultLoading">
        <n-collapse>
          <n-collapse-item
            v-for="group in visibleGroups"
            :key="group.poc"
            :title="group.poc || '(empty PoC key)'"
          >
            <template #header-extra>
              <n-tag :type="group.target_found ? 'success' : 'warning'">
                {{ group.target_found ? 'Target found' : 'Target missing' }}
              </n-tag>
            </template>
            <n-list bordered>
              <n-list-item v-for="(requirement, index) in group.requirements" :key="index">
                {{ requirement }}
              </n-list-item>
            </n-list>
          </n-collapse-item>
        </n-collapse>
      </n-spin>
      <n-alert
        v-if="result.groups.length > visibleGroups.length"
        type="info"
        style="margin-top: 16px"
      >
        Showing the first {{ visibleGroups.length }} groups. Download the JSON result for all
        groups.
      </n-alert>
    </n-card>
  </n-space>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import PageJobStatus from '@/features/jobs/components/PageJobStatus.vue'
import { usePocLinker } from '@/features/tools/composables/usePocLinker'

const directionOptions = [
  { label: 'Reference → Target', value: 'ref2tar' },
  { label: 'Target → Reference', value: 'tar2ref' }
]

const {
  runner,
  cancel,
  cancelling,
  canCreateLinks,
  canQueue,
  cropPreview,
  download,
  downloading,
  errorMessage,
  form,
  job,
  loadStatus,
  openJobCenter,
  queue,
  queueing,
  readinessMessage,
  result,
  resultLoading,
  statusLoading,
  testText,
  visibleGroups
} = usePocLinker()

const sourceDescription = computed(() =>
  form.direction === 'ref2tar' ? 'the reference module' : 'the target module'
)
</script>
