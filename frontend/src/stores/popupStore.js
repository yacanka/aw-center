import { defineStore } from "pinia"

export const popupStore = defineStore(
    "popup",
    {
      state: () => ({
        closable: false,
        visible: false,
        title: null,
        text_content: null,
        list_content: null,
      }),
      actions: {
        open(title, content, closable=true) {
            this.closable = closable
            this.visible = true
            this.title = title
            if (typeof(content) === "string"){
              this.text_content = content
            }else if(Array.isArray(content)){
              this.list_content = content
            }
        },
        close() {
            this.visible = false
            //this.text_content = null
            //this.list_content = null
      }
    }
})