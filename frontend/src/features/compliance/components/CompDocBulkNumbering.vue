<script setup lang="ts">
import { computed, toRef } from 'vue'
import type { ICompDoc } from '../models/compdocs'
import NumberingContextFields from './NumberingContextFields.vue'
import { useBulkNumbering } from '../composables/bulkNumbering'

const props = defineProps<{ project: string; canEdit: boolean; documents: ICompDoc[] }>()
const emit = defineEmits<{ updated: [document: unknown] }>()
const state = useBulkNumbering(
  props.project,
  toRef(props, 'canEdit'),
  (document) => emit('updated', document),
  toRef(props, 'documents')
)
const {
  visible,
  loading,
  submitting,
  refreshing,
  started,
  available,
  formats,
  format,
  error,
  rows,
  selected,
  completed,
  canSubmit
} = state
const allSelected = computed(
  () => rows.value.length > 0 && selected.value.length === rows.value.length
)
function selectAll(event: Event) {
  const checked = (event.target as HTMLInputElement).checked
  rows.value.forEach((row) => {
    row.selected = checked
  })
}
defineExpose({ open: state.open })
</script>

<template>
  <n-modal
    :show="visible"
    :mask-closable="!submitting"
    :close-on-esc="!submitting"
    @update:show="!$event && state.close()"
  >
    <section
      class="bulk-numbering"
      role="dialog"
      aria-modal="true"
      aria-labelledby="bulk-numbering-title"
      :aria-busy="loading || submitting"
    >
      <header>
        <div>
          <h2 id="bulk-numbering-title">Assign cover page numbers</h2>
          <p>{{ project.toUpperCase() }} · Missing cover page numbers on the current table page</p>
        </div>
        <button class="secondary" :disabled="submitting" @click="state.close">Close</button>
      </header>
      <div v-if="loading" class="notice" role="status">Loading number formats…</div>
      <div v-else-if="error" class="notice" role="alert">
        <p>{{ error }}</p>
        <button class="secondary" @click="state.load">Retry loading</button>
      </div>
      <template v-else>
        <div class="scope">
          <div class="count-block">
            <strong class="count">{{ started ? completed : selected.length }}</strong>
            <span>{{
              started ? `of ${selected.length} assigned` : `of ${rows.length} documents selected`
            }}</span>
          </div>
          <div class="format-field">
            <label for="bulk-numbering-format">Number format</label>
            <select id="bulk-numbering-format" v-model="format" :disabled="started || !available">
              <option disabled value="">Select a format</option>
              <option v-for="value in formats" :key="value" :value="value">{{ value }}</option>
            </select>
            <p>
              Applies only to selected documents on the current table page. Existing requests keep
              their original format.
            </p>
          </div>
        </div>
        <NumberingContextFields
          v-if="available && format"
          class="context-inputs"
          id-prefix="bulk-context"
          :fields="state.context.fields.value"
          :values="state.context.values.value"
          :loading="state.context.loading.value"
          :error="state.context.error.value"
          :disabled="started || !canEdit"
          @update:values="state.context.values.value = $event"
          @retry="state.context.load"
        />
        <p v-if="!available" class="notice" role="status">
          Numarator is not configured for this project.
        </p>
        <p v-else-if="!rows.length" class="notice" role="status">
          No active documents on this table page have missing cover page numbers.
        </p>
        <div v-if="rows.length" class="document-list" tabindex="0" aria-label="Documents to number">
          <table>
            <thead>
              <tr>
                <th class="selection">
                  <input
                    type="checkbox"
                    aria-label="Select all documents"
                    :checked="allSelected"
                    :indeterminate="selected.length > 0 && !allSelected"
                    :disabled="started || !canEdit"
                    @change="selectAll"
                  />
                </th>
                <th>Document</th>
                <th>Technical document no.</th>
                <th>Result</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in rows" :key="row.document.id">
                <td class="selection">
                  <input
                    v-model="row.selected"
                    type="checkbox"
                    :aria-label="`Select ${row.document.name}`"
                    :disabled="started || !canEdit"
                  />
                </td>
                <td>
                  {{ row.document.name
                  }}<small class="mobile-reference">{{ row.document.tech_doc_no }}</small>
                </td>
                <td>{{ row.document.tech_doc_no || '—' }}</td>
                <td :class="{ assigned: row.allocation?.status === 'completed' }">
                  {{ state.status(row) }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <footer>
          <p v-if="started" role="status">
            {{
              submitting
                ? 'Submitting requests…'
                : 'Queued requests continue in the background. Reopen a document to recover an unfinished request.'
            }}
          </p>
          <p v-else>
            Each selected document receives its own number. Existing numbers are preserved.
          </p>
          <div class="actions">
            <button
              v-if="started && completed === selected.length"
              class="secondary"
              :disabled="submitting || refreshing"
              @click="state.chooseMore"
            >
              Choose more documents
            </button>
            <button
              v-if="started"
              class="secondary"
              :disabled="submitting || refreshing"
              @click="state.refresh"
            >
              {{ refreshing ? 'Refreshing…' : 'Refresh results' }}
            </button>
            <button class="primary" :disabled="!canSubmit" @click="state.submit">
              {{
                submitting
                  ? 'Submitting…'
                  : started
                    ? 'Retry unfinished'
                    : `Assign ${selected.length} numbers`
              }}
            </button>
          </div>
        </footer>
      </template>
    </section>
  </n-modal>
</template>

<style scoped>
.bulk-numbering {
  width: min(960px, calc(100vw - 32px));
  max-height: calc(100dvh - 48px);
  overflow: auto;
  background: #ffffff;
  color: #171717;
  font-family: 'Helvetica Neue', Helvetica, sans-serif;
  text-align: left;
  border: 1px solid #d6d6da;
}
header,
.scope,
footer {
  display: flex;
  justify-content: space-between;
  gap: 24px;
  padding: 24px;
}
header,
.scope {
  border-bottom: 1px solid #d6d6da;
}
h2 {
  margin: 0;
  font-size: 24px;
  font-weight: 600;
  letter-spacing: -0.6px;
}
p {
  margin: 8px 0 0;
  font-size: 14px;
  line-height: 1.5;
}
header button {
  align-self: flex-start;
}
.scope {
  background: #f7f7f8;
  align-items: center;
}
.count-block {
  display: flex;
  flex-direction: column;
  min-width: 200px;
}
.count {
  font-size: 64px;
  line-height: 1;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  letter-spacing: -3px;
  color: #002fa7;
}
.count-block span {
  font-size: 14px;
  margin-top: 12px;
}
.format-field {
  flex: 1;
  max-width: 460px;
}
label {
  display: block;
  font-size: 14px;
  font-weight: 600;
  margin-bottom: 8px;
}
select {
  width: 100%;
  padding: 10px;
  background: #ffffff;
  border: 1px solid #8c8c94;
  border-radius: 0;
  color: inherit;
  font: inherit;
}
.document-list {
  max-height: 340px;
  overflow: auto;
}
table {
  width: 100%;
  border-collapse: collapse;
  font-size: 14px;
}
th,
td {
  padding: 14px 16px;
  border-bottom: 1px solid #d6d6da;
  text-align: left;
  overflow-wrap: anywhere;
}
th {
  position: sticky;
  top: 0;
  background: #f7f7f8;
  font-weight: 600;
}
td {
  vertical-align: top;
}
.selection {
  width: 24px;
  padding-right: 0;
}
input {
  accent-color: #002fa7;
  width: 16px;
  height: 16px;
}
.assigned {
  color: #002fa7;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}
.context-inputs {
  padding: 20px 24px;
  border-bottom: 1px solid #d6d6da;
}
.mobile-reference {
  display: none;
}
.notice {
  padding: 24px;
}
footer {
  align-items: center;
}
footer p {
  max-width: 450px;
  margin: 0;
}
.actions {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}
button {
  padding: 10px 14px;
  border: 1px solid #002fa7;
  border-radius: 0;
  cursor: pointer;
  font: inherit;
  font-size: 14px;
}
.primary {
  background: #002fa7;
  color: #ffffff;
}
.secondary {
  background: #ffffff;
  color: #002fa7;
}
button:disabled,
select:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
button:focus-visible,
select:focus-visible,
input:focus-visible,
.document-list:focus-visible {
  outline: 2px solid #002fa7;
  outline-offset: 3px;
}
@media (max-width: 640px) {
  th:nth-child(3),
  td:nth-child(3) {
    display: none;
  }
  th:last-child {
    width: 30%;
  }
  .mobile-reference {
    display: block;
    margin-top: 4px;
  }
  header,
  .scope,
  footer {
    padding: 16px;
    gap: 16px;
  }
  .scope,
  footer {
    flex-direction: column;
    align-items: stretch;
  }
  .format-field {
    max-width: none;
  }
  .actions {
    flex-wrap: wrap;
  }
  th,
  td {
    padding: 10px;
  }
  h2 {
    font-size: 20px;
  }
}
</style>
