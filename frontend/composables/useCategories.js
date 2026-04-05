/**
 * Composable for working with Parahub category tree
 * Uses content-addressed static JSON files for instant loading with lazy loading per language
 */
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { CATEGORY_VERSIONS } from '~/data/categories-versions.js'

// Memory cache for loaded categories (shared across all instances)
const categoryCache = ref({})
const loading = ref(false)
const error = ref(null)

// Cache TTL - can be longer since we use content-addressed files
const CACHE_TTL = 7 * 24 * 60 * 60 * 1000 // 7 days

export const useCategories = () => {
  // Get language from i18n or default to 'en'
  const { locale } = useI18n()
  const currentLang = computed(() => locale.value || 'en')

  /**
   * Load categories for a specific language with caching
   * Uses memory cache -> localStorage -> content-addressed static JSON file (lazy load)
   */
  const loadCategoriesForLang = async (lang = 'en') => {
    // Check memory cache first (fastest)
    if (categoryCache.value[lang]) {
      return categoryCache.value[lang]
    }

    loading.value = true
    error.value = null

    try {
      // Get content hash for this language
      const version = CATEGORY_VERSIONS[lang]
      if (!version) {
        throw new Error(`No version found for language: ${lang}`)
      }

      // Check localStorage cache (keyed by content hash) — skip on SSR
      const cacheKey = `parahub_categories_${lang}_${version}`
      const hasLocalStorage = typeof localStorage !== 'undefined'

      if (hasLocalStorage) {
        const cached = localStorage.getItem(cacheKey)
        if (cached) {
          try {
            const { data, timestamp } = JSON.parse(cached)
            if (Date.now() - timestamp < CACHE_TTL) {
              categoryCache.value[lang] = data
              return data
            }
          } catch (e) {
            localStorage.removeItem(cacheKey)
          }
        }
      }

      // Cache miss or expired - load from content-addressed static file
      const url = `/data/categories.${lang}.${version}.json`
      const response = await $fetch(url)

      // Store in memory cache
      categoryCache.value[lang] = response

      // Store in localStorage cache (skip on SSR)
      if (hasLocalStorage) {
        try {
          localStorage.setItem(cacheKey, JSON.stringify({
            data: response,
            timestamp: Date.now()
          }))
        } catch (e) {
          console.warn('localStorage full, skipping cache:', e)
        }
      }

      return response
    } catch (err) {
      error.value = err.message
      console.error(`Failed to load categories for ${lang}:`, err)
      return []
    } finally {
      loading.value = false
    }
  }

  /**
   * Deep-filter category tree by domain (market/directory/events).
   * Keeps a node if its applicable_to includes the domain OR any descendant matches.
   * Prunes non-matching branches to show only relevant categories.
   */
  const filterTreeByDomain = (tree, domain) => {
    if (!domain) return tree

    const filterNode = (node) => {
      const matches = node.applicable_to && node.applicable_to.includes(domain)
      const filteredChildren = (node.children || [])
        .map(child => filterNode(child))
        .filter(child => child !== null)

      if (matches || filteredChildren.length > 0) {
        return { ...node, children: filteredChildren }
      }
      return null
    }

    return tree.map(node => filterNode(node)).filter(node => node !== null)
  }

  /**
   * Fetch hierarchical category tree (static files)
   * @param {Object} params - { lang, domain }
   * @param {string} params.domain - Filter by domain: 'market', 'directory', 'events'
   */
  const fetchCategoryTree = async (params = {}) => {
    const lang = params.lang || currentLang.value
    const tree = await loadCategoriesForLang(lang)
    return filterTreeByDomain(tree, params.domain)
  }

  /**
   * Fetch flat list of categories with filters
   * @param {Object} params - { lang, domain, parent, search }
   */
  const fetchCategories = async (params = {}) => {
    const lang = params.lang || currentLang.value
    let tree = await loadCategoriesForLang(lang)
    tree = filterTreeByDomain(tree, params.domain)

    // Flatten tree to array
    const flattenTree = (nodes) => {
      const result = []
      for (const node of nodes) {
        result.push(node)
        if (node.children && node.children.length > 0) {
          result.push(...flattenTree(node.children))
        }
      }
      return result
    }

    let categories = flattenTree(tree)

    // Apply filters
    if (params.parent !== undefined) {
      if (params.parent === null || params.parent === '') {
        // Root categories only
        categories = tree
      } else {
        // Children of specific parent
        const findChildren = (nodes, parentId) => {
          for (const node of nodes) {
            if (node.id === parentId) {
              return node.children || []
            }
            if (node.children) {
              const found = findChildren(node.children, parentId)
              if (found) return found
            }
          }
          return []
        }
        categories = findChildren(tree, params.parent)
      }
    }

    // Search filter
    if (params.search) {
      const query = params.search.toLowerCase()
      categories = categories.filter(cat =>
        cat.name.toLowerCase().includes(query) ||
        cat.slug.toLowerCase().includes(query)
      )
    }

    return categories
  }

  /**
   * Fetch single category by slug
   */
  const fetchCategory = async (slug, lang = null) => {
    const targetLang = lang || currentLang.value
    const tree = await loadCategoriesForLang(targetLang)

    // Find category in tree recursively
    const findCategory = (nodes, targetSlug) => {
      for (const node of nodes) {
        if (node.slug === targetSlug) {
          return node
        }
        if (node.children) {
          const found = findCategory(node.children, targetSlug)
          if (found) return found
        }
      }
      return null
    }

    return findCategory(tree, slug)
  }

  /**
   * Get breadcrumbs for a category (path from root to category)
   */
  const fetchBreadcrumbs = async (slug, lang = null) => {
    const targetLang = lang || currentLang.value
    const tree = await loadCategoriesForLang(targetLang)

    // Find path to category
    const findPath = (nodes, targetSlug, path = []) => {
      for (const node of nodes) {
        const currentPath = [...path, { id: node.id, name: node.name, slug: node.slug, icon: node.icon }]

        if (node.slug === targetSlug) {
          return currentPath
        }

        if (node.children) {
          const found = findPath(node.children, targetSlug, currentPath)
          if (found) return found
        }
      }
      return null
    }

    return findPath(tree, slug) || []
  }

  /**
   * Get root categories (top-level only)
   */
  const fetchRootCategories = async (lang = null) => {
    const targetLang = lang || currentLang.value
    return await loadCategoriesForLang(targetLang)
  }

  /**
   * Get children of a specific category
   */
  const fetchChildren = async (parentSlug, lang = null) => {
    const targetLang = lang || currentLang.value
    const parent = await fetchCategory(parentSlug, targetLang)
    return parent?.children || []
  }

  /**
   * Search categories by name (client-side)
   * @param {string} query - Search query
   * @param {string} lang - Language code
   * @param {string} domain - Filter by domain: 'market', 'directory', 'events'
   */
  const searchCategories = async (query, lang = null, domain = null) => {
    if (!query || query.trim().length === 0) {
      return []
    }

    const results = await fetchCategories({
      search: query.trim(),
      lang: lang || currentLang.value,
      domain
    })

    // Add breadcrumbs for search results
    let tree = await loadCategoriesForLang(lang || currentLang.value)
    tree = filterTreeByDomain(tree, domain)

    return results.map(cat => {
      // Calculate breadcrumbs for this category
      const findPath = (nodes, targetId, path = []) => {
        for (const node of nodes) {
          const currentPath = [...path, { id: node.id, name: node.name, slug: node.slug, icon: node.icon }]

          if (node.id === targetId) {
            return currentPath
          }

          if (node.children) {
            const found = findPath(node.children, targetId, currentPath)
            if (found) return found
          }
        }
        return null
      }

      return {
        ...cat,
        breadcrumbs: findPath(tree, cat.id) || []
      }
    })
  }

  /**
   * Get flat category options for select dropdown
   * Returns array of { value: slug, label: name, icon: icon }
   */
  const getCategoryOptions = async (lang = null) => {
    const categories = await fetchCategories({ lang })
    return categories.map(cat => ({
      value: cat.slug,
      label: cat.name,
      icon: cat.icon,
      id: cat.id
    }))
  }

  /**
   * Build nested category tree for UI components
   * Recursive helper for rendering hierarchical categories
   */
  const buildNestedOptions = (tree = null, level = 0) => {
    if (!tree) return []

    const options = []
    tree.forEach(cat => {
      options.push({
        value: cat.slug,
        label: '  '.repeat(level) + (cat.icon || '') + ' ' + cat.name,
        icon: cat.icon,
        id: cat.id,
        level: level
      })

      if (cat.children && cat.children.length > 0) {
        options.push(...buildNestedOptions(cat.children, level + 1))
      }
    })

    return options
  }

  /**
   * Clear category cache (useful for development/testing)
   * Clears both memory cache and all localStorage entries
   */
  const clearCache = () => {
    categoryCache.value = {}
    if (typeof localStorage !== 'undefined') {
      const keys = Object.keys(localStorage)
      keys.forEach(key => {
        if (key.startsWith('parahub_categories_')) {
          localStorage.removeItem(key)
        }
      })
    }
  }

  return {
    // State
    loading,
    error,
    currentLang,

    // Methods
    fetchCategories,
    fetchCategoryTree,
    fetchCategory,
    fetchBreadcrumbs,
    fetchRootCategories,
    fetchChildren,
    searchCategories,
    getCategoryOptions,
    buildNestedOptions,
    loadCategoriesForLang,
    clearCache
  }
}
