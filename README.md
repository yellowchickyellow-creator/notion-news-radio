# Notion → 毎朝ニュースラジオ（設定用ひな形）

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
