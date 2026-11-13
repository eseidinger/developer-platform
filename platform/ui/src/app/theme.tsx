import {
  createTheme,
  MantineProvider,
  type MantineProviderProps,
} from '@mantine/core'

// Keep the portal's light, neutral appearance while components migrate.
const portalTheme = createTheme({
  fontFamily: 'Geist Variable, sans-serif',
  primaryColor: 'gray',
  primaryShade: 9,
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
