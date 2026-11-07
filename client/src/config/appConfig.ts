export const appConfig = {
  name: 'PETs Transformer',
  tagline: 'Protect the data, keep its value',
  /** server/api.py base URL (`/` = via the Vite dev proxy); empty = everything runs in the browser */
  apiBaseUrl: (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? '',
  /** max rows parsed from an uploaded CSV (keeps the in-browser preview fast) */
  maxUploadRows: 5000,
  defaultK: 5,
}
