export function submitConsoleLaunch(url: string, launch: string) {
  const form = document.createElement('form')
  // noreferrer makes cross-origin POSTs send Origin: null, which the gateway
  // rejects. noopener preserves tab isolation and the portal Origin header.
  form.method = 'POST'
  form.action = url
  form.target = '_blank'
  form.rel = 'noopener'
  const input = document.createElement('input')
  input.type = 'hidden'
  input.name = 'launch'
  input.value = launch
  form.append(input)
  document.body.append(form)
  try {
    form.submit()
  } finally {
    input.value = ''
    form.remove()
  }
}
