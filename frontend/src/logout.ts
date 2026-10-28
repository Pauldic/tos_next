// Ends the session and goes back to the sign-in page. Works on every screen.
export async function logout() {
  try {
    await fetch('/api/method/logout', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'X-Frappe-CSRF-Token': (window as any).csrf_token || '' },
    })
  } catch {
    /* fall through to the redirect */
  }
  window.location.href = '/login'
}
