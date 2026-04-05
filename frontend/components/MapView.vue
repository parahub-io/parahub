<template>
  <div
    v-show="!loading"
    class="map-view fullscreen"
    :class="{ 'no-animation': !animationEnabled }"
  >
    <!-- Map Container -->
    <div
      ref="miniMapContainer"
      class="mini-map-container"
    >
      <!-- Maplibre mini-map renders here -->
      <div ref="mapRoot" class="mini-map-root" role="application" :aria-label="$t('map.aria_interactive_map')"></div>
      <!-- Cached screenshot overlay for instant KeepAlive restore -->
      <img class="map-snapshot-overlay" style="display: none" alt="" aria-hidden="true">

      <!-- Back button + browse toggle row (when returnTo) -->
      <div
        v-if="route.query.returnTo && !selectedFeature && activeAvatarPanel === null && !selectedVehicle && !selectedIoTDevice && !selectedCondominium && !selectedEstablishment"
        class="absolute top-[4.5rem] left-4 z-[1001] flex items-center gap-2"
      >
        <button
          v-if="!browseVisible && !routingVisible"
          @click="openBrowsePanel"
          class="p-2.5 bg-white dark:bg-neutral-800 rounded-lg shadow-lg border border-neutral-200 dark:border-neutral-700 hover:shadow-xl transition-all"
          :title="$t('map.browse.toggle_tooltip')"
        >
          <Building2 class="w-5 h-5 text-neutral-700 dark:text-neutral-300" />
        </button>
        <button
          @click.stop="router.push(localePath(route.query.returnTo as string))"
          class="flex items-center gap-2 px-4 py-2.5 bg-white dark:bg-neutral-800 text-neutral-900 dark:text-neutral-100 rounded-lg shadow-lg hover:shadow-xl transition-all border border-neutral-200 dark:border-neutral-700"
        >
          <ArrowLeft class="w-4 h-4" />
          <span class="text-sm font-medium">{{ $t('map.back_to_page') }}</span>
        </button>
      </div>

      <!-- Browse Panel (left sidebar) -->
      <MapBrowsePanel
        v-if="browseVisible"
        :map-instance="mapStore.mapInstance"
        :initial-category-id="browseCategoryId"
        :initial-category-name="browseCategoryName"
        :initial-category-icon="browseCategoryIcon"
        @close="closeBrowsePanel"
        @results="updateBrowseMarkers"
        @select="handleBrowseSelect"
        @category-cleared="handleBrowseCategoryCleared"
      />

      <!-- Routing Panel (left sidebar, same position as browse) -->
      <MapRoutingPanel
        v-if="routingVisible"
        @close="closeRoutingPanel"
        @route-ready="showRouteOnMap"
        @route-cleared="clearRouteFromMap"
      />

      <!-- Unified Search bar with Browse + Directions buttons -->
      <div class="search-with-directions" :class="{ 'panel-open': browseVisible || routingVisible, 'detail-panel-open': !!selectedFeature || activeAvatarPanel !== null || !!selectedVehicle || !!selectedIoTDevice || !!selectedCondominium || !!selectedEstablishment }">
        <button
          v-if="!route.query.returnTo"
          @click="openBrowsePanel"
          class="browse-fab"
          :class="{ active: browseVisible }"
          :title="$t('map.browse.toggle_tooltip')"
        >
          <Building2 class="w-5 h-5" />
        </button>
        <MapUnifiedSearch
          :panel-open="browseVisible || routingVisible || !!selectedFeature || activeAvatarPanel !== null || !!selectedVehicle"
          @category-selected="handleUnifiedCategorySelect"
          @establishment-selected="handleUnifiedEstablishmentSelect"
          @location-selected="onLocationSelected"
          @search-cleared="onSearchCleared"
          :lang="searchLanguage"
        />
        <button
          @click="toggleRoutingPanel"
          class="directions-fab"
          :class="{ active: routingVisible }"
          :title="$t('map.routing.title')"
        >
          <Route class="w-5 h-5" />
        </button>
      </div>

      <!-- Unified Feature Panel (OSM, avatar controls, profile view, vehicle) -->
      <MapFeaturePanel
        ref="featurePanelRef"
        :feature="selectedFeature"
        :all-features="clickedFeatures"
        :click-coordinates="clickCoordinates"
        :content-type="panelContentTypeWithVehicle"
        :avatar-data="panelAvatarData"
        :vehicle-data="selectedVehicle"
        :iot-device-data="selectedIoTDevice"
        :iot-following="iot.isFollowing.value"
        :condominium-data="selectedCondominium"
        :hub-data="selectedHub"
        :establishment-data="selectedEstablishment"
        :show-back-to-browse="browseWasOpen"
        @close="closeFeaturePanel"
        @back="handleFeaturePanelBack"
        @feature-selected="selectedFeature = $event"
        @search-location="handleSearchLocation"
        @establishment-selected="handleEstablishmentSelected"
        @avatar-type-change="handleAvatarTypeChange"
        @show-trail="handleShowTrail"
        @clear-trail="handleClearTrail"
        @trail-cursor="handleTrailCursor"
        @recenter-iot="handleRecenterIoT"
        @osm-resolved="handleOsmResolved"
      />

      <!-- Highlighted item marker with blinking animation -->
      <div
        v-if="mapStore.highlightedItem && mapStore.animationsEnabled"
        class="highlight-marker"
        :style="highlightMarkerStyle"
      >
        <div class="highlight-box"></div>
      </div>

      <!-- Map Presence Overlay (MMORPG-style avatars) -->
      <MapPresenceOverlay
        v-if="authStore.isAuthenticated && mapPresenceEnabled"
        :map="mapStore.mapInstance"
        :avatars="nearbyAvatars"
        :own-profile-id="authStore.activeProfile?.id || null"
        :own-avatar-type="currentAvatarType"
        :own-speech-bubble="currentSpeechBubble"
        :own-avatar-state="currentAvatarState"
        :is-keyboard-moving="keyboard.isKeyboardMoving.value"
        :keyboard-direction="keyboard.keyboardDirection.value"
        @avatar-click="handleAvatarClick"
      />

      <!-- Map Layer Controls -->
      <div class="map-layer-controls" :style="{ top: customControlsTop }">
        <!-- Layers + Tools + IoT (single group) -->
        <div class="map-ctrl-group">
          <!-- Layers button (Aerial + Transit + Condo + Gov + Hubs + Mesh + Energy) -->
          <div class="layers-control">
            <button
              @click.stop="layersPopoverOpen = !layersPopoverOpen; architectPopoverOpen = false; iotPopoverOpen = false; hideIoTPreview()"
              class="opensky-btn"
              :title="$t('map.layers.title')"
            >
              <Layers class="w-5 h-5" />
            </button>
            <div v-if="layersPopoverOpen" class="layers-popover" @click.stop>
              <button
                class="layers-popover-item"
                :class="{ active: openSkyEnabled }"
                :aria-pressed="openSkyEnabled"
                @click="toggleOpenSkyLayer"
              >
                <Satellite class="w-4 h-4 flex-shrink-0" aria-hidden="true" />
                <span class="layers-popover-label">{{ $t('map.layers.aerial') }}</span>
                <Eye v-if="openSkyEnabled" class="w-3.5 h-3.5 flex-shrink-0 opacity-70" aria-hidden="true" />
                <EyeOff v-else class="w-3.5 h-3.5 flex-shrink-0 opacity-30" aria-hidden="true" />
              </button>
              <button
                class="layers-popover-item"
                :class="{ active: tiles3dEnabled }"
                :aria-pressed="tiles3dEnabled"
                @click="toggle3DTiles"
              >
                <Box class="w-4 h-4 flex-shrink-0" aria-hidden="true" />
                <span class="layers-popover-label">{{ $t('map.layers.aerial_3d') }}</span>
                <Eye v-if="tiles3dEnabled" class="w-3.5 h-3.5 flex-shrink-0 opacity-70" aria-hidden="true" />
                <EyeOff v-else class="w-3.5 h-3.5 flex-shrink-0 opacity-30" aria-hidden="true" />
              </button>
              <button
                class="layers-popover-item"
                :class="{ active: transitEnabled }"
                :aria-pressed="transitEnabled"
                @click="toggleTransitLayer"
              >
                <Bus class="w-4 h-4 flex-shrink-0" aria-hidden="true" />
                <span class="layers-popover-label">{{ $t('map.layers.transit') }}</span>
                <span v-if="transit.activeRouteFilter.value" class="w-2 h-2 bg-secondary-600 rounded-full flex-shrink-0" aria-hidden="true"></span>
                <Eye v-if="transitEnabled" class="w-3.5 h-3.5 flex-shrink-0 opacity-70" aria-hidden="true" />
                <EyeOff v-else class="w-3.5 h-3.5 flex-shrink-0 opacity-30" aria-hidden="true" />
              </button>
              <button
                class="layers-popover-item"
                :class="{ active: governmentEnabled }"
                :aria-pressed="governmentEnabled"
                @click="gov.toggleGovernment()"
              >
                <Landmark class="w-4 h-4 flex-shrink-0" aria-hidden="true" />
                <span class="layers-popover-label">{{ $t('map.layers.government') }}</span>
                <Eye v-if="governmentEnabled" class="w-3.5 h-3.5 flex-shrink-0 opacity-70" aria-hidden="true" />
                <EyeOff v-else class="w-3.5 h-3.5 flex-shrink-0 opacity-30" aria-hidden="true" />
              </button>
              <button
                class="layers-popover-item"
                :class="{ active: churchEnabled }"
                :aria-pressed="churchEnabled"
                @click="church.toggleChurches()"
              >
                <Cross class="w-4 h-4 flex-shrink-0" aria-hidden="true" />
                <span class="layers-popover-label">{{ $t('map.layers.churches') }}</span>
                <Eye v-if="churchEnabled" class="w-3.5 h-3.5 flex-shrink-0 opacity-70" aria-hidden="true" />
                <EyeOff v-else class="w-3.5 h-3.5 flex-shrink-0 opacity-30" aria-hidden="true" />
              </button>
              <button
                class="layers-popover-item"
                :class="{ active: condosEnabled }"
                :aria-pressed="condosEnabled"
                @click="condo.toggleCondos()"
              >
                <Building2 class="w-4 h-4 flex-shrink-0" aria-hidden="true" />
                <span class="layers-popover-label">{{ $t('map.layers.condominiums') }}</span>
                <Eye v-if="condosEnabled" class="w-3.5 h-3.5 flex-shrink-0 opacity-70" aria-hidden="true" />
                <EyeOff v-else class="w-3.5 h-3.5 flex-shrink-0 opacity-30" aria-hidden="true" />
              </button>
              <button
                class="layers-popover-item"
                :class="{ active: hubsEnabled }"
                :aria-pressed="hubsEnabled"
                @click="hub.toggleHubs()"
              >
                <Package class="w-4 h-4 flex-shrink-0" aria-hidden="true" />
                <span class="layers-popover-label">{{ $t('map.layers.hubs') }}</span>
                <Eye v-if="hubsEnabled" class="w-3.5 h-3.5 flex-shrink-0 opacity-70" aria-hidden="true" />
                <EyeOff v-else class="w-3.5 h-3.5 flex-shrink-0 opacity-30" aria-hidden="true" />
              </button>
              <button
                class="layers-popover-item"
                :class="{ active: meshEnabled }"
                :aria-pressed="meshEnabled"
                @click="mesh.toggleMesh()"
              >
                <Wifi class="w-4 h-4 flex-shrink-0" aria-hidden="true" />
                <span class="layers-popover-label">{{ $t('map.layers.mesh_network') }}</span>
                <Eye v-if="meshEnabled" class="w-3.5 h-3.5 flex-shrink-0 opacity-70" aria-hidden="true" />
                <EyeOff v-else class="w-3.5 h-3.5 flex-shrink-0 opacity-30" aria-hidden="true" />
              </button>
              <button
                class="layers-popover-item"
                :class="{ active: energyCellsEnabled }"
                :aria-pressed="energyCellsEnabled"
                @click="iot.toggleEnergyCells()"
              >
                <Zap class="w-4 h-4 flex-shrink-0" aria-hidden="true" />
                <span class="layers-popover-label">{{ $t('map.layers.energy') }}</span>
                <Eye v-if="energyCellsEnabled" class="w-3.5 h-3.5 flex-shrink-0 opacity-70" aria-hidden="true" />
                <EyeOff v-else class="w-3.5 h-3.5 flex-shrink-0 opacity-30" aria-hidden="true" />
              </button>
            </div>
          </div>
          <!-- Map Tools -->
          <div class="architect-control">
            <button
              @click.stop="architectPopoverOpen = !architectPopoverOpen; layersPopoverOpen = false; iotPopoverOpen = false; hideIoTPreview()"
              class="opensky-btn"
              :class="{ active: measureActive || sunStudyActive || isochroneActive }"
              :title="$t('map.architect.title')"
            >
              <Ruler class="w-5 h-5" />
            </button>
            <div v-if="architectPopoverOpen" class="layers-popover" @click.stop>
              <button
                class="layers-popover-item"
                :class="{ active: measureActive && measureMode === 'distance' }"
                @click="if (sunStudyActive) sunStudy.stopSunStudy(); if (isochroneActive) isochrone.stopIsochrone(); measure.toggleMeasure('distance'); architectPopoverOpen = false"
              >
                <Ruler class="w-4 h-4 flex-shrink-0" aria-hidden="true" />
                <span class="layers-popover-label">{{ $t('map.architect.measure') }}</span>
              </button>
              <button
                class="layers-popover-item"
                :class="{ active: measureActive && measureMode === 'area' }"
                @click="if (sunStudyActive) sunStudy.stopSunStudy(); if (isochroneActive) isochrone.stopIsochrone(); measure.toggleMeasure('area'); architectPopoverOpen = false"
              >
                <Pentagon class="w-4 h-4 flex-shrink-0" aria-hidden="true" />
                <span class="layers-popover-label">{{ $t('map.architect.measure_area') }}</span>
              </button>
              <button
                class="layers-popover-item"
                :class="{ active: sunStudyActive }"
                @click="if (measureActive) measure.stopMeasure(); if (isochroneActive) isochrone.stopIsochrone(); sunStudy.toggleSunStudy(); architectPopoverOpen = false"
              >
                <Sun class="w-4 h-4 flex-shrink-0" aria-hidden="true" />
                <span class="layers-popover-label">{{ $t('map.architect.sun_study') }}</span>
              </button>
              <button
                class="layers-popover-item"
                :class="{ active: isochroneActive }"
                @click="if (measureActive) measure.stopMeasure(); if (sunStudyActive) sunStudy.stopSunStudy(); isochrone.toggleIsochrone(); architectPopoverOpen = false"
              >
                <Clock class="w-4 h-4 flex-shrink-0" aria-hidden="true" />
                <span class="layers-popover-label">{{ $t('map.architect.isochrone') }}</span>
              </button>
            </div>
          </div>
          <!-- IoT Devices popover (Routers + Trackers) -->
          <div v-if="authStore.isAuthenticated" class="tracker-control">
            <button
              @click.stop="iotPopoverOpen = !iotPopoverOpen; layersPopoverOpen = false; architectPopoverOpen = false; if (!iotPopoverOpen) hideIoTPreview()"
              class="opensky-btn"
              title="IoT Devices"
            >
              <Radar class="w-5 h-5" />
            </button>
          <div v-if="iotPopoverOpen" class="tracker-popover" @click.stop>
            <!-- My Homes section -->
            <div v-if="propertyStore.properties.length > 0" class="tracker-popover-header" @click="iotHomesExpanded = !iotHomesExpanded" @keydown.enter="iotHomesExpanded = !iotHomesExpanded" @keydown.space.prevent="iotHomesExpanded = !iotHomesExpanded" role="button" tabindex="0" style="cursor: pointer;">
              <div class="iot-section-toggle">
                <ChevronRight class="w-3 h-3 iot-chevron" :class="{ expanded: iotHomesExpanded }" />
                <Home class="w-3.5 h-3.5" />
                <span class="tracker-popover-title">{{ $t('property.my_homes') }}</span>
              </div>
            </div>
            <template v-if="iotHomesExpanded && propertyStore.properties.length > 0">
              <button
                v-for="p in propertyStore.properties"
                :key="p.id"
                class="tracker-popover-item"
                :disabled="!p.latitude"
                @click="p.latitude && selectAndFlyToProperty(p)"
                @mouseenter="p.latitude && showIoTPreview(p.latitude, p.longitude)"
                @mouseleave="hideIoTPreview()"
              >
                <component :is="propertyTypeIcon(p.property_type)" class="w-3 h-3 opacity-60" />
                <span class="tracker-item-name">{{ p.name }}</span>
                <span v-if="p.device_count" class="tracker-item-speed">{{ p.device_count }} IoT</span>
              </button>
            </template>
            <!-- Mesh Routers section -->
            <div class="tracker-popover-header" @click="iotRoutersExpanded = !iotRoutersExpanded" @keydown.enter="iotRoutersExpanded = !iotRoutersExpanded" @keydown.space.prevent="iotRoutersExpanded = !iotRoutersExpanded" role="button" tabindex="0" style="cursor: pointer;">
              <div class="iot-section-toggle">
                <ChevronRight class="w-3 h-3 iot-chevron" :class="{ expanded: iotRoutersExpanded }" />
                <Radio class="w-3.5 h-3.5" />
                <span class="tracker-popover-title">{{ $t('mesh.mesh_routers') }}</span>
              </div>
            </div>
            <template v-if="iotRoutersExpanded">
              <div v-if="meshRouterPositionsList.length === 0" class="tracker-popover-empty">
                No routers with location
              </div>
              <button
                v-for="r in meshRouterPositionsList"
                :key="r.device_id"
                class="tracker-popover-item"
                @click="selectAndFlyToMeshRouter(r)"
                @mouseenter="showIoTPreview(r.latitude, r.longitude)"
                @mouseleave="hideIoTPreview()"
              >
                <span class="tracker-status-dot" :class="r.status === 'online' ? 'online' : r.status === 'recent' ? 'online' : 'offline'"></span>
                <span class="tracker-item-name">{{ r.name }}</span>
                <span v-if="r.firmware_role" class="tracker-item-speed">{{ r.firmware_role }}</span>
              </button>
            </template>
            <!-- GPS Trackers section -->
            <div class="tracker-popover-header" @click="iotTrackersExpanded = !iotTrackersExpanded" @keydown.enter="iotTrackersExpanded = !iotTrackersExpanded" @keydown.space.prevent="iotTrackersExpanded = !iotTrackersExpanded" role="button" tabindex="0" style="cursor: pointer;">
              <div class="iot-section-toggle">
                <ChevronRight class="w-3 h-3 iot-chevron" :class="{ expanded: iotTrackersExpanded }" />
                <Radar class="w-3.5 h-3.5" />
                <span class="tracker-popover-title">GPS Trackers</span>
              </div>
              <button @click.stop="toggleTrackerLayer" class="tracker-eye-btn" :aria-label="trackersEnabled ? $t('map.toggle_hide_layer', { layer: 'GPS Trackers' }) : $t('map.toggle_show_layer', { layer: 'GPS Trackers' })">
                <Eye v-if="trackersEnabled" class="w-3.5 h-3.5" />
                <EyeOff v-else class="w-3.5 h-3.5 opacity-50" />
              </button>
            </div>
            <template v-if="iotTrackersExpanded">
              <div v-if="trackerPositionsList.length === 0" class="tracker-popover-empty">
                No trackers
              </div>
              <button
                v-for="t in trackerPositionsList"
                :key="t.device_id"
                class="tracker-popover-item"
                @click="selectAndFlyToTracker(t)"
                @mouseenter="showIoTPreview(t.latitude, t.longitude)"
                @mouseleave="hideIoTPreview()"
              >
                <span class="tracker-status-dot" :class="t.traccar_status === 'online' ? 'online' : t.traccar_status === 'offline' ? 'offline' : 'unknown'"></span>
                <span class="tracker-item-name">{{ t.name }}</span>
                <span v-if="trackerSignalAge(t) >= 5" class="tracker-item-signal-lost" :title="t.last_update">{{ trackerSignalAgeText(t) }}</span>
                <span v-else-if="t.speed && t.speed > 1" class="tracker-item-speed">{{ Math.round(t.speed) }} km/h</span>
              </button>
            </template>
          </div>
        </div>
        </div>
        <!-- OpenSky pilot tools (only when aerial mode active) -->
        <div v-if="openSkyMode" class="map-ctrl-group">
          <NuxtLink
            :to="localePath('/opensky')"
            class="opensky-btn"
            title="OpenSky Dashboard"
          >
            <Plane class="w-5 h-5" />
          </NuxtLink>
          <button
            v-if="authStore.isAuthenticated"
            @click="toggleMissionArea"
            class="opensky-btn"
            :class="{ active: tileGridMode || missionGenerating }"
            :disabled="missionGenerating"
            :title="tileGridMode ? 'Exit mission planning' : 'Plan drone missions'"
          >
            <Grid3x3 class="w-5 h-5" :class="{ 'animate-pulse': missionGenerating }" />
          </button>
        </div>
      </div>

      <!-- Measure bar (bottom center) -->
      <div v-if="measureActive" class="measure-bar">
        <span v-if="measure.measurePoints.value.length === 0" class="measure-bar-hint">{{ $t('map.architect.click_to_measure') }}</span>
        <template v-else-if="measureMode === 'area'">
          <span class="measure-bar-distance">{{ measure.formattedArea.value }}</span>
          <span class="measure-bar-segments">{{ $t('map.architect.perimeter') }}: {{ measure.formattedPerimeter.value }}</span>
        </template>
        <template v-else>
          <span class="measure-bar-distance">{{ measure.formattedTotal.value }}</span>
          <span class="measure-bar-segments">{{ measure.measurePoints.value.length }} {{ $t('map.architect.points') }}</span>
        </template>
        <button @click="measure.undoLastPoint()" class="measure-bar-btn" :disabled="measure.measurePoints.value.length === 0">
          {{ $t('map.architect.undo') }}
        </button>
        <button @click="measure.clearMeasure()" class="measure-bar-btn" :disabled="measure.measurePoints.value.length === 0">
          {{ $t('map.architect.clear') }}
        </button>
        <button @click="measure.stopMeasure()" class="measure-bar-btn measure-bar-btn-close">
          ×
        </button>
      </div>

      <!-- Sun study panel (bottom center) -->
      <div v-if="sunStudyActive" class="sun-study-panel">
        <div class="sun-study-header">
          <Sun class="w-4 h-4 flex-shrink-0 text-amber-500" />
          <input type="date" v-model="sunDateISO" class="sun-study-date" />
          <span class="sun-study-time-display">{{ formattedTime }}</span>
          <div class="sun-study-badges">
            <button
              class="sun-study-badge"
              :class="realtimeMode ? 'sun-live' : 'sun-live-off'"
              @click="!realtimeMode && sunStudy.startSunStudy()"
            >LIVE</button>
            <span v-if="isGoldenHour" class="sun-study-badge sun-golden">{{ $t('map.architect.golden_hour') }}</span>
            <span v-else-if="isNight" class="sun-study-badge sun-night">{{ $t('map.architect.night') }}</span>
          </div>
          <button @click="sunStudy.stopSunStudy()" class="sun-study-close">×</button>
        </div>
        <div class="sun-study-slider-wrap">
          <input
            type="range"
            v-model.number="sunTimeMinutes"
            min="0" max="1440" step="1"
            class="sun-study-slider"
            @input="realtimeMode = false"
          />
          <div class="sun-study-ticks">
            <span v-for="h in [0, 3, 6, 9, 12, 15, 18, 21, 24]" :key="h"
              class="sun-study-tick" :style="{ left: (h / 24 * 100) + '%' }">{{ h }}:00</span>
          </div>
        </div>
        <div class="sun-study-info">
          <span class="sun-study-stat">↑ {{ sunTimes?.sunrise }}</span>
          <span class="sun-study-stat">
            Az {{ sunPosition?.azimuthDeg?.toFixed(0) }}° · Alt {{ sunPosition?.altitudeDeg?.toFixed(1) }}°
          </span>
          <span class="sun-study-stat">↓ {{ sunTimes?.sunset }}</span>
        </div>
      </div>

      <!-- Isochrone panel (bottom center) -->
      <div v-if="isochroneActive" class="isochrone-bar">
        <template v-if="!isochrone.isochroneCenter.value">
          <span class="measure-bar-hint">{{ $t('map.architect.click_for_isochrone') }}</span>
        </template>
        <template v-else>
          <span class="isochrone-bar-legend">
            <span class="isochrone-dot" style="background: #22c55e"></span>5 min
            <span class="isochrone-dot" style="background: #f59e0b"></span>10 min
            <span class="isochrone-dot" style="background: #ef4444"></span>15 min
          </span>
        </template>
        <div class="isochrone-mode-btns">
          <button
            class="isochrone-mode-btn" :class="{ active: costingMode === 'pedestrian' }"
            @click="isochrone.setCostingMode('pedestrian')" :title="$t('map.architect.pedestrian')"
          >🚶</button>
          <button
            class="isochrone-mode-btn" :class="{ active: costingMode === 'bicycle' }"
            @click="isochrone.setCostingMode('bicycle')" :title="$t('map.architect.bicycle')"
          >🚲</button>
          <button
            class="isochrone-mode-btn" :class="{ active: costingMode === 'auto' }"
            @click="isochrone.setCostingMode('auto')" :title="$t('map.architect.car')"
          >🚗</button>
        </div>
        <span v-if="isochroneLoading" class="isochrone-loading">⏳</span>
        <button @click="isochrone.stopIsochrone()" class="measure-bar-btn measure-bar-btn-close">×</button>
      </div>

    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onActivated, onDeactivated, onBeforeUnmount, nextTick } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { MapPin, Map as MapIcon, ArrowLeft, Layers, Grid3x3, Plane, Radar, Eye, EyeOff, Building2, Radio, ChevronRight, Bus, Route, Zap, Home, Warehouse, LandPlot, Landmark, Package, Wifi, Satellite, Cross, Ruler, Sun, Pentagon, Clock, Box } from 'lucide-vue-next'
