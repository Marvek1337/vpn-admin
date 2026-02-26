import { createRouter, createWebHistory } from 'vue-router';
import LoginPage from '../pages/LoginPage.vue';
import DashboardPage from '../pages/DashboardPage.vue';
import ServersPage from '../pages/ServersPage.vue';
import ServerDetailsPage from '../pages/ServerDetailsPage.vue';

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', component: LoginPage },
    { path: '/dashboard', component: DashboardPage },
    { path: '/servers', component: ServersPage },
    { path: '/servers/:id', component: ServerDetailsPage },
    { path: '/:pathMatch(.*)*', redirect: '/dashboard' },
  ],
});

router.beforeEach((to) => {
  const token = localStorage.getItem('accessToken');
  if (to.path !== '/login' && !token) return '/login';
  if (to.path === '/login' && token) return '/dashboard';
});

export default router;
