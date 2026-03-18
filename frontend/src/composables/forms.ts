import { FormInst } from "naive-ui"

export async function validateForm(formRef: FormInst | null) {
    try {
        if (!formRef) {
            return false
        }
        await formRef.validate()
        return true
    } catch (err) {
        window.$message.error('Complete all required fields on the form.')
        return false
    }
}