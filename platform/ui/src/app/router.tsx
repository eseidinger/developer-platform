import { createBrowserRouter } from 'react-router-dom'

import { AppLayout } from '@/app/layout'
import { RootPage } from '@/app/root-page'
import { ProjectWorkspace } from '@/features/projects/project-workspace'
import { PlatformAdministrationPage } from '@/features/platform/platform-administration-page'

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
      {
        path: 'platform/administration',
        element: <PlatformAdministrationPage />,
      },
    ],
  },
])

export { router }
