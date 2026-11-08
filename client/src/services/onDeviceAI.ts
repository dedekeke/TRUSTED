import { ROLES, SUBTYPES } from '@/utils/constants'
import type { ColumnStats, PrivacyRole } from '@/types/pipeline.types'

export type NanoStatus = 'unsupported' | 'unavailable' | 'downloadable' | 'downloading' | 'available'

interface LanguageModelSession {
  prompt: (input: string, options?: { responseConstraint?: unknown }) => Promise<string>
  destroy?: () => void
}
interface LanguageModelStatic {
  availability: (opts?: unknown) => Promise<string>
  create: (opts?: unknown) => Promise<LanguageModelSession>
}

const lm = (): LanguageModelStatic | undefined =>
  (globalThis as unknown as { LanguageModel?: LanguageModelStatic }).LanguageModel

export async function nanoStatus(): Promise<NanoStatus> {
  const LM = lm()
  if (!LM) return 'unsupported'
  try {
    const s = await LM.availability({ expectedInputs: [{ type: 'text', languages: ['en'] }] })
    return (['unavailable', 'downloadable', 'downloading', 'available'].includes(s) ? s : 'unavailable') as NanoStatus
  } catch {
    return 'unavailable'
  }
}

const SYSTEM = `You are a data-protection analyst. You classify one column of a tabular dataset for privacy.
privacy_role is one of: ${ROLES.join(', ')}.
- direct_identifier: identifies a person alone (name, national id, email, phone, IBAN, card, plate, street address)
- quasi_identifier: identifies in combination (birth date, age, sex, postcode, municipality, timestamps, coordinates, employer, occupation)
- sensitive_attribute: the protected fact itself (health, diagnosis, income, salary, union, religion, special support, fraud flag)
- technical_identifier: device/network/account ids (IP, MAC, hostname, username, card id, meter id, hashed ids)
- free_text: unstructured notes or messages
- record_key: meaningless row identifier
- non_sensitive: safe to share
subtype is one of: ${SUBTYPES.join(', ')}.
Answer with JSON only.`

const SCHEMA = {
  type: 'object',
  properties: {
    privacy_role: { type: 'string', enum: ROLES },
    subtype: { type: 'string', enum: SUBTYPES },
    reason: { type: 'string' },
  },
  required: ['privacy_role', 'subtype', 'reason'],
}

export interface NanoAnswer {
  role: PrivacyRole
  subtype: string
  reason: string
}

let session: LanguageModelSession | null = null

export async function nanoClassify(
  column: string,
  stats: ColumnStats,
  onProgress?: (p: number) => void,
): Promise<NanoAnswer> {
  const LM = lm()
  if (!LM) throw new Error('Chrome built-in AI (Prompt API) is not available in this browser')
  session ??= await LM.create({
    initialPrompts: [{ role: 'system', content: SYSTEM }],
    expectedInputs: [{ type: 'text', languages: ['en'] }],
    monitor(m: EventTarget) {
      m.addEventListener('downloadprogress', (e) => onProgress?.((e as unknown as { loaded: number }).loaded))
    },
  })
  const input = [
    `Column name: ${column}`,
    `Distinct values: ${stats.distinct} of ${stats.nonEmpty} non-empty (unique ratio ${stats.uniqueRatio.toFixed(2)})`,
    `Average length: ${stats.avgLength.toFixed(1)}`,
    `Sample values: ${stats.examples
      .slice(0, 12)
      .map((e) => JSON.stringify(e.slice(0, 80)))
      .join(', ')}`,
  ].join('\n')
  const raw = await session.prompt(input, { responseConstraint: SCHEMA })
  const parsed = JSON.parse(raw) as { privacy_role: PrivacyRole; subtype: string; reason: string }
  if (!ROLES.includes(parsed.privacy_role)) throw new Error(`unexpected role ${parsed.privacy_role}`)
  return { role: parsed.privacy_role, subtype: parsed.subtype, reason: parsed.reason }
}
