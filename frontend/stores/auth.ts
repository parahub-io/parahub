import { defineStore } from 'pinia'
import { useNuxtApp } from '#app'
import { syncPreferencesFromProfile } from '~/composables/usePreferencesSync'

export interface User {
  id: string
  email: string
  first_name?: string
  last_name?: string
  username?: string
  profile?: any
  is_staff?: boolean  // Admin flag from backend
}

export interface ProfileDetail {
  id: string
  hna: string
  display_name: string
  profile_type: 'PERSONAL' | 'PSEUDONYMOUS'
  is_primary: boolean
  reputation_score: number
  is_verified_wot: boolean
  is_foundation_member: boolean
  can_manage: boolean
}

export const useAuthStore = defineStore('auth', {
  state: () => ({
    user: null as User | null,
    token: null as string | null,
    refreshToken: null as string | null,  // For JWT blacklist on logout
    loading: false,
    error: null as string | null,
    // Multiple profiles support
    activeProfile: null as ProfileDetail | null,
    manageableProfiles: [] as ProfileDetail[],
    profilesLoading: false,
    // Token fetching promise cache to prevent multiple simultaneous requests
    tokenFetchPromise: null as Promise<void> | null,
    // Session check promise cache to prevent duplicate concurrent checks
    sessionCheckPromise: null as Promise<boolean> | null,
    // New OAuth user needs to confirm username
    needsUsernameConfirmation: false,
  }),

  getters: {
    isAuthenticated: (state) => !!state.user,
    accessToken: (state) => state.token,
    profile: (state) => state.user?.profile || null,
    fullName: (state) => {
      if (!state.user) return ''
      if (state.user.profile?.display_name) return state.user.profile.display_name
      return `${state.user.first_name || ''} ${state.user.last_name || ''}`.trim() || state.user.email
    }
  },

  actions: {
    async login(email: string, password: string) {
      this.loading = true
      this.error = null
      
      try {
        // Call Django login endpoint
        const response: any = await $fetch('/api/v1/auth/token/', {
          method: 'POST',
          body: {
            username: email,
            password: password
          },
          credentials: 'include'
        })
        
        // Keep tokens in memory only - NEVER persist to localStorage
        this.token = response?.access_token ?? null
        this.refreshToken = response?.refresh_token ?? null

        // Fetch user details
        await this.fetchUser()
      } catch (error: any) {
        // Store error code for translation in UI
        this.error = error.data?.detail || error.message || 'auth.error.login'
        throw error
      } finally {
        this.loading = false
      }
    },

    async checkAuthStatus(): Promise<boolean> {
      // Check if user is authenticated via session cookie
      try {
        const sessionData: any = await $fetch('/api/v1/auth/session/', {
          credentials: 'include',
          headers: {
            'Accept': 'application/json',
          }
        })

        if (sessionData?.authenticated && sessionData.user) {
          this.user = sessionData.user
          this.needsUsernameConfirmation = sessionData.needs_username_confirmation || false
          return true
        }
      } catch (error) {
        // Silent: session check failed
      }

      this.user = null
      this.needsUsernameConfirmation = false
      return false
    },

    async fetchUser() {
      try {
        // Get user info using session cookie and/or memory token
        const user = await $fetch('/api/v1/profiles/me/', {
          credentials: 'include',
          headers: this.token ? {
            'Authorization': `Bearer ${this.token}`
          } : {}
        })

        // Transform profile response to user format
        this.user = {
          id: user.id,
          email: user.hna,
          username: user.local_name,
          first_name: user.display_name?.split(' ')[0] || '',
          last_name: user.display_name?.split(' ').slice(1).join(' ') || '',
          profile: user,
          is_staff: user.is_staff || false  // Admin flag for UI features
        } as User

        // Sync server preferences → localStorage
        syncPreferencesFromProfile(user)

        // Set active profile from /me/ response (backend returns current active profile from session)
        // This ensures activeProfile is synced with backend session after page reload
        if (!this.activeProfile || this.activeProfile.id !== user.id) {
          this.activeProfile = {
            id: user.id,
            hna: user.hna,
            display_name: user.display_name,
            profile_type: user.profile_type,
            is_primary: user.is_primary,
            reputation_score: user.reputation_score || 0,
            is_verified_wot: user.is_verified_wot || false,
            is_foundation_member: user.is_foundation_member || false,
            can_manage: true
          } as ProfileDetail
        }
      } catch (error) {
        // If fails, clear user data
        this.user = null
        throw error
      }
    },


    async logout() {
      try {
        // Call Django logout endpoint with refresh token for blacklisting
        await $fetch('/api/v1/auth/logout/', {
          method: 'POST',
          credentials: 'include',
          body: {
            refresh_token: this.refreshToken
          }
        })
      } catch (error) {
        console.error('Logout error:', error)
      }

      // Clear memory-only state
      this.user = null
      this.token = null
      this.refreshToken = null
      this.error = null
      this.activeProfile = null
      this.manageableProfiles = []

      // Disconnect Breez SDK if active
      if (process.client) {
        try {
          const { useLightning } = await import('~/composables/useLightning')
          const { disconnect } = useLightning()
          await disconnect()
        } catch {
          // SDK not loaded or already disconnected
        }
      }

      // Clear all sensitive cryptographic data from localStorage
      if (process.client) {
        // PGP keys
        localStorage.removeItem('parahub_pgp_keys')
        // Seed phrase
        localStorage.removeItem('parahub_seed')
        localStorage.removeItem('parahub_seed_version')
        localStorage.removeItem('parahub_encrypted_seed')  // legacy
        // Bitcoin wallet (legacy)
        localStorage.removeItem('parahub_btc_address_index')
        localStorage.removeItem('parahub_btc_known_addresses')
      }

      // Navigation is the caller's responsibility — store should not navigate
    },

    // Ensure we have a valid in-memory JWT (client-side only)
    async ensureToken() {
      if (process.server) return

      // If there's already a token fetch in progress, wait for it
      if (this.tokenFetchPromise) {
        await this.tokenFetchPromise
        return
      }

      // If we have a token, check if it might be expired and try to refresh
      if (this.token) {
        try {
          // Try to decode token to check expiry (simple check without full validation)
          const tokenParts = this.token.split('.')
          if (tokenParts.length === 3) {
            const payload = JSON.parse(atob(tokenParts[1]))
            const expiry = payload.exp * 1000 // Convert to milliseconds
            const now = Date.now()

            // If token expires in less than 1 minute, refresh it
            if (expiry - now < 60000) {
              if (this.refreshToken) {
                this.tokenFetchPromise = (async () => {
                  try {
                    const tokenData: any = await $fetch('/api/v1/auth/refresh/', {
                      method: 'POST',
                      body: { refresh_token: this.refreshToken }
                    })
                    this.token = tokenData?.access_token || null
                    this.refreshToken = tokenData?.refresh_token || null
                  } catch {
                    // Refresh failed, try to get new token from session
                    const sessionData: any = await $fetch('/api/v1/auth/session/token/', {
                      credentials: 'include'
                    })
                    this.token = sessionData?.access_token || null
                    this.refreshToken = sessionData?.refresh_token || null
                  } finally {
                    this.tokenFetchPromise = null
                  }
                })()
                await this.tokenFetchPromise
                return
              }
            } else {
              // Token is still valid
              return
            }
          }
        } catch {
          // Token parsing failed, try to get from session
        }
      }

      // Try to get token from session
      this.tokenFetchPromise = (async () => {
        try {
          const tokenData: any = await $fetch('/api/v1/auth/session/token/', {
            credentials: 'include'
          })
          this.token = tokenData?.access_token || null
          this.refreshToken = tokenData?.refresh_token || null
        } catch {
          // If session doesn't support JWT or user not authenticated, leave tokens null
          this.token = null
          this.refreshToken = null
        } finally {
          this.tokenFetchPromise = null
        }
      })()
      await this.tokenFetchPromise
    },

    // New session-based reconciliation for client-side auth checks
    // Uses promise cache to prevent duplicate concurrent session checks
    // (init.client.ts and page onMounted both call this)
    async ensureSession(): Promise<boolean> {
      if (this.user) return true

      // If there's already a session check in progress, wait for it
      if (this.sessionCheckPromise) {
        return this.sessionCheckPromise
      }

      this.sessionCheckPromise = (async () => {
        try {
          return await this.checkAuthStatus()
        } finally {
          this.sessionCheckPromise = null
        }
      })()
      return this.sessionCheckPromise
    },

    // Set tokens directly (used for quick signup auto-login)
    setToken(accessToken: string, refreshToken: string) {
      this.token = accessToken
      this.refreshToken = refreshToken
    },

    // Load user data after setting tokens
    async loadUser() {
      try {
        await this.fetchUser()
      } catch (error) {
        console.error('Failed to load user:', error)
        throw error
      }
    },

    // ===== Multiple Profiles Support =====

    async fetchManageableProfiles() {
      /**
       * Fetch all profiles the current user can manage
       * (personal, organization, pseudonymous)
       */
      // Early return if user not authenticated
      if (!this.user || !this.isAuthenticated) {
        this.manageableProfiles = []
        return []
      }

      this.profilesLoading = true
      try {
        await this.ensureToken()

        // If no token after ensuring, user is not authenticated - return empty
        if (!this.token) {
          this.manageableProfiles = []
          return []
        }

        const profiles = await $fetch<ProfileDetail[]>('/api/v1/profiles/manageable/', {
          credentials: 'include',
          headers: {
            'Authorization': `Bearer ${this.token}`
          }
        })

        this.manageableProfiles = profiles

        // Update active profile with fresh data from API
        if (profiles.length > 0) {
          if (this.activeProfile) {
            // If active profile already set, update it with fresh data
            const updatedProfile = profiles.find(p => p.id === this.activeProfile?.id)
            if (updatedProfile) {
              this.activeProfile = updatedProfile
            }
          } else {
            // Set active profile to current profile if not set
            const currentProfile = this.user?.profile
            if (currentProfile) {
              const match = profiles.find(p => p.id === currentProfile.id)
              this.activeProfile = match || profiles[0]
            } else {
              this.activeProfile = profiles[0]
            }
          }
        }

        return profiles
      } catch (error) {
        // Silent fail for auth errors - user simply not authenticated
        this.manageableProfiles = []
        return []
      } finally {
        this.profilesLoading = false
      }
    },

    async switchProfile(profileId: string) {
      /**
       * Switch to a different profile
       * Updates session on backend and refreshes local state
       */
      try {
        await this.ensureToken()

        const newProfile = await $fetch<ProfileDetail>(`/api/v1/profiles/switch/${profileId}/`, {
          method: 'POST',
          credentials: 'include',
          headers: this.token ? {
            'Authorization': `Bearer ${this.token}`
          } : {}
        })

        this.activeProfile = newProfile

        // Refresh user data to sync with new profile
        await this.fetchUser()

        return newProfile
      } catch (error) {
        console.error('Failed to switch profile:', error)
        throw error
      }
    },

    async createProfile(data: {
      local_name: string
      display_name: string
    }) {
      /**
       * Create a new organization or pseudonymous profile
       * Requires WoT verification (3+ verifications)
       */
      try {
        await this.ensureToken()

        const newProfile = await $fetch<ProfileDetail>('/api/v1/profiles/create/', {
          method: 'POST',
          credentials: 'include',
          headers: this.token ? {
            'Authorization': `Bearer ${this.token}`
          } : {},
          body: data
        })

        // Refresh manageable profiles list
        await this.fetchManageableProfiles()

        // Set active profile to newly created profile (backend already switched session)
        this.activeProfile = newProfile

        return newProfile
      } catch (error) {
        console.error('Failed to create profile:', error)
        throw error
      }
    },

    async deleteProfile(profileId: string) {
      /**
       * Delete a profile (only non-primary profiles)
       */
      try {
        await this.ensureToken()

        await $fetch(`/api/v1/profiles/${profileId}/`, {
          method: 'DELETE',
          credentials: 'include',
          headers: this.token ? {
            'Authorization': `Bearer ${this.token}`
          } : {}
        })

        // Refresh manageable profiles list
        await this.fetchManageableProfiles()

        // If deleted profile was active, switch to primary
        if (this.activeProfile?.id === profileId) {
          const primaryProfile = this.manageableProfiles.find(p => p.is_primary)
          if (primaryProfile) {
            await this.switchProfile(primaryProfile.id)
          }
        }
      } catch (error) {
        console.error('Failed to delete profile:', error)
        throw error
      }
    },

    getProfileTypeLabel(type: string): string {
      // SSR-safe: Check if i18n is available before using it
      try {
        const nuxtApp = useNuxtApp()
        if (nuxtApp?.$i18n?.t) {
          const labels: Record<string, string> = {
            'PERSONAL': nuxtApp.$i18n.t('profiles.personal'),
            'PSEUDONYMOUS': nuxtApp.$i18n.t('profiles.pseudonymous')
          }
          return labels[type] || type
        }
      } catch (e) {
        // SSR fallback - return English labels
      }

      // Fallback labels when i18n is not available (SSR)
      const fallbackLabels: Record<string, string> = {
        'PERSONAL': 'Personal',
        'PSEUDONYMOUS': 'Pseudonymous'
      }
      return fallbackLabels[type] || type
    },

    canCreateAdditionalProfiles(): boolean {
      /**
       * Check if current user can create additional profiles
       * Requires WoT verification and max 6 additional profiles (7 total)
       */
      if (!this.user?.profile?.is_verified_wot && !this.user?.profile?.is_foundation_member) {
        return false
      }

      // Check if already at max profiles (7 total = 1 primary + 6 additional)
      if (this.manageableProfiles.length >= 7) {
        return false
      }

      return true
    }
  }
})