/**
 * Canonical extraction of a human-readable message from a failed $fetch call.
 *
 * Backend endpoints progressively adopt LocalizedHttpError (parahub/errors.py),
 * which sends `{ detail, code }` — `code` is a stable machine-readable slug
 * meant to be mapped through a domain i18n namespace (established pattern:
 * `wot.error_codes.*`, see UserVerifyModal). This composable generalizes that
 * mapping and the fallback chain so call sites stop hand-rolling
 * `error?.data?.detail || $t('...')` variants.
 *
 * Usage:
 *   const { apiErrorMessage } = useApiError()
 *   catch (e) { showError(apiErrorMessage(e, 'market.error_codes', t('market.notifications.status_error'))) }
 */
export function useApiError() {
  const { t, te } = useI18n()

  const apiErrorMessage = (error: any, codeNamespace?: string, fallback?: string): string => {
    const data = error?.data ?? error?.response?._data ?? {}
    if (codeNamespace && data.code && te(`${codeNamespace}.${data.code}`)) {
      return t(`${codeNamespace}.${data.code}`)
    }
    // detail = ninja HttpError / LocalizedHttpError; message/error = legacy formats
    return data.detail || data.message || data.error || fallback || t('error_server')
  }

  return { apiErrorMessage }
}
