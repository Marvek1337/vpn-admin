<script setup lang="ts">
import { onMounted } from 'vue';
import { useRoute } from 'vue-router';
import { useMetricsStore } from '../stores/metrics';
import { useWgClientsStore } from '../stores/wgClients';
const route = useRoute();
const metrics = useMetricsStore();
const wg = useWgClientsStore();
onMounted(() => { metrics.fetch(route.params.id as string); wg.fetch(route.params.id as string); });
</script>
<template>
  <div>
    <h3>Server {{ route.params.id }}</h3>
    <p>Metrics points: {{ metrics.series.length }}</p>
    <p>WG clients: {{ wg.clients.length }}</p>
  </div>
</template>