import { createGeolocationControl } from '~/composables/useGeolocationControl'
import { useMapKeyboard } from '~/composables/useMapKeyboard'
import { useMapHighlight } from '~/composables/useMapHighlight'
import { useMapIoTLayers } from '~/composables/useMapIoTLayers'
import { useMapOpenSky } from '~/composables/useMapOpenSky'
import { useMapTransitLayers } from '~/composables/useMapTransitLayers'
import { useMapBrowse } from '~/composables/useMapBrowse'
import { useMapRouting } from '~/composables/useMapRouting'
import { useMapAvatarPanel } from '~/composables/useMapAvatarPanel'
import { useMapCondoLayers } from '~/composables/useMapCondoLayers'
import { useMapMeshLayer } from '~/composables/useMapMeshLayer'
import { useMapGovernmentLayer } from '~/composables/useMapGovernmentLayer'
import { useMapChurchLayer } from '~/composables/useMapChurchLayer'
import { useMapMeasure } from '~/composables/useMapMeasure'
import { useMapSunStudy } from '~/composables/useMapSunStudy'
import { useMapIsochrone } from '~/composables/useMapIsochrone'

const router = useRouter()
const localePath = useLocalePath()
const route = useRoute()
const { t } = useI18n()
const mapStore = useMapStore()
const authStore = useAuthStore()

