export function getEvalCredentials() {
  return {
    username: process.env.EVAL_USERNAME || 'eval-test',
    password: process.env.EVAL_PASSWORD || 'EvalTest@2026',
  }
}

export async function getAuthToken(baseUrl: string): Promise<string> {
  const creds = getEvalCredentials()
  const res = await fetch(`${baseUrl}/api/user/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(creds),
  })
  if (!res.ok) throw new Error(`auth failed: ${res.status} ${await res.text()}`)
  const data = await res.json() as { data?: { token?: string } }
  const token = data?.data?.token
  if (!token) throw new Error('no token in response')
  return token
}
