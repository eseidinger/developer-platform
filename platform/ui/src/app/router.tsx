import { createBrowserRouter } from 'react-router-dom'

import { AppLayout } from '@/app/layout'
import { RootPage } from '@/app/root-page'
import { ProjectWorkspace } from '@/features/projects/project-workspace'
import { PlatformAdministrationPage } from '@/features/platform/platform-administration-page'
import { ApplicationAccessPage } from '@/features/access/application-access-page'

import { StoresPage } from '@/features/stores/stores-page'
import { AiAssistancePage } from '@/features/ai/ai-assistance-page'

const router = createBrowserRouter([
  {
    path: '/',
    element: <AppLayout />,
    children: [
      {
        index: true,
        element: <RootPage />,
      },
      {
        path: 'projects/:name',
        element: <ProjectWorkspace />,
      },
      { path: 'projects/:name/stores', element: <StoresPage /> },
      { path: 'store-access', element: <StoresPage /> },
      { path: 'projects/:name/ai', element: <AiAssistancePage /> },
      {
        path: 'projects/:name/application-access',
        element: <ApplicationAccessPage />,
      },
      {
        path: 'platform/administration',
        element: <PlatformAdministrationPage />,
      },
    ],
  },
])

export { router }
