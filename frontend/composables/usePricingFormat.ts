
export interface PricingOption {
  type?: string
  amount?: number | string
  currency?: string
  unit?: string
  note?: string
  converted_from?: string
}

// Fallback symbols for the rare currencies Intl can't resolve to a glyph
// (Intl already handles EUR→€, USD→$, GBP→£, RUB→₽… on its own).
const CURRENCY_SYMBOLS: Record<string, string> = {
  EUR: '€', USD: '$', GBP: '£', RUB: '₽', UAH: '₴', PLN: 'zł', CHF: 'CHF',
}

export const usePricingFormat = () => {
  const { t, locale } = useI18n()

  // Locale-aware money string: currency symbol (not code) + grouped digits,
  // and trailing ",00" dropped for whole amounts ("14 500 €", not "14 500,00 EUR").
  const formatAmount = (amount: number, currency: string): string => {
    if (currency === 'BTC') {
      return `₿${amount.toFixed(8).replace(/\.?0+$/, '')}`
    }
    try {
      return new Intl.NumberFormat(locale.value, {
        style: 'currency',
        currency,
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
        // Drops the fraction entirely when the amount is a whole number.
        trailingZeroDisplay: 'stripIfInteger',
      } as Intl.NumberFormatOptions).format(amount)
    } catch {
      // Currency is not a valid ISO 4217 code — fall back to symbol + amount.
      const n = amount.toLocaleString(locale.value, { minimumFractionDigits: 0, maximumFractionDigits: 2 })
      return `${n} ${CURRENCY_SYMBOLS[currency] || currency}`
    }
  }

  // `withNote: false` drops the trailing "(note)" tail — for dense list cards
  // where every pixel counts. The roomy detail page keeps it (default true).
  // The conversion hint and the zero-amount/negotiable note always stay: there
  // the note IS the price, not a descriptive aside.
  const formatPricingOption = (
    opt: PricingOption | null | undefined,
    { withNote = true }: { withNote?: boolean } = {},
  ): string => {
    if (!opt) return t('market.pricing.free')
    if (opt.type === 'free') return t('market.pricing.free')

    const amount = parseFloat(String(opt.amount)) || 0
    const currency = opt.currency || 'EUR'

    // Zero amount = negotiable price, show note or "Price negotiable"
    if (amount === 0) {
      if (opt.note) return opt.note
      return t('market.pricing.negotiable')
    }

    let priceStr = formatAmount(amount, currency)

    // Translate the unit ("month" → "месяц"); fall back to the raw value for
    // free-text units the user typed manually.
    if (opt.unit) {
      priceStr += `/${t(`market.pricing.units.${opt.unit}`, opt.unit)}`
    }

    if (opt.converted_from) {
      priceStr += ` (${t('market.pricing.converted_from', { currency: opt.converted_from })})`
    } else if (opt.note && withNote) {
      priceStr += ` (${opt.note})`
    }

    return priceStr
  }

  // Short label for the offer kind, used to disambiguate stacked options
  // (a listing can carry both a sale and a rent price). Free needs no label —
  // formatPricingOption already renders "Free".
  const pricingTypeLabel = (opt: PricingOption | null | undefined): string => {
    if (opt?.type === 'rent') return t('market.pricing.rent')
    if (opt?.type === 'sale') return t('market.pricing.sale')
    return ''
  }

  // Money only — the amount with no "/unit" or "(note)" tail. Lets a stacked
  // tier list put the price in its own right-aligned column instead of cramming
  // amount + period + note into one mixed-language run.
  const priceAmount = (opt: PricingOption | null | undefined): string => {
    if (!opt || opt.type === 'free') return t('market.pricing.free')
    const amount = parseFloat(String(opt.amount)) || 0
    if (amount === 0) return opt.note || t('market.pricing.negotiable')
    return formatAmount(amount, opt.currency || 'EUR')
  }

  // The rental period / sale unit as a standalone label for the left column
  // ("hour" → "час"; free-text units fall back to the raw value, then to the
  // owner's note). Deliberately one descriptor, not unit + note concatenated —
  // pairing an English unit with a Portuguese note is what made the old line
  // read as bilingual soup.
  const pricingPeriod = (opt: PricingOption | null | undefined): string => {
    if (opt?.unit) return t(`market.pricing.units.${opt.unit}`, opt.unit)
    return opt?.note || ''
  }

  return { formatPricingOption, pricingTypeLabel, priceAmount, pricingPeriod }
}
