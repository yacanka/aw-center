<script setup lang="ts">
import JiraConnection from '../components/JiraConnection.vue'
import JiraDocumentGeneration from '../components/JiraDocumentGeneration.vue'
import JiraTemplateLibrary from '../components/JiraTemplateLibrary.vue'
</script>
<template>
  <n-flex justify="center">
    <n-card title="Documents" class="app-page-container">
      <n-tabs type="line" default-value="generate">
        <n-tab-pane name="generate" tab="Generate document">
          <JiraConnection><JiraDocumentGeneration /></JiraConnection>
        </n-tab-pane>
        <n-tab-pane name="library" tab="Template library"><JiraTemplateLibrary /></n-tab-pane>
      </n-tabs>
    </n-card>
  </n-flex>
</template>
