import { useCallback, useEffect, useRef, useState, type RefObject } from 'react'
import { AlertTriangle, ChevronDown, ChevronRight, Eye, EyeOff, KeyRound, RefreshCw, Save, Terminal, Trash2 } from 'lucide-react'
import { toast } from 'sonner'

import { api } from '@/lib/api'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { formatBytes } from '@/lib/utils'
import { getApiToken, setApiToken } from '@/lib/token'

// ─── 型定義 ──────────────────────────────────────────────────────────────────

type TokenQuota = {
  window_hours: number
  soft_limit_tokens: number
  hard_limit_tokens: number
}

type NotificationSettings = {
  min_level: string
  quiet_hours_start: number
  quiet_hours_end: number
}

// モデル構成の1エントリ
type ModelConfigEntry = {
  temperature: number
  max_tokens: number
  fallback_model: string
}

// ポリシールールの1カテゴリ
type PolicyCategory = {
  conditions: Record<string, string>
}

// 構造化ポリシールール（フォーム内部表現）
type StructuredPolicyRules = {
  auto_approve: PolicyCategory
  human_required: PolicyCategory
  auto_reject: PolicyCategory
}

type SettingsData = {
  llm_model: string
  daemon_interval: number
  daemon_max_files: number
  model_configurations: Record<string, unknown>
  prompt_templates: Record<string, unknown>
  policy_rules: Record<string, unknown>
  token_quota?: TokenQuota
  notification_settings?: NotificationSettings
  settings_file: string
  has_llm: boolean
}

const NOTIFICATION_LEVELS = ['info', 'warn', 'critical'] as const

type ModelsResponse = {
  provider: string
  models: string[]
  source: string
}

type RuntimeStatus = {
  claude: { available: boolean; binary?: string | null }
  wmux: { running: boolean; state: string }
  driver: string
}

type StorageEntry = {
  label: string
  path: string
  exists: boolean
  file_count: number
  size_bytes: number
  last_modified: string | null
}

type StorageInfo = {
  platform_home: string
  note: string
  storage: Record<string, StorageEntry>
}

// ─── デフォルト値 ──────────────────────────────────────────────────────────

const DEFAULT_MODEL_CONFIG: ModelConfigEntry = { temperature: 0.2, max_tokens: 4096, fallback_model: '' }

const DEFAULT_POLICY_RULES: StructuredPolicyRules = {
  auto_approve: { conditions: {} },
  human_required: { conditions: {} },
  auto_reject: { conditions: {} },
}

// ─── ユーティリティ ────────────────────────────────────────────────────────

function prettyJson(value: unknown): string {
  return JSON.stringify(value, null, 2)
}

function parseJsonObject(label: string, text: string): Record<string, unknown> {
  let parsed: unknown
  try {
    parsed = JSON.parse(text)
  } catch {
    throw new Error(`${label} の JSON 構文が不正です。`)
  }
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
    throw new Error(`${label} は JSON オブジェクトで指定してください。`)
  }
  return parsed as Record<string, unknown>
}

function wmuxLabel(state: string): string {
  if (state === 'connected') return 'wmux 接続中'
  if (state === 'awaiting-approval') return 'wmux 承認待ち（wmux ウィンドウで pantheon を承認）'
  if (state === 'not-running') return 'wmux 未起動'
  return 'wmux エラー'
}

/** StructuredPolicyRules → Record<string,unknown>（バックエンド互換） */
function policyToPayload(p: StructuredPolicyRules): Record<string, unknown> {
  return {
    auto_approve: { conditions: p.auto_approve.conditions },
    human_required: { conditions: p.human_required.conditions },
    auto_reject: { conditions: p.auto_reject.conditions },
  }
}

/** Record<string,unknown> → StructuredPolicyRules（取り込み） */
function payloadToPolicyRules(raw: Record<string, unknown>): StructuredPolicyRules {
  function toCategory(v: unknown): PolicyCategory {
    if (v && typeof v === 'object' && !Array.isArray(v)) {
      const obj = v as Record<string, unknown>
      if (obj.conditions && typeof obj.conditions === 'object' && !Array.isArray(obj.conditions)) {
        const conds: Record<string, string> = {}
        for (const [k, val] of Object.entries(obj.conditions as Record<string, unknown>)) {
          conds[k] = String(val)
        }
        return { conditions: conds }
      }
    }
    return { conditions: {} }
  }
  return {
    auto_approve: toCategory(raw.auto_approve),
    human_required: toCategory(raw.human_required),
    auto_reject: toCategory(raw.auto_reject),
  }
}

/** model_configurations から構造化表現へ */
function payloadToModelConfigs(raw: Record<string, unknown>): Record<string, ModelConfigEntry> {
  const result: Record<string, ModelConfigEntry> = {}
  for (const [key, val] of Object.entries(raw)) {
    if (val && typeof val === 'object' && !Array.isArray(val)) {
      const obj = val as Record<string, unknown>
      result[key] = {
        temperature: typeof obj.temperature === 'number' ? obj.temperature : DEFAULT_MODEL_CONFIG.temperature,
        max_tokens: typeof obj.max_tokens === 'number' ? obj.max_tokens : DEFAULT_MODEL_CONFIG.max_tokens,
        fallback_model: typeof obj.fallback_model === 'string' ? obj.fallback_model : '',
      }
    } else {
      result[key] = { ...DEFAULT_MODEL_CONFIG }
    }
  }
  if (Object.keys(result).length === 0) {
    result['default'] = { ...DEFAULT_MODEL_CONFIG }
  }
  return result
}

/** model_configurations 構造化 → ペイロード用 Record */
function modelConfigsToPayload(configs: Record<string, ModelConfigEntry>): Record<string, unknown> {
  const result: Record<string, unknown> = {}
  for (const [k, v] of Object.entries(configs)) {
    result[k] = {
      temperature: v.temperature,
      max_tokens: v.max_tokens,
      fallback_model: v.fallback_model,
    }
  }
  return result
}

/** prompt_templates → キー/値ペア配列（フォーム表現） */
type PromptEntry = { key: string; value: string }

function payloadToPromptEntries(raw: Record<string, unknown>): PromptEntry[] {
  const entries: PromptEntry[] = []
  for (const [k, v] of Object.entries(raw)) {
    if (typeof v === 'string') {
      entries.push({ key: k, value: v })
    } else {
      // 配列/オブジェクト値は黙殺しない — JSON文字列化して保持する
      entries.push({ key: k, value: prettyJson(v) })
    }
  }
  if (entries.length === 0) entries.push({ key: 'analysis', value: '' })
  return entries
}

function promptEntriesToPayload(entries: PromptEntry[]): Record<string, string> {
  const result: Record<string, string> = {}
  for (const { key, value } of entries) {
    if (key.trim()) result[key.trim()] = value
  }
  return result
}

