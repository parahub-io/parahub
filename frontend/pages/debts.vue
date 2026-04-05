<script setup>
definePageMeta({
  middleware: 'auth'
})

const localePath = useLocalePath()
await navigateTo(localePath('/wallet/debts'), { redirectCode: 301, replace: true })
</script>
