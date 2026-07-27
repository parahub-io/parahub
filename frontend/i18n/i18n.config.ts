export default defineI18nConfig(() => ({
  legacy: false,
  fallbackLocale: 'en',
  pluralRules: {
    // Russian message form order: 2 forms = [one, many], 3 forms = [one, few, many],
    // 4 forms = [zero, one, few, many]. "one" also covers 21, 31... (but not 11).
    ru: (choice: number, choicesLength: number): number => {
      const teen = choice % 100 > 10 && choice % 100 < 20
      const one = !teen && choice % 10 === 1
      const few = !teen && choice % 10 >= 2 && choice % 10 <= 4
      if (choicesLength === 2) return one ? 0 : 1
      if (choicesLength === 3) return one ? 0 : few ? 1 : 2
      if (choice === 0) return 0
      return one ? 1 : few ? 2 : 3
    },
  },
}))