// ─── サブコンポーネント: フィールドエラー表示 ───────────────────────────────

function FieldError({ message }: { message: string | null }) {
  if (!message) return null
  return <p className="text-xs text-red mt-1" role="alert">{message}</p>
}

// ─── サブコンポーネント: モデル構成エディタ ─────────────────────────────────

type ModelConfigEditorProps = {
  configs: Record<string, ModelConfigEntry>
  onChange: (configs: Record<string, ModelConfigEntry>) => void
  rawMode: boolean
  rawText: string
  onRawChange: (text: string) => void
  rawError: string | null
}

function ModelConfigEditor({ configs, onChange, rawMode, rawText, onRawChange, rawError }: ModelConfigEditorProps) {
  if (rawMode) {
    return (
      <div className="input-group">
        <textarea
          id="model-configurations-textarea"
          className="textarea mono"
          rows={8}
          value={rawText}
          onChange={(e) => onRawChange(e.target.value)}
          aria-label="モデル構成 JSON"
        />
        {rawError ? <FieldError message={rawError} /> : null}
      </div>
    )
  }

  const updateEntry = (key: string, field: keyof ModelConfigEntry, value: string | number) => {
    onChange({
      ...configs,
      [key]: { ...configs[key], [field]: value },
    })
  }

  const addEntry = () => {
    const newKey = `config_${Object.keys(configs).length + 1}`
    onChange({ ...configs, [newKey]: { ...DEFAULT_MODEL_CONFIG } })
  }

  const removeEntry = (key: string) => {
    const next = { ...configs }
    delete next[key]
    onChange(next)
  }

  return (
    <div className="flex flex-col gap-4">
      {Object.entries(configs).map(([key, cfg]) => (
        <div key={key} className="border border-border rounded-lg p-3 flex flex-col gap-3">
          <div className="flex items-center justify-between gap-2">
            <span className="font-mono text-sm font-semibold">{key}</span>
            {Object.keys(configs).length > 1 ? (
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                onClick={() => removeEntry(key)}
                aria-label={`${key} を削除`}
              >
                <Trash2 size={12} />
              </button>
            ) : null}
          </div>
          <div className="settings-row-2">
            <div className="input-group">
              <label className="input-label" htmlFor={`mc-temp-${key}`}>temperature</label>
              <input
                id={`mc-temp-${key}`}
                className="input"
                type="number"
                min={0}
                max={1}
                step={0.05}
                value={cfg.temperature}
                onChange={(e) => {
                  const v = parseFloat(e.target.value)
                  if (!Number.isNaN(v)) updateEntry(key, 'temperature', v)
                }}
              />
            </div>
            <div className="input-group">
              <label className="input-label" htmlFor={`mc-tokens-${key}`}>max_tokens</label>
              <input
                id={`mc-tokens-${key}`}
                className="input"
                type="number"
                min={1}
                step={256}
                value={cfg.max_tokens}
                onChange={(e) => {
                  const v = parseInt(e.target.value, 10)
                  if (!Number.isNaN(v) && v >= 1) updateEntry(key, 'max_tokens', v)
                }}
              />
            </div>
            <div className="input-group">
              <label className="input-label" htmlFor={`mc-fallback-${key}`}>fallback_model（任意）</label>
              <input
                id={`mc-fallback-${key}`}
                className="input"
                type="text"
                value={cfg.fallback_model}
                onChange={(e) => updateEntry(key, 'fallback_model', e.target.value)}
                placeholder="省略可"
              />
            </div>
          </div>
        </div>
      ))}
      <button type="button" className="btn btn-secondary btn-sm w-fit" onClick={addEntry}>
        + 構成を追加
      </button>
    </div>
  )
}

// ─── サブコンポーネント: プロンプトテンプレートエディタ ───────────────────────

type PromptEditorProps = {
  entries: PromptEntry[]
  onChange: (entries: PromptEntry[]) => void
  rawMode: boolean
  rawText: string
  onRawChange: (text: string) => void
  rawError: string | null
  entryErrors: Record<number, string>
}

function PromptEditor({ entries, onChange, rawMode, rawText, onRawChange, rawError, entryErrors }: PromptEditorProps) {
  if (rawMode) {
    return (
      <div className="input-group">
        <textarea
          id="prompt-templates-textarea"
          className="textarea mono"
          rows={8}
          value={rawText}
          onChange={(e) => onRawChange(e.target.value)}
          aria-label="プロンプトテンプレート JSON"
        />
        {rawError ? <FieldError message={rawError} /> : null}
      </div>
    )
  }

  const updateKey = (idx: number, key: string) => {
    const next = entries.map((e, i) => (i === idx ? { ...e, key } : e))
    onChange(next)
  }

  const updateValue = (idx: number, value: string) => {
    const next = entries.map((e, i) => (i === idx ? { ...e, value } : e))
    onChange(next)
  }

  const addEntry = () => onChange([...entries, { key: '', value: '' }])

  const removeEntry = (idx: number) => onChange(entries.filter((_, i) => i !== idx))

  return (
    <div className="flex flex-col gap-4">
      {entries.map((entry, idx) => (
        <div key={idx} className="border border-border rounded-lg p-3 flex flex-col gap-2">
          <div className="flex items-center gap-2">
            <input
              className="input font-mono text-sm"
              type="text"
              placeholder="テンプレート名（キー）"
              value={entry.key}
              onChange={(e) => updateKey(idx, e.target.value)}
              aria-label={`テンプレート ${idx + 1} キー`}
            />
            {entries.length > 1 ? (
              <button
                type="button"
                className="btn btn-ghost btn-sm shrink-0"
                onClick={() => removeEntry(idx)}
                aria-label={`テンプレート ${idx + 1} を削除`}
              >
                <Trash2 size={12} />
              </button>
            ) : null}
          </div>
          <textarea
            className="textarea text-sm"
            rows={4}
            placeholder="プロンプト本文"
            value={entry.value}
            onChange={(e) => updateValue(idx, e.target.value)}
            aria-label={`テンプレート ${idx + 1} 本文`}
          />
          {entryErrors[idx] ? <FieldError message={entryErrors[idx]} /> : null}
        </div>
      ))}
      <button type="button" className="btn btn-secondary btn-sm w-fit" onClick={addEntry}>
        + テンプレートを追加
      </button>
    </div>
  )
}

// ─── サブコンポーネント: ポリシーエディタ ───────────────────────────────────

type PolicyCategoryEditorProps = {
  label: string
  categoryKey: keyof StructuredPolicyRules
  category: PolicyCategory
  onChange: (key: keyof StructuredPolicyRules, value: PolicyCategory) => void
  warn: boolean
}

