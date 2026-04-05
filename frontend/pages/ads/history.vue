<script setup lang="ts">
// History is now integrated into the Feed tab
definePageMeta({ middleware: 'auth' })
const localePath = useLocalePath()
navigateTo(localePath('/ads'), { replace: true })
</script>
