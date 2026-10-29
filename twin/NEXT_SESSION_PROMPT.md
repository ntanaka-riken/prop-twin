# 次のセッション用プロンプト

以下をそのまま新しいセッションに貼り付けてください。

---

`~/blink_ota_esp8266_v36` の続きです。Switch Science ESPr Developer(ESP8266)+ L293D(2ブリッジ並列)+ 130 級 DC モーター + 3 枚羽根プロペラ(紙コップ上)のデジタルツインを前セッションで作りました。まず `twin/README.md`、`twin/params.json`、`README.md`、`WIRING.md` を読んで現状を把握してから、下の「次の作業」を進めてください。返答は日本語で。

## 現状(前セッションの到達点)
- **ファーム** `blink_ota_esp8266_v36.ino`(Arduino CLI、FQBN `esp8266:esp8266:generic:eesz=2M512,ip=lm2f`、ポート `/dev/cu.usbserial-DN05I0TZ`)。コマンド:`dcm:*`(speed/ramp/ramp-step/brake/off/auto)、同期 LED(IO14、ACK ごとに 100 ms)、`adc:read` / `adc:cap <us> <n> <pre> [cmd]` / `adc:emf [settle_us] [n]`(EN を切って逆起電力を読む回転計)/ `adc:zero`、閉ループ `rpm:set <rpm>`(750–3200、FF + PI、Kp 0.04、Ki 0.25、duty 下限 40 %)/ `rpm:off`、テレメトリ `tel:on`(50 ms ごとに `TEL t= duty= rpm= filt= ref=`)。ブートシーケンス(起動 5 s 後 50→100 %/5 s → 1 s 後停止)は既定 ON(`dcm:auto 0` で無効、再起動で戻る)。
- **ADC 配線**:端子A(L293D 3番)→ 10 kΩ → TOUT → 2 kΩ → GND(比 0.167)、端子B(6番)→ 270 Ω → GND。ADC ゼロ点 raw ≈ 21。analogRead ≈ 42.5 µs。
- **ツイン** `twin/motor_twin.py`(ファーム挙動 + PWM 1 周期ごとに厳密解の電気系 + 機械系 + 推力 kT·ω² + 回転数制御・回転計プローブの再現)、`twin/fit_joint.py`(現行の同時同定:`--fix-K 6.06e-3 --free-V0 --free-b`)、`twin/adc_backemf.py`、`twin/compare_runs.py`、`twin/identify.py`(動画の音声コム/羽根追跡)、`twin/scan_to_web.py`(3D スキャン → web)。
- **現行パラメータ**(params.json、`fit_joint.py --fix-K 6.06e-3 --free-V0 --free-b --bemt --flag`):K = 6.06e-3(ADC で直接測定)、R = 11.3 Ω、L = 4.1 mH、V0 = 1.32 V(逆転は +0.067 V、`dV0_rev`)、rd = 0.6、J = 9.54e-7(回転子 2.66e-7)、Tc = 0.26 mN·m、b = 3.4e-7、Ts = 0.47 mN·m、V_bk = 3.0 V、Vs = 4.9 V(事前値)。プロペラ負荷は BEMT(`twin/bemt.py`、`params.json` の `aero` 表):ピッチ 18°、弦長は CHORD 表、揚力の効き kL = 0.90 ×(Re/14977)^0.49(IMG_5785 の推力 5 点、回転数は TEL で同時測定)、kD = 7.09(正転)/ kD_r = 4.96(逆転)、全速 FM ≈ 0.18。IMG_5759 の旗の抵抗は `c_flag` = 1.7e-9 として分離。16 観測を ±2.2σ で再現(最大は全速、温まり)。kD・b・R は互いに打ち消し合う方向に動けて決まりにくい。両 HTML は BEMT を JS で同じく計算(`bemtSolve` / `buildAero`)。
- **主な実測**:推力 1.9 gf @ 3164 rpm(風は上向き、C_T ≈ 0.34、D = 61–67 mm、FM ≈ 0.16)、部分 duty 回転数 100/80/60/50/40 % = 3070/2216/1628/1269/712 rpm、30 % で停止、閉ループで 1500/2500/1000/2000 rpm を ±1 % で保持。撮影ごとに全速が 51.3 → 48.6 Hz に下がる(温まり)。
- **可視化**:`twin/twin.html`(2D)と `twin/twin3d.html`(3D、Object Capture スキャン + パラメトリック回転体)。両方とも 1 画面ダッシュボード、時系列(回転数/電圧/電流/トルク/電力/推力/duty)、プロペラあり/なし切替、`rpm:set`、Web Serial で実機 TEL を重ね描き。公開版:2D https://claude.ai/artifact/L9NsA7vWr4yVxaVDhCqNYH 、3D https://claude.ai/artifact/CsxYQveZCxizwQcCJ4pikm (公開版は Web Serial 不可)。ローカル:`python3 -m http.server 8766 --directory twin` → Chrome で http://localhost:8766/twin.html。**JS のモデル定数は両 HTML に直書き**(`const ID=` / `const P=`、`CTL=`)なので、params.json を変えたら両ページも更新し、Python と JS の数値一致を確認すること。
- **データ**:`twin/data/`(各動画の measured json、ADC 捕捉 `data/adc/`、推力 `thrust_IMG_5769.json`、閉ループ `rpm_ctl_run1.*`)。セッション全体のバックアップ:`~/Desktop/PropTwin/blink_ota_esp8266_v36_session_2026-10-28_29/`(会話記録、動画、写真、3D スキャン)。
- **環境**:Python 解析用 venv は消える一時領域にあったので、必要なら作り直す(numpy scipy matplotlib opencv-python-headless)。動画の音声は `afconvert -f WAVE -d LEI16@48000 -c 1 in.MOV out.wav`。HPC が必要なら RIKEN R-CCS の rikyu(`ssh rikyu`、GB200)を使ってよい。