// ======== Theme / Animation ========

const colorMode = useColorMode()
const mapStyle = computed(() => colorMode.value === 'dark' ? 'dark-liberty' : 'osm-liberty')

const animationEnabled = useLocalPref('animation_enabled', true)

// ======== Shared Map State ========

const { mapCenter, mapZoom } = useMapState()
const {
  currentMarker, selectedFeature, clickedFeatures, clickCoordinates,
  setCurrentMarker, setSelectedFeature, setClickedFeatures, setClickCoordinates,
  setMapCenter, setMapZoom
} = useMapState()

// Search language from profile
const searchLanguage = ref('en')
watch(() => authStore.profile?.preferred_language, (newLang) => {
  if (newLang) searchLanguage.value = newLang
}, { immediate: true })

// ======== Composables ========

const highlight = useMapHighlight()

const browse = useMapBrowse({
  setSelectedFeature,
  setClickedFeatures,
  setClickCoordinates,
  animationEnabled,
})
const {
  browseVisible, browseWasOpen,
  browseCategoryId, browseCategoryName, browseCategoryIcon,
} = browse

const routing = useMapRouting({ browseVisible, animationEnabled })
const {
  routingVisible, routeGeoJSON, routeBounds,
  awaitingMapClick, routingOrigin, routingDest,
} = routing

const avatar = useMapAvatarPanel({
  browseVisible,
  browseWasOpen,
  setSelectedFeature,
  setClickedFeatures,
  setClickCoordinates,
})
const {
  mapPresenceEnabled, currentAvatarType, currentSpeechBubble, currentAvatarState,
  activeAvatarPanel, nearbyAvatars, isMapPresenceConnected,
  panelContentType, panelAvatarData,
  wrappedSetState, wrappedSetSpeechBubble,
} = avatar

// Current OpenSky mission filter from URL
const currentOpenSkyMission = computed(() => route.query.opensky_mission as string | undefined)

const openSky = useMapOpenSky(currentOpenSkyMission)
const { openSkyEnabled, openSkyMode, missionGenerating, tileGridMode } = openSky

// Layers popover state
const layersPopoverOpen = ref(false)

const iot = useMapIoTLayers()
const {
  trackersEnabled, trackerPositionsList,
  meshRouterPositionsList,
  energyCellsEnabled,
  iotPopoverOpen, iotRoutersExpanded, iotTrackersExpanded,
  showIoTPreview, hideIoTPreview,
} = iot

const transit = useMapTransitLayers()
const { transitEnabled } = transit

const mesh = useMapMeshLayer()
const { meshEnabled } = mesh

const condo = useMapCondoLayers()
const { condosEnabled } = condo

const hub = useMapHubLayers()
const { hubsEnabled } = hub

const gov = useMapGovernmentLayer()
const { governmentEnabled } = gov

const church = useMapChurchLayer()
const { churchEnabled } = church

const tiles3d = useMap3DTiles()
const { tiles3dEnabled } = tiles3d

// ======== Map Tools ========

const measure = useMapMeasure()
const { measureActive, measureMode } = measure

const sunStudy = useMapSunStudy()
const { sunStudyActive, sunTimeMinutes, sunDateISO, realtimeMode, sunPosition, sunTimes, formattedTime, isGoldenHour, isNight } = sunStudy

const isochrone = useMapIsochrone()
const { isochroneActive, isochroneLoading, costingMode, costingLabel } = isochrone

const architectPopoverOpen = ref(false)
const customControlsTop = ref('250px') // updated dynamically after map init
/** Sky + atmosphere config adapted to current theme */
function _applySky(map: any) {
  const dark = colorMode.value === 'dark'
  map.setSky({
    'sky-color': dark ? '#0a0a1a' : '#88c0ec',
    'fog-color': dark ? '#0a0a1a' : '#88c0ec',
    'sky-horizon-blend': 0.4,
    'horizon-fog-blend': 0,
    'fog-ground-blend': 0,
    'atmosphere-blend': 0,
  })
}

// ======== My Homes (properties) in IoT popover ========

const propertyStore = usePropertyStore()
const iotHomesExpanded = ref(true)
const propertiesLoaded = ref(false)

watch(iotPopoverOpen, async (open) => {
  if (open && !propertiesLoaded.value && authStore.isAuthenticated) {
    await propertyStore.fetchProperties()
    propertiesLoaded.value = true
  }
})

const propertyTypeIcon = (type: string) => {
  switch (type) {
    case 'apartment': return Building2
    case 'garage': return Warehouse
    case 'land': return LandPlot
    default: return Home
  }
}

// ======== Vehicle panel state ========

const selectedVehicle = ref<any>(null)

// ======== IoT device panel state ========

const selectedIoTDevice = ref<any>(null)

// ======== Condominium panel state ========

const selectedCondominium = ref<any>(null)

// ======== Hub panel state ========

const selectedHub = ref<any>(null)

// ======== Establishment panel state (government, churches, etc.) ========

const selectedEstablishment = ref<any>(null)

// Override panelContentType to include vehicle, IoT device, condominium, hub, and establishment
const panelContentTypeWithVehicle = computed(() => {
  if (selectedVehicle.value) return 'vehicle'
  if (selectedIoTDevice.value) return 'iot_device'
  if (selectedCondominium.value) return 'condominium'
  if (selectedHub.value) return 'hub'
  if (selectedEstablishment.value) return 'establishment'
  return panelContentType.value
})

// Wire vehicle click → panel
transit.setVehicleClickHandler((vehicle: any) => {
  // Clear other panel states (mutual exclusion)
  setSelectedFeature(null)
  setClickedFeatures([])
  setClickCoordinates(null)
  avatar.clearAvatarPanel()
  selectedIoTDevice.value = null
  selectedCondominium.value = null
  selectedHub.value = null
  selectedEstablishment.value = null
  if (routingVisible.value) routingVisible.value = false
  if (browseVisible.value) {
    browseWasOpen.value = true
    browseVisible.value = false
  }
  selectedVehicle.value = vehicle
})

// ======== IoT popover → panel bridge ========

const selectIoTDevice = (deviceType: string, data: any) => {
  // Clear other panel states
  setSelectedFeature(null)
  setClickedFeatures([])
  setClickCoordinates(null)
  avatar.clearAvatarPanel()
  selectedVehicle.value = null
  if (routingVisible.value) routingVisible.value = false
  if (browseVisible.value) { browseWasOpen.value = true; browseVisible.value = false }

  selectedIoTDevice.value = {
    deviceType,
    device_id: data.device_id || data.id || '',
    name: data.name || '',
    status: data.status || 'unknown',
    speed: data.speed ? `${Math.round(data.speed)} km/h` : '',
    firmware_role: data.firmware_role || '',
    hardware_profile: data.hardware_profile || '',
    price: data.price || '',
    lngLat: data.latitude != null ? { lat: data.latitude, lng: data.longitude } : null,
    last_update: data.last_update || null,
  }

  // Show lock-on animation
  if (data.latitude != null) iot.showIoTLockOn(data.latitude, data.longitude)
}

/** Returns age in minutes since last tracker update, or 0 if fresh/unavailable. */
const trackerSignalAge = (t: any): number => {
  if (!t.last_update) return 0
  return Math.floor((Date.now() - new Date(t.last_update).getTime()) / 60_000)
}

const trackerSignalAgeText = (t: any): string => {
  const min = trackerSignalAge(t)
  if (min < 60) return `${min}m`
  const h = Math.floor(min / 60)
  const rem = min % 60
  return rem > 0 ? `${h}h${rem}m` : `${h}h`
}

const selectAndFlyToMeshRouter = (r: any) => {
  selectIoTDevice('mesh_router', r)
  iot.flyToMeshRouter(r.latitude, r.longitude, r.name)
}

const selectAndFlyToTracker = (t: any) => {
  selectIoTDevice('tracker', { ...t, status: t.traccar_status })
  iot.flyToTracker(t.latitude, t.longitude, t.name)
  iot.enableFollow()
}

const handleShowTrail = (geojson: any) => {
  const map = mapStore.mapInstance
  if (!map) return
  iot.showTrail(map, geojson)
  const coords = geojson?.features?.find((f: any) => f.properties?.role === 'trail')?.geometry?.coordinates
  if (coords && coords.length >= 2) {
    let minLng = Infinity, maxLng = -Infinity, minLat = Infinity, maxLat = -Infinity
    for (const [lng, lat] of coords) {
      if (lng < minLng) minLng = lng
      if (lng > maxLng) maxLng = lng
      if (lat < minLat) minLat = lat
      if (lat > maxLat) maxLat = lat
    }
    map.fitBounds([[minLng, minLat], [maxLng, maxLat]], { padding: 80, maxZoom: 16 })
  }
}

const handleClearTrail = () => {
  const map = mapStore.mapInstance
  if (map) iot.clearTrail(map)
}

const handleTrailCursor = (data: { lng: number; lat: number; heading: number | null }) => {
  const map = mapStore.mapInstance
  if (map) iot.updateTrailCursor(map, data.lng, data.lat, data.heading)
}

const handleRecenterIoT = () => {
  const dev = selectedIoTDevice.value
  if (!dev?.lngLat) return
  iot.enableFollow()
  iot.flyToTracker(dev.lngLat.lat, dev.lngLat.lng, dev.name || '')
  iot.replayIoTLockOn(dev.lngLat.lat, dev.lngLat.lng)
}

const selectAndFlyToProperty = (p: any) => {
  // Clear panel states + fly to property location with lock-on
  setSelectedFeature(null)
  setClickedFeatures([])
  setClickCoordinates(null)
  avatar.clearAvatarPanel()
  selectedVehicle.value = null
  selectedIoTDevice.value = null
  selectedCondominium.value = null
  selectedHub.value = null
  selectedEstablishment.value = null
  if (routingVisible.value) routingVisible.value = false
  if (browseVisible.value) { browseWasOpen.value = true; browseVisible.value = false }

  iot.showIoTLockOn(p.latitude, p.longitude)
  iot.hideIoTPreview()
  const map = mapStore.mapInstance
  if (map) {
    const animEnabled = useLocalPref('animation_enabled', true)
    if (animEnabled.value !== false) {
      map.flyTo({ center: [p.longitude, p.latitude], zoom: 17, essential: true, speed: 4.5 })
    } else {
      map.jumpTo({ center: [p.longitude, p.latitude], zoom: 17 })
    }
  }
  iotPopoverOpen.value = false
  layersPopoverOpen.value = false
}

