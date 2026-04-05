export default defineNuxtPlugin((nuxtApp) => {
  // Provide a dedicated API fetch that always includes credentials
  const apiFetch = $fetch.create({
    credentials: 'include'
  })
  
  return {
    provide: {
      apiFetch
    }
  }
})