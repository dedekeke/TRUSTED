export const appConfig = {
  name: 'PETs Transformer',
  tagline: 'Protect the data, keep its value',
  /** FastAPI backend; empty = everything runs in the browser */
  apiBaseUrl: (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? '',
  /** max rows parsed from an uploaded CSV (keeps the in-browser preview fast) */
  maxUploadRows: 5000,
  defaultK: 5,
}
