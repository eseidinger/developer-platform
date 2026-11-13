import {
  render as testingLibraryRender,
  type RenderOptions,
} from '@testing-library/react'
import type { ReactElement } from 'react'

import { PortalThemeProvider } from '@/app/theme'

export * from '@testing-library/react'

export function render(ui: ReactElement, options?: RenderOptions) {
  return testingLibraryRender(ui, {
    wrapper: PortalThemeProvider,
    ...options,
  })
}
