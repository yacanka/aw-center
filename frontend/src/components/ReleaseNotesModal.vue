<template>
    <n-modal v-model:show="store.show" preset="card"
        :title="store.current ? `AW Center (v${store.current.version}) Release Notes` : 'Update'"
        :closable="store.current ? !store.current.requires_ack : true"
        :mask-closable="store.current ? !store.current.requires_ack : true" style="width: min(920px, 92vw);"
        @close="store.closeIfAllowed">
        <n-carousel v-if="store.current" direction="horizontal" dot-type="line" dot-placement="bottom" draggable
            autoplay style="margin-bottom: -24px;">
            <n-carousel-item v-for="item in store.current.items">
                <n-h2>
                    {{ item.heading }}
                    <n-tag size="tiny" style="margin-left: 8px'; justify-content: center;"
                        :type="tagType(item.item_type)">
                        {{ item.item_type }}
                    </n-tag>
                </n-h2>
                <n-divider style="margin: -16px 0 0 0" />
                <div class="release-body" style="margin-bottom: 60px" v-html="md.render(item.body_md)"></div>
            </n-carousel-item>
        </n-carousel>

        <div style="display:flex; justify-content:flex-end; gap:8px; margin-top: 8px;">
            <n-button v-if="store.current?.requires_ack" type="primary" @click="onAck">
                I've read
            </n-button>
        </div>
    </n-modal>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { useReleaseNotesStore } from "@/stores/releaseNotes";
import MarkdownIt from "markdown-it";

const store = useReleaseNotesStore();

const md = new MarkdownIt({
    html: false, 
    linkify: true,
    breaks: true,
});

function tagType(noteType: string) {
    if (noteType === "breaking") return "error";
    if (noteType === "feature") return "success";
    if (noteType === "fix") return "warning";
    return "default";
}

async function onAck() {
    await store.acknowledge();
}
</script>

<style scoped>
.release-body :deep(h1),
.release-body :deep(h2),
.release-body :deep(h3) {
    margin: 8px 0;
}

.release-body :deep(p) {
    margin: 6px 0;
    line-height: 1.5;
}

.release-body :deep(ul) {
    padding-left: 18px;
}
</style>