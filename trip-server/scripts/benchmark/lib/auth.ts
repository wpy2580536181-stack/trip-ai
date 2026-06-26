export const EVAL_CREDENTIALS = {
  username: 'eval-test',
  password: 'EvalTest@2026',
} as const

export async function getAuthToken(baseUrl: string): Promise<string> {
  const res = await fetch(`${baseUrl}/api/user/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(EVAL_CREDENTIALS),
  })
  const data = (await res.json()) as { data: { token: string } }
  return data.data.token
}
