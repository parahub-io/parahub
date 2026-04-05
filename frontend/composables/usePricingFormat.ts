
export interface PricingOption {
  type?: string
  amount?: number | string
  currency?: string
  unit?: string
  note?: string
  converted_from?: string
}

export const usePricingFormat = () => {
  const { t, locale } = useI18n()

  const formatPricingOption = (opt: PricingOption | null | undefined): string => {
    if (!opt) return t('market.pricing.free')
    if (opt.type === 'free') return t('market.pricing.free')

    const amount = parseFloat(String(opt.amount)) || 0
    const currency = opt.currency || 'EUR'

    // Zero amount = negotiable price, show note or "Price negotiable"
    if (amount === 0) {
      if (opt.note) return opt.note
      return t('market.pricing.negotiable')
    }

    // Locale-aware number formatting
    const formattedAmount = currency === 'BTC'
      ? amount.toFixed(8)
      : amount.toLocaleString(locale.value, { minimumFractionDigits: 2, maximumFractionDigits: 2 })

    let priceStr = opt.unit
      ? `${formattedAmount} ${currency}/${opt.unit}`
      : `${formattedAmount} ${currency}`

    if (opt.converted_from) {
      priceStr += ` (${t('market.pricing.converted_from', { currency: opt.converted_from })})`
    } else if (opt.note) {
      priceStr += ` (${opt.note})`
    }

    return priceStr
  }

  return { formatPricingOption }
}
