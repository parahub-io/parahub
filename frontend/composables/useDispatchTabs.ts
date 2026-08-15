import { Radio, RouteIcon, MapPin } from 'lucide-vue-next'

/**
 * Section tabs shared by the three dispatch pages. Each section is its own
 * route, so the strip is navigation (UiRouteTabs), not in-page state.
 */
export function useDispatchTabs() {
  const { t } = useI18n()
  const localePath = useLocalePath()

  return computed(() => [
    { label: t('dispatch.assignments'), to: localePath('/dispatch/assignments'), icon: Radio },
    { label: t('transit_manage.routes'), to: localePath('/dispatch/routes'), icon: RouteIcon },
    { label: t('transit_manage.stops'), to: localePath('/dispatch/stops'), icon: MapPin },
  ])
}
