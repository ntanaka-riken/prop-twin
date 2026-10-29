# prop-twin — JAPAN SCIENTIST AI JAM SESSION 2026 のプロペラ・デジタルツイン

![3D ツインで回転数制御 1500→2500→1000→2000 rpm を動かしたところ](media/twin3d_rpmctl.webp)

*[`twin/twin3d.html`](twin/twin3d.html) で閉ループ回転数制御 `rpm:set` 1500 → 2500 → 1000 → 2000 rpm を動かしたところ(左:実機の 3D スキャン + プロペラ、右:回転数・電圧・電流・トルク・電力・推力)*

[JAPAN SCIENTIST AI JAM SESSION 2026](https://www.riken.jp/pr/events/lectures/20261027_1/index.html)(理化学研究所 TRIP 事業本部・AGIS 主催)で取り組んだ内容です。2026-10-28(東京・AP日本橋)と 10-29(理研神戸 R-CCS)の本番セッションに両日とも参加し、AI エージェント(Claude Code、Codex)を共同研究者として、机の上の小さな装置のデジタルツインを 2 日間で作りました。

- **装置**:Switch Science ESPr Developer(ESP8266)+ L293D(2 ブリッジ並列)+ 130 級 DC モーター + 3 枚羽根プロペラ(紙コップ上)
- **ファーム**:USB シリアル 1 行 1 コマンドの `blink_ota_esp8266_v36.ino`。会期中に、動画同期用 LED、ADC の逆起電力プローブと回転計(`adc:*`)、閉ループ回転数制御(`rpm:set`)、テレメトリ(`tel:on`)を加えました
- **計測**:iPhone 動画(音声・羽根の追跡)、ESPr の ADC、電子天秤による推力、RealityKit Object Capture の 3D スキャン
- **ツイン**:PWM 1 周期ごとに解く電気系 + 機械系 + BEMT(翼素運動量理論)の空力。2D / 3D のブラウザ版は Web Serial で実機の値を重ねて表示([`twin/`](twin/))
- **主な結果**:K = 6.06e-3 V·s/rad を ADC で直接測定、推力 1.9 gf @ 3164 rpm、部分 duty の 13 観測を ±1.5σ で再現、閉ループで 1000–2500 rpm を ±1 % で保持

## 使った AI エージェント

| エージェント(モデル) | 時期 | 取り組んだこと |
|---|---|---|
| Claude Code(Claude Opus 5.5、デスクトップアプリ) | 10-28 午後〜10-29 | v36 ファームの修正と機能追加、動画・ADC・天秤の解析、ツイン本体と同定、BEMT、2D / 3D のブラウザ版、記録の整理と公開 |
| Codex(GPT-6.1 Sol、VS Code) | 10-28 午前〜10-29 午前 | モーター未接続での USB・通信の立ち上げ、フラッシュの退避、専用 AP 経由の OTA、出力を無効にした制御ロジックの dry-run 14 項目 |
| Hermes Agent + RiVault(GLM-5.3-Flash) | 10-25〜26(会期前の準備)、10-29 | 会期前に ESP32(ELEGOO キット)と ESPr Developer のシリアル接続・書き込み・OTA の手順を確立し、FLIR サーモカメラで Mac の発熱を記録。10-29 にその作業記録を学習データ用に書き出し(秘密情報・LAN IP・SSID をマスク) |

10-29 には、これら 3 種類のエージェントの作業記録をまとめて、Nemotron 3.5 Lightning 30B-A3B と Super VL を rikyu(GB200)で LoRA 微調整し、このツイン上で実機操作を模した課題で評価する実験も行いました(結果は [2 日目の日報](docs/daily/2026-10-29.md))。

経緯は [`docs/HISTORY.md`](docs/HISTORY.md)、日ごとの要約は [1 日目 10-28](docs/daily/2026-10-28.md)・[2 日目 10-29](docs/daily/2026-10-29.md) にあります。

## 開発の記録

2026-10-28〜29 に、動画・ADC・電子天秤で測りながらデジタルツインを作った経緯を [`docs/HISTORY.md`](docs/HISTORY.md) にまとめています。日ごとの要約は [`docs/daily/`](docs/daily/)(例:[2026-10-28](docs/daily/2026-10-28.md)、[2026-10-29](docs/daily/2026-10-29.md))。

| フォルダ | 内容 |
|---|---|
| [`docs/`](docs/) | 開発の記録(時系列、使った動画とコード、主な数値の移り変わり) |
| [`media/`](media/) | 写真と図。動画・3D スキャン・作業用フォルダは GitHub のリリース `media-2026-10-29` に添付(一覧と取得方法は `media/README.md`) |
| [`analysis/`](analysis/) | 作業中に書いた解析コード(1 日目と 2 日目) |
| [`transcripts/`](transcripts/) | Claude Code との会話の記録(個人情報は伏せ字) |

## ファイル構成

| ファイル | 内容 |
|---|---|
| `blink_ota_esp8266_v36.ino` | ファームウェア本体(v36、約230行) |
| `WIRING.md` | L293D 配線ガイド(ピン対応表・電源・実測しきい値) |
| `tools/serial_console.py` | Mac 側シリアルコンソール(モニタ/コマンド送信) |
| `twin/` | デジタルツイン(電気+機械モデル、動画からのパラメータ同定、可視化 `twin.html`)。[twin/README.md](twin/README.md) |

## ハードウェア

| 名称 | 仕様 |
|---|---|
| ボード | ESPr Developer(ESP-WROOM-02、2MB flash、FT231XS USB-serial) |
| モータードライバ | L293D(**2ブリッジ並列**、連続1.2A / ピーク2.4A) |
| モーター | DCモーター(3-6V 級) |
| 電源 | 5V(L293D VCC1/VCC2 と ESPr への給電) |

ピン割り当てと配線の詳細は [WIRING.md](WIRING.md) を参照してください。

## クイックスタート

```bash
# 1. ビルド(Arduino CLI + esp8266 コア 3.1.2)
arduino-cli compile --fqbn "esp8266:esp8266:generic:eesz=2M512,ip=lm2f" \
  --build-path build blink_ota_esp8266_v36

# 2. シリアル書き込み(データ対応USBケーブル必須、約20秒)
arduino-cli upload --fqbn "esp8266:esp8266:generic:eesz=2M512,ip=lm2f" \
  --input-dir build -p /dev/cu.usbserial-XXXX blink_ota_esp8266_v36

# 3. シリアルコンソールで操作
python3 tools/serial_console.py                       # モニタ([HB]確認)
python3 tools/serial_console.py -c stat               # 状態表示
python3 tools/serial_console.py -c "dcm:ramp 80 5000" # 0→80%を5秒でランプ
python3 tools/serial_console.py -c "dcm:off"          # 停止
```

ポート名は `ls /dev/cu.usb*` で確認(FT231XS は `usbserial-DN…` 形式)。

## ピンマップ

| ESP8266 GPIO | L293D ピン | 役割 |
|---|---|---|
| IO12 | 2, 10(1A/3A) | 方向A(正転) |
| IO13 | 7, 15(2A/4A) | 方向B(逆転) |
| IO15 | 1, 9(EN1,2/EN3,4) | PWM 速度 0-255 |
| IO14 | —(同期 LED) | `dcm:*` が受理されるたびに 100 ms 点灯(IO14→抵抗→LED→GND) |

- `dcmApply()` は INA/INB の片方を HIGH、他方を LOW にして方向を決め、EN に `analogWrite()` で duty を出します。
- IO15 はブート時 LOW が必要なストラップピンですが、アイドル状態(`dcmOff()`)が EN=LOW なので整合します。PWM 実績のあるピンです(v31-34で検証済み)。
- IO1/IO3 はシリアル(TX/RX)で使用、IO16 は ESP8266 で PWM 非対応のため EN には使えません。

## シリアルコマンド一覧

| コマンド | 動作 | 引数範囲(コードでクランプ) | 応答例 |
|---|---|---|---|
| `stat` | ヒープ・断片化を表示 | — | `STAT blink_ota_esp8266 v36 serial-only (L293D + sync LED) heap=51256 maxfree=51256 frag=0` |
| `dcm:ramp <pct> <ms>` | 現在の duty から pct% へ ms ミリ秒かけて連続ランプ | pct 0-100 / ms 0-30000 | `ACK dcm:ramp 80% over 5000ms (duty 51->204)` |
| `dcm:ramp-step <pct> <ms> <inc>` | 階段状ランプ(ms間隔で inc% ずつ目標へ増減) | pct 0-100 / ms 50-10000 / inc 1-51 | `ACK dcm:ramp-step target=80% every=1000ms inc=10% (duty 51->204)` |
| `dcm:speed <-255..255>` | 即時設定。符号=方向、0=コースト | -255..255 | `ACK dcm:speed dir=1 duty=204` |
| `dcm:brake` | 短絡ブレーキ(両入力 HIGH + EN=255)。duty は 0 扱い | — | `ACK dcm:brake` |
| `dcm:off` | コースト(EN LOW)。ランプ停止 + duty=0 リセット | — | `ACK dcm:off` |
| `adc:read` | ADC を1回読む | — | `ADC raw=14 tout_mV=13 terminalA_mV=76` |
| `adc:cap <us> <n> <pre> [cmd]` | ADC を us 間隔で n 点 RAM に記録、pre 点目で cmd を実行、終了後に `ADC ...` 行で出力 | us ≥ 10、n ≤ 4000、n·us ≤ 3 s | `ADC cap n=4000 interval_us=200 pre=500 ...` |
| `adc:emf [settle_us] [n]` | 回転計:EN を settle_us(既定 1500)切って電流を消し、端子A(= 逆起電力)を n 回読んで PWM を戻す。どの duty でも使える | settle 200–20000、n 1–64 | `EMF terminalA_mV=1150 raw_mean=196.0 ... coast_us=1846 duty=153 drive` |
| `rpm:set <rpm>` | 回転数の閉ループ制御(750–3200 rpm)。停止中なら 100 % でキックして起動。0 で停止。`dcm:*` を送ると解除 | 750–3200 | `ACK rpm:set ref=1500` |
| `rpm:off` | 制御を止めてコースト | — | `ACK rpm:off` |
| `tel:on` / `tel:off` | 50 ms ごとに回転計で測って `TEL` 行を出力(制御中でなくても可) | — | `TEL t=12345 duty=150 rpm=1523 filt=1497 ref=1500` |
| `adc:zero` | モーター停止中に ADC のゼロ点を測り直す(起動時にも自動) | — | `ACK adc:zero raw=21.1` |
| `dcm:auto <0\|1>` | ブートシーケンスの ON/OFF(実行中に 0 にすると即停止) | — | `ACK dcm:auto boot-soft-start=OFF` |

未定義コマンドには `ERR unknown cmd '...' (stat|dcm:*)` が、`dcm:ramp` / `dcm:ramp-step` の引数不足には `ERR ... usage: ...` が返ります。

### 動作上の規則

- **連続ランプと階段ランプは相互排他**。どちらかを開始すると他方はキャンセルされます。`dcm:speed` / `dcm:brake` / `dcm:off` もランプをキャンセルします。
- `dcm:off` は duty を 0 に戻すため、**次のランプは必ず 0 から始まります**(停止後に途中の duty が残るバグは v34 で修正済み)。
- `dcm:ramp` / `dcm:ramp-step` は**方向を変更しません**(現方向のまま duty を変える)。逆転は先に `dcm:speed -N`(または `-N` からの階段)を使います。
- `dcm:brake` 後のランプも **0 から始まります**(ブレーキ中は duty=0 として扱う)。
- `dcm:ramp-step` は目標が現在 duty より低ければ inc% ずつ**減速**します。
- ブートシーケンスは **起動5秒後に 50% で始動 → 5秒かけて 100% → 1秒ホールド → コースト(停止)** です。50% は停止状態から起動できる最低 duty です。途中で `dcm:speed` などの操作コマンドを送るとシーケンスはキャンセルされ(以後の停止も行わない)、`dcm:auto 0` を送ると即停止して無効化します。**RAM 保持のため再起動すると ON に戻ります**。
- `[HB] <millis>` を500msごとに出力(ループ生存確認用)。これが途絶えたらフリーズかリセットです。

## ブートシーケンス(正常系のログ)

```
[RESET] External System
[FW] blink_ota_esp8266 v36 serial-only (L293D + sync LED)
[DCM] L293D ready (EN=IO15 PWM, 1A+3A=IO12, 2A+4A=IO13)
[DCM] boot sequence armed: in 5s, 50->100% over 5s, hold 1s, coast (dcm:auto 0 to disable)
Ready. Type a command (stat | dcm:speed 255 | dcm:ramp 80 5000 | ...)
[HB] 5012 ...
[DCM] boot sequence: 50% -> 100% over 5s
[HB] 10020 ...
[DCM] boot sequence done: coast
[HB] 11025 ...
```

v36 は Wi-Fi を持たないため、**書き込み直後から即座に**このシーケンスが始まります。

## 実測データ(このモーター+ドライバーでの測定値)

### 冷間始動しきい値(二分探索で実測)

| duty | 結果 |
|---|---|
| 20% | 不転 |
| 40% | 不転 |
| **45%** | **境界**(遅れて breakaway) |
| 50% | 転 |
| 60% / 100% | 転 |

- **確実な起動 = 50%以上、安定運転 = 55%以上**を推奨。
- **維持しきい値は起動しきい値より低い**(未測定)。回転中にしきい値未満へ落とすと、逆起電力が実効電圧を上回り減速・停止します。
- L293D の電圧降下は 1.4-2.6V。20% duty では実効 ~0.5V しかかからず、3-6V モーターは起動できません(上記しきい値の物理的理由)。

### リソース使用量(v36 実測)

| 項目 | 値 |
|---|---|
| bin サイズ | 282,992 B(OTAスロット ~768KB の約37%) |
| RAM(グローバル/静的) | 29,212 / 80,192 B(36%) |
| 起動時ヒープ | 51,256 B(frag 0%) |

## ビルド設定の意味

| FQBN オプション | 意味 |
|---|---|
| `generic` | 現行 esp8266 コアに ESPr Developer 専用定義はないため Generic ESP8266 Module を使用 |
| `eesz=2M512` | 2MB flash、FS 512KB → スケッチ+OTA領域 ~1.5MB(2スロット各 ~768KB) |
| `ip=lm2f` | lwIP v2 Lower Memory(Wi-Fi コードが無いため動作への影響なし) |

- シリアル書き込みは RTS ハードリセットで自動的にブートローダーへ入り、書き込み後にハッシュ検証されます(115200 baud で 283KB ≈ 20秒)。
- 書き込みはブートローダー+アプリ領域のみを上書きします。

## トラブルシューティング

| 症状 | 確認点 |
|---|---|
| モーターが回らない | ACK の duty を確認 → 50%未満の冷間始動は不転の可能性(55%+で再試験)。VCC1/VCC2 が 5V か、GND 共通か、ジャンパ(1↔9 / 2↔10 / 7↔15)を WIRING.md で確認 |
| 低速で失速する | 実測しきい値以上か確認。維持は起動より緩いが、極端な低速は電圧降下で不可 |
| 途中でリセット/[HB] 途絶 | 電源容量不足の典型。モーターを別 5V 電源にし GND を共通化 |
| `/dev/cu.usb*` が出ない | データ対応ケーブルか確認(給電専用ケーブルは通信不可)。再挿入で復帰するか試す |
| 書き込みがタイムアウト | ケーブル再挿入のうえ再実行。`arduino-cli upload` は RTS 自動リセットするためボタン操作は不要 |
| コマンドが無反応 | `[HB]` が出ているか確認。出ていれば受信側(ケーブル/アプリ)の問題、出ていなければボード側 |
