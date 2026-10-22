// Server-only helpers for talking to the Python extraction service.

// Set in apps/web/.env.local, e.g. EXTRACTION_SERVICE_URL=http://127.0.0.1:8000
export const EXTRACTION_SERVICE_URL = process.env.EXTRACTION_SERVICE_URL || 'http://127.0.0.1:8000'

// The extraction service rejects requests without this header (see main.py get_api_key).
// Set BACKEND_SECRET_TOKEN in apps/web/.env.local to the same value as the service's env.
export function backendHeaders(extra: Record<string, string> = {}): Record<string, string> {
  const token = process.env.BACKEND_SECRET_TOKEN
  return token ? { ...extra, 'X-Backend-Token': token } : extra
}
