import { createBrowserRouter } from 'react-router-dom'

import { AppLayout } from '@/app/layout'
import { HomePage } from '@/features/home/home-page'

const router = createBrowserRouter([
  {
    path: '/',
    element: <AppLayout />,
    children: [
      {
        index: true,
        element: <HomePage />,
      },
    ],
  },
])

export { router }
