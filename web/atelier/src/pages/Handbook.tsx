import { useState, type ReactNode } from 'react'

import { ArrowIcon } from '@/components/Icon'
import { Exhibit, Plate, Tag } from '@/components/ui'
import { cn } from '@/lib/cn'
import { pad2 } from '@/lib/format'

type Mode = 'web' | 'cli'

// ============================================================================
// Pantheon Handbook — 収益化の実務マニュアル
// Pantheon の内部を知らなくても、これ1枚で「お金を生む作業」が最後まで回せる。
// 重要な前提: Pantheon は「下書き工場」。承認済みの Markdown 下書きをリポジトリに
// 書き出すところまでが自動で、note / X / YouTube への公開は人間が手動で行う
// （現行 main にライブ自動投稿は無い）。
// ============================================================================

export function Handbook() {
  const [mode, setMode] = useState<Mode>('web')

  return (
    <>
      <Exhibit
        index={6}
        kicker="The Handbook"
        title={
          <>
            稼ぐための、<em>作業書。</em>
          </>
        }
        lede="Pantheon が内部で何をしているか知らなくても、この一冊で収益化の作業を最後まで回せます。全体像 → WEB 操作編 / CLI 操作編 → 24時間運用の TIPS の順。"
      />

      {/* 最重要の前提 */}
      <Callout tone="gold" title="まず知るべき1点 — Pantheon は「下書き工場」です">
        <p>
          Pantheon が自動で行うのは「ネタ集め → 下書き生成 → 承認待ちに並べる」まで。承認すると
          下書きが各組織の Git ワークスペースに <K>content/*.md</K> として書き出されます。
          <b className="text-gold"> note / X / YouTube への公開は、あなたが手動で行います</b>
          （現行版にライブ自動投稿はありません）。つまり「承認 = 出荷ゲート」、最後の貼り付けは人間の仕事です。
        </p>
      </Callout>

      {/* 全体像 */}
      <SectionLabel n={1} title="全体像 — 収益化のループ" note="the flywheel" />
      <Plate className="rise">
        <ol className="flex flex-col gap-0">
          {FLOW.map((f, i) => (
            <li
              key={f.t}
              className="flex gap-4 border-t border-[color:var(--line)] py-4 first:border-t-0"
            >
              <span className="numeral text-2xl text-gold w-8 shrink-0">{pad2(i + 1)}</span>
              <div>
                <div className="serif text-lg leading-snug">{f.t}</div>
                <div className="text-dim text-sm mt-1">{f.d}</div>
              </div>
            </li>
          ))}
        </ol>
        <p className="text-faint mono text-[10px] tracking-wider mt-5">
          集客 → 販売 → 収益化 の各 hop に「人間の承認」が必ず1枚入る。これが暴走しない仕組み。
        </p>
      </Plate>

      {/* 前提 */}
      <SectionLabel n={2} title="最初の準備（1回だけ）" note="prerequisites" />
      <div className="grid grid-cols-1 gap-5 md:grid-cols-3">
        <Plate className="rise">
          <Tag tone="gold">1</Tag>
          <h3 className="serif text-lg mt-3">claude にログイン</h3>
          <p className="text-dim text-sm mt-2">
            生成は全て<b>ローカルの claude CLI</b> 経由（API キーは不要・使いません）。一度だけ：
          </p>
          <Cmd>{`claude`}</Cmd>
          <p className="text-faint text-xs mt-2">未ログインだと生成系コマンドは中断します。</p>
        </Plate>
        <Plate className="rise">
          <Tag tone="gold">2</Tag>
          <h3 className="serif text-lg mt-3">プラットフォーム初期化</h3>
          <p className="text-dim text-sm mt-2">
            グローバル状態（<K>~/.pantheon</K>）と Meta 組織を作成。冪等です：
          </p>
          <Cmd>{`pantheon init`}</Cmd>
        </Plate>
        <Plate className="rise">
          <Tag tone="gold">3</Tag>
          <h3 className="serif text-lg mt-3">Windows の注意</h3>
          <p className="text-dim text-sm mt-2">
            <K>python</K> / <K>node</K> は既定で PATH に無し。アプリ本体は <K>pantheon ...</K>
            （または <K>Pantheon.exe</K>）で実行。テスト等の素の Python は venv を使用：
          </p>
          <Cmd>{`.\\.venv\\Scripts\\python.exe -m pytest`}</Cmd>
        </Plate>
      </div>

      {/* モード切替 */}
      <SectionLabel n={3} title="操作編" note="step by step" />
      <div className="mb-7 flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-2" role="tablist" aria-label="操作モード">
          {(['web', 'cli'] as Mode[]).map((m) => (
            <button
              key={m}
              type="button"
              role="tab"
              aria-selected={mode === m}
              className={cn('btn', mode === m && 'btn-gold')}
              onClick={() => setMode(m)}
            >
              {m === 'web' ? 'WEB 操作編' : 'CLI 操作編'}
            </button>
          ))}
        </div>
        <span className="text-faint mono text-[10px] tracking-wider">
          {mode === 'web'
            ? 'ブラウザのダッシュボードで進める'
            : 'ターミナルで完結・自動化向き'}
        </span>
      </div>

      {mode === 'web' ? <WebFlow /> : <CliFlow />}

      {/* 承認ゲート */}
      <SectionLabel n={4} title="承認ゲート — 唯一の出荷スイッチ" note="the only gate" />
      <Callout tone="ice" title="何が自動で、何が承認待ちか">
        <p>
          すべての提案は <K>PolicyEngine</K> を通ります。
          <b> content_asset（記事・投稿の下書き）/ 引き渡し / 外部アクション / 構造変更 / セキュリティ系は常に「人間の承認が必要」</b>
          で、自動承認には決して落ちません。自動承認されるのは低リスクな整形・ドキュメント・コメント程度の小修正のみ。
        </p>
        <p className="mt-2">
          承認すると即「適用」されます。content_asset と構造提案は専用エグゼキュータがリポジトリ内に
          ファイルを書き出し（リポジトリ外への書込はガードで拒否）、コード提案はブランチ / PR を作成します。
        </p>
      </Callout>

      {/* 成果物 */}
      <SectionLabel n={5} title="成果物の正体と、手動公開" note="what you ship" />
      <Callout tone="gold" title="最終成果物 = Git 内の Markdown 下書き">
        <p>
          手に入るのは、各組織のワークスペースにコミットされた下書きです：
        </p>
        <ul className="mt-2 flex flex-col gap-1 text-sm">
          <li>
            <K>content/brief-note-*.md</K> — note 有料記事の骨子（無料エリア3要素＋価格ティア）
          </li>
          <li>
            <K>content/brief-affiliate-*.md</K> — アフィリエイト原稿（<b>#PR 表記</b>・A8.net 規約対応）
          </li>
          <li>
            <K>content/draft-*.md</K> / <K>content/content_brief-*.md</K> — SNS 投稿・集客ブリーフ
          </li>
        </ul>
        <p className="mt-3">
          これらを <b className="text-gold">あなたが note / X / YouTube に貼って公開</b>すると収益化が始まります。
          <K>monetization_lead</K> 系の下書きには景表法（ステマ規制）対応の <K>#PR</K> と A8.net コンプラ文が
          自動で入ります — 手動公開時に消さないでください。
        </p>
      </Callout>

      {/* TIPS */}
      <SectionLabel n={6} title="24時間 無人運用の TIPS" note="run it for days" />
      <div className="grid grid-cols-1 gap-5 md:grid-cols-2">
        {TIPS.map((t) => (
          <Plate key={t.t} className="rise">
            <div className="flex items-center gap-2">
              <Tag tone={t.tone}>{t.tag}</Tag>
            </div>
            <h3 className="serif text-lg mt-3">{t.t}</h3>
            <div className="text-dim text-sm mt-2 flex flex-col gap-2">{t.body}</div>
          </Plate>
        ))}
      </div>

      {/* ハマりどころ */}
      <SectionLabel n={7} title="ハマりどころ（先に知っておく）" note="gotchas" />
      <Plate className="rise">
        <ul className="flex flex-col">
          {GOTCHAS.map((g, i) => (
            <li
              key={i}
              className="flex gap-3 border-t border-[color:var(--line)] py-3 text-sm first:border-t-0"
            >
              <span className="text-rose mt-0.5 shrink-0" style={{ color: 'var(--rose)' }}>
                ●
              </span>
              <span className="text-dim">{g}</span>
            </li>
          ))}
        </ul>
      </Plate>
    </>
  )
}

