import { ref } from 'vue'
import { useAuthStore } from '~/stores/auth'

interface HubBrief {
  id: string
  name: string
  slug: string
  lat: number | null
  lon: number | null
  hub_instructions: string
}

interface ProfileBrief {
  id: string
  display_name: string
  hna: string | null
}

export interface Shipment {
  id: string
  object_type: string
  title: string
  tracking_code: string
  status: string
  size_category: string
  sender: ProfileBrief
  receiver: ProfileBrief
  origin_hub: HubBrief
  destination_hub: HubBrief
  current_hub: HubBrief | null
  item_id: string | null
  storage_fee_total: number
  delivery_fee: number
  expires_at: string | null
  delivered_at: string | null
  created_at: string
  pickup_code?: string
  role?: string
  events?: ShipmentEvent[]
  carrier_offers?: CarrierOffer[]
}

export interface ShipmentEvent {
  id: string
  event_type: string
  hub: HubBrief | null
  actor: ProfileBrief
  note: string
  created_at: string
}

export interface CarrierOffer {
  id: string
  carrier: ProfileBrief
  from_hub: HubBrief
  to_hub: HubBrief
  fee_sats: number
  status: string
  matrix_room_id: string | null
  created_at: string
}

export interface Hub {
  id: string
  name: string
  slug: string
  lat: number | null
  lon: number | null
  hub_capacity: number | null
  hub_max_days: number
  hub_storage_fee_daily: number
  hub_accepted_sizes: string[]
  hub_instructions: string
  opening_hours: Record<string, string>
  phone: string
  spark_address: string
  rating_avg: number
  distance_m: number | null
}

function authHeaders() {
  const authStore = useAuthStore()
  return {
    credentials: 'include' as RequestCredentials,
    headers: { Authorization: `Bearer ${authStore.token}` },
  }
}

export function useShipments() {
  const loading = ref(false)
  const error = ref<string | null>(null)

  async function fetchMyShipments(): Promise<{ items: Shipment[]; count: number }> {
    const authStore = useAuthStore()
    await authStore.ensureToken()
    return await $fetch('/api/v1/shipments/', authHeaders())
  }

  async function fetchShipment(trackingCode: string): Promise<Shipment> {
    const authStore = useAuthStore()
    await authStore.ensureToken()
    return await $fetch(`/api/v1/shipments/${trackingCode}/`, authHeaders())
  }

  async function createShipment(data: {
    title: string
    size_category: string
    receiver_id: string
    origin_hub_id: string
    destination_hub_id: string
    item_id?: string
    delivery_fee?: number
  }): Promise<Shipment> {
    const authStore = useAuthStore()
    await authStore.ensureToken()
    return await $fetch('/api/v1/shipments/', {
      method: 'POST',
      body: data,
      ...authHeaders(),
    })
  }

  async function depositShipment(id: string): Promise<Shipment> {
    const authStore = useAuthStore()
    await authStore.ensureToken()
    return await $fetch(`/api/v1/shipments/${id}/deposit/`, {
      method: 'PATCH',
      ...authHeaders(),
    })
  }

  async function cancelShipment(id: string): Promise<Shipment> {
    const authStore = useAuthStore()
    await authStore.ensureToken()
    return await $fetch(`/api/v1/shipments/${id}/cancel/`, {
      method: 'PATCH',
      ...authHeaders(),
    })
  }

  async function fetchAvailableShipments(): Promise<{ items: Shipment[]; count: number }> {
    const authStore = useAuthStore()
    await authStore.ensureToken()
    return await $fetch('/api/v1/shipments/available/', authHeaders())
  }

  async function createCarrierOffer(shipmentId: string, feeSats: number = 0): Promise<CarrierOffer> {
    const authStore = useAuthStore()
    await authStore.ensureToken()
    return await $fetch(`/api/v1/shipments/${shipmentId}/offer/`, {
      method: 'POST',
      body: { fee_sats: feeSats },
      ...authHeaders(),
    })
  }

  async function acceptCarrierOffer(offerId: string): Promise<CarrierOffer> {
    const authStore = useAuthStore()
    await authStore.ensureToken()
    return await $fetch(`/api/v1/shipments/offers/${offerId}/accept/`, {
      method: 'PATCH',
      ...authHeaders(),
    })
  }

  async function fetchHubs(lat?: number, lon?: number, radiusKm: number = 20): Promise<{ items: Hub[]; count: number }> {
    const params = new URLSearchParams()
    if (lat != null && lon != null) {
      params.set('lat', String(lat))
      params.set('lon', String(lon))
      params.set('radius_km', String(radiusKm))
    }
    const url = `/api/v1/shipments/hubs/?${params}`
    // Hubs discovery works with optional auth
    try {
      const authStore = useAuthStore()
      await authStore.ensureToken()
      return await $fetch(url, authHeaders())
    } catch {
      return await $fetch(url)
    }
  }

  async function updateHubSettings(establishmentId: string, settings: Record<string, any>) {
    const authStore = useAuthStore()
    await authStore.ensureToken()
    return await $fetch(`/api/v1/shipments/hubs/${establishmentId}/settings/`, {
      method: 'PATCH',
      body: settings,
      ...authHeaders(),
    })
  }

  // Hub operator
  async function fetchHubShipments(establishmentId: string): Promise<{ items: Shipment[]; count: number }> {
    const authStore = useAuthStore()
    await authStore.ensureToken()
    return await $fetch(`/api/v1/shipments/hub/${establishmentId}/`, authHeaders())
  }

  async function confirmArrival(establishmentId: string, shipmentId: string): Promise<Shipment> {
    const authStore = useAuthStore()
    await authStore.ensureToken()
    return await $fetch(`/api/v1/shipments/hub/${establishmentId}/${shipmentId}/confirm-arrival/`, {
      method: 'PATCH',
      ...authHeaders(),
    })
  }

  async function markReady(establishmentId: string, shipmentId: string): Promise<Shipment> {
    const authStore = useAuthStore()
    await authStore.ensureToken()
    return await $fetch(`/api/v1/shipments/hub/${establishmentId}/${shipmentId}/mark-ready/`, {
      method: 'PATCH',
      ...authHeaders(),
    })
  }

  async function verifyPickup(establishmentId: string, shipmentId: string, pickupCode: string): Promise<Shipment> {
    const authStore = useAuthStore()
    await authStore.ensureToken()
    return await $fetch(`/api/v1/shipments/hub/${establishmentId}/${shipmentId}/verify-pickup/`, {
      method: 'PATCH',
      body: { pickup_code: pickupCode },
      ...authHeaders(),
    })
  }

  return {
    loading,
    error,
    fetchMyShipments,
    fetchAvailableShipments,
    fetchShipment,
    createShipment,
    depositShipment,
    cancelShipment,
    createCarrierOffer,
    acceptCarrierOffer,
    fetchHubs,
    updateHubSettings,
    fetchHubShipments,
    confirmArrival,
    markReady,
    verifyPickup,
  }
}
