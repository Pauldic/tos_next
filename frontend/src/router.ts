import { createRouter, createWebHistory } from 'vue-router'

export const router = createRouter({
  // The same path as `frontendRoute` in vite.config.ts
  history: createWebHistory('/tos'),
  routes: [
    { path: '/', name: 'dashboard', component: () => import('./pages/Dashboard.vue'), meta: { title: 'Dashboard' } },
    { path: '/yard', name: 'yard', component: () => import('./pages/Yard.vue'), meta: { title: '3D Yard' } },
    { path: '/gate', name: 'gate', component: () => import('./pages/Gate.vue'), meta: { title: 'Gate' } },
    { path: '/appointments', name: 'appointments', component: () => import('./pages/Appointments.vue'), meta: { title: 'Appointments' } },
    { path: '/ops', name: 'ops', component: () => import('./pages/Ops.vue'), meta: { title: 'My moves', bare: true } },
    { path: '/portal', name: 'portal', component: () => import('./pages/Portal.vue'), meta: { title: 'Carrier portal', bare: true } },
    { path: '/portal/fleet', name: 'portal-fleet', component: () => import('./pages/PortalFleet.vue'), meta: { title: 'My fleet', bare: true } },
    { path: '/:path(.*)*', component: () => import('./pages/NotFound.vue') },
  ],
})

// A signed-out visitor goes to the Frappe login page and comes back here afterwards.
// Only a production build has boot data, so the dev server skips this.
router.beforeEach((to) => {
  const user = (window as any).user
  if (user === 'Guest') {
    window.location.href = `/login?redirect-to=${encodeURIComponent('/tos' + to.fullPath)}`
    return false
  }
})
