type NotificationLevel = "success" | "warning" | "error" | "info"

function notify(level: NotificationLevel, message: string, title: string, duration = 3000) {
  window.$notification[level]({
    title,
    content: message,
    duration,
  })
}

export function notifySuccess(message = "", title = "Success", duration = 3000) {
  notify("success", message, title, duration)
}

export function notifyWarning(message = "", title = "Warning", duration = 3000) {
  notify("warning", message, title, duration)
}

export function notifyError(message = "", title = "Error", duration = 3000) {
  notify("error", message, title, duration)
}

export function showErrorMessage(message: string) {
  window.$message.error(message)
}