// ----------------------------------------------------------------------------
// WEB 操作編
// ----------------------------------------------------------------------------
function WebFlow() {
  return (
    <div className="flex flex-col gap-5">
      <Step n={1} title="サーバーを起動してブラウザで開く">
        <Cmd>{`pantheon serve --port 7860
# → http://127.0.0.1:7860 を開く`}</Cmd>
        <p>
          既定で配信されるのは従来 GUI です。LAN に公開する（<K>--host 0.0.0.0</K>）ときは必ず
          <K>PANTHEON_API_TOKEN</K> を設定し、<K>/?token=...</K> 付きで開いてください。
        </p>
      </Step>

      <Step n={2} title="組織（収益化の単位）を作る">
        <p>
          <K>組織</K> ページ →「新規組織」→ 名前・目的・<b>リポジトリの絶対パス</b>を入力。
          1組織 = 1リポジトリで、リポジトリは必須です。
        </p>
        <Callout tone="rose" title="WEB の制限" compact>
          ジャンル / ペルソナ / デザインの指定は <b>Web ではできません</b>（CLI の{' '}
          <K>org create</K> 専用）。Web 作成は素のデフォルト組織になります。こだわるなら CLI 操作編へ。
        </Callout>
      </Step>

      <Step n={3} title="コンテンツを予約して下書きを生む">
        <p>
          <K>コンテンツ予約</K> ページ →「ジョブを追加」。種別（<K>content_brief</K> /{' '}
          <K>audience_signal</K> / <K>monetization_lead</K> / <K>generic</K>）と間隔（1h / 6h / 1d / 1w）を選択。
          リポジトリを持つ組織のみ対象です。
        </p>
        <p>
          「今すぐ生成」で 1 本、または「ループ開始」で常時生成。生成物は
          <b>承認待ちの下書き（content_asset 提案）</b>として保存され、外部公開はされません。
        </p>
      </Step>

      <Step n={4} title="トレンドを取り込む（任意・強力）">
        <Callout tone="ice" title="従来 GUI にトレンド画面はありません" compact>
          トレンド収集は CLI（<K>pantheon trends collect</K>）か trend デーモン、または新 GUI「Signals」で行います。
          変換は <K>POST /api/trends/convert</K>（高スコアのネタ →「無効状態の ContentJob」＋ 新規事業提案）。
        </Callout>
      </Step>

      <Step n={5} title="承認する（= 出荷）">
        <p>
          <K>改善提案</K> ページで組織を選び「承認 / 却下」（複数は「一括承認」）。
          承認するとその場で適用され、下書きがリポジトリに書き出されます。コード提案ならブランチ / PR を作成。
          ポリシーが拒否した提案は承認できません（409）。
        </p>
      </Step>

      <Step n={6} title="引き渡し（集客→販売→収益化）を承認する">
        <p>
          <K>引き渡し</K> ページ →「承認＋本文生成」。1 ボタンで承認と同時に、受け取り側の組織に
          本文の下書き（content_asset 提案）が claude で自動生成されます。
          <b>その下書きも、受け取り側の組織で改めて承認 / 適用が必要</b>です。
        </p>
      </Step>

      <Step n={7} title="監視する">
        <p>
          <K>ダッシュボード</K>でセッション × エージェントとフライホイール（承認待ち件数）を確認。
          トークン使用量は <K>GET /api/usage/summary</K>。新 GUI なら「Observatory」が同等です。
        </p>
      </Step>

      <Step n={8} title="公開する（手動）">
        <p>
          承認済みの <K>&lt;リポジトリ&gt;/content/*.md</K> を note / X / YouTube に
          <b className="text-gold"> あなたが貼って公開</b>します。ここからが実収益。
        </p>
      </Step>
    </div>
  )
}

// ----------------------------------------------------------------------------
// CLI 操作編
// ----------------------------------------------------------------------------
function CliFlow() {
  return (
    <div className="flex flex-col gap-5">
      <Step n={1} title="起動">
        <Cmd>{`pantheon up               # チャット＋GUI＋ブラウザ自動起動
# または GUI だけ:
pantheon serve --port 7860`}</Cmd>
      </Step>

      <Step n={2} title="ジャンル組織を量産する（CLI だけの強み）">
        <p>
          1 コマンドで、LLM がジャンル別の部門 / チーム / エージェントを設計し、外部分離の組織と
          Git ワークスペースを自動生成します。ペルソナ（口調）とデザイン（トーン）も付与。
        </p>
        <Cmd>{`pantheon org create --name "AI副業ラボ" \\
  --genre side_business \\
  --persona sns_growth_hacker \\
  --design vibrant
# --genre 例: ai / side_business / video_edit / game_dev / business
# 既定で isolation-level=external（コア汚染を防ぐ）`}</Cmd>
        <p className="text-faint text-xs">
          既存リポジトリを使うなら <K>pantheon org add --name MyApp --repo C:\path\to\repo</K>、
          まとめてなら <K>pantheon org scan &lt;親フォルダ&gt; --yes</K>。
        </p>
      </Step>

      <Step n={3} title="トレンドを集める">
        <Cmd>{`pantheon trends collect
pantheon trends list --min-score 7 --source web`}</Cmd>
        <Callout tone="rose" title="convert は CLI に無い" compact>
          <K>pantheon trends</K> は <K>collect</K> と <K>list</K> のみ。トレンド → ジョブ / 提案への
          <b>変換</b>は Web の <K>POST /api/trends/convert</K> か trend デーモンの巡回で行われます。
          収集だけでは何も動き出しません。
        </Callout>
      </Step>

      <Step n={4} title="（コード資産系）分析 → 提案 → 承認適用">
        <Cmd>{`pantheon analyze  --org-name "AI副業ラボ" --max-files 15
pantheon proposals --org-name "AI副業ラボ"
pantheon approve <提案ID8桁> --org-name "AI副業ラボ" --yes
# PR を作るなら: --github-repo owner/repo --github-token <tok>`}</Cmd>
        <p className="text-faint text-xs">
          <K>approve</K> は <K>proposal apply</K> の別名。ID は先頭一致（8文字以上）でOK。
        </p>
      </Step>

      <Step n={5} title="引き渡しで 集客→販売→収益化 を繋ぐ">
        <Cmd>{`pantheon handoff create --from "SNS運用" --to "note販売" \\
  --kind audience_signal --title "今週のバズ題材を記事化"
pantheon handoff approve <id> --draft        # 承認＋本文下書きまで一気に
pantheon proposal apply <id> --org-name "note販売"  # 受け取り側で適用`}</Cmd>
        <p>
          <K>--kind</K>: <K>audience_signal</K>（→ note 有料記事ブリーフ）/{' '}
          <K>content_brief</K>（→ SNS 集客）/ <K>monetization_lead</K>（→ アフィリエイト）。
          承認は<b>各 hop に都度必要</b>です。
        </p>
      </Step>

      <Step n={6} title="24時間 自律運転にする">
        <Cmd>{`pantheon daemons start all          # improvement/content/trend/watchdog
pantheon daemons watchdog install  # 再起動後も自動復帰（Windowsタスク）
pantheon daemons status            # 健全性＋レート制限の確認`}</Cmd>
        <p className="text-faint text-xs">
          デーモンは<b>下書き / 提案を生成して並べるだけ</b>。承認・公開は別途あなたが行います。
          <K>watchdog install</K> をしないと PC 再起動では復帰しません。
        </p>
      </Step>

      <Step n={7} title="公開する（手動）">
        <p>
          承認済みの <K>&lt;リポジトリ&gt;/content/*.md</K> を各プラットフォームに手動投稿。
          ここで初めて収益が発生します。
        </p>
      </Step>
    </div>
  )
}

// ----------------------------------------------------------------------------
// データ
// ----------------------------------------------------------------------------
const FLOW: { t: string; d: string }[] = [
  { t: '組織を立てる', d: 'ジャンル/ペルソナ/デザイン付きの組織を量産（CLI）。1組織=1リポジトリ。' },
  { t: 'トレンドを集める', d: 'Web/RSS/YouTube を収集・採点。高スコアが次の一手のタネになる。' },
  { t: '下書きを生成', d: 'ContentJob が claude でペルソナ口調＋デザイントーンの Markdown を生成。' },
  { t: '引き渡しで連鎖', d: '集客→販売→収益化。ある組織の成果を次の組織の入力に渡す。' },
  { t: '承認ゲート', d: 'content/handoff/外部/構造は常に人間承認。承認＝リポジトリに書き出し。' },
  { t: '手動で公開', d: '承認済み content/*.md を note/X/YouTube に自分で貼って収益化。' },
]

const TIPS: { tag: string; tone: 'gold' | 'ice' | 'green' | 'rose' | 'neutral'; t: string; body: ReactNode }[] = [
  {
    tag: 'autonomy',
    tone: 'ice',
    t: '4つのデーモン＋watchdog',
    body: (
      <>
        <p>
          <K>improvement</K>（自己改善 3600s）/ <K>content</K>（下書き 600s）/ <K>trend</K>（収集 6h）/{' '}
          <K>watchdog</K>（監視 60s）。<K>daemons start all</K> で全起動、desired-state が保存され watchdog が生かし続けます。
        </p>
        <p className="text-faint text-xs">
          PC 再起動を跨ぐには <K>daemons watchdog install</K>（ONLOGON＋5分ガードの Windows タスク、管理者不要）。
        </p>
      </>
    ),
  },
  {
    tag: 'zero-waste',
    tone: 'green',
    t: 'レート制限は自動 pause→resume',
    body: (
      <p>
        Claude の利用上限に当たると全プロセス共有のゲートが立ち、制限中は <b>claude を起動しません</b>
        （トークンも時間も浪費ゼロ）。リセット時刻を過ぎると自動で解除され、作業が再開します。
      </p>
    ),
  },
  {
    tag: 'quota',
    tone: 'gold',
    t: 'トークン枠は先回りで節約',
    body: (
      <>
        <p>
          5時間枠の実測消費が soft（既定 300万）に近づくと低優先（improvement/PDCA）を間引き、hard（既定 500万）で
          critical のみ＋light ティアに降格。due な投稿は残す設計です。
        </p>
        <p className="text-faint text-xs">
          この値は<b>推定値</b>。<K>GET /api/usage/summary</K> の実測で <K>config/token_quota.yaml</K> を調整。
        </p>
      </>
    ),
  },
  {
    tag: 'model',
    tone: 'neutral',
    t: 'モデル使い分けは task_type で opt-in',
    body: (
      <p>
        要約/採点=haiku、レビュー/コンテンツ=sonnet、コード変更/メタ改善=opus と自動選択。
        ただし <b>task_type が付いた呼び出しだけ</b>がルーティング対象。20,000字超の入力は1ティア自動昇格。
      </p>
    ),
  },
  {
    tag: 'state',
    tone: 'neutral',
    t: '状態の置き場所',
    body: (
      <p>
        グローバルは <K>~/.pantheon</K>（rate_limit_state / pid / log / daemons/enabled.json / heartbeat）。
        リポジトリ固有（提案・決定）は <K>&lt;repo&gt;/.pantheon</K>。バックアップはここを。
      </p>
    ),
  },
  {
    tag: 'safety',
    tone: 'ice',
    t: 'LAN 公開時はトークン必須',
    body: (
      <p>
        ローカル専用なら認証不要。<K>--host 0.0.0.0</K> で公開するなら <K>PANTHEON_API_TOKEN</K> を設定。
        未設定だとネットワーク上の誰でもデーモン起動・承認・設定変更ができてしまいます。
      </p>
    ),
  },
]

const GOTCHAS: ReactNode[] = [
  <>
    <b>ライブ自動投稿は現行 main に無い。</b> 生成物は承認待ちの下書きとしてリポジトリに保存されるだけ。
    最後の公開は人間が手動で行う（_publish_live / 投稿 API クライアントは未実装）。
  </>,
  <>
    <b>
      <K>pantheon trends convert</K> は存在しない。
    </b>{' '}
    変換は Web の <K>/api/trends/convert</K> か trend デーモンの巡回のみ。<K>collect</K> だけでは何も並ばない。
  </>,
  <>
    <b>ジャンル/ペルソナ/デザイン組織は CLI 専用。</b> Web の組織作成は名前・目的・リポジトリのみ。
  </>,
  <>
    <b>トレンド由来の ContentJob は「無効」で作られる。</b> 人間が有効化（または「今すぐ生成」）するまで動かない（承認ゲート）。
  </>,
  <>
    <b>引き渡しの承認は終わりではない。</b> 受け取り側にもう一つ承認待ち提案ができるので、そこで <K>proposal apply</K> が要る。
  </>,
  <>
    <b>
      <K>stop</K> は粘着する。
    </b>{' '}
    停止すると desired-state が OFF になり watchdog は復活させない。戻すには <K>enable</K> か <K>start</K>。
  </>,
  <>
    <b>生死判定は pid でなく heartbeat。</b> レート制限で休止中のデーモンは鼓動を打ち続け「健全」表示。直さないこと。
  </>,
  <>
    <b>環境変数のキルスイッチに注意。</b> <K>PANTHEON_NO_RATE_GATE=1</K> / <K>PANTHEON_QUOTA_GOVERNOR=0</K> /{' '}
    <K>PANTHEON_MODEL_ROUTING=0</K> が残っていると無人運転で無駄/暴走の原因に。
  </>,
  <>
    <b>Windows の既知テスト失敗2件は無視してよい。</b> <K>chmod 0o600</K> が Windows で効かないだけの恒常的なもの（旧6件のうちパス区切り由来4件は根治済み）。新規の失敗だけが本物。
  </>,
]

// ----------------------------------------------------------------------------
// 小さな部品
// ----------------------------------------------------------------------------
function SectionLabel({ n, title, note }: { n: number; title: string; note: string }) {
  return (
    <div className="mt-16 mb-6 flex items-center gap-4">
      <span className="mono text-gold text-xs tracking-[0.2em]">{pad2(n)}</span>
      <h2 className="serif text-3xl">{title}</h2>
      <span className="kicker">{note}</span>
      <span className="ml-2 h-px flex-1" style={{ background: 'var(--line)' }} />
    </div>
  )
}

function Step({ n, title, children }: { n: number; title: string; children: ReactNode }) {
  return (
    <Plate className="rise">
      <div className="flex items-baseline gap-4">
        <span className="numeral text-3xl text-gold shrink-0">{pad2(n)}</span>
        <h3 className="serif text-xl leading-snug">{title}</h3>
      </div>
      <div className="mt-3 text-dim text-sm leading-relaxed flex flex-col gap-3">{children}</div>
    </Plate>
  )
}

function Cmd({ children }: { children: ReactNode }) {
  return <pre className="code-block">{children}</pre>
}

function K({ children }: { children: ReactNode }) {
  return <code className="code-inline">{children}</code>
}

function Callout({
  tone,
  title,
  children,
  compact,
}: {
  tone: 'gold' | 'ice' | 'rose'
  title: string
  children: ReactNode
  compact?: boolean
}) {
  const color = tone === 'gold' ? 'var(--gold)' : tone === 'ice' ? 'var(--ice)' : 'var(--rose)'
  return (
    <div
      className={cn('callout', !compact && 'my-2')}
      style={{ borderLeftColor: color }}
    >
      <div className="flex items-center gap-2 mb-2">
        <ArrowIcon size={14} style={{ color }} />
        <span className="mono text-[11px] tracking-[0.14em] uppercase" style={{ color }}>
          {title}
        </span>
      </div>
      <div className="text-dim text-sm leading-relaxed flex flex-col">{children}</div>
    </div>
  )
}
