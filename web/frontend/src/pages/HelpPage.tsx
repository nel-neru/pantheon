import { useState, type ReactNode } from 'react'
import {
  Bot,
  Building2,
  ChevronDown,
  ChevronRight,
  Database,
  HelpCircle,
  Info,
  LayoutDashboard,
  Lightbulb,
  MessageSquare,
  Search,
  Settings,
  Target,
  Wrench,
} from 'lucide-react'

type Section = {
  id: string
  title: string
  content: ReactNode
}

function Accordion({ sections }: { sections: Section[] }) {
  const [open, setOpen] = useState<string | null>(sections[0]?.id ?? null)

  return (
    <div className="help-accordion">
      {sections.map((section) => (
        <div key={section.id} className={`help-accordion-item ${open === section.id ? 'open' : ''}`}>
          <button
            type="button"
            className="help-accordion-trigger"
            onClick={() => setOpen(open === section.id ? null : section.id)}
          >
            <span>{section.title}</span>
            {open === section.id ? <ChevronDown size={15} /> : <ChevronRight size={15} />}
          </button>
          {open === section.id ? <div className="help-accordion-body">{section.content}</div> : null}
        </div>
      ))}
    </div>
  )
}

function CodeBlock({ children }: { children: string }) {
  return <code className="help-code">{children}</code>
}