// ======== Tracker WS real-time updates ========

const trackerWs = useTrackerDeviceWs()
let lastLockOnTime = 0
let lastLockOnLat = 0
let lastLockOnLon = 0
const LOCK_ON_MIN_INTERVAL = 30000 // 30s between animations
const LOCK_ON_MIN_DISTANCE = 0.0001 // ~11m — skip if barely moved
const PANEL_UPDATE_INTERVAL = 2000 // min ms between panel reactive updates
let panelUpdateTimer: ReturnType<typeof setTimeout> | null = null
let pendingPanelUpdate: { speed: string; lat: number; lon: number; status: string; last_update: string | null } | null = null
let lastPanelFlush = 0

function flushPanelUpdate() {
  if (pendingPanelUpdate && selectedIoTDevice.value) {
    selectedIoTDevice.value = {
      ...selectedIoTDevice.value,
      speed: pendingPanelUpdate.speed,
      status: pendingPanelUpdate.status,
      lngLat: { lat: pendingPanelUpdate.lat, lng: pendingPanelUpdate.lon },
      last_update: pendingPanelUpdate.last_update,
    }
    pendingPanelUpdate = null
  }
}

// Watch only device_id changes — NOT every position update from WS callback.
// Without this, the WS callback setting selectedIoTDevice.value triggers
// the watcher, which re-subscribes, which gets an update, which triggers
// the watcher again → infinite loop (2-5MB/s memory growth, 130% CPU).
watch(() => selectedIoTDevice.value?.device_id, (newId, oldId) => {
  // Unsubscribe from previous
  if (oldId) {
    trackerWs.unsubscribe()
    if (panelUpdateTimer) { clearTimeout(panelUpdateTimer); panelUpdateTimer = null }
    pendingPanelUpdate = null
  }
  // Subscribe to new tracker
  const dev = selectedIoTDevice.value
  if (dev?.deviceType === 'tracker' && newId) {
    lastLockOnTime = Date.now()
    lastLockOnLat = dev.lngLat?.lat || 0
    lastLockOnLon = dev.lngLat?.lng || 0

    lastPanelFlush = 0

    trackerWs.subscribeDevice(newId, (tracker) => {
      // tracker: { dev, name, lat, lon, spd, hdg, bat, t, owner }
      if (!selectedIoTDevice.value || selectedIoTDevice.value.device_id !== tracker.dev) return
      const newLat = tracker.lat
      const newLon = tracker.lon
      const newSpeed = tracker.spd || 0
      // Derive status from tracker timestamp age
      const trackerEpoch = tracker.t || 0
      const ageSec = Math.floor(Date.now() / 1000) - trackerEpoch
      const wsStatus = ageSec < 120 ? 'online' : ageSec < 600 ? 'unknown' : 'offline'
      const wsLastUpdate = trackerEpoch ? new Date(trackerEpoch * 1000).toISOString() : null
      // Throttled panel update — only trigger Vue reactivity at most every PANEL_UPDATE_INTERVAL
      pendingPanelUpdate = {
        speed: newSpeed > 1 ? `${Math.round(newSpeed)} km/h` : '',
        lat: newLat,
        lon: newLon,
        status: wsStatus,
        last_update: wsLastUpdate,
      }
      const now2 = Date.now()
      if (now2 - lastPanelFlush >= PANEL_UPDATE_INTERVAL) {
        flushPanelUpdate()
        lastPanelFlush = now2
      } else if (!panelUpdateTimer) {
        panelUpdateTimer = setTimeout(() => {
          flushPanelUpdate()
          lastPanelFlush = Date.now()
          panelUpdateTimer = null
        }, PANEL_UPDATE_INTERVAL - (now2 - lastPanelFlush))
      }
      // Update map dot (immediate, no reactivity cost)
      iot.updateSingleTracker(tracker.dev, newLat, newLon, newSpeed, wsStatus)
      // Move lock-on marker (immediate, just setLngLat)
      iot.moveIoTLockOn(newLat, newLon)
      // Follow mode: smoothly pan camera to new position
      iot.followToPosition(newLat, newLon)
      // Replay full lock-on animation only if moved significantly AND throttle interval passed
      const now = Date.now()
      const moved = Math.abs(newLat - lastLockOnLat) + Math.abs(newLon - lastLockOnLon) > LOCK_ON_MIN_DISTANCE
      if (moved && now - lastLockOnTime >= LOCK_ON_MIN_INTERVAL) {
        iot.replayIoTLockOn(newLat, newLon)
        lastLockOnTime = now
        lastLockOnLat = newLat
        lastLockOnLon = newLon
      }
    })
  } else if (!newId) {
    trackerWs.unsubscribe()
    if (panelUpdateTimer) { clearTimeout(panelUpdateTimer); panelUpdateTimer = null }
    pendingPanelUpdate = null
  }
})

// ======== Template aliases ========

const toggleOpenSkyLayer = () => {
  // Mutual exclusion: disable 3D tiles when enabling 2D aerial
  if (!openSky.openSkyEnabled.value && tiles3d.tiles3dEnabled.value) {
    tiles3d.toggle()
  }
  openSky.toggleLayer()
}
const toggle3DTiles = () => {
  // Mutual exclusion: disable 2D aerial when enabling 3D tiles
  if (!tiles3d.tiles3dEnabled.value && openSky.openSkyEnabled.value) {
    openSky.toggleLayer()
  }
  tiles3d.toggle()
}
const toggleMissionArea = () => openSky.toggleMissionArea()
const toggleTrackerLayer = () => iot.toggleTrackers()
const toggleTransitLayer = () => transit.toggleLayer()
const toggleRoutingPanel = () => {
  if (!routingVisible.value) {
    // Opening routing → close other panels (mutual exclusion)
    closeFeaturePanel()
    if (browseVisible.value) closeBrowsePanel()
  }
  routing.togglePanel()
}
const closeRoutingPanel = () => routing.closePanel()
const showRouteOnMap = routing.showRouteOnMap
const clearRouteFromMap = routing.clearRouteFromMap
const closeBrowsePanel = () => browse.closePanel()
const updateBrowseMarkers = (results: any[]) => browse.updateMarkers(results)
const handleBrowseSelect = (est: any) => browse.handleSelect(est)
const handleBrowseCategoryCleared = () => browse.handleCategoryCleared()
const handleAvatarClick = avatar.handleAvatarClick
const handleAvatarTypeChange = avatar.handleAvatarTypeChange

const openBrowsePanel = () => {
  if (browseVisible.value) {
    closeBrowsePanel()
    return
  }
  // Clear other panels (mutual exclusion)
  setSelectedFeature(null)
  setClickedFeatures([])
  setClickCoordinates(null)
  avatar.clearAvatarPanel()
  selectedVehicle.value = null
  selectedIoTDevice.value = null
  selectedCondominium.value = null
  selectedHub.value = null
  selectedEstablishment.value = null
  if (routingVisible.value) routing.closePanel()
  browseVisible.value = true
}

// ======== Refs ========

const miniMapContainer = ref<HTMLDivElement | null>(null)
const mapRoot = ref<HTMLDivElement | null>(null)
const featurePanelRef = ref<any>(null)
const loading = ref(true)
let miniMap: any = null

// KeepAlive active state
const isActive = ref(true)
let snapshotImgEl: HTMLImageElement | null = null
let cachedCanvasSnapshot: string | null = null
let transitStopMarker: any = null

// Highlighted item marker positioning
const highlightMarkerStyle = computed(() => {
  if (!mapStore.highlightedItem || !mapStore.userLocation) return {}
  return { left: '50%', top: '50%', transform: 'translate(-50%, -50%)' }
})

// Close popovers on outside click
const onDocumentClick = () => { iotPopoverOpen.value = false; hideIoTPreview(); layersPopoverOpen.value = false; architectPopoverOpen.value = false }

// ======== Keyboard ========

const keyboard = useMapKeyboard({
  getMap: () => miniMap,
  isActive,
  mapPresenceEnabled,
  authStore,
  presenceActions: { setState: wrappedSetState, setSpeechBubble: wrappedSetSpeechBubble },
  currentSpeechBubble,
  currentAvatarState,
  currentAvatarType,
  activeAvatarPanel: avatar.activeAvatarPanel,
  selectedOtherAvatar: avatar.selectedOtherAvatar,
  setSelectedFeature,
  setClickedFeatures,
  setClickCoordinates,
  featurePanelRef,
})

// ======== URL helpers ========

const buildMapQuery = (lat: number, lng: number, zoom: number, feature?: any) => {
  const query: any = { lat: lat.toFixed(6), lng: lng.toFixed(6), zoom: zoom.toFixed(2) }
  if (feature?.sourceLayer) query.layer = feature.sourceLayer
  if (feature?.id) query.featureId = feature.id
  // Preserve osmId: from feature props, or keep existing URL value (set by handleOsmResolved)
  const osmId = feature?.properties?.osm_id || (feature ? route.query.osmId : undefined)
  if (osmId) query.osmId = String(osmId)
  // Preserve establishmentId while panel is open
  if (feature && route.query.establishmentId) query.establishmentId = route.query.establishmentId
  if (currentOpenSkyMission.value) query.opensky_mission = currentOpenSkyMission.value
  if (route.query.returnTo) query.returnTo = route.query.returnTo
  return query
}

const updateUrlWithMapState = (lat: number, lng: number, feature: any = null) => {
  if (!miniMap || !isActive.value) return
  router.replace({ path: localePath('/map'), query: buildMapQuery(lat, lng, miniMap.getZoom(), feature) })
}

const handleOsmResolved = ({ osmId }: { osmId: number }) => {
  if (!miniMap || !isActive.value || !osmId) return
  const query = { ...route.query, osmId: String(osmId) }
  router.replace({ path: localePath('/map'), query })
}

// ======== Search handlers ========

const onLocationSelected = async (location: any) => {
  if (!miniMap) return
  const lngLat = [location.lon, location.lat]
  if (currentMarker.value && typeof currentMarker.value.remove === 'function') currentMarker.value.remove()
  // Zoom based on result type: city/region → 13, neighbourhood → 15, default → 17
  const layer = location.raw?.properties?.layer || ''
  const targetZoom = ['locality', 'localadmin', 'region', 'country'].includes(layer) ? 13
    : ['borough', 'neighbourhood', 'macrohood'].includes(layer) ? 15
    : 17
  if (animationEnabled.value) {
    miniMap.flyTo({ center: lngLat, zoom: targetZoom, essential: true, speed: 4.5 })
  } else {
    miniMap.jumpTo({ center: lngLat, zoom: targetZoom })
  }
  try {
    const maplibreModule = await import('maplibre-gl')
    const maplibregl = maplibreModule.default || maplibreModule
    const { createLockOnElement } = await import('~/utils/lockOnMarker')
    const marker = new maplibregl.Marker({ element: createLockOnElement({ noDot: true }), anchor: 'center' }).setLngLat(lngLat).addTo(miniMap)
    setCurrentMarker(marker)
  } catch (err) {
    console.error('[MapView] Failed to add marker:', err)
  }
}

const handleSearchLocation = async (query: string) => {
  try {
    const response = await fetch(`/api/v1/geo/geocode/search?q=${encodeURIComponent(query)}&limit=1&lang=${searchLanguage.value}`)
    const data = await response.json()
    if (data.features && data.features.length > 0) {
      const feature = data.features[0]
      await onLocationSelected({ lat: feature.geometry.coordinates[1], lon: feature.geometry.coordinates[0], name: feature.properties.name || feature.properties.street || query })
    } else {
      useToastStore().warning(`"${query}" not found in geocoder`)
    }
  } catch (error) {
    console.error('Error searching location:', error)
    useToastStore().error('Search failed')
  }
}

const onSearchCleared = () => {
  if (currentMarker.value && typeof currentMarker.value.remove === 'function') {
    currentMarker.value.remove()
    setCurrentMarker(null)
  }
}

// ======== Establishment selection from panel ========

const handleEstablishmentSelected = (establishmentId: string | null) => {
  if (!miniMap || !isActive.value) return
  const center = miniMap.getCenter()
  const query = buildMapQuery(center.lat, center.lng, miniMap.getZoom(), selectedFeature.value)
  if (establishmentId) query.establishmentId = establishmentId
  router.replace({ path: localePath('/map'), query })
}

// ======== Unified search handlers ========

