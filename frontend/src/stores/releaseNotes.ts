import { defineStore } from "pinia";
import axios from "axios";
import { sleep } from "@/utils/general";

export type ReleaseNoteItem = {
    id: number;
    heading: string;
    body_md: string;
    item_type: "feature" | "fix" | "breaking" | "info" | "security";
    published_at: string;
    order: number;
};

export type ReleaseNote = {
    id: number;
    version: string;
    title: string;
    requires_ack: boolean;
    items: ReleaseNoteItem[];
}

export const useReleaseNotesStore = defineStore("releaseNotes", {
    state: () => ({
        loading: false as boolean,
        current: null as ReleaseNote | null,
        unseen_ids: [] as Array<number>,
        show: false as boolean,
        _checkedThisSession: false as boolean, // UI guard
    }),

    actions: {
        async checkUnseen() {
            if (this._checkedThisSession) return;
            this._checkedThisSession = true;

            this.loading = true;
            try {
                const res = await axios.get<{latest: ReleaseNote, mark_seen_ids: Array<number>}>("/releases/release-notes/unseen");

                if (!res.data) return

                this.current = res.data.latest;
                this.unseen_ids = res.data.mark_seen_ids
                this.show = true;
                
                await axios.post(`/releases/release-notes/bulk-seen`, {
                    ids: res.data.mark_seen_ids
                });
            } catch (err: any) {
                const status = err?.response?.status;
                if (status === 204) {
                    this.current = null;
                    this.show = false;
                    return;
                }
                console.error("checkUnseen failed:", err);
            } finally {
                this.loading = false;
            }
        },

        async acknowledge() {
            if (!this.current) return;

            await axios.post(`/releases/release-notes/${this.current.id}/ack`);

            this.show = false;
            this.current = null;
        },

        async closeIfAllowed() {
            if (this.current && !this.current.requires_ack) {
                this.show = false;
                await sleep(1000)
                this.current = null;
            }
        },
    },
});

