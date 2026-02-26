<script setup lang="ts">
import { onMounted } from 'vue';
import { useServersStore } from '../stores/servers';
const servers = useServersStore();
onMounted(() => servers.fetchAll());
</script>
<template><div><h3>Servers</h3><ul><li v-for="s in servers.items" :key="s.id">{{ s.name }} - {{ s.host }}</li></ul></div></template>
