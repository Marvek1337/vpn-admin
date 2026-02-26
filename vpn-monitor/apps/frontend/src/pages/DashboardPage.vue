<script setup lang="ts">
import { onMounted } from 'vue';
import { useServersStore } from '../stores/servers';
const servers = useServersStore();
onMounted(() => servers.fetchAll());
</script>
<template>
  <div>
    <h3>Dashboard</h3>
    <table>
      <tr><th>Name</th><th>Host</th><th>SSH</th><th>WG</th><th>CPU</th></tr>
      <tr v-for="s in servers.items" :key="s.id"><td>{{ s.name }}</td><td>{{ s.host }}</td><td>{{ s.lastSshOk }}</td><td>{{ s.lastWgOk }}</td><td>{{ s.latestMetric?.cpuPercent }}</td></tr>
    </table>
  </div>
</template>
