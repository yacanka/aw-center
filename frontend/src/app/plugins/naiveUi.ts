import {
  create,
  NAlert,
  NButton,
  NCard,
  NConfigProvider,
  NDialogProvider,
  NForm,
  NFormItemGi,
  NFlex,
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
  NTag,
  NText
} from 'naive-ui'

/** Components required before authentication; keep the login graph intentionally small. */
export const NAIVE_UI_COMPONENTS = [
  NAlert,
  NButton,
  NCard,
  NConfigProvider,
  NDialogProvider,
  NForm,
  NFormItemGi,
  NFlex,
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
  NTag,
  NText
] as const

export const naiveUi = create({ components: [...NAIVE_UI_COMPONENTS] })
