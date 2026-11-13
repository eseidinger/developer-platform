import {
  createContext,
  useContext,
  type ComponentProps,
  type ReactNode,
} from 'react'
import { Button, Modal } from '@mantine/core'

import styles from './dialog.module.css'

type DialogContextValue = {
  open: boolean
  onOpenChange: (open: boolean) => void
}

const DialogContext = createContext<DialogContextValue | null>(null)

function useDialog() {
  const context = useContext(DialogContext)
  if (!context) throw new Error('Dialog content must be inside Dialog')
  return context
}

function Dialog({
  open = false,
  onOpenChange,
  children,
}: {
  open?: boolean
  onOpenChange: (open: boolean) => void
  children: ReactNode
}) {
  return (
    <DialogContext.Provider value={{ open, onOpenChange }}>
      {children}
    </DialogContext.Provider>
  )
}

function DialogContent({
  className,
  children,
  showCloseButton = true,
  finalFocus,
}: {
  className?: string
  children: ReactNode
  showCloseButton?: boolean
  finalFocus?: () => HTMLElement | null | undefined
}) {
  const { open, onOpenChange } = useDialog()
  return (
    <Modal
      opened={open}
      onClose={() => {
        onOpenChange(false)
        if (finalFocus) {
          requestAnimationFrame(() => finalFocus()?.focus())
        }
      }}
      centered
      withCloseButton={showCloseButton}
      closeOnEscape={showCloseButton}
      closeOnClickOutside={showCloseButton}
      returnFocus={!finalFocus}
      onExitTransitionEnd={() => finalFocus?.()?.focus()}
      classNames={{ content: className, body: styles.content }}
    >
      {children}
    </Modal>
  )
}

function DialogHeader({ className, ...props }: ComponentProps<'div'>) {
  return (
    <div
      className={[styles.header, className].filter(Boolean).join(' ')}
      {...props}
    />
  )
}

function DialogFooter({
  className,
  children,
  showCloseButton = false,
  ...props
}: ComponentProps<'div'> & { showCloseButton?: boolean }) {
  const { onOpenChange } = useDialog()
  return (
    <div
      className={[styles.footer, className].filter(Boolean).join(' ')}
      {...props}
    >
      {children}
      {showCloseButton && (
        <Button variant="outline" onClick={() => onOpenChange(false)}>
          Close
        </Button>
      )}
    </div>
  )
}

function DialogTitle({ children }: { children: ReactNode }) {
  return <Modal.Title>{children}</Modal.Title>
}

function DialogDescription({ children }: { children: ReactNode }) {
  return <p className={styles.description}>{children}</p>
}

export {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
}
