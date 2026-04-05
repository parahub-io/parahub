<template>
  <Teleport to="body">
    <div
      v-show="incomingCall"
      class="fixed top-0 left-0 right-0 z-[100] bg-gradient-to-r from-primary-600 to-primary-500 text-black shadow-2xl transition-all duration-300"
      :class="incomingCall ? 'translate-y-0 opacity-100' : 'translate-y-[-100%] opacity-0'"
    >
        <div class="max-w-7xl mx-auto px-4 py-4 flex items-center justify-between gap-4">
          <!-- Caller info -->
          <div class="flex items-center gap-4 min-w-0">
            <!-- Pulsing phone icon -->
            <div class="relative">
              <div class="absolute inset-0 bg-white/30 rounded-full animate-ping"></div>
              <div class="relative bg-white/20 p-3 rounded-full">
                <Phone class="w-6 h-6 text-black animate-pulse" />
              </div>
            </div>

            <!-- Caller details -->
            <div class="min-w-0">
              <p class="text-sm font-medium opacity-80">{{ t('call.incoming_call') }}</p>
              <p class="text-lg font-bold truncate">
                {{ callerDisplayName }}
              </p>
            </div>
          </div>

          <!-- Actions -->
          <div class="flex items-center gap-3 flex-shrink-0">
            <!-- Decline button -->
            <button
              @click="declineCall"
              class="btn-error p-3 rounded-full shadow-lg"
              :aria-label="t('call.decline')"
            >
              <PhoneOff class="w-6 h-6" />
            </button>

            <!-- Answer button -->
            <button
              @click="answerCall"
              class="btn-success p-3 rounded-full shadow-lg animate-bounce"
              :aria-label="t('call.answer')"
            >
              <PhoneCall class="w-6 h-6" />
            </button>
          </div>
        </div>
      </div>
  </Teleport>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { storeToRefs } from 'pinia'
import { Phone, PhoneCall, PhoneOff } from 'lucide-vue-next'
import { useCallStore } from '~/stores/call'

const { t } = useI18n()
const router = useRouter()
const localePath = useLocalePath()
const callStore = useCallStore()
const { incomingCall } = storeToRefs(callStore)

const callerDisplayName = computed(() => {
  if (!incomingCall.value) return ''
  const caller = incomingCall.value.caller
  return caller.display_name || caller.local_name || 'Unknown'
})

function answerCall() {
  const roomName = callStore.answerCall()
  if (roomName) {
    router.push(localePath(`/call?room=${encodeURIComponent(roomName)}`))
  }
}

function declineCall() {
  callStore.declineCall()
}
</script>
