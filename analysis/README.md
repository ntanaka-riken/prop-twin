# analysis/ — 作業中に書いた解析コード

整理済みのツイン本体と同定は [`../twin/`](../twin/) にあります。ここにあるのは、その途中で書いたスクリプトです。開発の流れは [`../docs/HISTORY.md`](../docs/HISTORY.md) を参照してください。

## day1/(1 日目〜2 日目午前、最初のセッション)

作業用フォルダにあったスクリプトをそのまま入れています(パスだけ伏せ字に置き換え)。入力の音声 wav やフレーム画像、途中の図は、リリースの `analysis_scratch_day1.zip` に作業用フォルダごと入っています。

| ファイル | 内容 |
|---|---|
| `analyze1.py`〜`analyze6.py`、`an*.py` | 動画の音声(ブラシ音の倍音コム)と映像(黄色い羽根の楕円当てはめ、極座標プロファイルの相互相関)から回転数を取り出す試行。番号は動画(`an44` = IMG_5744、`an59` = IMG_5759 など) |
| `track.py`、`onset.py`、`sp44.py` | 羽根の追跡、通電開始の検出、スペクトログラム |
| `led.py`、`led2.py`、`beep.py` | 同期 LED の点灯フレームの検出、Mac の Tink 音と送信時刻の記録 |
| `adccap.py` | ADC 捕捉(`adc:cap`)の初期版 |
| `ctl.js`、`check.js`、`scope.js`、`c.js` | ページの JS(回転数制御・スコープ)をブラウザの外で検証したもの |

## day2/(2 日目午後、このリポジトリを作ったセッション)

その場で書いて実行したコードを、動画とホストのログを引数で受け取るスクリプトに整えたものです。

| ファイル | 使った実験 | 内容 |
|---|---|---|
| `bemt_probe.py` | — | BEMT の最初の試算(ピッチ何度で実測推力になるか) |
| `prop_scan/` | IMG_5778 | プロペラ単体の 3D 復元(`scan.swift`)→ 回転軸(3 回対称)→ 円筒断面 → ピッチと反り(`axis.py`、`sect.py`、`meas.py`)。`blade_pitch.py` は机の法線を軸とした最初の失敗版 |
| `bemt_block.js`、`bemt_block2.js` | — | ページに入れた BEMT の JS(方向・コップ・天秤を入れる前と後) |
| `sync_audio.py` | IMG_5779 / 5780 / 5785 | ブラシ雑音の包絡線で動画とホストのログを同期し、各区間の回転数を倍音コムで読む |
| `display_crops.py` | IMG_5779 / 5781 / 5785 | 天秤の表示を各区間の後半で切り出して並べる(読み取りは目視、結果は `twin/data/*.json`) |
| `direction_and_motor.py` | IMG_5779 / 5780 | 正転・逆転の差をドリフトを除いて求め、モーター自体の方向差がプロペラ付きでどう効くかを 3 つの仮説で計算 |
| `bare_ripple.py` | ADC(`tools/bare_speed_adc.py`) | プロペラなしの全速を整流子リップルから(73.6 Hz) |
| `rig_scan_5782/` | IMG_5782 | 天秤に載せた装置の 3D 復元を水平にし(`scan_views.py`)、紙コップを円錐で当てはめて縮尺を決め(`scale_cup.py`)、ミリ単位の OBJ と寸法を書き出す(`export_mm.py`) |
| `thrust_checks.py` | IMG_5781 / 5785 | ブートシーケンス中の推力と天秤の遅れ、6 s ずつの推力と `TEL` の回転数 → 推力 ∝ n^2.23 |

実行例(プロジェクトのフォルダで。動画はリリースから取得):

```bash
python3 analysis/day2/sync_audio.py media/release/IMG_5785.MOV twin/data/thrust_steps3_hostlog.json --search 2 12
python3 analysis/day2/thrust_checks.py steps
```

いま実行すると、ツインのパラメータがその後に同定し直されているため、当時の値と少し違う結果が出ます。当時の値は `twin/README.md` と `twin/data/*.json` に残っています。

必要なもの:numpy、scipy、opencv-python-headless、matplotlib(作図のみ)。音声の取り出しに macOS の `afconvert`、3D 復元に macOS の RealityKit(`swiftc`)を使います。