## 次の作業(この順で提案・相談してから進める)
1. ~~**空力モデル(BEMT)**~~ 済み(twin/README.md「空力モデル」)。逆転(コップへの吹き付け + 反りの向き)の予測も済み(README「逆転の予測」、`data/reverse_prediction.json`)。逆転は実測済み(IMG_5779 プロペラあり +0.57 %、IMG_5780 プロペラなし −2.19 %、天秤は逆転では後流が皿に戻るので推力を測れない)。プロペラなし・旗なしの全速は ADC で 73.6 Hz。逆転を測るときは TOUT のジャンパーを抜く(`tools/run_sequence.py --preset reverse|bare`)。残り:反り比率の実測、紙コップの影響(スペーサーで持ち上げて推力)、必要なら rikyu で CFD。
   旧メモ::羽根の弦長分布(平置き写真から ⟨r²⟩ = 0.462 R²、ハブ/R = 0.345、`twin3d.html` の `CHORD` 表)とピッチ(スキャン・写真から推定)で翼素運動量理論を実装し、実測の推力(kT)と空力トルク(c)に合わせる。推力・後流速度・空気への仕事を回転数の関数として両ツインに組み込む。足りなければ rikyu で CFD(数点の回転数)→ 低次元サロゲート。
2. **温度モデル**:銅損 R⟨i²⟩ から巻線温度(熱容量・熱抵抗の 1 次遅れ)、R(T) = R0(1 + 0.0039 ΔT)。全速回転数の 51.3 → 48.6 Hz のドリフトで同定。必要なら長時間の `tel:on` 記録を取る。
3. **ADC 校正**:テスターで端子電圧(と電源 VCC2)を測り、ADC 利得とゼロ点を補正 → K と V0 の不確かさを下げる。

## 注意点
- 実機を回すコマンドを送る前にユーザーに確認する。プロペラ付き全速は約 3000 rpm、外した状態は約 3700 rpm。
- ファーム書き込みでリセットされるとブートシーケンスが 5 s 後に回るので、書き込み直後に `dcm:auto 0` を送る。
- シリアルポートは同時に 1 つしか開けない(Web Serial のタブ、`tools/serial_console.py` など)。
- 撮影時の同期:LED(コマンド ACK ごと 100 ms)、Mac の Tink 音、ホスト側の送信時刻ログ(`twin/data/*_hostlog.json`)。
