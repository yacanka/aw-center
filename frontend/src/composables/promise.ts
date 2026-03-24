import { setAuthToken } from "@/services/http"
import { notifyWarning } from "@/services/notify"
import { removeKey, STORAGE_KEYS } from "@/services/storage"
import { isPlainObject } from "@/utils/general"
import { isJsonString } from "@/utils/text"

export async function handleRequest<T>(request: Promise<any>, onSuccess: (data: T) => void, onError: (errorMsg: string) => void, onFinally?: () => void) {
    try {
        const res = await request
        console.log(res)

        if (res.status == 200 || res.status == 201 || res.status == 204) {
            onSuccess(res.data?.message || res.data)
            return res.data
        } else {
            onError(res.data)
            throw new Error(res.data?.message || "Request failed with status: " + res.status);
        }
    } catch (err: any) {
        const data = err?.response?.data || {}
        let errorRepresentation = "Something went wrong."

        if (data.detail) {
            errorRepresentation = data.detail
            if (err?.response?.status == 401 && data.detail == "Invalid token.") {
                removeKey(STORAGE_KEYS.token)
                removeKey(STORAGE_KEYS.user)
                removeKey(STORAGE_KEYS.project)
                setAuthToken(null)
                notifyWarning("Login required.", "Invalid Token")
            }
        }
        else if (data.message) {
            errorRepresentation = data.message
        }
        else if (isPlainObject(data)) {
            errorRepresentation = Object.entries(data).map(([key, value]) => `${key}: ${value}`).join("\n");
        } else if (isJsonString(data)) {
            const parsed = JSON.parse(data);
            errorRepresentation = Object.entries(parsed["errors"]).map(([key, value]) => `${key}: ${value}`).join("\n");
        }

        onError(errorRepresentation)
        console.error(err)
        throw errorRepresentation;
    } finally {
        onFinally?.()
    }
}
