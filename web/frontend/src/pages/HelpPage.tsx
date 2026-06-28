import { useState, type ReactNode } from 'react'
import {
  ArrowRightLeft,
  Bot,
  Building2,
  CalendarClock,
  CheckCheck,
  ChevronDown,
  ChevronRight,
  Clipboard,
  Coins,
  Database,
  HelpCircle,
  Info,
  KanbanSquare,
  LayoutDashboard,
  Lightbulb,
  Map as MapIcon,
  Rocket,
  Settings,
  Terminal,
  Wrench,
} from 'lucide-react'
import { toast } from 'sonner'

import { PageHeader } from '@/components/PageHeader'

/** ページ内で使うナビルート定数（ドリフト検出テストで参照する）。
 *  App.tsx の navGroups と 1:1 対応させること。 */
export const PAGE_SECTION_ROUTES = [
  '/dashboard',
  '/orgs',
  '/proposals',
  '/agents',
  '/handoffs',
  '/content',
  '/revenue',
  '/sessions',
  '/board',
  '/data',
  '/settings',
  '/help',
] as const

type Section = {
  id: string
  title: string
  /** ルートと1:1対応するセクションに付与（ドリフト検出用）*/
  route?: string
  content: ReactNode
}

// ─── CodeBlock ────────────────────────────────────────────────────────────────

type CodeBlockProps = {
  children: string
  /** href を渡すと a タグで開く（URL 向け） */
  href?: string
}

function CodeBlock({ children, href }: CodeBlockProps) {
  const [copied, setCopied] = useState(false)

  function handleCopy() {
    void navigator.clipboard.writeText(children).then(
      () => {
        setCopied(true)
        toast.success('コピーしました', { duration: 1500 })
        setTimeout(() => setCopied(false), 1500)
      },
      () => toast.error('コピーに失敗しました'),
    )
  }

  const codeEl = href ? (
    <a href={href} target="_blank" rel="noopener noreferrer" className="help-code-link">
      {children}
    </a>
  ) : (
    <code className="help-code">{children}</code>
  )

  return (
    <span className="help-code-wrap">
      {codeEl}
      <button
        type="button"
        aria-label={`「${children}」をコピー`}
        className="help-code-copy"
        onClick={handleCopy}
      >
        {copied ? <CheckCheck size={11} /> : <Clipboard size={11} />}
      </button>
    </span>
  )
}

// ─── Accordion ────────────────────────────────────────────────────────────────

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

// ─── Table ────────────────────────────────────────────────────────────────────

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

// ─── Overview sections ────────────────────────────────────────────────────────

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
              <strong>セットアップ</strong>
              <p>生成はローカルの <CodeBlock>claude</CodeBlock> CLI を使います。API キーは不要です。初回に一度 <CodeBlock>claude</CodeBlock> を実行してログインし、設定画面で既定モデルを選びます。</p>
            </div>
          </li>
          <li>
            <span className="help-step-num">2</span>
            <div>
              <strong>組織</strong>
              <p>テンプレートから収益モデル会社を自動構築するか、新しい組織を作成して対象リポジトリ（ワークスペース）を登録します。</p>
            </div>
          </li>
          <li>
            <span className="help-step-num">3</span>
            <div>
              <strong>対話・実行（wmux 連携・外部）</strong>
              <p>wmux の汎用チャット（<CodeBlock>pantheon up</CodeBlock> で起動）や組織チャットから、分析やゴールを自然言語で実行します。この Web GUI は監視・承認・可視化に専念します。</p>
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
  {
    id: 'wmux',
    title: '対話・実行（wmux 連携・外部）',
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
]

// ─── Page sections（サイドナビと 1:1 対応）────────────────────────────────────

