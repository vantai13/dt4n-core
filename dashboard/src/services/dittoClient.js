// ---------------------------------------------------------------------------
// dittoClient.js -- service layer fetches Things from Ditto.
// Components call fetchAllThings(); they do not know URL/auth/pagination details.
// ---------------------------------------------------------------------------

const NAMESPACE = import.meta.env.VITE_DITTO_NAMESPACE || 'org.dt4n'
const DITTO_PREFIX = '/ditto/api/2'

async function dittoGet(path) {
  const res = await fetch(DITTO_PREFIX + path, {
    headers: { Accept: 'application/json' },
  })

  if (!res.ok) {
    const body = await res.text()
    throw new Error(`Ditto ${res.status} at ${path}: ${body.slice(0, 200)}`)
  }

  return res.json()
}

async function searchThingsPage(cursor) {
  const params = new URLSearchParams()
  params.set('filter', `like(thingId,"${NAMESPACE}:*")`)

  const options = ['size(200)']
  if (cursor) options.push(`cursor(${cursor})`)
  params.set('option', options.join(','))

  const data = await dittoGet('/search/things?' + params.toString())
  return {
    items: data.items || [],
    nextCursor: data.cursor || null,
  }
}

export async function fetchAllThings() {
  const all = []
  let cursor = null
  let guard = 0

  do {
    const { items, nextCursor } = await searchThingsPage(cursor)
    all.push(...items)
    cursor = nextCursor
    guard += 1
  } while (cursor && guard < 100)

  return all
}