function Table({ headers, rows }: { headers: string[]; rows: string[][] }) {
  return (
    <div className="help-table-wrap">
      <table className="help-table">
        <thead>
          <tr>
            {headers.map((header) => (
              <th key={header}>{header}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={`${row[0]}-${index}`}>
              {row.map((cell, cellIndex) => (
                <td key={`${cell}-${cellIndex}`}>{cell}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

const overviewSections: Section[] = [
  {
    id: 'overview',
    title: 'RepoCorp AI とは',
    content: (
      <div className="help-prose">
        <p>
          <strong>あなたのアイデアと意図を入力するだけで、AI組織が自律的に計画・実行・改善を担うプラットフォーム</strong>
          です。
        </p>
        <p>
          <strong>一人でも、組織で動く。</strong>
        </p>
        <p>
          自然言語の指示を起点に、組織の作成、リポジトリ分析、ゴール実行、改善提案の承認、
          データ管理までをひとつの GUI で進められます。
        </p>
      </div>
    ),
  },
  {
    id: 'concepts',
    title: '主要概念',
    content: (
      <div className="help-prose">
        <p>RepoCorp AI は階層化された AI 組織として動作します。</p>
        <div className="help-concept-grid">
          <div className="help-concept-card">
            <div className="help-concept-label">Core</div>
            <div className="help-concept-desc">プラットフォーム全体の基盤。設定、状態管理、オーケストレーションを支えます。</div>
          </div>
          <div className="help-concept-card">
            <div className="help-concept-label">Organization</div>
            <div className="help-concept-desc">目的やリポジトリ単位で作る AI 組織です。分析や改善提案の主体になります。</div>
          </div>
          <div className="help-concept-card">
            <div className="help-concept-label">Division</div>
            <div className="help-concept-desc">大きな役割を分担する上位レイヤーです。分析、実装、レビューなどの機能を束ねます。</div>
          </div>
          <div className="help-concept-card">
            <div className="help-concept-label">Team</div>
            <div className="help-concept-desc">Division の中で実際のタスクを担当する実働ユニットです。専門領域ごとに編成されます。</div>
          </div>
          <div className="help-concept-card">
            <div className="help-concept-label">Specialist Agent</div>
            <div className="help-concept-desc">個別スキルを持つ専門エージェントです。役割に応じて分析や提案生成を担当します。</div>
          </div>
        </div>
      </div>
    ),
  },
  {
    id: 'flow',
    title: '使い始めの流れ',
    content: (
      <div className="help-prose">
        <ol className="help-steps">
          <li>
            <span className="help-step-num">1</span>
            <div>
              <strong>設定</strong>
              <p>設定画面で LLM プロバイダー、モデル、API キーを入力します。</p>
            </div>
          </li>
          <li>
            <span className="help-step-num">2</span>
            <div>
              <strong>組織</strong>
              <p>サンプル組織で始めるか、新しい組織を作成して対象リポジトリを登録します。</p>
            </div>
          </li>
          <li>
            <span className="help-step-num">3</span>
            <div>
              <strong>分析 / ゴール</strong>
              <p>分析画面で改善提案の材料を作るか、ゴール画面で達成したい目的を自然言語で実行します。</p>
            </div>
          </li>
          <li>
            <span className="help-step-num">4</span>
            <div>
              <strong>改善と確認</strong>
              <p>改善提案で承認し、プラットフォームとデータ管理で状態や履歴を確認します。</p>
            </div>
          </li>
        </ol>
      </div>
    ),
  },
]

const pageSections: Section[] = [
  {
    id: 'chat',
    title: 'チャット',
    content: (
      <div className="help-prose">
        <div className="help-page-icon-row">
          <MessageSquare size={16} />
          <span>自然言語で AI 組織に依頼する入口です。</span>
        </div>
        <p>自由文で指示を出せるほか、スラッシュコマンドを使って操作を素早く開始できます。</p>
        <Table
          headers={['コマンド', '説明']}
          rows={[
            ['/help', 'ヘルプを表示します。'],
            ['/analyze', '分析ワークフローを開始します。'],
            ['/goal', 'ゴール実行の流れを呼び出します。'],
            ['/proposals', '改善提案を確認します。'],
            ['/agents', 'エージェント一覧を確認します。'],
            ['/status', 'プラットフォーム状態を確認します。'],
          ]}
        />
        <p><CodeBlock>Enter</CodeBlock> で送信、<CodeBlock>Shift+Enter</CodeBlock> で改行です。</p>
      </div>
    ),
  },
  {
    id: 'orgs',
    title: '組織',
    content: (
      <div className="help-prose">
        <div className="help-page-icon-row">
          <Building2 size={16} />
          <span>組織の作成・管理・削除を行います。</span>
        </div>
        <Table
          headers={['操作', '内容']}
          rows={[
            ['サンプル組織で始める', '初回表示のウェルカムカードからサンプル組織を作成できます。'],
            ['新規組織', '組織名、目的、リポジトリパスを入力して組織を追加します。'],
            ['詳細を見る', '詳細スライドパネルで説明、目的、リポジトリパス、状態、提案を確認できます。'],
            ['編集 / 削除', 'カードまたは詳細パネルから組織情報の更新や削除を行えます。'],
          ]}
        />
      </div>
    ),
  },
  {
    id: 'analyze',
    title: '分析',
    content: (
      <div className="help-prose">
        <div className="help-page-icon-row">
          <Search size={16} />
          <span>リポジトリを分析して改善提案を生成します。</span>
        </div>
        <Table
          headers={['項目', '内容']}
          rows={[
            ['対象組織', '分析対象の組織を選択します。'],
            ['最大ファイル数', '1 回の分析で確認するファイル数の上限を指定できます。'],
            ['分析を実行', '開始するとリアルタイムログが流れます。'],
            ['分析結果', '完了後に確認ファイル数と生成提案数が表示され、提案画面へ移動できます。'],
          ]}
        />
      </div>
    ),
  },
  {
    id: 'goals',
    title: 'ゴール',
    content: (
      <div className="help-prose">
        <div className="help-page-icon-row">
          <Target size={16} />
          <span>自然言語でゴールを入力して実行します。</span>
        </div>
        <Table
          headers={['操作', '内容']}
          rows={[
            ['ゴールテキスト', '達成したい内容を自然言語で入力します。'],
            ['対象組織', '特定組織またはプラットフォーム全体を対象にできます。'],
            ['実行', 'クリックするとリアルタイムログが表示されます。'],
            ['結果 / 履歴', '直近の結果と過去の実行履歴をページ内で確認できます。'],
          ]}
        />
      </div>
    ),
  },
  {
    id: 'proposals',
    title: '改善提案',
    content: (
      <div className="help-prose">
        <div className="help-page-icon-row">
          <Lightbulb size={16} />
          <span>分析結果から生成された提案をレビューします。</span>
        </div>
        <Table
          headers={['機能', '内容']}
          rows={[
            ['組織切り替え', '対象組織ごとの提案一覧を表示します。'],
            ['ステータスフィルター', '未処理、承認済み、却下済み、すべてで絞り込みできます。'],
            ['カテゴリ / 優先度', '各提案カードでカテゴリと優先度を確認できます。'],
            ['承認 / 却下', '承認すると提案が実行フェーズへ進み、却下で状態を更新できます。'],
          ]}
        />
      </div>
    ),
  },
  {
    id: 'agents',
    title: 'エージェント',
    content: (
      <div className="help-prose">
        <div className="help-page-icon-row">
          <Bot size={16} />
          <span>登録されている Specialist Agent とスキルを確認します。</span>
        </div>
        <Table
          headers={['項目', '内容']}
          rows={[
            ['登録済みエージェント', '名前、capability ID、説明、スキルをカードで確認できます。'],
            ['スキルレジストリ', 'スキル名、ペルソナ、注力領域、説明を一覧表示します。'],
            ['オーケストレーション分析', 'タスク種別ごとの推奨エージェントを確認できます。'],
          ]}
        />
      </div>
    ),
  },
  {
    id: 'dashboard',
    title: 'プラットフォーム',
    content: (
      <div className="help-prose">
        <div className="help-page-icon-row">
          <LayoutDashboard size={16} />
          <span>システム全体のステータスとヘルスを確認します。</span>
        </div>
        <Table
          headers={['項目', '内容']}
          rows={[
            ['プラットフォーム状態', 'LLM 設定状態、組織数、アクティブ数、バランスを表示します。'],
            ['組織一覧', '組織ごとのヘルスと提案数を確認できます。'],
            ['デーモン状態', '自動改善プロセスの起動、停止、PID、ログパスを管理します。'],
            ['システム情報', 'LLM プロバイダー、モデル、設定取得状態を確認できます。'],
          ]}
        />
      </div>
    ),
  },
  {
    id: 'data',
    title: 'データ管理',
    content: (
      <div className="help-prose">
        <div className="help-page-icon-row">
          <Database size={16} />
          <span>ゴール履歴とナレッジを管理します。</span>
        </div>
        <Table
          headers={['タブ', '内容']}
          rows={[
            ['ゴール履歴', '過去のゴール実行履歴を確認し、不要な履歴はクリアできます。'],
            ['ナレッジ', 'knowledge 配下のファイルを一覧表示し、クリックでプレビューできます。'],
            ['編集', '選択したナレッジファイルをテキストエディタで編集して保存できます。'],
            ['新規作成 / 削除', '空のナレッジファイルを作成し、不要なファイルは削除できます。'],
          ]}
        />
      </div>
    ),
  },
  {
    id: 'settings',
    title: '設定',
    content: (
      <div className="help-prose">
        <div className="help-page-icon-row">
          <Settings size={16} />
          <span>LLM、デーモン、保存先設定を管理します。</span>
        </div>
        <Table
          headers={['項目', '内容']}
          rows={[
            ['LLM プロバイダー', 'Anthropic / OpenAI / Groq / GitHub Models (無料) / Google Gemini を選択できます。'],
            ['モデル一覧', 'プロバイダー変更時に利用可能モデルを自動取得します。'],
            ['API キー', 'マスク表示されたキーを確認し、表示切り替えしながら更新できます。'],
            ['デーモン設定', '実行間隔と最大ファイル数を設定できます。'],
            ['ストレージ情報', '設定ファイルの保存先を確認できます。'],
          ]}
        />
      </div>
    ),
  },
  {
    id: 'help',
    title: 'ヘルプ',
    content: (
      <div className="help-prose">
        <div className="help-page-icon-row">
          <HelpCircle size={16} />
          <span>このページ自身の説明です。</span>
        </div>
        <Table
          headers={['タブ', '内容']}
          rows={[
            ['概要', 'RepoCorp AI の考え方と基本フローをまとめています。'],
            ['各画面の使い方', '全 10 ページの用途と操作ポイントを確認できます。'],
            ['設定・CLI・トラブル', 'API キー取得先、CLI コマンド、よくある問題を確認できます。'],
          ]}
        />
      </div>
    ),
  },
]

const advancedSections: Section[] = [
  {
    id: 'providers',
    title: 'LLM プロバイダー設定',
    content: (
      <div className="help-prose">
        <p>
          設定画面では API キーが設定済みのプロバイダーから最新モデル一覧を取得できます。
          各プロバイダーの「対応機能」(ツール呼び出し / JSONモード / ストリーミング / 文脈長) も表示され、
          API キーさえあればどのプロバイダーでも全機能が動作します（未対応項目は内部で安全に代替されます）。
        </p>
        <Table
          headers={['プロバイダー', 'API キー取得先', '補足']}
          rows={[
            ['Anthropic', 'console.anthropic.com', 'Claude 系モデルを利用します。'],
            ['OpenAI', 'platform.openai.com/api-keys', 'GPT 系モデルを利用します。'],
            ['Groq', 'console.groq.com', '無料枠があります。'],
            ['GitHub Models (無料)', 'github.com/settings/tokens', 'GITHUB_TOKEN を設定して利用します。'],
            ['Google Gemini', 'aistudio.google.com/app/apikey', '無料枠があります。'],
          ]}
        />
      </div>
    ),
  },
  {
    id: 'self-improve',
    title: 'Core 自己改善（実験的）',
    content: (
      <div className="help-prose">
        <p>
          改善提案画面の「Core 自己改善」パネルから、RepoCorp 自身のコードを契約中の任意の LLM で改善できます。
          内蔵エージェントが対象ファイルを編集し、既存テストで検証（必要なら反復）してから、
          検証済みの変更を「人間承認待ち」の改善提案として登録します（作業ツリーへは自動適用しません）。
        </p>
        <Table
          headers={['ステップ', '内容']}
          rows={[
            ['1. 入力', '対象ファイル(リポジトリ相対パス)と改善指示を入力'],
            ['2. 検証', 'LLM が編集 → 既存テスト実行 → 失敗時は自動で反復'],
            ['3. 提案', '検証済み差分を人間承認待ちの提案として登録 (PolicyEngine)'],
            ['4. 承認', '提案を承認すると既存フローでブランチ/PR が作成されます'],
          ]}
        />
      </div>
    ),
  },
  {
    id: 'terminal',
    title: '埋め込みターミナル & 実行モード (API/CLI)',
    content: (
      <div className="help-prose">
        <p>
          「ターミナル」ページに cmux 風のワークスペースを埋め込んでいます。各ワークスペースは
          実シェル(PTY)で、縦タブに git ブランチ・作業ディレクトリ・状態が表示され、エージェントが
          入力待ちになると青いリングで通知します（localhost 限定）。
        </p>
        <Table
          headers={['実行モード', '説明']}
          rows={[
            ['API モード', '内蔵のプロバイダー非依存エージェント (core/llm) で実行する。'],
            ['CLI モード', '導入済みの外部コーディングCLI (Claude Code / Codex / Gemini / Aider / OpenCode) をターミナルのワークスペースで起動する。'],
          ]}
        />
        <p>
          実行モードと既定 CLI は設定画面で切り替えられます。ターミナルの「新規ワークスペース」から
          シェルや各 CLI エージェントを起動できます（未インストールの CLI は選択不可で導入方法が表示されます）。
        </p>
      </div>
    ),
  },
  {
    id: 'cli',
    title: 'CLI の使い方',
    content: (
      <div className="help-prose">
        <p>Web GUI とあわせて CLI からも主要操作を実行できます。</p>
        <Table
          headers={['コマンド', '説明']}
          rows={[
            ['python main.py serve', 'サーバーを起動します。'],
            ['python main.py chat', 'CLI チャットを開始します。'],
            ['python main.py analyze', 'CLI から分析を実行します。'],
          ]}
        />
      </div>
    ),
  },
  {
    id: 'troubleshooting',
    title: 'トラブルシューティング',
    content: (
      <div className="help-prose">
        <Table
          headers={['症状', '対処法']}
          rows={[
            ['設定を取得できませんでした', 'サーバーを再起動してください: python main.py serve'],
            ['API キーが未設定', '設定画面で API キーを入力して保存してください。'],
            ['プラットフォーム画面が表示されない', 'サーバーが起動しているか確認してください。'],
          ]}
        />
      </div>
    ),
  },
]

export function HelpPage() {
  const [activeTab, setActiveTab] = useState<'overview' | 'pages' | 'advanced'>('overview')

  const tabs = [
    { id: 'overview' as const, label: '概要', icon: Info },
    { id: 'pages' as const, label: '各画面の使い方', icon: LayoutDashboard },
    { id: 'advanced' as const, label: '設定・CLI・トラブル', icon: Wrench },
  ]

  return (
    <div className="page-content">
      <div className="page-header">
        <h1 className="page-title">ヘルプ</h1>
        <p className="page-subtitle">現在の画面構成に合わせた RepoCorp AI の操作ガイドです。</p>
      </div>

      <div className="help-tabs">
        {tabs.map((tab) => {
          const Icon = tab.icon
          return (
            <button
              key={tab.id}
              type="button"
              className={`help-tab ${activeTab === tab.id ? 'active' : ''}`}
              onClick={() => setActiveTab(tab.id)}
            >
              <Icon size={14} />
              {tab.label}
            </button>
          )
        })}
      </div>

      <div className="help-body">
        {activeTab === 'overview' ? <Accordion sections={overviewSections} /> : null}
        {activeTab === 'pages' ? <Accordion sections={pageSections} /> : null}
        {activeTab === 'advanced' ? <Accordion sections={advancedSections} /> : null}
      </div>
    </div>
  )
}
