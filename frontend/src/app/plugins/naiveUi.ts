import {
  create,
  NButton,
  NCard,
  NConfigProvider,
  NDialogProvider,
  NForm,
  NFormItemGi,
  NGrid,
  NInput,
  NLoadingBarProvider,
  NMessageProvider,
  NModal,
  NNotificationProvider,
  NSpace,
  NSpin,
  NTabPane,
  NTabs,
  NTag
} from 'naive-ui'

/** Components required before authentication; keep the login graph intentionally small. */
export const NAIVE_UI_COMPONENTS = [
  NButton,
  NCard,
  NConfigProvider,
  NDialogProvider,
  NForm,
  NFormItemGi,
  NGrid,
  NInput,
  NLoadingBarProvider,
  NMessageProvider,
  NModal,
  NNotificationProvider,
  NSpace,
  NSpin,
  NTabPane,
  NTabs,
  NTag
] as const

export const naiveUi = create({ components: [...NAIVE_UI_COMPONENTS] })
