<script setup lang="ts">
import { ref } from 'vue';
import { useRouter } from 'vue-router';
import { useAuthStore } from '../stores/auth';
const login = ref('admin');
const password = ref('admin');
const error = ref('');
const auth = useAuthStore();
const router = useRouter();
const submit = async () => {
  error.value = '';
  try { await auth.login(login.value, password.value); router.push('/dashboard'); }
  catch (e: any) { error.value = e.response?.data?.error?.message || 'Login failed'; }
};
</script>
<template>
  <div>
    <h3>Login</h3>
    <input v-model="login" placeholder="login" />
    <input v-model="password" type="password" placeholder="password" />
    <button @click="submit">Sign in</button>
    <p>{{ error }}</p>
  </div>
</template>