const handleUnifiedCategorySelect = (cat: any) => {
  browse.handleCategorySelect(cat)
  if (routingVisible.value) { routing.closePanel(); routing.clearRoute() }
}

const handleUnifiedEstablishmentSelect = (est: any) => {
  browse.handleSelect(est)
}

// ======== Feature panel ========

const closeFeaturePanel = () => {
  setSelectedFeature(null)
  setClickedFeatures([])
  setClickCoordinates(null)
  avatar.clearAvatarPanel()
  selectedVehicle.value = null
  selectedIoTDevice.value = null
  selectedCondominium.value = null
  selectedHub.value = null
  selectedEstablishment.value = null
  // Remove search marker
  if (currentMarker.value && typeof currentMarker.value.remove === 'function') {
    currentMarker.value.remove()
    setCurrentMarker(null)
  }
  iot.hideIoTLockOn()
  iot.disableFollow()
  if (mapStore.mapInstance) iot.clearTrail(mapStore.mapInstance)
  browseWasOpen.value = false
  if (tileGridMode.value) openSky.toggleMissionArea()
  if (isActive.value) {
    const center = mapStore.mapInstance?.getCenter()
    if (center) {
      const query: any = { lat: center.lat.toFixed(6), lng: center.lng.toFixed(6), zoom: mapStore.mapInstance?.getZoom().toFixed(2) }
      if (route.query.returnTo) query.returnTo = route.query.returnTo
      router.replace({ path: localePath('/map'), query })
    }
  }
}

const handleFeaturePanelBack = () => {
  setSelectedFeature(null)
  setClickedFeatures([])
  setClickCoordinates(null)
  avatar.clearAvatarPanel()
  selectedVehicle.value = null
  selectedIoTDevice.value = null
  selectedCondominium.value = null
  selectedHub.value = null
  selectedEstablishment.value = null
  iot.hideIoTLockOn()
  browseVisible.value = true
  browseWasOpen.value = false
}

// ======== Escape key — close topmost panel ========

const onEscapeKey = (e: KeyboardEvent) => {
  if (e.key !== 'Escape') return
  // Don't intercept if user is typing in an input/textarea
  const tag = (e.target as HTMLElement)?.tagName
  if (tag === 'INPUT' || tag === 'TEXTAREA') return

  if (selectedFeature.value || selectedVehicle.value || selectedIoTDevice.value || selectedCondominium.value || selectedHub.value || selectedEstablishment.value) {
    closeFeaturePanel()
  } else if (avatar.activeAvatarPanel.value !== null) {
    avatar.clearAvatarPanel()
  } else if (browseVisible.value) {
    closeBrowsePanel()
  } else if (routingVisible.value) {
    routing.closePanel()
    routing.clearRoute()
  } else if (measureActive.value) {
    measure.stopMeasure()
  } else if (sunStudyActive.value) {
    sunStudy.stopSunStudy()
  } else if (isochroneActive.value) {
    isochrone.stopIsochrone()
  } else {
    return // nothing to close
  }
  e.preventDefault()
}

// ======== Transit vehicle data sync (watcher) ========
transit.syncVehicleData()

// ======== onMounted ========

