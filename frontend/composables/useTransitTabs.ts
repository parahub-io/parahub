import { Bus, Car } from 'lucide-vue-next'

/**
 * Section tabs shared by the transit landing and the rideshare page.
 * Both stay separate routes — the strip is navigation, not in-page state.
 */
export function useTransitTabs() {
  const { t } = useI18n()
  const localePath = useLocalePath()

  return computed(() => [
    { label: t('transit.title'), to: localePath('/transit'), icon: Bus },
    { label: t('rides.title'), to: localePath('/transit/rides'), icon: Car },
  ])
}
