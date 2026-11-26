# Notion → 朝と夜の車内ラジオ

## 朝夜対応の運用

既存の朝7:27（日本時間）の実行時刻、`NOTION_API_KEY`、`NOTION_PAGE_ID`、女性音声・速度設定を維持し、同じ実行で夜用も生成します。原稿そのものは既存のChatGPT自動タスクがNotionへ書き込みます。このコードは原稿生成タスクを変更しません。

- 朝: 既存 `NOTION_PAGE_ID`（未設定時 `406c2f0d-3b78-8160-a63f-e2057a7fe097`）→ `today.mp3` / `today.txt` / `status.json`。
- 夜: `424c2f0d-3b78-81d7-82ab-ee281bf1ffb1` → `evening.mp3` / `evening.txt` / `evening-status.json`。
- 夜ページにも、GitHubの `NOTION_API_KEY` に対応する既存Notionインテグレーションを接続してください。ChatGPTから読めることと、そのキーで読めることは別です。
- 公開プレイヤーは開いた時点の日本時間で朝夜を選択。`?episode=morning` / `?episode=evening` で固定選択も可能です。
- 既存のCarPlayショートカットが `today.mp3` を直接取得する場合は従来どおり朝になります。ショートカット側で日本時間17時以上なら `evening.mp3`、それ以外は `today.mp3` を取得する分岐が必要です。Webページを開く場合の選択は実装済みです。
- 全ページ・全rich_textを順番に取得。30階層を超えた場合は省略せず失敗します。ページの今日の更新を確認しますが、本文全体が今日のニュースかを意味判定するものではありません。
- 夜失敗時も朝を公開。失敗した番組は公開済みの前回分が検証できれば維持し、日付と警告を表示。朝を新規生成・復旧のいずれもできない場合は公開を止め、既存サイトを維持します。部分失敗は公開後もActions上で失敗として報告します。
- HTTP、音声生成（各10分）、合成（各3分）、ジョブ全体（40分）に上限を設けています。
- BGMは外部音源を使わない自作の合成音です。[由来・利用条件](BGM.md)。`BGM_ENABLED: 'false'` で無効化できます。
- 文字数と実際の音声秒数を記録します。6〜7分にするにはNotionの原稿量を調整してください。音声を強制的に切り詰めたり、不自然に加速したりしません。
- 公開後、HTML・番組情報・MP3のSHA-256を生成結果と照合します。CarPlay実機での再生は別途確認が必要です。

以下は既存の初期設定ガイドです。

ChatGPTなどが毎朝7:00に更新する **Notionの同一ページ** を、朝7:27（日本時間）に読み出して、音声MP3にしてGitHub Pages上の簡単なプレイヤーで公開します。毎朝PCを起動する必要はありません。

**注意**: このひな形はコードの基本検査まで行ったものです。ユーザーのNotion・GitHubアカウントでの動作確認、CarPlayでの途切れない再生確認は未実施です。

## 事前に把握しておくこと

- GitHub Freeの**公開リポジトリ**と標準ランナーなら、GitHub Actionsの実行料金は原則無料です。
- GitHub PagesのMP3や原稿は**インターネット上で公開**されます。非公開にしたい原稿や個人情報を入れないでください。NotionのAPIキーは公開しません。
- `edge-tts` はMicrosoft Edgeのオンライン音声読み上げサービスを使う非公式ライブラリです。無料で試せますが**永続的な利用・動作保証はありません**。
- GitHubのスケジュールは遅延・実行されない場合があります。公開リポジトリは60日間、リポジトリに活動がない場合、スケジュールが自動で無効化されます。長期運用では定期的な稼働確認が必要です。
- Notion側の更新が遅れていたら、**昨日の原稿を『今日』として作らない**よう停止します。

## 1. Notion APIの読み取りキーを用意する

