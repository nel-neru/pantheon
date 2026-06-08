import { useState, type ReactNode } from 'react'
import {
  ArrowRightLeft,
  Bot,
  Building2,
  ChevronDown,
  ChevronRight,
  Database,
  HelpCircle,
  Info,
  LayoutDashboard,
  Lightbulb,
  Map as MapIcon,
  Rocket,
  Settings,
  Terminal,
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
    title: 'Pantheon とは',
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
        <p>Pantheon は階層化された AI 組織として動作します。</p>
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
              <strong>対話・実行（wmux）</strong>
              <p>wmux の汎用チャット（pantheon up で起動）や組織チャットから、分析やゴールを自然言語で実行します。</p>
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
    id: 'workspace',
    title: '対話・実行（wmux）',
    content: (
      <div className="help-prose">
        <div className="help-page-icon-row">
          <Terminal size={16} />
          <span>チャットと実行（分析・ゴール・適用）は wmux のタブで行います。</span>
        </div>
        <p>
          この Web GUI は<strong>監視・可視化・承認・ガイド</strong>に専念し、AI との対話や
          実行系の操作は wmux 側に集約しています。<CodeBlock>pantheon up</CodeBlock>（exe の
          ダブルクリックと同じ）で、Web GUI と一緒に wmux の「汎用チャット」タブが起動します。
        </p>
        <Table
          headers={['やりたいこと', '操作']}
          rows={[
            ['汎用チャット', 'pantheon up で起動する Pantheon · chat タブ、または端末で pantheon chat。'],
            ['組織チャット', 'pantheon chat --org <組織名> でその組織スコープのタブを開きます。'],
            ['分析・ゴール実行', 'チャットから /analyze や /goal を実行すると wmux にエージェントタブが生えます。'],
            ['進捗の確認', 'この GUI の「セッション」「プラットフォーム」でライブ監視します。'],
          ]}
        />
        <p>チャットで使える主なスラッシュコマンド:</p>
        <Table
          headers={['コマンド', '説明']}
          rows={[
            ['/help', 'ヘルプを表示します。'],
            ['/analyze', 'リポジトリ分析を開始します。'],
            ['/goal', 'ゴール実行を呼び出します。'],
            ['/proposals', '改善提案を確認します。'],
            ['/agents', 'エージェント一覧を確認します。'],
            ['/status', 'プラットフォーム状態を確認します。'],
          ]}
        />
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
    id: 'handoffs',
    title: '引き渡し',
    content: (
      <div className="help-prose">
        <div className="help-page-icon-row">
          <ArrowRightLeft size={16} />
          <span>組織をまたぐ引き渡し（handoff）を人間の承認ボタンで進めます。</span>
        </div>
        <p>
          「集客 → 販売 → 収益化」のように複数組織を繋ぐフライホイールの橋渡しです。すべての
          引き渡しは承認ゲート（human-in-the-loop）を通ります。
        </p>
        <Table
          headers={['操作', '内容']}
          rows={[
            ['一覧', '送り手・受け手・状態（承認待ち / 承認済み / 消費済み / 却下）で確認します。'],
            ['承認 / 却下', '承認待ちの引き渡しをボタンで承認・却下できます。'],
            ['自動ブリーフ', '承認すると受け手組織にブリーフ提案を自動生成します。'],
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
    id: 'atlas',
    title: 'Atlas',
    content: (
      <div className="help-prose">
        <div className="help-page-icon-row">
          <MapIcon size={16} />
          <span>リポジトリ構造を読み取り専用で可視化します（生成 AI 非依存）。</span>
        </div>
        <Table
          headers={['可視化', '内容']}
          rows={[
            ['依存グラフ', 'モジュール間の import 依存関係を図示します。'],
            ['使用フロー', '主要な操作の流れ（フローカタログ）を確認できます。'],
            ['CLI コマンド木', 'pantheon の全サブコマンド構造を一覧します。'],
            ['API ルートマップ', 'FastAPI の REST / WebSocket ルートを確認できます。'],
            ['サブシステム', 'CLI / Web API / Frontend / Agents などの構成を俯瞰します。'],
          ]}
        />
      </div>
    ),
  },
  {
    id: 'sessions',
    title: 'セッション / 作業ボード',
    content: (
      <div className="help-prose">
        <div className="help-page-icon-row">
          <LayoutDashboard size={16} />
          <span>AI の動作確認ダッシュボードと、人間用の作業ボードです。</span>
        </div>
        <Table
          headers={['画面', '内容']}
          rows={[
            ['セッション (/sessions)', 'wmux 上で動く各エージェント（1エージェント=1タブ）の状態・終了コード・claude 出力ログをライブ確認します。claude/wmux/driver の接続状態も表示します。'],
            ['作業ボード (/board)', 'キュー / 実行中 / レビュー / 完了 の Kanban で、AI ループの外から人間がタスクを起票・キャンセルできます。'],
            ['自動再開', 'エージェントが Claude のレート制限に当たると rate_limited 状態になり、リセット時刻に達すると自動的に再開されます。'],
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
            ['概要', 'Pantheon の考え方と基本フローをまとめています。'],
            ['各画面の使い方', '各画面の用途と操作ポイントを確認できます。'],
            ['設定・CLI・トラブル', 'API キー取得先、CLI コマンド、よくある問題を確認できます。'],
          ]}
        />
      </div>
    ),
  },
]

const advancedSections: Section[] = [
  {
    id: 'launch',
    title: '起動とインストール',
    content: (
      <div className="help-prose">
        <div className="help-page-icon-row">
          <Rocket size={16} />
          <span>exe をダブルクリックすれば GUI が起動し、ブラウザが自動で開きます。</span>
        </div>
        <p>
          Pantheon は <CodeBlock>Pantheon.exe</CodeBlock> 一つで GUI も CLI も使えます。引数なしで実行
          （ダブルクリック）すると<strong>フル起動（up）</strong>: Web GUI（監視）が立ち上がって
          <CodeBlock>http://localhost:7860</CodeBlock> が既定ブラウザで開き、同時に wmux に汎用チャットタブが
          起動します。
        </p>
        <Table
          headers={['起動方法', '内容']}
          rows={[
            ['ダブルクリック', 'フル起動（up）: GUI 監視＋ブラウザ＋wmux 汎用チャット（引数なし実行と同じ）。'],
            ['Pantheon.exe up', 'フル起動。--no-browser / --no-wmux / --port を指定できます。'],
            ['Pantheon.exe serve', 'Web GUI のみ起動。--port でポート変更、--no-browser で自動オープン無効。'],
            ['Pantheon.exe chat [--org N]', 'CLI チャットを開始（claude が必要）。--org で組織スコープ。'],
            ['インストーラ', 'Pantheon-Setup.exe を実行するとスタートメニューに登録されます。'],
          ]}
        />
        <p>
          生成機能（分析・チャット・改善適用）には外部の <CodeBlock>claude</CodeBlock> CLI が必要です。
          初回のみ <CodeBlock>claude</CodeBlock> を実行してログインしてください。GUI・閲覧機能は claude
          なしでも動作します。詳細は <CodeBlock>docs/GUIDE.md</CodeBlock> を参照してください。
        </p>
      </div>
    ),
  },
  {
    id: 'providers',
    title: 'LLM プロバイダー設定',
    content: (
      <div className="help-prose">
        <p>設定画面では API キーが設定済みのプロバイダーから最新モデル一覧を取得できます。</p>
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
    id: 'cli',
    title: 'CLI の使い方',
    content: (
      <div className="help-prose">
        <div className="help-page-icon-row">
          <Terminal size={16} />
          <span>同じ実行体から CLI も使えます（exe は Pantheon.exe、ソース実行は pantheon）。</span>
        </div>
        <Table
          headers={['コマンド', '説明']}
          rows={[
            ['Pantheon.exe init', 'プラットフォームを初期化します（初回のみ）。'],
            ['Pantheon.exe serve', 'Web GUI を起動します（--port / --no-browser 指定可）。'],
            ['Pantheon.exe chat', 'CLI チャットを開始します。'],
            ['Pantheon.exe analyze --org-name N', 'リポジトリを分析して提案を生成します。'],
            ['Pantheon.exe approve <id> --org-name N', '提案を承認して適用します。'],
            ['Pantheon.exe doctor', '健康診断（claude 検出など）。--fix で自動修復。'],
          ]}
        />
        <p>全コマンドは <CodeBlock>Pantheon.exe --help</CodeBlock> で確認できます。</p>
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
            ['「Claude Code CLI が必要」で止まる', 'claude をインストールし、一度 claude を実行してログイン。Pantheon.exe doctor で確認。'],
            ['ポートが使用中', 'Pantheon.exe serve --port 8080 のように別ポートで起動してください。'],
            ['ブラウザが自動で開かない', '表示された http://localhost:7860 を手動で開いてください。'],
            ['GUI は出るが分析・チャットが失敗', 'ほぼ claude 未ログインです。claude を実行して認証を確認してください。'],
            ['設定を取得できない / 画面が出ない', 'サーバーを再起動してください: Pantheon.exe serve'],
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
        <p className="page-subtitle">現在の画面構成に合わせた Pantheon の操作ガイドです。</p>
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
