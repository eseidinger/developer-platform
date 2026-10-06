import { createBrowserRouter } from 'react-router-dom'

import { AppLayout } from '@/app/layout'
import { RootPage } from '@/app/root-page'

const router = createBrowserRouter([
  {
    path: '/',
    element: <AppLayout />,
    children: [
      {
        index: true,
        element: <RootPage />,
      },
    ],
  },
])

export { router }
