# media/ — 動画・写真・3D スキャン・作業用フォルダ

開発の流れは [`../docs/HISTORY.md`](../docs/HISTORY.md) を参照してください。

- **大きなファイル**(動画、3D スキャン、作業用フォルダ、会話の生ログ)は GitHub のリリース [`media-2026-10-29`](https://github.com/ntanaka-riken/prop-twin/releases/tag/media-2026-10-29) に、元の画質のまま添付しています。`sh media/fetch_media.sh` で `media/release/` に取得し、`SHA256SUMS` と照合できます(`gh` が必要)。
- **写真と小さな図**はこのフォルダに直接入れています。
- **個人情報の処理**:iPhone の動画には撮影場所の緯度経度(ISO 6709)が入っていたので、映像と音声はそのままに、位置情報の文字列だけをゼロで上書きしました。HEIC の写真はメタデータを含まない JPEG(元の解像度、品質 95)に変換しています。zip の中の JPEG も、Exif を持つものは作り直しました。会話の記録と作業用フォルダのテキストからは、メールアドレス、ホームフォルダのパス、計算機のホスト名とユーザー ID を伏せ字にしています。

## リリースに添付(19 個、計 1.34 GB)

| ファイル | 種類 | 大きさ | 内容 |
|---|---|---|---|
| `IMG_5741.MOV` | 動画 | 9.1 MB | day 1: 100 % 2 s then coast (30 fps), first identification (location metadata zeroed: 2) |
| `IMG_5742.MOV` | 動画 | 51.2 MB | day 1: 100 % 3 s -> 20 % 8 s -> off, sync LED (60 fps): inductance L (location metadata zeroed: 2) |
| `IMG_5744.MOV` | 動画 | 45.5 MB | day 1: coast vs brake (location metadata zeroed: 2) |
| `IMG_5745.MOV` | 動画 | 72.5 MB | day 1: coast vs brake with a 1-yen coin (vibration, not used) (location metadata zeroed: 2) |
| `IMG_5755.MOV` | 動画 | 17.9 MB | day 2: orbit of the rig for the Object Capture scan (location metadata zeroed: 2) |
| `IMG_5759.MOV` | 動画 | 68.1 MB | day 2: propeller off, tape flag, from above (60 fps): K, rotor J (location metadata zeroed: 2) |
| `IMG_5769.MOV` | 動画 | 58.2 MB | day 2: thrust on the balance 100 -> 40 % (first kT) (location metadata zeroed: 2) |
| `IMG_5778.MOV` | 動画 | 36.5 MB | day 2: orbit of the propeller alone + 10-yen coin -> pitch 18 deg (location metadata zeroed: 2) |
| `IMG_5779.MOV` | 動画 | 159.8 MB | day 2: forward / reverse x3 on the balance (reverse jet returns to the pan) (location metadata zeroed: 2) |
| `IMG_5780.MOV` | 動画 | 104.0 MB | day 2: propeller off, forward / reverse x4 (motor's own asymmetry) (location metadata zeroed: 2) |
| `IMG_5781.MOV` | 動画 | 15.4 MB | day 2: boot-sequence button over Web Serial, balance tared (location metadata zeroed: 2) |
| `IMG_5782.MOV` | 動画 | 41.4 MB | day 2: orbit of the rig on the balance (not processed) (location metadata zeroed: 2) |
| `IMG_5785.MOV` | 動画 | 115.9 MB | day 2: steady thrust steps 100/80/60/50/40 % x2 with TEL -> Re-dependent lift (location metadata zeroed: 2) |
| `scan_rig_IMG_5755.zip` | 3D スキャン | 123.1 MB | Object Capture of the whole rig (IMG_5755, 159 frames): usdz, obj/mtl, textures, frames, scan.swift, alignment intermediates |
| `scan_prop_IMG_5778.zip` | 3D スキャン | 191.8 MB | Object Capture of the propeller alone (IMG_5778, 230 frames): usdz, obj/mtl, textures, frames, pitch/section analysis |
| `analysis_scratch_day1.zip` | 作業用フォルダ | 51.8 MB | day-1/2 morning scratch folder as it was (audio wav, frames, montages, intermediates, scripts) |
| `analysis_scratch_day2.zip` | 作業用フォルダ | 139.1 MB | day-2 afternoon scratch folder (frame sheets, display crops, comb results, BEMT probes) |
| `session_day1_2026-10-28_29_raw.jsonl.gz` | 会話の生ログ | 32.0 MB | raw Claude Code session log, day1_2026-10-28_29 (email, home path, HPC host/user removed) |
| `session_day2_2026-10-29_raw.jsonl.gz` | 会話の生ログ | 11.5 MB | raw Claude Code session log, day2_2026-10-29 (email, home path, HPC host/user removed) |

## このフォルダ(27 個)

| ファイル | 大きさ | 内容 |
|---|---|---|
| [`photos/IMG_5750.jpg`](photos/IMG_5750.jpg) | 3.3 MB | rig before the scan (HEIC -> JPEG, metadata removed) |
| [`photos/IMG_5751.jpg`](photos/IMG_5751.jpg) | 2.7 MB | rig, propeller on the cup (HEIC -> JPEG, metadata removed) |
| [`photos/IMG_5752.jpg`](photos/IMG_5752.jpg) | 3.7 MB | rig (HEIC -> JPEG, metadata removed) |
| [`photos/IMG_5753.jpg`](photos/IMG_5753.jpg) | 3.3 MB | rig (HEIC -> JPEG, metadata removed) |
| [`photos/IMG_5754.jpg`](photos/IMG_5754.jpg) | 2.7 MB | rig from directly above (propeller diameter) (HEIC -> JPEG, metadata removed) |
| [`photos/IMG_5760.jpg`](photos/IMG_5760.jpg) | 5.1 MB | resistors for the ADC probe (HEIC -> JPEG, metadata removed) |
| [`photos/IMG_5761.jpg`](photos/IMG_5761.jpg) | 4.6 MB | resistors (HEIC -> JPEG, metadata removed) |
| [`photos/IMG_5762.jpg`](photos/IMG_5762.jpg) | 4.0 MB | resistors (HEIC -> JPEG, metadata removed) |
| [`photos/IMG_5763.jpg`](photos/IMG_5763.jpg) | 4.6 MB | resistors (HEIC -> JPEG, metadata removed) |
| [`photos/IMG_5764.jpg`](photos/IMG_5764.jpg) | 4.8 MB | resistors (HEIC -> JPEG, metadata removed) |
| [`photos/IMG_5774.jpg`](photos/IMG_5774.jpg) | 2.4 MB | propeller from the side with a 10-yen coin (pitch question) |
| [`chat/day2_chat_1.jpg`](chat/day2_chat_1.jpg) | 0.7 MB | image pasted in the day-2 chat |
| [`chat/day2_chat_2.jpg`](chat/day2_chat_2.jpg) | 1.1 MB | image pasted in the day-2 chat |
| [`chat/day2_chat_3.jpg`](chat/day2_chat_3.jpg) | 1.0 MB | image pasted in the day-2 chat (wiring) |
| [`chat/day2_inline_1.webp`](chat/day2_inline_1.webp) | 0.4 MB | inline image, day-2 chat |
| [`chat/day2_inline_2.webp`](chat/day2_inline_2.webp) | 0.2 MB | inline image, day-2 chat |
| [`chat/prop_side_10yen.webp`](chat/prop_side_10yen.webp) | 0.2 MB | propeller side view sent for the pitch (day 2 afternoon) |
| [`chat/prop_top_10yen.webp`](chat/prop_top_10yen.webp) | 0.4 MB | propeller top view sent for the pitch (day 2 afternoon) |
| [`3d/rig_scan_views.png`](3d/rig_scan_views.png) | 0.3 MB | rig scan, levelled and scaled |
| [`3d/rig_scan_top.png`](3d/rig_scan_top.png) | 0.4 MB | rig scan from above |
| [`3d/rig_scan_prop_region.png`](3d/rig_scan_prop_region.png) | 0.3 MB | propeller region of the rig scan (not reconstructable) |
| [`3d/prop_scan_top.png`](3d/prop_scan_top.png) | 0.2 MB | propeller scan from above (true colour, height) |
| [`3d/prop_scan_unwrap_first_try.png`](3d/prop_scan_unwrap_first_try.png) | 35 kB | first cylinder cut (wrong radius) |

会話の記録(読みやすい版)は [`../transcripts/`](../transcripts/) にあります。