1. [Notion Developer Portal](https://www.notion.so/profile/integrations)で、読み取り権限のある自分用のインテグレーションを作成する（画面により表記が異なります）。
2. 対象のニュースページで `…` → `接続`（Connections）からそのインテグレーションを接続する。
3. 秘密のAPIキーを取得する。**このキーを公開リポジトリのファイルに書いてはいけません**。
4. ニュースのNotionページのURLに含まれる32文字のページIDを控える（ハイフン付きでも可）。

権限画面の仕様は更新され得るため、最新のNotion公式ドキュメントも参照してください：
https://developers.notion.com/reference/get-block-children

## 2. GitHubリポジトリを作る

1. GitHubで新規 **Public（公開）** リポジトリ `notion-news-radio` を作る。
2. このZIPを展開した全ファイルを、`.github/workflows/daily_news_audio.yml` の階層を維持してアップロードする。
3. Repository → **Settings → Secrets and variables → Actions → New repository secret** で以下2個を登録。

| 名前 | 値 |
|---|---|
| `NOTION_API_KEY` | Notionの秘密のAPIキー |
| `NOTION_PAGE_ID` | ニュース原稿ページのページID |

4. **Settings → Pages → Build and deployment → Source: GitHub Actions** を選ぶ。`Deploy from a branch` ではありません。
5. **Actions → 毎朝のニュース音声を作る → Run workflow** を選び、手動で一度動作確認する。
6. 当日更新の原稿がある日に成功したら、Actions実行履歴の `deploy-pages` ステップに表示されるPagesサイトを開いてMP3を再生する。

## 3. iPhoneとCarPlayで再生する

### 最初に試す方法

- iPhoneのSafariで `https://<GitHubユーザー名>.github.io/notion-news-radio/` を開き、再生ボタンを押す。
- CarPlay接続時もそのMP3が車のスピーカーから再生できるか試す。
- 長いMP3をより安定して操作したい場合は、CarPlay対応オーディオプレーヤーアプリ（例：BookPlayer）にMP3を取り込み、そちらで再生する。**自動取り込み機能は未検証**。

### CarPlay接続時の自動再生（要実機検証）

ショートカットで以下の処理を作り、オートメーションのトリガーを **CarPlayに接続** にします。

1. `URL`：`https://<GitHubユーザー名>.github.io/notion-news-radio/today.mp3`
2. `URLの内容を取得`
3. `サウンドを再生` に2の結果を渡す

これは「テキストを読み上げる」と違い、生成済みの音声ファイルの再生です。ただし、**CarPlayで長時間途切れず再生・完全自動開始できるかは端末と車で試す必要があります**。Safariでの手動再生やBookPlayerでの再生を先に確認してください。

## 設定とトラブル

- 開始時刻: `.github/workflows/daily_news_audio.yml` の `cron: '27 7 * * *'`、`timezone: 'Asia/Tokyo'` を変更。
- 女性音声: `ja-JP-NanamiNeural`（デフォルト）、男性音声: `ja-JP-KeitaNeural`。
- 音声速度: `TTS_RATE: '+0%'` を、たとえば `'+10%'` に変更。
- 失敗: Actionsの実行ログを確認する。Notionのページ権限・ページID・新しい原稿への書き換え時刻・GitHub Pages設定を最初に調べる。
- 公開後に音声が更新されない: ブラウザで日付を確認し、キャッシュを避けるため `?v=今日の日付` を付けてアクセスする。
- 自動実行が60日頃で止まる: GitHub Actionsのスケジュール停止警告を確認し、必要なら有効化する。

## 検証済み／未検証

- この配布物: Pythonの構文検査・YAML構造の検査・サンプルNotionブロックからの原稿抽出テスト済み。
- Notion APIの実接続: **未検証**（資格情報がないため）。
- `edge-tts`の実際のMP3生成・音声品質: **未検証**（この環境では外部API接続不可）。
- GitHub Actions実行・GitHub Pages公開・CarPlay再生: **未検証**。

公式参考: 
- https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows
- https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site
- https://developers.notion.com/reference/get-block-children
- https://github.com/rany2/edge-tts