const pageSections: Section[] = [
  {
    id: 'dashboard',
    route: '/dashboard',
    title: 'ダッシュボード',
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
            ['システム情報', 'claude CLI の稼働状態、既定モデル、設定取得状態を確認できます。'],
          ]}
        />
      </div>
    ),
  },
  {
    id: 'orgs',
    route: '/orgs',
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
            ['副業ポートフォリオを自動構築', '初回表示のウェルカムカードから、テンプレートで収益モデル会社（事業部・エージェント・初期KPI 付き）を作成できます。'],
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
    route: '/proposals',
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
    route: '/agents',
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
    id: 'handoffs',
    route: '/handoffs',
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
    id: 'content',
    route: '/content',
    title: 'コンテンツ予約',
    content: (
      <div className="help-prose">
        <div className="help-page-icon-row">
          <CalendarClock size={16} />
          <span>投稿ドラフトを定期生成し、PDCA で回します（コンテンツ・スケジュール）。</span>
        </div>
        <p>
          ワークスペース（組織）ごとに「どんな投稿を・どの間隔で生成するか」を登録します。生成物は
          repo 内の <strong>承認待ち下書き（content_asset 提案）</strong> として作られ、外部公開は一切しません。
          公開するかどうかは人間が承認ボタンで判断します。
        </p>
        <Table
          headers={['操作', '内容']}
          rows={[
            ['ジョブ追加', '対象組織・種類・テーマ・生成間隔を指定して定期ジョブを作成します。'],
            ['今すぐ生成', '即時に投稿ドラフトを1件生成します（承認待ち提案として保存）。'],
            ['PDCA ループ', '開始すると定期生成＋成果由来の介入提案を回し、レート制限を検知すると自動停止します。'],
          ]}
        />
      </div>
    ),
  },
  {
    id: 'revenue',
    route: '/revenue',
    title: '収益',
    content: (
      <div className="help-prose">
        <div className="help-page-icon-row">
          <Coins size={16} />
          <span>収益の集計・トラッキングを確認します。</span>
        </div>
        <p>
          組織が生み出した収益イベントを集計し、目標に対する進捗を可視化します。
          収益として集計されるのは、手動記録・CSV インポート・接続済みコレクタ経由で記録された
          実イベントのみです（確定収益）。予測・見通しは「概算」として区別表示され、確定収益には含まれません。
        </p>
        <Table
          headers={['項目', '内容']}
          rows={[
            ['収益サマリ', '全組織の収益合計・目標・達成率をカードで確認できます。'],
            ['収益イベント一覧', '日付・組織・金額・種別で収益イベントを一覧表示します。'],
            ['グラフ', '期間別の収益推移をチャートで可視化します。'],
          ]}
        />
      </div>
    ),
  },
  {
    id: 'atlas',
    route: '/atlas',
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
    route: '/sessions',
    title: 'セッション',
    content: (
      <div className="help-prose">
        <div className="help-page-icon-row">
          <LayoutDashboard size={16} />
          <span>AI の動作確認ダッシュボードです。</span>
        </div>
        <Table
          headers={['項目', '内容']}
          rows={[
            ['エージェント一覧', 'wmux 上で動く各エージェント（1エージェント=1タブ）の状態・終了コード・claude 出力ログをライブ確認します。'],
            ['接続状態', 'claude / wmux / driver の接続状態を表示します。'],
            ['自動再開', 'エージェントが Claude のレート制限に当たると rate_limited 状態になり、リセット時刻に達すると自動的に再開されます。'],
          ]}
        />
      </div>
    ),
  },
  {
    id: 'board',
    route: '/board',
    title: '作業ボード',
    content: (
      <div className="help-prose">
        <div className="help-page-icon-row">
          <KanbanSquare size={16} />
          <span>人間用の作業ボードです。</span>
        </div>
        <Table
          headers={['項目', '内容']}
          rows={[
            ['Kanban ビュー', 'キュー / 実行中 / 失敗 / 完了 の4列でタスクを管理します。'],
            ['タスク起票', 'AI ループの外から人間がタスクを起票できます。'],
            ['キャンセル', '実行中のタスクを人間の判断でキャンセルできます。'],
          ]}
        />
      </div>
    ),
  },
  {
    id: 'data',
    route: '/data',
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
    route: '/settings',
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
            ['実行ランタイム', 'ローカルの claude CLI を使用します（API キー不要）。CLI の稼働状態を表示します。'],
            ['既定モデル', 'claude CLI で利用可能なモデル（Opus / Sonnet / Haiku）から既定を選べます。'],
            ['デーモン設定', '実行間隔と最大ファイル数を設定できます。'],
            ['ストレージ情報', '設定ファイルの保存先を確認できます。'],
          ]}
        />
      </div>
    ),
  },
  {
    id: 'help',
    route: '/help',
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
            ['設定・CLI・トラブル', '起動とインストール、claude CLI、CLI コマンド、よくある問題を確認できます。'],
          ]}
        />
      </div>
    ),
  },
]

// ─── Advanced sections ────────────────────────────────────────────────────────

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
          <CodeBlock href="http://localhost:7860">http://localhost:7860</CodeBlock> が既定ブラウザで開き、同時に wmux に汎用チャットタブが
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
    id: 'runtime',
    title: '実行ランタイム（claude CLI）',
    content: (
      <div className="help-prose">
        <p>
          Pantheon の生成（分析・チャット・コンテンツ生成）はすべてローカルの
          <CodeBlock>claude</CodeBlock> CLI を通します。<strong>ホスト型 LLM の API キーは使いません。</strong>
          初回に一度 <CodeBlock>claude</CodeBlock> を実行してログインすれば利用できます。
        </p>
        <Table
          headers={['項目', '内容']}
          rows={[
            ['認証', '一度 claude を実行してログイン（API キーの入力欄はありません）。'],
            ['既定モデル', '設定画面で Opus / Sonnet / Haiku から選択します。'],
            ['CLI が無い場合', '分析・生成は 503 になり、偽のデータは生成しません。GUI の閲覧機能は動作します。'],
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

// ─── HelpPage ─────────────────────────────────────────────────────────────────

export function HelpPage() {
  const [activeTab, setActiveTab] = useState<'overview' | 'pages' | 'advanced'>('overview')

  const tabs = [
    { id: 'overview' as const, label: '概要', icon: Info },
    { id: 'pages' as const, label: '各画面の使い方', icon: LayoutDashboard },
    { id: 'advanced' as const, label: '設定・CLI・トラブル', icon: Wrench },
  ]

  return (
    <div className="page-content">
      <PageHeader
        title="ヘルプ"
        subtitle="現在の画面構成に合わせた Pantheon の操作ガイドです。"
      />

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
