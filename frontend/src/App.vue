<script setup lang="ts">
import { onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  Button,
  DesktopShell,
  FrappeUIProvider,
  Sidebar,
  SidebarHeader,
  SidebarItem,
  SidebarLabel,
  useColorScheme,
} from 'frappe-ui'
import { useTerminal } from './composables/useTerminal'

const route = useRoute()
const router = useRouter()
const { resolvedColorScheme, toggleColorScheme } = useColorScheme()
const { terminals, selected, load, select } = useTerminal()

onMounted(load)

const nav = [
  { label: 'Dashboard', to: '/', icon: 'lucide-layout-dashboard' },
  { label: '3D Yard', to: '/yard', icon: 'lucide-boxes' },
  { label: 'Gate', to: '/gate', icon: 'lucide-door-open' },
  { label: 'Appointments', to: '/appointments', icon: 'lucide-calendar-clock' },
  { label: 'My Moves', to: '/ops', icon: 'lucide-forklift' },
]
const isActive = (to: string) => (to === '/' ? route.path === '/' : route.path.startsWith(to))
</script>

<template>
  <FrappeUIProvider>
    <div v-if="route.meta.bare" class="min-h-screen bg-surface-base text-ink-gray-8">
      <RouterView />
    </div>
    <div v-else class="h-screen bg-surface-base text-ink-gray-8">
      <DesktopShell>
        <template #sidebar>
          <Sidebar class="border-r" :collapsible="false" width="14rem">
            <SidebarHeader title="TOS Next" subtitle="Terminal Operating System" />

            <div class="px-3 pb-2">
              <label class="mb-1 block text-xs text-ink-gray-5" for="terminal">Terminal</label>
              <select
                id="terminal"
                class="w-full rounded-4 border border-outline-gray-2 bg-surface-white px-2 py-1.5 text-sm text-ink-gray-8"
                :value="selected"
                @change="select(($event.target as HTMLSelectElement).value)"
              >
                <option v-for="t in terminals" :key="t.name" :value="t.name">{{ t.terminal_name }}</option>
              </select>
            </div>

            <div class="flex-1 space-y-0.5 overflow-y-auto px-2 pb-2">
              <SidebarLabel class="px-2">Operations</SidebarLabel>
              <SidebarItem v-for="item in nav" :key="item.to" :active="isActive(item.to)" @click="router.push(item.to)">
                <span class="flex items-center gap-2">
                  <span :class="[item.icon, 'size-4']" aria-hidden="true" />
                  {{ item.label }}
                </span>
              </SidebarItem>
            </div>

            <div class="flex items-center gap-2 border-t border-outline-gray-1 p-3">
              <Button
                :icon="resolvedColorScheme === 'dark' ? 'lucide-sun' : 'lucide-moon'"
                :tooltip="resolvedColorScheme === 'dark' ? 'Light mode' : 'Dark mode'"
                aria-label="Switch light and dark mode"
                @click="toggleColorScheme"
              />
              <Button icon-left="lucide-layout-grid" label="Desk" href="/desk" />
            </div>
          </Sidebar>
        </template>

        <RouterView />
      </DesktopShell>
    </div>
  </FrappeUIProvider>
</template>
