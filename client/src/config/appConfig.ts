export const appConfig = {
  name: 'PETs Transformer',
  tagline: 'Protect the data, keep its value',

  apiBaseUrl: (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? '',

  maxUploadRows: 5000,
  defaultK: 5,
}