onMounted(async () => {
  await nextTick()
  document.addEventListener('click', onDocumentClick)
  document.addEventListener('keydown', onEscapeKey)

  if (!mapRoot.value) { console.error('[MapView] No map root element'); return }

  // Parse query params for initial map position and feature
  if (route.query) {
    const lat = parseFloat(route.query.lat as string)
    const lng = parseFloat(route.query.lng as string)
    const zoom = parseFloat(route.query.zoom as string)
    if (!isNaN(lat) && !isNaN(lng)) {
      setMapCenter([lng, lat])
      if (!isNaN(zoom)) setMapZoom(zoom)
      if (route.query.transit === '1') {
        transitEnabled.value = true
        window._pendingTransitMarker = { lat, lng, routeCity: route.query.routeCity as string, routeSlug: route.query.routeSlug as string }
      }
      if (route.query.layer || route.query.featureId || route.query.osmId || route.query.establishmentId) {
        window._pendingFeatureRestore = { lat, lng, layer: route.query.layer, featureId: route.query.featureId, osmId: route.query.osmId, establishmentId: route.query.establishmentId }
      }
    }
  }

  let isUpdatingFromUser = false
  let isUpdatingFromCode = false

  try {
    const maplibreModule = await import('maplibre-gl')
    await import('maplibre-gl/dist/maplibre-gl.css')
    const maplibregl = maplibreModule.default || maplibreModule

    const styleMap: Record<string, string> = { 'osm-liberty': '/map-styles/liberty-parahub.json', 'dark-liberty': '/map-styles/dark-liberty-parahub.json' }
    const styleUrl = styleMap[mapStyle.value] || styleMap['osm-liberty']

    miniMap = new maplibregl.Map({
      container: mapRoot.value,
      style: styleUrl,
      center: mapCenter.value,
      zoom: mapZoom.value,
      interactive: true,
      attributionControl: false,
      trackResize: true,
      canvasContextAttributes: { preserveDrawingBuffer: true },
      fadeDuration: animationEnabled.value ? 300 : 0
    })

    miniMap.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2))
    loading.value = false
    await nextTick()
    miniMap.resize()

    // Controls — nav + geolocation merged into one visual group
    const navControl = new maplibregl.NavigationControl({ showCompass: true })
    miniMap.addControl(navControl, 'top-right')

    const GeolocationControl = createGeolocationControl(mapStore, animationEnabled)
    const geoControl = new GeolocationControl()
    miniMap.addControl(geoControl, 'top-right')

    // Move geolocation button into nav control group (avoids separate visual block)
    const topRight = miniMap.getContainer().querySelector('.maplibregl-ctrl-top-right')
    if (topRight) {
      const groups = topRight.querySelectorAll(':scope > .maplibregl-ctrl-group')
      if (groups.length >= 2) {
        const geoBtn = groups[1].querySelector('button')
        if (geoBtn) { groups[0].appendChild(geoBtn); groups[1].remove() }
      }
      // Position custom controls below nav group
      const navGroup = topRight.querySelector('.maplibregl-ctrl-group')
      if (navGroup) {
        const rect = navGroup.getBoundingClientRect()
        const mapRect = miniMap.getContainer().getBoundingClientRect()
        customControlsTop.value = (rect.bottom - mapRect.top + 10) + 'px'
      }
    }

    const attributionControl = new maplibregl.AttributionControl({ compact: true })
    miniMap.addControl(attributionControl, 'bottom-right')

    const scaleControl = new maplibregl.ScaleControl({ maxWidth: 200 })
    miniMap.addControl(scaleControl, 'bottom-left')

    // Cache canvas snapshot on every idle for KeepAlive
    miniMap.on('idle', () => {
      if (isActive.value && miniMap) {
        try { cachedCanvasSnapshot = miniMap.getCanvas().toDataURL('image/jpeg', 0.8) } catch {}
      }
    })

    // Disable IoT follow mode when user drags the map
    miniMap.on('dragstart', () => { iot.disableFollow() })

    miniMap.on('load', () => {
      // Attribution: remove auto-expand, enable user-toggled expand via attrib-ready marker
      const attribEl = miniMap.getContainer().querySelector('.maplibregl-ctrl-attrib')
      if (attribEl) { attribEl.classList.remove('maplibregl-compact-show'); attribEl.classList.add('attrib-ready') }

      nextTick(() => {
        snapshotImgEl = miniMapContainer.value?.querySelector('.map-snapshot-overlay') as HTMLImageElement | null
      })
      mapStore.setMapInstance(miniMap)
      if (typeof window !== 'undefined') (window as any).mapInstance = miniMap

      // Globe projection + atmosphere
      miniMap.setProjection({ type: 'globe' })
      _applySky(miniMap)

      // Layer order: highlight → markers → OpenSky → IoT → gov/church → transit → interactive (last, needs all layers)
      highlight.setupLayers(miniMap)
      highlight.syncMarkers(miniMap, mapStore)
      openSky.setupLayers(miniMap, currentOpenSkyMission.value)
      iot.setupLayers(miniMap)
      mesh.setupLayers(miniMap)
      condo.setupLayers(miniMap)
      hub.setupLayers(miniMap)
      const reRegister = () => highlight.setupInteractiveFeatures(miniMap)
      gov.setupLayers(miniMap, reRegister)
      church.setupLayers(miniMap, reRegister)
      transit.setupLayers(miniMap)
      measure.setupLayers(miniMap)
      sunStudy.setupLayers(miniMap)
      isochrone.setupLayers(miniMap)
      highlight.setupInteractiveFeatures(miniMap) // after all sync layers exist; async layers re-register via callback

      // Auto-enable transit + marker/route from /transit "Show on map"
      if (window._pendingTransitMarker) {
        const { lat, lng, routeCity, routeSlug } = window._pendingTransitMarker
        delete window._pendingTransitMarker
        transit.connectWs()
        if (transitStopMarker) { transitStopMarker.remove(); transitStopMarker = null }
        if (routeCity && routeSlug) {
          transit.showRouteOnMap(miniMap, routeCity, routeSlug)
        } else {
          import('~/utils/lockOnMarker').then(({ createLockOnElement, flashCrosshair }) => {
            const el = createLockOnElement({ iconUrl: '/img/bus-stop.png', clickable: true })
            el.addEventListener('click', () => { marker.remove(); transitStopMarker = null })
            const marker = new maplibregl.Marker({ element: el, anchor: 'center' }).setLngLat([lng, lat]).addTo(miniMap)
            transitStopMarker = marker
            setTimeout(() => {
              if (!transitStopMarker) return
              const pt = miniMap.project([lng, lat])
              flashCrosshair(miniMap.getContainer(), Math.round(pt.x), Math.round(pt.y))
            }, 450)
          })
        }
      }

      browse.setupLayers(miniMap)

      // Initialize map presence
      if (authStore.isAuthenticated && mapPresenceEnabled.value) {
        avatar.initializeMapPresence(miniMap)
      }

      // Restore feature panel from URL
      if (window._pendingFeatureRestore) {
        const pending = window._pendingFeatureRestore
        setTimeout(() => {
          const point = miniMap.project([pending.lng, pending.lat])
          const features = miniMap.queryRenderedFeatures(point)
          if (features && features.length > 0) {
            let targetFeature = features[0]
            if (pending.layer) targetFeature = features.find((f: any) => f.sourceLayer === pending.layer) || features[0]
            if (pending.featureId) targetFeature = features.find((f: any) => f.id == pending.featureId) || targetFeature
            setClickedFeatures(features)
            setSelectedFeature(targetFeature)
            setClickCoordinates({ lat: pending.lat, lng: pending.lng })
            if (pending.establishmentId) window._pendingEstablishmentId = pending.establishmentId
          }
          delete window._pendingFeatureRestore
        }, 500)
      }

      // Dynamic 2D/3D building switching based on pitch
      miniMap.on('pitch', () => {
        const pitch = miniMap.getPitch()
        if (pitch > 0) {
          miniMap.setLayoutProperty('building', 'visibility', 'none')
          miniMap.setLayoutProperty('building-3d', 'visibility', 'visible')
        } else {
          miniMap.setLayoutProperty('building', 'visibility', 'visible')
          miniMap.setLayoutProperty('building-3d', 'visibility', 'none')
        }
      })
    })

    miniMap.on('error', (e: any) => { console.error('[MapView] Map error:', e) })

    // Watch for theme changes
    watch(mapStyle, async (newStyle) => {
      if (!miniMap) return
      await nextTick()
      const styleMap: Record<string, string> = { 'osm-liberty': '/map-styles/liberty-parahub.json', 'dark-liberty': '/map-styles/dark-liberty-parahub.json' }
      const newStyleUrl = styleMap[newStyle] || styleMap['osm-liberty']
      miniMap.once('style.load', () => {
        // Restore globe projection and atmosphere after style reload
        miniMap.setProjection({ type: 'globe' })
        _applySky(miniMap)

        highlight.setupLayers(miniMap)
        openSky.setupLayers(miniMap, currentOpenSkyMission.value)
        // Re-enable tile grid if it was active before style change
        if (tileGridMode.value) {
          tileGridMode.value = false
          openSky.toggleTileGrid()
        }
        iot.setupLayersOnly(miniMap)
        mesh.setupLayersOnly(miniMap)
        condo.setupLayersOnly(miniMap)
        hub.setupLayersOnly(miniMap)
        gov.setupLayersOnly(miniMap)
        church.setupLayersOnly(miniMap)
        transit.resetDataLoaded()
        transit.setupLayers(miniMap)
        browse.setupLayers(miniMap)
        measure.setupLayers(miniMap)
        sunStudy.setupLayers(miniMap)
        highlight.setupInteractiveFeatures(miniMap) // after all layers
        highlight.syncMarkers(miniMap, mapStore)
        if (routingVisible.value && routeGeoJSON.value && routeBounds.value) {
          showRouteOnMap(routeGeoJSON.value, routeBounds.value)
        }
      })
      miniMap.setStyle(newStyleUrl)
    }, { flush: 'post' })

    // Watch for OpenSky mission filter changes
    watch(currentOpenSkyMission, (newMissionId) => {
      if (!miniMap) return
      openSky.setupLayers(miniMap, newMissionId)
      // Fly to coordinates from query params (e.g. navigating from /opensky "Show on map")
      if (newMissionId) {
        const lat = parseFloat(route.query.lat as string)
        const lng = parseFloat(route.query.lng as string)
        const zoom = parseFloat(route.query.zoom as string)
        if (!isNaN(lat) && !isNaN(lng)) {
          miniMap.flyTo({ center: [lng, lat], zoom: !isNaN(zoom) ? zoom : 17, speed: 4.5 })
        }
      }
    })

    // Save map position changes (debounced)
    const { debounce } = await import('~/utils/debounce')
    const saveMapPosition = debounce(() => {
      if (!miniMap || isUpdatingFromCode || !isActive.value) return
      isUpdatingFromUser = true
      const center = miniMap.getCenter()
      const currentZoom = miniMap.getZoom()
      const { setMapCenter, setMapZoom } = useMapState()
      setMapCenter([center.lng, center.lat])
      setMapZoom(currentZoom)
      const query = buildMapQuery(center.lat, center.lng, currentZoom, selectedFeature.value)
      router.replace({ path: localePath('/map'), query })
      setTimeout(() => { isUpdatingFromUser = false }, 100)
    }, 500)

    miniMap.on('moveend', saveMapPosition)
    miniMap.on('zoomend', saveMapPosition)

    // WASD keyboard
    keyboard.attach()

    // Handle map clicks
    miniMap.on('click', (event: any) => {
      // Intercept click for architect tools (handled by composable's own handlers)
      if (measureActive.value) return
      if (isochroneActive.value) return

      // Intercept click for routing waypoints
      if (awaitingMapClick.value) {
        const which = awaitingMapClick.value
        const lngLat = event.lngLat
        $fetch<any>(`/api/v1/geo/geocode/search?q=${lngLat.lat.toFixed(6)},${lngLat.lng.toFixed(6)}&limit=1&lang=${searchLanguage.value}`)
          .then((data: any) => {
            const label = data?.features?.[0]?.properties?.label || `${lngLat.lat.toFixed(5)}, ${lngLat.lng.toFixed(5)}`
            const point = { lat: lngLat.lat, lon: lngLat.lng, name: label }
            if (which === 'origin') routingOrigin.value = point
            else routingDest.value = point
          })
          .catch(() => {
            const point = { lat: lngLat.lat, lon: lngLat.lng, name: `${lngLat.lat.toFixed(5)}, ${lngLat.lng.toFixed(5)}` }
            if (which === 'origin') routingOrigin.value = point
            else routingDest.value = point
          })
        awaitingMapClick.value = null
        return
      }

      // If clicked on a transit vehicle, let the vehicle handler handle it (skip OSM panel)
      const vehicleHit = miniMap.queryRenderedFeatures(event.point, { layers: ['transit-vehicles-circle', 'transit-vehicles-icon'].filter(id => miniMap.getLayer(id)) })
      if (vehicleHit?.length > 0) return

      // If clicked on an IoT device, open IoT panel (before avatar check — IoT uses exact pixel hit, avatars use radius)
      const iotLayers = ['trackers-circle', 'mesh-routers-circle', 'energy-cells-circle'].filter(id => miniMap.getLayer(id))
      if (iotLayers.length > 0) {
        const iotHit = miniMap.queryRenderedFeatures(event.point, { layers: iotLayers })
        if (iotHit?.length > 0) {
          const f = iotHit[0]
          const layerId = f.layer?.id || ''
          const coords = (f.geometry as any)?.coordinates
          const deviceType = layerId.startsWith('trackers') ? 'tracker' : layerId.startsWith('mesh-routers') ? 'mesh_router' : 'energy_cell'
          // Clear other panel states
          setSelectedFeature(null)
          setClickedFeatures([])
          setClickCoordinates(null)
          avatar.clearAvatarPanel()
          selectedVehicle.value = null
          if (routingVisible.value) routingVisible.value = false
          if (browseVisible.value) { browseWasOpen.value = true; browseVisible.value = false }
          // Look up last_update from tracker positions list
          const trackerEntry = deviceType === 'tracker'
            ? trackerPositionsList.value.find((tp: any) => tp.device_id === f.properties?.device_id)
            : null
          selectedIoTDevice.value = {
            deviceType,
            device_id: f.properties?.device_id || '',
            name: f.properties?.name || '',
            status: f.properties?.status || 'unknown',
            speed: f.properties?.speed || '',
            firmware_role: f.properties?.firmware_role || '',
            hardware_profile: f.properties?.hardware_profile || '',
            price: f.properties?.price || '',
            lngLat: coords ? { lng: coords[0], lat: coords[1] } : null,
            last_update: trackerEntry?.last_update || null,
          }
          // Show lock-on animation
          if (coords) iot.showIoTLockOn(coords[1], coords[0])
          // Fly to device
          if (coords) {
            const currentZoom = miniMap.getZoom()
            const targetZoom = 17
            const zoom = Math.max(currentZoom, targetZoom)
            if (animationEnabled.value !== false) {
              miniMap.flyTo({ center: coords, zoom, essential: true, speed: 4.5 })
            } else {
              miniMap.jumpTo({ center: coords, zoom })
            }
          }
          return
        }
      }

      // If clicked on a condominium marker, open condominium panel
      const condoLayers = ['condos-circle'].filter(id => miniMap.getLayer(id))
      if (condoLayers.length > 0) {
        const condoHit = miniMap.queryRenderedFeatures(event.point, { layers: condoLayers })
        if (condoHit?.length > 0) {
          const f = condoHit[0]
          const coords = (f.geometry as any)?.coordinates
          // Clear other panel states
          setSelectedFeature(null)
          setClickedFeatures([])
          setClickCoordinates(null)
          avatar.clearAvatarPanel()
          selectedVehicle.value = null
          selectedIoTDevice.value = null
          selectedHub.value = null
  selectedEstablishment.value = null
          if (routingVisible.value) routingVisible.value = false
          if (browseVisible.value) { browseWasOpen.value = true; browseVisible.value = false }
          selectedCondominium.value = {
            id: f.properties?.id || '',
            name: f.properties?.name || '',
            slug: f.properties?.slug || '',
            full_address: f.properties?.full_address || '',
            fraction_count: f.properties?.fraction_count || 0,
            member_count: f.properties?.member_count || 0,
            lngLat: coords ? { lng: coords[0], lat: coords[1] } : null,
          }
          // Fly to building
          if (coords) {
            const currentZoom = miniMap.getZoom()
            const targetZoom = 17
            const zoom = Math.max(currentZoom, targetZoom)
            if (animationEnabled.value !== false) {
              miniMap.flyTo({ center: coords, zoom, essential: true, speed: 4.5 })
            } else {
              miniMap.jumpTo({ center: coords, zoom })
            }
          }
          return
        }
      }

      // If clicked on a hub marker, open hub panel
      const hubLayers = ['hubs-circle'].filter(id => miniMap.getLayer(id))
      if (hubLayers.length > 0) {
        const hubHit = miniMap.queryRenderedFeatures(event.point, { layers: hubLayers })
        if (hubHit?.length > 0) {
          const f = hubHit[0]
          const coords = (f.geometry as any)?.coordinates
          // Clear other panel states
          setSelectedFeature(null)
          setClickedFeatures([])
          setClickCoordinates(null)
          avatar.clearAvatarPanel()
          selectedVehicle.value = null
          selectedIoTDevice.value = null
          selectedCondominium.value = null
          if (routingVisible.value) routingVisible.value = false
          if (browseVisible.value) { browseWasOpen.value = true; browseVisible.value = false }
          selectedHub.value = {
            id: f.properties?.id || '',
            name: f.properties?.name || '',
            slug: f.properties?.slug || '',
            hub_capacity: f.properties?.hub_capacity || 0,
            hub_accepted_sizes: f.properties?.hub_accepted_sizes || '',
            hub_storage_fee_daily: f.properties?.hub_storage_fee_daily || '0',
            opening_hours: f.properties?.opening_hours || '',
            phone: f.properties?.phone || '',
            lngLat: coords ? { lng: coords[0], lat: coords[1] } : null,
          }
          // Fly to hub
          if (coords) {
            const currentZoom = miniMap.getZoom()
            const targetZoom = 17
            const zoom = Math.max(currentZoom, targetZoom)
            if (animationEnabled.value !== false) {
              miniMap.flyTo({ center: coords, zoom, essential: true, speed: 4.5 })
            } else {
              miniMap.jumpTo({ center: coords, zoom })
            }
          }
          return
        }
      }

      // Check if click was on a government or church marker → open establishment panel
      const establishmentLayers = ['government-icon', 'churches-icon'].filter(id => miniMap.getLayer(id))
      if (establishmentLayers.length > 0) {
        const estHit = miniMap.queryRenderedFeatures(event.point, { layers: establishmentLayers })
        if (estHit?.length > 0) {
          const f = estHit[0]
          const coords = (f.geometry as any)?.coordinates
          const layerId = f.layer?.id || ''
          setSelectedFeature(null)
          setClickedFeatures([])
          setClickCoordinates(null)
          avatar.clearAvatarPanel()
          selectedVehicle.value = null
          selectedIoTDevice.value = null
          selectedCondominium.value = null
          selectedHub.value = null
          selectedEstablishment.value = null
          if (routingVisible.value) routingVisible.value = false
          if (browseVisible.value) { browseWasOpen.value = true; browseVisible.value = false }
          selectedEstablishment.value = {
            id: f.properties?.id || '',
            name: f.properties?.name || '',
            slug: f.properties?.slug || '',
            category_label: layerId === 'churches-icon' ? t('map.layers.churches') : t('map.layers.government'),
            municipality: f.properties?.municipality || '',
            lngLat: coords ? { lng: coords[0], lat: coords[1] } : null,
          }
          if (coords) {
            const currentZoom = miniMap.getZoom()
            const targetZoom = 16
            const zoom = Math.max(currentZoom, targetZoom)
            if (animationEnabled.value !== false) {
              miniMap.flyTo({ center: coords, zoom, essential: true, speed: 4.5 })
            } else {
              miniMap.jumpTo({ center: coords, zoom })
            }
          }
          return
        }
      }

      // Check if click was on avatar (after IoT — IoT uses exact pixel hit, avatars use radius)
      const clickRadius = 32
      const ownClickRadius = 48
      if (authStore.activeProfile?.id && mapPresenceEnabled.value) {
        const center = miniMap.getCenter()
        const centerPoint = miniMap.project([center.lng, center.lat])
        const dx = event.point.x - centerPoint.x
        const dy = event.point.y - centerPoint.y
        if (Math.sqrt(dx * dx + dy * dy) <= ownClickRadius) {
          handleAvatarClick({
            profile_id: authStore.activeProfile.id, lat: center.lat, lon: center.lng,
            zoom: 14, avatar_type: currentAvatarType.value, avatar_state: 'idle',
            speech_bubble: '', profile_hna: '', profile_name: 'You'
          }, true)
          return
        }
      }

      for (const av of nearbyAvatars.value) {
        if (!av.lat || !av.lon) continue
        if (av.profile_id === authStore.activeProfile?.id) continue
        const avatarPoint = miniMap.project([av.lon, av.lat])
        const dx = event.point.x - avatarPoint.x
        const dy = event.point.y - avatarPoint.y
        if (Math.sqrt(dx * dx + dy * dy) <= clickRadius) {
          handleAvatarClick(av, false)
          return
        }
      }

      // Query all features at click point
      const allFeatures = miniMap.queryRenderedFeatures(event.point)
      highlight.clearActiveFeature(miniMap)

      let features = allFeatures?.filter((f: any) => {
        const layerId = f.layer?.id || ''
        if (layerId.endsWith('-hover') || layerId.endsWith('-active')) return false
        if (layerId.includes('_casing')) return false
        if (layerId === 'map-presence-layer' || layerId === 'map-presence-bubbles') return false
        if (layerId === 'poi-hover-hex-layer') return false
        if (layerId.startsWith('transit-vehicles')) return false
        if (layerId.startsWith('trackers-') || layerId.startsWith('mesh-routers-') || layerId.startsWith('energy-cells-') || layerId.startsWith('condos-')) return false
        return true
      }) || []

      const seen = new Set()
      features = features.filter((f: any) => {
        const key = `${f.sourceLayer || 'unknown'}_${f.id || Math.random()}`
        if (seen.has(key)) return false
        seen.add(key)
        return true
      })

      if (features.length > 0) {
        let feature = features[0]
        if (feature.sourceLayer === 'housenumber') {
          const buildingFeature = features.find((f: any) => f.sourceLayer === 'building')
          if (buildingFeature) feature = buildingFeature
        }
        selectedVehicle.value = null
        selectedIoTDevice.value = null
        selectedCondominium.value = null
        selectedHub.value = null
  selectedEstablishment.value = null
        highlight.setActiveFeature(miniMap, feature)
        if (routingVisible.value) routingVisible.value = false
        if (browseVisible.value) { browseWasOpen.value = true; browseVisible.value = false }
        setClickedFeatures(features)
        setSelectedFeature(feature)
        setClickCoordinates({ lat: event.lngLat.lat, lng: event.lngLat.lng })
        updateUrlWithMapState(event.lngLat.lat, event.lngLat.lng, feature)
      } else {
        closeFeaturePanel()
      }
    })

    // Sync center/zoom watchers
    watch(mapCenter, (center) => {
      if (miniMap && center && !isUpdatingFromUser) {
        isUpdatingFromCode = true
        miniMap.setCenter(center)
        setTimeout(() => { isUpdatingFromCode = false }, 100)
      }
    })
    watch(mapZoom, (zoom) => {
      if (miniMap && zoom != null && !isUpdatingFromUser) {
        const currentZoom = miniMap.getZoom()
        if (Math.abs(currentZoom - zoom) > 0.01) {
          isUpdatingFromCode = true
          miniMap.setZoom(zoom)
          setTimeout(() => { isUpdatingFromCode = false }, 100)
        }
      }
    })

    // Watch for marker changes in store
    watch(() => mapStore.markers, () => { highlight.syncMarkers(miniMap, mapStore) }, { deep: true })

  } catch (err) {
    console.error('[MapView] Failed to initialize:', err)
    loading.value = false
  }
})

