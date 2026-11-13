import {
  createTheme,
  MantineProvider,
  type MantineProviderProps,
} from '@mantine/core'

// Shared light-mode design tokens for the operational portal.
const portalTheme = createTheme({
  fontFamily: 'Geist Variable, sans-serif',
  headings: { fontFamily: 'Geist Variable, sans-serif' },
  primaryColor: 'indigo',
  primaryShade: 7,
  defaultRadius: 'md',
})

export function PortalThemeProvider({
  children,
}: Pick<MantineProviderProps, 'children'>) {
  return (
    <MantineProvider
      theme={portalTheme}
      forceColorScheme="light"
      env={import.meta.env.MODE === 'test' ? 'test' : undefined}
    >
      {children}
    </MantineProvider>
  )
}
