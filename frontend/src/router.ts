import { createRouter, createWebHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'

const routes: RouteRecordRaw[] = [
  { path: '/login', component: () => import('./views/LoginView.vue'), meta: { public: true, title: '登录' } },
  { path: '/', redirect: '/query' },
  { path: '/query', component: () => import('./views/QueryView.vue'), meta: { title: '智能问答' } },
  { path: '/upload', component: () => import('./views/UploadView.vue'), meta: { title: '文档上传' } },
  { path: '/documents', component: () => import('./views/DocumentView.vue'), meta: { title: '文档管理' } },
  { path: '/permissions', component: () => import('./views/PermissionView.vue'), meta: { title: '权限管理', adminOnly: true } },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

// 路由守卫
router.beforeEach((to, from, next) => {
  const token = localStorage.getItem('access_token')
  const userInfo = JSON.parse(localStorage.getItem('user_info') || '{}')

  if (to.meta.public) {
    // 公开页面（登录页）
    if (token) {
      next('/query')
    } else {
      next()
    }
    return
  }

  // 需要登录
  if (!token) {
    next('/login')
    return
  }

  // 需要管理员权限
  if (to.meta.adminOnly && userInfo.role !== 'admin') {
    next('/query')
    return
  }

  next()
})

export default router
