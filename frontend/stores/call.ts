import { defineStore } from 'pinia'

export interface IncomingCall {
  caller: {
    id: string
    display_name: string
    local_name?: string
    avatar_url?: string | null
  }
  room_name: string
  receivedAt: number
}

interface CallState {
  incomingCall: IncomingCall | null
}

export const useCallStore = defineStore('call', {
  state: (): CallState => ({
    incomingCall: null
  }),

  actions: {
    setIncomingCall(call: Omit<IncomingCall, 'receivedAt'>) {
      this.incomingCall = {
        ...call,
        receivedAt: Date.now()
      }
    },

    clearIncomingCall() {
      this.incomingCall = null
    },

    // Answer the call - navigate to call page
    answerCall() {
      if (!this.incomingCall) return null
      const roomName = this.incomingCall.room_name
      this.incomingCall = null
      return roomName
    },

    // Decline the call - just clear the notification
    declineCall() {
      this.incomingCall = null
    }
  }
})