function PolicyCategoryEditor({ label, categoryKey, category, onChange, warn }: PolicyCategoryEditorProps) {
  const updateCondKey = (idx: number, newKey: string) => {
    const entries = Object.entries(category.conditions)
    entries[idx] = [newKey, entries[idx][1]]
    onChange(categoryKey, { conditions: Object.fromEntries(entries) })
  }

  const updateCondValue = (idx: number, value: string) => {
    const entries = Object.entries(category.conditions)
    entries[idx] = [entries[idx][0], value]
    onChange(categoryKey, { conditions: Object.fromEntries(entries) })
  }

  const addCond = () => {
    const newKey = `condition_${Object.keys(category.conditions).length + 1}`
    onChange(categoryKey, { conditions: { ...category.conditions, [newKey]: '' } })
  }

  const removeCond = (idx: number) => {
    const entries = Object.entries(category.conditions).filter((_, i) => i !== idx)
    onChange(categoryKey, { conditions: Object.fromEntries(entries) })
  }

  const condEntries = Object.entries(category.conditions)

  return (
    <div className={`border rounded-lg p-3 flex flex-col gap-2 ${warn ? 'border-yellow' : 'border-border'}`}>
      <div className="flex items-center justify-between">
        <span className="font-semibold text-sm">{label}</span>
        {warn ? (
          <span className="badge badge-yellow text-xs">条件なし（すべてに適用）</span>
        ) : null}
      </div>
      {condEntries.length === 0 ? (
        <p className="text-xs text-muted">条件が設定されていません。</p>
      ) : (
        <div className="flex flex-col gap-1">
          {condEntries.map(([k, v], idx) => (
            <div key={idx} className="flex items-center gap-2">
              <input
                className="input text-sm font-mono"
                type="text"
                placeholder="条件キー"
                value={k}
                onChange={(e) => updateCondKey(idx, e.target.value)}
                aria-label={`${label} 条件 ${idx + 1} キー`}
              />
              <input
                className="input text-sm"
                type="text"
                placeholder="値"
                value={v}
                onChange={(e) => updateCondValue(idx, e.target.value)}
                aria-label={`${label} 条件 ${idx + 1} 値`}
              />
              <button
                type="button"
                className="btn btn-ghost btn-sm shrink-0"
                onClick={() => removeCond(idx)}
                aria-label={`${label} 条件 ${idx + 1} を削除`}
              >
                <Trash2 size={12} />
              </button>
            </div>
          ))}
        </div>
      )}
      <button type="button" className="btn btn-secondary btn-sm w-fit" onClick={addCond}>
        + 条件を追加
      </button>
    </div>
  )
}

type PolicyEditorProps = {
  rules: StructuredPolicyRules
  onChange: (rules: StructuredPolicyRules) => void
  rawMode: boolean
  rawText: string
  onRawChange: (text: string) => void
  rawError: string | null
}

function PolicyEditor({ rules, onChange, rawMode, rawText, onRawChange, rawError }: PolicyEditorProps) {
  const updateCategory = (key: keyof StructuredPolicyRules, value: PolicyCategory) => {
    onChange({ ...rules, [key]: value })
  }

  if (rawMode) {
    return (
      <div className="input-group">
        <textarea
          id="policy-rules-textarea"
          className="textarea mono"
          rows={10}
          value={rawText}
          onChange={(e) => onRawChange(e.target.value)}
          aria-label="ポリシールール JSON"
        />
        {rawError ? <FieldError message={rawError} /> : null}
      </div>
    )
  }

  const autoApproveEmpty = Object.keys(rules.auto_approve.conditions).length === 0
  const humanRequiredEmpty = Object.keys(rules.human_required.conditions).length === 0

  return (
    <div className="flex flex-col gap-3">
      {autoApproveEmpty ? (
        <div className="settings-status-bar warn">
          <AlertTriangle size={14} className="shrink-0" />
          <span className="text-sm">auto_approve の条件が空です。すべての操作が自動承認されます。安全境界に影響します。</span>
        </div>
      ) : null}
      {humanRequiredEmpty ? (
        <div className="settings-status-bar warn">
          <AlertTriangle size={14} className="shrink-0" />
          <span className="text-sm">human_required の条件が空です。人手確認がスキップされます。</span>
        </div>
      ) : null}
      <PolicyCategoryEditor
        label="自動承認（auto_approve）"
        categoryKey="auto_approve"
        category={rules.auto_approve}
        onChange={updateCategory}
        warn={autoApproveEmpty}
      />
      <PolicyCategoryEditor
        label="人手必須（human_required）"
        categoryKey="human_required"
        category={rules.human_required}
        onChange={updateCategory}
        warn={humanRequiredEmpty}
      />
      <PolicyCategoryEditor
        label="自動却下（auto_reject）"
        categoryKey="auto_reject"
        category={rules.auto_reject}
        onChange={updateCategory}
        warn={false}
      />
    </div>
  )
}

// ─── メインページ ────────────────────────────────────────────────────────────

// フィールドエラー管理用の型
type FieldErrors = {
  daemonInterval?: string
  daemonMaxFiles?: string
  windowHours?: string
  softLimit?: string
  hardLimit?: string
  quietStart?: string
  quietEnd?: string
  modelConfigurations?: string
  promptTemplates?: string
  policyRules?: string
}

