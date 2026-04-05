/**
 * OpenSky Aerial Imagery System composable
 *
 * Provides functions for:
 * - Fetching system stats
 * - Listing missions (public + personal)
 * - Uploading drone photos
 * - Deleting missions
 */

export type MeshStatus = 'NONE' | 'MESH_QUEUED' | 'MESH_PROCESSING' | 'MESH_READY' | 'MESH_FAILED'

export interface OpenSkyMission {
  id: string
  object_type: 'opensky_mission'
  name: string
  status: 'UPLOADING' | 'QUEUED' | 'PROCESSING' | 'PUBLISHED' | 'FAILED'
  pilot_id: string | null
  pilot_name: string | null
  area?: GeoJSON.Polygon | null
  center_lat: number | null
  center_lng: number | null
  source_photos_count: number
  tiles_count: number
  tiles_size_mb?: number
  min_zoom?: number
  max_zoom?: number
  uploaded_at: string
  published_at: string | null
  processing_started_at: string | null
  processing_step: '' | 'odm' | 'reprojection' | 'alignment' | 'tiling' | 'finalizing'
  error_message?: string | null
  mesh_status?: MeshStatus
  mesh_size_mb?: number
  mesh_glb_size_mb?: number
  mesh_error_message?: string | null
  mesh_requested_at?: string | null
  mesh_completed_at?: string | null
  tile_z?: number | null
  tile_x?: number | null
  tile_y?: number | null
}

export interface OpenSkyStats {
  total_missions: number
  published_missions: number
  processing_missions: number
  queued_missions: number
  failed_missions: number
  total_pilots: number
  total_coverage_km2: number
  total_tiles: number
  total_size_gb: number
}

export interface OpenSkyMissionBounds {
  id: string
  bounds: [number, number, number, number]  // [minLng, minLat, maxLng, maxLat]
  minzoom: number
  maxzoom: number
}