// ======== KeepAlive lifecycle ========

onActivated(() => {
  isActive.value = true
  if (!snapshotImgEl) {
    snapshotImgEl = miniMapContainer.value?.querySelector('.map-snapshot-overlay') as HTMLImageElement | null
  }
  const showingSnapshot = !!(cachedCanvasSnapshot && snapshotImgEl)
  if (showingSnapshot) {
    snapshotImgEl!.src = cachedCanvasSnapshot!
    snapshotImgEl!.style.display = ''
  }
  nextTick(() => {
    miniMap?.resize()
    if (showingSnapshot && miniMap) {
      miniMap.once('idle', () => {
        requestAnimationFrame(() => {
          requestAnimationFrame(() => {
            if (snapshotImgEl) snapshotImgEl.style.display = 'none'
          })
        })
      })
      miniMap.triggerRepaint()
    }
    // Handle pending transit marker
    if (miniMap && (window as any)._pendingTransitMarker) {
      const pending = (window as any)._pendingTransitMarker
      delete (window as any)._pendingTransitMarker
      const { lat, lng, zoom, routeCity, routeSlug } = pending
      if (transitStopMarker) { transitStopMarker.remove(); transitStopMarker = null }
      transit.enableLayerVisibility(miniMap)
      miniMap.jumpTo({ center: [lng, lat], zoom: !isNaN(zoom) ? zoom : 16 })
      transit.connectWs()
      if (routeCity && routeSlug) {
        transit.showRouteOnMap(miniMap, routeCity, routeSlug)
      } else {
        Promise.all([import('~/utils/lockOnMarker'), import('maplibre-gl')]).then(([{ createLockOnElement, flashCrosshair }, mod]) => {
          const maplibregl = mod.default || mod
          const el = createLockOnElement({ iconUrl: '/img/bus-stop.png', clickable: true })
          el.addEventListener('click', () => { marker.remove(); transitStopMarker = null })
          const marker = new maplibregl.Marker({ element: el, anchor: 'center' }).setLngLat([lng, lat]).addTo(miniMap)
          transitStopMarker = marker
          setTimeout(() => {
            if (!transitStopMarker) return
            const pt = miniMap.project([lng, lat])
            flashCrosshair(miniMap.getContainer(), Math.round(pt.x), Math.round(pt.y))
          }, 450)
        })
      }
    }
  })

  iot.resumeRefresh()
  mesh.resumeRefresh()

  // Handle transit=1 query param
  if (route.query.transit === '1') {
    const lat = parseFloat(route.query.lat as string)
    const lng = parseFloat(route.query.lng as string)
    if (!isNaN(lat) && !isNaN(lng)) {
      transitEnabled.value = true
      if (miniMap) transit.removeRouteOverlay(miniMap)
      ;(window as any)._pendingTransitMarker = { lat, lng, zoom: parseFloat(route.query.zoom as string), routeCity: route.query.routeCity as string, routeSlug: route.query.routeSlug as string }
      transit.resetDataLoaded()
    }
  } else if (transitEnabled.value && miniMap) {
    transit.connectWs()
  }

  if (authStore.isAuthenticated && mapPresenceEnabled.value) {
    avatar.initializeMapPresence(miniMap)
  }
})

onDeactivated(() => {
  // Save map position immediately before deactivating —
  // the debounced saveMapPosition would be blocked by isActive=false
  if (miniMap) {
    const center = miniMap.getCenter()
    const { setMapCenter, setMapZoom } = useMapState()
    setMapCenter([center.lng, center.lat])
    setMapZoom(miniMap.getZoom())
  }
  isActive.value = false
  iot.pauseRefresh()
  mesh.pauseRefresh()
  transit.disconnectWs()
  trackerWs.disconnect()
  avatar.disconnectMapPresence?.()
})

// React to avatar toggle changes (from preferences or other pages)
watch(mapPresenceEnabled, (enabled) => {
  if (!miniMap || !authStore.isAuthenticated) return
  if (enabled) {
    avatar.initializeMapPresence(miniMap)
  } else {
    avatar.disconnectMapPresence?.()
  }
})

onBeforeUnmount(() => {
  highlight.cleanupMarkers()
  keyboard.detach()
  document.removeEventListener('click', onDocumentClick)
  document.removeEventListener('keydown', onEscapeKey)
  iot.cleanup()
  mesh.pauseRefresh()
  transit.disconnectWs()
  trackerWs.disconnect()
  if (isMapPresenceConnected.value) avatar.disconnectMapPresence()
  miniMap = null
})
</script>

<style scoped>
/* Base styles */
.map-view {
  position: fixed;
  z-index: 40;
}

/* Smooth transition only when animations enabled */
.map-view:not(.no-animation) {
  transition: all 0.3s ease;
  animation: map-reveal 0.4s cubic-bezier(0.16, 1, 0.3, 1) both;
}
@keyframes map-reveal {
  0% { opacity: 0; }
  40% { opacity: 1; }
  100% { opacity: 1; }
}

/* No animation when disabled - instant changes */
.map-view.no-animation {
  transition: none !important;
}

/* Fullscreen mode */
.map-view.fullscreen {
  top: calc(56px + var(--safe-area-inset-top, env(safe-area-inset-top, 0px))); /* Below navbar + safe area */
  left: 0;
  right: 0;
  bottom: var(--safe-area-inset-bottom, env(safe-area-inset-bottom, 0px));
  width: 100vw;
  height: calc(100vh - 56px - var(--safe-area-inset-top, env(safe-area-inset-top, 0px)) - var(--safe-area-inset-bottom, env(safe-area-inset-bottom, 0px)));
  border-radius: 0;
  border: none;
  background: transparent;
  box-shadow: none;
  z-index: 10; /* Below navbar (50) */
}
@media (min-width: 640px) {
  .map-view.fullscreen {
    top: calc(64px + var(--safe-area-inset-top, env(safe-area-inset-top, 0px)));
    height: calc(100vh - 64px - var(--safe-area-inset-top, env(safe-area-inset-top, 0px)) - var(--safe-area-inset-bottom, env(safe-area-inset-bottom, 0px)));
  }
}
@media (min-width: 768px) {
  .map-view.fullscreen {
    top: calc(80px + var(--safe-area-inset-top, env(safe-area-inset-top, 0px)));
    height: calc(100vh - 80px - var(--safe-area-inset-top, env(safe-area-inset-top, 0px)) - var(--safe-area-inset-bottom, env(safe-area-inset-bottom, 0px)));
  }
}

.mini-map-container {
  position: relative;
  width: 100%;
  height: 100%;
}

.mini-map-root {
  width: 100%;
  height: 100%;
  background: #1a1a3e;
}
:root.dark .mini-map-root {
  background: #0d0d1f;
}

.map-snapshot-overlay {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
  z-index: 1;
  pointer-events: none;
}

/* User location marker (MapLibre marker) */
:deep(.user-location-marker) {
  width: 20px;
  height: 20px;
  position: relative;
  pointer-events: none;
}

:deep(.user-location-marker .user-marker-dot) {
  width: 12px;
  height: 12px;
  background: var(--color-secondary);
  border: 2px solid white;
  border-radius: 50%;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.3);
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  z-index: 2;
}

:deep(.user-location-marker .user-marker-pulse) {
  position: absolute;
  top: 50%;
  left: 50%;
  width: 20px;
  height: 20px;
  margin: -10px 0 0 -10px;
  background: color-mix(in srgb, var(--color-primary) 40%, transparent);
  border-radius: 50%;
  animation: pulse 2s infinite;
}

@keyframes pulse {
  0% {
    transform: scale(0.8);
    opacity: 1;
  }
  100% {
    transform: scale(2.5);
    opacity: 0;
  }
}

/* Highlighted item marker (blinking rectangle) */
.highlight-marker {
  position: absolute;
  pointer-events: none;
  z-index: 9;
}

.highlight-box {
  width: 40px;
  height: 40px;
  border: 3px solid var(--color-error);
  border-radius: 4px;
  animation: blink 1s infinite;
  box-shadow: 0 0 10px color-mix(in srgb, var(--color-error) 60%, transparent);
}

@keyframes blink {
  0%, 100% {
    opacity: 1;
    transform: scale(1);
  }
  50% {
    opacity: 0.3;
    transform: scale(1.1);
  }
}

/* Custom geolocation control styles */
:deep(.maplibregl-ctrl-geolocate) {
  background-color: var(--color-surface);
  background-image: none;
  border: 0;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 5px;
  color: var(--color-text);
}

