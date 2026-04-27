import { createRouter, createWebHistory } from "vue-router";

import AdminDocumentsPage from "./pages/AdminDocumentsPage.vue";
import ChatPage from "./pages/ChatPage.vue";
import DocumentViewerPage from "./pages/DocumentViewerPage.vue";

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: "/",
      name: "chat",
      component: ChatPage,
    },
    {
      path: "/documents",
      name: "documents",
      component: DocumentViewerPage,
    },
    {
      path: "/admin/documents",
      name: "admin-documents",
      component: AdminDocumentsPage,
    },
  ],
});

export default router;