export const useOpenSky = () => {
  const authStore = useAuthStore()

  const stats = ref<OpenSkyStats | null>(null)
  const missions = ref<OpenSkyMission[]>([])
  const myMissions = ref<OpenSkyMission[]>([])
  const publishedBounds = ref<OpenSkyMissionBounds[]>([])
  const loading = ref(false)
  const uploading = ref(false)
  const uploadProgress = ref(0)

  // Multi-file upload state
  const multiUploadState = ref<{
    currentBatch: number
    totalBatches: number
    currentFile: number
    totalFiles: number
    currentFileName: string
  } | null>(null)

  // Batch settings
  const BATCH_SIZE_MB = 500  // Max MB per batch
  const BATCH_SIZE_FILES = 50  // Max files per batch

  /**
   * Fetch OpenSky system statistics
   */
  const fetchStats = async () => {
    try {
      const data = await $fetch<OpenSkyStats>('/api/v1/geo/opensky/stats/')
      stats.value = data
      return data
    } catch (error) {
      console.error('Failed to fetch OpenSky stats:', error)
      throw error
    }
  }

  /**
   * Fetch list of missions with optional filters
   */
  const fetchMissions = async (filters?: {
    status?: string
    pilot_id?: string
    year?: number
    page?: number
  }) => {
    loading.value = true
    try {
      const params = new URLSearchParams()
      if (filters?.status) params.set('status', filters.status)
      if (filters?.pilot_id) params.set('pilot_id', filters.pilot_id)
      if (filters?.year) params.set('year', filters.year.toString())
      if (filters?.page) params.set('page', filters.page.toString())

      const queryString = params.toString()
      const url = `/api/v1/geo/opensky/missions/${queryString ? '?' + queryString : ''}`

      const data = await $fetch<{ items: OpenSkyMission[], count: number }>(url)
      missions.value = data.items
      return data
    } catch (error) {
      console.error('Failed to fetch OpenSky missions:', error)
      throw error
    } finally {
      loading.value = false
    }
  }

  /**
   * Fetch current user's missions (all statuses)
   */
  const fetchMyMissions = async () => {
    await authStore.ensureToken()
    loading.value = true
    try {
      const data = await $fetch<OpenSkyMission[]>('/api/v1/geo/opensky/missions/me/', {
        credentials: 'include',
        headers: { 'Authorization': `Bearer ${authStore.token}` }
      })
      myMissions.value = data
      return data
    } catch (error) {
      console.error('Failed to fetch my OpenSky missions:', error)
      throw error
    } finally {
      loading.value = false
    }
  }

  /**
   * Fetch single mission details
   */
  const fetchMission = async (missionId: string) => {
    try {
      return await $fetch<OpenSkyMission>(`/api/v1/geo/opensky/missions/${missionId}/`)
    } catch (error) {
      console.error('Failed to fetch OpenSky mission:', error)
      throw error
    }
  }

  /**
   * Fetch published mission bounds for map layer
   */
  const fetchPublishedBounds = async () => {
    try {
      const data = await $fetch<{ missions: OpenSkyMissionBounds[] }>('/api/v1/geo/opensky/published-bounds/')
      publishedBounds.value = data.missions
      return data.missions
    } catch (error) {
      console.error('Failed to fetch OpenSky published bounds:', error)
      throw error
    }
  }

  /**
   * Upload ZIP archive with drone photos
   */
  const uploadMission = async (file: File, name?: string, satelliteAlign?: boolean): Promise<OpenSkyMission> => {
    await authStore.ensureToken()
    uploading.value = true
    uploadProgress.value = 0

    try {
      const formData = new FormData()
      formData.append('file', file)
      if (name) formData.append('name', name)
      if (satelliteAlign) formData.append('satellite_align', 'true')

      // Use XMLHttpRequest for progress tracking
      return new Promise((resolve, reject) => {
        const xhr = new XMLHttpRequest()

        xhr.upload.onprogress = (event) => {
          if (event.lengthComputable) {
            uploadProgress.value = Math.round((event.loaded / event.total) * 100)
          }
        }

        xhr.onload = () => {
          if (xhr.status >= 200 && xhr.status < 300) {
            const response = JSON.parse(xhr.responseText)
            // Refresh my missions
            fetchMyMissions()
            resolve(response)
          } else {
            let errorMessage = 'Upload failed'
            try {
              const error = JSON.parse(xhr.responseText)
              errorMessage = error.detail || error.message || errorMessage
            } catch {}
            reject(new Error(errorMessage))
          }
        }

        xhr.onerror = () => {
          reject(new Error('Network error during upload'))
        }

        xhr.open('POST', '/api/v1/geo/opensky/upload/')
        xhr.setRequestHeader('Authorization', `Bearer ${authStore.token}`)
        xhr.withCredentials = true
        xhr.send(formData)
      })
    } finally {
      uploading.value = false
      uploadProgress.value = 0
    }
  }

  /**
   * Split files into batches based on size and count limits
   */
  const createBatches = (files: File[]): File[][] => {
    const batches: File[][] = []
    let currentBatch: File[] = []
    let currentBatchSize = 0

    for (const file of files) {
      // Start new batch if limits exceeded
      if (currentBatch.length >= BATCH_SIZE_FILES ||
          (currentBatchSize + file.size) > BATCH_SIZE_MB * 1024 * 1024) {
        if (currentBatch.length > 0) {
          batches.push(currentBatch)
          currentBatch = []
          currentBatchSize = 0
        }
      }
      currentBatch.push(file)
      currentBatchSize += file.size
    }

    if (currentBatch.length > 0) {
      batches.push(currentBatch)
    }

    return batches
  }

  /**
   * Upload multiple files as a single mission (supports ZIP or JPG)
   * JPG files are automatically batched to stay under size limits
   */
  const uploadMultipleFiles = async (files: File[], name?: string, satelliteAlign?: boolean, existingMissionId?: string): Promise<OpenSkyMission> => {
    await authStore.ensureToken()
    uploading.value = true
    uploadProgress.value = 0

    let missionId: string | null = existingMissionId || null
    let lastMission: OpenSkyMission | null = null

    // Check if all files are JPG (direct upload) or ZIP
    const allJpg = files.every(f => f.name.toLowerCase().match(/\.jpe?g$/))
    const allZip = files.every(f => f.name.toLowerCase().endsWith('.zip'))

    // For JPG files, create batches; for ZIP, each file is a batch
    const batches = allJpg ? createBatches(files) : files.map(f => [f])
    const totalFiles = files.length

    multiUploadState.value = {
      currentBatch: 0,
      totalBatches: batches.length,
      currentFile: 0,
      totalFiles,
      currentFileName: ''
    }

    let filesProcessed = 0

    try {
      for (let batchIdx = 0; batchIdx < batches.length; batchIdx++) {
        const batch = batches[batchIdx]

        multiUploadState.value = {
          currentBatch: batchIdx + 1,
          totalBatches: batches.length,
          currentFile: filesProcessed + 1,
          totalFiles,
          currentFileName: batch.length === 1 ? batch[0].name : `${batch.length} files`
        }

        const formData = new FormData()

        if (allJpg) {
          // Direct JPG upload - use 'files' field for multiple
          for (const file of batch) {
            formData.append('files', file)
          }
        } else {
          // ZIP upload - use 'file' field
          formData.append('file', batch[0])
        }

        if (batchIdx === 0 && !existingMissionId) {
          if (name) formData.append('name', name)
          if (satelliteAlign) formData.append('satellite_align', 'true')
          formData.append('multi_file', 'true')
        } else {
          formData.append('mission_id', existingMissionId || missionId!)
        }

        // Upload batch with progress tracking
        lastMission = await new Promise<OpenSkyMission>((resolve, reject) => {
          const xhr = new XMLHttpRequest()

          xhr.upload.onprogress = (event) => {
            if (event.lengthComputable) {
              const completedProgress = (filesProcessed / totalFiles) * 100
              const batchFiles = batch.length
              const batchProgress = (event.loaded / event.total) * (batchFiles / totalFiles) * 100
              uploadProgress.value = Math.round(completedProgress + batchProgress)
            }
          }

          xhr.onload = () => {
            if (xhr.status >= 200 && xhr.status < 300) {
              const response = JSON.parse(xhr.responseText)
              if (batchIdx === 0) {
                missionId = response.id
              }
              resolve(response)
            } else {
              let errorMessage = 'Upload failed'
              try {
                const error = JSON.parse(xhr.responseText)
                errorMessage = error.detail || error.message || errorMessage
              } catch {}
              reject(new Error(`Batch ${batchIdx + 1}/${batches.length}: ${errorMessage}`))
            }
          }

          xhr.onerror = () => {
            reject(new Error(`Network error uploading batch ${batchIdx + 1}/${batches.length}`))
          }

          xhr.open('POST', '/api/v1/geo/opensky/upload/')
          xhr.setRequestHeader('Authorization', `Bearer ${authStore.token}`)
          xhr.withCredentials = true
          xhr.send(formData)
        })

        filesProcessed += batch.length
      }

      // All batches uploaded, finalize the mission
      if (missionId) {
        lastMission = await finalizeMission(missionId)
      }

      fetchMyMissions()
      return lastMission!
    } finally {
      uploading.value = false
      uploadProgress.value = 0
      multiUploadState.value = null
    }
  }

  /**
   * Finalize a multi-file upload mission (UPLOADING → QUEUED)
   */
  const finalizeMission = async (missionId: string): Promise<OpenSkyMission> => {
    await authStore.ensureToken()
    try {
      return await $fetch<OpenSkyMission>(`/api/v1/geo/opensky/missions/${missionId}/finalize/`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Authorization': `Bearer ${authStore.token}` }
      })
    } catch (error) {
      console.error('Failed to finalize OpenSky mission:', error)
      throw error
    }
  }

  /**
   * Delete a mission
   */
  const deleteMission = async (missionId: string) => {
    await authStore.ensureToken()
    try {
      await $fetch(`/api/v1/geo/opensky/missions/${missionId}/`, {
        method: 'DELETE',
        credentials: 'include',
        headers: { 'Authorization': `Bearer ${authStore.token}` }
      })
      // Remove from local state
      myMissions.value = myMissions.value.filter(m => m.id !== missionId)
      missions.value = missions.value.filter(m => m.id !== missionId)
    } catch (error) {
      console.error('Failed to delete OpenSky mission:', error)
      throw error
    }
  }

  /**
   * Get status badge color
   */
  const getStatusColor = (status: string) => {
    switch (status) {
      case 'PUBLISHED': return 'green'
      case 'PROCESSING': return 'yellow'
      case 'QUEUED': return 'blue'
      case 'UPLOADING': return 'purple'
      case 'FAILED': return 'red'
      default: return 'gray'
    }
  }

  /**
   * Get status display text
   */
  const getStatusText = (status: string) => {
    switch (status) {
      case 'PUBLISHED': return 'Published'
      case 'PROCESSING': return 'Processing'
      case 'QUEUED': return 'Queued'
      case 'UPLOADING': return 'Uploading'
      case 'FAILED': return 'Failed'
      default: return status
    }
  }

  /**
   * Format file size for display
   */
  const formatSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    if (bytes < 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`
    return `${(bytes / 1024 / 1024 / 1024).toFixed(2)} GB`
  }

  const checkSatelliteAlign = async (missionId: string) => {
    await authStore.ensureToken()
    return await $fetch<{ offset: number; dx: number; dy: number; needs_correction: boolean }>(
      `/api/v1/geo/opensky/missions/${missionId}/satellite-align/?action=check`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Authorization': `Bearer ${authStore.token}` }
      })
  }

  const applySatelliteAlign = async (missionId: string) => {
    await authStore.ensureToken()
    return await $fetch<{ success: boolean; message: string }>(
      `/api/v1/geo/opensky/missions/${missionId}/satellite-align/?action=apply`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Authorization': `Bearer ${authStore.token}` }
      })
  }

  /**
   * Download mesh ZIP archive
   */
  const downloadMesh = async (missionId: string) => {
    await authStore.ensureToken()
    try {
      const response = await fetch(`/api/v1/geo/opensky/missions/${missionId}/mesh/download/`, {
        credentials: 'include',
        headers: { 'Authorization': `Bearer ${authStore.token}` }
      })
      if (!response.ok) throw new Error('Download failed')
      const blob = await response.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `mesh_${missionId.slice(0, 8)}.glb`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
    } catch (error) {
      console.error('Failed to download mesh:', error)
      throw error
    }
  }

  /**
   * Get GLB URL for 3D viewer
   */
  const getMeshGlbUrl = (missionId: string) => {
    return `/api/v1/geo/opensky/missions/${missionId}/mesh/model.glb`
  }

  // ---- Real-time WS updates ----

  const _handleMissionUpdate = (data: any) => {
    const idx = myMissions.value.findIndex(m => m.id === data.mission_id)
    if (idx === -1) return

    const mission = myMissions.value[idx]
    if (data.status) mission.status = data.status
    if (data.processing_step !== undefined) mission.processing_step = data.processing_step
    if (data.processing_started_at) mission.processing_started_at = data.processing_started_at
    if (data.published_at) mission.published_at = data.published_at
    if (data.tiles_count !== undefined) mission.tiles_count = data.tiles_count
    if (data.center_lat !== undefined) mission.center_lat = data.center_lat
    if (data.center_lng !== undefined) mission.center_lng = data.center_lng
    if (data.error_message !== undefined) mission.error_message = data.error_message
  }

  const connectRealtimeUpdates = () => {
    const realtimeStore = useRealtimeStore()
    realtimeStore.connect()
    realtimeStore.joinRoom('opensky', 'missions')
    realtimeStore.on('opensky.mission_updated', _handleMissionUpdate)
  }

  const disconnectRealtimeUpdates = () => {
    const realtimeStore = useRealtimeStore()
    realtimeStore.leaveRoom('opensky', 'missions')
    realtimeStore.off('opensky.mission_updated', _handleMissionUpdate)
  }

  return {
    // State
    stats,
    missions,
    myMissions,
    publishedBounds,
    loading,
    uploading,
    uploadProgress,
    multiUploadState,

    // Actions
    fetchStats,
    fetchMissions,
    fetchMyMissions,
    fetchMission,
    fetchPublishedBounds,
    uploadMission,
    uploadMultipleFiles,
    finalizeMission,
    deleteMission,
    downloadMesh,
    getMeshGlbUrl,
    checkSatelliteAlign,
    applySatelliteAlign,
    connectRealtimeUpdates,
    disconnectRealtimeUpdates,

    // Helpers
    getStatusColor,
    getStatusText,
    formatSize
  }
}