export function SettingsPage() {
  const [data, setData] = useState<SettingsData | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({})
  const [storageInfo, setStorageInfo] = useState<StorageInfo | null>(null)
  const [runtime, setRuntime] = useState<RuntimeStatus | null>(null)
  const [modelsError, setModelsError] = useState(false)
  const [showDriverDetail, setShowDriverDetail] = useState(false)

  // ── フォームフィールド ───────────────────────────────────────────────────
  const [model, setModel] = useState('claude-opus-4-8')
  const [availableModels, setAvailableModels] = useState<string[]>([])
  const [daemonInterval, setDaemonInterval] = useState(3600)
  const [daemonMaxFiles, setDaemonMaxFiles] = useState(10)

  // 高度な構成: 構造化モード
  const [modelConfigs, setModelConfigs] = useState<Record<string, ModelConfigEntry>>({
    default: { ...DEFAULT_MODEL_CONFIG },
  })
  const [promptEntries, setPromptEntries] = useState<PromptEntry[]>([{ key: 'analysis', value: '' }])
  const [policyRules, setPolicyRules] = useState<StructuredPolicyRules>({ ...DEFAULT_POLICY_RULES })
  const [promptEntryErrors, setPromptEntryErrors] = useState<Record<number, string>>({})

  // 高度な構成: RAW JSON モード
  const [modelConfigsRaw, setModelConfigsRaw] = useState(false)
  const [promptTemplatesRaw, setPromptTemplatesRaw] = useState(false)
  const [policyRulesRaw, setPolicyRulesRaw] = useState(false)
  const [modelConfigsRawText, setModelConfigsRawText] = useState('')
  const [promptTemplatesRawText, setPromptTemplatesRawText] = useState('')
  const [policyRulesRawText, setPolicyRulesRawText] = useState('')
  const [modelConfigsRawError, setModelConfigsRawError] = useState<string | null>(null)
  const [promptTemplatesRawError, setPromptTemplatesRawError] = useState<string | null>(null)
  const [policyRulesRawError, setPolicyRulesRawError] = useState<string | null>(null)

  // クォータ・通知
  const [windowHours, setWindowHours] = useState(5)
  const [softLimit, setSoftLimit] = useState(0)
  const [hardLimit, setHardLimit] = useState(0)
  const [notifyMinLevel, setNotifyMinLevel] = useState('info')
  const [quietStart, setQuietStart] = useState(0)
  const [quietEnd, setQuietEnd] = useState(0)

  // APIトークン（C010）— /api/settings には混ぜない
  const [apiToken, setApiTokenState] = useState('')
  const [apiTokenVisible, setApiTokenVisible] = useState(false)
  const [apiTokenSaved, setApiTokenSaved] = useState(false)
  const [confirmClearToken, setConfirmClearToken] = useState(false)

  // dirty追跡
  const [isDirty, setIsDirty] = useState(false)

  // フォーカス用 ref
  const daemonIntervalRef = useRef<HTMLInputElement>(null)
  const daemonMaxFilesRef = useRef<HTMLInputElement>(null)
  const windowHoursRef = useRef<HTMLInputElement>(null)
  const softLimitRef = useRef<HTMLInputElement>(null)
  const hardLimitRef = useRef<HTMLInputElement>(null)
  const quietStartRef = useRef<HTMLInputElement>(null)
  const quietEndRef = useRef<HTMLInputElement>(null)

  // ── データロード ──────────────────────────────────────────────────────────

  const initFormFromSettings = useCallback((s: SettingsData) => {
    setModel(s.llm_model)
    setDaemonInterval(s.daemon_interval)
    setDaemonMaxFiles(s.daemon_max_files)

    const parsedModelConfigs = payloadToModelConfigs(s.model_configurations)
    setModelConfigs(parsedModelConfigs)
    setModelConfigsRawText(prettyJson(s.model_configurations))

    const parsedPromptEntries = payloadToPromptEntries(s.prompt_templates)
    setPromptEntries(parsedPromptEntries)
    setPromptTemplatesRawText(prettyJson(s.prompt_templates))

    const parsedPolicy = payloadToPolicyRules(s.policy_rules)
    setPolicyRules(parsedPolicy)
    setPolicyRulesRawText(prettyJson(s.policy_rules))

    if (s.token_quota) {
      setWindowHours(s.token_quota.window_hours)
      setSoftLimit(s.token_quota.soft_limit_tokens)
      setHardLimit(s.token_quota.hard_limit_tokens)
    }
    if (s.notification_settings) {
      setNotifyMinLevel(s.notification_settings.min_level)
      setQuietStart(s.notification_settings.quiet_hours_start)
      setQuietEnd(s.notification_settings.quiet_hours_end)
    }
    setIsDirty(false)
    setFieldErrors({})
    setPromptEntryErrors({})
  }, [])

  const load = useCallback(async () => {
    setLoading(true)
    const [settingsResult, storageResult, runtimeResult, modelsResult] = await Promise.allSettled([
      api<SettingsData>('GET', '/api/settings'),
      api<StorageInfo>('GET', '/api/storage/info'),
      api<RuntimeStatus>('GET', '/api/sessions/runtime'),
      api<ModelsResponse>('GET', '/api/providers/claude/models'),
    ])

    if (settingsResult.status === 'fulfilled') {
      const s: SettingsData = { ...settingsResult.value }
      setData(s)
      initFormFromSettings(s)
      setLoadError(null)
    } else {
      setData(null)
      setLoadError('設定を取得できませんでした。再読込をお試しください。')
    }

    setStorageInfo(storageResult.status === 'fulfilled' ? storageResult.value : null)
    setRuntime(runtimeResult.status === 'fulfilled' ? runtimeResult.value : null)

    if (modelsResult.status === 'fulfilled' && modelsResult.value.models.length > 0) {
      setAvailableModels(modelsResult.value.models)
      setModelsError(false)
    } else {
      setModelsError(true)
    }

    // APIトークンを localStorage から読み込む
    setApiTokenState(getApiToken())

    setLoading(false)
  }, [initFormFromSettings])

  useEffect(() => {
    void load()
  }, [load])

  // フォームが変更されたら dirty フラグをセット
  const markDirty = () => setIsDirty(true)

  // ── RAW JSON トグル ────────────────────────────────────────────────────────

  const toggleModelConfigsRaw = () => {
    if (!modelConfigsRaw) {
      // 構造化 → RAW: 現在の構造化フォームを JSON テキストへ変換
      setModelConfigsRawText(prettyJson(modelConfigsToPayload(modelConfigs)))
      setModelConfigsRawError(null)
    } else {
      // RAW → 構造化: RAW テキストをパースして構造化へ戻す
      try {
        const parsed = parseJsonObject('モデル構成', modelConfigsRawText)
        setModelConfigs(payloadToModelConfigs(parsed))
        setModelConfigsRawError(null)
      } catch (e) {
        setModelConfigsRawError(e instanceof Error ? e.message : 'JSON 解析エラー')
        return // エラーがあればトグルしない
      }
    }
    setModelConfigsRaw((v) => !v)
    markDirty()
  }

  const togglePromptTemplatesRaw = () => {
    if (!promptTemplatesRaw) {
      setPromptTemplatesRawText(prettyJson(promptEntriesToPayload(promptEntries)))
      setPromptTemplatesRawError(null)
    } else {
      try {
        const parsed = parseJsonObject('プロンプトテンプレート', promptTemplatesRawText)
        setPromptEntries(payloadToPromptEntries(parsed))
        setPromptTemplatesRawError(null)
      } catch (e) {
        setPromptTemplatesRawError(e instanceof Error ? e.message : 'JSON 解析エラー')
        return
      }
    }
    setPromptTemplatesRaw((v) => !v)
    markDirty()
  }

  const togglePolicyRulesRaw = () => {
    if (!policyRulesRaw) {
      setPolicyRulesRawText(prettyJson(policyToPayload(policyRules)))
      setPolicyRulesRawError(null)
    } else {
      try {
        const parsed = parseJsonObject('ポリシールール', policyRulesRawText)
        setPolicyRules(payloadToPolicyRules(parsed))
        setPolicyRulesRawError(null)
      } catch (e) {
        setPolicyRulesRawError(e instanceof Error ? e.message : 'JSON 解析エラー')
        return
      }
    }
    setPolicyRulesRaw((v) => !v)
    markDirty()
  }

  // ── APIトークン操作 ────────────────────────────────────────────────────────

  const handleSaveApiToken = () => {
    const trimmed = apiToken.trim()
    setApiToken(trimmed)
    setApiTokenSaved(true)
    setTimeout(() => setApiTokenSaved(false), 2000)
    toast.success('APIトークンを保存しました。')
  }

  const handleClearApiToken = () => {
    setApiToken('')
    setApiTokenState('')
    setApiTokenSaved(false)
    toast.success('APIトークンを消去しました。')
  }

  // ── バリデーション ─────────────────────────────────────────────────────────

  type ValidationResult =
    | { ok: true; payload: Parameters<typeof api>[2] }
    | { ok: false; errors: FieldErrors; promptErrors: Record<number, string>; firstRef?: RefObject<HTMLInputElement | null> }

  const validate = (): ValidationResult => {
    const errors: FieldErrors = {}
    const promptErrors: Record<number, string> = {}
    let firstRef: RefObject<HTMLInputElement | null> | undefined

    // デーモン設定
    const intervalVal = daemonInterval
    if (Number.isNaN(intervalVal) || intervalVal < 60) {
      errors.daemonInterval = '実行間隔は 60 秒以上にしてください。'
      if (!firstRef) firstRef = daemonIntervalRef
    }
    const maxFilesVal = daemonMaxFiles
    if (Number.isNaN(maxFilesVal) || maxFilesVal < 1 || maxFilesVal > 1000) {
      errors.daemonMaxFiles = '最大ファイル数は 1〜1000 の範囲で指定してください。'
      if (!firstRef) firstRef = daemonMaxFilesRef
    }

    // クォータ
    const wh = windowHours
    if (Number.isNaN(wh) || wh < 1) {
      errors.windowHours = 'クォータ窓は 1 時間以上にしてください。'
      if (!firstRef) firstRef = windowHoursRef
    }
    const soft = softLimit
    const hard = hardLimit
    if (Number.isNaN(soft) || soft < 0) {
      errors.softLimit = 'ソフト上限は 0 以上の整数で指定してください（0=無制限）。'
      if (!firstRef) firstRef = softLimitRef
    }
    if (Number.isNaN(hard) || hard < 0) {
      errors.hardLimit = 'ハード上限は 0 以上の整数で指定してください（0=無制限）。'
      if (!firstRef) firstRef = hardLimitRef
    }
    if (!errors.softLimit && !errors.hardLimit && soft > 0 && hard > 0 && soft > hard) {
      errors.softLimit = 'ソフト上限はハード上限以下にしてください。'
      if (!firstRef) firstRef = softLimitRef
    }

    // 静音時間
    const qs = quietStart
    const qe = quietEnd
    if (Number.isNaN(qs) || qs < 0 || qs > 23) {
      errors.quietStart = '静音開始時刻は 0〜23 の範囲で指定してください。'
      if (!firstRef) firstRef = quietStartRef
    }
    if (Number.isNaN(qe) || qe < 0 || qe > 23) {
      errors.quietEnd = '静音終了時刻は 0〜23 の範囲で指定してください。'
      if (!firstRef) firstRef = quietEndRef
    }

    // 高度な構成: RAW モードの場合は JSON 構文チェック
    let modelConfigurationsPayload: Record<string, unknown>
    let promptTemplatesPayload: Record<string, string>
    let policyRulesPayload: Record<string, unknown>

    if (modelConfigsRaw) {
      try {
        modelConfigurationsPayload = parseJsonObject('モデル構成', modelConfigsRawText)
      } catch (e) {
        errors.modelConfigurations = e instanceof Error ? e.message : 'JSON 解析エラー'
        modelConfigurationsPayload = {}
      }
    } else {
      modelConfigurationsPayload = modelConfigsToPayload(modelConfigs)
    }

    if (promptTemplatesRaw) {
      try {
        const parsed = parseJsonObject('プロンプトテンプレート', promptTemplatesRawText)
        // 各値が文字列かチェック
        const result: Record<string, string> = {}
        for (const [k, v] of Object.entries(parsed)) {
          if (typeof v !== 'string') {
            errors.promptTemplates = `プロンプトテンプレートの値は文字列で指定してください（"${k}" が文字列ではありません）。`
            break
          }
          result[k] = v
        }
        promptTemplatesPayload = result
      } catch (e) {
        errors.promptTemplates = e instanceof Error ? e.message : 'JSON 解析エラー'
        promptTemplatesPayload = {}
      }
    } else {
      // 構造化: 各エントリの値が重複キーなし、かつキーが空でないかチェック
      const result: Record<string, string> = {}
      for (let i = 0; i < promptEntries.length; i++) {
        const { key, value } = promptEntries[i]
        if (!key.trim()) {
          promptErrors[i] = 'テンプレート名（キー）を入力してください。'
        } else if (key.trim() in result) {
          promptErrors[i] = 'テンプレート名が重複しています。'
        } else {
          result[key.trim()] = value
        }
      }
      promptTemplatesPayload = result
    }

    if (policyRulesRaw) {
      try {
        policyRulesPayload = parseJsonObject('ポリシールール', policyRulesRawText)
      } catch (e) {
        errors.policyRules = e instanceof Error ? e.message : 'JSON 解析エラー'
        policyRulesPayload = {}
      }
    } else {
      policyRulesPayload = policyToPayload(policyRules)
    }

    const hasErrors = Object.keys(errors).length > 0 || Object.keys(promptErrors).length > 0
    if (hasErrors) {
      return { ok: false, errors, promptErrors, firstRef }
    }

    return {
      ok: true,
      payload: {
        llm_model: model,
        daemon_interval: intervalVal,
        daemon_max_files: maxFilesVal,
        model_configurations: modelConfigurationsPayload,
        prompt_templates: promptTemplatesPayload,
        policy_rules: policyRulesPayload,
        token_quota: {
          window_hours: wh,
          soft_limit_tokens: soft,
          hard_limit_tokens: hard,
        },
        notification_settings: {
          min_level: notifyMinLevel,
          quiet_hours_start: qs,
          quiet_hours_end: qe,
        },
      },
    }
  }

  // ── 保存 ──────────────────────────────────────────────────────────────────

  const handleSave = async () => {
    const result = validate()
    if (!result.ok) {
      setFieldErrors(result.errors)
      setPromptEntryErrors(result.promptErrors)
      // 最初のエラーフィールドへフォーカス/スクロール
      if (result.firstRef?.current) {
        result.firstRef.current.focus()
        result.firstRef.current.scrollIntoView({ behavior: 'smooth', block: 'center' })
      }
      const msgs = [
        ...Object.values(result.errors),
        ...Object.values(result.promptErrors),
      ]
      toast.error(msgs[0] ?? '設定の検証に失敗しました。')
      return
    }

    setSaving(true)
    try {
      await api('PUT', '/api/settings', result.payload)
      toast.success('設定を保存しました。')
      setFieldErrors({})
      setPromptEntryErrors({})
      setIsDirty(false)
      await load()
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '設定の保存に失敗しました。')
    } finally {
      setSaving(false)
    }
  }

  // ── モデル選択肢の組み立て（現在値を必ずマージ） ──────────────────────────

  const modelOptions = availableModels.length > 0
    ? (availableModels.includes(model) ? availableModels : [model, ...availableModels])
    : [model]

  // ── claude CLI 検出判定（runtime 一本に統一。runtime 未取得時は has_llm フォールバック） ──

  const claudeAvailable = runtime
    ? runtime.claude.available
    : (data?.has_llm ?? false)

  // ─────────────────────────────────────────────────────────────────────────

  return (
    <>
      <header className="page-header">
        <div className="page-title">設定</div>
        <div className="page-actions">
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            onClick={() => void load()}
            disabled={loading}
          >
            <RefreshCw size={14} />
            再読込
          </button>
        </div>
      </header>

      <div className="page-content flex flex-col gap-4">
        {loading ? (
          <div className="card">
            <div className="card-body flex items-center gap-3">
              <div className="spinner" />
              <div className="text-muted">設定を読み込み中…</div>
            </div>
          </div>
        ) : null}

        {!loading ? (
          <form onSubmit={(e) => { e.preventDefault() }} className="flex flex-col gap-4">
            {/* ── 読み込みエラーバー ── */}
            {loadError ? (
              <div className="settings-status-bar warn" role="alert">
                <AlertTriangle size={14} className="shrink-0" />
                <span className="text-sm flex-1">{loadError}</span>
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  onClick={() => void load()}
                >
                  再読込
                </button>
              </div>
            ) : null}

            {/* ── 接続/認証: APIトークン（C010） ── */}
            <div className="card">
              <div className="card-header">
                <div>
                  <div className="card-title flex items-center gap-2">
                    <KeyRound size={15} />
                    接続・認証
                  </div>
                  <div className="card-description">
                    サーバが PANTHEON_API_TOKEN を要求する場合にトークンを設定します。設定しない場合は認証なしで接続します。
                  </div>
                </div>
              </div>
              <div className="card-body flex flex-col gap-3">
                <div className="input-group max-w-xl">
                  <label className="input-label" htmlFor="api-token-field">
                    APIトークン（ローカル保存）
                  </label>
                  <div className="flex items-center gap-2">
                    <input
                      id="api-token-field"
                      className="input flex-1"
                      type={apiTokenVisible ? 'text' : 'password'}
                      value={apiToken}
                      onChange={(e) => {
                        setApiTokenState(e.target.value)
                        setApiTokenSaved(false)
                      }}
                      placeholder="トークンを貼り付け…"
                      autoComplete="off"
                      aria-label="APIトークン"
                    />
                    <button
                      type="button"
                      className="btn btn-ghost btn-sm"
                      onClick={() => setApiTokenVisible((v) => !v)}
                      aria-label={apiTokenVisible ? 'トークンを隠す' : 'トークンを表示'}
                    >
                      {apiTokenVisible ? <EyeOff size={14} /> : <Eye size={14} />}
                    </button>
                    <button
                      type="button"
                      className="btn btn-secondary btn-sm"
                      onClick={handleSaveApiToken}
                      disabled={!apiToken.trim()}
                    >
                      {apiTokenSaved ? '保存済み' : '保存'}
                    </button>
                    <button
                      type="button"
                      className="btn btn-danger btn-sm"
                      onClick={() => setConfirmClearToken(true)}
                      disabled={!getApiToken()}
                    >
                      <Trash2 size={12} />
                      消去
                    </button>
                  </div>
                  <p className="settings-hint">
                    このトークンはブラウザの localStorage にのみ保存されます。/api/settings には含まれません。
                  </p>
                </div>
              </div>
            </div>

            {/* ── 実行ランタイム ── */}
            <div className="card">
              <div className="card-header">
                <div>
                  <div className="card-title flex items-center gap-2">
                    <Terminal size={15} />
                    実行ランタイム（Claude Code）
                  </div>
                  <div className="card-description">
                    Pantheon は API キー不要。すべてローカルの claude CLI と wmux 経由で動作します。
                  </div>
                </div>
              </div>
              <div className="card-body flex flex-col gap-3">
                <div className="flex items-center gap-3 flex-wrap">
                  <span className={`badge ${claudeAvailable ? 'badge-green' : 'badge-red'}`}>
                    {claudeAvailable ? 'claude CLI 検出' : 'claude CLI 未検出'}
                  </span>
                  {!claudeAvailable ? (
                    <span className="text-xs text-muted">
                      claude CLI が見つかりません。インストール後 PATH を通してサーバーを再起動してください。
                    </span>
                  ) : null}
                  {runtime ? (
                    <span className={`badge ${runtime.wmux.state === 'connected' ? 'badge-green' : runtime.wmux.state === 'awaiting-approval' ? 'badge-yellow' : 'badge-neutral'}`}>
                      {wmuxLabel(runtime.wmux.state)}
                    </span>
                  ) : null}
                </div>

                {runtime?.claude.binary ? (
                  <div className="storage-location">
                    <span className="text-muted text-sm">claude:</span>
                    <code className="mono text-sm">{runtime.claude.binary}</code>
                  </div>
                ) : null}

                {/* driver バッジは詳細折りたたみへ退避（C039/P3） */}
                {runtime ? (
                  <div>
                    <button
                      type="button"
                      className="btn btn-ghost btn-sm text-muted"
                      onClick={() => setShowDriverDetail((v) => !v)}
                      aria-expanded={showDriverDetail}
                    >
                      {showDriverDetail ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
                      詳細情報
                    </button>
                    {showDriverDetail ? (
                      <div className="flex items-center gap-2 mt-2 pl-4">
                        <span className="text-xs text-muted">実行ドライバ:</span>
                        <span className="badge badge-neutral text-xs">{runtime.driver}</span>
                      </div>
                    ) : null}
                  </div>
                ) : null}

                {/* 既定モデル選択 */}
                <div className="input-group max-w-sm">
                  <label className="input-label" htmlFor="llm-model-select">既定モデル（任意）</label>
                  <select
                    id="llm-model-select"
                    className="select"
                    value={model}
                    onChange={(e) => { setModel(e.target.value); markDirty() }}
                  >
                    {modelOptions.map((m) => (
                      <option key={m} value={m}>{m}</option>
                    ))}
                  </select>
                  {modelsError ? (
                    <p className="settings-hint text-yellow">モデル一覧を取得できません（CLI 既定を使用）。</p>
                  ) : (
                    <p className="settings-hint">省略時は claude CLI の既定モデルが使われます。</p>
                  )}
                </div>
              </div>
            </div>

            {/* ── 高度な構成管理 ── */}
            <div className="card">
              <div className="card-header">
                <div>
                  <div className="card-title">高度な構成管理</div>
                  <div className="card-description">モデル構成、プロンプトテンプレート、ポリシールールを保存します。</div>
                </div>
              </div>
              <div className="card-body flex flex-col gap-6">
                {/* モデル構成 */}
                <div className="flex flex-col gap-2">
                  <div className="flex items-center justify-between">
                    <label className="input-label mb-0">モデル構成</label>
                    <button
                      type="button"
                      className="btn btn-ghost btn-sm text-muted"
                      onClick={toggleModelConfigsRaw}
                    >
                      {modelConfigsRaw ? '構造化エディタ' : 'RAW (JSON)'}
                    </button>
                  </div>
                  <ModelConfigEditor
                    configs={modelConfigs}
                    onChange={(c) => { setModelConfigs(c); markDirty() }}
                    rawMode={modelConfigsRaw}
                    rawText={modelConfigsRawText}
                    onRawChange={(t) => { setModelConfigsRawText(t); setModelConfigsRawError(null); markDirty() }}
                    rawError={modelConfigsRawError ?? fieldErrors.modelConfigurations ?? null}
                  />
                  {!modelConfigsRaw && fieldErrors.modelConfigurations ? (
                    <FieldError message={fieldErrors.modelConfigurations} />
                  ) : null}
                </div>

                {/* プロンプトテンプレート */}
                <div className="flex flex-col gap-2">
                  <div className="flex items-center justify-between">
                    <label className="input-label mb-0">プロンプトテンプレート</label>
                    <button
                      type="button"
                      className="btn btn-ghost btn-sm text-muted"
                      onClick={togglePromptTemplatesRaw}
                    >
                      {promptTemplatesRaw ? '構造化エディタ' : 'RAW (JSON)'}
                    </button>
                  </div>
                  <PromptEditor
                    entries={promptEntries}
                    onChange={(e) => { setPromptEntries(e); markDirty() }}
                    rawMode={promptTemplatesRaw}
                    rawText={promptTemplatesRawText}
                    onRawChange={(t) => { setPromptTemplatesRawText(t); setPromptTemplatesRawError(null); markDirty() }}
                    rawError={promptTemplatesRawError ?? fieldErrors.promptTemplates ?? null}
                    entryErrors={promptEntryErrors}
                  />
                  {!promptTemplatesRaw && fieldErrors.promptTemplates ? (
                    <FieldError message={fieldErrors.promptTemplates} />
                  ) : null}
                </div>

                {/* ポリシールール */}
                <div className="flex flex-col gap-2">
                  <div className="flex items-center justify-between">
                    <label className="input-label mb-0">ポリシールール</label>
                    <button
                      type="button"
                      className="btn btn-ghost btn-sm text-muted"
                      onClick={togglePolicyRulesRaw}
                    >
                      {policyRulesRaw ? '構造化エディタ' : 'RAW (JSON)'}
                    </button>
                  </div>
                  <PolicyEditor
                    rules={policyRules}
                    onChange={(r) => { setPolicyRules(r); markDirty() }}
                    rawMode={policyRulesRaw}
                    rawText={policyRulesRawText}
                    onRawChange={(t) => { setPolicyRulesRawText(t); setPolicyRulesRawError(null); markDirty() }}
                    rawError={policyRulesRawError ?? fieldErrors.policyRules ?? null}
                  />
                  {!policyRulesRaw && fieldErrors.policyRules ? (
                    <FieldError message={fieldErrors.policyRules} />
                  ) : null}
                </div>
              </div>
            </div>

            {/* ── デーモン設定 ── */}
            <div className="card">
              <div className="card-header">
                <div>
                  <div className="card-title">デーモン設定</div>
                  <div className="card-description">バックグラウンドの自律改善ループの動作パラメータです。</div>
                </div>
              </div>
              <div className="card-body flex flex-col gap-4">
                <div className="settings-row-2">
                  <div className="input-group">
                    <label className="input-label" htmlFor="daemon-interval-input">実行間隔（秒）</label>
                    <input
                      id="daemon-interval-input"
                      ref={daemonIntervalRef}
                      className={`input ${fieldErrors.daemonInterval ? 'border-red-500' : ''}`}
                      type="number"
                      min={60}
                      value={daemonInterval}
                      onChange={(e) => {
                        const v = parseInt(e.target.value, 10)
                        setDaemonInterval(Number.isNaN(v) ? 0 : v)
                        setFieldErrors((prev) => ({ ...prev, daemonInterval: undefined }))
                        markDirty()
                      }}
                    />
                    {daemonInterval >= 60 ? (
                      <p className="settings-hint">
                        {daemonInterval >= 3600
                          ? `${daemonInterval} 秒 = ${Math.floor(daemonInterval / 3600)} 時間`
                          : daemonInterval >= 60
                          ? `${daemonInterval} 秒 = ${Math.floor(daemonInterval / 60)} 分`
                          : null}
                      </p>
                    ) : null}
                    <FieldError message={fieldErrors.daemonInterval ?? null} />
                  </div>
                  <div className="input-group">
                    <label className="input-label" htmlFor="daemon-max-files-input">最大ファイル数</label>
                    <input
                      id="daemon-max-files-input"
                      ref={daemonMaxFilesRef}
                      className={`input ${fieldErrors.daemonMaxFiles ? 'border-red-500' : ''}`}
                      type="number"
                      min={1}
                      max={1000}
                      value={daemonMaxFiles}
                      onChange={(e) => {
                        const v = parseInt(e.target.value, 10)
                        setDaemonMaxFiles(Number.isNaN(v) ? 0 : v)
                        setFieldErrors((prev) => ({ ...prev, daemonMaxFiles: undefined }))
                        markDirty()
                      }}
                    />
                    <FieldError message={fieldErrors.daemonMaxFiles ?? null} />
                  </div>
                </div>
              </div>
            </div>

            {/* ── リソース制御 ── */}
            <div className="card">
              <div className="card-header">
                <div>
                  <div className="card-title">リソース制御</div>
                  <div className="card-description">
                    トークンクォータ上限（窓の自動スロットリング）。soft 到達でタスクを light モードに降格、hard 到達で低優先タスクをスキップします。0=無制限。
                  </div>
                </div>
              </div>
              <div className="card-body flex flex-col gap-4">
                <div className="settings-row-2">
                  <div className="input-group">
                    <label className="input-label" htmlFor="quota-window-input">クォータ窓（時間）</label>
                    <input
                      id="quota-window-input"
                      ref={windowHoursRef}
                      className={`input ${fieldErrors.windowHours ? 'border-red-500' : ''}`}
                      type="number"
                      min={1}
                      value={windowHours}
                      onChange={(e) => {
                        const v = parseInt(e.target.value, 10)
                        setWindowHours(Number.isNaN(v) ? 0 : v)
                        setFieldErrors((prev) => ({ ...prev, windowHours: undefined }))
                        markDirty()
                      }}
                    />
                    <p className="settings-hint">既定 5h。トークン消費の集計窓を時間単位で指定します。</p>
                    <FieldError message={fieldErrors.windowHours ?? null} />
                  </div>
                  <div className="input-group">
                    <label className="input-label" htmlFor="quota-soft-input">ソフト上限（トークン）</label>
                    <input
                      id="quota-soft-input"
                      ref={softLimitRef}
                      className={`input ${fieldErrors.softLimit ? 'border-red-500' : ''}`}
                      type="number"
                      min={0}
                      value={softLimit}
                      onChange={(e) => {
                        const v = parseInt(e.target.value, 10)
                        setSoftLimit(Number.isNaN(v) ? 0 : v)
                        setFieldErrors((prev) => ({ ...prev, softLimit: undefined }))
                        markDirty()
                      }}
                    />
                    <p className="settings-hint">0=無制限。到達でタスクを light モードに降格します。</p>
                    <FieldError message={fieldErrors.softLimit ?? null} />
                  </div>
                  <div className="input-group">
                    <label className="input-label" htmlFor="quota-hard-input">ハード上限（トークン）</label>
                    <input
                      id="quota-hard-input"
                      ref={hardLimitRef}
                      className={`input ${fieldErrors.hardLimit ? 'border-red-500' : ''}`}
                      type="number"
                      min={0}
                      value={hardLimit}
                      onChange={(e) => {
                        const v = parseInt(e.target.value, 10)
                        setHardLimit(Number.isNaN(v) ? 0 : v)
                        setFieldErrors((prev) => ({ ...prev, hardLimit: undefined }))
                        markDirty()
                      }}
                    />
                    <p className="settings-hint">0=無制限。到達で低優先タスクをスキップします。soft ≤ hard にしてください。</p>
                    <FieldError message={fieldErrors.hardLimit ?? null} />
                  </div>
                </div>
              </div>
            </div>

            {/* ── 通知設定 ── */}
            <div className="card">
              <div className="card-header">
                <div>
                  <div className="card-title">通知設定</div>
                  <div className="card-description">
                    通知の最小レベルと静音時間帯を設定します。静音開始＝終了（両方 0）は静音なし。
                  </div>
                </div>
              </div>
              <div className="card-body flex flex-col gap-4">
                <div className="settings-row-2">
                  <div className="input-group">
                    <label className="input-label" htmlFor="notify-level-select">通知 最小レベル</label>
                    <select
                      id="notify-level-select"
                      className="select"
                      value={notifyMinLevel}
                      onChange={(e) => { setNotifyMinLevel(e.target.value); markDirty() }}
                    >
                      {NOTIFICATION_LEVELS.map((lv) => (
                        <option key={lv} value={lv}>
                          {lv === 'info' ? '情報（info）' : lv === 'warn' ? '警告（warn）' : '重要（critical）'}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div className="input-group">
                    <label className="input-label" htmlFor="quiet-start-input">静音 開始（時）</label>
                    <input
                      id="quiet-start-input"
                      ref={quietStartRef}
                      className={`input ${fieldErrors.quietStart ? 'border-red-500' : ''}`}
                      type="number"
                      min={0}
                      max={23}
                      value={quietStart}
                      onChange={(e) => {
                        const v = parseInt(e.target.value, 10)
                        setQuietStart(Number.isNaN(v) ? 0 : v)
                        setFieldErrors((prev) => ({ ...prev, quietStart: undefined }))
                        markDirty()
                      }}
                    />
                    <p className="settings-hint">0〜23 時。ラップアラウンド可（例: 22 開始 6 終了 = 夜間）。</p>
                    <FieldError message={fieldErrors.quietStart ?? null} />
                  </div>
                  <div className="input-group">
                    <label className="input-label" htmlFor="quiet-end-input">静音 終了（時）</label>
                    <input
                      id="quiet-end-input"
                      ref={quietEndRef}
                      className={`input ${fieldErrors.quietEnd ? 'border-red-500' : ''}`}
                      type="number"
                      min={0}
                      max={23}
                      value={quietEnd}
                      onChange={(e) => {
                        const v = parseInt(e.target.value, 10)
                        setQuietEnd(Number.isNaN(v) ? 0 : v)
                        setFieldErrors((prev) => ({ ...prev, quietEnd: undefined }))
                        markDirty()
                      }}
                    />
                    <p className="settings-hint">0〜23 時。開始＝終了のとき静音なしとして扱います。</p>
                    <FieldError message={fieldErrors.quietEnd ?? null} />
                  </div>
                </div>
              </div>
            </div>

            {/* ── ストレージ情報 ── */}
            {storageInfo ? (
              <div className="card">
                <div className="card-header">
                  <div>
                    <div className="card-title">ストレージ情報</div>
                    <div className="card-description">{storageInfo.note}</div>
                  </div>
                </div>
                <div className="card-body flex flex-col gap-4">
                  <div className="storage-location">
                    <span className="text-muted text-sm">保存場所:</span>
                    <code className="mono text-sm">{storageInfo.platform_home}</code>
                  </div>
                  <div className="storage-table">
                    {Object.values(storageInfo.storage).map((entry) => (
                      <div key={entry.path} className="storage-row">
                        <div className="storage-label">{entry.label}</div>
                        <div className="storage-meta">
                          {entry.exists ? (
                            <>
                              <span className="badge badge-green text-xs">保存済み</span>
                              <span className="text-xs text-muted">{entry.file_count} ファイル</span>
                              <span className="text-xs text-muted">{formatBytes(entry.size_bytes)}</span>
                            </>
                          ) : (
                            <span className="badge badge-neutral text-xs">未作成</span>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            ) : null}

            {/* ── 保存ボタン ── */}
            <div className="settings-save-row">
              {isDirty ? (
                <span className="text-xs text-muted">未保存の変更があります</span>
              ) : null}
              <button
                id="save-button"
                type="button"
                className="btn btn-primary"
                disabled={saving || !!loadError}
                title={loadError ? '設定の読み込みに失敗しています。再読込してから保存してください。' : undefined}
                onClick={() => void handleSave()}
              >
                <Save size={14} />
                {saving ? '保存中…' : '設定を保存'}
              </button>
            </div>
          </form>
        ) : null}
      </div>

      {/* APIトークン消去の確認ダイアログ */}
      <ConfirmDialog
        open={confirmClearToken}
        onOpenChange={setConfirmClearToken}
        title="APIトークンを消去しますか？"
        description="ローカルに保存されたAPIトークンを削除します。次回アクセス時に認証が必要な場合は再設定してください。"
        confirmLabel="消去する"
        destructive
        onConfirm={() => {
          handleClearApiToken()
        }}
      />
    </>
  )
}
