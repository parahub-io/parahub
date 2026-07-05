<template>
  <div class="webgl-error-overlay" role="alert">
    <div class="webgl-error-card">
      <AlertTriangle class="webgl-error-icon" aria-hidden="true" />
      <h2 class="webgl-error-title">{{ $t('map.webgl_error.title') }}</h2>
      <p class="webgl-error-desc">{{ $t('map.webgl_error.description') }}</p>
      <p class="webgl-error-fix-intro">{{ $t('map.webgl_error.fix_intro') }}</p>
      <ol class="webgl-error-steps">
        <li>
          <i18n-t keypath="map.webgl_error.fix_settings" tag="span">
            <template #settings>
              <code>chrome://settings/system</code>
            </template>
          </i18n-t>
        </li>
        <li>
          <i18n-t keypath="map.webgl_error.fix_check" tag="span">
            <template #gpu>
              <code>chrome://gpu</code>
            </template>
          </i18n-t>
        </li>
      </ol>
      <button @click="$emit('retry')" class="webgl-error-retry">{{ $t('map.webgl_error.retry') }}</button>
    </div>
  </div>
</template>

<script setup lang="ts">
/** Full-map overlay shown when the WebGL context cannot be created. */
import { AlertTriangle } from 'lucide-vue-next'

defineEmits<{ (e: 'retry'): void }>()
</script>

<style scoped>
.webgl-error-overlay {
  position: absolute;
  inset: 0;
  z-index: 1100;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 1.5rem;
  background: rgba(13, 13, 31, 0.78);
  backdrop-filter: blur(4px);
}
.webgl-error-card {
  max-width: 32rem;
  width: 100%;
  padding: 1.75rem;
  border-radius: 0.75rem;
  background: rgb(255 255 255);
  color: rgb(23 23 23);
  box-shadow: 0 20px 50px -12px rgba(0,0,0,0.45);
  border: 1px solid rgb(229 229 229);
}
:root.dark .webgl-error-card {
  background: rgb(38 38 38);
  color: rgb(245 245 245);
  border-color: rgb(64 64 64);
}
.webgl-error-icon {
  width: 2rem;
  height: 2rem;
  color: rgb(234 88 12);
  margin-bottom: 0.5rem;
}
.webgl-error-title {
  font-size: 1.25rem;
  font-weight: 600;
  margin-bottom: 0.5rem;
}
.webgl-error-desc {
  font-size: 0.95rem;
  line-height: 1.5;
  margin-bottom: 1rem;
  color: rgb(82 82 82);
}
:root.dark .webgl-error-desc {
  color: rgb(212 212 212);
}
.webgl-error-fix-intro {
  font-weight: 500;
  margin-bottom: 0.5rem;
}
.webgl-error-steps {
  list-style: decimal;
  padding-left: 1.25rem;
  margin-bottom: 1.25rem;
  font-size: 0.9rem;
  line-height: 1.6;
}
.webgl-error-steps code {
  padding: 0.1rem 0.35rem;
  border-radius: 0.25rem;
  background: rgb(245 245 245);
  font-size: 0.85em;
}
:root.dark .webgl-error-steps code {
  background: rgb(64 64 64);
}
.webgl-error-retry {
  padding: 0.5rem 1rem;
  border-radius: 0.5rem;
  background: rgb(234 88 12);
  color: white;
  font-weight: 500;
  cursor: pointer;
  border: 0;
  transition: background 0.15s;
}
.webgl-error-retry:hover {
  background: rgb(194 65 12);
}
</style>