:deep(.maplibregl-ctrl-geolocate:hover) {
  background-color: var(--color-primary-100, #fef9c3);
}

/* Yellow hover for zoom & compass buttons */
:deep(.maplibregl-ctrl-group button:hover) {
  background-color: var(--color-primary-100, #fef9c3);
}
:root.dark :deep(.maplibregl-ctrl-group button:hover) {
  background-color: var(--color-primary-900, #422006);
}
:root.dark :deep(.maplibregl-ctrl-geolocate:hover) {
  background-color: var(--color-primary-900, #422006);
}
/* Dark mode base styles for maplibregl-ctrl-group moved to main.css (global) */

:deep(.maplibregl-ctrl-geolocate-active) {
  color: var(--color-secondary) !important;
  background-color: color-mix(in srgb, var(--color-secondary) 10%, transparent) !important;
}

:deep(.maplibregl-ctrl-geolocate-error) {
  color: var(--color-error) !important;
  background-color: color-mix(in srgb, var(--color-error) 10%, transparent) !important;
}

:deep(.maplibregl-ctrl-geolocate svg) {
  display: block;
}

/* Attribution: collapsed by default, no flash on load */
:deep(.maplibregl-ctrl-attrib.maplibregl-compact) {
  min-height: 20px;
}
:deep(.maplibregl-ctrl-attrib.maplibregl-compact:not(.attrib-ready)) {
  padding: 2px 24px 2px 0;
}
:deep(.maplibregl-ctrl-attrib.maplibregl-compact .maplibregl-ctrl-attrib-inner) {
  display: none;
}
:deep(.maplibregl-ctrl-attrib.maplibregl-compact.attrib-ready.maplibregl-compact-show .maplibregl-ctrl-attrib-inner) {
  display: block;
}

/* Search + Directions FAB wrapper — aligned with feature panel (md:left-0 md:w-96) */
.search-with-directions {
  position: absolute;
  top: 14px;
  left: 20px;
  right: 80px;
  z-index: 1001;
  display: flex;
  align-items: flex-start;
  gap: 10px;
  max-width: 480px;
  pointer-events: none;
}

@media (min-width: 768px) {
  .search-with-directions {
    left: 10px;
    right: auto;
    max-width: calc(24rem - 10px); /* w-96 minus left offset, aligns right edge with panel */
  }
}

.search-with-directions > * {
  pointer-events: auto;
}

.search-with-directions :deep(.map-unified-search) {
  position: static;
  flex: 1;
  min-width: 0;
  max-width: none;
}

.browse-fab,
.directions-fab {
  width: 44px;
  height: 44px;
  border-radius: 50%;
  border: none;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.15);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  transition: all 0.2s;
}

.browse-fab,
.directions-fab {
  background: white;
  color: var(--color-text);
}

:root.dark .browse-fab,
:root.dark .directions-fab {
  background: #262626;
}

.browse-fab:hover,
.directions-fab:hover {
  background: var(--color-primary-100, #fef9c3);
}

:root.dark .browse-fab:hover,
:root.dark .directions-fab:hover {
  background: var(--color-primary-900, #422006);
}

.browse-fab.active,
.directions-fab.active {
  background: var(--color-primary);
  color: var(--color-neutral-900, #171717);
}

/* Desktop: hide search bar when detail panel is open (IoT, establishment, vehicle, etc.) */
@media (min-width: 768px) {
  .search-with-directions.detail-panel-open {
    display: none;
  }
}

/* Mobile */
@media (max-width: 640px) {
  .search-with-directions {
    left: 10px;
    right: 60px;
    max-width: none;
  }

  .browse-fab,
  .directions-fab {
    width: 40px;
    height: 40px;
  }
}

/* Layer Controls — stacked groups like maplibregl-ctrl */
.map-layer-controls {
  position: absolute;
  right: 10px;
  z-index: 1000;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.map-ctrl-group {
  display: flex;
  flex-direction: column;
  border-radius: 4px;
  box-shadow: 0 0 0 2px rgba(0, 0, 0, 0.1);
  background: var(--color-surface);
}
:root.dark .map-ctrl-group {
  box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.08);
  background: rgba(30, 30, 30, 0.75);
  backdrop-filter: blur(8px);
}

.map-ctrl-group > * + * {
  border-top: 1px solid rgba(0, 0, 0, 0.12);
}
:root.dark .map-ctrl-group > * + * {
  border-top: 1px solid rgba(255, 255, 255, 0.08);
}

.opensky-btn {
  width: 44px;
  height: 44px;
  background: transparent;
  border: none;
  border-radius: 0;
  box-shadow: none;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--color-text);
  transition: background 0.2s, color 0.2s;
}

/* Round corners on first/last elements in the group */
.map-ctrl-group > :first-child,
.map-ctrl-group > :first-child > .opensky-btn {
  border-top-left-radius: 4px;
  border-top-right-radius: 4px;
}

.map-ctrl-group > :last-child,
.map-ctrl-group > :last-child > .opensky-btn {
  border-bottom-left-radius: 4px;
  border-bottom-right-radius: 4px;
}

.opensky-btn:hover {
  background: var(--color-primary-100, #fef9c3);
}
:root.dark .opensky-btn:hover {
  background: var(--color-primary-900, #422006);
}

.opensky-btn.active {
  background: var(--color-secondary);
  color: white;
}

/* Layers popover */
.layers-control {
  position: relative;
}

.layers-popover {
  position: absolute;
  right: 48px;
  top: 0;
  width: 190px;
  background: var(--color-surface);
  border-radius: 8px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  overflow: hidden;
  z-index: 1001;
}

.layers-popover-item {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 9px 10px;
  border: none;
  background: none;
  cursor: pointer;
  text-align: left;
  font-size: 13px;
  color: var(--color-text);
  transition: background 0.15s;
}

.layers-popover-item + .layers-popover-item {
  border-top: 1px solid var(--color-border);
}

.layers-popover-item:hover {
  background: var(--color-primary-100, #fef9c3);
}
:root.dark .layers-popover-item:hover {
  background: var(--color-primary-900, #422006);
}

.layers-popover-item.active {
  background: var(--color-secondary-50, #eff6ff);
}
:root.dark .layers-popover-item.active {
  background: rgba(59, 130, 246, 0.15);
}

.layers-popover-label {
  flex: 1;
  white-space: nowrap;
}

/* Tracker popover */
.tracker-control {
  position: relative;
}

.iot-section-toggle {
  display: flex;
  align-items: center;
  gap: 5px;
}

.iot-chevron {
  transition: transform 0.15s;
  flex-shrink: 0;
}

.iot-chevron.expanded {
  transform: rotate(90deg);
}

.tracker-popover {
  position: absolute;
  right: 48px;
  top: 0;
  width: 210px;
  max-height: calc(100vh - 300px);
  overflow-y: auto;
  background: var(--color-surface);
  border-radius: 8px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  z-index: 1001;
}

.tracker-popover-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 10px;
  border-bottom: 1px solid var(--color-border);
}

.tracker-popover-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--color-text);
}

.tracker-eye-btn {
  background: none;
  border: none;
  cursor: pointer;
  padding: 2px;
  color: var(--color-text-muted);
  display: flex;
  align-items: center;
}

.tracker-eye-btn:hover {
  color: var(--color-secondary);
}

.tracker-popover-empty {
  padding: 12px 10px;
  text-align: center;
  color: var(--color-text-muted);
  font-size: 12px;
}

.tracker-popover-item {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 7px 10px;
  border: none;
  background: none;
  cursor: pointer;
  text-align: left;
  font-size: 12px;
  color: var(--color-text);
  transition: background 0.15s;
}

.tracker-popover-item:hover {
  background: var(--color-primary-100, #fef9c3);
}
:root.dark .tracker-popover-item:hover {
  background: var(--color-primary-900, #422006);
}

.tracker-status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.tracker-status-dot.online { background: var(--color-success); }
.tracker-status-dot.offline { background: var(--color-error); }
.tracker-status-dot.unknown { background: var(--color-text-muted); }

.tracker-item-name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tracker-item-speed {
  color: var(--color-text-muted);
  font-size: 11px;
  flex-shrink: 0;
}

.tracker-item-signal-lost {
  color: var(--color-error);
  font-size: 10px;
  flex-shrink: 0;
  opacity: 0.8;
}

/* Map Tools */
.architect-control {
  position: relative;
}

/* Measure distance bar */
.measure-bar {
  position: absolute;
  bottom: 40px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 1001;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 16px;
  background: var(--color-surface);
  border-radius: 24px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.18);
  white-space: nowrap;
}
:root.dark .measure-bar {
  background: rgba(30, 30, 30, 0.9);
  backdrop-filter: blur(8px);
}

.measure-bar-distance {
  font-size: 16px;
  font-weight: 700;
  color: #3b82f6;
}

.measure-bar-segments {
  font-size: 12px;
  color: var(--color-text-muted);
}

.measure-bar-hint {
  font-size: 13px;
  color: var(--color-text-muted);
}

.measure-bar-btn {
  padding: 4px 10px;
  font-size: 12px;
  border: 1px solid var(--color-border);
  border-radius: 6px;
  background: none;
  color: var(--color-text);
  cursor: pointer;
  transition: background 0.15s;
}
.measure-bar-btn:hover:not(:disabled) {
  background: var(--color-primary-100, #fef9c3);
}
:root.dark .measure-bar-btn:hover:not(:disabled) {
  background: var(--color-primary-900, #422006);
}
.measure-bar-btn:disabled {
  opacity: 0.4;
  cursor: default;
}

.measure-bar-btn-close {
  border: none;
  font-size: 18px;
  padding: 2px 6px;
  line-height: 1;
}

/* Sun study panel */
.sun-study-panel {
  position: absolute;
  bottom: 40px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 1001;
  width: 600px;
  max-width: calc(100vw - 20px);
  padding: 12px 16px;
  background: var(--color-surface);
  border-radius: 12px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.18);
}
:root.dark .sun-study-panel {
  background: rgba(30, 30, 30, 0.9);
  backdrop-filter: blur(8px);
}

.sun-study-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  min-width: 0;
}

.sun-study-date {
  flex: 0 0 auto;
  padding: 3px 6px;
  font-size: 13px;
  border: 1px solid var(--color-border);
  border-radius: 6px;
  background: transparent;
  color: var(--color-text);
  cursor: pointer;
}

.sun-study-time-display {
  font-size: 18px;
  font-weight: 700;
  color: #f59e0b;
  flex: 0 0 auto;
}

.sun-study-badges {
  display: flex;
  align-items: center;
  gap: 6px;
  flex: 1;
  min-width: 0;
}

.sun-study-close {
  border: none;
  background: none;
  font-size: 20px;
  color: var(--color-text-muted);
  cursor: pointer;
  padding: 0 4px;
  line-height: 1;
  flex-shrink: 0;
}
.sun-study-close:hover {
  color: var(--color-text);
}

.sun-study-slider-wrap {
  position: relative;
  padding-bottom: 18px;
}

.sun-study-slider {
  width: 100%;
  height: 6px;
  -webkit-appearance: none;
  appearance: none;
  border-radius: 3px;
  background: linear-gradient(to right, #1e3a5f, #3b82f6, #f59e0b, #f59e0b, #3b82f6, #1e3a5f);
  outline: none;
  margin: 4px 0 0;
}
.sun-study-slider::-webkit-slider-thumb {
  -webkit-appearance: none;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: #f59e0b;
  border: 2px solid white;
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.3);
  cursor: grab;
}
.sun-study-slider::-moz-range-thumb {
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: #f59e0b;
  border: 2px solid white;
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.3);
  cursor: grab;
}

.sun-study-ticks {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  height: 16px;
  pointer-events: none;
}
.sun-study-tick {
  position: absolute;
  transform: translateX(-50%);
  font-size: 9px;
  color: var(--color-text-muted);
  opacity: 0.7;
  &::before {
    content: '';
    position: absolute;
    top: -4px;
    left: 50%;
    width: 1px;
    height: 4px;
    background: var(--color-text-muted);
    opacity: 0.4;
  }
}

.sun-study-info {
  display: flex;
  justify-content: space-between;
  margin-top: 4px;
}

.sun-study-stat {
  font-size: 12px;
  color: var(--color-text-muted);
}

.sun-study-badge {
  font-size: 11px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 10px;
  flex-shrink: 0;
  white-space: nowrap;
}

.sun-golden {
  background: rgba(245, 158, 11, 0.2);
  color: #f59e0b;
}

.sun-night {
  background: rgba(30, 58, 95, 0.3);
  color: #60a5fa;
}

.sun-live {
  background: rgba(239, 68, 68, 0.2);
  color: #ef4444;
  cursor: default;
  letter-spacing: 0.05em;
}

.sun-live-off {
  background: rgba(107, 114, 128, 0.15);
  color: var(--color-text-muted);
  cursor: pointer;
  letter-spacing: 0.05em;
  opacity: 0.6;
  &:hover { opacity: 1; }
}

@media (max-width: 640px) {
  .measure-bar {
    left: 10px;
    right: 10px;
    transform: none;
    justify-content: center;
  }
  .sun-study-panel {
    left: 10px;
    right: 10px;
    width: auto;
    transform: none;
  }
  .isochrone-bar {
    left: 10px;
    right: 10px;
    transform: none;
    justify-content: center;
  }
}

/* Isochrone bar */
.isochrone-bar {
  position: absolute;
  bottom: 40px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 1001;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 16px;
  background: var(--color-surface);
  border-radius: 24px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.18);
  white-space: nowrap;
}
:root.dark .isochrone-bar {
  background: rgba(30, 30, 30, 0.9);
  backdrop-filter: blur(8px);
}

.isochrone-bar-legend {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--color-text-muted);
}

.isochrone-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
  margin-left: 4px;
}

.isochrone-mode-btns {
  display: flex;
  gap: 2px;
  border: 1px solid var(--color-border);
  border-radius: 8px;
  overflow: hidden;
}

.isochrone-mode-btn {
  padding: 4px 8px;
  font-size: 14px;
  border: none;
  background: none;
  cursor: pointer;
  transition: background 0.15s;
  line-height: 1;
}
.isochrone-mode-btn:hover {
  background: var(--color-primary-100, #fef9c3);
}
:root.dark .isochrone-mode-btn:hover {
  background: var(--color-primary-900, #422006);
}
.isochrone-mode-btn.active {
  background: var(--color-secondary-50, #eff6ff);
}
:root.dark .isochrone-mode-btn.active {
  background: rgba(59, 130, 246, 0.2);
}

.isochrone-loading {
  font-size: 14px;
  animation: pulse 1s infinite;
}

</style>

<style>
</style>
